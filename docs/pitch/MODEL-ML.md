# Komponen machine learning Q-Shield — cara menyebutnya

> Dokumen internal tim. Bukan surat, bukan koreksi. Isinya: apa yang
> sebenarnya berjalan, nama teknis yang tepat untuk menyebutnya, bukti
> yang bisa ditunjukkan kalau ditanya, dan garis yang tidak boleh
> dilewati.

---

## Klaim di POC: "unsupervised ML models" — benar, pertahankan

Klaim itu **akurat**. Q-Shield memuat dua model pembelajaran tak
terawasi yang berjalan di produksi hari ini, plus empat komponen lain
yang pengetahuannya dibentuk dari data pengamatan.

Tidak perlu dikoreksi, tidak perlu diperhalus, tidak perlu minta maaf.
Yang perlu adalah **menyebutnya dengan presisi**, karena juri track
keamanan akan menguji apakah kalian paham yang kalian bangun.

---

## Dua model, sebutkan namanya

### 1. Model kelangkaan profil merchant — `src/qshield/profile.py`

Deteksi pencilan tak terawasi pada data kategorikal.

Sistem mengestimasi **sebaran marginal empiris** delapan ciri merchant
dari korpus yang diamati — kategori usaha (MCC), skala usaha, kota,
panjang nomor akun, keberadaan kode pos, tipe statis/dinamis, mata
uang, kode negara. Sebuah nilai disebut langka bila muncul pada kurang
dari 5% merchant. Payload yang membawa **tiga atau lebih** nilai langka
sekaligus ditandai.

| Parameter | Nilai | Arti |
|---|---|---|
| `MIN_CORPUS` | 40 | di bawah ini model diam — "langka" tidak punya arti pada data sedikit |
| `RARE_THRESHOLD` | 0,05 | ambang kelangkaan per nilai |
| `MIN_RARE_FEATURES` | 3 | satu keanehan bukan apa-apa; tiga sekaligus adalah pola |
| `W_RARE_PROFILE` | 25 | sama dengan ambang `proceed`, sehingga sinyal ini tidak pernah menggeser tier sendirian |

Keluarga metodenya: **frequency-based categorical outlier detection**,
sekerabat dengan Attribute Value Frequency (AVF). Bedanya, AVF
merata-ratakan frekuensi seluruh atribut jadi satu skor; kita memakai
ambang per-atribut lalu menuntut konjungsi minimal tiga — supaya
putusannya bisa menyebut **fitur mana** yang langka dan **seberapa**.

> Kalau mau mencantumkan sitasi AVF di slide, verifikasi dulu
> referensinya. Tanpa sitasi pun deskripsi di atas sudah berdiri
> sendiri.

### 2. Model dialek penerbit — `issuer_dialect`

Mempelajari **cara tiap penyelenggara menyusun payload**, bukan isinya:
urutan field, nomor template merchant, susunan sub-tag, gaya penulisan
checksum, panjang nomor akun, panjang Merchant ID.

Sebuah atribut baru dipakai menilai bila disepakati **≥5 NMID berbeda**
(`ISSUER_MIN_NMIDS`) dan **≥90%** dari merchant penerbit itu
(`ISSUER_MIN_SHARE`). Penyimpangan berbobot 18 per atribut, maksimum 45.

Sengaja tidak memuat apa pun yang khas satu merchant — bukan NMID,
bukan nama, bukan kota. Yang dikumpulkan gaya penerbitnya.

---

## Empat komponen adaptif lain

| Komponen | Yang dipelajari |
|---|---|
| Konsensus pengamat | reputasi lokasi terbentuk dari pengamatan banyak perangkat independen |
| Penghalusan jangkar | koordinat menajam seiring pengamatan — galat 6,9 m → 1,3 m pada 47 pengamatan |
| Pengetahuan wilayah (`area_city`) | kota yang berlaku di suatu wilayah disimpulkan dari merchant sekitarnya, tidak ditanam sebagai tabel |
| Jejak percobaan serangan | riwayat per lokasi, dengan peluruhan waktu |

---

## Bukti yang bisa ditunjukkan

**Korpus produksi hari ini:** 122 merchant, 10 penerbit, 5 di antaranya
sudah melewati ambang `ISSUER_MIN_NMIDS` — semuanya dikumpulkan di
lapangan oleh tim, bukan dibangkitkan.

