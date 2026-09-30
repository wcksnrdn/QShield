# Kenapa angkanya segitu

Dokumen ini menjawab satu pertanyaan yang pantas ditanyakan siapa pun
yang membaca kode ini: **kalau sebuah sinyal memang fatal, kenapa cuma
diberi +75 dan bukan +100?**

Jawabannya bukan "biar aman-aman saja". Ada tiga aturan desain yang
membuat angka nanggung itu justru yang benar, dan di bawahnya ada
tabel lengkap dari mana tiap angka berasal.

---

## 1. Jawaban singkatnya

**Status dan tier itu dua hal berbeda, dan yang fatal sudah ditangani
di status — bukan di skor.**

Sinyal yang sungguh-sungguh kontradiktif ditandai `hard=True`. Lewat
`binding.compose()`, penandaan itu **memaksa status jadi `anomaly`
tanpa melihat skor sama sekali**:

```python
if behavior.hard_violation:
    status = ANOMALY
```

Jadi menaikkan bobotnya dari 75 ke 100 **tidak mengubah status sedikit
pun** — ia sudah `anomaly` pada 75, pada 70, bahkan pada 1.

Yang diatur bobot adalah **tier friksi**: seberapa keras sistem menahan
pembayaran. Dan itu memang harus bisa dipengaruhi bukti lain.

---

## 2. Tiga aturan yang membuat 100 justru merusak

### Aturan 1 — skor itu anggaran yang dijumlah, bukan probabilitas

Sinyal tidak datang sendiri-sendiri. Layer 1 dan Layer 2 dijumlahkan,
lalu dijepit ke 0–100:

```python
score = max(0, min(100, verdict.risk_score + behavior.score))
```

Begitu sebuah bobot dipasang 100, ia **menjenuhkan jumlahnya**. Semua
yang ditambahkan sesudahnya tidak berarti apa-apa — dan sistem
kehilangan kemampuan membedakan:

```
stiker tempel di tempat yang belum dikenal   100
stiker tempel di jangkar mapan 47 pengamat   100   <- padahal jauh lebih pasti
```

Dengan 75, dua kasus itu tetap terpisah, dan jejak auditnya tetap bisa
merekonstruksi mana yang lebih kuat.

### Aturan 2 — urutan alasan mengikuti bobot

Sejak Keputusan 47, alasan yang dibaca pengguna diurutkan menurut bobot
sebenarnya, bukan urutan kode dijalankan:

```python
bobot_l1 = verdict.reason_weights or [0] * len(verdict.reasons)
berbobot = list(zip(bobot_l1, verdict.reasons))
berbobot += list(zip(behavior.weights, behavior.reasons))
alasan, bobot = urutkan_alasan(berbobot)
```

Kalau semua sinyal fatal bernilai 100, **urutannya jadi sembarang**.
Pengguna membaca dari atas dan sering berhenti di baris pertama; yang
muncul di situ harus yang paling menentukan.

Ini bukan teori — inilah persis bug yang diperbaiki Keputusan 47.
Sebelumnya "lokasi ini belum pernah tercatat" (+35, paling lemah) muncul
**di atas** "format Merchant ID tidak sesuai standar" (+70, yang
menentukan). Yang paling tidak penting dibaca duluan, yang menuduh
tersembunyi.

### Aturan 3 — bobot 100 mematikan Layer 1

Ini yang paling penting, dan paling mudah dilewatkan.

`printed_nmid_mismatch` bergantung pada **teks tercetak** — diketik
pengguna atau hasil OCR klien. OCR salah baca. Pengguna salah ketik.

Dengan bobot 100, satu huruf yang salah dibaca OCR **memblokir total**
sebuah QR yang sudah dikonfirmasi 47 pengamatan di titik itu. Dengan 75,
bukti Layer 1 masih punya suara.

Buktinya bisa dijalankan:

```
Layer 1 paling rendah yang mungkin (jangkar mapan, NMID cocok): skor 0

  +75  printed_nmid_mismatch      ->  75  anomaly/step_up
```

Di seluruh konteks lain, ia tetap memblokir:

```
konteks Layer 1                      skor L1   +L2   total  putusan
--------------------------------------------------------------------
tempat baru (first_observation)           35    75     100  anomaly/cooling_off
binding muda, 1 pengamat                  15    75      90  anomaly/cooling_off
jangkar mapan milik merchant lain         83    75     100  anomaly/cooling_off
```

