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

    def __init__(
        self,
        on_utterance_end: Callable[[str], None],
        on_speech_activity: Callable[[], None] | None = None,
    ):
        self._on_utterance_end = on_utterance_end
        self._on_speech_activity = on_speech_activity
        self._buffer: list[str] = []
        # Set by the server once it knows the call's CallSid (the transcriber
        # is constructed before the "start" event arrives) — purely for
        # tagging log lines so concurrent calls' logs stay distinguishable.
        self.call_sid: str | None = None
        client = DeepgramClient(
            config.DEEPGRAM_API_KEY, DeepgramClientOptions(options={"keepalive": "true"})
        )
        self._connection = client.listen.websocket.v("1")
        self._connection.on(LiveTranscriptionEvents.Transcript, self._on_transcript)
        self._connection.on(LiveTranscriptionEvents.UtteranceEnd, self._on_utterance_end_event)
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
        if alt.transcript.strip() and self._on_speech_activity:
            # Fires on interim results too — earliest possible signal that the
            # agent is making sound, used by the server to cut off our TTS
            # playback if we're talking over them.
            self._on_speech_activity()
        if result.is_final and alt.transcript.strip():
            logger.info(
                "[%s] Transcript (speech_final=%s): %s",
                self.call_sid, result.speech_final, alt.transcript,
            )
            self._buffer.append(alt.transcript.strip())
        if result.speech_final:
            self._flush()

    def _on_utterance_end_event(self, *_args, **kwargs):
        # Fires from Deepgram's own silence-duration timer (utterance_end_ms),
        # independent of speech_final — speech_final can fail to fire even
        # after a long pause, so this is the reliable end-of-turn signal.
        logger.info("[%s] Deepgram UtteranceEnd event", self.call_sid)
        self._flush()

    def _flush(self):
        if not self._buffer:
            return
        text = " ".join(self._buffer).strip()
        self._buffer = []
        if text:
            self._on_utterance_end(text)

    def send_audio(self, mulaw_bytes: bytes):
        self._connection.send(mulaw_bytes)

    def close(self):
        self._connection.finish()
