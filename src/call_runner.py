import argparse
import logging

from twilio.rest import Client

from src import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("call_runner")


def place_call(scenario: str, persona: str | None = None) -> str:
    if not config.PUBLIC_BASE_URL:
        raise RuntimeError(
            "PUBLIC_BASE_URL is not set in .env — set it to your ngrok https URL first."
        )
    client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    twiml_url = f"{config.PUBLIC_BASE_URL}/twiml/voice?scenario={scenario}"
    if persona:
        twiml_url += f"&persona={persona}"
    call = client.calls.create(
        to=config.PGAI_TEST_NUMBER,
        from_=config.TWILIO_PHONE_NUMBER,
        url=twiml_url,
        record=True,
        recording_channels="dual",
        recording_status_callback=f"{config.PUBLIC_BASE_URL}/recording-status",
        recording_status_callback_event=["completed"],
    )
    logger.info(
        "Call placed: sid=%s to=%s scenario=%s persona=%s",
        call.sid, config.PGAI_TEST_NUMBER, scenario, persona,
    )
    return call.sid


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="smoke_test", help="Scenario name from src/scenarios")
    parser.add_argument(
        "--persona",
        default=None,
        help="Persona name from src/scenarios (defaults to alex_default if omitted)",
    )
    args = parser.parse_args()
    place_call(args.scenario, args.persona)
