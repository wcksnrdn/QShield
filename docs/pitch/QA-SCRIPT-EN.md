# Q&A Script — English, for the onsite final

> **Code freeze is in effect.** Nothing in this file changes the system.
> It only writes down what is already true, in the language you will
> have to say it in.
>
> **How to practise.** Cover the answer. Read the question out loud.
> Answer from memory. Then check. Do the first twelve questions until
> they are automatic — those are the ones you will certainly get.
>
> **Every answer here is short on purpose.** Two to four sentences. If
> the judge wants more, they will ask, and the *if they push* line is
> what you say next. Answering a short question with a long speech is
> the most common way to lose a room.

---

## 1. The numbers you must know cold

Say these without hesitating. Nothing else needs memorising.

```
3 devices over 24 hours    before a location is trusted
50 metres                  anchor radius
0-25 / 26-50 / 51-75 / 76-100    proceed / warn / step_up / cooling_off
90 seconds                 verification ticket lifetime
0.8 ms median              our measured latency (budget is 200 ms)
4.1%                       false positives of the rarity model
122 merchants              our field corpus, collected by hand
8 invariants, 20 test suites, 44 attack scenarios
```

**Pronunciation to watch:** *anchor* (ANG-ker, not AN-chor) · *geospatial*
(jee-oh-SPAY-shul) · *consensus* (kun-SEN-sus) · *adversarial*
(ad-ver-SAIR-ee-ul) · *invariant* (in-VAIR-ee-unt).

---

## 2. The opener — memorise this one

**"Tell us about Q-Shield in one minute."**

> In Indonesia, the most common QRIS fraud is not a fake QR code.
> The attacker registers a real merchant account, gets a real sticker
> from a real payment provider, and puts it on top of someone else's.
> The code is genuine. Only its placement is a lie.
>
> We tested whether you could catch this by inspecting the payload. You
> cannot — we compared sixteen attributes, and none of the twelve
> structural ones differ, because both stickers come from the same
> issuer.
>
> So Q-Shield checks something else: **is this merchant supposed to be
> at this place?** We build that knowledge from ordinary shoppers.
> When three different phones scan the same code at the same spot over
> a day, that place becomes trusted. When a different code appears
> there, we hold the payment before the PIN screen.

*Pause. Let them ask.*

---

## 3. The core technical questions

**"How do you know where a merchant is supposed to be?"**

> We do not know at the start. We learn it. Every scan is one
> observation. When three different devices see the same merchant ID at
> the same location, spread over at least twenty-four hours, we call
> that an anchor. The anchor is a running average, so it gets more
> precise over time — from about seven metres to one and a half after
> forty-seven observations.

*If they push:* "Why three and twenty-four hours?" → Those are
calibrated, not guessed. Lower, and one person with a few phones can
forge it in an afternoon. Higher, and honest new merchants wait too
long.

---

**"What happens on the very first scan, when you know nothing?"**

> We say we do not know. That is a real answer in our system — we have
> three states, not two: verified, unknown, and anomaly. And there is a
> rule we cannot break: **unknown never means safe.** The user sees a
> warning that says this place has never been recorded, not a green
> light.

*If they push:* "So it is useless for new merchants?" → For an
unregistered new merchant, yes, at first — and we would rather say that
than guess. There is a fast path: a payment provider can register the
merchant, and then it is trusted immediately.

---

**"What stops me from just faking my GPS?"**

> Nothing stops you from faking it. We cannot verify coordinates — we
> say that openly. What we do is refuse to use them. If the phone
> reports a mock location, we do not run the location layer at all and
> the payment never gets a green light. The same thing happens when GPS
> accuracy is worse than a hundred metres.

*If they push:* "Then your whole system falls apart." → It changes what
the attacker gains. Faking GPS does not make a sticker trusted; it
makes the scan unknown. To get a green light you still need three real
devices at the real place over a real day.

---

**"What if I invent fake device IDs to build fake trust?"**

> That works, and we found it ourselves. Three invented identifiers,
> spread over the time threshold, will turn a new location into a
> verified one. We publish it as an open limit.
>
> What we did about it: every verdict now says where its reputation came
> from. If it was built only from anonymous scans, the response says so.
> A provider can decide to trust only observers whose devices they have
> attested themselves.

*This is a strong answer. Do not hide this question — walk into it.*

---

**"Two stalls stand side by side in a food court. Won't you accuse them?"**

