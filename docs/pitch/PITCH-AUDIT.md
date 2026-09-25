# Audit naskah pitch terhadap sistem yang berjalan

Tiap kalimat naskah 15 Agustus diperiksa ke kode. Status ditentukan
dengan menjalankan atau membaca kodenya, bukan dari ingatan.

---

## Ringkasan

**Diperbarui 20 September 2026.** Audit pertama menemukan delapan klaim
yang tidak ada di sistem. Tim memutuskan menyesuaikan sistem ke naskah,
bukan sebaliknya, karena naskah itu sudah lolos juri.

| | Audit pertama | Sekarang |
|---|---|---|
| Akurat | 8 | 8 |
| Perlu diperhalus | 2 | 2 |
| Tidak ada di sistem | **8** | **0** |

Kedelapan-delapannya sudah dibangun dan diuji. Dua di antaranya menuntut
kalimat yang lebih tepat — bukan karena kemampuannya tidak ada,
melainkan karena kalimat aslinya menjanjikan lebih dari yang dilakukan.
Rinciannya di bawah.

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

## Yang dibangun sejak audit pertama

Kedelapan klaim di bawah dulu tidak ada. Sekarang ada, dengan
penunjuk buktinya masing-masing.

### 1. "hashed WiFi BSSIDs" — ADA

Aplikasi native meng-hash BSSID dengan SHA-256 di sisi klien; yang
mentah tidak pernah meninggalkan perangkat. Server menyimpannya per
binding di tabel `binding_ap`, membandingkannya di
`behavior._ap_signals()`, dan mencari jangkar dari sidik jarinya di
`store.locate_by_ap()`.

Korpus lapangan sungguhan sudah terkumpul: empat merchant, 31–32 titik
akses masing-masing.

**Bisa diperagakan.** Pindai di dalam ruangan, tunjukkan
`location_source: "wifi"` di tanggapan.

### 2. "stays reliable even indoors" — ADA, tapi kalimatnya perlu tepat

Jalur akurasi rendah kini membaca sidik jari WiFi. Diukur dari data
lapangan tim:

| | irisan Jaccard |
|---|---|
| tempat sama (1–3 m) | 0,66 – 0,80 |
| tempat berbeda (116 km) | 0,00 |

Sebelumnya semua pemindaian akurasi rendah menghasilkan `warn` datar —
stiker asli dan stiker tukar diperlakukan sama persis. Sekarang stiker
tukar di dalam ruangan naik ke `step_up` dengan alasan yang menyebut
nama merchant yang seharusnya ada di tempat itu.

**Yang belum, dan jangan diklaim:** WiFi tidak pernah dipakai MEMBERI
izin. Merchant sah di dalam ruangan tetap berhenti di `warn`, bukan
`proceed`. Sebabnya jujur — korpusnya baru memuat tempat sama dan
tempat sangat jauh; kasus tengah, ruko sebelah yang berbagi titik
akses, belum terukur. Itu diuji sebagai batasan yang disengaja di
`test_adversarial.py`.

Kalimat yang aman dan tetap kuat:

> *"Indoors, where GPS drifts to hundreds of metres, we fall back to
> the ambient WiFi fingerprint — so we can still tell whether this
> sticker belongs in this place."*

Itu benar seluruhnya, dan justru lebih menarik: ia menyebut mekanisme,
bukan janji.

### 3. "unsupervised ML models" — ADA, dengan istilah yang tepat

`profile.py` mempelajari sebaran ciri merchant dari korpus dan menandai
profil yang langka; `area_city` dan `issuer_dialect` mempelajari
kebiasaan wilayah dan penerbit. Semuanya tanpa label, tanpa data
latih — pembelajaran statistik tak terawasi dalam arti sebenarnya.

Yang TIDAK ada: jaringan saraf, bobot terlatih, berkas model. Kalau
juri bertanya "modelnya apa", jawaban yang benar adalah sebaran
empiris, bukan arsitektur. Naskah jawabannya di `MODEL-ML.md` —
termasuk nama teknis tiap model dan bukti yang bisa dijalankan di
depan juri.

### 4–7. Sinyal transfer manual — ADA

`transfer.py` memuat keempatnya sebagai field `TransferTelemetry`:

| klaim | field |
|---|---|
| transaction velocity | `transfers_last_hour` |
| account age | `beneficiary_account_age_days` |
| first-time beneficiaries | `first_time_beneficiary` |
| active call telemetry | `call_active` |

Dikalibrasi supaya tidak ada sinyal tunggal yang mencapai `step_up`
sendirian: 1,4% gesekan pada transfer sah, 89,6% pola penipuan
tertangkap.

**Batasan yang harus disebut kalau ditanya:** angka itu dari model
sebaran, bukan data transaksi sungguhan — Q-Shield tidak punya akses ke
data PJP. Yang dibangun adalah lapisannya; kalibrasi sungguhan menunggu
integrasi.

### 8. "pola korban yang sedang dipandu penipu" — ADA

`transfer.evaluate()` menggabungkan keempat sinyal di atas. Pola yang
dicarinya: penerima baru, rekening muda, panggilan sedang aktif,
transfer beruntun dalam satu jam. Itu bentuk khas korban yang sedang
dituntun lewat telepon.

---

## Kenapa ketepatan kalimat tetap menentukan

Track ini **Secure Digital Payments**, dan jurinya termasuk Kaspersky.
Pertanyaan "tunjukkan WiFi fingerprinting-nya" bukan pertanyaan yang
mustahil muncul — itu justru hal yang menarik perhatian orang keamanan.

Sekarang pertanyaan itu bisa dijawab dengan demo. Yang berubah bukan
cuma status klaimnya, tapi posisi kalian saat ditanya.

Tetap ada satu hal yang tidak berubah: **sekali satu klaim terbukti
lebih besar dari kenyataannya, juri akan menguji ulang semua klaim
lain** — termasuk yang benar-benar kuat. Karena itu dua kalimat di
bagian 2 dan 3 tetap harus diperhalus. Bukan karena kemampuannya tidak
ada, melainkan karena kalimat aslinya menjanjikan sedikit lebih banyak
daripada yang bisa ditunjukkan.

Menyebut batasan sendiri lebih dulu juga menguntungkan. Suite
adversarial kalian memuat enam serangan yang **diakui belum ditahan**,
dan itu satu-satunya alasan angka-angka lainnya layak dipercaya.

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
| 16 ciri, nol berbeda | **Sebutkan presisinya**: 12 ciri struktural, nol berbeda; nol dari 16 terhadap penipu yang mencocokkan isian pendaftaran. Nama & kota sengaja di luar daftar dan diumumkan begitu. Peragaan: `scripts/enam_belas_ciri.py`, dikunci `tests/test_enam_belas.py` |
| privasi | `python tests/test_invariants.py` |
