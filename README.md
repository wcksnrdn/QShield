# Q-Shield — PoC

Verifikasi kepercayaan QRIS sebelum PIN entry, dua lapis:

- **Layer 1 — ikatan merchant-lokasi.** Apakah merchant ini memang yang
  seharusnya ada di lokasi ini.
- **Layer 2 — perilaku artefak QR.** Apakah kode yang barusan dipindai
  berperilaku seperti QR yang sah.

Keduanya bisa gagal sendiri-sendiri, jadi Layer 2 **melengkapi**, bukan
menggantikan, putusan Layer 1. Aturan komposisinya ada di
`binding.compose()` dan dicatat sebagai Keputusan 10 di `PROCESS-LOG.md`.

## Menjalankan

### 1. Persiapan Awal (Sekali Saja)

```bash
# Buat dan aktifkan virtual environment
python3 -m venv .venv && source .venv/bin/activate

# Install dependencies dan package qshield (editable)
pip install -e .

# (Opsional) Jika butuh membuat/mencetak prop QR fisik (OpenCV & QRCode):
# pip install -e ".[props]"
```

### 2. Generate Sertifikat HTTPS Lokal & Seed Database

Kamera (`getUserMedia`) dan GPS (`navigator.geolocation`) **menuntut secure context (HTTPS)** agar browser di HP mengizinkan akses.

```bash
# Buat sertifikat SSL self-signed lokal untuk IP LAN laptop
python3 scripts/make_cert.py

# Seed database dengan koordinat demo/venue
rm -f qshield.db
python3 scripts/seed.py $(python3 scripts/venue_fixture.py coords)
```

### 3. Menjalankan Server

#### Mode Demo Lokal (Rekomendasi untuk Pengujian Cepat):
Autentikasi dimatikan (`QSHIELD_AUTH=off`) sehingga scanner di HP dapat langsung memindai tanpa memasukkan API key:

```bash
QSHIELD_AUTH=off uvicorn qshield.api:app --host 0.0.0.0 --port 8000 \
    --ssl-certfile certs/cert.pem \
    --ssl-keyfile certs/key.pem
```

#### Mode Dengan Kunci API (PJP):
```bash
# Buat API key baru (hanya jika belum punya):
# python3 scripts/make_apikey.py pjp-demo

QSHIELD_API_KEYS="pjp-demo:4aaaac1c73f6e64bda1a431d945645367ee9aef1eab5929e6f4dde4e6fce45ba" \
uvicorn qshield.api:app --host 0.0.0.0 --port 8000 \
    --ssl-certfile certs/cert.pem \
    --ssl-keyfile certs/key.pem
```

### 4. Akses Scanner & Dokumentasi

- **Dari HP (satu WiFi dengan laptop)**: Buka `https://<ip-laptop>:8000/`. Terima peringatan sertifikat self-signed di browser HP.
- **Dari Laptop**: Buka `https://localhost:8000/` (atau `http://localhost:8000/` jika dijalankan tanpa SSL).
- **Dokumentasi Interaktif (Swagger UI)**: `https://localhost:8000/docs`

Pindah WiFi berarti IP berubah; jalankan ulang `python3 scripts/make_cert.py`. `python3 scripts/preflight.py` memeriksa kesiapan sistem sebelum demo.

## Menguji

```bash
python3 tests/test_emvco.py
python3 tests/test_geo.py
python3 tests/test_binding.py
python3 tests/test_invariants.py               # kunci regresi kedelapan invarian
python3 tests/test_adversarial.py              # 13 skenario dari sisi penyerang
python3 tests/test_hardening.py                # input, auth, rate limit, audit, konkurensi
python3 tests/test_contract.py                 # kunci bentuk API v1
python3 tests/test_frontend.py                 # kecocokan halaman dengan API
python3 tests/test_registration.py             # pendaftaran merchant + penyalahgunaannya
python3 tests/test_transfer.py                 # Layer 2 jalur transfer manual
PYTHONPATH=scripts python3 tests/test_api.py   # test_api.py mengimpor scripts/seed.py

python3 scripts/calibrate_geo.py               # kalibrasi presisi geohash
python3 scripts/calibrate_layer2.py            # kalibrasi konstanta Layer 2
```

`test_invariants.py` keluar dengan status bukan-nol kalau ada satu invarian
yang jebol — jalankan itu sebelum commit apa pun yang menyentuh penilaian.

## Struktur

