# Q-Shield — Project Report

**Version 2 (team draft) · 30 September 2026**

> **This is a parallel draft, not a replacement.** Vyone's report lives
> at `docs/report/QShield-Project-Report.pdf` and is left untouched, so
> the two can be compared section by section. The differences and the
> reason for each are listed in `docs/report/SCREENING-REPORT.json`.
>
> **Rule followed while writing this:** every number below is either
> produced by a script in this repository or points at a file and line.
> Nothing is stated that cannot be re-run. Where something is not
> measured, it says so.

---

# CHAPTER I — Introduction & Background

## 1.1 QRIS Adoption

QRIS, Indonesia's national QR payment standard, was implemented by Bank
Indonesia via Payment Administrative Order No. 21/18/PADG/2019 and
developed with the Indonesian Payment System Association (ASPI). Built on
the EMVCo QR specification, it is fully interoperable: a single code
displayed by a street vendor can be paid from any authorised mobile
banking app or e-wallet.

Adoption has been massive. By the end of 2025 QRIS recorded the highest
transaction-volume growth of any payment system in Indonesia, rising
139.9% year-on-year and reaching 59.53 million users and 42.75 million
merchants (Bank Indonesia, 2026). As of mid-2025, 93.16% of its merchants
are SMEs (Bank Indonesia, 2025). QRIS has become the backbone of retail
digital payments in Indonesia, particularly for small businesses.

## 1.2 Physical Attack Surface

That reach creates an asymmetric *physical* attack surface. QRIS displays
used by most MSMEs are static QR codes printed on inexpensive paper,
laminated cards, or acrylic stands. Unlike POS terminals, these displays
are passive data carriers: they direct payments to the merchant's account
but have no electronic display, no challenge–response, no tamper
detection, and no way to verify that the code actually belongs to the
stall where it hangs.

The risk is compounded by placement. In public markets, food courts,
roadside stalls, and at donation boxes, these codes are routinely left
unattended and physically accessible.

## 1.3 The Sticker-Swap Attack

In a sticker-swap attack the attacker forges nothing. They register a
legitimate merchant account with an authorised payment service provider
(PJP), obtain an officially issued, standards-compliant QR code, and
place it over the original merchant's code. Every payment bypasses the
legitimate merchant and reaches the attacker.

The press calls these "fake QR codes." They are not fake. **The code is
genuine; only its placement is deceptive.**

The pattern gained national attention in April 2023, when an individual
placed such stickers at 38 mosques and prayer rooms across Jakarta and
Tangerang, generating IDR 13.06 million between 1 and 9 April (DW, 2023).
The codes were labelled "Restorasi Masjid" and linked to accounts
registered in Medan and South Jakarta (Kompas, 2023). In late September
2025, vendors at a food court at Telkom University in Bandung found the
QR codes of roughly 10–20 stalls covered over, with losses per stall
ranging from IDR 30,000 to IDR 1 million; the stickers are believed to
have been applied overnight (Kompas TV, 2025).

## 1.4 Why Inspecting the Code Is Not Enough

Before building a location layer, we tested the cheaper hypothesis: can a
legitimate tag be told apart from a fraudulent one by inspecting the
payload alone? We extracted **16 structural and semantic attributes**
from both and compared them side by side
(`scripts/enam_belas_ciri.py`, locked by `tests/test_enam_belas.py`).

| Attribute class | Count | Differ between victim and attacker |
|---|---|---|
| Structural — decided by the acquirer's generator | 12 | **0** |
| Descriptive — filled in by the merchant at registration | 4 | 2 |

**None of the 12 structural attributes differ.** Field count, field
order, CRC validity and casing, acquirer GUID, merchant template number,
sub-tag layout, account-number length and prefix, NMID format, currency,
country — identical. This is the expected result: both stickers were
issued by the same compliant acquirer.

Two *descriptive* attributes do differ in our sample — merchant category
(MCC 5812 vs 5999) and merchant-name length (13 vs 14). **We do use
them**, and Layer 2 scores them. But the attacker fills those fields in
himself when registering, so a careful attacker erases the difference
without changing anything about the attack.

Re-measured against real data rather than a constructed pair: across
**52 real merchants collected in the field from a single issuer
(93600914)**, five of the six retained structural attributes are
identical for **all 52**; the sixth (tag order) has two variants, which
tracks generator versions, not fraud. What varies is descriptive — 21 MCC
variants, 35 city variants — and that is evidence the 52 are genuinely
different businesses, not evidence of tampering.

> **Conclusion.** A classifier trained to recognise "what a real QRIS
> payload looks like" would call both tags real, because both *are* real.
> The fraud is not in the code; it is in the code's physical placement.
> Detecting it requires the one thing QRIS does not carry: **knowledge of
> where a code is supposed to be.**

