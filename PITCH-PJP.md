# Q-Shield untuk penyelenggara pembayaran

Dokumen ini untuk kepala produk, risk, atau compliance di PJP — bukan
untuk tim engineering. Panduan teknisnya terpisah di `INTEGRATION.md`.

---

## Siapa kami, apa adanya

Tim mahasiswa Telkom University. Q-Shield adalah proof of concept yang
dibangun untuk kompetisi Telkom University × Kaspersky, track Secure
Digital Payments & Fintech.

**Kami bukan vendor, dan belum punya satu pun pelanggan.** Kami
menyebutkannya di awal supaya tidak ada yang keliru menilai kematangan
kodenya. Yang kami punya: sistem yang berjalan, pengujian yang bisa
dijalankan sendiri, dan dokumen ancaman yang menyebut batasannya dengan
terus terang.

Yang kami minta di percakapan pertama bukan kontrak. Hanya penilaian
kalian apakah masalah yang kami tangani memang masalah kalian.

---

## Masalahnya

QRIS memverifikasi rekening merchant yang tertanam di dalam kode. Tidak
ada lapisan mana pun dalam stack yang memverifikasi ikatan antara
rekening itu, **artefak fisik yang menampilkannya**, dan **lokasi tempat
artefak itu dipasang**.

Konsekuensinya konkret: stiker QRIS yang ditempel menutupi stiker
merchant lain adalah payload yang **sah secara sintaksis**. CRC-nya
valid. Formatnya benar. Nama merchant bisa ditiru persis.

Kami menguji ini: enam belas ciri yang bisa diekstrak dari payload —
panjang, urutan field, checksum, format Merchant ID, kode kategori —
dibandingkan antara stiker asli dan stiker pengganti.

> **Nol dari enam belas berbeda.**

Sebabnya bukan kelemahan pemeriksaan kami. Penipu tidak memalsukan QR.
Ia mendaftar akun merchant sungguhan ke penyelenggara sungguhan,
menerima stiker yang diterbitkan resmi, lalu menempelkannya di tempat
orang lain. Payload-nya memang asli.

**Penipuannya tidak ada di dalam kodenya. Penipuannya ada di
penempatannya** — dan penempatan tidak pernah diperiksa siapa pun.

---

## Kenapa ini sulit ditangani sendiri

Untuk mendeteksinya, seseorang harus tahu **merchant mana yang
seharusnya berada di lokasi itu**. Tidak ada satu pihak pun yang
memegang informasi tersebut hari ini.

Dan di sinilah letak persoalan yang sebenarnya: **stiker penipu tidak
berhenti di batas satu penyelenggara.** Satu stiker menargetkan siapa
pun yang lewat, apa pun aplikasi yang mereka pakai.

Kami menjalankan skenario yang sama di dua dunia. Warung yang sudah lama
berjualan; pelanggannya kebanyakan memakai satu aplikasi:

| | Tiap PJP menyimpan datanya sendiri | Satu lapisan dipakai bersama |
|---|---|---|
| Pengguna PJP besar | **dihentikan** | **dihentikan** |
| Pengguna PJP kecil | diteruskan ke layar PIN | **dihentikan** |

Pengguna PJP besar terlindungi di kedua dunia — datanya sendiri sudah
cukup. Yang menentukan adalah pengguna PJP yang lebih kecil: di dunia
pertama ia **tidak punya dasar apa pun** untuk menghentikannya, karena
warung itu tidak pernah terbentuk di basis datanya.

**Semakin kecil pangsa Anda, semakin besar keuntungan Anda dari lapisan
bersama.** Ini bukan retorika — itu konsekuensi matematis dari adopsi
yang tidak merata, dan bisa Anda jalankan sendiri:
`python scripts/demo_lintas_pjp.py`.

---

## Apa yang Q-Shield lakukan

Satu panggilan API setelah QR dipindai, **sebelum layar PIN muncul**.

```
kamera → payload QRIS → POST /api/v1/verify → layar PIN
```

Jawabannya salah satu dari empat tingkat friksi: lanjutkan, peringatkan,
minta verifikasi tambahan, atau tunda. Beserta kalimat yang bisa
ditampilkan langsung ke pengguna — bukan skor yang tidak bisa dijelaskan.

Yang **tidak** berubah di sisi Anda:

- standar QRIS tidak disentuh
- perangkat merchant tidak diubah
- dana tidak lewat sini sama sekali
- tidak ada perubahan pada alur settlement

Yang Anda tambahkan: satu panggilan HTTP dengan anggaran latensi 200 ms
(terukur p50 2,8 ms, p95 3,7 ms pada perangkat keras sederhana).

---

## Privasi — bagian yang menentukan apakah ini layak dipertimbangkan

