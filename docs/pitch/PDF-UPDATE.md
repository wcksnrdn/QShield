# Teks pengganti untuk Q-Shield-Overview.pdf

Berkas sumber PDF tidak ada di repo, jadi ini bukan tambalan otomatis —
ini **teks siap tempel**. Cari kalimat lamanya di dokumen sumber kalian
(Canva/Figma/Docs), ganti dengan yang baru.

Seluruh angka di sini **diukur ulang hari ini** dari kode yang berjalan,
bukan dari ingatan. Kalau kalian mengubah sesuatu setelah ini, ukur
ulang sebelum menyalin — perintahnya disertakan di tiap bagian.

> **Urutan pengerjaan yang disarankan.** Bagian 10 lebih dulu: itu
> pembeda utama kalian dan satu-satunya yang mengubah cara juri membaca
> seluruh sisanya. Sisanya koreksi angka.

---

## 1. Halaman 4 — berkas pengujian

**Lama:**

> Empat berkas pengujian (`test_emvco.py`, `test_geo.py`,
> `test_binding.py`, `test_api.py`) mencakup parser payload, geohash &
> jarak, 13 skenario konsensus (termasuk kasus ruko dan relokasi
> merchant), serta alur end-to-end lewat API sungguhan.

**Baru:**

> **Tujuh belas berkas pengujian**, mencakup parser payload, geohash &
> jarak, **21 skenario konsensus** (ruko, relokasi, pedagang
> bersebelahan, pedagang keliling), **44 skenario adversarial** — enam
> di antaranya batasan yang diakui belum ditahan, diuji justru agar
> sistem tetap jujur — **9 invarian** yang dikunci regression test,
> **11 bagian kontrak API** yang dikunci, seam SDK, pembayaran jarak
> jauh, asal-usul konsensus, serta pengerasan (validasi masukan,
> autentikasi klien, pembatasan laju, audit tanpa PII, dan konkurensi).

> ⚠️ **Jangan menjumlahkan jadi satu angka total.** Empat berkas tidak
> menomori pemeriksaannya sendiri, jadi total apa pun yang kalian tulis
> akan meleset — dan angka yang tidak bisa kalian pertanggungjawabkan
> asalnya adalah hal pertama yang runtuh saat ditanya. Sebut angka
> per-kategori di atas; semuanya bisa ditunjukkan langsung.

*Ukur ulang:* `ls tests/test_*.py | wc -l`, lalu jalankan
`tests/test_adversarial.py` dan `tests/test_invariants.py` — keduanya
mencetak jumlahnya sendiri di baris terakhir.

---

## 2. Halaman 4 — angka besar "13 SKENARIO BINDING DIUJI"

**Lama:** `13` / SKENARIO BINDING DIUJI

**Baru:** `44` / SKENARIO ADVERSARIAL DIUJI

Enam di antaranya adalah batasan yang **diakui belum ditahan**, diuji
justru agar tidak diam-diam berubah jadi klaim aman. Sebutkan itu —
juri keamanan mempercayai angka yang datang bersama batasannya.

**Angka besar kedua yang layak dipertimbangkan:** `24` / RISIKO
RESIDUAL TERDOKUMENTASI. Hampir tidak ada tim yang berani memasang
angka ini di slide. Itu justru kekuatannya.

---

## 3. Halaman 4 — latensi

**Lama:**

> 200 permintaan berturut-turut lewat SQLite lokal: p50 2,8 ms, p95
> 3,5 ms, maks 22,4 ms — jauh di bawah anggaran 200 ms.

**Baru:**

> 200 permintaan berturut-turut lewat SQLite lokal: **p50 0,7 ms, p95
> 0,9 ms, maks 3,4 ms** — dua ratus kali lebih cepat dari anggaran
> 200 ms. Angka ini belum diuji pada volume produksi.

Turunnya bukan kebetulan: penguncian basis data diperbaiki (dua bug
konkurensi yang membuat 1 dari 200 pengamatan hilang), dan perhitungan
jejak kehadiran diubah dari O(n²) jadi O(k²+n log n) — 481 ms menjadi
2,6 ms pada 1.000 pengamatan.

