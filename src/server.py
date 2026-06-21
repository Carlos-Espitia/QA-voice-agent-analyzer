import asyncio
import base64
import json
import logging
import threading

import requests
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from twilio.twiml.voice_response import Connect, VoiceResponse

from src import config
from src.persona_agent import PersonaAgent
from src.scenarios import get_persona
from src.stt import StreamingTranscriber
from src.transcript import CallTranscript, call_dir
from src.tts import synthesize_ulaw_chunks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")

app = FastAPI()

# mu-law is a type of audio
# Twilio sends mu-law audio in 20ms frames (160 bytes each at 8kHz).
FRAME_SIZE = 160


@app.post("/twiml/voice")
async def twiml_voice(request: Request):
    """Twilio fetches this when the outbound call connects; it tells Twilio
    to open a Media Stream back to our websocket so we get raw call audio
    instead of being limited to turn-based <Gather>/<Say>."""
    scenario = request.query_params.get("scenario", "smoke_test")
    persona = request.query_params.get("persona", "")
    response = VoiceResponse()
    connect = Connect()
    ws_url = config.PUBLIC_BASE_URL.replace("https://", "wss://").replace("http://", "ws://")
    stream = connect.stream(url=f"{ws_url}/media-stream")
    stream.parameter(name="scenario", value=scenario)
    stream.parameter(name="persona", value=persona)
    response.append(connect)
    return Response(content=str(response), media_type="application/xml")

# This code handles recording calls
@app.post("/recording-status") # This HTTP POST request is invoked by Twillio after a call ends
async def recording_status(request: Request):
    """Twilio calls this once the dual-channel call recording is ready.
    We download it immediately so the mp3 lives in recordings/ alongside
    the transcript, both keyed by the same CallSid."""
    form = await request.form()
    call_sid = form.get("CallSid") # Gets ended call ID
    recording_url = form.get("RecordingUrl")
    if not recording_url:
        return Response(status_code=200)

    resp = requests.get(
        f"{recording_url}.mp3",
        auth=(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN),
    )
    resp.raise_for_status()
    out_path = call_dir(call_sid) / "recording.mp3"
    out_path.write_bytes(resp.content) # saves mp3 file in recordings
    logger.info("Saved recording: %s", out_path)
    return Response(status_code=200)


# This websocket handles real time conversation
@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    await websocket.accept()
    loop = asyncio.get_event_loop()
    stream_sid: str | None = None
    persona: PersonaAgent | None = None
    transcript: CallTranscript | None = None
    voice_id: str | None = None
    barge_in = threading.Event()

    # This function handles real time conversion text to speech by using ElevenLabs
    async def speak(text: str):
        nonlocal stream_sid
        if not stream_sid:
            return
        logger.info("Bot speaking: %s", text)
        barge_in.clear()
        for chunk in synthesize_ulaw_chunks(text, voice_id):  # streams audio chunks as ElevenLabs generates them
            for i in range(0, len(chunk), FRAME_SIZE):  # Twilio expects audio sent over the media stream in small packets.
                if barge_in.is_set():
                    # We send TTS frames much faster than real playback speed,
                    # so most of a short reply is already sitting in Twilio's
                    # playback buffer by the time we detect barge-in — just
                    # stopping our send loop doesn't un-send that audio. The
                    # "clear" event tells Twilio to drop whatever's buffered
                    # and unplayed for this stream right now.
                    logger.info("Bot interrupted (barge-in detected)")
                    await websocket.send_json({"event": "clear", "streamSid": stream_sid})
                    return
                frame = chunk[i : i + FRAME_SIZE]
                if not frame:
                    continue
                await websocket.send_json(
                    {
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {"payload": base64.b64encode(frame).decode("ascii")},
                    }
                )

    def on_utterance_end(agent_text: str):
        logger.info("Agent said: %s", agent_text)
        transcript.add_turn("agent", agent_text)
        reply = persona.respond_to(agent_text)
        transcript.add_turn("bot", reply)
        asyncio.run_coroutine_threadsafe(speak(reply), loop)

    transcriber = StreamingTranscriber(
        on_utterance_end=on_utterance_end,
        on_speech_activity=barge_in.set,
    )

    # The conversation loop
    try:
        while True:
            message = await websocket.receive_text()  # receives text frames pushed by Twilio over the tunnel
            data = json.loads(message)
            event = data.get("event")

            if event == "start":
                stream_sid = data["start"]["streamSid"]
                call_sid = data["start"]["callSid"]
                params = data["start"].get("customParameters", {})
                scenario = params.get("scenario", "smoke_test")
                persona_name = params.get("persona") or None
                persona = PersonaAgent(scenario, persona_name)
                voice_id = get_persona(persona_name)["voice_id"]
                transcript = CallTranscript(call_sid, scenario, persona_name)
                logger.info(
                    "Stream started: %s scenario=%s persona=%s call_sid=%s",
                    stream_sid, scenario, persona_name, call_sid,
                )
            elif event == "media":
                # Twilio sends mu-law audio base64-encoded inside the JSON text frame; decode to raw bytes for Deepgram.
                payload = base64.b64decode(data["media"]["payload"])
                transcriber.send_audio(payload)
            elif event == "stop":
                logger.info("Stream stopped")
                break
    except WebSocketDisconnect:
        logger.info("Websocket disconnected")
    finally: # Runs this code when streaming ends or call ends and saves transcript
        transcriber.close()
        if transcript:
            path = transcript.save()
            logger.info("Saved transcript: %s", path)
