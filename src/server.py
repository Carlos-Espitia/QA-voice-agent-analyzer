import asyncio
import base64
import json
import logging

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from twilio.twiml.voice_response import Connect, VoiceResponse

from src import config
from src.persona_agent import PersonaAgent
from src.stt import StreamingTranscriber
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
    response = VoiceResponse()
    connect = Connect()
    ws_url = config.PUBLIC_BASE_URL.replace("https://", "wss://").replace("http://", "ws://")
    stream = connect.stream(url=f"{ws_url}/media-stream")
    stream.parameter(name="scenario", value=scenario)
    response.append(connect)
    return Response(content=str(response), media_type="application/xml")


# This websocket handles real time conversation
@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    await websocket.accept()
    loop = asyncio.get_event_loop()
    stream_sid: str | None = None
    persona: PersonaAgent | None = None

    # This function handles real time conversion text to speech by using ElevenLabs
    async def speak(text: str):
        nonlocal stream_sid
        if not stream_sid:
            return
        logger.info("Bot speaking: %s", text)
        for chunk in synthesize_ulaw_chunks(text): # This function converts text to speech as live streaming and returning chunks of audio
            for i in range(0, len(chunk), FRAME_SIZE): # Twilio expects audio sent over the media stream in small packets.
                frame = chunk[i : i + FRAME_SIZE] # UNderstand how a frame works
                if not frame:
                    continue
                await websocket.send_json(
                    {
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {"payload": base64.b64encode(frame).decode("ascii")},
                    }
                )


    def on_utterance_end(transcript: str):
        logger.info("Agent said: %s", transcript)
        reply = persona.respond_to(transcript)
        asyncio.run_coroutine_threadsafe(speak(reply), loop)

    transcriber = StreamingTranscriber(on_utterance_end=on_utterance_end) # better understand how this works

    # The conversation loop
    try:
        while True:
            message = await websocket.receive_text() # receives text from twillio api which uses ngrok connection
            data = json.loads(message)
            event = data.get("event")

            if event == "start":
                stream_sid = data["start"]["streamSid"]
                scenario = data["start"].get("customParameters", {}).get("scenario", "smoke_test")
                persona = PersonaAgent(scenario)
                logger.info("Stream started: %s scenario=%s", stream_sid, scenario)
            elif event == "media":
                # twillio sends mu-law audio encoded in base64 which needs to be decoded to get raw mu-law bytes to then give to deepgram
                payload = base64.b64decode(data["media"]["payload"]) 
                transcriber.send_audio(payload)
            elif event == "stop":
                logger.info("Stream stopped")
                break
    except WebSocketDisconnect:
        logger.info("Websocket disconnected")
    finally:
        transcriber.close()
