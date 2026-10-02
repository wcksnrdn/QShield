# Apa yang bikin Q-Shield beda

> Dokumen ini buat **dibaca seluruh tim sebelum tampil**. Isinya bukan
> kata sifat — tiap klaim keunikan di sini punya angka atau mekanisme
> di belakangnya, dan semuanya bisa dijalankan ulang dari repo.
>
> Aturan yang kupegang saat menulis: **kalau sebuah klaim tidak bisa
> ditunjuk ke kode atau ke hasil pengukuran, klaim itu tidak masuk.**

---

## Satu kalimat, kalau cuma punya sepuluh detik

> Semua orang memeriksa **apakah QR-nya asli**.
> Kami memeriksa **apakah QR-nya ada di tempat yang benar** —
> karena pada serangan ini, QR-nya memang asli.

---

# BAGIAN 1 — Keunikan yang paling kuat

## Keunikan #1: Kami membuktikan pendekatan yang lazim itu MUSTAHIL, sebelum membangun punya kami

Ini yang paling jarang dilakukan tim lain, dan paling mudah diperiksa
juri.

Sebelum membangun apa pun, kami uji dulu cara yang paling murah:
**bisa nggak penipuan ini ketahuan cuma dari isi QR-nya?** Kami ambil
**16 ciri** dari QR korban dan QR penipu, lalu dibandingkan
berdampingan.

```
ciri STRUKTURAL  — ditentukan generator acquirer     12 ciri   0 berbeda
ciri DESKRIPTIF  — diisi merchant saat mendaftar      4 ciri   2 berbeda
```

**Nol dari dua belas.** Dan itu masuk akal: stiker penipu diterbitkan
acquirer yang sama dengan stiker korban.

Lalu diukur ulang di data lapangan: dari **52 merchant asli** satu
penerbit, **5 dari 6 ciri struktural identik pada SELURUH 52**.

**Kenapa ini keunikan, bukan sekadar riset:**

Kebanyakan solusi anti-penipuan QR menjual "deteksi QR palsu". Kami
punya **bukti terukur bahwa pendekatan itu tidak bisa menangkap
sticker-swap** — dan bukti itu bentuknya negatif, melawan kategori kami
sendiri. Tim yang berani mengukur bahwa jalan mudah itu buntu, biasanya
sudah memikirkan yang sulit.

> **Cara bilangnya:** *"Kami tidak memilih pendekatan ini karena kelihatan
> keren. Kami memilihnya karena kami ukur dulu bahwa yang lain tidak
> mungkin."*

---

## Keunikan #2: Bukti berselang-seling — pembedanya NOL, bukan kecil

Ini **mekanisme paling baru** yang kami punya, dan paling layak jadi
klaim paten.

**Masalahnya.** Satu titik dipakai bergantian: nasi uduk pagi, es buah
siang, nasi goreng malam. Semuanya sah, semuanya punya QRIS sendiri.
Tapi di mata sistem, pedagang kedua **tidak bisa dibedakan** dari orang
yang menempel stiker di atas stiker orang.

**Yang hampir semua orang lakukan:** turunkan ambangnya sampai pedagang
sah lolos. Harganya, penyerang ikut lolos.

**Yang kami lakukan:** cari bukti yang **tidak bisa dipalsukan penyerang
secara struktural**, bukan secara statistik.

> **Stiker yang menutupi tidak bisa bergantian.**
> Begitu ia menutup, QR di bawahnya hilang selamanya.

Jadi kalau merchant lama **muncul kembali** setelah penantang ada — lalu
penantang lagi, lalu merchant lama lagi — berarti tidak ada yang
tertutup.

```
pola                            kemunculan kembali / 7 hari
bergiliran (sah)                            6
stiker menutupi (serangan)                  0
```

**Nol, bukan kecil.** Itu bedanya dengan ambang statistik: serangan yang
sungguhan tidak lolos jalur ini pada ambang berapa pun, karena angkanya
memang nihil.

Hasilnya buat pedagang jujur: syarat perangkat turun dari 8 ke 4, dan
lapak sepi diterima **hari ke-5, bukan hari ke-9**.

> **Cara bilangnya:** *"Pembedanya bukan margin yang kami setel. Pembedanya
> nol — dan nol itu sifat fisik stikernya, bukan pilihan kami."*

---