Sistem yang mengumpulkan lokasi saat orang bertransaksi bisa dengan
mudah menjadi alat pelacakan berkedok anti-fraud. Kami tahu tidak ada
penyelenggara yang berani memakainya, jadi itu ditutup di tingkat skema,
bukan kebijakan:

- **Tidak ada kolom identitas pengguna di skema mana pun.** Bukan "tidak
  dipakai" — tidak ada kolomnya.
- Pengenal perangkat yang Anda kirim **tidak pernah disimpan apa
  adanya.** Yang masuk basis data adalah hash yang dilingkupi
  per-lokasi, sehingga baris pengamatan **tidak bisa dirangkai
  antar-lokasi** menjadi jejak perjalanan.
- Tabel pengamatan tidak menyimpan koordinat.
- Jejak audit mencatat putusan dan alasannya, bukan siapa yang memindai.

Ini bisa Anda **verifikasi sendiri, bukan percayai**. Pengujian kami
menjalankan tiga serangan perangkaian jejak terhadap basis datanya
sendiri, dan ketiganya harus gagal:

```
python tests/test_invariants.py
```

Konsekuensinya penting bagi Anda: karena tidak ada data pribadi yang
berpindah, berbagi data ikatan antar-penyelenggara tidak menyentuh
kerahasiaan bank maupun UU PDP. **Itu yang membuat penyelenggara yang
bersaing tetap bisa duduk di lapisan yang sama.**

---

## Cara memulai yang tidak menuntut kepercayaan pada kami

Keberatan yang wajar: mengapa Anda mau mengirim data pemindaian ke
server tim mahasiswa?

Jawabannya: **tidak perlu.** Q-Shield berjalan di infrastruktur Anda
sendiri — satu proses, satu basis data, tanpa ketergantungan eksternal.
Kode dan skema terbuka untuk diaudit sebelum Anda menjalankan apa pun.

Tahapannya:

1. **Jalankan sendiri, tertutup.** Anda mendapat deteksi sticker-swap
   dari data pengguna Anda sendiri. Tidak ada data yang keluar. Tidak
   ada hubungan dengan kami yang diperlukan.
2. **Daftarkan merchant Anda.** Anda sudah tahu Merchant ID mana milik
   siapa dari data onboarding. Memindahkan pengetahuan itu menutup
   masalah cold start seketika.
3. **Ikut lapisan bersama — kalau dan ketika Anda mau.** Di sinilah
   keuntungan lintas-penyelenggara muncul. Ini keputusan terpisah yang
   bisa diambil bertahun-tahun kemudian.

Tahap satu tidak menuntut kepercayaan apa pun pada kami. Silakan mulai
di situ.

---

## Yang belum bisa kami lakukan

Kami menyebutkan ini di depan karena Anda akan menemukannya sendiri,
dan lebih baik mendengarnya dari kami.

| Batasan | Keadaan |
|---|---|
| GPS yang dipalsukan | Server tidak bisa memverifikasi koordinat. Protokol kami sudah menyediakan slot untuk hasil Play Integrity / App Attest — **aplikasi native Anda** yang mengisinya |
| Replay kriptografis QR dinamis | Butuh nonce sekali pakai dari sisi Anda. Yang kami deteksi: pemakaian ulang dan perubahan nominal pada nomor tagihan yang sama |
| Merchant berjarak di bawah 15 meter | Batas presisi GPS. Dipersempit lewat penghalusan jangkar, tidak hilang |
| Parameter belum dikalibrasi lapangan | Nilai sekarang berasal dari simulasi dan pengujian terbatas, ditandai eksplisit di kode |

Dokumen ancaman lengkap beserta pengujiannya ada di `THREAT-MODEL.md`.
Setiap klaim keamanan di sana menunjuk ke pengujian yang bisa Anda
jalankan sendiri.

---

## Yang kami minta

Tiga puluh menit. Kami tunjukkan demonya, Anda katakan apakah masalah
ini memang masalah Anda, dan di mana asumsi kami keliru.

Kalau ternyata ini bukan prioritas Anda, itu jawaban yang berguna juga —
dan kami akan berterima kasih karena Anda menghemat waktu kami.

---

# Lampiran — memulai dari nol

Bagian ini catatan kerja tim, bukan bagian dokumen yang dikirim.

## Siapa yang lebih mudah diajak bicara

Bukan nama perusahaan, melainkan ciri. Verifikasi sendiri siapa yang
cocok — kami tidak punya pengetahuan orang dalam soal ini.

**Lebih mudah:**

- **Penyelenggara berskala menengah dan bank daerah.** Mereka
  menerbitkan QRIS tapi tidak punya tim riset fraud sendiri. Dan
  merekalah yang paling diuntungkan lapisan bersama — lihat tabel dua
  dunia di atas.
- **Agregator dan payment gateway.** Satu integrasi menyentuh banyak
  merchant sekaligus, jadi nilainya lebih besar untuk usaha yang sama.
