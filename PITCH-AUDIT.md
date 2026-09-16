# Audit naskah pitch terhadap sistem yang berjalan

Tiap kalimat naskah 15 Agustus diperiksa ke kode. Status ditentukan
dengan menjalankan atau membaca kodenya, bukan dari ingatan.

---

## Ringkasan

| | Jumlah |
|---|---|
| Akurat | 8 |
| Perlu diperhalus | 2 |
| **Tidak ada di sistem** | **8** |

Delapan klaim terakhir bukan soal istilah. Semuanya menyebut kemampuan
yang tidak pernah ada — dan beberapa di antaranya **tidak mungkin ada**
pada PoC berbasis web.

---

## Yang akurat, pertahankan apa adanya

| Klaim | Bukti |
|---|---|
| Arsitektur dua lapis | `binding.py` + `behavior.py` |
| Layer 1 memeriksa konsistensi Merchant ID di satu lokasi lintas waktu | `evaluate()`, konsensus pengamat |
| Di bawah 200 ms, sebelum PIN | terukur p50 2,8 ms, p95 3,7 ms |
| Respons berjenjang, bukan biner | empat tier, invarian §4 |
| Cooling-off untuk risiko tertinggi | `_action_for()` |
| Nol perubahan pada standar QRIS | tidak ada penerbitan ulang QR |
| Nol perangkat tambahan untuk merchant | stiker yang sama dipakai |
| Menandai Merchant ID yang berubah di jangkar mapan, dan satu ID yang tersebar di banyak lokasi | `nmid_changed_at_anchor`, `nmid_scatter` |

---

## Yang perlu diperhalus

**"parsing the EMVCo payload offline — entirely on-device"**

Parsing terjadi di **server**, bukan di perangkat. Frontend mengirim
payload mentah ke `POST /api/v1/verify`, lalu `api.py` memanggil
`emvco.parse()`.

Ganti dengan: *"parses the EMVCo payload and validates the CRC16
checksum — no network round-trip to any third party."* Itu benar dan
tetap kuat: pemeriksaannya tidak menghubungi pihak luar mana pun.

**"catch social engineering on manual transfers"**

Di luar jangkauan, dan itu keputusan arsitektural (Keputusan 9): pada
transfer manual tidak ada artefak yang bisa diperiksa sebelum korban
menekan kirim.

Ganti dengan menyebut apa yang Layer 2 **benar-benar** tangkap — lihat
naskah baru di bawah.

---

## Yang tidak ada di sistem

Delapan ini harus dihapus atau diganti sebelum 3 Oktober.

### 1. "hashed WiFi BSSIDs"

**Tidak ada sama sekali.** Diperiksa: `bssid` dan `ssid` nol
kemunculan di seluruh kode.

Ini yang paling serius, karena **tidak mungkin ada** pada PoC berbasis
web — browser tidak menyediakan API untuk memindai WiFi, dan memang
tidak akan pernah, karena itu sidik jari lokasi yang kuat.

Catatan kalian sendiri mencatatnya sebagai kebutuhan MASA DEPAN:
*"Perlu ambient WiFi fingerprinting — tidak tersedia di browser,
karenanya PoC ini berbasis web dan MVP memerlukan SDK native."*

### 2. "stays reliable even indoors, where GPS alone tends to drift"

Konsekuensi dari klaim di atas, dan **berlawanan dengan perilaku
sebenarnya**. Invarian §6 justru **menolak memberi putusan** ketika
akurasi GPS di atas 100 m — persis kondisi dalam ruangan.

Itu bukan kelemahan yang perlu ditutupi. Itu fitur, dan jawaban yang
lebih baik: *"when the signal is too poor to trust, we refuse to give a
verdict rather than guess."*

### 3. "unsupervised ML models"

Tidak ada model apa pun. Lihat `KLARIFIKASI-ML.md`.

### 4. "transaction velocity"

Pernah ada, lalu **dibuang setelah dikalibrasi** (Keputusan 13).
Alasannya terukur: membangun reputasi palsu butuh 3 perangkat dalam 24
jam, jadi serangannya pelan. Ambang mana pun yang menangkapnya menandai
100% warung laris.

Menyebutnya sekarang bukan cuma keliru — itu menyebut sesuatu yang
kalian **sengaja tolak dengan data**.

### 5. "account age"

Tidak ada. Sistem tidak pernah melihat akun pengguna — invarian §8
melarang identitas pengguna di skema mana pun.