```
src/qshield/     package utama — import sebagai `qshield` setelah `pip install -e .`
  emvco.py         parser payload QRIS (EMVCo TLV) + CRC16
  geo.py           geohash encode/decode, tetangga, haversine
  binding.py       Layer 1 — konsensus lokasi, plus aturan komposisi
  behavior.py      Layer 2 — sinyal struktural & perilaku artefak QR
  transfer.py      Layer 2 jalur transfer manual
  store.py         persistensi SQLite
  auth.py          autentikasi klien PJP (kunci disimpan sebagai hash)
  limits.py        pembatasan laju (memori, tanpa menyimpan IP)
  audit.py         jejak audit terstruktur tanpa PII
  api.py           endpoint FastAPI
  web/index.html   scanner — satu berkas, tanpa build step
scripts/         skrip yang dijalankan langsung, bukan bagian dari package
  seed.py             isi data demo, cetak QR asli & palsu
  make_qr.py          cetak prop QR + verifikasi keterbacaan (OpenCV)
  venue_fixture.py    rekam koordinat venue, putar ulang naskah demo
  make_apikey.py      terbitkan kunci API untuk satu PJP
  make_cert.py        sertifikat HTTPS lokal (wajib untuk demo dari HP)
  preflight.py        pemeriksaan kesiapan sebelum demo
  calibrate_geo.py    kalibrasi presisi geohash
  calibrate_layer2.py kalibrasi konstanta Layer 2
  calibrate_anchor.py kalibrasi penghalusan jangkar
  calibrate_dynamic.py kalibrasi deteksi QR dinamis dipakai ulang
  calibrate_decay.py  kalibrasi peluruhan jejak serangan
  fieldkit.py         kumpulkan & analisis data lapangan
  diagnose.py         bongkar kenapa satu pemindaian berakhir begitu
tests/           test_*.py — dijalankan langsung (bukan lewat pytest)
```

`pip install -e .` membuat `qshield` importable dari mana saja di dalam
venv ini (dipakai oleh `uvicorn qshield.api:app`, `tests/`, dan
`scripts/`), tanpa perlu `PYTHONPATH` manual — kecuali `test_api.py`,
yang juga mengimpor `scripts/seed.py` secara langsung.

## Dokumen

| Berkas | Isi |
|---|---|
| `PROCESS-LOG.md` | keputusan desain, temuan, dan alasannya |
| `THREAT-MODEL.md` | batas kepercayaan, ancaman, mitigasi + bukti testnya |
| `API.md` | kontrak API v1 dan kebijakan versinya |
| `DEPLOY.md` | rencana migrasi Postgres, secrets, container |
| `INTEGRATION.md` | panduan integrasi untuk PJP, termasuk slot integritas perangkat |
| `PDF-UPDATE.md` | teks pengganti untuk Q-Shield-Overview.pdf yang sudah basi |
| `PITCH-PJP.md` | alasan bisnis untuk PJP + panduan pendekatan dari nol |
| `KLARIFIKASI-ML.md` | koreksi istilah ML untuk panitia, plus panduan kapan perlu dikirim |
| `PITCH-AUDIT.md` | audit naskah pitch ke kode + naskah pengganti |

## Sebelum demo

```bash
python3 scripts/preflight.py
```

Memeriksa konfigurasi, basis data, kecocokan jangkar dengan koordinat
venue, prop tercetak, putusan API, dan seluruh suite. Keluar bukan-nol
kalau ada yang belum siap.

## Troubleshooting: `ModuleNotFoundError: No module named 'qshield'`

Proyek ini ada di `~/Documents`, yang di macOS biasanya disinkron iCloud
Drive. iCloud kadang diam-diam nge-flag file
`.venv/lib/python*/site-packages/__editable__.qshield-*.pth` (dibuat oleh
`pip install -e .`) sebagai **hidden**, dan Python 3.14 melewati file
`.pth` yang hidden tanpa pesan error — jadi `import qshield` gagal walau
sudah ter-install, dan bisa berulang meski sudah pernah "sembuh".

Sudah ditambal secara permanen: `.venv/bin/activate` mengisi
`PYTHONPATH` ke `src/` setiap kali di-source, jadi tidak lagi bergantung
pada file `.pth` itu sama sekali. Kalau bikin ulang `.venv` dari nol dan
error ini muncul lagi, cek dulu:

```bash
echo $PYTHONPATH   # harus mengandung .../src setelah `source .venv/bin/activate`
```