- **Siapa pun yang sedang menjalankan program inovasi.** Mereka memang
  sedang mencari hal seperti ini, dan jalur masuknya terbuka.

**Lebih sulit untuk percakapan pertama:** penyelenggara terbesar. Bukan
karena mereka tidak peduli, tapi karena mereka punya tim internal, siklus
pengadaan panjang, dan ratusan pihak yang mengantre di depan kalian.

## Jalur masuk, urut dari yang paling dekat

1. **Kompetisinya sendiri.** Juri Telkom dan Kaspersky persis orang yang
   punya akses ke penyelenggara. Menang atau tidak, itu pintu terdekat
   yang kalian punya — dan sudah kalian buka.
2. **Kampus.** Telkom University punya hubungan industri. Tanya dosen
   pembimbing siapa yang bisa memperkenalkan.
3. **ASPI dan Bank Indonesia.** Mereka pemilik dan regulator standar
   QRIS. Celah di standarnya adalah urusan mereka, dan lapisan yang
   tidak menyimpan data pribadi adalah bahasa yang mereka mengerti.
4. **Langsung ke orangnya.** Cari kepala produk, risk, atau fraud di
   LinkedIn. Pesan pendek, bukan lampiran 20 halaman.

## Contoh pesan pertama

Pendek dengan sengaja. Permintaannya kecil, dan kejujuran soal siapa
kalian justru yang membuatnya dibaca.

> Selamat pagi Pak/Bu [nama],
>
> Saya [nama], mahasiswa Telkom University. Tim kami membangun lapisan
> verifikasi QRIS untuk kompetisi Telkom University × Kaspersky, dan
> kami ingin tahu apakah masalah yang kami tangani memang masalah nyata
> di [perusahaan].
>
> Singkatnya: stiker QRIS yang ditempel menutupi stiker merchant lain
> menghasilkan payload yang sah secara sintaksis. Kami mengukur enam
> belas ciri payload antara stiker asli dan stiker pengganti — nol yang
> berbeda. Penipuannya ada di penempatannya, bukan di kodenya, dan
> penempatan tidak pernah diperiksa siapa pun.
>
> Kami membuat lapisan yang memeriksa itu sebelum PIN dimasukkan. Tidak
> mengubah standar QRIS, tidak mengubah perangkat merchant, dan tidak
> menyentuh dana. Bisa dijalankan sepenuhnya di infrastruktur sendiri.
>
> Bukan mau menjual apa pun — kami belum punya pelanggan. Yang kami cari
> adalah 30 menit untuk menunjukkan demonya dan mendengar di mana asumsi
> kami keliru.
>
> Kalau ini bukan prioritas, itu jawaban yang berguna juga.
>
> Terima kasih,
> [nama]

## Yang dibawa ke pertemuan

| Berkas | Untuk siapa |
|---|---|
| `PITCH-PJP.md` | kepala produk / risk / compliance |
| `INTEGRATION.md` | tim engineering mereka |
| `THREAT-MODEL.md` | tim keamanan mereka |
| demo langsung | semua orang |

Demonya jalankan **sebelum** presentasi, bukan sambil bicara:

```bash
python scripts/demo_lintas_pjp.py     # kenapa lapisan bersama
python scripts/preflight.py           # bukti sistemnya memang jalan
```

## Tiga hal yang akan ditanyakan, dan jawabannya

**"Data kami keluar ke mana?"**
Tidak ke mana-mana. Tahap satu dijalankan penuh di infrastruktur Anda.
Kode dan skemanya terbuka untuk diaudit sebelum dijalankan.

**"Kalau salah menandai merchant sah bagaimana?"**
Itu yang paling kami jaga. Sistem tidak pernah memblokir — tingkat
tertinggi adalah menunda, karena rekayasa sosial bergantung pada tekanan
waktu. Dan status "belum dikenal" ditampilkan sebagai belum dikenal,
bukan sebagai peringatan.

**"Siapa yang menjamin ini kalau ada apa-apa?"**
Tidak ada. Kami tim mahasiswa dengan proof of concept, dan tidak akan
berpura-pura sebaliknya. Karena itu permintaan kami hanya percakapan,
bukan pemasangan.

## Jangan lakukan ini

- Jangan menyebut angka kerugian fraud yang tidak kalian punya
  sumbernya. Orang industri tahu angka sebenarnya, dan angka karangan
  mengakhiri percakapan lebih cepat daripada tidak ada angka.
- Jangan menyebut Layer 2 "pakai AI" atau "machine learning". Sistem ini
  deterministik, dan itu keunggulannya — tiap putusan bisa dijelaskan
  kalimat per kalimat.
- Jangan mengklaim parameter sudah dikalibrasi lapangan sebelum
  surveinya benar-benar dijalankan.