---

# CHAPTER II — Solution Overview & Market Differentiation

## 2.1 Solution Overview

Q-Shield is a **low-latency, zero-trust verification service that the PJP
calls synchronously before the PIN screen**, returning a verdict and a
signed ticket that the settlement path can require.

```
Camera feed → payload extraction → PJP backend → POST /api/v1/verify
            → dynamic friction gate → PIN entry
```

We state the boundary precisely, because overstating it is the single
easiest way to lose a payments audience: **Q-Shield does not sit in the
payment path and cannot force any outcome.** The PJP executes the
payment. What Q-Shield produces is a verdict plus a cryptographic binding
of that verdict to the exact code scanned. Enforcement is the PJP's, and
in the consortium model the national switch's. This limitation is
recorded as R15 in `docs/THREAT-MODEL.md` and written into the source of
`src/qshield/ticket.py` as a claim that must never be made.

Rather than post-transaction fraud detection, Q-Shield runs a synchronous
pre-PIN assertion through a **two-layer composite architecture**.

**Layer 1 — Merchant-Location Binding.** Determines whether the scanned
National Merchant ID (NMID) is established at the user's coordinates,
through distributed observer consensus. An anchor is a location where a
given NMID has been repeatedly observed; it becomes *established* at
**3 distinct devices spanning at least 24 hours**, and is maintained as a
bounded running average of incoming observations.

**Layer 2 — Artifact & Structural Behavioural Scoring.** Determines
whether the payload behaves like a legitimately issued artefact. Seven
signal families:

| # | Family | Detects |
|---|---|---|
| 1 | Structural contradictions | payload that a compliant acquirer could not have issued |
| 2 | Dynamic-QR trail | single-use codes reused, spread across locations, or re-priced |
| 3 | Printed label vs encoded content | a sticker whose visible text contradicts its own code |
| 4 | Ambient WiFi fingerprint | a place that does not match the place this anchor knows |
| 5 | Device integrity | rooted device, failed attestation |
| 6 | Provenance | QR city vs learned area city; inconsistent merchant names |
| 7 | Unsupervised merchant-profile rarity | attribute combinations that do not occur among real merchants |

**Layer 2 can only ever lower trust, never raise it.** There is not a
single negative weight in `src/qshield/behavior.py`. The absence of a
Layer 2 signal is not evidence of legitimacy.

Both layers emit into one 0–100 risk score mapped to four friction tiers:

```
 0–25   proceed      pay normally
26–50   warn         allow, but show the reasons
51–75   step_up      require additional verification
76–100  cooling_off  hold — do not pay
```

## 2.2 What Actually Differentiates Q-Shield

1. **It verifies placement, not authenticity.** Every payload-inspection
   product answers a question that this attack does not fail (§1.4).

2. **It is built to be wrong safely.** The system has a third state —
   `unknown` — that never maps to `proceed`. Absence of evidence is never
   converted into trust. This is enforced structurally, not by weight
   tuning (invariant §2).

3. **Its false-positive cost is measured, not asserted.** Indonesian
   street commerce breaks naive geospatial rules constantly: vendors
   share one spot by time of day, roving carts appear in many places,
   stalls stand centimetres apart. Each of these was found in the field,
   measured, and given an evidence-based exemption — not a threshold
   loosened until the complaint stopped.

4. **Its limits are published.** Chapter V.4 lists six open ones with the
   measurement behind each.

5. **Its value compounds across PJPs.** A scan by one wallet's user
   protects every other wallet's users (Chapter VI).

---

# CHAPTER III — Proof of Concept: Implementation & Repository References

## 3.1 Repository Structure

The system is a modifiable package under `src/qshield/`, separating
evaluation logic from persistence and network I/O.

| Module | Responsibility |
|---|---|
| `emvco.py` | recursive EMVCo TLV parsing, CRC16 validation |
| `geo.py` | geohash-7 indexing, haversine distance |
| `binding.py` | Layer 1 spatial consensus, tier mapping |
| `behavior.py` | Layer 2 artefact and behavioural signals |
| `profile.py` | unsupervised merchant-profile rarity model |
| `store.py` | thread-safe SQLite WAL persistence; anchor smoothing; zero-PII schema |
| `ticket.py` | short-lived HMAC-SHA256 verification tokens |
| `transfer.py` | Layer 2 for the manual bank-transfer channel |
| `auth.py`, `limits.py`, `audit.py`, `config.py` | API keys, rate limiting, audit trail, configuration |
| `api.py` | FastAPI surface |
| `web/index.html` | dual-mode mobile web scanner, single file, no build step |

