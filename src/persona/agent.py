import logging

from anthropic import Anthropic

from src import config
from src.persona.personas import get_persona
from src.persona.scenarios import BASE_RULES, get_scenario_text

logger = logging.getLogger("persona_agent")

_client = Anthropic(api_key=config.ANTHROPIC_API_KEY)


class PersonaAgent:
    """Drives the simulated caller's side of one call.

    Holds the conversation history for a single scenario and asks Claude,
    on each agent turn, what the caller should say next — rather than a
    fixed script, so the bot can adapt to whatever the real agent actually
    says (the challenge calls this "active steering toward the intended
    test-case outcome").
    """

    def __init__(self, scenario_id: str, persona_name: str, call_sid: str | None = None):
        persona = get_persona(persona_name)
        scenario_text = get_scenario_text(scenario_id)
        self._system_prompt = persona["prompt"] + "\n" + BASE_RULES + scenario_text
        self._history: list[dict] = []
        self._call_sid = call_sid

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
        logger.info("[%s] Persona reply: %s", self._call_sid, reply)
        return reply
