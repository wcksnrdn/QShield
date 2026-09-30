# Apa yang terjadi waktu kamu scan — dari awal sampai lampunya nyala

> Dokumen ini pasangannya [`PENJELASAN-SEDERHANA.md`](PENJELASAN-SEDERHANA.md).
> Yang itu menjelaskan **kasus-kasus** yang kita tangani. Yang ini
> menjelaskan **mesinnya** — apa yang jalan, urutannya bagaimana.
>
> Buat dibaca siapa saja di tim, termasuk yang tidak ngoding. Kalau ada
> yang bikin bingung, itu salah dokumennya.
>
> Istilah dasar (NMID, jangkar, pengamat, konsensus) dijelaskan di
> **§2 PENJELASAN-SEDERHANA.md**. Dokumen ini menganggap kamu sudah
> baca bagian itu.

---

## Gambaran besarnya dulu

Kamu buka aplikasi, arahin kamera ke stiker QRIS, dan **kurang dari
seperseratus detik** kemudian lampunya nyala.

Yang terjadi di antaranya, urut:

```
   kamu scan
       |
       v
  [ GERBANG ]     boleh diperiksa nggak?
       |          kalau nggak -> berhenti di sini
       v
  [ LAYER 1 ]     tempatnya bener nggak?
       |
       v
  [ LAYER 2 ]     QR-nya kelakuannya bener nggak?
       |
       v
  [ DIGABUNG ]    dua jawaban jadi satu lampu
       |
       +---> lampunya nyala di HP kamu
       |
       +---> sistem belajar dari scan ini (kalau bersih)
```

Lima tahap. Kita bahas satu-satu.

---

## Tahap 0 — Gerbang: "boleh diperiksa nggak?"

Sebelum satpam mulai kerja, ada empat pertanyaan. **Tiga di antaranya
bisa menghentikan pemeriksaan di tengah jalan** — dan itu memang
disengaja.

### Gerbang 1 — QR-nya kebaca nggak?

Isi QR dibongkar dan checksum-nya dihitung ulang. Kalau gagal, atau
nomor NMID-nya tidak ketemu:

> **Berhenti total.** Nggak ada putusan, nggak ada lampu, nggak ada yang
> dipelajari.

Analoginya: satpam nggak bisa memeriksa KTP yang robek jadi dua.

### Gerbang 2 — GPS-nya ngaku palsu?

Android bisa bilang terus terang *"lokasi ini hasil aplikasi fake GPS."*
Kalau HP mengaku begitu:

> **Layer 1 nggak dijalanin.** Skor lokasi dikunci di 65.

Kenapa nggak sekadar "dikurangi nilainya"? Karena kalau lokasinya palsu,
menilai "tempatnya bener nggak" itu **nggak ada artinya sama sekali** —
bukan sekadar kurang akurat.

### Gerbang 3 — QR-nya dari foto, bukan dari kamera langsung?

Ini kasus **"aku difotoin QR-nya, temenku yang bayar dari rumah."**

> **Layer 1 nggak dijalanin.** Skor lokasi = 0.

Lokasi temenmu itu **beneran** — dia memang di rumahnya. Tapi lokasi itu
**nggak ngomongin apa-apa soal di mana stikernya nempel.** Jadi jangan
dipakai.

### Gerbang 4 — GPS-nya terlalu ngawur?

Kalau HP bilang *"saya di sini, meleset paling banyak 800 meter"*:

> **Layer 1 nggak dijalanin.** Skor lokasi = 40.

Bayangin lingkaran 800 meter di peta. Di dalamnya muat **ratusan toko.**
Koordinat yang dikirim HP kebetulan jatuh di dekat es kelapa — tapi bisa
juga kamu 700 meter jauhnya. **GPS-nya sendiri nggak tahu.**

Batasnya **100 meter**. Ini yang kita sebut **Invarian §6**.

---

> ### Yang penting di tiga gerbang terakhir
>
> Layer 1 mati, tapi **Layer 2 tetap jalan penuh.**
>
> Alasannya gampang: kalau bentuk QR-nya cacat, cacatnya **nggak ada
> hubungannya sama GPS.** QR rusak tetap rusak mau kamu scan di Bandung
> atau di Papua. Buang Layer 2 = buang bukti yang masih sehat.

---

## Tahap 1 — Layer 1: "tempatnya bener nggak?"

Ini satpam yang ngecek **tempat**.

Sebelum mikir, dia ambil empat hal dari catatan:

| yang diambil | maksudnya |
|---|---|
| **tetangga** | semua jangkar dalam radius 50 meter dari kamu |
| **di tempat lain** | NMID yang sama ini pernah kecatat di mana aja |
| **buku pendatang** | siapa aja yang pernah "ditolak" di titik ini |
| **jejak kehadiran** | kalau NMID ini muncul di ≥2 wilayah, jejaknya ditarik |

