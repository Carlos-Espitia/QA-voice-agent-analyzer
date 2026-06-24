# PGAI Voice Agent — Bug Report

Based on analysis of 10 real calls placed against the PGAI test agent
(+1-805-439-8008), covering 7 `medical/*` happy-path scenarios and 3 `qa/*`
adversarial scenarios, with 3 personas (Alex Rivera, Jordan Kim, William
Hayes). Full transcripts and recordings are in `recordings/<call_sid>/`.

Audio-quality issues (clarity, latency, naturalness) are being added
separately by the project author and are not covered in this document —
this report focuses on conversational/logical bugs in the agent's behavior.

## 0. Audio glitch mid-digit when reading back a phone number

**Seen in:** `medical/cancel`, call `CA40245d7272ca5239d39e76ab46df0c3c`

> Agent: "I have your number as five five five two four eight zero one
> three. Is that correct?"

Listening to the actual recording, the agent's audio briefly cuts off
partway through saying "six" and instead plays "eight" — it sounds like a
TTS/audio-splicing glitch rather than the agent simply mispronouncing a
digit. The transcript above reads as a clean sentence, but the underlying
audio is broken at that point, which text alone wouldn't reveal.

## 1. "Connecting you to a representative" never actually transfers — the call just ends

**Seen in:** `medical/cancel`, `medical/reschedule`, `medical/schedule_new`,
`qa/vague_request`, `qa/changes_mind` (5 of 10 calls)

**Caveat:** this is a test line, so it's likely there's simply no live transfer
target wired up in this environment — the "Goodbye" may be intentional test
behavior rather than a logic bug. Flagging it anyway because the caller-facing
outcome is identical regardless of cause: the agent promises a transfer it
doesn't deliver, with no resolution to the caller's actual request. Worth
confirming with the team whether this is a known test-environment limitation
or a real gap that would also occur in production.

Every time the agent says "Connecting you to a representative. Please wait,"
the very next thing it says — usually within 2-15 seconds — is "Hello.
You've reached the Pretty Good AI test line. Goodbye," and the call ends.
No actual transfer happens. In every one of these calls, the caller's
original request (cancel an appointment, reschedule, schedule a new visit)
is **never fulfilled** within the call.

Example (`medical/cancel`, call `CAa779e99d0eb4f2155dfe6d2c0e0e04f7`):
> Agent: "I can't proceed further right now, but I can make sure our
> clinic support team follows up with you. Would you like me to have them
> call you back about canceling your appointment?"
> Caller: "Well, I suppose so, yes."
> Agent: "Connecting you to a representative. Please wait."
> Agent (3 seconds later): "Hello. You've reached the Pretty Good AI test
> line. Goodbye."

If this does reflect real production behavior (not just a test-environment
gap), it would mean
a real caller trying to cancel, reschedule, or book an appointment can be
left with nothing accomplished and no actual human follow-up, despite being
explicitly told they would be transferred or called back.

## 2. Identity-verification loop gets stuck and re-asks for already-confirmed info

**Seen in:** `medical/cancel`, `qa/vague_request`, `qa/changes_mind`

After the caller's name, date of birth, and phone number have all been
explicitly confirmed ("Is that correct?" → "Yes"), the agent sometimes
asks for the same information again moments later, then declares a system
error.

Example (`qa/vague_request`, call `CA28c6bdc9566737bc948fb5d1dc6ad64f`):
> Agent: "...and your date of birth is November twelfth nineteen eighty
> five. Is that correct?"
> Caller: "Yes, that's right."
> Agent (10 seconds later): "Please provide your date of birth."
> Caller: "I already gave you that — November 12th, 1985."
> Agent: "Something's not right with the system, and I can't pull up your
> record."

This happened with two different personas (Jordan Kim, William Hayes) in
three separate calls, suggesting it's a systemic issue with the lookup/
verification flow rather than a one-off glitch.

## 3. Phone number read-back is sometimes garbled or wrong

**Seen in:** `medical/cancel`, `medical/refill_request`, `qa/changes_mind`

When confirming a caller-provided phone number, the agent's read-back
sometimes drops digits or is unrelated to the actual number given.

Most severe example (`medical/refill_request`, call
`CAd748a8f5b13ebd450d7439be3fe3dceb`) — caller's actual number is
555-123-4567:
> Agent: "Can I confirm your callback number as five zero one Five zero
> one? Seven six three five"

That bears no resemblance to the number provided. In two other calls
(`medical/cancel`, `qa/changes_mind`), the agent dropped a leading "5"
from "555," reading it back as "five five two four six eight zero one
three" instead of "five five five two four six eight zero one three,"
requiring the caller to correct it 2-3 times before it was captured
correctly.

## 4. Mid-sentence interruption point unclear from transcripts (needs audio review)

In several calls, the agent's sentence is split across two short turns in
a way that looks like either (a) the agent genuinely pauses mid-sentence
for a few seconds, or (b) the caller's turn-detection picked up too early.
Example (`medical/insurance_question`):
> Agent: "Can you" *(pause)*
> Caller: "Sure, go ahead!"
> Agent: "Thanks, Alex. Can you please provide your date of birth?"

This is flagged for follow-up during the audio-quality review rather than
called a confirmed bug here, since it's hard to tell from text alone
whether the agent paused unusually long or our own system's turn-taking
was too eager.