## Keunikan #3: Fisika, bukan statistik

Masalah yang sama bentuknya, jalan keluar yang sama jenisnya.

**Masalahnya.** Gerobak kopi keliling dan sekotak stiker yang disebar
menghasilkan gejala **identik**: satu Merchant ID muncul di banyak
tempat berjauhan.

**Pembedanya bukan angka, tapi hukum alam:**

> Satu gerobak cuma bisa ada di satu tempat pada satu waktu.
> Lima stiker yang ditempel barengan hidup di lima tempat sekaligus.

Jadi tuduhan sebaran **menuntut bukti positif kehadiran serentak** — dua
pengamatan di area berbeda, terpaut waktu terlalu singkat untuk ditempuh
siapa pun.

```
ambang      pedagang dorong    pedagang bermotor    penyebar
            tertuduh           tertuduh             tertangkap
20 km/jam        0,0%              89,5%              13,2%
40 km/jam        0,0%              23,2%               6,8%
80 km/jam        0,0%               0,0%               3,8%
```

Kami pilih **80 km/jam** — nol persen pada **kedua** profil pedagang.

**Dan ini bagian yang penting:** kami memilih demi keselamatan pedagang,
**bukan demi angka tangkapan**. Harganya kami sebut terus terang — pada
ambang itu cuma 3,8% penyebar yang tertangkap lewat jalur ini.

> **Cara bilangnya:** *"Kami lebih memilih melewatkan penyerang daripada
> menuduh pedagang jujur. Dan kami menerbitkan harga dari pilihan itu."*

---

## Keunikan #4: Sistem kami boleh bilang "saya tidak tahu"

Hampir semua sistem deteksi itu biner: aman atau bahaya. Yang biner
**wajib menebak**, karena tidak punya tempat untuk ketidaktahuan.

Kami punya **tiga status**:

```
verified   kami kenal tempat ini, dan QR-nya cocok
unknown    kami TIDAK TAHU
anomaly    ada yang salah di sini
```

Dan satu aturan yang dikunci: **`unknown` tidak pernah berarti aman.**

Ini bukan sekadar niat baik — dijaga **struktural**. Fungsi penjaganya
dipanggil **dua kali**: sekali di akhir Layer 1, sekali lagi setelah
Layer 2 ikut dijumlahkan.

```
binding.py:1235   di akhir Layer 1
binding.py:1295   di akhir compose()   <- supaya sinyal Layer 2 baru
                                          tidak bisa membobolnya diam-diam
```

Dan ada tempat di mana kami **menolak memberi putusan sama sekali**:
kalau akurasi GPS di atas 100 meter, lingkaran ketidakpastiannya memuat
ratusan toko. Menilai jangkar terhadap itu bukan penilaian yang kurang
akurat — itu **penilaian yang tidak berarti**. Jadi Layer 1 tidak
dijalankan.

> **Cara bilangnya:** *"Menolak menjawab saat sinyalnya buruk itu fitur,
> bukan bug. Sistem yang tidak pernah bilang 'tidak tahu' adalah sistem
> yang menebak diam-diam."*

---

## Keunikan #5: Menuduh pedagang jujur kami perlakukan sebagai ANCAMAN, bukan sebagai gangguan

Ini yang paling Indonesia dari seluruh proyek ini, dan paling sulit
ditiru tim yang mengerjakan dari belakang meja.

Dagang jalanan di Indonesia melanggar aturan geospasial naif **setiap
hari**. Empat bentuknya kami temukan **di lapangan**, bukan di papan
tulis — lalu masing-masing kami ukur dan beri jalan keluar sendiri:

| Yang kami temui | Jalan keluarnya | Bukti yang dituntut |
|---|---|---|
| Dua lapak berdempetan (food court) | koeksistensi | basis pengamat sebanding, **atau** 8 perangkat + merchant lama masih terpindai |
| Pedagang pindah lapak | relokasi | 8 perangkat di tempat baru, lokasi lama sudah diam, periode tidak pernah beririsan |
| Gerobak keliling | mobilitas | tidak ada bukti kehadiran serentak, kecepatan ≤ 80 km/jam |
| Satu titik dipakai bergiliran | berselang-seling | merchant lama muncul kembali ≥ 2 kali |

Perhatikan polanya: **tidak satu pun diselesaikan dengan menurunkan
ambang sampai keluhannya berhenti.** Semuanya menuntut **bukti baru**.