> **Baris pertama itu yang membenarkan angka 75.** QR yang dikonfirmasi
> 47 pengamatan, dengan label yang tidak cocok, mendapat `step_up` —
> *minta verifikasi* — bukan `cooling_off`. Itu putusan yang benar:
> dalam keadaan itu yang paling mungkin salah justru **labelnya**,
> bukan kodenya. Pada 100, kasus ini mustahil dibedakan.

---

## 2b. Dua demonstrasi yang bisa dijalankan sendiri

**Demonstrasi 1 — bobot tidak menentukan status.**
Sinyal `hard=True` yang sama, bobotnya diubah-ubah, di tempat yang belum
pernah tercatat (Layer 1 = 35):

```
hard_violation, bobot   1 -> skor  36  anomaly/warn
hard_violation, bobot  10 -> skor  45  anomaly/warn
hard_violation, bobot  70 -> skor 100  anomaly/cooling_off
hard_violation, bobot  75 -> skor 100  anomaly/cooling_off
hard_violation, bobot 100 -> skor 100  anomaly/cooling_off
```

Dua hal terbaca sekaligus. Pertama, **statusnya `anomaly` pada bobot
1 sekalipun** — bobot tidak ada urusannya dengan itu. Kedua, di atas
65 **skornya sudah jenuh**: 70, 75, dan 100 menghasilkan putusan yang
identik. Menaikkan 75 jadi 100 di konteks ini tidak membeli apa pun.

**Demonstrasi 2 — di mana selisihnya benar-benar terasa.**
Layer 1 paling rendah yang mungkin: jangkar mapan 47 pengamat, NMID
cocok, tanpa konflik → skor **0**.

```
  +75  printed_nmid_mismatch      ->  75  anomaly/step_up
  +70  W_STRUCTURAL               ->  70  anomaly/step_up
  +55  W_DYNAMIC_SPREAD           ->  55  unknown/step_up
  +45  W_PRINTED_NAME_MISMATCH    ->  45  unknown/warn
  +40  W_CITY_MISMATCH            ->  40  unknown/warn
  +30  W_DYNAMIC_REUSED           ->  30  unknown/warn
  +25  W_RARE_PROFILE             ->  25  unknown/warn
```

**Inilah satu-satunya tempat selisih 75 vs 100 menentukan hasil** — dan
hasilnya justru yang kita mau. QR yang dikonfirmasi 47 pengamatan,
dengan label tercetak yang tidak cocok, mendapat `step_up`: *minta
verifikasi*, bukan *tahan*. Dalam keadaan itu yang paling mungkin salah
adalah OCR-nya, bukan kodenya.

**Catatan ketelitian soal `W_RARE_PROFILE` = 25.** Komentar di
`profile.py` menyebut bobot di atas 25 sebagai "veto permanen terhadap
verifikasi". Diukur langsung, kalimat itu **terlalu kuat**: `compose()`
menurunkan `verified` jadi `unknown` begitu ada sinyal Layer 2 apa pun,
jadi pada 25 pun merchant yang tertandai tidak bisa `verified`.

Yang benar-benar dibeli angka 25 adalah **tier**, dan selisihnya nyata
begitu ada sinyal kedua:

```
jangkar mapan + kelangkaan 25 + sidik jari 25  ->  50  warn
jangkar mapan + kelangkaan 30 + sidik jari 25  ->  55  step_up
```

Itu persis yang diukur `calibrate_rarity_weight.py`: dari 1.392
kombinasi bobot, **12 melemah satu tier**, umumnya pasangan kelangkaan
dengan satu sinyal 25–30 lain yang turun dari `step_up` ke `warn`.
Ditukar dengan berhentinya 4,1% merchant sah di korpus lapangan
tertandai lebih keras dari yang pantas. Pertukaran itu dipilih sadar.

Prinsip yang berlaku dan bisa dinyatakan tanpa berlebihan:
**pada 25 sinyal ini tidak pernah menggeser tier sendirian** — skor 25
adalah batas atas pita `proceed`.

---

## 3. Dari mana tiap angka berasal

### Ambang tier — kerangka yang mengikat semuanya

```
skor  0-25   proceed      bayar saja
     26-50   warn         lanjutkan, tapi baca alasannya
     51-75   step_up      minta verifikasi tambahan
     76-100  cooling_off  tahan
```

Terkunci sebagai **invarian §4**. Setiap bobot di bawah dipilih relatif
terhadap empat batas ini — itulah kenapa angkanya terlihat "nanggung":
masing-masing punya tier tujuan yang spesifik.

Satu konsekuensi yang harus selalu diingat:

> `verified` menuntut `skor <= 25`. Jadi **bobot mana pun di atas 25
> yang bisa menyala pada merchant sah adalah veto verifikasi permanen.**

### Layer 1 — ikatan merchant-lokasi

