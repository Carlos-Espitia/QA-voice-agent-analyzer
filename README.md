# QA Voice Agent Analyzer

A voice bot that places real phone calls to an automated phone agent, plays a
simulated caller through a natural multi-turn conversation, and saves the
audio + transcript for QA analysis. Built against PGAI's test voice agent,
but the persona/scenario design generalizes to testing any phone agent.

## How it works (short version)

1. We place an outbound call via **Twilio** to the target number, and open a **Media Stream**
   (a WebSocket carrying raw call audio both ways).
2. Incoming audio (the agent's voice) is transcribed live by **Deepgram**.
3. Once the agent finishes a turn, the transcript + conversation history is sent to **Claude**,
   which is playing a caller persona pursuing a specific scenario goal, and decides what to say next.
4. Claude's reply is converted to speech by **ElevenLabs** and streamed back over the same
   Media Stream.
5. Twilio's dual-channel call recording and the full turn-by-turn transcript are saved to
   `recordings/<call_sid>/` once the call ends.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design rationale and known limitations.

## Setup

1. `python -m venv .venv && .venv\Scripts\activate` (Windows) or `source .venv/bin/activate` (mac/linux)
2. `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill in your API keys (Twilio, Deepgram, ElevenLabs, Anthropic).
4. Start an ngrok tunnel: `ngrok http 8000`, then put the resulting HTTPS URL into `PUBLIC_BASE_URL` in `.env`.
5. Start the server: `uvicorn src.server:app --port 8000`
6. In a second terminal, place a call:
   ```
   python -m src.call_runner --scenario medical/schedule_new --persona alex_default
   ```

`PUBLIC_BASE_URL` is read once at server startup — restart the server after changing it
(e.g. when ngrok's free-tier URL changes between sessions).

## Personas and scenarios

A **persona** is who is calling — identity (name, date of birth, phone number), speaking
style, and an ElevenLabs voice. Defined in `src/persona/personas.py`:

- `alex_default` — calm, average-pace caller
- `jordan_impatient` — terse, in a hurry
- `william_elderly` — speaks slowly, sometimes asks for things to be repeated

A **scenario** is what the caller wants, grouped by domain, defined in
`src/persona/scenarios.py`. A scenario id is `<domain>/<key>`:

- `medical/*` — happy-path goals: `schedule_new`, `reschedule`, `cancel`, `refill_request`,
  `hours_question`, `insurance_question`, `location_question`
- `qa/*` — adversarial/edge-case goals aimed at finding bugs: `vague_request`,
  `changes_mind`, `unprepared_question`, `contradictory_info`, `double_booking_attempt`,
  `out_of_scope_request`, `ambiguous_date`, `wrong_info_correction`,
  `long_run_on_utterance`, `jailbreak_attempt`, `background_noise` (mixes real audio-level
  noise into the bot's speech, not just a text description)

Any persona can run any scenario — they're independent. Adding a new scenario is one line
in the relevant domain's `goals` dict; adding a new domain is copying one `_domain(...)`
block.

```
python -m src.call_runner --scenario qa/contradictory_info --persona william_elderly
```

## Output

Each call writes to `recordings/<call_sid>/`:

- `recording.mp3` — Twilio's dual-channel recording of the full call
- `transcript.json` — every turn (`agent`/`bot`), with text and timestamps, plus the
  scenario and persona used

## Project status

- 10 real calls placed and recorded against the PGAI test line; see [bug_report.md](bug_report.md)
  for findings.
- Known limitations (barge-in handling, account call-concurrency limits) are documented in
  [ARCHITECTURE.md](ARCHITECTURE.md).