**Note on anchor maintenance.** The anchor is not frozen at first sight
and not re-decided per scan: `store.py` maintains it as a **bounded
running average**. Measured in `tests/test_invariants.py` (invariant 1):
positional error falls from **6.9 m to 1.4 m after 47 observations**, and
500 hostile devices can drag an anchor by **at most 20 m**.

**Note on anchor identity.** Anchors are decided by **distance**, not by
geohash-cell equality; geohash-7 is only the query index. This was a real
defect on the write path, fixed in commit `7311fcb`: one stall scanned by
three phones within the same minute was recorded as three separate places
(2/1/1 observers, none reaching the consensus threshold) because the
scans fell on opposite sides of a cell boundary. Locked by
`tests/test_jangkar.py`.

### Calibration and verification

Operational thresholds live in `scripts/`, and each is reproducible:

| Script | Calibrates |
|---|---|
| `calibrate_geo.py` | geohash precision |
| `calibrate_layer2.py` | structural signal weights against 20,000 synthetic payloads |
| `calibrate_dynamic.py` | dynamic-QR reuse and spread thresholds |
| `calibrate_keliling.py` | roving-merchant speed and span limits |
| `calibrate_bergiliran.py` | shift-sharing alternation threshold |
| `calibrate_rarity.py`, `calibrate_rarity_weight.py` | rarity threshold and weight |
| `calibrate_decay.py` | anomaly-trace half-life |
| `calibrate_relokasi.py`, `calibrate_adjacency.py`, `calibrate_tetangga.py` | relocation and coexistence |
| `calibrate_falsepos.py` | end-to-end friction on honest vendors |
| `evaluate_rarity.py` | rarity model against the real field corpus |
| `preflight.py` | pre-demo system readiness |

**20 test suites, all green** at the time of writing:

| Suite | Covers |
|---|---|
| `test_invariants.py` | 8 architectural invariants (9 checks) |
| `test_adversarial.py` | 44 attacker-side scenarios |
| `test_hardening.py` | input validation, auth, rate limiting, audit, concurrency (31) |
| `test_frontend.py` | scanner/API agreement (22) |
| `test_registration.py` | merchant registration and its abuse (14) |
| `test_transfer.py` | manual-transfer channel (12) |
| `test_contract.py` | API v1 shape (11 sections) |
| `test_bergiliran.py` | one spot shared by time of day (10) |
| `test_gambar.py` | remote payment from a photographed code (10) |
| `test_keliling.py` | roving merchant vs scattered stickers (9) |
| `test_bobot.py` | the weights quoted in documentation (9) |
| `test_ticket.py` | ticket binding, forgery, expiry (9) |
| `test_konsensus.py` | provenance of anchor reputation (8) |
| `test_jangkar.py` | anchors decided by distance (7) |
| `test_enam_belas.py` | the §1.4 claim (6) |
| `test_sdk_contract.py` | native SDK seam freshness (4) |
| `test_emvco.py`, `test_geo.py`, `test_binding.py`, `test_api.py` | parsing, geometry, binding logic, end-to-end |

## 3.2 Core Component Breakdown

### 1. Spatial ingestion and consensus engine — Layer 1

Extracts the NMID from the raw code and cross-references it with the
payer's GPS coordinates. Rather than trusting a single reading, it
aggregates scans from independent shoppers into an *anchor*.

Beyond the base consensus, Layer 1 resolves four situations that all look
identical in the data and are not all fraud:

**(a) Adjacent merchants.** Two legitimate stalls at the same coordinates
(food court, or a juice cart next to a donation box). Coexistence is
granted when the observer bases are comparable (`ADJACENT_MIN_RATIO` =
0.10), or when physical presence is proven: **8 distinct devices over 24
hours, and the incumbent must still be getting scanned.** Closed as R11.

**(b) A merchant who relocated.** `nmid_scatter` becomes
`nmid_relocated` (weight 25 instead of 60) when 8 distinct devices are
seen at the new place, all old locations have gone quiet, and the active
periods never overlapped. Closed as R12.

**(c) A roving merchant.** A mobile coffee cart and a batch of scattered
stickers produce the *same* symptom: one NMID in many distant places.
What separates them is not statistics but physics —

> one cart can only be in one place at one time; five stickers applied at
> once live in five places simultaneously.

So an accusation of scattering now requires **positive proof of
simultaneous presence**: two observations in different areas too close in
time for anyone to travel between. Calibrated in `calibrate_keliling.py`:

| Speed limit | Push-cart vendors accused | Motorised vendors accused | Scatterers caught |
|---|---|---|---|
| 20 km/h | 0.0% | 89.5% | 13.2% |
| 40 km/h | 0.0% | 23.2% | 6.8% |
| 60 km/h | 0.0% | 2.5% | 4.7% |
| **80 km/h** | **0.0%** | **0.0%** | **3.8%** |

80 km/h was chosen for vendor safety rather than catch rate; measured p99
for motorised vendors is 69.6 km/h. A second limit bounds the daily range
at 80 km (metropolitan roving p99 is 53.6 km; intercity scattering
reaches 1,974 km). Where neither test fires, multi-area presence is
scored as **ignorance, not accusation** — weight 35, the same price as
"this place has never been recorded."

**(d) One spot shared by time of day.** An iced-fruit cart works
middays; in the evening a different legitimate vendor takes the exact
same spot. Both are real, both have their own QRIS. Under the old path
the second vendor was accused of sticker-swapping for **3 to 9 days** — a
cost paid by someone innocent, for a trading pattern that is everyday in
Indonesia.

The evidence was already in the data and simply unread: **alternation.**
The incumbent is scanned, then the challenger, then the incumbent
*again*. An overlay sticker structurally cannot produce that pattern:
once it covers the code beneath, that code can never be scanned again.
Measured in `calibrate_bergiliran.py`:

| Pattern | Incumbent re-appearances in 7 days |
|---|---|
| Legitimate shift-sharing | 6 |
| Overlay sticker (attack) | **0** |

The difference is zero, not merely small — so a genuine overlay never
passes this path at any threshold, because the number is structurally
nil. With alternation proven, the device requirement drops from 8 to 4,
and a quiet stall is accepted on day 5 instead of day 9. Verified
end-to-end in `tests/test_bergiliran.py`, including the three-vendor case
(morning nasi uduk, midday iced fruit, evening fried rice), where a
challenger faces two established anchors at once.

### 2. Artefact and behavioural anomaly engine — Layer 2

Inspects the code itself, even when the place is unknown. Weights and
their justification are in `docs/KALIBRASI-BOBOT.md`; the summary:

| Signal | Weight | Basis |
|---|---|---|
| Structural contradiction (static QR carrying an amount; missing mandatory tag; malformed NMID; malformed country code) | 70, hard | a compliant acquirer cannot issue it |
| Printed NMID ≠ encoded NMID | 75, hard | direct evidence of overlay, works on the first scan |
| Dynamic QR spread >150 m | 55 | 0.000% false positives (GPS error p99.9 = 34 m) |
| Implausible accuracy claim (<1.0 m) | 45 | no consumer GNSS reports below ~3 m |
| Printed name ≠ encoded name | 45 | legitimate drift exists (old stickers, trade names) |
| Invoice amount changed for the same bill reference | 35 | legitimate case exists: re-issued order |
| Dynamic QR reused ≥4× | 30 | 0.60% false positives |
| Ambient WiFi fingerprint mismatch | 30 | not yet field-calibrated |
| Failed device attestation / rooted device | 30 / 25 | reported by the client, vouched by the PJP |
| Issuer-dialect deviation | 18, capped 45 | a hint, not proof |
| Rare merchant profile (≥3 of 16 attributes rare) | 25 | 4.1% false positives on the real field corpus |
| Repeated anomaly attempts at this anchor | 12, capped 30, 7-day half-life | scales with evidence |
| Encoding fingerprint (tag order, CRC casing) | 15 / 10, capped 25 | **UNCALIBRATED** — capped so it can never move a tier alone |

Two of these are unsupervised models built from a corpus we collected
ourselves, with no fraud labels at all — because confirmed fraud examples
do not exist, and a supervised classifier cannot be trained without them:

- **Issuer dialect.** Each PJP's generator is deterministic in how it
  *assembles* a payload. A code claiming a given issuer but not following
  that issuer's dialect was re-generated by someone else. Profiles form
  only for issuers whose generators are consistent (`ISSUER_MIN_NMIDS` =
  5, `ISSUER_MIN_SHARE` = 0.90). Of 10 issuers in the field corpus, 5
  currently pass the threshold.
- **Merchant-profile rarity.** Records how often each attribute value
  occurs among observed merchants and flags payloads carrying several
  rare values at once. It names *which* attribute is rare and *how* rare
  — an opaque verdict has no place in a payment system. Leave-one-out
  against **122 real field-collected merchants** flags 5, a **4.1% false
  positive rate** (`evaluate_rarity.py`).

### 3. Persistence and zero-PII gateway

SQLite in WAL mode behind a single shared connection with explicit
locking, written for correctness under concurrency rather than for scale
(the Postgres migration plan is in `docs/DEPLOY.md`).

