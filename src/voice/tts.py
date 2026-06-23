import audioop
import random

from elevenlabs.client import ElevenLabs

from src import config

_client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)

# Linear PCM sample width (bytes) audioop needs for ulaw<->lin conversion.
_PCM_WIDTH = 2


def _white_noise(num_samples: int, amplitude: int) -> bytes:
    """16-bit signed linear PCM white noise, one sample per mu-law byte."""
    samples = bytearray()
    for _ in range(num_samples):
        samples += random.randint(-amplitude, amplitude).to_bytes(
            2, byteorder="little", signed=True
        )
    return bytes(samples)


def _add_background_noise(mulaw_chunk: bytes, amplitude: int) -> bytes:
    """Mixes white noise into a mu-law chunk by decoding to linear PCM,
    summing with generated noise, and re-encoding — a real audio-level
    distortion (not just a textual description) to test whether the
    agent's STT holds up against a noisy line."""
    lin = audioop.ulaw2lin(mulaw_chunk, _PCM_WIDTH)
    noise = _white_noise(len(mulaw_chunk), amplitude)
    mixed = audioop.add(lin, noise, _PCM_WIDTH)
    return audioop.lin2ulaw(mixed, _PCM_WIDTH)


def synthesize_ulaw_chunks(
    text: str, voice_id: str | None = None, noise_amplitude: int = 0
):
    """Yields raw mu-law 8kHz audio bytes for the given text.

    We ask ElevenLabs for ulaw_8000 output directly so the bytes can be
    base64-encoded and sent straight back over the Twilio Media Stream
    with no resampling/format conversion on our side.

    noise_amplitude > 0 mixes synthetic white noise into the audio before
    yielding it, for the background-noise QA scenario.
    """
    stream = _client.text_to_speech.convert(
        voice_id=voice_id or config.ELEVENLABS_VOICE_ID,
        model_id="eleven_turbo_v2_5",
        text=text,
        output_format="ulaw_8000",
    )
    for chunk in stream:
        if chunk:
            if noise_amplitude:
                chunk = _add_background_noise(chunk, noise_amplitude)
            yield chunk # streams audio chunks for speak() function for live low latency speach responses
