# Architecture

## What this is

A voice QA bot that places real phone calls to an automated phone agent
(currently PGAI's test line), plays a simulated caller through a full
multi-turn conversation, and saves the audio + transcript for analysis.
The goal is to find real conversational bugs in the agent being tested,
while itself sounding natural enough that the call doesn't fall apart —
that second part drove most of the architectural decisions below.

## Call flow

```
call_runner.py ──places call──► Twilio ──dials──► target agent (PGAI)
                                    │
                                    │ (once answered)
                                    ▼
                          POST /twiml/voice  ──► server.py
                                    │
                          returns <Connect><Stream> TwiML
                                    │
                                    ▼
                    Twilio opens a Media Stream WebSocket
                       to /media-stream on this server
                                    │
        ┌───────────────────────────┴───────────────────────────┐
        │                     server.py (per call)                │
        │                                                          │
        │  inbound mu-law audio (the agent's voice)                │
        │     → voice/stt.py (Deepgram streaming transcription)    │
        │     → on a detected turn-end → persona/agent.py           │
        │         (Claude decides what the caller says next,       │
        │          given the scenario + persona + history)          │
        │     → voice/tts.py (ElevenLabs streams audio for the      │
        │         reply, ulaw_8000 — no resampling needed)           │
        │     → sent back over the same Media Stream                │
        │                                                          │
        │  every turn is appended to transcript.py's in-memory      │
        │  CallTranscript and written to disk when the call ends   │
        └──────────────────────────────────────────────────────────┘
                                    │
                      Twilio finishes the dual-channel
                       recording, POSTs /recording-status
                                    │
                                    ▼
                  recording.mp3 + transcript.json saved under
                       recordings/<call_sid>/
```

## Key design decisions

**Twilio Media Streams instead of `<Gather>`/`<Say>`.** Twilio's simple
voice webhooks are turn-based and round-trip through HTTP per turn — too
slow and clunky for natural conversation. Media Streams gives raw audio
over a persistent WebSocket, so this project controls STT/TTS timing and
turn-taking directly, which is what a natural-sounding conversation needs.

**Deepgram streaming STT, not batch transcription.** Streaming partial
transcripts let the bot detect when the other agent stops talking
without waiting for a full utterance to be processed offline — necessary
for any kind of responsive turn-taking.

**`UtteranceEnd` event, not just `speech_final`.** Initially turn-taking
relied on Deepgram's `speech_final` flag on the `Transcript` event. In
practice this sometimes never fired even after several seconds of real
silence (observed directly: the agent would ask a question and the bot
would just never respond). Deepgram's dedicated `UtteranceEnd` event,
driven by its own silence-duration timer (`utterance_end_ms`) independent
of `speech_final`, turned out to be the reliable signal. `stt.py` now
buffers finalized transcript fragments and flushes them on `UtteranceEnd`.

**Personas and scenarios are separate concerns.** A *persona*
(`persona/personas.py`) is who is calling — a name, date of birth, phone
number, speaking style, and an ElevenLabs voice. A *scenario*
(`persona/scenarios.py`) is what they want — a goal description tied to a
domain (`medical`, `qa`). Any persona can run any scenario
(`--persona jordan_impatient --scenario qa/jailbreak_attempt`). This
split exists because the original target (a medical scheduling agent) is
just one domain this tool could test — the personas have no medical
language baked in, so adding a new domain is just a new scenario goal
text, not a new persona.

**Claude drives the persona, not a fixed script.** Each scenario is a
goal description, not a transcript to play back. `persona/agent.py` feeds
the full conversation history to Claude on every turn and asks what the
caller should say next, so the bot adapts to whatever the agent actually
says rather than following a script that breaks the moment the agent
deviates from the expected path. This is also what makes the QA/edge-case
scenarios (jailbreak attempts, contradicting earlier answers, vague
requests) possible at all — a scripted bot couldn't react to the agent's
specific responses.

**Twilio's built-in dual-channel recording, not custom audio capture.**
`call_runner.py` requests `record=True, recording_channels="dual"` and a
`recording_status_callback`. This is simpler and more reliable than
buffering and muxing the audio ourselves, since Twilio already has both
sides of the call audio.

**Real background noise mixing for the noise QA scenario.** For
`qa/background_noise`, synthetic white noise is mixed directly into the
outgoing mu-law audio (`voice/tts.py`, via `audioop`: decode → add noise
in linear PCM → re-encode) rather than just describing noise in the
prompt — an actual audio-level distortion is a more meaningful test of
the target agent's STT robustness than a caller merely saying "it's
noisy here."

**Every log line is tagged with `call_sid`.** Once calls started running
concurrently, unlabeled log lines from different calls became impossible
to tell apart in a shared terminal. Every log line in `server.py`,
`persona/agent.py`, and `voice/stt.py` now includes the call's SID.

## Known limitations

**Barge-in / talk-over is not fully solved.** The bot detects when the
other agent starts talking again mid-reply (`barge_in` event from
Deepgram) and sends Twilio's `clear` event to flush queued audio, but
since TTS frames are sent to Twilio much faster than real playback speed,
most of a short reply may already be queued by the time barge-in is
detected — there's often little left for `clear` to flush. A real fix
requires pacing frame-sending to real playback time
(`await asyncio.sleep(0.02)` per 20ms frame). Other deferred improvements
include adaptive turn-taking thresholds (rather than Deepgram's fixed
`endpointing`/`utterance_end_ms`) and proper flow control on TTS
streaming.

**Outbound call concurrency is capped by the Twilio account tier.**
Firing 10 calls simultaneously resulted in only 3 connecting; the other 7
were queued and failed with Twilio error 10004 before ever dialing out.
This is an account-level limit, not an application bug — calls should be
run sequentially or in small batches within that cap.

**No automatic detection of conversation breakdown.** If the bot's
persona produces an incoherent or out-of-character reply, nothing
currently flags it — transcripts have to be reviewed manually.
