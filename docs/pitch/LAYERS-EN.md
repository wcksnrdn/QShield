# The Two Layers — spoken script, English

> Written to be **said out loud**, not read. Short sentences on purpose.
> `[pause]` means stop talking for a beat — it is where the judge decides
> whether to interrupt with a question, and you want them to.
>
> Three lengths: **60 seconds**, **3 minutes**, **full**. Pick by your slot.

---

## The 60-second version

> Q-Shield runs two independent checks before the PIN screen.
>
> **Layer One asks: is this merchant supposed to be here?**
> We don't have a map — QRIS codes carry no coordinates. So we build one
> from ordinary shoppers. When three different phones scan the same
> merchant at the same spot, spread over at least a day, that place
> becomes an anchor.
>
> **Layer Two asks: does this code behave like a legitimate one?**
> That's the payload itself — its structure, whether a single-use code is
> being reused, whether the printed label matches what's encoded.
> [pause]
> The two can fail independently, so Layer Two **completes** Layer One
> rather than replacing it. And Layer Two can only ever lower trust,
> never raise it.

---

## The 3-minute version

### Open with the question, not the architecture

> Before I show you the layers, here's the thing they're built around.
>
> In this attack the QR code is **genuine**. The attacker registers a
> real merchant account, gets a real sticker from a real provider, and
> places it over someone else's. We measured whether you could catch
> that by inspecting the payload — sixteen attributes — and **none of
> the twelve structural ones differ.** They can't. Both stickers came
> off the same generator.
> [pause]
> So the question we ask is not *is this code real*. It's **is this code
> where it's supposed to be.**

### Layer One

> Layer One is the location layer.
>
> An **anchor** is a place where a given merchant ID has been seen
> repeatedly. It becomes trusted at **three distinct devices spanning at
> least twenty-four hours**, within a **fifty-metre** radius. And the
> anchor sharpens over time — it's a running average, so our positional
> error drops from about seven metres to one and a half after forty-seven
> observations.
>
> Two thresholds, not one, and that's deliberate. Three devices alone
> means one person with three phones finishes in five minutes. The
> twenty-four hours is what forces an attacker to come back.

### Layer Two

> Layer Two never looks at the place. It looks at the artefact.
>
> Seven families of signal: structural contradictions, dynamic-QR reuse,
> printed label versus encoded content, ambient WiFi fingerprint, device
> integrity, provenance, and merchant-profile rarity.
>
> And one rule I want to be explicit about: **there is not a single
> negative weight in Layer Two.** The absence of a signal is not evidence
> of legitimacy. If Layer Two could subtract, an attacker could craft a
> structurally perfect payload and **buy back** the trust Layer One
> withheld. Payload structure is entirely under his control. Location
> history is not.

### How they combine

> Scores add and clamp to zero to one hundred, mapped to four tiers:
> proceed, warn, step up, cooling off.
>
> Layer Two can only make it worse. A hard contradiction forces an
> anomaly. Any other signal demotes *verified* to *unknown*. And an
> anomaly from Layer One is never withdrawn by Layer Two.
> [pause]
> That asymmetry is the whole safety argument: **a value the attacker
> controls may tighten the verdict, never loosen it.**

---

## The full version — add these when you have time

### The four gates, before any scoring

> Four gates run before either layer. Three of them stop Layer One from
> running **at all**.
>
> If the payload won't parse, we stop entirely — no verdict, no ticket,
> nothing learned.
>
> If the phone reports a mock location, we don't run Layer One. If the
> code was scanned from a photo, we don't run Layer One. If GPS accuracy
> is worse than a hundred metres, we don't run Layer One.
>
> That last one deserves a sentence. At eight hundred metres of
> uncertainty, hundreds of shops fit inside the circle. Scoring an anchor
> against that isn't a less accurate judgement — it's a **meaningless**
> one. So we return *unknown* and say why.
> [pause]
> But in all three cases **Layer Two still runs in full.** A malformed
> payload is malformed regardless of GPS. Throwing that away because a
> different sensor failed would be discarding healthy evidence.

### The third state

> We have three verdicts, not two: verified, unknown, and anomaly.
>
> Most detection systems are binary, and a binary system is **forced to
> guess**, because it has nowhere to put ignorance. We have somewhere to
> put it. And there's a rule we enforce structurally: **unknown never
> maps to proceed.**
>
> It's enforced twice — once at the end of Layer One, and again after
> Layer Two is added in — specifically so that a future Layer Two signal
> can't quietly open that hole.

### What the system learns

> This is where a lot of systems leak, so we made it narrow.
>
> If the verdict is an anomaly, we learn **nothing**. A fraudulent
> sticker must never be able to build reputation by being scanned —
> otherwise an attacker just scans his own sticker into legitimacy.
>
> If the scan came from a photo or a replay, we learn **payload**
> knowledge only — issuer dialects, attribute rarity — and **never**
> location. That rule came from a real incident: a teammate catalogued
> codes from the internet while sitting in an office, and seven codes
> from across Indonesia were all recorded at one point in Jakarta.
>
> Only a clean field scan teaches us a place.

### The ticket

> Finally, every verdict ships with an HMAC-signed ticket, valid ninety
> seconds, binding that verdict to the fingerprint of the exact code
> scanned. It closes the gap between *checked* and *paid* — so malware
> can't verify code A and then settle code B.
>
> What it does **not** do: it binds, but it cannot compel. A provider
> that ignores our highest tier will ignore the ticket too. Real
> enforcement needs the national switch to refuse settlement without a
> valid ticket — that's infrastructure, not a library, and we don't
> claim otherwise.

---

## The four exemptions — only if they ask about false positives

This is the part that shows field work rather than theory. Lead with the
principle, then pick **one** example.

> Indonesian street commerce breaks naive geospatial rules every day. We
> found four in the field, and each one we solved by requiring **new
> evidence** — never by loosening a threshold until the complaints
> stopped.

**If they ask about food courts:**
> Two stalls at the same coordinates coexist if their observer counts are
> comparable, or if the newcomer proves physical presence — eight devices
> over a day, **while the original is still being scanned.** That last
> condition is the safety: a covering sticker silences the original.

**If they ask about roving vendors:** *(the strongest one — use this)*
> A moving cart and scattered stickers look identical in the data. What
> separates them isn't statistics, it's physics: **one cart can only be
> in one place at one time.** So we require proof of simultaneous
> presence — two sightings too far apart for the time between them. At
> eighty kilometres an hour, **zero percent** of push-cart vendors and
> zero percent of motorbike vendors get accused.

**If they ask about vendors sharing a spot by time of day:**
> Morning, midday, evening — all legitimate, one spot. The proof was
> already in our data: **alternation.** The incumbent is scanned, then
> the challenger, then the incumbent *again*. A covering sticker cannot
> produce that, because once it covers the code, that code can never be
> scanned again. Measured: six re-appearances a week for real
> shift-sharing. **Zero** for a covering attack. Not small — zero.

---

## Numbers, pronounced

```
three devices over twenty-four hours
fifty metres
zero point eight milliseconds, median
four point one percent false positives
a hundred and twenty-two real merchants
eight invariants, twenty test suites, forty-four adversarial scenarios
```

*anchor* = ANG-ker · *geospatial* = jee-oh-SPAY-shul ·
*invariant* = in-VAIR-ee-unt

---

## If you only remember one sentence per layer

> **Layer One asks whether this merchant belongs here.
> Layer Two asks whether this code behaves like a real one.
> They fail independently, so Layer Two completes Layer One —
> and Layer Two can only ever lower trust, never raise it.**