Terus dia nanya **tiga pertanyaan**, urut:

### Pertanyaan A — "titik ini udah ada yang punya belum?"

```
titik ini kosong
  -> +35   "belum pernah kecatat"  (harga ketidaktahuan)

titik ini punya NMID LAIN yang udah mapan
  -> +60 sampai +85, dan langsung ANOMALY
     angkanya naik ikut jumlah pengamat:
       6 pengamat  -> 63
      47 pengamat  -> 83

titik ini TERDAFTAR RESMI atas merchant lain
  -> +85   sendirian aja udah cukup buat cooling_off

namanya DITIRU pula
  -> +90   ini yang paling berat di seluruh sistem
```

**Tapi sebelum menuduh, dia cek dua pintu keluar dulu:**

1. **Bersebelahan** — food court, dua lapak nempel. Bukan penukaran.
2. **Bergiliran** — es buah siang, nasi goreng malam. Bukan penukaran.
   (Cerita lengkapnya di §4.5 PENJELASAN-SEDERHANA.md.)

### Pertanyaan B — "NMID ini ada di mana aja selain di sini?"

```
cuma di sini            -> aman, nggak ngomong apa-apa
di banyak tempat jauh   -> curiga: stiker disebar?
```

Tapi **pedagang keliling juga kelihatan persis begitu.** Jadi sebelum
menuduh, dia pakai **fisika**, bukan statistik:

> Satu gerobak cuma bisa ada di satu tempat pada satu waktu.
> Lima stiker yang ditempel bareng hidup di lima tempat sekaligus.

Kalau nggak ada bukti "ada di dua tempat barengan" → **bukan tuduhan,
cuma nggak tahu.** Dihargai +35, sama persis kayak "tempat baru".

### Pertanyaan C — "riwayat titik ini gimana?"

```
terdaftar resmi     -20    lampu hijau paling kuat
mapan (>=3 HP, >=24 jam)  -20
masih baru          +15
belum pernah ada    +35
```

### Hasilnya

Lampu hijau (`verified`) cuma keluar kalau **dua-duanya** kepenuhan:

```
jangkarnya mapan   DAN   skornya <= 25
```

> **Konsekuensi yang harus selalu diingat:** bobot apa pun di atas 25
> yang bisa nyala di merchant jujur = **merchant itu nggak akan pernah
> bisa hijau.** Ini alasan kenapa angka-angkanya dipilih hati-hati —
> lihat [`docs/KALIBRASI-BOBOT.md`](../KALIBRASI-BOBOT.md).

---

## Tahap 2 — Layer 2: "QR-nya kelakuannya bener nggak?"

Satpam kedua. Dia **nggak lihat tempat sama sekali** — dia lihat
**QR-nya sendiri.**

Analoginya: satpam pertama ngecek *"orang ini emang tinggal di sini?"*,
satpam kedua ngecek *"KTP-nya bentuknya bener nggak?"*

Tujuh hal yang dia periksa:

| yang dicek | contoh yang bikin curiga | +skor |
|---|---|---|
| **bentuk QR** | nomor NMID bukan 15 karakter; stiker statis kok ada nominalnya | 70 |
| **QR sekali pakai** | QR kasir dipakai 4× / muncul di dua kota | 30 / 55 |
| **label tercetak** | tulisan di stiker ≠ isi QR-nya | 75 / 45 |
| **WiFi sekitar** | daftar WiFi nggak cocok sama yang dulu | 30 |
| **HP-nya** | rooted / gagal pemeriksaan PJP | 25 / 30 |
| **asal-usul** | kota di QR ≠ kota wilayah itu | 40 |
| **keanehan profil** | ≥3 dari 16 ciri merchant tergolong langka | 25 |

Dua yang terakhir bukan aturan yang ditulis tangan — itu **dipelajari
dari data lapangan**. Sistem menghitung sendiri apa yang "normal", lalu
mengenali yang menyimpang.

---

## Tahap 3 — Digabung jadi satu lampu

Dua jawaban tadi disatukan. **Tiga aturan, dan ketiganya searah:**

### Aturan 1 — skornya dijumlah, maksimal 100

```
skor Layer 1  +  skor Layer 2  =  skor akhir
```

### Aturan 2 — Layer 2 cuma bisa memperburuk, nggak pernah memperbaiki

**Nggak ada satu pun angka minus di Layer 2.** Ini disengaja:

> QR yang bentuknya rapi **bukan berarti** stikernya di tempat yang benar.

Kalau Layer 2 boleh mengurangi skor, penipu tinggal bikin QR yang
rapi-rapi banget buat **menebus** kecurigaan dari Layer 1. Bentuk QR itu
dikendalikan penipu; riwayat tempat nggak.

