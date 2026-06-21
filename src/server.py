import asyncio
import base64
import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from twilio.twiml.voice_response import Connect, VoiceResponse

from src import config
from src.stt import StreamingTranscriber
from src.tts import synthesize_ulaw_chunks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")

app = FastAPI()

# Twilio sends mu-law audio in 20ms frames (160 bytes each at 8kHz).
FRAME_SIZE = 160


@app.post("/twiml/voice")
async def twiml_voice():
    """Twilio fetches this when the outbound call connects; it tells Twilio
    to open a Media Stream back to our websocket so we get raw call audio
    instead of being limited to turn-based <Gather>/<Say>."""
    response = VoiceResponse()
    connect = Connect()
    ws_url = config.PUBLIC_BASE_URL.replace("https://", "wss://").replace("http://", "ws://")
    connect.stream(url=f"{ws_url}/media-stream")
    response.append(connect)
    return Response(content=str(response), media_type="application/xml")


@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    await websocket.accept()
    loop = asyncio.get_event_loop()
    stream_sid: str | None = None

    async def speak(text: str):
        nonlocal stream_sid
        if not stream_sid:
            return
        logger.info("Bot speaking: %s", text)
        for chunk in synthesize_ulaw_chunks(text):
            for i in range(0, len(chunk), FRAME_SIZE): # Twillio expects audio sent over media stream in small packets
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

    def on_utterance_end(transcript: str):
        logger.info("Agent said: %s", transcript)
        # Phase 1: prove the loop with a canned reply. Phase 2 swaps this
        # for a Claude-generated response based on the transcript + persona.
        asyncio.run_coroutine_threadsafe(
            speak("Yes, that works for me, thank you."), loop
        )

    transcriber = StreamingTranscriber(on_utterance_end=on_utterance_end)

    try:
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)
            event = data.get("event")

            if event == "start":
                stream_sid = data["start"]["streamSid"]
                logger.info("Stream started: %s", stream_sid)
            elif event == "media":
                payload = base64.b64decode(data["media"]["payload"])
                transcriber.send_audio(payload)
            elif event == "stop":
                logger.info("Stream stopped")
                break
    except WebSocketDisconnect:
        logger.info("Websocket disconnected")
    finally:
        transcriber.close()
