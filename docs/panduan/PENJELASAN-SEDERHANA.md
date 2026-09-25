# Q-Shield dijelaskan pakai bahasa manusia

> Dokumen ini untuk **dibaca siapa saja di tim**, termasuk yang tidak
> ngoding. Tidak ada istilah yang dipakai sebelum dijelaskan. Kalau ada
> bagian yang bikin bingung, itu salah dokumennya, bukan salah kamu.
>
> Isinya: cara kerja Q-Shield secara umum, lalu **empat hal yang
> dibangun 25 September 2026** beserta alasannya.

---

## 1. Q-Shield itu apa, dalam satu paragraf

Bayangin **satpam** yang berdiri di sebelah setiap stiker QRIS. Tugasnya
cuma satu: sebelum kamu bayar, dia mastiin **stiker ini memang stiker
yang seharusnya ada di tempat ini.**

Kenapa itu penting? Karena penipuan QRIS yang paling sering kejadian di
Indonesia bukan "QR palsu". Penipunya **daftar akun merchant beneran**
di penyelenggara beneran, dapat stiker terbitan resmi, lalu
**menempelkannya menutupi stiker warung orang.** Uangmu masuk ke dia.

Jadi QR-nya asli. Yang palsu **tempatnya.**

Itu sebabnya Q-Shield tidak memeriksa "QR ini asli atau tidak" — itu
pertanyaan yang salah. Yang diperiksa: **"QR ini di tempat yang benar
atau tidak."**

---

## 2. Kosakata — tujuh istilah, sekali baca selesai

| Istilah | Artinya kalau diomongin manusia |
|---|---|
| **NMID** | nomor KTP-nya merchant. Setiap warung punya satu, tertulis di dalam QR-nya |
| **Jangkar** (anchor) | titik di peta tempat sebuah NMID biasa ditemukan. "Warung Bu Sri biasanya ada di sini" |
| **Pengamat** (observer) | HP berbeda yang pernah scan QR itu di titik itu. 10 pengamat = 10 HP berbeda |
| **Konsensus** | kesepakatan banyak HP. Kalau 3 HP berbeda scan QR yang sama di tempat yang sama, jangkar itu dianggap "nyata" |
| **Payload** | isi mentah QR-nya — teks panjang penuh angka yang kamu lihat kalau QR-nya dibaca |
| **PJP** | Penyelenggara Jasa Pembayaran. DANA, GoPay, OVO, BCA. Mereka yang punya jutaan pengguna |
| **Dijamin** (vouched) | pengamat yang HP-nya sudah diperiksa PJP, bukan sekadar mengaku |

---

## 3. Lampu-lampunya

Q-Shield tidak cuma bilang "aman" atau "bahaya". Ada **tiga status** dan
**empat lampu**.

**Status** menjawab: *sistem tahu apa soal tempat ini?*

| Status | Artinya |
|---|---|
| `verified` | kami kenal tempat ini, dan QR-nya cocok ✅ |
| `unknown` | kami **tidak tahu**. Bukan berarti aman, bukan berarti bahaya |
| `anomaly` | ada yang salah di sini 🚨 |

**Lampu** menjawab: *jadi kamu harus apa?*

| Lampu | Artinya buat pengguna |
|---|---|
| `proceed` | jalan terus, hijau |
| `warn` | lanjut boleh, tapi baca dulu peringatannya |
| `step_up` | butuh verifikasi tambahan sebelum lanjut |
| `cooling_off` | berhenti. Jangan bayar |

**Aturan penting yang tidak boleh dilanggar:** kalau statusnya `unknown`,
lampunya **tidak akan pernah** `proceed`. "Tidak tahu" tidak boleh
berubah jadi "aman". Ini kita sebut **Invarian §2**, dan ada test khusus
yang memastikan aturan ini tidak pernah bocor.

---

## 4. Yang dibangun semalam — empat hal