> **Prinsip yang mengatur seluruh sistem:** hal yang dikendalikan penipu
> boleh bikin lebih ketat, nggak pernah boleh bikin lebih longgar.

### Aturan 3 — lampunya tetap empat itu aja

```
 0-25   proceed      bayar aja
26-50   warn         lanjut boleh, baca dulu peringatannya
51-75   step_up      minta verifikasi tambahan
76-100  cooling_off  stop, jangan bayar
```

### Dan satu hal soal urutan alasan

Alasan dari dua layer **diurutkan ulang menurut beratnya**, bukan
menurut urutan kode jalan. Dulu pernah kebalik: *"lokasi ini belum
pernah tercatat"* (+35, paling ringan) muncul **di atas** *"format
Merchant ID nggak sesuai standar"* (+70, yang menentukan).

Orang baca dari atas dan sering berhenti di baris pertama. Yang di atas
harus yang paling penting.

---

## Tahap 4 — Sistem belajar dari scan ini

Bagian ini yang bikin Q-Shield makin pinter tiap hari.

```
hasilnya ANOMALY        ->  nggak belajar apa-apa
hasilnya dari FOTO      ->  belajar bentuk QR aja, NGGAK belajar tempat
hasilnya bersih         ->  belajar semuanya
```

**Kenapa anomaly nggak dipelajari?** Karena kalau dipelajari, penipu
bisa scan stikernya sendiri berkali-kali sampai stikernya dianggap
"mapan". Ini **Invarian §3**.

**Kenapa dari foto cuma belajar sebagian?** Dulu ada anggota tim
mengkatalogkan QRIS dari internet sambil duduk di kantor — hasilnya
**tujuh QRIS dari Karanganyar sampai Mandailing Natal semuanya tercatat
di satu titik di Jakarta.** Pengetahuan wilayah untuk lingkungan itu
jadi kacau.

Jadi dipisah:

```
pengetahuan TEMPAT    jangkar, kota wilayah, sidik WiFi
                      -> cuma dari scan di tempatnya langsung

pengetahuan BENTUK    kebiasaan penerbit, keanehan profil
                      -> boleh dari foto; bentuk QR nggak berubah
                         gara-gara difoto
```

### Dan satu buku catatan lagi

Kalau hasilnya anomaly **yang berkaitan tempat**, dicatat dua kali, dari
dua sudut:

- dari sudut **titiknya**: "titik ini jadi sasaran"
- dari sudut **yang ditolak**: masuk **buku pendatang**

Buku pendatang inilah yang dipakai pedagang jujur buat membuktikan diri
— pedagang giliran, pedagang yang pindah lapak. Jadi ditolak sekali
bukan vonis seumur hidup.

---

## Tahap 5 — Tiket

Terakhir, dikeluarkan **tiket**: surat pendek bertanda tangan yang
bilang *"jam segini, buat QR dengan sidik jari ini, putusannya ini."*

Gunanya: biar nggak ada yang bisa **memeriksa QR A terus bayar ke QR B**.

> Jujur soal batasnya: tiket ini cuma berguna kalau **ada yang
> memeriksanya.** Yang mengeksekusi pembayaran itu PJP, dan Q-Shield
> nggak ada di jalur itu. Jangan pernah bilang ke juri "aplikasi nggak
> bisa mengabaikannya" — itu nggak bener.

---

## Empat contoh sungguhan

Semua di bawah ini hasil **menjalankan sistemnya beneran**, bukan
karangan.

### A. Merchant yang dikenal, GPS bagus

```
verdict : verified / proceed    skor 0
layers  : lokasi 0   perilaku 0
  - Konsisten dengan 6 pengamatan sebelumnya di lokasi ini
  - Reputasi lokasi ini dibangun dari pemindaian anonim — tidak ada
    pengamat yang dijamin penyelenggara pembayaran
```

Baris kedua itu **kejujuran yang sengaja dipasang**. Hijau yang berdiri
di atas 6 scan anonim nggak boleh kelihatan sama persis dengan hijau
yang berdiri di atas 50 scan yang dijamin PJP.

### B. Tempat yang belum pernah tercatat

```
verdict : unknown / warn        skor 35
layers  : lokasi 35  perilaku 0
  - Lokasi ini belum pernah tercatat sebelumnya
```

Perhatiin: **bukan hijau, tapi juga bukan tuduhan.** Sistem lagi jujur
bilang "saya nggak tahu".

### C. Stiker lain di titik yang udah bertuan

Jangkar dengan **6 pengamat**:

```
verdict : anomaly / step_up     skor 63
  - Di titik ini tercatat ES KELAPA BU SRI. Kode yang dipindai atas
    nama TOKO LAIN.
  - Merchant ID berbeda dari 6 pengamatan sebelumnya di lokasi ini
```

Jangkar yang sama tapi **47 pengamat**:

