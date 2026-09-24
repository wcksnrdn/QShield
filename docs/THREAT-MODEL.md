# Q-Shield — Threat Model

**Status:** draf untuk direview Filbert Alfredo Saputro
**Versi:** 1.0 — 10 September 2026
**Cakupan:** Q-Shield Layer 1 (ikatan merchant-lokasi) dan Layer 2 (perilaku artefak QR)

Setiap mitigasi di dokumen ini menunjuk ke test yang membuktikannya.
Klaim keamanan tanpa test yang menjalankannya adalah klaim kosong, dan
kolom terakhir di tiap tabel ada supaya itu bisa diperiksa, bukan
dipercaya.

---

## 1. Apa yang Q-Shield lakukan, dan apa yang tidak

Menyebut batasnya lebih dulu mencegah dokumen ini mengklaim wilayah yang
bukan miliknya.

**Yang dilakukan.** Q-Shield adalah lapisan verifikasi kepercayaan
**pra-pembayaran**. Ia menjawab satu pertanyaan sebelum pengguna
memasukkan PIN: apakah artefak QR yang barusan dipindai memang milik
merchant yang seharusnya berada di lokasi ini.

**Yang tidak dilakukan.** Q-Shield bukan sistem pembayaran, tidak
menyentuh dana, tidak memindahkan uang, dan tidak menggantikan
pemeriksaan mana pun yang sudah dilakukan PJP. Ia juga tidak mengubah
standar QRIS maupun perangkat merchant — justru itu prasyarat desainnya.

**Konsekuensi keamanan yang penting:** karena Q-Shield tidak memindahkan
dana, kompromi total terhadapnya **tidak** langsung menyebabkan kerugian
finansial. Yang hilang adalah sinyal peringatan. Ini menurunkan dampak
sebagian besar ancaman di bawah, dan disebut di sini supaya penilaian
risikonya proporsional.

---

## 2. Batas kepercayaan

```
  [Pengguna + kamera HP]           ZONA TIDAK DIPERCAYA
            │                      artefak fisik dikendalikan siapa saja
            │  payload QRIS, lat/lng, accuracy, device_anon_id
            ▼
  ══════════════════════════════   BATAS 1: masuk API
            │                      validasi ketat, rate limit, batas ukuran
            ▼
  [FastAPI /api/v1/verify]         ZONA SEMI-DIPERCAYA
            │                      logika penilaian, tanpa state per-pengguna
            ▼
  ══════════════════════════════   BATAS 2: masuk penyimpanan
            │                      query berparameter, skema tanpa identitas
            ▼
  [SQLite / Postgres]              ZONA DIPERCAYA
            │                      bindings + observations
            ▼
  ══════════════════════════════   BATAS 3: keluar ke log
            │                      audit tanpa PII
            ▼
  [stdout / agregator log]
```

Yang paling menentukan: **Batas 1**. Semua yang datang dari klien —
termasuk koordinat dan `accuracy_m` — adalah klaim, bukan fakta. Server
tidak punya cara memverifikasinya secara independen. Seluruh dokumen ini
berdiri di atas pengakuan itu.

---

## 3. Aset

| # | Aset | Kenapa berharga bagi penyerang | Dampak bila jatuh |
|---|---|---|---|
| A1 | Integritas basis data binding | binding palsu yang terlihat mapan membuat stiker penipu lolos sebagai `verified` | **Tinggi** — inti nilai sistem |
| A2 | Ketersediaan endpoint verifikasi | verifikasi mati = pengguna kembali membayar tanpa perlindungan | Sedang |
| A3 | Privasi lokasi pengguna | data pergerakan bernilai komersial dan berisiko hukum (UU PDP) | **Tinggi** — lihat §7 |
| A4 | Kredibilitas putusan | positif palsu beruntun membuat pengguna mengabaikan peringatan | Sedang-Tinggi |
| A5 | Jejak audit | jejak yang bisa dipalsukan/dihapus menutupi serangan | Sedang |

Perhatikan A4. Sistem anti-fraud yang terlalu sering salah akan
diabaikan, dan pengguna yang mengabaikan peringatan sama tidak
terlindunginya dengan pengguna yang tidak punya sistem sama sekali.
Positif palsu diperlakukan sebagai ancaman keamanan di dokumen ini,
bukan sekadar gangguan UX.

---

## 4. Profil penyerang

| Profil | Kemampuan | Motivasi |
|---|---|---|
| **P1 — Penempel stiker** | akses fisik ke lokasi merchant, printer, HP biasa | mengalihkan pembayaran ke rekeningnya |
| **P2 — Penipu terkoordinasi** | P1 + banyak perangkat, banyak lokasi, mampu skrip | mencemari basis data agar stikernya terlihat sah |
| **P3 — Penyerang teknis** | akses API langsung, mampu memalsukan permintaan, mock location, perangkat di-root | membobol atau memutarbalikkan logika penilaian |
| **P4 — Penguntit privasi** | akses baca ke basis data atau log (orang dalam, atau lewat kebocoran) | merekonstruksi pergerakan orang |
| **P5 — Perusak** | akses API, tanpa target finansial | membuat sistem tidak berguna atau tidak dipercaya |

---

## 5. Ancaman, mitigasi, dan buktinya

### 5.1 Terhadap integritas binding (A1)

