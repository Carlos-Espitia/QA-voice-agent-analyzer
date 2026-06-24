## 0. Deepgram transcript drops trailing words mid-utterance (new top candidate — found organically)

Listening back to call `CA4b2c8b308b6fa0a614fce68a2e35cde8` against the actual recording
audio, the saved transcript cuts a sentence short:

> Agent (transcript): "Thank you for confirming. I have your phone number as five five
> five"
> Bot: "Yes, go ahead."

The agent's audio continues with the rest of the phone number digits, but the transcript
captured in `src/voice/stt.py` never includes them — the turn was flushed and handed to
the persona agent before Deepgram finished transcribing the full utterance. This isn't a
target-agent bug; it's a real gap in our own STT capture, and it's serious because it
means the persona's replies (and the bug report's conclusions) may be based on an
incomplete view of what the agent actually said.

Same pattern recurs in `CA40245d7272ca5239d39e76ab46df0c3c`:

> Agent (transcript): "Thank you for clarifying. I have your number as five five
> five"
> Bot: "Mm-hmm, go ahead."

Two separate calls cutting off mid-phone-number specifically suggests this isn't random —
phone-number readbacks are long enough, and numeric tokens may be finalized by Deepgram
in a way that makes the flush race more likely to land mid-sequence.

**Likely cause:** the turn-end flush (`UtteranceEnd` handling in `_on_utterance_end_event`)
fires before all finalized fragments for the utterance have arrived/been appended, or a
fragment is still in-flight (interim, not yet finalized) when the flush happens and gets
dropped instead of awaited.

**Why this one:** found live while reviewing real call audio (authentic, not staged),
has a concrete before/after (play the audio next to the transcript), and the fix is
contained to `stt.py`'s buffering/flush logic — fits in 5 minutes.

## 0.5. ElevenLabs TTS output glitches into gibberish on some replies (found organically)

In call `CA5a27cff1a8793dfd24d8ece34c6986fe`, right after the agent hangs up
("Hello. You've reached the Pretty Good AI test line. Goodbye."), the bot's next line
is transcribed as "Wait, what? That's it? I just need to reschedule an appointment.
Hello?" — but on the actual recording, that audio is garbled/gibberish, not clean
speech. The text sent to ElevenLabs was fine (it's the persona's intended reply); the
synthesized audio itself broke.

**Likely cause:** this reply was generated and queued for TTS right as the call was
ending (the agent's "Goodbye" had just played and the call/stream may have been
tearing down). Possible causes: the ElevenLabs stream got cut off mid-synthesis and
partial/corrupt audio chunks were sent anyway, or μ-law frames from two different
replies got interleaved/concatenated incorrectly in `speak()` once the Twilio stream
was closing.

**Why this one:** also found organically while reviewing real call audio, distinct
from the transcript-drop bug (this is on the *output* side, TTS/audio assembly, not
STT capture), and pairs naturally with end-of-call teardown behavior which is already
a known rough edge.

## 0.7. Deepgram is hardcoded to `en-US`, so the agent's Spanish disclaimer is never transcribed (found organically, likely root cause of early barge-in)

`src/voice/stt.py:49` sets `language="en-US"` on the `LiveOptions` for the Deepgram
connection. Every call's opening disclaimer line — "This call may be recorded for
quality and training purposes." — is immediately followed by a Spanish version of the
same disclaimer, and with `language="en-US"` Deepgram either drops that audio or
returns garbage/empty transcripts for it instead of finalizing a turn-end.

This is a strong candidate root cause for our bot starting to talk over the agent
early in calls (a recurring issue across most of the recorded calls): if Deepgram
never reports a clean end to the agent's turn during the Spanish segment, our
turn-taking logic (`UtteranceEnd`/`endpointing`) has nothing reliable to key off of,
so the bot's next reply can fire at the wrong moment relative to what's actually still
playing.

**Fix path:** switch the Deepgram `LiveOptions` to a multilingual-capable setting (Nova-2
supports `language="multi"`, or Deepgram's auto-language-detection) and re-run a call to
confirm the Spanish disclaimer is now transcribed and turn-taking around it cleans up.

**Why this one:** found organically while reviewing real audio, one-line root cause in
a config option, and gives a very clean before/after — the broken transcript next to
the fixed one, with the secondary payoff of (likely) fixing the early-barge-in pattern
seen elsewhere in the calls.

## 1. Barge-in / talk-over isn't fully fixed

We added a `clear` event (`{"event": "clear", "streamSid": ...}`) to flush Twilio's
playback buffer when the agent starts talking over our bot, but the deeper cause is
still there: `speak()` in `src/server.py` sends every TTS frame to Twilio as fast as
ElevenLabs streams it, with no pacing to match real playback speed (160 bytes = 20ms
of audio, sent essentially all at once for a short reply). By the time barge-in is
detected, most or all of the reply may already be queued on Twilio's side, so the
`clear` event has little left to flush.

**Fix path:** pace frame-sending with `await asyncio.sleep(0.02)` between frames (20ms
per frame, matching real playback time) so the send loop and the barge-in check stay
roughly in sync with what's actually been heard by the caller.

**Why this one:** unresolved, well-understood root cause, clear before/after to
demonstrate, complete arc fits in 5 minutes.

## 2. No flow control / backpressure on TTS streaming generally

Related to #1 — `speak()` has no awareness of how much audio Twilio has already
buffered vs. played. Pacing (above) is the simplest fix; a more robust version would
track elapsed audio time sent vs. wall-clock time and throttle accordingly.

## 3. Fixed endpointing/pause thresholds don't adapt to how the other agent talks

`src/voice/stt.py` sets Deepgram's `endpointing=700` and `utterance_end_ms="1000"`
once at connection start and never adjusts them. An agent that speaks in short
clipped phrases vs. one with long thoughtful pauses mid-sentence both get the same
fixed turn-taking threshold, which can make our bot jump in too early or wait too
long depending on who it's talking to.

**Fix path:** track the actual gaps between transcript events for the current call
(e.g. a rolling average of inter-phrase silence) in `_on_transcript`/
`_on_utterance_end_event`, and use that running estimate — rather than the fixed
constants — to decide when a turn has really ended. Deepgram's own `endpointing`/
`utterance_end_ms` options are connection-level and can't be changed mid-stream, so
this means layering adaptive logic on top of (or instead of) relying purely on those
fixed thresholds.

**Note:** an LLM (Claude) choosing the wait time was considered and rejected — it
only ever sees post-transcription text, not real-time audio/silence signals, so it
has no actual basis to pick a pause duration. This has to live in the audio/STT
layer, not the persona logic.