```
verdict : anomaly / cooling_off  skor 83
  - Merchant ID berbeda dari 47 pengamatan sebelumnya di lokasi ini
```

> **Ini inti sistemnya dalam satu gambar.** Serangannya sama persis.
> Yang beda cuma **seberapa banyak bukti yang dikumpulin sistem.**
> Makin banyak orang pernah scan, makin berani sistemnya menahan.

### D. GPS jelek (akurasi 800 meter)

```
verdict : unknown / warn        skor 40
layers  : lokasi 40  perilaku 0
  - Akurasi lokasi rendah (800 m) — verifikasi lokasi tidak dapat
    dilakukan
```

**Sistem menolak menebak.** Ini Invarian §6 lagi.

---

## Kedelapan invarian, bahasa gampang

Invarian itu **janji yang nggak boleh dilanggar perubahan kode apa pun
di masa depan.** Bukan fitur — fitur boleh diganti, invarian nggak.

Ada test khusus yang tiap kali dijalankan **sengaja mencoba
melanggarnya**. Kalau ada yang jebol, testnya gagal.

| # | Janjinya | Kenapa |
|---|---|---|
| **§1** | Kotak peta pakai ukuran ~153 m, bukan yang lebih kecil | Yang lebih kecil cuma nangkep 44% — jangkarnya ilang gara-gara GPS goyang |
| **§2** | `unknown` **nggak pernah** berarti aman | Nggak ada bukti ≠ bukti nggak ada |
| **§3** | Scan yang ditolak **nggak pernah** bikin reputasi | Biar penipu nggak bisa scan stikernya sendiri sampai "mapan" |
| **§4** | Empat lampu, titik. Nggak ada lampu kelima | Konsisten buat PJP yang mengintegrasikan |
| **§5** | Rumus konsensus dikunci apa adanya | Angka ini dipakai di pitch — harus tetap bener |
| **§6** | GPS >100 m → **nolak ngasih putusan** | Nebak dari lingkaran 800 m itu bukan penilaian |
| **§7** | Merchant bersebelahan **bukan** penukaran stiker | Food court nggak boleh dituduh |
| **§8** | **Nggak ada identitas orang** di database | 69 kolom, 13 tabel, dan serangannya gagal semua |

Jalanin sendiri:

```bash
python3 tests/test_invariants.py
```

Hasilnya sekarang: **Seluruh 9 invarian utuh.**
(Sembilan pemeriksaan, delapan invarian — §1 diperiksa dua kali.)

---

## Contekan buat juri

**"Bedanya Layer 1 sama Layer 2 apa?"**

> Layer 1 nanya *"stiker ini emang yang seharusnya ada di sini?"*
> Layer 2 nanya *"QR ini kelakuannya kayak QR yang sah?"*
> Keduanya bisa gagal sendiri-sendiri, jadi Layer 2 **melengkapi**,
> bukan menggantikan.

**"Kenapa sering keluar `unknown`, bukan hijau?"**

> Karena `unknown` itu **jawaban yang jujur**, dan kami memilih
> mengatakannya daripada menebak. Sistem yang nggak pernah bilang
> "nggak tahu" itu sistem yang menebak diam-diam.

**"Kalau GPS-nya jelek gimana?"**

> Kami **menolak memberi putusan lokasi.** Itu fitur, bukan bug —
> kebanyakan sistem akan menebak.

**"Datanya aman nggak?"**

> Nggak ada identitas orang sama sekali di database. Yang disimpan
> "berapa HP berbeda", bukan "HP siapa". Dan penanda HP-nya **beda-beda
> di tiap tempat**, jadi nggak bisa dipakai melacak orang pindah-pindah.

---

## Kalau mau nyoba sendiri

```bash
python3 scripts/diagnose.py PAYLOAD LAT LNG [AKURASI]   # bongkar satu scan
python3 scripts/diagnose.py --anchor LAT LNG            # isi jangkar di titik itu
python3 tests/test_invariants.py                        # kedelapan janji
python3 tests/test_bobot.py                             # kenapa angkanya segitu
```

---

## Bacaan lanjutan

| Kalau mau tahu | Baca |
|---|---|
| kasus-kasus yang ditangani + ceritanya | [`PENJELASAN-SEDERHANA.md`](PENJELASAN-SEDERHANA.md) |
| kenapa tiap angka bobotnya segitu | [`../KALIBRASI-BOBOT.md`](../KALIBRASI-BOBOT.md) |
| ancaman + yang masih terbuka | [`../THREAT-MODEL.md`](../THREAT-MODEL.md) |
| cara dipakai PJP | [`../INTEGRATION.md`](../INTEGRATION.md) |
| cara scan yang bener di lapangan | [`PANDUAN-SCAN.md`](PANDUAN-SCAN.md) |
