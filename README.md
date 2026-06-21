# QA Voice Agent Analyzer

An automated "patient" voice bot that calls Pretty Good AI's test voice agent, holds a
natural multi-turn phone conversation simulating realistic patient scenarios, and records
the call for QA analysis.

## How it works (short version)

1. We place an outbound call via **Twilio** to the target number, and open a **Media Stream**
   (a WebSocket carrying raw call audio both ways).
2. Incoming audio (the agent's voice) is transcribed live by **Deepgram**.
3. Once the agent finishes a turn, the transcript + conversation history is sent to **Claude**,
   which is playing a "patient" persona for the current scenario and decides what to say next.
4. Claude's reply is converted to speech by **ElevenLabs** and streamed back over the same
   Media Stream.
5. Both sides of the audio and the full transcript are saved to disk for later review.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design rationale.

## Setup

1. `python -m venv .venv && .venv\Scripts\activate` (Windows) or `source .venv/bin/activate` (mac/linux)
2. `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill in your API keys (Twilio, Deepgram, ElevenLabs, Anthropic).
4. Start an ngrok tunnel: `ngrok http 8000`, then put the resulting HTTPS URL into `PUBLIC_BASE_URL` in `.env`.
5. Start the server: `uvicorn src.server:app --port 8000`
6. In a second terminal, place a call: `python -m src.call_runner --scenario scheduling`

## Project status

This README will be filled in further as the project is built out (scenario list, bug report,
recordings index, etc.).
