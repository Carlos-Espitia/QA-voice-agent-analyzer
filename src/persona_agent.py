import logging

from anthropic import Anthropic

from src import config
from src.scenarios import build_system_prompt

logger = logging.getLogger("persona_agent")

_client = Anthropic(api_key=config.ANTHROPIC_API_KEY)


class PersonaAgent:
    """Drives the simulated patient's side of one call.

    Holds the conversation history for a single scenario and asks Claude,
    on each agent turn, what the patient should say next — rather than a
    fixed script, so the bot can adapt to whatever the real agent actually
    says (the challenge calls this "active steering toward the intended
    test-case outcome").
    """

    def __init__(self, scenario_name: str, persona_name: str | None = None):
        self._system_prompt = build_system_prompt(scenario_name, persona_name)
        self._history: list[dict] = []

    def respond_to(self, agent_utterance: str) -> str:
        self._history.append({"role": "user", "content": agent_utterance}) # Gives conversation history context to LLM 
        message = _client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=200,
            system=self._system_prompt,
            messages=self._history,
        )
        reply = message.content[0].text.strip()
        self._history.append({"role": "assistant", "content": reply})
        logger.info("Persona reply: %s", reply)
        return reply