Dan ada contoh nyata betapa seriusnya kami menanganinya. Dulu cacat
payload apa pun ikut menandai sebuah tempat sebagai "pernah diserang".
Akibatnya terukur di produksi:

```
7 merchant sungguhan di satu titik
mewarisi 4 percobaan anomali
— semuanya dari QR scam bercacat yang kebetulan dipindai di situ,
  bukan dari percobaan tukar stiker
```

Sekarang hanya anomali **yang berkaitan lokasi** yang boleh menandai
tempat. Dan pemilik sah sebuah jangkar **kebal** terhadap tanda itu —
secara desain:

```python
if (state.anomaly_attempts > 0 and not nmid_matches_anchor
        and anchor_has_owner):
```

Komentarnya di kode menyebut serangan yang dicegahnya: tanpa syarat itu,
penipu bisa menaikkan risiko merchant jujur cukup dengan menempel stiker
palsu berkali-kali di depan lapaknya.

> **Cara bilangnya:** *"Deteksi yang menuduh pedagang sah tidak akan
> pernah dipasang PJP mana pun — kasirnya menolak lebih dulu."*

---

## Keunikan #6: Model tanpa label, dan model itu bisa menjelaskan dirinya

Kami pakai dua model machine learning, dan **keduanya tak-terawasi
(unsupervised)** — bukan karena gaya-gayaan, tapi karena terpaksa, dan
alasannya penting:

> **Contoh penipuan yang terkonfirmasi itu tidak ada.**
> Classifier terawasi mustahil dilatih tanpa label.

Jadi yang kami pelajari bukan "seperti apa penipuan", melainkan
**"seperti apa normal"**, lalu penyimpangan dikenali dari situ.

```
dialek penerbit      cara tiap PJP MENYUSUN payload-nya. Generatornya
                     deterministik. Payload yang mengaku dari penerbit
                     tertentu tapi tidak mengikuti dialeknya berarti
                     dibangkitkan ulang orang lain.

kelangkaan profil    seberapa sering tiap nilai ciri muncul pada
                     merchant yang diamati. Payload yang membawa
                     BEBERAPA nilai langka sekaligus ditandai.
```

**Dan ini pembedanya dari model buram:** model kami **menyebut ciri mana
yang langka dan seberapa langka**. Bukan skor tanpa penjelasan.

> Putusan yang tidak bisa dijelaskan tidak punya tempat di sistem
> pembayaran.

Diukur terhadap merchant sungguhan, bukan populasi sintetis:
leave-one-out pada **122 merchant lapangan** menandai 5 — **4,1% positif
palsu**.

---

# BAGIAN 2 — Keunikan dari cara kerja, bukan dari fitur

## Keunikan #7: Kami menerbitkan batas-batas kami, lengkap dengan pengukurannya

Enam batas masih terbuka, dan semuanya tertulis di `THREAT-MODEL.md`
dengan angka di belakangnya:

| | Batasnya |
|---|---|
| **R19** | model kelangkaan buta terhadap penyerang yang meniru profil lazim |
| **R20** | stiker yang sudah ditukar sebelum difoto tidak bisa ditangkap dari sisi pembayar |
| **R21** | penyebar sekota tidak terpisahkan dari pedagang keliling — cuma 3,8% tertangkap |
| **R22** | konsensus bisa dikarang dengan identitas perangkat buatan |
| **R23** | ambang waktu tidak membebani penyerang yang tidak perlu hadir |
| **R24** | swap paruh waktu tidak terpisahkan dari pedagang bergiliran |

Dua di antaranya layak disebut khusus:

**R22 adalah kelemahan yang kami temukan di sistem kami sendiri**, lalu
kami terbitkan alih-alih tutupi. Tiga string karangan yang direntang
melewati ambang waktu bisa membuat jangkar baru jadi `verified`.
Tanggapannya bukan menaikkan ambang — menghitung angka yang bisa
dikarang tetap menghitung angka yang bisa dikarang — melainkan membuat
tiap putusan **menyebutkan asal-usul reputasinya**.

**R23 adalah keputusan yang kami BATALKAN**, lengkap dengan alasannya,
supaya tidak diulang orang lain di kemudian hari.

> **Cara bilangnya:** *"Laporan tanpa batas terbaca seperti brosur. Kami
> menuliskan enam, dengan pengukurannya."*