---

## 4. Halaman 4–5 — Layer 2

**Baru (kalau Layer 2 belum disebut sama sekali, tambahkan):**

> **Layer 2 — perilaku artefak.** Tiga model tanpa label berjalan di
> atas korpus yang dikumpulkan sendiri: dialek penerbit (cara tiap
> penyelenggara menyusun payload), kelangkaan profil merchant, dan
> jejak QR dinamis. Layer 2 **tidak pernah bisa menaikkan** status ke
> arah terverifikasi — ia hanya menurunkan. Ketiadaan sinyal bukan
> bukti keabsahan.

---

## 5. Halaman 5 — merchant berpindah

**Lama:**

> ...serta menangani relokasi merchant yang sah (saat ini memicu satu
> kali peringatan)...

**Baru:**

> Relokasi merchant yang sah pulih sendiri dalam tiga hari, tanpa
> menunggu tindakan siapa pun. Pembedanya fisik: seorang pedagang hanya
> bisa berada di satu tempat pada satu waktu, sehingga periode aktif
> lokasi-lokasinya tidak pernah beririsan — sementara penyebar stiker
> memasang QR-nya sekaligus.

---

## 6. Halaman 5 — merchant keliling ⚠️ **GANTI TOTAL**

**Lama:**

> ...dan merchant keliling (belum ditangani sama sekali, perlu
> penandaan khusus saat pendaftaran).

**Versi perantara yang PERNAH kami tulis dan sekarang SALAH:**

> ~~Merchant keliling ditandai saat pendaftaran; ikatan lokasi tidak
> diberlakukan untuknya.~~

Itu hanya benar untuk yang **terdaftar PJP**. Untuk kopi keliling dan
kaki lima yang belum terdaftar di mana pun — yaitu hampir semuanya —
dulu mereka divonis `anomaly`.

**Baru:**

> **Pedagang keliling tidak lagi dituduh menyebar stiker.** Keduanya
> menghasilkan gejala yang sama di basis data — satu Merchant ID di
> banyak tempat — jadi tuduhan sebaran kini menuntut **bukti fisik**:
> kecepatan yang mustahil ditempuh satu pedagang (>80 km/jam antar dua
> pengamatan), atau rentang di luar jangkauan satu pedagang (>80 km).
> Tanpa bukti itu, sistem menjawab apa adanya: *"bisa pedagang
> keliling, bisa juga stiker yang disebar; belum ada bukti yang
> memisahkan keduanya."*
>
> Ambangnya dipilih demi keselamatan pedagang, bukan demi angka
> tangkapan: pada 20 km/jam, **89,5% kopi keliling bermotor akan
> tertuduh.** Pada 80 km/jam, nol.

**Yang layak diceritakan lisan** (ini cerita terbaik yang kalian
punya): aturan lama ternyata **tidak pernah bisa menangkap penyebar
sungguhan sama sekali.** Pemindaian penipu ditolak sebagai anomali, dan
invarian kami melarang pemindaian yang ditolak membangun reputasi —
jadi penipu tidak pernah berhasil mengumpulkan "banyak tempat". Aturan
itu praktis hanya menuduh pedagang jujur.

---

## 7. Halaman 5 — kalibrasi lapangan

**Lama:**

> ...perlu dikalibrasi ulang dari data lapangan sebelum produksi.

**Baru — ini sudah boleh diklaim:**

> Dikalibrasi dari korpus lapangan yang dikumpulkan tim sendiri:
> **124 merchant QRIS nyata dari 10 penyelenggara**, lima di antaranya
> sudah melewati ambang pembentukan profil dialek. Enam belas skrip
> kalibrasi menyertai repo; tiap konstanta punya sapuan di belakangnya.
>
> Korpus itu juga yang membongkar bug di model kami sendiri: fitur
> "kota" punya 79 nilai berbeda untuk 122 merchant sehingga kota
> terbanyak pun terbaca langka, memberi satu fitur langka gratis ke
> **setiap** merchant. Setelah diperbaiki, positif palsu turun
> **8,2% → 4,1%** tanpa kehilangan satu pun deteksi.