**Kalibrasi ambang kelangkaan** (`scripts/calibrate_rarity.py`), sapuan
yang menentukan `RARE_THRESHOLD = 0,05`. Diukur pada populasi
**sintetis** — sebut itu kalau mengutipnya, dan lanjutkan ke angka
lapangan di bawahnya:

| ambang | sah tertandai | kombinasi langka tertangkap | payload ngawur tertangkap |
|---|---|---|---|
| 0,02 | 0,00% | **0%** | 100% |
| **0,05** | **0,07%** | **100%** | **100%** |
| 0,08 | 0,13% | 100% | 100% |
| 0,12 | 3,23% | 100% | 100% |

0,02 ditolak bukan karena lemah menangkap, tapi karena pada ambang itu
model merosot jadi sekadar deteksi "nilai tak dikenal" — bukan deteksi
kelangkaan.

**Evaluasi terhadap merchant sungguhan** (`scripts/evaluate_rarity.py`,
metode leave-one-out: tiap merchant dinilai terhadap korpus yang
dibentuk 121 merchant lainnya, sehingga tidak ikut membentuk sebaran
yang menilainya). Semua merchant di korpus ini SAH, jadi setiap yang
tertandai adalah positif palsu:

> **5 dari 122 merchant sah tertandai — 4,1%.**

Angka ini **berbeda jauh dari 0,07% pada populasi sintetis**, dan
perbedaannya sendiri adalah temuan. Penyebabnya ditemukan lalu
diperbaiki: fitur `kota` punya 79 nilai berbeda untuk 122 merchant, dan
kota terbanyak pun hanya 6 merchant (4,9%) — di bawah ambang langka.
Artinya **seluruh** nilai kota terbaca langka, dan fitur itu memberi
satu "fitur langka" gratis kepada setiap merchant, termasuk yang sah.
Konjungsi tiga fitur diam-diam merosot jadi konjungsi dua. Setelah
fitur semacam itu dilewati, positif palsu turun 8,2% → 4,1% tanpa
kehilangan satu pun deteksi.

Kalau ditanya kenapa angkanya tidak nol: karena korpus merchant
sungguhan memang memuat merchant yang tidak biasa, dan model yang
menandai nol dari 122 juga akan menandai nol dari serangan.

Yang menjaga kelima merchant itu tetap hijau adalah bobotnya: 25, persis
ambang `proceed`. Angka itu bukan selera — status VERIFIED di
`binding.py` menuntut `score <= 25`, jadi bobot 26 ke atas membuat
sinyal ini sendirian mencabut status hijau merchant sah, dan kelangkaan
adalah sifat payload yang tidak bisa dihapus dengan dipindai lebih
sering. Pada 25 ia tidak pernah menggeser tier sendirian, dan tetap
berarti begitu ditemani sinyal lain.

**Dialek penerbit**, penerbit `93600914` dari korpus lapangan kita:
keenam atributnya konsisten **51 dari 51 merchant**. Payload yang
mengaku dari penerbit itu tapi disusun ulang orang lain langsung
menyimpang — dan sistem menyebut atribut mana yang menyimpang.

Keduanya bisa dijalankan di depan juri. Itu poin yang lebih kuat
daripada angka akurasi mana pun.

**Batas yang disebut duluan, jangan ditunggu ditanya.** Model
kelangkaan buta terhadap penyerang yang menyalin profil lazim — MCC
5812, kriteria UMI, PAN 18 digit terbaca sepenuhnya normal. Diukur
terhadap korpus nyata: penyerang seperti itu lolos, begitu pula yang
hanya menyimpang di dua ciri. Itu memang bukan tugas lapisan ini —
QR yang dibangkitkan ulang ditangkap model dialek, dan penempatan
stikernya ditangkap ikatan geospasial. Tercatat sebagai R19 di
`THREAT-MODEL.md`.

---

## Garis yang tidak boleh dilewati

Ini yang akan membuat kalian kehilangan kredibilitas kalau disebut:

- ❌ "deep learning", "neural network", "LLM"
- ❌ "dilatih dengan data penipuan" — sampel penipuan terkonfirmasi yang
  kita punya **nol**
- ❌ akurasi / precision / recall / AUC terhadap data berlabel — tidak
  ada labelnya
- ❌ "model kami mendeteksi QRIS palsu" — lihat bagian berikut

Yang aman dan benar: **unsupervised anomaly detection**, **statistical
learning dari pengamatan**, **empirical distribution**, **sebaran
marginal**, **deteksi pencilan kategorikal**.