| # | Ancaman | Aktor | Mitigasi | Bukti |
|---|---|---|---|---|
| T1 | Sticker swap: stiker penipu menutupi yang asli | P1 | Konflik NMID di jangkar mapan → `anomaly`, bobot berskala dengan jumlah pengamat | `test_adversarial.py` "Sticker swap di jangkar mapan"; `test_invariants.py` #5 |
| T2 | Swap sambil menggeser titik GPS agar jatuh di sel geohash lain | P1, P3 | Jangkar ditentukan **jarak haversine**, bukan kesamaan sel; indeks presisi 7 + 8 tetangga mencakup 100% radius 100 m | `test_adversarial.py` (60 posisi dalam radius 45 m, nol lolos); `test_invariants.py` #1 |
| T3 | Membangun reputasi dengan memindai stiker sendiri berulang kali | P2 | Pemindaian `anomaly` tidak pernah dicatat sebagai observation | `test_invariants.py` #3 (8x); `test_adversarial.py` (25x) |
| T4 | Priming pelan di lokasi kosong lalu klaim `verified` | P2 | Butuh `MIN_OBSERVERS`=3 **dan** `MIN_AGE_HOURS`=24; status tetap `unknown` sampai keduanya terpenuhi | `test_adversarial.py` (30 device boneka) |
| T5 | Ketiadaan bukti dikonversi jadi kepercayaan | P2 | `unknown` tidak pernah menghasilkan `proceed`, dijaga struktural di `_floor_action()` | `test_invariants.py` #2 |
| T6 | Stiker dicetak ulang dengan CRC yang benar | P1, P3 | CRC valid tidak menyelamatkan; jangkar yang menangkap. Layer 2 menambah deteksi kontradiksi struktural | `test_adversarial.py` "CRC ditambal"; "NMID dipalsukan" |
| T7 | Payload dibangkitkan ulang oleh generator penyerang | P3 | Sinyal struktural Layer 2: QR statis membawa nominal, tag wajib hilang, NMID cacat bentuk — 0 positif palsu dari 20.000 payload sah | `calibrate_layer2.py` bagian 2 |
| T40 | Tag wajib hadir tapi isinya cacat, lolos karena hanya kehadirannya diperiksa | P3 | Nilai tag 58 diperiksa BENTUKNYA (alpha-2, dua huruf) — bukan negaranya, supaya keterhubungan QRIS lintas negara tidak dihukum | `test_adversarial.py` "Kode negara cacat bentuk" |

### 5.2 Terhadap ketersediaan (A2)

| # | Ancaman | Aktor | Mitigasi | Bukti |
|---|---|---|---|---|
| T8 | Payload raksasa menghabiskan CPU parser | P3, P5 | Badan permintaan dipotong 8 KB di lapisan HTTP; payload dibatasi 1024 karakter. 8 MB kini ditolak 43 ms (sebelumnya 1.890 ms) | `test_hardening.py` "Payload kebesaran" |
| T9 | Banjir permintaan | P3, P5 | Rate limit jendela geser, bawaan 60/menit per klien | `test_hardening.py` "Rate limit menahan banjir" |
| T10 | Penghitung rate limit sendiri jadi jalur kehabisan memori | P5 | `MAX_TRACKED_KEYS` + pemangkasan kunci kedaluwarsa | `limits.py:_prune` |

### 5.3 Terhadap kredibilitas putusan (A4)

| # | Ancaman | Aktor | Mitigasi | Bukti |
|---|---|---|---|---|
| T35 | Menyeret jangkar merchant jujur menjauh dari lokasinya | P5 | Batas geser 20 m dari titik mula-mula; hanya pengamat BARU yang menggeser; pemindaian di luar sel geohash membuat binding baru alih-alih menggeser | `test_invariants.py` #1 "Jangkar menajam" — 500 device, seretan berhenti di batas |
| T11 | Meracuni jangkar merchant jujur agar skornya naik (DoS reputasi) | P5 | `repeated_anomaly_at_anchor` dimatikan bila yang memindai adalah merchant **mapan** di jangkar itu; "mapan" diambil dari putusan Layer 1 | `test_adversarial.py` "Meracuni jangkar merchant jujur" |
| T12 | Merchant bersebelahan saling memicu alarm | — (bukan serangan, tapi merusak A4) | Koeksistensi dibedakan dari penggantian: bila keduanya mapan dan aktif → `adjacent_merchant`, bobot ringan | `test_invariants.py` #7 (jarak 5-35 m) |
| T13 | Putusan palsu dari GPS yang tidak layak dipercaya | P3 | `accuracy_m` > 100 m → menolak memberi putusan lokasi, `unknown` + alasan eksplisit | `test_invariants.py` #6 |
| T39 | Nominal QR dinamis diubah, nomor tagihan tetap | P3 | Nominal dilacak per nomor tagihan (tag 62) dengan masa hidup 48 jam; perubahan ditandai dan **kedua nominalnya disebut** agar pengguna bisa mencocokkan sendiri ke layar kasir | `test_adversarial.py` "Nominal QR dinamis diubah" |
| T36 | Satu QR dinamis disebar ke banyak korban | P2 | Sebaran jarak dan jumlah pemakaian dilacak per payload; ambang dikalibrasi terhadap perilaku pemindaian yang sah | `test_adversarial.py` "disebar ke banyak korban" |
| T37 | Sinyal pemakaian ulang menuduh stiker statis | — (positif palsu, aset A4) | Sinyal hanya berlaku bila tag 01 = dinamis | `test_adversarial.py` "statis tidak ikut tertuduh" |
| T38 | QR dibangkitkan ulang generator lain, mengaku dari PJP yang sah | P3 | Dialek penerbit dipelajari per prefiks PAN; penyimpangan susunan ditandai. TIDAK menangkap sticker-swap, yang payload-nya diterbitkan resmi | `test_adversarial.py` "dibangkitkan ulang oleh generator lain" |
| T28 | Akurasi dikarang di bawah batas fisik perangkat | P3 | GNSS ponsel tidak pernah melaporkan radius <1 m; nilai di bawah itu ditandai `implausible_accuracy` | `test_adversarial.py` "Akurasi GPS dikarang" |
| T29 | `accuracy_m` dihilangkan untuk melewati T13 | P3 | Field ini **wajib**; absennya ditolak `422` di batas sistem, bukan diberi skor | `test_adversarial.py` "Akurasi dihilangkan" |
| T32 | Perangkat di-root / aplikasi dimodifikasi | P3 | Dilaporkan klien native lewat `device_integrity`; `rooted` dan `attested: false` diberi skor | `test_contract.py` "Integritas perangkat opsional" |
| T33 | GPS dipalsukan di perangkat yang melaporkan jujur | P3 | `mock_location: true` menolak memberi putusan lokasi sama sekali — perlakuan yang sama dengan akurasi buruk, karena masalahnya sama | `test_contract.py` "Integritas perangkat opsional" |
| T34 | Klien berbohong soal integritasnya sendiri | P3 | Tidak bisa dicegah Q-Shield. `attested` bermakna hanya karena PJP memverifikasinya di sisi mereka dan mempertanggungkannya lewat kunci API — kepercayaan pada PJP, bukan pada perangkat | `INTEGRATION.md` §3 |
| T41 | Verifikasi QR A, lalu eksekusi pembayaran ke QR B | P3, P5 | Tiket verifikasi mengikat putusan ke sidik jari payload; pihak yang mengeksekusi menghitung ulang dan menuntutnya cocok | `test_ticket.py` "SERANGAN: verifikasi QR A, bayar QR B" |
| T42 | Tiket dicuri, dirusak, atau dipakai lewat masa berlaku | P3, P5 | HMAC-SHA256 + `compare_digest`; TTL 90 detik; tiket dari masa depan ditolak | `test_ticket.py` "Tiket rusak, palsu, dan kedaluwarsa" — 5 bentuk serangan |
| T43 | Jejak audit salah melabeli peristiwa integritas, sehingga auditor melewatkannya | — (bug, bukan serangan) | Ketiga cabang `verify()` wajib meneruskan status integritas yang sama dengan tanggapannya; dulu cabang mock location jatuh ke bawaan `not_provided` | `test_hardening.py` "Jejak audit mencatat status integritas yang SEBENARNYA" — 4 keadaan × 3 cabang |
| T14 | Sinyal yang menandai merchant sah sebagai penyerang | — | Konstanta wajib punya dasar empiris; sinyal yang gagal kalibrasi dibuang, bukan dipaksakan | `calibrate_layer2.py` — sinyal lonjakan pemindaian dibuang |