Kalau venv memang dibuat ulang, tambal manualnya:
```bash
chflags nohidden .venv/lib/python*/site-packages/__editable__.qshield-*.pth
```
— tapi ini tidak permanen selama proyek masih di folder yang disinkron
iCloud. Solusi paling tuntas: pindahkan proyek ke folder yang tidak
disinkron iCloud (mis. di luar `~/Documents`/`~/Desktop`).

## Prop fisik untuk demo

```bash
pip install -e '.[props]'                     # qrcode, pillow, opencv
python3 scripts/make_qr.py -6.2088 106.8456    # koordinat SAMA dengan seed.py
python3 scripts/make_qr.py --calibrate         # sapu ulang parameter cetak
```

Mencetak empat skenario ke `props/` lalu memverifikasi tiap berkas lewat
OpenCV dalam sembilan kondisi — diperkecil, diburamkan, dimiringkan,
diredupkan, diberi derau. Jangan cetak apa pun yang belum berstatus `SIAP`.

## Jalur cadangan demo (GPS indoor)

GPS di dalam gedung kerap melaporkan akurasi >100 m, dan invarian §6 akan
menolak memberi putusan — sistemnya benar, tapi demonya mati. Siapkan
rekamannya **sebelum** hari-H, jangan panik di lokasi.

```bash
# PAGI, DI LUAR GEDUNG, berdiri persis di titik demo
python3 scripts/venue_fixture.py record -6.9147 107.6098 --accuracy 8

# seed dan prop pakai koordinat yang SAMA
python3 scripts/seed.py    $(python3 scripts/venue_fixture.py coords)
python3 scripts/make_qr.py $(python3 scripts/venue_fixture.py coords)

# gladi bersih / fallback saat GPS ruangan payah
python3 scripts/venue_fixture.py replay
python3 scripts/demo_lintas_pjp.py             # peragaan berbagi data antar-PJP
```

Yang diputar ulang ditandai eksplisit sebagai replay — di permintaan
(`location_source`), di tanggapan, di alasan paling depan, dan di jejak
audit. Penilaiannya tidak berubah sedikit pun, dan mode ini tidak bisa
dipakai membobol invarian akurasi GPS (diuji di `test_hardening.py`).
Sampaikan terus terang ke juri: menolak memberi putusan saat sinyal buruk
memang fitur, bukan bug.

## Kalau hasilnya tidak sesuai harapan

```bash
python3 scripts/diagnose.py PAYLOAD LAT LNG [AKURASI]   # bongkar satu pemindaian
python3 scripts/diagnose.py --anchor LAT LNG            # apa isi jangkar di titik itu
```

Membongkar tiap sinyal beserta bobot dan alasannya, lalu menjelaskan
kenapa putusannya bukan `proceed`.

> **Kebersihan demo.** Jangan memindai prop palsu (`02-swap.png`) di
> tempat yang sama dengan QRIS sungguhan. Pemindaian yang ditolak
> mencatat percobaan anomali pada jangkar itu, dan tiap merchant baru di
> titik itu ikut kena sampai jejaknya pudar. Pisahkan lokasinya, atau
> reset dulu:
>
> ```bash
> rm -f qshield.db*
> python3 scripts/seed.py $(python3 scripts/venue_fixture.py coords)
> ```

## Kalibrasi lapangan

Hampir semua parameter masih bertanda "titik awal demo". Menutupnya
menuntut data nyata:

```bash
QSHIELD_FIELD_MODE=on QSHIELD_AUTH=off \
  uvicorn qshield.api:app --host 0.0.0.0 --port 8000 \
    --ssl-certfile certs/cert.pem --ssl-keyfile certs/key.pem
```

Buka scanner dari HP, nyalakan **Mode survei** di setelan, isi label
lokasi, lalu berkeliling memindai QRIS sungguhan. Label SAMA untuk
pemindaian berulang di merchant yang sama; label BERBEDA untuk merchant
berbeda walau bersebelahan.

```bash
python3 scripts/fieldkit.py status      # berapa data terkumpul, apa yang kurang
python3 scripts/fieldkit.py analyse     # turunkan parameternya
```

> **Mode survei menyimpan payload mentah dan koordinat presisi** — persis
> dua hal yang model privasi sistem ini sengaja tidak simpan. Ia mati
> secara bawaan, tetap menuntut kunci API, dan diteriakkan sebagai
> BAHAYA saat start. Jangan pernah menyalakannya di lingkungan yang
> melayani pengguna sungguhan.

## Konfigurasi

Semua lewat env var, semuanya punya nilai bawaan yang aman:

| Variabel | Bawaan | Guna |
|---|---|---|
| `QSHIELD_API_KEYS` | *(kosong)* | `client_id:sha256` dipisah koma; kosong = endpoint verifikasi menolak melayani |
| `QSHIELD_AUTH` | *(kosong)* | `off` mematikan autentikasi, untuk demo lokal |
| `QSHIELD_ALLOWED_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | daftar origin CORS |
| `QSHIELD_RATE_LIMIT` | `60` | permintaan per jendela; `off` mematikan |
| `QSHIELD_RATE_WINDOW` | `60` | panjang jendela (detik) |
| `QSHIELD_LOG_LEVEL` | `INFO` | level audit log |
| `QSHIELD_VENUE_FIXTURE` | `venue.json` | berkas rekaman koordinat |
| `QSHIELD_FIELD_MODE` | *(kosong)* | `on` membuka endpoint survei kalibrasi |
| `QSHIELD_FIELD_FILE` | `fielddata.jsonl` | berkas hasil survei |
| `QSHIELD_DEVICE_SALT` | *(dibangkitkan sekali, disimpan di basis data)* | garam untuk `device_ref`; harus stabil — mengubahnya membuat pengamat lama terhitung ulang |

Di WiFi acara yang ber-NAT seluruh ruangan terlihat sebagai satu alamat —
kalau rate limit mulai menolak permintaan sah saat gladi bersih, jalankan
dengan `QSHIELD_RATE_LIMIT=off`.

## Autentikasi klien

Klien Q-Shield adalah **PJP**, bukan orang. Satu kunci mewakili satu
penyelenggara yang memanggil API sebelum PIN entry.

```bash
python3 scripts/make_apikey.py pjp-alpha     # cetak kunci + baris env
export QSHIELD_API_KEYS="pjp-alpha:<sha256>"
```

Klien menyertakannya sebagai header:

```
X-API-Key: <kunci mentah>
```

Tiga sifat yang disengaja:

- **Gagal tertutup.** Kalau `QSHIELD_API_KEYS` kosong dan `QSHIELD_AUTH`
  tidak disetel `off`, endpoint verifikasi mengembalikan `503`, bukan
  melayani tanpa autentikasi. Ketiadaan konfigurasi bukan izin — logika
  yang sama dengan invarian §2.
- **Kunci disimpan sebagai hash.** Konfigurasi yang bocor tidak langsung
  memberi penyerang kunci yang bisa dipakai, dan kunci mentah tidak
  pernah masuk log — bahkan saat autentikasi gagal.
- **Kuota dihitung per klien, bukan per IP.** Ini yang menutup batasan R8:
  di balik NAT seluruh ruangan berbagi satu alamat.

Untuk demo lokal jalankan dengan `QSHIELD_AUTH=off`.

## Endpoint

Kontrak lengkap beserta kebijakan versinya ada di [`API.md`](API.md),
dan dikunci oleh `tests/test_contract.py`.

```
GET    /api/v1/health
POST   /api/v1/verify
POST   /api/v1/merchants           daftarkan ikatan merchant-lokasi
DELETE /api/v1/merchants/{nmid}    cabut pendaftaran
```

Semua kecuali `/health` menuntut header `X-API-Key`. Daftar putih, bukan
daftar hitam — endpoint baru tertutup secara bawaan.

Seluruh field **wajib**. `accuracy_m` khususnya: tanpa tahu seberapa
bagus fix GPS-nya, jangkar tidak bisa dinilai sama sekali — dan kalau
field itu opsional, penyerang yang akurasinya buruk tinggal tidak
mengirimkannya untuk melewati invarian §6.

Contoh permintaan:

```json
{
  "payload": "00020101021126660014ID.CO.QRIS.WWW...",
  "lat": -6.914744,
  "lng": 107.609810,
  "device_anon_id": "uuid-v4",
  "accuracy_m": 12
}
```

Contoh tanggapan:

```json
{
  "verdict": "anomaly",
  "action": "cooling_off",
  "risk_score": 83,
  "reasons": [
    "Merchant ID berbeda dari 47 pengamatan sebelumnya di lokasi ini"
  ],
  "signals": ["nmid_changed_at_anchor"],
  "layers": { "location": 83, "behavior": 0 },
  "processing_ms": 2.8
}
```

`layers` memisahkan sumbangan tiap lapisan supaya bisa ditelusuri dari mana
skornya datang — `location` untuk Layer 1, `behavior` untuk Layer 2.