The schema is designed for UU PDP alignment: **no names, no phone
numbers, no user GPS traces.** What is stored is *how many distinct
devices*, never *which device*. The device reference is
`sha256(salt ‖ binding_id ‖ device_anon_id)` — **scoped per anchor**, so
the same phone produces a different reference at every place and cannot
be chained into a movement trail.

This is verified adversarially, not asserted:
`tests/test_invariants.py` invariant 8 enumerates the live schema (**69
columns across 13 tables**) and then attacks it — a JOIN attack, a
cross-location linkage attack, and a reference-counting attack all fail,
while de-duplication still works.

## 3.3 API Surface

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/verify` | the main pre-PIN assertion |
| `POST /api/v1/inspect` | payload analysis without coordinates (catalogue mode) |
| `POST /api/v1/tickets/verify` | ticket check for the settlement side |
| `POST /api/v1/merchants` | PJP registers a merchant–location binding |
| `DELETE /api/v1/merchants/{nmid}` | revocation |
| `POST /api/v1/assess-transfer` | manual bank-transfer risk assessment |
| `POST /api/v1/beneficiary-reports` | beneficiary account reports |
| `POST /api/v1/field` | field survey ingestion |
| `GET /api/v1/health` | health and corpus statistics |

Registration matters architecturally: it is the fast path out of cold
start (R4) and out of relocation (R5). A registered merchant is
`verified` immediately, without waiting for consensus — so the consensus
machinery is the fallback for the ~unregistered majority, not the only
route.

### The manual-transfer channel

`transfer.py` addresses the second major fraud channel, where there is no
artefact at all: the victim types an account number dictated over the
phone. There is no sticker, no payload, no anchor to verify.

What can be assessed is the *shape* of the transaction and what the PJP
already knows about the destination account. The module therefore
**receives telemetry from the PJP** — account age, beneficiary history,
transaction velocity — rather than collecting it. The PJP knows these
things; we do not, and should not. The pattern recognised is
social-engineering shape, not one person's behaviour, and the module
scores the **destination** account, which in a fraud scenario is the
perpetrator. Verified in `tests/test_transfer.py` (12 checks).

---

# CHAPTER IV — Technical Architecture & Feasibility

## 4.1 System Flow

A client scans a QRIS code. The app captures payload and GPS and routes
them through the PJP backend, which attaches its API key and calls
`POST /api/v1/verify`.

**Four gates run before any scoring**, and three of them deliberately
stop Layer 1 from running at all:

| Gate | Condition | Effect |
|---|---|---|
| 1 | payload unparseable, or no NMID | **422, stop.** No verdict, no ticket, nothing learned |
| 2 | `mock_location: true` | Layer 1 not run; location risk pinned at **65** |
| 3 | `from_image: true` | Layer 1 not run; location risk **0** |
| 4 | `accuracy_m > 100` | Layer 1 not run; location risk **40** |

In gates 2–4, **Layer 2 still runs in full.** A malformed payload is
malformed regardless of GPS quality; discarding that evidence because a
different sensor failed would be throwing away healthy proof.

Gate 4 is invariant §6 — with an 800 m confidence radius, hundreds of
shops fit inside the circle and scoring an anchor against it is not a
less accurate judgement but a meaningless one. Gate 2 is the same logic
with a different cause, priced higher because bad accuracy is misfortune
while a mock provider is intent. Gate 3 covers remote payment: the
payer's coordinates are real, but they say nothing about where the
sticker hangs.

Otherwise both layers evaluate, and the results are composed under three
rules:

1. Scores add and clamp to 0–100.
2. Layer 2 can only worsen the status: a hard contradiction forces
   `anomaly`; any other signal demotes `verified` to `unknown`. An
   `anomaly` from Layer 1 is never withdrawn by Layer 2.
3. The same four tiers and thresholds apply; Layer 2 introduces no new
   scale.

Reasons from both layers are **re-sorted by actual weight** before
display. Users read from the top and often stop at the first line, so the
line that decided the verdict must be the line they read.

**What the system learns** depends on the verdict, and the split is
deliberate:

| Outcome | Learns |
|---|---|
| `anomaly` | nothing — a fraudulent sticker must never build reputation (invariant §3) |
| replay or `from_image` | payload knowledge only (issuer dialect, attribute rarity) — never location |
| clean field scan | anchor, area city, ambient-WiFi fingerprint, and payload knowledge |

That second row came from a real incident: a team member catalogued QRIS
codes from the internet while sitting in an office, and seven codes from
Karanganyar to Mandailing Natal were all recorded at one point in
Jakarta, corrupting the area's learned city.

On a **location-related** anomaly, two records are written from opposite
viewpoints: the anchor's attempt counter is incremented, and the rejected
NMID is entered in a **challenge ledger**. That ledger is the route back
for honest vendors — the shift-sharing vendor and the relocating vendor
both prove themselves through it. Payload-only defects mark nothing;
scoring them against the place was a defect found in production, where
seven genuine merchants at one point had inherited four anomaly attempts
that all came from defective scam codes scanned there, not from any
swap attempt.

Finally, every response carries an HMAC-SHA256 verification ticket valid
for 90 seconds. On `cooling_off` the reference client never renders the
PIN screen at all — it is not hidden by CSS; it is never constructed —
and shows a 30-second countdown, because delay is what breaks time
pressure while refusal only sends the victim looking for another route.

## 4.2 Measured Performance

200 sequential `POST /api/v1/verify` requests over local SQLite,
re-measured on 30 September 2026:

```
p50 0.8 ms    p95 0.9 ms    p99 1.2 ms    max 5.1 ms
```

Against a 200 ms latency budget, that is roughly two hundred times
faster than required. Two caveats stated plainly:

- **This is not production volume.** It is a local SQLite instance with a
  small corpus. The figure demonstrates that the algorithm is not the
  bottleneck; it does not demonstrate production capacity.
- An earlier version was far slower for a real reason: the
  simultaneous-presence computation was O(n²) and took **481 ms at 1,000
  observations**. It is now O(k² + n log n), measured at **2.6 ms** on
  the same input. Two concurrency defects that lost 1 observation in 200
  were fixed at the same time.

---

# CHAPTER V — Security Architecture & Intellectual Property

## 5.1 Threat Matrix

| ID | Threat | Impact | Defence | Verification |
|---|---|---|---|---|
| T1 | Physical sticker overlay | High | Layer 1 consensus, weight `60 + min(25, observers/2)`; reaches `cooling_off` at ≥32 independent observers (83 at 47) | `test_invariants.py` (inv. 5), `test_bobot.py`, `test_adversarial.py` |
| T2 | Sybil cold-start flooding (<5 attacker devices) | High | consensus requires ≥3 distinct devices spanning 24 h; `ADJACENT_MIN_RATIO` = 0.10 blocks the minimum-capital attack | `test_adversarial.py` |
| T3 | Dynamic-QR reuse / invoice tampering | Medium | tag-62 bill tracking, amount caching, 48 h TTL; spread >150 m and reuse ≥4× | `test_adversarial.py` |
| T4 | Client-side TOCTOU bypass | High | stateless HMAC-SHA256 verification ticket | `test_ticket.py` |
| T5 | Database compromise / user tracking | High | zero-PII schema; anchor-scoped device hashing | `test_invariants.py` (inv. 8) |
| T6 | OS-level mock-location spoofing | Medium | dedicated gate: Layer 1 refuses to run, location risk pinned at 65; attestation vouched by the PJP | `test_hardening.py` |
| T7 | Implausible accuracy claim | Medium | accuracy below 1.0 m flagged at weight 45 | `test_adversarial.py` |
| T8 | Overlay under unusable GPS | Medium | ambient-WiFi fingerprint recognises the place; a foreign NMID there escalates to `step_up` | `test_adversarial.py` |
| T9 | Forged consensus via synthetic device IDs | High | **disclosed, not closed** — every verdict now carries `evidence.vouched_observers` and a `consensus_unvouched` signal | `test_konsensus.py` |
| T10 | False accusation of legitimate vendors | High | adjacency, relocation, roving, and shift-sharing exemptions, each empirically calibrated | `test_keliling.py`, `test_bergiliran.py`, `test_binding.py` |

T9 and T10 are in this table on purpose. T9 is a weakness we found in our
own system and chose to publish rather than hide; T10 treats harm to
honest merchants as a first-class threat, because a detector that accuses
real vendors will never be deployed by any PJP — the cashier rejects it
first.

## 5.2 Verification Ticket Architecture

A TOCTOU attack substitutes a different code between authorisation and
execution. Every Q-Shield verdict therefore carries the SHA-256
fingerprint of the scanned payload plus the verdict, signed with
HMAC-SHA256 and valid for 90 seconds. Before settling, the PJP approves
only if all four hold:

```
SHA-256(P_pay) = T.fp   ∧   HMAC-Verify(K_PJP, T)   ∧   Now < T.exp   ∧   T.action ∈ A_allowed
```

A tampered code fails the fingerprint check; a ticket carrying a refusal
fails the action check.

**What the ticket does not do**, stated because a payments audience will
find it anyway:

- It **binds but does not compel.** A PJP that ignores `cooling_off` will
  ignore the ticket too. Real enforcement requires the switch or acquirer
  to refuse settlement without a valid ticket — infrastructure-level, not
  library-level (R15).
- It **does not prevent replay.** The ticket is stateless and unstored,
  so the same code can be settled twice inside its 90-second window.
  Transaction idempotency belongs to the PJP (R16).
- HMAC rather than asymmetric signatures is a deliberate dependency
  trade-off, with the consequence recorded as R14: leaking
  `QSHIELD_API_KEYS` would allow ticket forgery in that PJP's name.

## 5.3 Intellectual Property Potential

**Method 1 — Multi-entity spatial consensus for offline payment terminal
verification.** Crowdsourcing trusted merchant anchors across disparate
payment service providers using bounded running-average coordinate
convergence and location-scoped hashing, such that participation
strengthens the shared map without any participant contributing personal
data.

**Method 2 — Alternation-based resolution of physical terminal
coexistence conflicts.** Resolving conflicts at a shared physical
location without manual onboarding, by requiring proof of **alternation**
— repeated re-appearance of the incumbent terminal after a challenger's
entry. The novelty is structural rather than statistical: an overlay
sticker cannot produce this pattern at all, because once it covers the
code beneath, that code can never be scanned again. The measured
separation is **zero versus six re-appearances per week**, not a margin
requiring a tuned threshold.

**Method 3 — Decoupled pre-PIN verification ticket protocol.** A
handshake generating an in-flight HMAC-SHA256 token that cryptographically
binds a pre-PIN risk verdict to the raw settlement payload digest under a
short TTL, allowing the verifying party and the settling party to be
different institutions.

## 5.4 Acknowledged Limits

Published in full at `docs/THREAT-MODEL.md`. Six remain open.

| ID | Limit | Why it stays open | What closes it |
|---|---|---|---|
| **R19** | The rarity model is blind to an attacker who copies a common profile | It scores how often a combination occurs; a copied dominant profile reads as entirely normal. Measured against 122 real merchants: profile-copying attackers pass | Not this layer — issuer dialect catches re-generated payloads, geospatial binding catches placement |
| **R20** | A sticker already swapped *before* being photographed cannot be caught from the payer's side | Q-Shield verifies placement, and a photo carries no place. The information was lost at the moment of the photograph | Protection must happen when photographing: an in-place scan, or a verification ticket for PJP-to-PJP integration |
| **R21** | Stickers scattered within one city, rarely scanned, are not separable from a roving vendor | The separator is physics, and the proof needs two cross-area observations close in time. With sparse observation only **3.8%** of scatterers leave it | Observation density — this evidence grows with adoption, with no tuning |
| **R22** | Consensus can be forged with synthetic device identities | `observer_count` grows from a client-supplied field. Measured: three invented strings spread past the age threshold turn a new anchor `verified` | Not a higher threshold — counting forgeable numbers still counts forgeable numbers. PJP registration, or attested observers |
| **R23** | Time thresholds do not burden an attacker who need not be present | Replacing the age threshold with "N distinct days" was evaluated and **cancelled**: coordinates are client-supplied, so "three different days" means three HTTP requests from a laptop | Recorded as a decision *not* taken, with its reasoning, so it is not revisited |
| **R24** | Part-time swapping is not separable from shift-sharing | An attacker who applies and *removes* the sticker daily produces exactly the alternation pattern | Not detection. What changes is cost: he must attend twice daily, forever, while letting his victim collect half the payments |

The honest summary of R21 and R24: the attack we actually defend against
— an overlay on an established merchant — is untouched by either. It is
caught as `nmid_changed_at_anchor` at `cooling_off`, and the attacker
never builds an anchor at all, because rejected scans build no reputation
(invariant §3).

## 5.5 Architectural Invariants

Eight decisions are locked by a regression suite whose purpose is to
*attempt to violate them* on every run. They are not features; features
may be replaced, invariants may not.

| # | Invariant | Reason |
|---|---|---|
| §1 | Geohash precision 7, not 8 | precision 8 covers only 44.4% of a 100 m radius under GPS drift; 7 covers 100% |
| §2 | `unknown` never means safe | absence of evidence is not evidence of absence |
| §3 | Rejected scans never build reputation | otherwise an attacker scans his own sticker into legitimacy |
| §4 | Four friction tiers, no fifth scale | integration consistency for PJPs |
| §5 | Consensus formula locked as written | the figures are quoted publicly and must stay true |
| §6 | GPS accuracy >100 m refuses a location verdict | guessing from an 800 m circle is not a judgement |
| §7 | Adjacent merchants are not sticker-swaps | food courts must not be accused |
| §8 | No user identity in the schema | 69 columns, 13 tables, three linkage attacks fail |

---

# CHAPTER VI — Scalability & Deployment Readiness

## 6.1 Deployment Topologies

**Model A — single PJP, private.** A PJP runs Q-Shield inside its own
infrastructure. Its app sends each scan to its own backend and no data
leaves the PJP. The merchant map is built only from that PJP's users.

**Model B — shared consortium.** All PJPs query one Q-Shield instance
before the PIN screen, over a single merchant-location map built from
every app's scans and containing no personal data. **A scan by one app's
user protects every other app's users.** After the PIN, the national
switch checks the verification ticket before settlement proceeds.

A PJP can start with Model A and join Model B later.

The difference is demonstrable rather than rhetorical:
`scripts/demo_lintas_pjp.py` runs both worlds side by side over an
identical event sequence — separate databases versus one shared binding
layer — so the causal link is visible. On two phones a judge sees only
two screens and cannot see that the protection on the second came from a
scan on the first.

## 6.2 Native Mobile SDK Seam

The integration boundary for Android (Kotlin) clients is defined in
`sdk/README.md`, backed by **ten request/response fixtures** in
`sdk/contract/` generated from the code and an OpenAPI schema, and kept
from going stale by `tests/test_sdk_contract.py`.

1. **On-device pre-parsing.** The SDK performs EMVCo TLV parsing in
   native memory. Non-EMVCo codes (URLs, phishing links) are rejected
   locally with no HTTP round trip.

2. **Device attestation slot.** The client gathers hardware attestation
   via Play Integrity or App Attest and populates `device_integrity`:

   ```json
   { "mock_location": false, "rooted": false,
     "attested": true, "platform": "android" }
   ```

   The trust chain is stated explicitly: **Q-Shield cannot verify these
   fields.** What gives them meaning is `attested` — a result the PJP
   verifies on its own side and then stands behind with its API key. We
   do not trust the device; we trust the PJP that says it checked. A scan
   only counts as *vouched* when attestation is present **and** the
   client is authenticated; an anonymous scanner claiming
   `attested: true` counts for nothing.

3. **Latency budget.** Q-Shield adds one HTTP call against a 200 ms
   budget (§4.2). Client behaviour on timeout is a PJP integration
   decision and is **not yet specified in the SDK contract** — see the
   open items below.

**Open SDK items, stated rather than implied:** timeout and offline
fallback behaviour, and a gallery-input entry point for the `from_image`
path (the backend side is complete and tested; the client control is
not).

## 6.3 Dual-Mode Web Scanner

`src/qshield/web/index.html` is a single file with no build step. It
includes multi-camera selection that steers away from the ultra-wide
(0.5×) lens toward the 1× main camera with continuous autofocus —
written after a real failure, where `facingMode: "environment"` selected
an ultra-wide lens whose minimum focus distance made QRIS codes
unreadable on some phones.

- **Verification mode** (`POST /api/v1/verify`) — captures live GPS and
  emits full risk scoring.
- **Catalogue mode** (`POST /api/v1/inspect`) — dispatches raw payloads
  without coordinates, for corpus building and merchant-side auditing.

A **replay mode** exists for indoor demonstration, where GPS routinely
reports accuracy above 100 m and invariant §6 correctly refuses a
verdict. Replayed scans are marked explicitly in four places — the
request (`location_source`), the response, the leading reason line, and
the audit trail — scoring is unchanged, and replay cannot be used to
bypass the accuracy invariant (`tests/test_hardening.py`).

---

## Appendix — Reproducing Every Number in This Report

```bash
python3 tests/test_invariants.py        # the eight invariants
python3 tests/test_bobot.py             # every weight quoted here
python3 scripts/enam_belas_ciri.py      # §1.4, the 16 attributes
python3 scripts/calibrate_keliling.py   # roving-vendor table
python3 scripts/calibrate_bergiliran.py # alternation: 6 vs 0
python3 scripts/calibrate_dynamic.py    # dynamic-QR thresholds
python3 scripts/evaluate_rarity.py      # 4.1% false positives
python3 scripts/demo_lintas_pjp.py      # Model A vs Model B
python3 scripts/diagnose.py PAYLOAD LAT LNG   # dissect one scan
```

Supporting documents: `docs/THREAT-MODEL.md` (R1–R24),
`docs/KALIBRASI-BOBOT.md` (why each weight is what it is),
`docs/panduan/ALUR-KERJA.md` (scan walkthrough),
`docs/API.md` (contract and versioning policy),
`docs/PROCESS-LOG.md` (decision history).
