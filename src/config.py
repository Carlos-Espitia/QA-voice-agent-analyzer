import os

from dotenv import load_dotenv

load_dotenv()

TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_PHONE_NUMBER = os.environ["TWILIO_PHONE_NUMBER"]
PGAI_TEST_NUMBER = os.environ["PGAI_TEST_NUMBER"]
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")

DEEPGRAM_API_KEY = os.environ["DEEPGRAM_API_KEY"]

ELEVENLABS_API_KEY = os.environ["ELEVENLABS_API_KEY"]
ELEVENLABS_VOICE_ID = os.environ["ELEVENLABS_VOICE_ID"]

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

# Twilio Media Streams send/expect 8kHz mono mu-law audio.
AUDIO_SAMPLE_RATE = 8000
AUDIO_ENCODING = "mulaw"
