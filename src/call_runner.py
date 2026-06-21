import argparse
import logging

from twilio.rest import Client

from src import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("call_runner")


def place_call() -> str:
    if not config.PUBLIC_BASE_URL:
        raise RuntimeError(
            "PUBLIC_BASE_URL is not set in .env — set it to your ngrok https URL first."
        )
    client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    call = client.calls.create(
        to=config.PGAI_TEST_NUMBER,
        from_=config.TWILIO_PHONE_NUMBER,
        url=f"{config.PUBLIC_BASE_URL}/twiml/voice",
    )
    logger.info("Call placed: sid=%s to=%s", call.sid, config.PGAI_TEST_NUMBER)
    return call.sid


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        default="smoke_test",
        help="Scenario name (ignored in Phase 1 — added in Phase 4).",
    )
    args = parser.parse_args()
    place_call()
