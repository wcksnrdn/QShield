# Klarifikasi istilah teknis — Q-Shield

> **Sebelum mengirim ini, baca bagian "Kapan ini perlu dikirim" di
> bagian akhir.** Kalau materi POC kalian tidak pernah menuliskan
> "machine learning" secara eksplisit, dokumen ini tidak perlu dikirim
> sama sekali — cukup dipakai menyamakan bahasa di dalam tim.

---

## Surat klarifikasi

Kepada Panitia Telkom University × Kaspersky
Track: Secure Digital Payments & Fintech
Tim: Q-Shield — Satria Ardan Wicaksono, Vyone Louis, Filbert Alfredo Saputro

**Perihal: koreksi istilah pada dokumen Proof of Concept**

Kami menyampaikan koreksi atas satu istilah teknis dalam materi POC
kami. Pada dokumen tersebut, mekanisme penilaian Q-Shield kami sebut
sebagai *machine learning*. Istilah itu tidak tepat, dan kami ingin
meluruskannya sebelum presentasi final agar tidak ada penilaian yang
didasarkan pada gambaran yang keliru.

### Yang sebenarnya berjalan

Q-Shield **tidak memakai model yang dilatih** (classifier, jaringan
saraf, atau sejenisnya). Sistemnya memakai aturan deterministik yang
bekerja di atas **pengetahuan yang dibentuk dari data pengamatan**.

Enam komponen sistem ini memang belajar dari data, bukan ditanam
sebagai nilai tetap:

| Komponen | Yang dipelajari |
|---|---|
| Konsensus pengamat | reputasi sebuah lokasi terbentuk dari pengamatan banyak perangkat independen |
| Penghalusan jangkar | koordinat lokasi menajam seiring bertambahnya pengamatan — galat turun dari 6,9 m menjadi 1,3 m pada 47 pengamatan |
| Pengetahuan wilayah | kota yang berlaku di suatu wilayah disimpulkan dari merchant di sekitarnya, tidak ditanam sebagai tabel |
| Dialek penerbit | ciri penyusunan payload tiap penyelenggara disimpulkan dari korpus payload |
| Jejak percobaan serangan | riwayat per lokasi, dengan peluruhan waktu |
| Jejak QR dinamis | sebaran dan pemakaian ulang per artefak |

Istilah yang tepat untuk ini adalah **statistical learning dari
pengamatan**, bukan *machine learning* dalam pengertian model terlatih.
Penggunaan istilah yang longgar itu kesalahan kami.

### Mengapa kami tidak memakai model terlatih

Ini keputusan yang diambil setelah diuji, bukan karena keterbatasan
waktu atau kemampuan.

**Pertama, tidak ada sinyal yang bisa dipelajari dari payload.** Kami
mengekstrak enam belas ciri dari payload QRIS — panjang, jumlah dan
urutan field, validitas serta gaya penulisan checksum, GUID
penyelenggara, panjang dan prefiks nomor akun, format Merchant ID,
kriteria usaha, kode kategori merchant, mata uang, kode negara, tipe
statis/dinamis, keberadaan nominal, dan panjang nama merchant — lalu
membandingkannya antara stiker asli dan stiker pengganti pada skenario
sticker-swap.

> **Nol dari enam belas ciri berbeda.**

Sebabnya bersifat mendasar: pelaku sticker-swap tidak memalsukan QR. Ia
mendaftarkan akun merchant sungguhan pada penyelenggara sungguhan,
menerima stiker yang diterbitkan resmi, lalu menempelkannya menutupi
stiker merchant lain. Payload-nya memang sah. Model yang dilatih
mengenali "pola QRIS asli" akan mengklasifikasikannya sebagai asli —
karena memang asli.

Penipuannya tidak berada di dalam kode, melainkan pada **penempatannya**
— dan penempatan tidak terekam di payload. Itu justru temuan yang
mendasari seluruh arsitektur Q-Shield.