| bobot | sinyal | kenapa segitu | sumber |
|---|---|---|---|
| **90** | `anchor_name_impersonation` | Sengaja **di atas** `60+confidence` milik `nmid_changed_at_anchor`, karena urutan alasan mengikuti bobot. "Kode ini memakai nama yang sama dengan merchant di sini" adalah fakta yang membuat orang berhenti; "Merchant ID berbeda dari 47 pengamatan" tidak. | Keputusan 47 |
| **85** | `nmid_changed_at_registered_anchor` | Dipilih supaya **sendirian pun mendarat di `cooling_off` (≥76)**, setara konflik konsensus 50 pengamat. Datar, bukan berskala — pendaftaran adalah pernyataan penyelenggara, kekuatannya tidak bertambah karena lebih banyak orang memindai. | — |
| **60 + min(25, obs//2)** | `nmid_changed_at_anchor` | Berskala dengan kekuatan bukti. 3 pengamat → 61, 47 → 83, 50 → 85 (mentok). Rumusnya **terkunci invarian §5** karena angka-angka ini dipakai di pitch. | `test_invariants.py` §5 |
| **45** | `nmid_name_inconsistent` | Satu NMID membawa dua nama merchant berbeda. Penipu yang memakai satu akun untuk banyak korban harus mengganti tag 59 agar cocok dengan nama toko tiap korban. Ditempatkan di **`warn` teratas**: cukup untuk membatalkan `verified`, tidak cukup untuk menuduh sendirian, karena merchant sah memang kadang berganti nama dagang. | penempatan tier; tidak ada skrip khusus |
| **40** | `city_mismatch` | Kota di QR ≠ kota yang dipelajari untuk wilayah itu. Ditahan **di bawah 50** karena wilayah perbatasan kota memang terbelah. Pengaman sebenarnya bukan bobot ini melainkan syarat pembentukan wilayah: `AREA_CITY_MIN_NMIDS` = 5 NMID **berbeda** dan `AREA_CITY_MIN_SHARE` = 0,75 suara — jadi seribu pemindaian dari satu stiker palsu tetap satu suara. | penempatan tier; positif palsu diukur `calibrate_falsepos.py` |
| **35** | `first_observation` | Harga **ketidaktahuan** tentang sebuah tempat. Cukup untuk menolak `verified` (>25), tidak pernah sendirian mencapai `step_up` (≤50). | — |
| **35** | `nmid_multi_area` tanpa bukti serentak | Bukan angka baru — **sengaja disamakan dengan `first_observation`.** Ketidaktahuan tentang *pola* tempat pantas dihargai sama dengan ketidaktahuan tentang *tempat*. | Keputusan 80 |
| **25** | `nmid_relocated` | Merchant yang **terbukti** pindah, menggantikan 60 milik `nmid_scatter`. | `calibrate_relokasi.py` |
| **20** | `adjacent_merchant_unproven` | **Aritmetika tier murni**: ditambah `young_binding` (15) menghasilkan tepat **35 — `warn`**, dengan margin ke `step_up` di 50. Sengaja tidak mencapai `proceed`: tenant ini boleh dibayar, tapi pembelinya harus membaca namanya dulu. Ambang koeksistensi yang menyertainya (`ADJACENT_MIN_RATIO` = 0,10) diukur terpisah. | `calibrate_adjacency.py`, `calibrate_tetangga.py` |
| **18** (cap 45) | `issuer_dialect_deviation` | **Sedang dengan sengaja**: penyimpangan dialek adalah petunjuk, bukan bukti. Positif palsu yang tersisa setara laju variasi sah penerbit itu sendiri — generator diperbarui, merchant lama memakai versi sebelumnya, integrator pihak ketiga. | `calibrate_issuer.py` |
| **15** | `young_binding` | Di bawah 25, jadi tidak sendirian membatalkan `proceed` — tapi `_floor_action()` mencegahnya jadi `proceed` lewat invarian §2. | — |
| **−20** | `established_binding` / `registered_merchant` | Satu-satunya arah turun di seluruh sistem, dan hanya berlaku kalau **tidak ada konflik dan tidak ada sebaran**. | — |

### Layer 2 — perilaku artefak QR

| bobot | sinyal | kenapa segitu | sumber |
|---|---|---|---|
| **75** `hard` | `printed_nmid_mismatch` | NMID tercetak ≠ NMID di dalam QR. Bukti pertukaran yang **langsung, pada pemindaian pertama**, tanpa perlu riwayat apa pun. Tidak 100 karena masukannya OCR — lihat Aturan 3 di atas. | — |
| **70** `hard` | 4 kontradiksi struktural: `static_qr_with_amount`, `missing_mandatory_tags`, `malformed_nmid`, `malformed_country` | **Bukan probabilistik** — acquirer yang patuh spec tidak bisa menerbitkannya. Terukur: ditambah konteks Layer 1 termurah yang realistis (`young_binding` 15) hasilnya 85 → `cooling_off`. | `calibrate_layer2.py` (laju positif palsu terhadap payload sah) |
| **55** | `dynamic_qr_spread` (>150 m) | **Lebih berat dari `reused`** dengan sengaja: empat kali pemindaian masih punya penjelasan wajar, satu QR yang dipindai di dua tempat berjauhan tidak. Ambang 150 m menandai **0,000%** QR dinamis sah (galat GPS p99,9 = 34 m). | `calibrate_dynamic.py` |
| **45** | `implausible_accuracy` (<1,0 m) | GNSS ponsel konsumen tidak pernah melaporkan radius keyakinan di bawah 1 m; yang terbaik berhenti di ~3 m. Ambangnya sengaja **jauh di bawah** kemampuan perangkat asli supaya nyaris mustahil menandai pemindaian sah. | — |
| **45** | `printed_name_mismatch` | Lebih ringan dari NMID-nya karena nama **memang sering berbeda secara sah**: stiker lama, nama dagang vs nama badan usaha, singkatan. | — |
| **35** | `bill_amount_changed` | Serius, tapi **tidak** dijadikan kontradiksi keras: ada kasus sah — pesanan ditambah, kasir menerbitkan ulang QR untuk tagihan yang sama. Yang membuatnya tetap berguna: alasannya menyebut **kedua** nominalnya, jadi pengguna bisa memeriksa sendiri ke layar kasir. | `calibrate_dynamic.py` |
| **30** | `dynamic_qr_reused` (≥4×) | Ambang 4 menandai **0,60%** QR dinamis sah. | `calibrate_dynamic.py` |
| **30** | `ap_fingerprint_mismatch` | Sidik jari WiFi sekitar tidak cocok. | belum dikalibrasi lapangan |
| **30** | `attestation_failed` | Lebih berat dari `rooted`: atestasi gagal berarti pemeriksaan yang **dijalankan PJP** menolak perangkat itu. | — |
| **25** | `device_rooted` | Dilaporkan klien, tidak bisa diverifikasi. Di bawah 26 supaya tidak sendirian menggeser tier dari `warn`. | — |
| **25** | `ap_foreign_nmid` | Ditambah 40 dasar jalur akurasi rendah → **65 = `step_up`, bukan `cooling_off`**, dan itu disengaja. Korpus sidik jari belum memuat kasus beda-tempat-tapi-berdekatan (ruko sebelah). Pelajaran R11: tuduhan palsu terhadap pedagang sah mahal harganya. | sidik jari lapangan |
| **25** | `rare_merchant_profile` (≥3 dari 16 ciri) | Diturunkan dari 30. 25 adalah batas atas pita `proceed`, jadi sinyal ini **tidak pernah menggeser tier sendirian** — sesuai niat modulnya: satu keanehan bukan apa-apa. Diukur leave-one-out pada 122 merchant lapangan: 5 tertandai = **4,1% positif palsu**. | `calibrate_rarity_weight.py`, `evaluate_rarity.py` |
| **12** naik, cap **30** | `repeated_anomaly_attempts` | Berskala dengan kekuatan bukti, pola yang sama dengan invarian §5. Memudar dengan paruh waktu **7 hari**: merchant sah yang muncul sebulan kemudian tidak lagi dihukum, sementara penyerang harus menunggu ~3 minggu — dan selama menunggu itu stikernya tidak menghasilkan apa pun. | `calibrate_decay.py` |
| **15 / 10**, cap **25** | `noncanonical_tag_order`, `noncanonical_crc_case` | **UNCALIBRATED dan diakui begitu.** Bobotnya sengaja kecil dan totalnya dibatasi agar **tidak pernah bisa menggerakkan tier sendirian**. | — |

---

## 4. Kenapa tidak ada bobot negatif di Layer 2

Nol, sama sekali. Ini bukan kelalaian:

> Tidak adanya sinyal Layer 2 **bukan bukti keabsahan** — logika yang
> sama dengan invarian §2.

Kalau Layer 2 boleh mengurangi skor, penyerang yang menyusun payload
yang bersih secara struktural bisa **membeli kembali** kepercayaan yang
dicabut Layer 1. Struktur payload sepenuhnya dalam kendali penyerang;
riwayat lokasi tidak.

Ini penerapan prinsip yang mengatur seluruh sistem:

> **Nilai yang dikendalikan penyerang boleh memperketat, tidak pernah
> memperlonggar.**

---

## 5. Sinyal yang DIBUANG, dan kenapa

Sama pentingnya dengan yang ada. Keduanya tercatat di kode supaya tidak
ada yang menambahkannya kembali tanpa membaca alasannya.

**`scan_burst` (lonjakan pemindaian) — dibuang.** Membangun reputasi
palsu hanya butuh `MIN_OBSERVERS=3` dalam `MIN_AGE_HOURS=24`, jadi
serangannya pelan — puncaknya 3 pemindaian. Sapuan di
`calibrate_layer2.py`:

```
ambang yang ditoleransi warung laris (>=120/jam)  -> melewatkan 100% serangan
ambang yang cukup rendah untuk menangkapnya       -> menandai 100% merchant sibuk
```

Volume tidak memisahkan keduanya. Pertahanan yang benar untuk probing
otomatis adalah **rate limiting**, bukan skor risiko.

**`accuracy_missing` (akurasi tidak dikirim) — dibuang.** Menghukum
absennya sebuah field sambil mendeklarasikan field itu opsional adalah
desain yang tidak koheren. Dan absennya membuka pintu keluar dari
invarian §6 — terlalu serius untuk diselesaikan dengan menambah skor.
Sekarang `accuracy_m` **wajib**, dan permintaan tanpanya ditolak 422 di
batas sistem.

---

## 6. Yang belum dikalibrasi, dinyatakan terbuka

Ini daftarnya, lengkap. Semuanya ditandai `UNCALIBRATED` di kode.

| parameter | kenapa belum | pengamannya sekarang |
|---|---|---|
| `W_TAG_ORDER` = 15, `W_CRC_CASE` = 10 | Memisahkan "dicetak ulang penyerang" dari "generator yang rewel" butuh korpus payload QRIS asli yang belum kami punya | `SOFT_FINGERPRINT_CAP` = 25 — tidak pernah bisa menggerakkan tier sendirian |
| `AP_MIN_KNOWN` = 4, `AP_MIN_OVERLAP` = 0,15 | Berapa titik akses yang wajar berubah antara dua kunjungan tidak bisa ditebak dari simulasi | Hanya berlaku bila jangkar sudah punya sidik jari cukup besar |
| `AP_LOCATE_MIN_OVERLAP` = 0,45 | Korpus belum memuat kasus **tempat berbeda yang berdekatan** (ruko sebelah, lantai atas) | Sidik jari WiFi **tidak pernah** dipakai memberi `proceed` |

---

## 7. Cara memeriksa ulang angka mana pun

```bash
python3 tests/test_bobot.py                 # angka yang dikutip dokumen INI
python3 tests/test_invariants.py            # kedelapan invarian
python3 scripts/calibrate_layer2.py         # bobot struktural
python3 scripts/calibrate_dynamic.py        # ambang QR dinamis
python3 scripts/calibrate_rarity_weight.py  # bobot kelangkaan
python3 scripts/evaluate_rarity.py          # positif palsu vs korpus lapangan
python3 scripts/calibrate_keliling.py       # ambang pedagang keliling
python3 scripts/calibrate_bergiliran.py     # ambang bergiliran
python3 scripts/calibrate_decay.py          # paruh waktu jejak serangan
python3 scripts/diagnose.py PAYLOAD LAT LNG # bongkar satu pemindaian
```

---

## Ringkasnya untuk juri

Kalau ditanya "kenapa 75 dan bukan 100", jawabannya tiga kalimat:

1. Sinyal fatal **sudah** memaksa `anomaly` lewat `hard_violation` —
   bobotnya tidak menentukan itu.
2. Bobot menentukan **tier friksi**, dan tier harus tetap bisa
   dipengaruhi bukti lain, karena masukannya (OCR, teks yang diketik)
   bisa salah.
3. Bobot 100 menjenuhkan penjumlahan, merusak urutan alasan yang dibaca
   pengguna, dan menghapus kemampuan audit membedakan kasus yang kuat
   dari yang sangat kuat.

Angka yang dikutip dokumen ini dikunci di `tests/test_bobot.py`, supaya
ia tidak basi diam-diam begitu ada bobot yang digeser. Dokumen yang
angkanya salah lebih buruk daripada tidak ada dokumen.

**Tidak satu pun angka di sistem ini adalah tebakan yang dibiarkan.**
Yang punya dasar empiris menyebut skrip kalibrasinya; yang belum punya
ditandai `UNCALIBRATED` dan diberi pembatas supaya tidak bisa
menggerakkan putusan sendirian.
