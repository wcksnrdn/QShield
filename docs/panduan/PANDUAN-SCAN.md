# Panduan pengumpulan QRIS

Ada **dua jenis pengumpulan** dengan aturan yang berbeda. Mencampurnya
merusak data — itu yang terjadi pada korpus pertama.

| | Korpus payload | Survei lokasi |
|---|---|---|
| Untuk apa | dialek penerbit, sebaran ciri merchant | pengetahuan wilayah |
| Sumber QR | **bebas** — foto, internet, kota mana pun | **wajib** berdiri di tempat merchantnya |
| Berapa lagi | **31 merchant** | **5 merchant per wilayah** |
| Cara masuk | `import_corpus.py` | mode survei di scanner |

---

# BAGIAN 1 — Korpus payload (31 merchant lagi)

Ini yang bisa dikerjakan sambil duduk. QR dari internet, foto teman,
screenshot — semuanya sah, karena yang dipelajari adalah **bentuk
kodenya**, bukan tempatnya.

## Sebelum mulai — satu langkah yang tidak boleh dilewat

**Simpan payload ke berkas teks, bukan hanya ke basis data.**

Korpus pertama hilang karena basis datanya terhapus. Berkas teks tidak
akan hilang, dan bisa diimpor ulang kapan saja — termasuk setelah
parser diperbaiki, seperti yang terjadi dengan bug dua-template.

```bash
touch payloads.txt
```

## Cara mengumpulkan

Satu payload per baris. Awali baris dengan `#` untuk catatan.

```
# dikumpulkan 17 Sep 2026
00020101021126660014ID.CO.QRIS.WWW0118936008990000012345...
00020101021126610014ID.CO.QRIS.WWW0115ID1026542245422...
```

Cara mendapatkan teks payload dari sebuah QR:

- **dari HP**: buka scanner Q-Shield, pindai, lalu salin dari setelan
- **dari gambar di laptop**: aplikasi pembaca QR mana pun yang bisa
  menyalin isinya sebagai teks
- **dari QR yang kalian buat sendiri**: jangan. Itu tidak mengajarkan
  apa pun tentang penerbit sungguhan

## Yang paling berharga dikumpulkan

Bukan jumlahnya saja — **keragamannya**.

| Prioritas | Kenapa |
|---|---|
| **PJP berbeda-beda** | dialek penerbit butuh 5 merchant per PJP. Lima merchant dari satu bank tidak sama nilainya dengan lima dari lima penerbit |
| Jenis usaha berbeda | warung, minimarket, bengkel, klinik, salon — sebaran kategori usaha jadi realistis |
| Skala usaha berbeda | UMI, UKE, UME, UBE |
| QR dinamis | kode dengan nominal terkunci, dari kasir |

Cara mengenali penerbitnya berbeda: lihat 8 digit awal nomor akun di
dalam payload. `93600014`, `93600899`, dan seterusnya — tiap PJP punya
prefiksnya sendiri.

## Memasukkannya

```bash
python3 scripts/import_corpus.py payloads.txt
python3 scripts/import_corpus.py --status
```

`--status` menunjukkan berapa lagi yang kurang. Ulangi sampai model
kelangkaan aktif.

**Yang tidak disentuh perintah ini**: bindings, observations, dan
area_city. Aman dijalankan berapa kali pun.

---

# BAGIAN 2 — Survei lokasi (5 merchant per wilayah)

Ini yang **harus** dilakukan dengan berjalan kaki. Tidak bisa diwakili
gambar.

## Kenapa harus fisik

Pengetahuan wilayah menjawab: *"merchant di sekitar sini menyebut
kotanya apa?"* Memindai QR Samarinda sambil duduk di Jakarta
mengajarkan sistem bahwa merchant di titik Jakarta itu menyebut
Samarinda — bukan sekadar tidak berguna, tapi **salah**, dan kalau
cukup banyak akan menuduh merchant Jakarta sungguhan.

## Sebelum berangkat

```bash
# 1. pastikan basis data bersih dari pemindaian gambar
python3 scripts/import_corpus.py --purge-area --yes

# 2. sertifikat HTTPS untuk IP laptop saat ini
python3 scripts/make_cert.py

# 3. jalankan dengan mode survei
QSHIELD_FIELD_MODE=on QSHIELD_AUTH=off \
  .venv/bin/uvicorn qshield.api:app --host 0.0.0.0 --port 8000 \
    --ssl-certfile certs/cert.pem --ssl-keyfile certs/key.pem
```

Buka `https://<ip-laptop>:8000/` dari HP. Terima peringatan sertifikat
**sekarang**, bukan nanti di lapangan.

Di setelan scanner: **Mode survei → nyala**.

## Saat memindai

1. **Berdiri di depan merchantnya.** Bukan di seberang jalan, bukan
   dari foto.
2. **Isi label lokasi** dengan nama tempatnya. Label SAMA untuk
   pemindaian berulang di merchant yang sama; label BERBEDA untuk
   merchant berbeda, walau bersebelahan.
3. **Tunggu akurasi GPS bagus.** Kalau di bawah naungan atau di dalam
   gedung, keluar dulu sebentar.
4. **Catat NMID yang tercetak** di stikernya, kalau terlihat. Itu yang
   menguji pencocokan teks tercetak.

## Targetnya

Minimal **5 merchant dalam satu wilayah ~5 km** yang sama, supaya
pengetahuan wilayahnya terbentuk. Satu ruko berisi 5 toko sudah cukup.

Lebih baik lagi: 5 merchant di dua atau tiga wilayah berbeda, supaya
bisa diuji bahwa sistem membedakan wilayah.

## Setelah pulang

```bash
python3 scripts/fieldkit.py status
python3 scripts/fieldkit.py analyse
```

`analyse` membandingkan angka terukur dengan konstanta yang dipakai
sekarang, lalu menyebut mana yang perlu digeser.

---

# Aturan kebersihan yang berlaku untuk keduanya

**Jangan memindai prop palsu di tempat yang sama dengan QRIS
sungguhan.** Pemindaian yang ditolak mencatat percobaan anomali pada
jangkar itu. Pisahkan lokasinya, atau reset di antaranya.

**Jangan memindai QR scam ke basis data kerja.** Kalau perlu mengujinya,
pakai basis data terpisah:

```bash
QSHIELD_DB=/tmp/uji.db python3 ...
```

**Payload selalu masuk `payloads.txt` dulu.** Basis data bisa hilang;
berkas teks tidak.

---

# Ringkasan yang harus dilakukan

- [ ] Buat `payloads.txt`
- [ ] Kumpulkan 31 payload lagi, dari **PJP sebanyak mungkin**
- [ ] `python3 scripts/import_corpus.py payloads.txt`
- [ ] `python3 scripts/import_corpus.py --status` sampai korpus 40
- [ ] `--purge-area --yes` sebelum survei fisik
- [ ] Survei 5+ merchant dalam satu wilayah, dengan label
- [ ] `python3 scripts/fieldkit.py analyse`
- [ ] Kabari hasilnya — kalau ada parameter yang perlu digeser, itu
      pekerjaan kalibrasi berikutnya