**Batas yang tetap harus disebut:** korpusnya dari satu wilayah, dan
angka latensi belum diuji pada volume produksi.

---

## 8. Halaman 5 — di dalam ruangan

**Baru:**

> Di dalam ruangan, ketika GPS melaporkan akurasi ratusan meter, sistem
> **menolak memberi putusan lokasi** dan beralih ke sidik jari WiFi
> sekitar untuk mengenali tempat. Sidik jari itu tidak pernah
> menerbitkan kepercayaan — ia hanya menaikkan kecurigaan dan memberi
> konteks.

---

## 9. BUTIR BARU — pembayaran jarak jauh

Belum ada di PDF sama sekali, dan ini kasus sehari-hari yang pasti
ditanyakan.

> **Foto QR yang dikirim lewat pesan.** Seseorang memfoto QRIS di
> warung, mengirimkannya, lalu orang lain membayar dari tempat berbeda.
> Q-Shield memverifikasi penempatan, jadi ia **mengaku tidak bisa**
> memverifikasinya dari sisi pembayar — bukan hijau, bukan tuduhan.
> Yang tetap diberikan: pemeriksaan bentuk payload secara penuh, plus
> atribusi Merchant ID — *"QR ini kami kenal sebagai WARUNG MADURA di
> Bandung, 47 pengamatan"* versus *"belum pernah kami amati di mana
> pun."* Nama di QR bisa diketik siapa saja saat mendaftar; riwayat
> pengamatan tidak bisa dikarang.
>
> Sama pentingnya, pemindaian semacam itu **tidak menanam jangkar palsu
> di lokasi pembayar.** Tanpa penjagaan ini, tiap pembayaran jarak jauh
> menambah hukuman permanen pada merchant yang sah — di skala
> penyelenggara, itu merusak korpus secara sistematis.

---

## 10. BUTIR BARU — **pembeda utama, kerjakan ini lebih dulu**

Kalau di PDF tertulis *"nol dari enam belas ciri berbeda"*, **ganti
dengan versi presisi di bawah.** Versi lama bisa dipatahkan juri dalam
satu pertanyaan: *"tapi kalian sendiri punya sinyal ketidakcocokan
kota — jadi payload memberi tahu sesuatu, dong?"*

> **Kenapa analisis payload tidak bisa menangkap penipuan ini.**
>
> Enam belas ciri payload kami ekstrak dan bandingkan antara stiker
> korban dan stiker penipu. Dua belas di antaranya **ciri struktural** —
> urutan field, gaya checksum, panjang dan prefiks nomor akun, format
> Merchant ID — yang ditentukan generator penyelenggara.
>
> **Nol yang berbeda.** Terhadap penipu yang mencocokkan isian
> pendaftarannya: **nol dari enam belas, seluruhnya.**
>
> Sebabnya mendasar: pelaku tidak memalsukan QR. Ia mendaftarkan akun
> merchant sungguhan pada penyelenggara sungguhan, menerima stiker
> terbitan resmi, lalu menempelkannya menutupi stiker merchant lain.
> Classifier yang dilatih mengenali "pola QRIS asli" akan
> mengklasifikasikannya **asli** — karena memang asli.
>
> Terukur ulang di korpus lapangan: 52 merchant nyata dari satu
> penyelenggara, lima dari enam ciri struktural identik pada
> seluruhnya.
>
> Penipuannya tidak ada di dalam kodenya. **Penipuannya ada di
> penempatannya** — dan penempatan tidak terekam di payload.

**Yang WAJIB ikut disebut, jangan sampai kelihatan disembunyikan:**

> Empat ciri sisanya deskriptif — kategori usaha, kriteria, tipe kode,
> panjang nama — diisi merchant saat mendaftar. Nama dan kota sengaja
> **di luar** enam belas karena keduanya teks bebas, bukan ciri
> struktural. Keduanya justru kami pakai: stiker bertuliskan Jakarta
> yang menempel di warung Bandung tertangkap pada pemindaian pertama.
> Tapi itu **kesalahan penipu, bukan deteksi struktural** — ia
> mengendalikan kolom itu, dan yang teliti tinggal mencocokkannya.

