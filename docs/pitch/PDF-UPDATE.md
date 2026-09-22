# Teks pengganti untuk Q-Shield-Overview.pdf

Berkas sumber PDF tidak ada di repo, jadi ini bukan tambalan otomatis —
ini teks siap tempel. Cari kalimat lamanya di dokumen sumber kalian
(Canva/Figma/Docs), ganti dengan yang baru.

Angka di sini diambil dari kode dan pengujian yang berjalan hari ini,
bukan dari ingatan. Kalau kalian mengubah sesuatu setelah ini, ukur
ulang sebelum menyalin.

---

## 1. Halaman 4 — berkas pengujian

**Lama:**

> Empat berkas pengujian (`test_emvco.py`, `test_geo.py`,
> `test_binding.py`, `test_api.py`) mencakup parser payload, geohash &
> jarak, 13 skenario konsensus (termasuk kasus ruko dan relokasi
> merchant), serta alur end-to-end lewat API sungguhan.

**Baru:**

> Sebelas berkas pengujian mencakup parser payload, geohash & jarak, 17
> skenario konsensus (termasuk ruko, relokasi merchant, pedagang
> bersebelahan, dan pedagang yang pindah dua kali), 36 skenario
> adversarial — enam di antaranya batasan yang diakui belum ditahan,
> diuji agar sistem tetap jujur — 9 invarian yang dikunci regression
> test, kontrak API, integrasi antarmuka, pendaftaran merchant, serta
> pengerasan (validasi masukan, autentikasi klien, pembatasan laju,
> audit tanpa PII, dan konkurensi).

Catatan: angka "13 skenario konsensus" di naskah lama **sudah tidak
benar**. `test_binding.py` kini berisi 17 skenario bernomor, bertambah
empat dari penutupan R11 dan R12.

---

## 2. Halaman 4 — angka besar "13 SKENARIO BINDING DIUJI"

**Lama:** `13` / SKENARIO BINDING DIUJI

**Baru:** `36` / SKENARIO ADVERSARIAL DIUJI

Enam di antaranya adalah batasan yang **diakui belum ditahan**, diuji
justru agar tidak diam-diam berubah jadi klaim aman. Sebutkan itu —
juri keamanan mempercayai angka yang datang bersama batasannya.

---

## 3. Halaman 4 — latensi

**Lama:**

> 200 permintaan berturut-turut lewat SQLite lokal: p50 2,8 ms, p95
> 3,5 ms, maks 22,4 ms — jauh di bawah anggaran 200 ms.

**Baru:**

> 200 permintaan berturut-turut lewat SQLite lokal: p50 2,8 ms, p95
> 3,7 ms, maks 7,5 ms — jauh di bawah anggaran 200 ms. Diuji juga pada
> 200 permintaan **serentak**: nol galat, hitungan pengamat tetap
> konsisten; dan 20 proses paralel: ~3.000 tulis/detik.

Angka p50 hampir tidak berubah meski sistemnya bertambah banyak.
Kalimat konkurensi ditambahkan karena itu pertanyaan yang wajar muncul
dari sisi teknis.

---

## 4. Halaman 4–5 — Layer 2 **(ini yang paling penting)**

**Lama:**

> **Layer 2 — Behavioral scoring untuk transfer manual** *(jangka
> menengah)*
> Q-Shield saat ini menutup jalur QRIS. Modus rekayasa sosial lewat
> transfer bank manual masih berupa rancangan, belum diimplementasikan.

**Baru — pecah jadi dua butir terpisah:**

> **Layer 2 — Penilaian perilaku pada jalur QR** *(selesai)*
> Melengkapi, bukan menggantikan, putusan Layer 1. Empat belas sinyal
> berjalan: kontradiksi struktural terhadap spec EMVCo, dialek penerbit
> yang dipelajari per penyelenggara, pemakaian ulang QR dinamis,
> integritas perangkat yang dilaporkan klien native, serta agregat
> percobaan anomali per jangkar yang memudar seiring waktu. Layer 2
> hanya dapat menaikkan risiko, tidak pernah menurunkannya.

> **Penilaian transfer bank manual** *(jangka menengah)*
> Q-Shield menutup jalur QRIS. Modus rekayasa sosial lewat transfer
> bank manual berada di luar jangkauan lapisan pra-pembayaran — pada
> transfer manual tidak ada artefak yang bisa diperiksa sebelum korban
> menekan kirim, dan menilai rekening tujuan adalah pekerjaan PJP
> dengan data yang tidak kami pegang.

**Alasan pemecahan ini:** dokumen fase 1 memakai istilah "Layer 2"
untuk dua sistem yang berbeda. Yang berbasis jalur QR sudah selesai;
yang berbasis transfer manual bukan sekadar belum dikerjakan, melainkan
memang di luar jangkauan arsitekturnya. Menyebut keduanya dengan satu
nama membuat yang sudah selesai terlihat belum, dan yang di luar
jangkauan terlihat seperti utang.

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
> memasang QR-nya sekaligus. Pendaftaran oleh penyelenggara tetap
> tersedia sebagai jalan cepat.