---

## Keunikan #8: Delapan janji yang dikunci oleh test yang BERUSAHA melanggarnya

Fitur boleh diganti. **Invarian tidak.**

`tests/test_invariants.py` bukan test fitur. Tugasnya satu: memastikan
tidak ada perubahan di masa depan — termasuk dari kami sendiri — yang
diam-diam melanggar keputusan yang sudah dibayar dengan pengujian.

Contohnya invarian §8 (tanpa identitas pengguna). Testnya **tidak**
sekadar memeriksa tidak ada kolom bernama "nama". Ia menghitung skema
yang hidup — **69 kolom, 13 tabel** — lalu **menyerangnya**: serangan
JOIN, perangkaian antar-lokasi, dan penghitungan rujukan. Ketiganya
harus gagal, sementara deduplikasi harus tetap jalan.

```
Seluruh 9 invarian utuh.
```

---

## Keunikan #9: Nilainya BERTAMBAH kalau dipakai bersama

Ini sifat yang jarang dimiliki produk keamanan.

Stiker penipu dipindai oleh pelanggan **semua dompet digital**. Jadi
tidak ada satu PJP pun yang melihat gambaran utuhnya — dan tidak ada
satu PJP pun yang bisa membangun pertahanannya sendirian.

```
Model A   satu PJP, di infrastrukturnya sendiri, tidak ada data keluar
Model B   satu peta bersama — pemindaian pengguna satu dompet
          melindungi pengguna dompet lain
```

Dan perbedaannya **bisa diperagakan**, bukan diperdebatkan:
`scripts/demo_lintas_pjp.py` menjalankan kedua dunia berdampingan dengan
rangkaian kejadian yang sama persis.

---

## Keunikan #10: Tiap angka bisa dijalankan ulang

Tidak ada satu pun angka di laporan kami yang berupa klaim. Semuanya
keluaran skrip di repo, dan laporannya mencantumkan perintahnya.

```
tests/test_bobot.py        mengunci TIAP bobot yang dikutip dokumen
scripts/calibrate_*.py     15 program kalibrasi
UNCALIBRATED               ditandai eksplisit di kode untuk yang BELUM
                           punya dasar empiris
```

Yang terakhir itu yang paling jarang: kami **menandai sendiri** tiga
parameter yang belum dikalibrasi lapangan, dan memberi mereka pembatas
supaya tidak bisa menggerakkan putusan sendirian.

---

# BAGIAN 3 — Dibanding pendekatan lain

| Pendekatan | Kenapa tidak menyelesaikan sticker-swap |
|---|---|
| **Deteksi "QR palsu" / cek keaslian payload** | QR-nya memang asli. Kami ukur: 0 dari 12 ciri struktural berbeda |
| **Deteksi penipuan pasca-transaksi** | Uangnya sudah pindah. Kami bekerja **sebelum** layar PIN |
| **Daftar putih merchant terpusat** | Menuntut pemetaan dari atas untuk 42,75 juta merchant, 93% di antaranya UMKM |
| **Laporan pengguna** | Baru bekerja setelah ada korban, dan korbannya sering tidak sadar |
| **Stiker anti-tamper fisik** | Ongkos per stiker × puluhan juta merchant |
| **Terminal POS** | Ongkos perangkat; justru yang tidak dimiliki pedagang kecil |
| **Geofencing biasa** | Butuh peta yang digambar duluan. QRIS tidak membawa koordinat, dan tidak ada yang menerbitkan posisi tiap pedagang kaki lima |

**Pembeda struktural kami:** peta itu kami **bangun dari pembayarannya
sendiri** — dan bukti yang sama yang melokasikan merchant adalah bukti
yang mendeteksi serangannya.

---

# BAGIAN 4 — Yang JUJUR tentang keunikan kami

Juri yang baik akan menguji apakah kalian tahu bedanya "baru" dan
"bagus". Jadi pisahkan sendiri sebelum ditanya:

**Benar-benar baru (layak klaim paten):**
- Bukti **berselang-seling** untuk memisahkan pedagang bergiliran dari
  stiker yang menutupi — pembedanya struktural dan bernilai nol
- Konsensus spasial **lintas-PJP** dengan hashing yang dilingkupi per
  lokasi