> That was our first serious false positive, and we fixed it with
> evidence rather than by loosening a threshold. Two merchants can share
> a spot if their observer counts are comparable, or if the newcomer
> proves physical presence — eight different devices over a day, **while
> the original merchant is still being scanned.**
>
> That last condition is what keeps it safe. A sticker placed on top
> makes the original code unscannable. So the original going quiet is
> exactly what a real attack looks like.

---

**"What about a vendor who moves around — a coffee cart?"**

> A roving cart and a batch of scattered stickers look identical in the
> data. What separates them is physics, not statistics: **one cart can
> only be in one place at one time. Five stickers placed at once live in
> five places at once.**
>
> So we require positive proof — two sightings in different areas, too
> close in time for anyone to travel between. We measured it at eighty
> kilometres per hour: zero percent of push-cart vendors and zero
> percent of motorbike vendors get accused.

*If they push:* "And the ones you miss?" → At that threshold we only
catch three point eight percent of in-city scatterers. We chose vendor
safety over catch rate, and we publish the number.

---

**"Two vendors share one spot at different times of day. What then?"**

> Morning rice seller, afternoon fruit cart, evening fried rice — all
> real, all at the same spot. The old system accused the second vendor
> for three to nine days.
>
> The proof was already in our data, and nobody had read it:
> **alternation.** The first merchant is scanned, then the newcomer,
> then the first merchant *again*. A covering sticker cannot produce
> that pattern, because once it covers the code, that code can never be
> scanned again.
>
> We measured it. Legitimate shift-sharing: six re-appearances in a
> week. A covering attack: **zero.** Not small — zero.

*This is our best answer in the whole deck. Slow down when you say
"zero".*

---

**"Is GPS accurate enough? Indoors it's terrible."**

> It is not, and that is why we refuse to answer. Above a hundred metres
> of reported accuracy, hundreds of shops fit inside the uncertainty
> circle. Scoring against that is not a less accurate judgement — it is
> a meaningless one. So we return unknown and say why.
>
> Where the client is a native app, we also read the hashed list of
> nearby WiFi access points. That works indoors. But we only ever use it
> to raise suspicion, never to grant trust.

---

**"Do you use machine learning?"**

> Yes, two unsupervised models — and the honest part is *why*
> unsupervised. There are no confirmed fraud examples to learn from. A
> supervised classifier cannot be trained without labels.
>
> So we learn what normal looks like. One model learns how each payment
> provider's generator assembles a payload — a code claiming that issuer
> but not following its pattern was built by someone else. The other
> learns how often each merchant attribute occurs, and flags
> combinations that almost never happen.

*If they push:* "How accurate?" → On a hundred and twenty-two real
merchants we collected in the field, leave-one-out testing flags five.
That is a four point one percent false positive rate, and the model
names which attribute is rare and how rare. An unexplainable verdict has
no place in payments.

---

**"Isn't this just geofencing?"**

> Geofencing starts with a map someone drew. We have no map — QRIS codes
> carry no coordinates, and nobody publishes where every street vendor
> stands. We build the map from the payments themselves, and the same
> evidence that locates a merchant is what detects the attack.

---

**"How fast is it? You're in the payment path."**

> We are not in the payment path, and that distinction matters. The
> provider calls us before the PIN screen and then decides what to do.
>
> On latency: two hundred sequential requests measured at zero point
> eight milliseconds median, zero point nine at the ninety-fifth
> percentile. The budget is two hundred milliseconds. I should add that
> this is a local database with a small corpus — it shows the algorithm
> is not the bottleneck, not that we have proven production capacity.

---

## 4. Privacy and regulation

**"Are you tracking users?"**

> No, and the schema is built so that we cannot. We store *how many
> different devices*, never *which device*. The device reference is a
> salted hash, and it is scoped to each location — so the same phone
> produces a different reference at every place, and the references
> cannot be joined into a movement trail.

*If they push:* "Prove it." → We test it adversarially. One of our
invariants enumerates the live schema — sixty-nine columns across
thirteen tables — and then attacks it. A join attack, a cross-location
linkage attack, and a reference-counting attack all fail.

---

**"Is this compliant with UU PDP?"**

> It is **designed for alignment** with it, and I want to be careful
> with that word. We store no names, no phone numbers, and no user
> location trails. Whether that constitutes full compliance is a legal
> judgement, and we are not the ones who get to make it.

*Say it exactly like that. Claiming "fully compliant" is the fastest way
to lose a regulator in the room.*

---

## 5. Business and adoption

**"Why would a payment provider adopt this?"**

