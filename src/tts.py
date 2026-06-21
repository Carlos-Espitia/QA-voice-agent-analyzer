from elevenlabs.client import ElevenLabs

from src import config

_client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)


def synthesize_ulaw_chunks(text: str):
    """Yields raw mu-law 8kHz audio bytes for the given text.

    We ask ElevenLabs for ulaw_8000 output directly so the bytes can be
    base64-encoded and sent straight back over the Twilio Media Stream
    with no resampling/format conversion on our side.
    """
    stream = _client.text_to_speech.convert(
        voice_id=config.ELEVENLABS_VOICE_ID,
        model_id="eleven_turbo_v2_5",
        text=text,
        output_format="ulaw_8000",
    )
    for chunk in stream:
        if chunk:
            yield chunk # streams audio chunks for speak() function for live low latency speach responses
