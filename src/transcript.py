import json
from datetime import datetime, timezone
from pathlib import Path

CALLS_DIR = Path(__file__).resolve().parent.parent / "recordings"


def call_dir(call_sid: str) -> Path:
    """Each call gets its own folder: recordings/<call_sid>/ holding both
    transcript.json and recording.mp3, so a call's deliverables stay together."""
    path = CALLS_DIR / call_sid
    path.mkdir(parents=True, exist_ok=True)
    return path


class CallTranscript:
    """Accumulates one call's turns in memory and writes them to
    recordings/<call_sid>/transcript.json once the call ends."""

    def __init__(self, call_sid: str, scenario: str, persona: str | None = None):
        self.call_sid = call_sid
        self.scenario = scenario
        self.persona = persona
        self.turns: list[dict] = []

    def add_turn(self, speaker: str, text: str):
        self.turns.append(
            {
                "speaker": speaker,
                "text": text,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def save(self):
        path = call_dir(self.call_sid) / "transcript.json"
        path.write_text(
            json.dumps(
                {
                    "call_sid": self.call_sid,
                    "scenario": self.scenario,
                    "persona": self.persona,
                    "turns": self.turns,
                },
                indent=2,
            )
        )
        return path