- Protokol **tiket pra-PIN** yang memisahkan pihak pemverifikasi dari
  pihak penyelesai

**Jarang, tapi bukan hal baru:**
- Konsensus crowdsourced untuk lokasi
- Deteksi anomali tak-terawasi
- Skema tanpa PII

**Bukan hal baru sama sekali, tapi jarang dikerjakan serapi ini:**
- Menerbitkan batas sendiri dengan pengukurannya
- Invarian yang dikunci test yang berusaha melanggarnya
- Menandai parameter yang belum dikalibrasi

> **Catatan jujur:** kami **belum** melakukan penelusuran prior art
> paten. Jadi yang kami klaim adalah *mekanismenya berbeda secara
> struktural dan kami bisa menunjukkan pengukurannya* — bukan *belum
> pernah ada orang yang memikirkannya*.

---

# BAGIAN 5 — Cara menyampaikannya

## Kalau cuma punya 30 detik

> Penipuan QRIS yang paling sering terjadi bukan QR palsu — QR-nya asli,
> yang palsu **tempatnya**. Kami buktikan dulu bahwa memeriksa isi QR
> tidak bisa menangkap itu: dari 16 ciri, nol ciri struktural yang
> berbeda. Jadi kami memeriksa hal lain — **apakah merchant ini memang
> seharusnya di sini** — dan kami bangun pengetahuan itu dari pemindaian
> pembeli biasa.

## Kalau punya 2 menit, tambahkan satu ini saja

Pilih **bukti berselang-seling**. Itu yang paling mudah dipahami dan
paling sulit dibantah:

> Satu titik dipakai bergantian — es buah siang, nasi goreng malam.
> Keduanya sah. Dulu sistem kami menuduh yang kedua selama 3 sampai 9
> hari.
>
> Buktinya ternyata sudah ada di data, cuma belum dibaca: **stiker yang
> menutupi tidak bisa bergantian.** Begitu ia menutup, QR di bawahnya
> hilang selamanya.
>
> Kami ukur: pedagang bergiliran yang sah, merchant lama muncul kembali
> enam kali seminggu. Stiker yang menutupi: **nol.** Bukan kecil — nol.

## Kalau punya 5 menit

Tambahkan **Keunikan #3** (fisika, bukan statistik) dan **Keunikan #7**
(batas yang diterbitkan). Keduanya memperlihatkan cara berpikir, bukan
cuma hasil.

---

## Kalau juri meremehkan

**"Ini kan cuma geofencing."**
> Geofencing mulai dari peta yang digambar seseorang. Kami tidak punya
> peta — QRIS tidak membawa koordinat, dan tidak ada yang menerbitkan
> posisi tiap pedagang kaki lima. Kami bangun petanya dari
> pembayarannya sendiri, dan bukti yang sama yang melokasikan merchant
> adalah yang mendeteksi serangannya.

**"Ini kan cuma crowdsourcing biasa."**
> Crowdsourcing bagian yang mudah. Yang sulit adalah menjaga agar
> penyerang tidak bisa ikut menyumbang. Scan yang ditolak membangun nol
> reputasi, dan kami terbitkan bagaimana konsensus itu masih bisa
> dikarang — R22.

**"Kenapa belum ada yang bikin kalau segampang itu?"**
> Karena bagian yang sulit bukan idenya, melainkan **tidak menuduh
> pedagang jujur.** Kami temukan empat bentuk dagang Indonesia yang
> melanggar aturan naif, dan tiap satunya menuntut mekanisme baru, bukan
> ambang yang dilonggarkan.

**"Kalian kan mahasiswa."**
> Benar, dan kami tidak akan berpura-pura sebaliknya. Karena itu kami
> menerbitkan batas-batas kami, tiap klaim menunjuk ke test yang bisa
> Anda jalankan sendiri, dan yang kami minta adalah percakapan tiga
> puluh menit — bukan pemasangan.

---

## Satu hal yang paling layak dibanggakan

Bukan fiturnya. **Cara kami sampai ke sana.**

Tiap mekanisme di dokumen ini lahir dari masalah yang ditemukan **di
lapangan**, lalu diukur, lalu diselesaikan dengan **bukti baru** —
bukan dengan melonggarkan ambang sampai keluhannya berhenti.

Dan tiap kali kami tidak bisa menyelesaikan sesuatu, kami tuliskan,
beserta angkanya.