Keempatnya berangkat dari **pertanyaan yang diajukan anggota tim**,
bukan dari daftar fitur. Itu sengaja: pertanyaan orang yang memakai
sistemnya menemukan lubang yang tidak ditemukan orang yang membangunnya.

---

### 4.1 Bayar dari jauh — "aku foto QR-nya, temenku yang bayar"

**Ceritanya.** Kamu di warung madura, difotoin QR-nya, dikirim WhatsApp
ke Fredo, Fredo yang bayar dari rumahnya.

**Masalahnya ada dua, dan yang kedua tidak kelihatan.**

Masalah pertama: Fredo ada di rumahnya, 11 km dari warung. Satpam kita
lihat "QR warung madura kok discan di perumahan?" lalu curiga. **Warung
yang sah kena tuduh gara-gara pembayarnya jauh.**

Masalah kedua, dan ini yang berbahaya: scan Fredo **bikin jangkar baru
di rumah Fredo.** Sekarang sistem mengira warung madura itu punya dua
tempat. Tiap "tempat palsu" yang jaraknya lebih dari 1 km menambah
**hukuman +25 permanen** ke warung itu — selamanya, tidak bisa dihapus.

Bayangin ribuan orang bayar dari galeri tiap hari. Korpus kita rusak
pelan-pelan, dan yang rusak justru reputasi pedagang yang sah.

**Yang kami bangun.** Penanda baru namanya `from_image`. Kalau aplikasi
bilang "ini dibaca dari gambar, bukan dari stiker di depan mata", maka:

- pemeriksaan lokasi **dimatikan total** — koordinat Fredo memang tidak
  mengatakan apa-apa soal letak stiker
- **tidak ada jangkar yang ditanam** — masalah kedua tertutup
- pemeriksaan bentuk QR **tetap jalan penuh** — bentuk QR tidak berubah
  cuma karena difoto
- jawabannya jujur: *"Dipindai dari gambar — penempatan stiker tidak
  dapat diverifikasi dari sini."* Kuning, bukan merah, bukan hijau

**Bonus: sistem tetap bisa kasih informasi berguna.** Namanya
`known` — apa yang sudah pernah **diamati** soal NMID itu:

```
QR ini kami kenal:
  WARUNG MADURA — Bandung
  47 pengamatan, terpantau sejak Maret 2026
```

versus QR penipu:

```
  belum pernah kami amati di mana pun
```

Bedanya kelihatan? **Nama di QR bisa diketik siapa saja waktu daftar.
Riwayat pengamatan tidak bisa dikarang.** Fredo tinggal cocokin sendiri
sama yang kamu bilang.

**Satu jebakan yang ditemukan test sendiri.** Penanda `from_image` itu
diisi aplikasi, dan aplikasi bisa bohong. Waktu diuji, ternyata
menyalakan penanda itu bisa **menurunkan** putusan dari "berhenti" jadi
"verifikasi dulu" untuk QR yang jelas-jelas cacat. Itu jadi tuas buat
penipu. Sudah ditutup: QR yang cacat bentuknya tetap merah, lewat jalur
apa pun.

**Yang tetap tidak bisa kami lakukan (jujur).** Kalau **kamu** yang
ketipu di warung, kamu memfoto stiker penipu, dan Fredo bayar ke penipu.
Informasinya sudah hilang sejak jepretan. Tidak ada mekanisme di sisi
pembayar yang bisa mengembalikannya. Ini kami catat terbuka sebagai
risiko **R20**.

---

### 4.2 Pedagang keliling — "kopi jago gerobaknya di mana-mana"

**Ceritanya.** Tukang kopi keliling muter 6 titik mangkal dalam sebulan.
Satpam kita punya aturan lama: *"satu NMID muncul di banyak tempat =
penipu yang nyebar stiker."*

Hasilnya: tukang kopi jujur dengan **46 pengamat** divonis
`anomaly` — *"pola khas stiker yang disebar."*

Yang bikin miris, di layar yang sama sistem juga menulis *"konsisten
dengan 9 pengamatan sebelumnya di lokasi ini."* Dua kalimat itu saling
bertentangan.

