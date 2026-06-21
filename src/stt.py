import logging
from collections.abc import Callable

from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveOptions,
    LiveTranscriptionEvents,
)

from src import config

logger = logging.getLogger("stt")


class StreamingTranscriber:
    """Wraps a single Deepgram live-transcription connection for one call.

    Deepgram's `speech_final` flag (vs. just `is_final`) tells us the speaker
    paused long enough that this is a genuine end-of-turn, not just a pause
    mid-sentence — that's what we use to decide "the agent finished talking,
    now generate our reply" instead of guessing from raw silence duration.
    """

    def __init__(self, on_utterance_end: Callable[[str], None]):
        self._on_utterance_end = on_utterance_end
        client = DeepgramClient(
            config.DEEPGRAM_API_KEY, DeepgramClientOptions(options={"keepalive": "true"})
        )
        self._connection = client.listen.websocket.v("1")
        self._connection.on(LiveTranscriptionEvents.Transcript, self._on_transcript)
        self._connection.on(LiveTranscriptionEvents.Open, self._on_open)
        self._connection.on(LiveTranscriptionEvents.Error, self._on_error)
        self._connection.on(LiveTranscriptionEvents.Close, self._on_close)

        options = LiveOptions(
            model="nova-2",
            language="en-US",
            encoding=config.AUDIO_ENCODING,
            sample_rate=config.AUDIO_SAMPLE_RATE,
            channels=1,
            punctuate=True,
            interim_results=True,
            endpointing=700,
            utterance_end_ms="1000",
        )
        started = self._connection.start(options)
        logger.info("Deepgram connection start() returned: %s", started)

    def _on_open(self, *_args, **_kwargs):
        logger.info("Deepgram connection opened")

    def _on_error(self, *_args, **kwargs):
        logger.error("Deepgram error: %s %s", _args, kwargs)

    def _on_close(self, *_args, **kwargs):
        logger.info("Deepgram connection closed: %s %s", _args, kwargs)

    def _on_transcript(self, _, result, **kwargs):
        alt = result.channel.alternatives[0]
        if alt.transcript.strip():
            logger.info(
                "Transcript (is_final=%s speech_final=%s): %s",
                result.is_final,
                result.speech_final,
                alt.transcript,
            )
        if result.speech_final and alt.transcript.strip():
            self._on_utterance_end(alt.transcript.strip())

    def send_audio(self, mulaw_bytes: bytes):
        self._connection.send(mulaw_bytes)

    def close(self):
        self._connection.finish()