### 5.4 Terhadap privasi (A3)

| # | Ancaman | Aktor | Mitigasi | Bukti |
|---|---|---|---|---|
| T15 | Basis data dipakai merekonstruksi pergerakan orang | P4 | Tidak ada `user_id` di skema mana pun; `observations` tidak menyimpan koordinat **dan** menyimpan rujukan perangkat yang dilingkupi per-binding, sehingga barisnya tidak bisa dirangkai antar-lokasi | `test_invariants.py` #8 — menjalankan tiga serangan, bukan memeriksa nama kolom |
| T16 | Jejak audit membocorkan apa yang tidak dibocorkan skema | P4 | Log tidak pernah memuat `device_anon_id`, koordinat presisi, IP, atau payload mentah. Lokasi dicatat sebagai sel ~152 m | `test_hardening.py` "Audit log tidak memuat identitas" |
| T17 | Alamat IP tersimpan lewat rate limiter | P4 | Kunci = hash SHA-256 terpotong, hanya di memori, hilang saat jendela lewat | `test_hardening.py` "Rate limit tidak menyimpan alamat IP" |
| T18 | Agregat Layer 2 diam-diam memperkenalkan pelacakan | P4 | Agregat menempel pada baris **binding**, bukan device: hitungan dan waktu, bukan siapa | `test_invariants.py` #8 (skema diperiksa ulang tiap run) |

### 5.5 Terhadap batas masuk (semua aset)