**Terus ada temuan yang membalik semuanya.**

Aku uji penipu sungguhan: nempel stiker di 4 warung mapan, 16 kali
discan korban. Hasilnya:

```
tiap stiker  -> merah, skor 75
berulang     -> merah total, skor 100
jangkar milik NMID penipu : 0
sinyal "nyebar stiker"    : TIDAK PERNAH menyala
```

**Kenapa nol?** Karena tiap scan penipu itu **ditolak**, dan ada aturan
keras di sistem kita: **scan yang ditolak tidak boleh membangun
reputasi.** Penipu tidak pernah berhasil mengumpulkan "banyak tempat",
jadi aturan "banyak tempat = penipu" tidak pernah kena ke dia.

Jadi aturan itu isinya **cuma nuduhin tukang kopi.**

**Yang kami bangun: tuduhan sekarang butuh bukti.** Dua macam bukti,
dan dua-duanya soal fisika, bukan statistik.

**Bukti 1 — "tidak ada yang bisa ada di dua tempat sekaligus"**

Perumpamaannya **kartu e-toll**. Operator tol tidak pernah mengukur kamu
nyetir berapa km/jam. Mereka cuma lihat dua catatan:

```
kartu #123 tap di gerbang Bandung   10:00
kartu #123 tap di gerbang Jakarta   10:10
```

lalu **hitung balik**: 150 km dalam 10 menit = 900 km/jam. Tidak ada
mobil begitu → **kartunya dikloning.**

QR kita persis sama:

| catatan | hitungan balik | putusan |
|---|---|---|
| 6 km dalam 2 jam | 3 km/jam | gerobak dorong, wajar |
| 6 km dalam 20 menit | 18 km/jam | motor santai, wajar |
| 6 km dalam 5 menit | 72 km/jam | ngebut, tapi masih mungkin |
| **6 km dalam 2 menit** | **186 km/jam** | **mustahil → stikernya dua** |

Garis batasnya **80 km/jam**. Di bawah: diam. Di atas: ini bukan satu
gerobak pindah, ini dua stiker hidup bareng.

**Bukti 2 — "kejauhan buat satu pedagang"**

Tukang kopi muter dalam satu kota. Kalau satu NMID muncul di Bandung
**dan** Surabaya, itu bukan gerobak — berapa pun jeda waktunya. Garis
batasnya **80 km**.

**Kalau tidak ada bukti keduanya?** Sistem bilang jujur: *"bisa pedagang
keliling, bisa juga stiker yang disebar; belum ada bukti yang memisahkan
keduanya."* **Kuning, bukan merah.**

**Angka pertamaku salah besar, dan kalibrasi menyelamatkannya.** Aku
awalnya menaruh garis di 20 km/jam. Pas diuji ke profil tukang kopi
**bermotor**:

| garis batas | tukang kopi bermotor yang tertuduh |
|---|---|
| 20 km/jam | **89,5%** ❌ |
| 40 km/jam | 23,2% ❌ |
| 80 km/jam | **0,0%** ✅ |

6 km dalam 18 menit itu **hari biasa** tukang kopi bermotor. Kalau
garisnya 20, hampir semuanya kena.

**Harga yang dibayar, jujur.** Penipu yang nyebar stiker **dalam satu
kota** dan jarang discan sekarang dapat kuning, bukan merah — cuma 3,8%
yang meninggalkan bukti. Kami pilih itu sadar, karena alternatifnya
menuduh **semua** tukang kopi keliling di Indonesia. Dan serangan yang
paling sering beneran kejadian — nempel di atas warung orang — **tidak
berubah sama sekali**, tetap merah total.

---

### 4.3 Asal-usul reputasi — temuan paling serius, dan tidak ada yang minta

Ini muncul dari satu pertanyaan iseng: **seberapa murah memalsukan
konsensus?**

Jawabannya bikin kaget:

```
Penipu nempel stiker di titik kosong, lalu scan sendiri
pakai 3 identitas HP karangan, dijeda 25 jam.

  Korban pertama scan -> HIJAU, "proceed"

  Ongkos: 3 string karangan + sabar 24 jam.
```

**Kenapa ini serius banget.** Seluruh sistem kita berdiri di atas satu
prinsip yang kami tulis sendiri dan pakai di mana-mana:

> **Nilai yang bisa diatur penyerang boleh bikin lebih ketat, tidak
> boleh bikin lebih longgar.**

Identitas HP (`device_anon_id`) itu **diisi aplikasi**. Dan reputasi
tumbuh dari situ. Jadi di **titik paling inti** — konsensus pengamat,
hal pertama yang kita sebut di tiap presentasi — prinsip itu dilanggar
**terbalik**. Tidak ada yang sadar sampai diuji.

**Yang sengaja TIDAK kami lakukan: menaikkan jumlah pengamat minimum.**

Menghitung angka yang bisa dikarang tetap menghitung angka yang bisa
dikarang. Naik dari 3 ke 6 cuma bikin penipu kerja dua kali lipat —
sambil menghukum **setiap pedagang jujur selamanya**. Dan Es Kelapa,
satu-satunya merchant hijau kita di lapangan, punya **tepat 6 pengamat**.
Pertahanan yang harganya data lapangan sendiri itu bukan pertahanan.

**Yang dilakukan: memisahkan angka yang bisa dikarang dari yang tidak.**

Perumpamaannya **tanda tangan vs materai**. Tanda tangan bisa ditiru
siapa saja. Materai harus dibeli dari negara. Dua-duanya ada di
dokumen, tapi bobotnya beda — dan selama ini kita menampilkan keduanya
sebagai angka yang sama.

Sekarang ada dua angka terpisah:

| angka | bisa dikarang penyerang? |
|---|---|
| `observers` — total HP berbeda | **bisa** |
| `vouched_observers` — yang **dijamin PJP** | **tidak bisa** |

"Dijamin" artinya HP-nya sudah diperiksa PJP (lewat Play Integrity /
App Attest) **dan** permintaannya datang dengan kunci API mereka.
Syaratnya **dua-duanya**. Penipu anonim yang aplikasinya mengaku *"HP
saya asli kok"* **tidak dihitung** — itu cuma klaim penipu soal dirinya
sendiri.

**Hasilnya, serangan yang sama sekarang ketahuan dasarnya:**

```
putusan : VERIFIED / proceed

  - Konsisten dengan 3 pengamatan sebelumnya di lokasi ini
  - Reputasi lokasi ini dibangun dari pemindaian anonim — tidak ada
    pengamat yang dijamin penyelenggara pembayaran

evidence: { observers: 3, vouched_observers: 0,
            registered: false, established: true, span_hours: 25.0 }
```

Sebelum ini, "hijau" yang berdiri di atas 3 scan anonim terbaca **sama
persis** dengan "hijau" yang berdiri di atas 50 scan yang dijamin PJP.
Sekarang tidak lagi.

**Penting: ini pengungkapan, bukan hukuman.** Skornya tetap 0, lampunya
tetap hijau. Yang berubah cuma sistem berhenti menyembunyikan **kualitas
buktinya sendiri**. Ada test khusus yang memastikan angka-angka baru ini
tidak pernah diam-diam menggeser putusan.

**Kenapa berhenti di situ, tidak ditutup total?** Karena penutupannya
**bukan milik kita** — butuh pengamat yang dijamin PJP, dan itu artinya
integrasi dengan DANA/GoPay. Yang bisa kita lakukan hari ini: berhenti
mengklaim lebih dari yang didukung bukti, dan serahkan angkanya ke PJP
untuk kebijakan mereka.

Buat juri keamanan, ini justru jawaban paling kuat: *"Kami tahu batas
kepercayaan kami, kami ukur harganya, dan sistem kami tidak
menyembunyikannya."*

---

### 4.4 Data demo yang berbohong ke tim sendiri

