# The bot said it would stop. That isn't evidence it did.

*Testing an AI texting bot where what it says and what it does are produced separately, and why
every opt-out test asserts on stored state instead of on the reply.*

## The system

For a real-estate investment client, I built an SMS bot on a CRM platform's conversational AI. It
texts property owners, qualifies interest, and hands warm leads to a person. Like most platforms of
this kind, it works in two layers that run on every inbound message:

- a **text layer**, where the model writes the reply the person reads, and
- an **action layer**, where the model picks from a set of actions, and each action starts a
  workflow that writes state: tags, dates, and the do-not-contact flag.

The opt-out action is the one with a legal edge. When someone says "stop", it has to switch on
do-not-contact for every channel, tag the contact, and record the date. Under U.S. texting rules,
telling someone they're off the list while continuing to text them is exactly the failure you
can't have.

## The turn where the two layers disagreed

During testing, one inbound message shared a property. The action layer did the right thing: it
created the opportunity and logged the handoff. Four seconds later, the text layer replied
**"Understood, I'll stop reaching out."** That's the opt-out script, sent to someone who hadn't
asked to stop.

That direction was harmless: no opt-out was recorded because none was asked for. The mirror image
is the dangerous one. If the words and the actions can disagree on one turn, a real person can be
told "I'll stop reaching out" with **no opt-out action behind it**, so nothing is suppressed and the
texts keep coming.

So every opt-out test in this build has one rule: **the reply text is not evidence the action
fired. Assert on the state the action writes.** Do-not-contact on all channels, the tag, and the
date, read back from the API.

## Working out what actually happened

The test contact's record held a "declined" tag, and at first that looked like damage from the
misfire. Reading the full thread and the contact's state from the API settled it without spending
another test:

- The decline state came from a **deliberate decline test** sixteen minutes earlier the same day.
  A date field alone could never have told the two apart. The **workflow signature** could: the
  decline workflow writes exactly three things, and the record held exactly those three.
- The misfire wrote **nothing**. The opt-out workflow's three writes were all absent, so it had
  never run. It also couldn't have written the decline tag even in principle, because that tag
  isn't in its steps.

## The obvious test couldn't answer the question

The platform has a test pane for chatting with the bot, and it was the natural place to probe this.
**Measured: the test pane doesn't fire actions at all.** It shows the bot's words, which is the half
that doesn't decide anything here. The real check needed a live text on a fresh conversation.

It also needed care around a second finding: each bot action has a cooldown of about 20 messages.
Inside that window, a blocked action produces a signature identical to "the model didn't pick it".
Every probe conversation had to be deleted first, or the result couldn't be read either way.

## The gate run passed, and found something else

The go-live gate was an unambiguous "Stop. Take me off your list." sent on the hardest fixture: a
thread of about 50 real messages holding objections, a decline, and an earlier property share. All
three opt-out writes landed within twelve seconds. That was the evidence the gate needed, and it
showed action selection held up on a long thread.

**The confirmation text never arrived.** The same string on a short thread earlier had gotten the
reply out two seconds before suppression. On the long thread, suppression won. The reply and the
workflow race each other, and the winner isn't stable.

The ordering itself was deliberate. Do-not-contact is switched on first, because that's the one
ordering in the build with a legal consequence. **The ordering that makes it safe is what swallows
the confirmation.** And the stored state is identical either way, so no check on state can tell
which happened. Two people sending the same word can get two different experiences. I logged it as
a decision for the owner to make, rather than patching it quietly.

## One the model has to judge

Measuring how often people ask for a call turned up this, in the client's own message history:
**"Do not text. Call me."** The opt-out action matches "do not text". The call-request action
matches "call me". The expensive branch is opt-out. It records a channel preference as permanent
suppression, so the person who asked for a phone call is marked never-contact.

It happened in only a handful of messages. But the two action conditions had almost no room left
under the platform's length limit, so the fix couldn't be one more clause on either. That's a
genuinely ambiguous message where the model has to choose, and it's harder than the misfire,
because both readings are defensible.

## What I took from it

- **When generation and actions are separate layers, test them separately.** A correct reply says
  nothing about the action, and a correct action says nothing about the reply.
- **Assert on stored state, not on words,** and know what each workflow writes, so that its
  signature can tell events apart when the timestamps can't.
- **Check what your test harness can actually see.** The test pane can't see actions, and one read
  tool silently showed only the newest 40 entries of a 76-entry thread. That nearly turned a later
  read into a false alarm about a damaged test fixture.
- **A safety ordering can have a cost.** Say so plainly, and let the owner decide.