| # | Ancaman | Aktor | Mitigasi | Bukti |
|---|---|---|---|---|
| T25 | Pihak tak dikenal mengirim pengamatan ke API | P2, P3, P5 | Kunci API per PJP; tanpa kunci valid endpoint verifikasi menolak. Gagal tertutup bila belum dikonfigurasi | `test_hardening.py` "menolak klien tanpa kunci"; "gagal TERTUTUP" |
| T26 | Kunci API bocor lewat log atau konfigurasi | P4 | Kunci disimpan sebagai sha256; kunci mentah tidak pernah dicatat, bahkan saat autentikasi gagal | `test_hardening.py` "tidak pernah masuk log"; "disimpan sebagai hash" |
| T30 | Kunci PJP bocor dipakai mendaftarkan stiker palsu | P3 | Tidak bisa dicegah — ini konsekuensi jalur kepercayaan. Dimitigasi agar terlacak dan bisa dibatalkan: pendaftar dicatat, PJP lain tidak bisa membajak (409) atau mencabut (403), dan sinyalnya selalu dibedakan dari konsensus | `test_registration.py` bagian "Penyalahgunaannya" |
| T31 | PJP membajak pendaftaran merchant PJP lain | P3 | NMID yang sudah terdaftar menolak pendaftaran dari PJP berbeda | `test_registration.py` "tidak bisa membajak" |
| T27 | Kunci ditebak lewat pengukuran waktu | P3 | `hmac.compare_digest`, dan seluruh daftar ditelusuri sampai habis | `auth.ClientRegistry.authenticate` |
| T19 | SQL injection lewat `device_anon_id` atau payload | P3 | Seluruh query berparameter; `device_anon_id` dibatasi `^[A-Za-z0-9_-]+$` | `test_hardening.py` "charset aman" |
| T20 | Karakter kendali / null byte menembus parser atau basis data | P3 | `payload` dibatasi ASCII yang bisa dicetak di batas sistem | `test_hardening.py` "Karakter kendali" |
| T21 | Situs pihak ketiga memanggil API dari browser korban | P3 | CORS dibatasi daftar origin lewat env; tidak lagi `["*"]` | `test_hardening.py` "CORS tidak lagi terbuka" |
| T22 | Tanggapan API di-embed / di-sniff tipe kontennya | P3 | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` | `test_hardening.py` "Header keamanan" |
| T23 | Nilai numerik ekstrem (`1e300`, NaN) merusak perhitungan | P3 | `lat`/`lng`/`accuracy_m` dibatasi rentang; NaN/inf ditolak lapisan JSON | `test_hardening.py` "accuracy_m punya batas atas" |
| T24 | Mode replay demo dipakai membobol invarian | P3 | `location_source` hanya melabeli, tidak mengubah penilaian; tidak bisa memaksa `verified` dari GPS buruk; default `live` | `test_hardening.py` empat pemeriksaan mode replay |

---

## 6. Risiko residual — yang belum ditahan

Bagian ini sengaja ditulis selengkap bagian mitigasi. Batasan yang
diketahui dan diakui jauh lebih tidak berbahaya daripada batasan yang
disembunyikan, dan `test_adversarial.py` menguji sistem agar tidak
diam-diam mengklaim bisa menahan hal-hal di bawah ini.

| # | Risiko residual | Kenapa belum ditahan | Rencana | Dampak nyata |
|---|---|---|---|---|
| R1 | **Mock location / GPS palsu** | Server tidak bisa memverifikasi koordinat. Klien WEB tidak bisa memeriksa integritas perangkat — browser sengaja tidak membocorkannya | **Slot protokolnya sudah ada**: `device_integrity` diisi klien native, dan PJP yang mengintegrasikan sudah punya aplikasi native | **Dipersempit jauh.** `mock_location: true` menolak putusan lokasi sama sekali; root & attestation gagal diberi skor; ketiadaan laporan diungkapkan (`not_provided`), tidak dianggap aman |
| R2 | **Replay QR dinamis** | Proteksi replay kriptografis menuntut nonce sekali pakai di sisi PJP | Tetap butuh PJP untuk penutupan penuh | **Dipersempit.** Pemakaian ulang artefak sekali pakai terdeteksi: sebaran >150 m (0,000% positif palsu) dan pemakaian >=4 kali (0,60%). Korban PERTAMA tetap tidak terlindungi — tidak ada riwayat |
| R3 | **Merchant berjarak <15 m** | Presisi GPS tidak cukup memisahkan | Ambient WiFi fingerprinting; tidak tersedia lewat browser | **Dipersempit.** Jangkar kini rata-rata berjalan, galatnya 6,3 m -> 1,0 m pada 47 pengamatan; ditambah `adjacent_merchant` |
| R17 | **Pedagang berjarak beberapa meter tidak terbedakan sinyal fisik apa pun** | Diukur dari korpus produksi: tiga merchant berjarak 0,6–2,8 m. Radius jangkar sekecil 3 m pun tidak memisahkan mereka, dan akurasi GPS 14–16 m membuat radius sempit memecah SATU pedagang jadi beberapa jangkar. Sidik jari WiFi memberi irisan 0,66–0,80 — benar menyatakan "tempat sama", tidak bisa menyatakan "pedagang mana" | Aturan koeksistensi (R11) dan pendaftaran PJP (R4); bukan penyetelan radius | Batas FISIK yang diakui, bukan kekurangan penyetelan. Dicatat supaya tidak ada yang mencoba menutupnya dengan mengubah ANCHOR_RADIUS_M |
| R18 | **Penyerang cold start memakai kelonggaran tetangga** | Tenant yang tertinggal beberapa jam dari tetangganya kini lolos sampai `warn` lewat `adjacent_merchant_unproven`. Penyerang yang sempat mengumpulkan MIN_OBSERVERS pengamat SEBELUM korbannya mapan bisa memakai jalur yang sama | Pendaftaran PJP (R4); di jangkar yang SUDAH mapan jalur ini tidak terjangkau — diukur: 12 korban, semua `cooling_off`, penyerang nol pengamat | Disengaja dan diukur. Alternatifnya dua hari menuduh tenant sah di ritel padat. Yang didapat penyerang bukan lampu hijau: `warn` dengan nama korban dan nama di QR-nya berdampingan |
| R19 | **Model kelangkaan buta terhadap penyerang yang meniru profil lazim** | Model menilai seberapa sering kombinasi ciri muncul, jadi penyerang yang menyalin nilai dominan — MCC 5812, kriteria UMI, panjang PAN 18 — terbaca sepenuhnya normal. Diukur terhadap korpus 122 merchant sungguhan: penyerang yang meniru nilai dominan LOLOS, begitu pula yang hanya menyimpang di dua ciri | Bukan lapisan ini. QR yang dibangkitkan ulang ditangkap `issuer_dialect` lewat cara penyusunan payload, dan penempatannya ditangkap ikatan geospasial | Diakui dan disengaja. Lapisan kelangkaan hanya bertugas menangkap kombinasi yang tidak pernah terjadi; positif palsunya 4,1% pada merchant sah di korpus lapangan (`evaluate_rarity.py`), dan bobotnya dikunci 25 — sama dengan ambang `proceed`, sehingga sinyal ini tidak pernah bisa sendirian mencabut status VERIFIED merchant sah (Keputusan 78) |
| R20 | **Stiker yang sudah ditukar sebelum difoto tidak bisa ditangkap dari sisi pembayar** | Q-Shield memverifikasi PENEMPATAN, dan foto tidak membawa tempat. Kalau yang memotret tertipu di warung, ia memfoto stiker penipu — payload-nya sah, terbitan acquirer sungguhan — lalu pembayar membayar penipu. Informasinya sudah hilang sejak jepretan | Bukan di sisi pembayar. Perlindungannya harus terjadi saat MEMOTRET: pemindaian Q-Shield di tempat, atau tiket verifikasi (TTL 90 detik) untuk integrasi PJP-ke-PJP | Batas DEFINISIONAL, bukan penyetelan. Yang bisa diberikan lewat `from_image`: pemeriksaan bentuk payload penuh dan atribusi Merchant ID, disertai pernyataan terbuka bahwa penempatan tidak diverifikasi. Sinyal "belum pernah diamati" baru kuat seiring cakupan korpus — dengan 122 merchant, warung sah yang belum terlihat juga muncul tidak dikenal |
| R21 | **Stiker yang disebar dalam SATU kota, jarang dipindai, tidak terpisahkan dari pedagang keliling** | Pemisahnya fisika — satu pedagang cuma bisa di satu tempat pada satu waktu — dan buktinya menuntut dua pengamatan lintas-area yang berdekatan waktu. Dengan pengamatan yang jarang, bukti itu jarang muncul: terukur hanya **3,8%** sebaran meninggalkannya pada ambang 80 km/jam. Rentang juga tidak menolong di dalam satu metropolitan: penyebar sekota berentang sama dengan gerobak sungguhan | Kerapatan pengamatan. Makin banyak pengguna, makin besar peluang dua stiker tertangkap hidup bersamaan — bukti ini tumbuh sendiri seiring adopsi, tanpa penyetelan | Diakui dan DIPILIH. Alternatifnya menuduh setiap pedagang keliling yang sah, dan itu ongkos yang jauh lebih besar. Serangan yang sebenarnya kita lawan — stiker yang MENUTUPI merchant mapan — tidak tersentuh sama sekali: ia ditangkap `nmid_changed_at_anchor` di `cooling_off` skor 100, dan penyerangnya bahkan tidak pernah berhasil membangun jangkar (invarian §3) |
| R22 | **Konsensus bisa dikarang dengan identitas perangkat buatan** | `observer_count` tumbuh dari `device_anon_id`, dan field itu diisi KLIEN. Terukur: tiga string karangan direntang lebih dari `MIN_AGE_HOURS` membuat jangkar baru di titik kosong menjadi `verified`/`proceed`, dan korban pertama melihat lampu hijau. Ini melanggar prinsip sistem ini sendiri — nilai yang dikendalikan penyerang boleh mengetatkan, tidak pernah melonggarkan | Bukan dengan menaikkan `MIN_OBSERVERS`: menghitung angka yang bisa dikarang tetap menghitung angka yang bisa dikarang, dan menaikkannya hanya memperlambat penyerang sambil menghukum pedagang sungguhan. Penutupan sebenarnya lewat pendaftaran PJP (R4) atau pengamat yang dijamin penyelenggara | **Diungkapkan, belum ditutup.** Keputusan 81: tiap putusan kini membawa `evidence.vouched_observers` dan sinyal `consensus_unvouched` — reputasi yang seluruhnya anonim tidak lagi terbaca sama dengan yang dijamin PJP. Sistem berhenti mengklaim lebih dari yang didukung buktinya; PJP memutuskan kebijakannya di atas angka itu |
| R23 | **Ambang waktu tidak membebani penyerang yang tidak perlu hadir** | Rencana mengganti `MIN_AGE_HOURS` dengan "N hari berbeda" diperiksa lalu DIBATALKAN. Koordinat dikirim klien dan tidak bisa diverifikasi (R1), jadi penyerang tidak perlu berada di lokasi: "tiga hari berbeda" baginya berarti tiga permintaan HTTP dari laptop, dijeda tiga hari | Bukan ambang waktu. Yang mengubah ongkos hanya pengamat yang dijamin penyelenggara atau pendaftaran PJP | Dicatat sebagai keputusan yang TIDAK diambil, beserta alasannya, supaya tidak diulang. Ongkos serangan naik dari 25 jam jadi 3 hari — penundaan, bukan pertahanan — sementara harganya menjatuhkan seluruh data demo (Keputusan 82) |
| R4 | ~~Cold start~~ **DITUTUP untuk merchant terdaftar** | — | PJP mendaftarkan ikatan merchant-lokasi | Merchant terdaftar `verified` seketika tanpa menunggu konsensus. **Koreksi:** klaim lama "sisanya tetap `unknown` yang jujur" TIDAK benar — yang tidak terdaftar menjadi `verified` begitu konsensusnya terpenuhi, dan konsensus itu bisa dikarang. Lihat R22 |
| R5 | ~~Merchant sah pindah lokasi~~ **DITUTUP** | — | PJP mendaftarkan ulang di lokasi baru; jangkar lama otomatis berhenti resmi | Tidak lagi memicu alarm |
| R6 | **Merchant keliling** — dipersempit, tidak ditutup | Klaim "DITUTUP" sebelumnya hanya benar untuk yang TERDAFTAR PJP; `is_mobile` cuma bisa diisi penyelenggara. Untuk kopi keliling, kaki lima, dan food truck yang belum terdaftar di mana pun — yaitu hampir semuanya — jangkarnya menyebar dan dulu divonis `anomaly` dengan alasan "pola khas stiker yang disebar". Terukur: 6 titik mangkal, 46 pengamat, hasilnya anomaly/step_up | Keputusan 80 mencabut tuduhannya: sebaran kini menuntut bukti kehadiran serentak (kecepatan mustahil) atau rentang di luar jangkauan satu pedagang. Hijau penuh tetap lewat pendaftaran PJP | **Dipersempit.** Yang terdaftar lolos seketika. Yang tidak terdaftar berhenti dituduh, tapi juga tidak pernah hijau — `unknown`, minimal `warn`, dengan alasan yang mengaku tidak tahu |
| R7 | **Sidik jari encoding tervalidasi sebagian** | Korpus lapangan kini ada — 122 merchant dari 10 penerbit — tapi baru 5 penerbit melewati `ISSUER_MIN_NMIDS`, dan semuanya terkumpul di satu wilayah | Perluas korpus lewat mode katalog; lima penerbit tipis butuh 4 merchant lagi masing-masing | **Dipersempit.** Dialek penerbit dipelajari per prefiks PAN dan dibandingkan per payload; profil hanya terbentuk untuk penerbit yang generatornya konsisten. Terukur: penerbit `93600914` konsisten pada keenam atribut untuk 51 dari 51 merchant |
| R8 | ~~Rate limit per-IP kasar di balik NAT~~ **DITUTUP** | — | Kuota kini dikunci ke `client_id` hasil autentikasi, bukan alamat | Klien di balik NAT tidak lagi saling menghabiskan kuota |
| R14 | **Konfigurasi yang bocor kini bisa memalsukan tiket** | Kunci tiket diturunkan dari hash kunci API yang tersimpan, supaya tidak ada kunci baru yang perlu didistribusikan. Harganya: bocornya `QSHIELD_API_KEYS` tidak lagi sekadar membocorkan verifier — ia memberi kemampuan menandatangani tiket atas nama PJP itu | Tanda tangan asimetris (kunci privat terpisah, tidak pernah ada di konfigurasi) saat `cryptography` sudah layak ditarik sebagai dependensi | **Sedang** — melemahkan properti yang diklaim README, tapi penyerang yang memegang kunci API sudah bisa memanggil `/verify` atas nama PJP itu |
| R15 | **Tiket tidak bisa MEMAKSA siapa pun** | Yang mengeksekusi pembayaran adalah PJP; Q-Shield tidak ada di jalur itu. PJP yang mengabaikan `cooling_off` akan mengabaikan tiketnya juga | Penegakan sungguhan menuntut switch/acquirer menolak menyelesaikan transaksi tanpa tiket sah — tingkat infrastruktur, bukan tingkat pustaka | **Diakui.** Tiket MENGIKAT, tidak memaksa; klaim sebaliknya tidak pernah dibuat di dokumen mana pun |
| R16 | **Tiket bisa di-replay dalam masa berlakunya** | Stateless dan tidak disimpan, jadi QR yang sama bisa dieksekusi dua kali dalam 90 detik | Idempotensi transaksi milik PJP; sejalan dengan R2 yang memang di luar jangkauan | Rendah — diuji dan didokumentasikan (`test_ticket.py` "Yang TIDAK diklaim") |
| R10 | **Penyerang yang menang balapan cold start** | **Dimitigasi sebagian.** `ADJACENT_MIN_RATIO` = 0,10 menuntut basis pengamat sebanding sebelum pengecualian koeksistensi berlaku; serangan modal minimum (3 device) tidak lagi lolos. Penyerang yang mengeluarkan >5 device masih lolos, TAPI hanya dengan nama merchant yang BERBEDA dari korban — nama korban kini ditahan `anchor_name_impersonation` | Penutupan penuh lewat R1; R9 sudah ditutup dan mempersempit populasi penyerang jadi PJP terdaftar | Sedang — biaya penyerang naik, celah belum tertutup |
| R11 | ~~Pedagang bersebelahan yang sah dituduh menukar stiker~~ **DITUTUP** | — | Pengecualian koeksistensi kini juga bisa diperoleh lewat bukti kehadiran fisik: `ADJACENT_MIN_DEVICES` = 8 perangkat berbeda, rentang 24 jam, DAN merchant lama harus tetap terpindai setelah penantang muncul | Kebuntuan hilang: lapak sah pulih dalam 3–5 hari. Penukaran sungguhan tetap ditahan — QR yang tertutup membuat merchant lama diam, dan itu tidak bisa dipalsukan tanpa membatalkan serangannya |
| R12 | ~~Pedagang yang pindah lokasi dituduh menyebar stiker~~ **DITUTUP** | — | `nmid_scatter` kini bisa diganti `nmid_relocated` bila terbukti: 8 perangkat berbeda di tempat baru, semua lokasi lama sudah diam, DAN periode aktif lokasi-lokasi lama tidak pernah beririsan | Sebelumnya permanen tanpa syarat — 500 pengamat di lokasi baru dan lokasi lama berumur 10 tahun pun tidak menyembuhkan, karena cabang ini tidak menyaring binding usang. Kini pulih dalam 3 hari. Penyebaran tetap ditahan: stiker yang dipasang bersamaan punya rentang yang tumpang tindih walau jarang dipindai |
| R13 | ~~Stiker tukar tak terlihat saat GPS tidak berguna~~ **DITUTUP** | — | Jalur akurasi rendah membaca sidik jari WiFi lewat `store.locate_by_ap()`; QR milik merchant lain di tempat yang dikenali naik ke `step_up` | Sebelumnya semua pemindaian akurasi rendah `warn` datar — asli dan tukar identik. Batasan disengaja: WiFi tidak pernah memberi `proceed`, karena kasus beda-tempat-berdekatan belum terukur |
| R9 | ~~Belum ada autentikasi klien~~ **DITUTUP** | — | Kunci API per PJP, disimpan sebagai hash, gagal tertutup. mTLS menyusul menuju produksi | Endpoint verifikasi hanya melayani PJP terdaftar |

### Proposal untuk R10 — belum diterapkan, butuh keputusan tim

**Jalur eksploitasinya.** Penyerang menempel stiker di merchant **baru**
yang jangkarnya belum terbentuk, lalu memupuknya dengan 3 device selama
24 jam — semuanya sah menurut aturan, karena belum ada konflik. Begitu
merchant sungguhan ikut mapan, keduanya dianggap koeksistensi dan
**stiker palsu jadi `verified` secara permanen.**

Yang sudah aman: jangkar yang korbannya **sudah** mapan tidak bisa
dibajak lewat API sama sekali. Diuji — 10 pemindaian dari 10 device
menghasilkan nol binding, karena anomali tidak pernah dicatat
(Keputusan 7). Jendela serangannya khusus periode cold start (R4).

**Kenapa tidak langsung ditambal.** Perbaikan yang jelas — menuntut
jarak minimum antar-jangkar sebelum sesuatu disebut "bersebelahan" —
menyentuh invarian §7, dan invarian tidak diubah tanpa persetujuan tim.
Lebih dari itu, perbaikan naif justru berbahaya: galat GPS membuat dua
lapak yang benar-benar bersebelahan kadang tercatat berjarak <5 m, jadi
ambang jarak yang terlalu ketat akan menandai ruko dan food court sah
sebagai serangan — merusak aset A4, persis yang dicegah Keputusan 5.

**Tiga opsi, sudah dikalibrasi** (`scripts/calibrate_adjacency.py`):

**Opsi A — koeksistensi menghasilkan `unknown`, bukan `verified`.**
Terukur sebagai yang **paling mahal**, dan ini membatalkan dugaan awal
kami. Karena `ANCHOR_RADIUS_M` = 50 m, apa pun yang berada dalam radius
itu memicu `adjacent_merchant` — bukan cuma lapak yang benar-benar
berdempetan:

| Tata letak | Jarak | Pemindaian sah yang turun ke `warn` |
|---|---|---|
| warung soliter | — | 0,0% |
| ruko 4 pintu | 8 m | 100,0% |
| pertokoan jalan | 20 m | 100,0% |
| pujasera kecil | 4 m | 100,0% |
| food court mall | 3 m | 100,0% |
| pasar tradisional | 2,5 m | 100,0% |

Artinya **setiap** pemindaian di area komersial mana pun berakhir
`warn`. Itu menghancurkan aset A4: peringatan yang selalu muncul adalah
peringatan yang diabaikan. **Opsi A ditolak.**

**Opsi B — jarak minimum antar-jangkar.** Gugur secara empiris. Koordinat
jangkar ditetapkan dari pengamatan pertama, jadi galat GPS satu pembacaan
(sigma ~8 m) melekat permanen padanya. Sebaran jarak jangkar untuk swap
di titik yang sama dan untuk merchant yang benar-benar bersebelahan
tumpang tindih hampir sempurna justru di jarak yang paling penting:

| Jarak nyata | Jangkar merchant sah (p10-p90) | Jangkar swap | Tumpang tindih |
|---|---|---|---|
| 2,5 m | 3,2-18,1 m | 2,8-17,6 m | 79,1% |
| 4 m | 3,5-18,6 m | 2,8-17,6 m | 78,0% |
| 8 m | 5,0-21,4 m | 2,8-17,6 m | 71,9% |
| 15 m | 8,7-26,6 m | 2,8-17,6 m | 48,7% |
| 25 m | 16,7-36,5 m | 2,8-17,6 m | 11,8% |

Ini batasan R3 yang muncul lagi, bukan parameter yang bisa disetel.
**Opsi B ditolak.**

**Opsi C — pengecualian koeksistensi menuntut basis pengamat yang
sebanding.** Merchant yang benar-benar bersebelahan menghisap lalu lintas
kaki yang sama, jadi jumlah pengamatnya sepadan. Penyerang yang memupuk 3
device di sebelah merchant 47 pengamat tidak. Aturannya perbandingan,
bukan jarak — sehingga tata letak padat tidak tersentuh sama sekali:

| Rasio | Pasangan merchant sah tertolak | Device yang harus dikeluarkan penyerang |
|---|---|---|
| 0,00 (sekarang) | 0,0% | 3 |
| 0,05 | 0,8% | 3 |
| **0,10** | **3,5%** | **5** |
| 0,15 | 7,3% | 8 |
| 0,25 | 13,6% | 12 |
| 0,40 | 23,9% | 19 |

**Diterapkan: opsi C dengan rasio 0,10** (`binding.ADJACENT_MIN_RATIO`),
disetujui tim 10 September 2026. Biaya 3,5% pada pasangan
merchant sah — dan itu pun hanya berlaku pada pasangan yang sama-sama
sudah mapan, bukan pada seluruh pemindaian seperti opsi A.

**Kejujuran yang harus disampaikan bersama angka ini:** opsi C
**menaikkan biaya** penyerang, tidak menutup celahnya. Penyerang yang mau
mengeluarkan lebih banyak device tetap lolos. Yang berubah adalah
serangan 3-device yang murah jadi tidak lagi cukup. Penutupan sungguhan
menuntut R1 (integritas perangkat). R9 sudah ditutup, dan itu sudah
mempersempit populasi penyerang jadi pihak yang memegang kunci PJP —
tapi tidak menghapus ancaman dari perangkat yang koordinatnya dipalsukan
di balik PJP yang sah.

**R9 dan R8 sudah ditutup** sejak autentikasi klien diterapkan. Yang
tersisa sebagai risiko terbuka terbesar adalah **R1 (mock location)**,
karena itulah yang juga menyisakan R10: penyerang bermodal besar masih
bisa memupuk binding dari perangkat yang koordinatnya dipalsukan.
Penutupannya menuntut deteksi integritas perangkat, yang memerlukan SDK
native — di luar jangkauan PoC berbasis web.

Catatan yang tetap berlaku: autentikasi klien memperkecil
populasi penyerang menjadi PJP terdaftar, tapi tidak menghapus ancaman
dari perangkat yang koordinatnya dipalsukan di balik PJP yang sah.

---

## 7. Analisis privasi

Sistem yang mengumpulkan lokasi saat orang bertransaksi bisa dengan mudah
menjadi alat pelacakan berkedok anti-fraud. Tidak ada PJP yang berani
memakainya, dan tidak seharusnya ada.

Tiga properti yang membuat Q-Shield tidak bisa dipakai begitu, dan
semuanya bersifat **struktural** — bukan kebijakan yang bisa dicabut
diam-diam:

1. **Tidak ada `user_id` di skema mana pun.** Bukan "tidak dipakai",
   melainkan tidak ada kolomnya.
2. **`observations` tidak menyimpan koordinat, DAN barisnya tidak bisa
   dirangkai.** Yang kedua penting: tanpa koordinat pun, menyimpan
   pengenal perangkat apa adanya membuat satu JOIN ke `bindings` cukup
   untuk memulihkan jejak perjalanan lengkap. Karena itu yang disimpan
   adalah `device_ref = sha256(garam || binding_id || device_anon_id)`,
   **dilingkupi per-binding** — perangkat yang sama menghasilkan nilai
   berbeda di tiap lokasi, sehingga dedup tetap bekerja tapi perangkaian
   tidak mungkin. Koordinat hanya ada pada `bindings`, yaitu properti
   lokasi **merchant**.
3. **Agregat Layer 2 menempel pada binding, bukan device.** Konsekuensi
   yang diterima sadar: Q-Shield tidak bisa mendeteksi perjalanan
   mustahil per perangkat — mitigasi terkuat yang tersedia untuk R1.
   Pertukaran itu diambil dengan mata terbuka.

**Sisa risiko yang disebut terus terang.** Pihak yang sudah mengetahui
sebuah `device_anon_id` masih bisa menghitung rujukannya di tiap binding
dan menguji keberadaannya. Pihak itu adalah PJP yang menerbitkan
pengenal tersebut, dan PJP sudah mengetahui transaksi penggunanya
sendiri — jadi tidak ada paparan baru. Yang hilang adalah kemampuan
siapa pun yang memegang basis data Q-Shield untuk memakainya sebagai
alat pelacak.

Kalimat yang meringkas seluruhnya: **yang disimpan adalah ikatan, bukan
kunjungan.**

Konsekuensi regulasi. Karena tidak ada data pribadi yang tersimpan,
berbagi data binding antar-PJP tidak menyentuh kerahasiaan bank maupun
UU PDP — dan justru berbagi itulah yang membuat lapisan ini bekerja,
karena stiker penipu tidak berhenti di batas satu penyelenggara.

**Cara membuktikannya, bukan mengklaimnya.** `test_invariants.py` #8
tidak berhenti di membaca nama kolom — versi yang berhenti di situ
pernah meloloskan kebocoran nyata, dan pemeriksaan yang memberi rasa
aman palsu lebih berbahaya daripada tidak ada pemeriksaan. Sekarang ia
menjalankan serangannya: JOIN memakai pengenal mentah, perangkaian baris
antar-lokasi lewat `device_ref`, dan penghitungan rujukan dari pengenal
yang sudah diketahui penyerang. Ketiganya harus gagal, dan dedup harus
tetap utuh. `test_hardening.py` melakukan hal setara untuk log.
Pertanyaan "bagaimana kalian membuktikan tidak menyimpan identitas
pengguna" dijawab dengan menjalankan dua berkas itu.

---

## 8. Yang harus dikerjakan sebelum produksi

Diurutkan berdasarkan risiko, bukan usaha.

1. **Deteksi integritas perangkat** (R1) — kini jalur pencemaran terkuat yang tersisa, dan yang menyisakan R10
2. **Migrasi ke Postgres** — SQLite tidak menangani tulis serentak dari banyak proses
3. **Jalur konfirmasi merchant** (R5, R6) — dibutuhkan sebelum merchant sah kena imbas
4. **Kalibrasi lapangan seluruh parameter** — nilai sekarang titik awal demo, bukan hasil data nyata
5. **Rotasi dan retensi log** — jejak audit tumbuh tanpa batas
6. **Korpus payload QRIS asli** (R7) — memvalidasi sinyal sidik jari encoding
7. **Verifikasi spec untuk tag 55-57 dan tag 58** — keduanya kini diparse
   dan diungkapkan tapi sengaja TIDAK diskor, karena belum terverifikasi
   apakah biaya layanan pada QR statis dan kode negara non-`ID` itu
   menyalahi spec QRIS atau justru sah (Keputusan 35, 41)
8. **Nilai forensik jejak audit** — payload mentah sengaja tidak dicatat
   (PAN merchant ada di dalamnya), sehingga penyidik tidak bisa memeriksa
   ulang byte QR setelah kejadian. Bentuk yang bertahan terhadap
   keberatan itu adalah mencatat **hash** payload, bukan payloadnya
9. **CI** — tidak ada `.github/`; `preflight.py` satu-satunya yang pernah
   menjalankan suite secara otomatis (Keputusan 37)

---

## 9. Catatan untuk review

Filbert — tiga hal yang paling perlu pandangan kedua:

1. **§5.5 T25-T27 (autentikasi klien).** Kunci API per PJP sudah
   diterapkan. Apakah itu cukup untuk pitch, atau mTLS perlu disebut
   sebagai rencana eksplisit di depan Kaspersky?
2. **§6 R10.** Pertanyaan ini sudah diuji dan jawabannya: jangkar yang
   korbannya sudah mapan **tidak** bisa dibajak lewat API, tapi penyerang
   yang menang balapan cold start lolos sebagai "merchant bersebelahan".
   Yang perlu pandangan kedua adalah pilihan A vs B dan biaya opsi A.
3. **§6 R10.** Opsi C rasio 0,10 sudah diterapkan dan diuji. Yang tersisa:
   apakah biaya penyerang ">5 device" cukup untuk demo, atau perlu
   dinaikkan ke 0,15 (7,3% positif palsu / 8 device) sebelum onsite?

4. **§7.** Argumen privasi ini yang akan dipakai menjawab pertanyaan
   Kaspersky. Apakah ada celah yang bisa dibantah?