> Because the loss is theirs to absorb and the complaint arrives at their
> support desk, even though the fraud happened on a wall. And the
> defence cannot be built by one provider alone — the attacker's sticker
> is scanned by customers of every wallet, so no single provider sees
> the whole picture.

---

**"Chicken and egg. With no data, it protects nobody."**

> Correct, and we do not pretend otherwise. Two things reduce it. A
> provider can register its own merchants, and those are trusted
> immediately with no waiting. And the coverage problem shrinks as it is
> shared: one wallet's scan protects every other wallet's users. We have
> a script that runs both worlds side by side so the difference is
> visible rather than argued.

---

**"What if only one provider joins?"**

> Then it still works, but only over that provider's own users. We call
> that Model A — it runs entirely inside their infrastructure and no
> data leaves. Model B is the shared consortium. A provider can start
> with A and join B later, and we designed it that way because asking
> for trust before proving anything is not reasonable.

---

**"Who pays for it?"**

> We have not built a pricing model, and I would rather say that than
> invent one. What we are asking for at this stage is a conversation
> with a provider, not a contract.

---

## 6. The hard questions — walk into these

**"So you cannot actually stop the payment?"**

> No. We produce a verdict and a signed ticket that binds that verdict
> to the exact code scanned. The provider executes the payment, and a
> provider that ignores our highest tier will ignore the ticket too.
> Real enforcement would require the national switch to refuse
> settlement without a valid ticket. That is infrastructure, not a
> library, and we do not claim otherwise.

---

**"What is the biggest weakness you know about?"**

> That our trust signal is built from a field the client controls. A
> determined attacker can forge device identities and manufacture
> consensus. We cannot close it by raising the threshold — counting
> forgeable numbers still counts forgeable numbers. It closes through
> provider registration or attested devices, both of which need a
> provider.

*Never answer this with "nothing". A security judge is testing whether
you know your own system.*

---

**"What doesn't work?"**

> Six things, and they are all written down with the measurement behind
> each. The most important two: a sticker that was already swapped
> before someone photographed it cannot be caught from the payer's side,
> because a photo carries no place. And an attacker who puts a sticker
> up and takes it down every day produces the same pattern as a
> legitimate shift-sharing vendor. We cannot separate those, and we do
> not claim to.

*If they push:* "Then the attack works?" → It costs him twice-daily
attendance at someone else's stall, forever, while letting his victim
collect half the payments. That is not an attack we detect. It is an
attack that stops being worth doing.

---

**"Why should we believe your numbers?"**

> Because you can run them. Every figure in our report comes from a
> script in the repository, and the report lists the commands. The
> weights are locked by a test that fails if any of them drift. We also
> mark the parameters that are *not* yet field-calibrated, explicitly,
> in the code.

---

**"How much of this is yours and how much is a library?"**

> Three runtime dependencies and no data files. The parsing, the
> geospatial logic, the consensus rules, the scoring, the storage, and
> the ticket protocol are ours. What we did not write is the web
> framework and the standard library.

---

**"You're students. Why should anyone trust this in production?"**

> They should not, and we say that in our own pitch document. We are a
> student team with a proof of concept. That is exactly why we publish
> our limits, why every claim points at a test, and why our ask is a
> thirty-minute conversation rather than a deployment.

---

## 7. When you do not know

Memorise these. They are better than guessing, and judges respect them.

> "I don't know. I'd have to measure that before answering."
>
> "We haven't tested that case. It's a real gap."
>
> "That's a simulation number, not a field number — I want to be clear
> about which."
>
> "Can I come back to that? [Teammate] worked on that part."

**Never** say *"it's impossible to attack"*, *"it's fully compliant"*,
*"the app cannot ignore it"*, or *"we're in the payment path"*. All four
are false, and all four are written down as false in our own repository.

---

## 8. Phrases to buy yourself time in English

Say these while you think. They sound deliberate, not lost.

> "That's a good question — let me take it in two parts."
>
> "So the short answer is no. The longer answer is…"
>
> "Let me make sure I understood. You're asking whether…"
>
> "I want to be precise about this, because it matters…"

And if you did not hear the question:

> "Sorry, could you repeat the last part?"

That is a completely normal thing for a native speaker to say too.

---

## 9. Three sentences to end on

If you get a closing slot, end with these rather than a summary:

> The fraud is not in the code. It is in the code's placement.
>
> Nobody can solve that alone, because the attacker's sticker is
> scanned by customers of every wallet.
>
> Everything we claim can be run from the repository — including the
> parts where we say it does not work yet.