**Ceritanya.** Ini ketemu bukan dari test yang gagal, tapi dari memeriksa
data produksi sebelum mengubah sesuatu.

`seed.py` adalah skrip yang mengisi database demo. Ternyata dia menulis
*"merchant ini punya 149 pengamat"* ke satu baris — **tanpa pernah
membuat catatan pengamatannya.** Merchant demo utama kita: **149
pengamat, nol jejak.**

Selama ini tidak kelihatan karena tidak ada yang membaca jejaknya.
Begitu fitur-fitur baru semalam mulai membacanya, ketiganya melaporkan
kekosongan — untuk merchant yang di layar justru tampak paling mapan.

**Kenapa ini diperbaiki padahal bukan soal keamanan.** Data demo yang
tidak konsisten dengan dirinya sendiri **lebih berbahaya** daripada
tidak ada data demo: ia berbohong ke tim sendiri. Kalau juri membuka
angka merchant paling meyakinkan di panggung dan menemukan sesuatu yang
mustahil, yang runtuh bukan satu fitur — tapi kepercayaan pada **semua**
angka yang kita sebutkan.

**Diperbaiki**, plus satu bug lain yang ikut ketahuan (data lama
menggantung tiap kali seed diulang).

**Bonusnya bagus banget buat demo.** Fixture sebaran stiker sekarang
memicu alarmnya lewat jalur yang lebih kuat:

```
sebelum : "terdeteksi di 4 area berbeda, terjauh 567 km"
sesudah : "terlihat di dua tempat berjarak 567 km hanya terpaut
           0 menit — tidak ada pedagang yang bisa berpindah secepat itu"
```

Demonya berhenti memperagakan **aturan**, dan mulai memperagakan
**bukti**.

---

## 5. Satu rencana yang sengaja DIBATALKAN

Kami sempat mau mengganti syarat umur jangkar dari "rentang 24 jam" jadi
"hadir di 3 hari berbeda". Logikanya: penipu harus balik ke lokasi 3
kali, capek.

Dicek dulu ke data produksi — **Es Kelapa aman** (4 hari berbeda).

**Tapi dibatalkan.** Alasannya lebih penting daripada hasil
pemeriksaannya: **koordinat dikirim aplikasi dan tidak bisa kami
verifikasi.** Penipu tidak perlu berada di lokasi sama sekali. "3 hari
berbeda" baginya artinya: 3 klik dari laptop, dijeda 3 hari.

Ongkos serangan naik dari 25 jam jadi 3 hari. **Itu penundaan, bukan
pertahanan** — sementara harganya adalah menjatuhkan seluruh data demo.

Dicatat sebagai **R23**, supaya tidak ada yang mengulang rencana ini
nanti dan mengira dia menemukan sesuatu.

---

## 6. Hal-hal yang wajib diingat di lapangan

> ### ⚠️ Jangan scan QR Es Kelapa dari Bandung dengan GPS hidup
>
> Termasuk waktu gladi bersih. Bandung–Jakarta Selatan jelas lebih dari
> 1 km, jadi itu bikin **jangkar hantu** dan merchant hijau satu-satunya
> kita rusak **permanen**. Pakai mode replay di Setelan.
>
> Es Kelapa sudah punya satu jangkar hantu (836 m). Itu masih di bawah
> ambang 1 km jadi aman — tapi satu lagi yang lebih jauh berakibat fatal.

**Mode replay** ada di scanner web: **Setelan → Sumber lokasi →
`replay`**, lalu isi koordinat aslinya:

```
Lintang : -6.168580
Bujur   : 106.872458
```

Hasilnya hijau, dan tanggapannya **mengaku sendiri** bahwa koordinatnya
diputar ulang. Tunjukkan itu ke juri — jangan disembunyikan.

---

## 7. Kalau juri nanya — contekan

**"Kok merchant keliling nggak bisa hijau?"**
> Karena kami memverifikasi penempatan, dan pedagang keliling memang
> tidak punya penempatan tetap. Kami tidak menuduhnya — kami bilang
> tidak tahu. Hijau penuh lewat pendaftaran penyelenggara.