### 6. "first-time beneficiaries"

Tidak ada, dan menuntut data penerima transfer yang hanya dimiliki PJP.

### 7. "active call telemetry"

Tidak ada. Mendeteksi korban sedang ditelepon menuntut izin akses
panggilan — yang tidak tersedia di browser, dan akan menjadi masalah
privasi besar kalau ada.

### 8. "catching the pattern of someone being guided through a scam in
real time"

Konsekuensi dari nomor 4–7. Tidak ada satu pun sinyalnya.

---

## Kenapa ini penting diperbaiki sekarang

Track ini **Secure Digital Payments**, dan jurinya termasuk Kaspersky.
Pertanyaan "tunjukkan WiFi fingerprinting-nya" bukan pertanyaan yang
mustahil muncul — itu justru hal yang menarik perhatian orang keamanan.

Dan risikonya bukan sekadar satu klaim gugur. Sekali satu kemampuan
terbukti tidak ada, juri akan menguji ulang **semua** klaim lain —
termasuk delapan yang benar-benar akurat dan kuat.

---

## Naskah pengganti

Panjang setara, struktur sama, tiap kalimat bisa ditunjukkan demonya.

### Segmen 1 — arsitektur

> Q-Shield runs on a two-layer architecture.
>
> The first layer checks spatial consensus — whether a merchant's ID has
> stayed consistent at this exact location over time, across many
> independent devices.
>
> The second layer reads the QR artifact itself — structural
> contradictions against the EMVCo spec, issuer dialects learned from
> real payloads, dynamic codes being reused or re-priced, and device
> integrity when the host app can report it.
>
> Both run in under two hundred milliseconds — we measure two point
> eight — before PIN entry. And critically, the response isn't binary.
> It's graduated, from a soft warning to a full cooling-off period, so
> legitimate transactions never get needlessly blocked.
>
> All of this requires zero changes to the QRIS standard, and no extra
> hardware for merchants.

### Segmen 2 — Layer 1

> Layer 1 parses the EMVCo payload and validates the CRC16 checksum
> directly — no round-trip to any third party.
>
> It then anchors the scan by distance, not by grid cell. We tested grid
> matching first: a twenty-metre GPS drift broke it in eighty-two
> percent of cases. Distance-based anchoring at geohash precision seven
> covers a hundred percent of points within a hundred metres.
>
> And the anchor sharpens as it's observed — the coordinate is a running
> average, so error drops from about seven metres to one metre across
> forty-seven observations.
>
> Trust is established by consensus. The system flags a merchant ID that
> changes at an already-established anchor, or a single ID deployed
> across multiple separate sites.
>
> When GPS accuracy is too poor to trust — above a hundred metres — we
> refuse to return a location verdict at all. We'd rather say we don't
> know than guess.

### Segmen 3 — Layer 2

> Layer 2 requires no labelled fraud data to start working — and that's
> deliberate, because confirmed fraud samples don't exist for a system
> that hasn't shipped.
>
> Instead it learns from what it observes. Which city the merchants in a
> given area report. How each payment provider's generator assembles its
> payloads. How often a location has been targeted, decaying over time.
>
> That lets it catch things on the very first scan of a sticker it has
> never seen: a QR registered in another city, a single merchant ID
> carrying two different business names, a dynamic code whose amount
> changed under the same bill number.
>
> We tested the machine-learning route and rejected it with evidence.
> Sixteen payload features, compared between a genuine sticker and a
> swapped one — zero differed. Because the fraudster's sticker is
> genuinely issued by a real acquirer. The fraud isn't in the code, it's
> in the placement.
>
> So every decision here is deterministic and explainable — which is
> what a payments regulator will actually ask for.

---

## Yang bisa diperagakan langsung

Tiap klaim di naskah baru punya buktinya:

| Segmen | Perintah |
|---|---|
| latensi, empat tier | `python tests/test_api.py` |
| 81,9% dan presisi 7 | `python scripts/calibrate_geo.py` |
| penajaman jangkar | `python tests/test_invariants.py` |
| tolak putusan saat GPS buruk | `python tests/test_invariants.py` |
| deteksi scan pertama | `python tests/test_adversarial.py` |
| 16 ciri, nol berbeda | ada di `PROCESS-LOG.md` Keputusan 39 |
| privasi | `python tests/test_invariants.py` |