**Kedua, tidak tersedia data latih.** Classifier memerlukan dua kelas.
Jumlah sampel stiker penipuan sungguhan yang terkonfirmasi yang kami
miliki adalah nol. Model yang dilatih pada data yang kami bangkitkan
sendiri hanya akan belajar mengenali generator kami sendiri.

**Ketiga, auditabilitas.** Sistem pembayaran tunduk pada pengawasan
regulator dan audit internal penyelenggara. Aturan deterministik dapat
menjawab pertanyaan "mengapa keputusan ini diambil" dengan kalimat yang
dapat diverifikasi; model terlatih menjawabnya dengan angka yang tidak
dapat ditelusuri. Untuk domain ini, sifat deterministik adalah
keunggulan, bukan kompromi.

### Yang tidak berubah

Koreksi ini menyangkut istilah, bukan fungsi. Seluruh kemampuan yang
kami sampaikan pada POC berjalan sebagaimana dijelaskan, dan dapat
diverifikasi langsung dengan menjalankan pengujiannya.

### Penutup

Kami menyampaikan koreksi ini atas inisiatif sendiri karena kami menilai
ketepatan istilah adalah bagian dari kualitas pekerjaan, terlebih pada
track keamanan. Kami siap menjelaskan lebih lanjut pada sesi presentasi.

Hormat kami,
Tim Q-Shield

---

## Versi pendek, untuk disampaikan lisan

Kalau ada yang menanyakannya di sesi tanya jawab:

> Di dokumen awal kami menyebutnya machine learning, dan itu istilah
> yang kami pakai terlalu longgar. Yang tepat: statistical learning dari
> pengamatan, bukan model yang dilatih.
>
> Sistemnya memang belajar — pengetahuan wilayah dan dialek penerbit
> dibentuk dari data, bukan ditanam di kode. Yang tidak ada adalah
> classifier terlatih, dan itu keputusan sadar.
>
> Kami menguji jalur itu: enam belas ciri payload, nol yang berbeda
> antara stiker asli dan stiker penipu — karena stiker penipu memang
> diterbitkan penyelenggara sungguhan. Tidak ada yang bisa dipelajari di
> sana. Kami memilih aturan deterministik karena tiap putusan bisa
> dijelaskan ke pengguna, auditor, dan regulator.

Sampaikan tanpa nada meminta maaf berlebihan. Ini bukan kegagalan —
ini menunjukkan kalian menguji jalan yang lebih mudah dan menolaknya
dengan alasan.

---

## Kapan ini perlu dikirim

**Kirim**, kalau materi POC kalian menuliskan secara eksplisit:
"machine learning", "model ML", "dilatih", "AI", atau sejenisnya.
Semakin cepat semakin baik — koreksi yang datang dari kalian sendiri
dibaca sebagai ketelitian; koreksi yang keluar dari pertanyaan juri
dibaca sebagai ketahuan.

**Tidak perlu dikirim**, kalau yang tertulis hanya "sistem adaptif",
"belajar dari data", "behavioral scoring", atau "risk scoring". Semua
itu masih akurat. Mengirim koreksi formal untuk sesuatu yang tidak
keliru justru menciptakan masalah yang tadinya tidak ada — cukup pakai
dokumen ini untuk menyamakan bahasa di dalam tim.

**Yang wajib dilakukan apa pun keputusannya:**

1. Periksa apa yang persis tertulis di berkas POC kalian.
2. Hapus istilah ML dari seluruh materi pitch yang masih memuatnya.
3. Sepakati satu istilah untuk bertiga. Jangan sampai satu orang
   menyebut ML dan yang lain menyebut deterministik di sesi yang sama —
   itu lebih merusak daripada kesalahan istilahnya sendiri.

## Sebelum mengirim

- [ ] Ganti nama tim dan anggota bila perlu penyesuaian
- [ ] Sesuaikan sapaan dengan format resmi panitia
- [ ] Pastikan tidak ada materi lain yang masih menyebut ML
- [ ] Baca sekali lagi dengan lantang — kalau terdengar seperti minta
      maaf, potong bagian itu