**Bisa diperagakan hidup di panggung** — ini tiga puluh detik paling
persuasif yang kalian punya:

```
python scripts/enam_belas_ciri.py "PAYLOAD_A" "PAYLOAD_B"
```

Dua QRIS asli masuk, keluar tabel berdampingan, dan kesimpulannya
dicetak sendiri oleh programnya. Dikunci di `tests/test_enam_belas.py`
supaya klaim ini tidak bisa lapuk diam-diam.

---

## 11. Slide yang layak ditambahkan — "apa yang membedakan kami"

Kalau ada ruang untuk satu slide baru, ini yang paling menaikkan nilai
keunikan:

> **Empat hal yang jarang dibawa tim lain**
>
> **1. Kami membalik pertanyaannya.** Semua orang mendeteksi "QR
> palsu". Kami membuktikan QR-nya tidak palsu — dan itu memindahkan
> seluruh masalah ke penempatan.
>
> **2. Bukti fisik, bukan skor kemiripan.** Tiap mekanisme bersandar
> pada hal yang tidak bisa dipalsukan penyerang tanpa membatalkan
> serangannya sendiri: stiker yang menutupi membuat merchant lama
> berhenti terpindai; satu pedagang tidak bisa ada di dua tempat
> sekaligus; nilai yang dikendalikan penyerang boleh mengetatkan,
> tidak pernah melonggarkan.
>
> **3. Kami menerbitkan batas kami sendiri, lengkap dengan harganya.**
> 24 risiko residual terdokumentasi — termasuk serangan terukur
> terhadap klaim inti kami sendiri: konsensus pengamat bisa dipalsukan
> dengan tiga identitas karangan dan kesabaran 24 jam. Karena itu tiap
> putusan kini membawa jumlah pengamat yang **dijamin penyelenggara**,
> terpisah dari yang sekadar dihitung.
>
> **4. Setiap konstanta punya sapuan kalibrasi.** Tebakan pertama kami
> untuk ambang kecepatan pedagang keliling adalah 20 km/jam — dan
> pengukuran menunjukkan itu akan menuduh 89,5% pedagang bermotor yang
> sah. Angka yang tidak diukur adalah angka yang belum diketahui.

---

## Yang TIDAK perlu diubah

Masih akurat apa adanya:

- seluruh Bagian 1–3 (celah yang ditangani, arsitektur, empat tier)
- ambang presisi geohash 7 dan angka 81,9%
- argumen privasi (tanpa `user_id`, tanpa koordinat kunjungan)
- keterangan bahwa angka latensi belum diuji pada volume produksi

## Yang HARUS dihapus kalau masih ada

- angka latensi lama (**p50 2,8 ms** — sekarang 0,7 ms)
- **"13 skenario"** di mana pun ia muncul
- **"empat berkas pengujian"**
- klaim bahwa merchant keliling **sudah ditangani** lewat pendaftaran
- *"nol dari enam belas"* tanpa penjelasan struktural vs deskriptif
- istilah **"machine learning"** tanpa kata "tak terawasi" di dekatnya
  (lihat `MODEL-ML.md` — klaimnya benar, penyebutannya yang harus tepat)

---

## Sebelum mengirim

- [ ] Bagian 10 dikerjakan lebih dulu, dan kalimat "di luar enam belas"
      ikut ditempel — bukan cuma bagian yang enak didengar
- [ ] Jalankan `python scripts/enam_belas_ciri.py` sekali, pastikan
      keluarannya sesuai yang kalian tulis di slide
- [ ] Sepakati satu istilah bertiga untuk bagian ML (`MODEL-ML.md`)
- [ ] Baca sekali lagi dengan lantang — kalau ada angka yang kalian
      sendiri tidak tahu asalnya, cari perintah ukurnya di dokumen ini