Ini perubahan yang layak ditonjolkan. Sebelumnya pedagang yang pindah
dua kali dituduh menyebar stiker **secara permanen** — 500 pengamat di
lokasi baru dan lokasi lama berumur sepuluh tahun pun tidak
menyembuhkan. Yang terkena justru segmen inti: pedagang kaki lima,
food truck, pedagang pasar.

---

## 6. Halaman 5 — merchant keliling

**Lama:**

> ...dan merchant keliling (belum ditangani sama sekali, perlu
> penandaan khusus saat pendaftaran).

**Baru:**

> Merchant keliling ditandai saat pendaftaran; ikatan lokasi tidak
> diberlakukan untuknya, dan bindingnya tidak mengklaim titik yang
> disinggahinya.

---

## 7. Halaman 5 — kalibrasi lapangan

**Lama:**

> ...perlu dikalibrasi ulang dari data lapangan sebelum produksi.

**Baru — hanya kalau kalian sudah menjalankan survei:**

> Dikalibrasi dari **N** pemindaian QRIS sungguhan di **M** lokasi
> (`scripts/fieldkit.py`). Parameter yang belum tervalidasi lapangan
> ditandai eksplisit di kode.

**Kalau belum jalan survei, JANGAN diganti.** Kalimat lamanya masih
benar, dan mengklaim kalibrasi yang belum dilakukan adalah kesalahan
yang paling mudah ketahuan saat ditanya ukuran sampelnya.

---

## 7b. Halaman 5 — di dalam ruangan

**Butir baru, tidak ada padanannya di naskah lama:**

> Ketika akurasi GPS jatuh ke ratusan meter — di dalam ruko, basement,
> atau lantai atas — Q-Shield beralih ke sidik jari WiFi di sekitar,
> sehingga tetap bisa menilai apakah sebuah stiker memang milik tempat
> itu. Titik akses lebih sulit dipalsukan daripada koordinat:
> memalsukan GPS cukup satu sakelar di opsi pengembang, memalsukan
> daftar titik akses menuntut kehadiran fisik di jangkauan radio yang
> sama.

Ambangnya dikalibrasi dari sidik jari lapangan sungguhan: tempat yang
sama beririsan 0,66–0,80, tempat berbeda 0,00.

**Yang jangan diklaim:** sidik jari WiFi tidak dipakai MEMBERI izin,
hanya menaikkan kecurigaan. Merchant sah di dalam ruangan tetap
berhenti di `warn`. Sebabnya korpus belum memuat kasus ruko sebelah
yang berbagi titik akses.

---

## 8. Butir baru yang layak ditambahkan

Empat hal ini belum ada di PDF sama sekali dan termasuk bagian
terkuat sekarang:

> **Pendaftaran merchant oleh penyelenggara**
> PJP sudah mengetahui NMID mana milik merchant mana dari data
> onboarding-nya. Memindahkan pengetahuan itu ke Q-Shield menutup
> masalah *cold start*: merchant tidak perlu menunggu tiga pengamat
> independen selama 24 jam. Pendaftaran menghasilkan sinyal yang
> berbeda dari konsensus, sehingga auditor selalu dapat membedakan
> "terverifikasi karena dinyatakan" dari "terverifikasi karena diamati".

> **Deteksi pada pemindaian pertama**
> Kota yang tercantum di stiker dibandingkan dengan kota yang dilaporkan
> merchant-merchant lain di wilayah yang sama. Stiker yang terdaftar di
> kota lain ketahuan pada pemindaian pertama, tanpa riwayat apa pun
> tentang merchant itu.

> **Autentikasi penyelenggara**
> Endpoint verifikasi hanya melayani PJP terdaftar. Kunci disimpan
> sebagai hash, tidak pernah masuk log bahkan saat autentikasi gagal,
> dan sistem gagal tertutup bila belum dikonfigurasi.

> **Privasi yang dibuktikan, bukan diklaim**
> `device_anon_id` tidak pernah disimpan apa adanya; yang masuk basis
> data adalah hash yang dilingkupi per-binding, sehingga baris
> pengamatan tidak dapat dirangkai antar-lokasi menjadi jejak
> perjalanan. Regression test menjalankan tiga serangan perangkaian
> jejak dan ketiganya harus gagal.

---

## Yang TIDAK perlu diubah

Masih akurat apa adanya:

- seluruh Bagian 1–3 (celah yang ditangani, arsitektur, empat tier)
- p50 2,8 ms
- ambang presisi geohash 7 dan angka 81,9%
- argumen privasi (tanpa `user_id`, tanpa koordinat kunjungan)
- keterangan bahwa angka latensi belum diuji pada volume produksi