---

## Kenapa tidak ada classifier terawasi — ini kekuatan, bukan kekurangan

Jalur itu **sudah kami uji dan tolak dengan alasan**, dan ini justru
temuan yang mendasari seluruh arsitektur Q-Shield.

Enam belas ciri payload diekstrak lalu dibandingkan antara stiker asli
dan stiker pengganti pada skenario sticker-swap:

> **Nol dari enam belas ciri berbeda.**

Sebabnya mendasar. Pelaku sticker-swap **tidak memalsukan QR**. Ia
mendaftarkan akun merchant sungguhan pada penyelenggara sungguhan,
menerima stiker terbitan resmi, lalu menempelkannya menutupi stiker
merchant lain. Payload-nya memang sah. Classifier yang dilatih
mengenali "pola QRIS asli" akan mengklasifikasikannya **asli** — karena
memang asli.

Penipuannya tidak ada di dalam kode, melainkan pada **penempatannya** —
dan penempatan tidak terekam di payload. Karena itu Q-Shield mengikat
identitas merchant ke tempat, bukan ke bentuk kode.

Tiga alasan, singkat, untuk dijawab di sesi tanya jawab:

1. **Tidak ada sinyal di payload** — 0 dari 16 ciri berbeda.
2. **Tidak ada data latih** — sampel penipuan terkonfirmasi nol;
   classifier butuh dua kelas. Model yang dilatih pada data bangkitan
   sendiri hanya belajar mengenali generator kita sendiri.
3. **Auditabilitas** — sistem pembayaran tunduk pengawasan regulator.
   Aturan yang bekerja di atas sebaran empiris bisa menjawab "mengapa
   putusan ini diambil" kalimat per kalimat. Model buram menjawabnya
   dengan angka yang tidak bisa ditelusuri.

---

## Kalau juri bertanya

**"Modelnya apa? Arsitekturnya?"**

> Dua model tak terawasi. Yang pertama deteksi pencilan kategorikal
> berbasis frekuensi — kami mengestimasi sebaran marginal delapan ciri
> merchant dari korpus, dan menandai payload yang membawa tiga nilai
> langka sekaligus. Yang kedua model dialek penerbit — ciri penyusunan
> payload tiap penyelenggara, dipelajari dari 122 merchant yang kami
> kumpulkan di lapangan. Tidak ada jaringan saraf; yang ada sebaran
> empiris. Itu pilihan sadar, dan saya bisa jelaskan kenapa.

**"Kenapa tidak pakai classifier?"** → tiga alasan di atas. Mulai dari
"0 dari 16".

**"Berapa akurasinya?"**

> Tidak ada angka akurasi berlabel, karena tidak ada sampel penipuan
> terkonfirmasi — kami tidak akan mengarang labelnya. Yang kami punya
> angka positif palsu terhadap merchant sungguhan: kami memindai 122
> merchant di lapangan, lalu menilai tiap merchant terhadap korpus yang
> dibentuk 121 lainnya. Lima tertandai — 4,1%. Kombinasi yang tidak
> pernah terjadi pada populasi nyata tertangkap 100%. Keduanya bisa
> dijalankan sekarang juga dari repo.
>
> Angka itu sempat 8,2%, dan cara kami menemukannya mungkin lebih
> menarik daripada angkanya: fitur kota punya 79 nilai untuk 122
> merchant, sehingga bahkan kota terbanyak pun terbaca langka dan
> memberi satu fitur langka gratis ke setiap merchant. Kalibrasi
> sintetis kami tidak pernah menunjukkan itu karena sebaran buatan
> selalu lebih rapi daripada kenyataan.

**"Ini machine learning atau rule-based?"**

> Keduanya, dan sengaja. Pengetahuannya dipelajari dari data tanpa
> label — itu bagian machine learning-nya. Keputusannya deterministik
> di atas pengetahuan itu — itu yang membuat tiap putusan bisa
> dijelaskan ke pengguna dan auditor.

---

## Satu hal yang wajib

**Sepakati satu bahasa bertiga.** Kalau satu orang bilang "kami pakai
ML" dan yang lain bilang "sistem kami deterministik, bukan ML" di sesi
yang sama, itu lebih merusak daripada salah istilah. Jawaban yang benar
memuat keduanya, dan urutannya: *belajar tanpa label, memutuskan secara
deterministik.*