**"Konsensus kalian bisa dipalsukan dong?"**
> Bisa, dan kami sudah mengukur ongkosnya: tiga identitas karangan dan
> kesabaran 24 jam. Karena itu sejak versi ini setiap putusan membawa
> `vouched_observers` — jumlah pengamat yang dijamin penyelenggara.
> Reputasi yang seluruhnya anonim tidak lagi terbaca sama dengan yang
> dijamin. Penutupan penuhnya butuh integrasi PJP, dan kami tidak
> berpura-pura sudah punya.

**"Kenapa nggak pakai model yang dilatih?"**
> Kami uji jalur itu: enam belas ciri payload. Dua belas di antaranya
> ciri struktural — cara QR dibangun — dan **nol** yang berbeda, karena
> stiker penipu memang diterbitkan penyelenggara sungguhan. Empat
> sisanya menggambarkan jenis usahanya, dan itu diisi penipu sendiri
> saat mendaftar; yang teliti tinggal mencocokkannya, lalu selisihnya
> nol seluruhnya. Penipuannya ada di penempatan, dan penempatan tidak
> terekam di payload.
>
> Bisa kami jalankan sekarang: `scripts/enam_belas_ciri.py`.

**"Ini machine learning atau aturan?"**
> Keduanya, dan urutannya penting: **belajar tanpa label, memutuskan
> secara deterministik.** Pengetahuannya dipelajari dari data tanpa
> label — itu bagian ML-nya. Keputusannya deterministik di atas
> pengetahuan itu — itu yang membuat tiap putusan bisa dijelaskan ke
> pengguna, auditor, dan regulator.

---

## 8. Angka-angka penting, satu tempat

| Angka | Nilai | Artinya |
|---|---|---|
| Pengamat minimum | 3 HP berbeda | sebelum jangkar dianggap nyata |
| Umur minimum | 24 jam | rentang scan pertama ke terakhir |
| Radius jangkar | 50 m | sejauh mana masih dianggap "tempat yang sama" |
| Batas kecepatan | 80 km/jam | di atas ini bukan pedagang pindah, tapi dua stiker |
| Batas rentang | 80 km | di atas ini bukan pedagang keliling |
| Jarak "area beda" | 1 km | di bawah ini dianggap tempat yang sama |
| Positif palsu model kelangkaan | 4,1% | diukur ke 122 merchant sungguhan |
| Merchant terkumpul | 122 | dari 10 penerbit, 5 sudah cukup tebal |

---

## 9. Kondisi proyek setelah semalam

```
16 berkas test lolos, 27 skenario baru
commit  97571b3 di branch feat/pembayaran-jarak-jauh-keliling-konsensus
dokumen Keputusan 79-82, risiko R20-R23, koreksi R4 & R6
kontrak API aman — semuanya tambahan, tidak ada yang dipecah
```

**Dua langkah yang menunggu:**

```bash
git checkout main && git merge --ff-only feat/pembayaran-jarak-jauh-keliling-konsensus
fly deploy --remote-only
```

**Sisa pekerjaan:**

1. **RESTORASI MESJID butuh 2 pengamat lagi + rentang 24 jam** — ini
   yang paling berharga, biar punya merchant hijau kedua buat demo
2. Input "pilih dari galeri" di scanner web — backend-nya sudah siap
3. Perbarui berkas sumber PDF pakai `docs/pitch/PDF-UPDATE.md`

---

## Satu hal yang layak dibanggakan

Empat temuan semalam **semuanya berawal dari pertanyaan anggota tim**,
bukan dari daftar fitur. Dua di antaranya bahkan menemukan bahwa aturan
yang sudah lama berdiri ternyata **tidak pernah menangkap penipu sama
sekali** — cuma menuduh orang jujur.

Menemukan itu di kamar sendiri jauh lebih enak daripada ditemukan juri
di atas panggung. 🙂
