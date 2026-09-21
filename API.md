# Q-Shield API v1

**Status:** stabil menuju code freeze 30 September 2026
**Dikunci oleh:** `tests/test_contract.py`

Bentuk API di dokumen ini bukan deskripsi, melainkan **kontrak**.
`test_contract.py` membacanya dari skema OpenAPI yang dihasilkan kode
dan gagal kalau ada yang bergeser — field hilang, wajib berubah jadi
opsional, tipe bergeser, atau nilai enum bertambah diam-diam.

---

## Kebijakan versi

Prefiks `/api/v1/` bukan hiasan. Aturannya:

| Perubahan | Butuh versi baru? |
|---|---|
| Menambah field **opsional** pada permintaan | tidak |
| Menambah field pada tanggapan | tidak — klien wajib mengabaikan yang tidak dikenal |
| Menambah nilai baru pada `signals` atau `reasons` | tidak — keduanya daftar terbuka |
| Menjadikan field permintaan **wajib** | **ya** |
| Menghapus atau mengganti nama field | **ya** |
| Menambah nilai pada `verdict`, `action`, `location_source` | **ya** — kosakata tertutup, klien memetakannya ke UI |
| Mengetatkan batas validasi | **ya** kalau menolak permintaan yang tadinya sah |

`signals` dan `reasons` sengaja **terbuka**: itu tempat sinyal baru
mendarat tanpa memecah klien. `verdict` dan `action` sengaja
**tertutup**: klien memetakannya ke tampilan, dan nilai tak dikenal
membuat mereka tidak tahu harus menampilkan apa.

### Perubahan yang sudah terjadi

| Tanggal | Perubahan | Sifat |
|---|---|---|
| 10 Sep 2026 | `layers` ditambahkan ke tanggapan | aditif |
| 10 Sep 2026 | `location_source` ditambahkan (permintaan opsional + tanggapan) | aditif |
| 10 Sep 2026 | **`accuracy_m` jadi wajib** | **memecah klien** |
| 10 Sep 2026 | `X-API-Key` jadi syarat pada `/verify` | **memecah klien** |
| 11 Sep 2026 | `POST/DELETE /api/v1/merchants` ditambahkan | aditif |
| 11 Sep 2026 | sinyal `registered_merchant`, `nmid_changed_at_registered_anchor`, `mobile_merchant` | aditif — `signals` memang daftar terbuka |
| 21 Sep 2026 | sinyal `malformed_country` (tag 58 cacat bentuk) | aditif — `signals` daftar terbuka |
| 21 Sep 2026 | `fees` ditambahkan ke tanggapan | aditif — klien wajib mengabaikan field tak dikenal |
| 21 Sep 2026 | `include_tlv` (permintaan, opsional, bawaan `false`) + `tlv` (tanggapan) | aditif — bawaannya mati, klien lama tidak terbebani |
| 21 Sep 2026 | `verification_ticket` + `ticket_expires_in` ditambahkan ke tanggapan | aditif — klien yang mengabaikannya tetap berjalan seperti sebelumnya |
| 21 Sep 2026 | `POST /api/v1/tickets/verify` ditambahkan | aditif — endpoint baru tidak memecah klien yang sudah ada |
| 21 Sep 2026 | `payload_fp` ditambahkan ke jejak audit | aditif; bukan kontrak API, tapi mengubah bentuk baris log |

Dua yang terakhir terjadi sebelum ada klien eksternal, jadi versinya
tidak dinaikkan. Setelah code freeze, perubahan sekelas itu menuntut
`/api/v2/`.

---

## Autentikasi

```
X-API-Key: <kunci mentah>
```

Wajib pada `/api/v1/verify`. Terbitkan lewat
`python scripts/make_apikey.py <client_id>`.

| Kode | Arti |
|---|---|
| `401` | kunci tidak valid atau tidak disertakan |
| `503` | server belum dikonfigurasi kunci sama sekali (gagal tertutup) |

Untuk demo lokal, jalankan dengan `QSHIELD_AUTH=off`.

---

## `POST /api/v1/verify`

### Permintaan

| Field | Tipe | Wajib | Batas | Catatan |
|---|---|---|---|---|
| `payload` | string | ya | 8–1024 char, ASCII yang bisa dicetak | string QRIS mentah hasil scan |
| `lat` | number | ya | −90…90 | |
| `lng` | number | ya | −180…180 | |
| `device_anon_id` | string | ya | 8–64 char, `[A-Za-z0-9_-]` | pengenal acak per perangkat, **bukan** identitas pengguna |
| `accuracy_m` | number | ya | 0…100000 | radius keyakinan GPS dalam meter |
| `location_source` | string | tidak | `live` \| `replay` | bawaan `live` |
| `device_integrity` | object | tidak | — | diisi klien **native**; klien web selalu mengosongkannya. Lihat `INTEGRATION.md` §3 |
| `include_tlv` | boolean | tidak | — | bawaan `false`. `true` menyertakan bedah TLV di `tlv` — hampir 4x ukuran tanggapan, jadi opt-in |

`accuracy_m` wajib dengan sengaja. Tanpa tahu seberapa bagus fix-nya,
jangkar tidak bisa dinilai — dan kalau field ini opsional, penyerang
yang akurasinya buruk tinggal tidak mengirimkannya untuk melewati
pemeriksaan ">100 m".

`device_anon_id` tidak pernah disimpan apa adanya; lihat `PROCESS-LOG.md`
Keputusan 24.

```json
{
  "payload": "00020101021126660014ID.CO.QRIS.WWW...",
  "lat": -6.914744,
  "lng": 107.609810,
  "device_anon_id": "550e8400-e29b-41d4-a716-446655440000",
  "accuracy_m": 12,
  "device_integrity": {
    "mock_location": false, "rooted": false,
    "attested": true, "platform": "android"
  },
  "include_tlv": false
}
```

Dua field terakhir opsional. `device_integrity` hanya bisa diisi klien
native; `include_tlv` hanya dipakai perkakas forensik dan mode demo.

### Tanggapan `200`

| Field | Tipe | Catatan |
|---|---|---|
| `verdict` | string | `verified` \| `unknown` \| `anomaly` — **tertutup** |
| `action` | string | `proceed` \| `warn` \| `step_up` \| `cooling_off` — **tertutup** |
| `risk_score` | integer | 0–100 |
| `reasons` | array of string | penjelasan siap tampil, bahasa manusia — **terbuka** |
| `signals` | array of string | nama sinyal untuk analitik — **terbuka** |
| `layers` | object | `{ "location": int, "behavior": int }` |
| `merchant` | object | `nmid`, `name`, `city`, `criteria`, `is_static` |
| `fees` | object | biaya di luar nominal yang DIMINTA payload — tag 55/56/57. **Pengungkapan, bukan skor**: tidak satu pun sinyal lahir darinya |
| `tlv` | array | bedah TLV per tag. **Kosong** kecuali permintaan menyetel `include_tlv: true`. Forensik, bukan penilaian |
| `verification_ticket` | string | putusan yang ditandatangani, terikat ke sidik jari payload. **Mengikat, bukan memaksa** |
| `ticket_expires_in` | integer | masa berlaku tiket dalam detik (90) |
| `location_source` | string | `live` \| `replay` |
| `processing_ms` | number | |

```json
{
  "verdict": "anomaly",
  "action": "cooling_off",
  "risk_score": 83,
  "reasons": ["Merchant ID berbeda dari 47 pengamatan sebelumnya di lokasi ini"],
  "signals": ["nmid_changed_at_anchor"],
  "layers": { "location": 83, "behavior": 0 },
  "merchant": {
    "nmid": "ID1024365478912", "name": "WARUNG BU SRI",
    "city": "BANDUNG", "criteria": "Usaha Mikro", "is_static": true
  },
  "fees": {
    "indicator": null, "label": null,
    "fixed": null, "percent": null, "present": false
  },
  "location_source": "live",
  "processing_ms": 2.8
}
```

**Tentang `verification_ticket`.** Setiap tanggapan membawa putusan yang
**ditandatangani dan diikat ke sidik jari payload** yang diperiksa,
berlaku `ticket_expires_in` detik (90).

Gunanya menutup satu celah: antara "diperiksa" dan "dieksekusi" ada
jeda, dan tanpa tiket tidak ada yang menjamin keduanya menyangkut QR
yang sama. Aplikasi — atau malware di antaranya — bisa memverifikasi QR
A lalu membayar ke QR B.

**Yang tiket ini TIDAK lakukan, dan tidak pernah kami klaim:** ia tidak
memaksa siapa pun mematuhi putusan. Tiket hanya berguna kalau ada yang
memeriksanya, dan yang mengeksekusi pembayaran adalah Anda, bukan kami.
PJP yang mengabaikan `cooling_off` akan mengabaikan tiketnya juga. Ia
**mengikat**, bukan **memaksa** — lihat R12 di `THREAT-MODEL.md`.

Ia juga tidak mencegah replay dalam masa berlakunya: tiketnya stateless
dan tidak disimpan, jadi QR yang sama bisa dieksekusi dua kali dalam 90
detik. Idempotensi transaksi tetap milik Anda (R13).

### `POST /api/v1/tickets/verify`

Kalau bahasa Anda tidak punya HMAC yang nyaman, atau Anda ingin jalur
yang sama dengan klien acuan kami, periksa tiketnya di sini.

```json
{
  "ticket": "eyJhY3Rpb24iOi...gwQ",
  "payload": "00020101021126660014ID.CO.QRIS.WWW..."
}
```

`payload` adalah QR yang **HENDAK DIBAYAR**, bukan yang tadi
diverifikasi — dan ia **wajib**. Menjadikannya opsional berarti
menyediakan cara memakai endpoint ini yang terasa benar tapi tidak
menutup celah apa pun, dan itu kesalahan yang paling mungkin dilakukan
integrator. Ditutup di batas sistem, bukan lewat peringatan di dokumen.

```json
{
  "valid": true,
  "verdict": "verified", "action": "proceed",
  "nmid": "ID1024365478912",
  "issued_at": "2026-09-21T08:34:08+00:00",
  "expires_at": "2026-09-21T08:35:38+00:00",
  "detail": null
}
```

Tiket yang tidak sah dijawab **`200` dengan `valid: false`**, bukan
`4xx`. Alasannya: "tiket tidak sah" adalah jawaban yang BENAR atas
pertanyaan yang sah, bukan kesalahan pemanggil. Klien yang
memperlakukan non-200 sebagai gangguan jaringan lalu mencoba lagi tidak
boleh diam-diam melewatkan penolakan. `detail` berisi alasannya.

Endpoint ini menuntut `X-API-Key` seperti jalur `/api/` lainnya —
kuncinya juga yang menentukan bahan penandatanganan yang dipakai.

Yang punya `hmac` di pustaka standarnya sebaiknya memeriksanya sendiri
tanpa perjalanan jaringan tambahan; algoritmanya di bawah.

### Cara memverifikasi tiket

Algoritmanya sengaja sederhana supaya bisa ditulis ulang di bahasa mana
pun tanpa pustaka tambahan.

```
tiket        = <badan>.<tanda>            keduanya base64url tanpa padding
bahan        = sha256_hex(kunci_API_mentah_Anda)
kunci_tiket  = HMAC-SHA256(bahan, "qshield-ticket-v1")
tanda_harap  = base64url(HMAC-SHA256(kunci_tiket, badan))   tanpa padding
```

1. Bandingkan `tanda` dengan `tanda_harap` memakai **perbandingan
   waktu-tetap**, bukan `==`.
2. Decode `badan` sebagai JSON. Tolak bila `v != "qs1"`.
3. Tolak bila `exp <= sekarang`, atau `iat > sekarang + 60`
   (jam tidak sinkron).
4. **Hitung `sha256_hex` dari payload yang HENDAK DIBAYAR dan tuntut
   sama dengan `fp`.** Langkah inilah gunanya tiket — tanpa langkah 4,
   Anda hanya membuktikan tiketnya asli, bukan bahwa ia menyangkut QR
   yang sedang dieksekusi.

Klaim di dalam `badan`:

| Klaim | Isi |
|---|---|
| `v` | versi format, `"qs1"` |
| `fp` | sha256 hex payload QRIS yang diperiksa |
| `verdict` / `action` | putusan, sama persis dengan tanggapannya |
| `nmid` | merchant yang diperiksa |
| `client` | `client_id` PJP penerbit |
| `iat` / `exp` | epoch detik UTC |

Tidak ada koordinat, tidak ada `device_anon_id`, tidak ada payload
mentah — hanya sidik jarinya. Invarian §8 berlaku di sini juga.

Implementasi acuan ada di `src/qshield/ticket.py`; PJP yang memakai
Python bisa langsung `from qshield.ticket import verify`.

**Tentang `tlv`.** Setel `include_tlv: true` di permintaan untuk
menerima bedah TLV payload — tiap tag beserta `tag`, `length`, `value`,
`label`, dan `children` untuk tag bersarang (26-51, 62, 64). Urutannya
urutan kemunculan di payload, bukan urut tag.

Sengaja **opt-in**: bedahnya hampir empat kali lipat ukuran tanggapan
normal (533 → 1984 byte pada payload demo), dan hanya panel forensik
yang memerlukannya. Tidak ada paparan baru — seluruh isinya turunan
dari `payload` yang wajib Anda kirim sendiri.

**Tidak menyentuh penilaian sama sekali.** `verdict`, `action`,
`risk_score`, `layers`, dan `signals` identik dengan atau tanpa flag
ini; dikunci `tests/test_contract.py` "Bedah TLV opt-in".

**Tentang `fees`.** Tag 55 (indikator tip/biaya layanan), 56 (nominal
tetap), dan 57 (persentase) diparse dan diteruskan apa adanya:

| Field | Isi |
|---|---|
| `indicator` | tag 55 mentah — `01` minta tip, `02` nominal tetap, `03` persentase |
| `label` | arti `indicator` dalam bahasa manusia |
| `fixed` | tag 56 |
| `percent` | tag 57 |
| `present` | `true` bila salah satu dari ketiganya ada |

**Tidak satu pun dari field ini menyentuh penilaian.** Belum
terverifikasi apakah biaya layanan pada QR **statis** itu kontradiksi
terhadap spec QRIS atau justru sah, dan menghukum yang ternyata sah
dengan bobot struktural berarti memaksa `anomaly` pada payload yang
benar. Jadi ia diperlakukan seperti `location_source` dan
`device_integrity`: pengungkapan, bukan skor. Dikunci
`tests/test_contract.py` "Tag biaya diungkapkan".

**`reasons` yang menjelaskan; angka hanya boleh tampil dengan skalanya.**
Kalimat itulah yang bisa dipertanggungjawabkan ke pengguna maupun
regulator — tampilkan selalu.

`risk_score` boleh ikut ditampilkan, tapi **tidak pernah telanjang**:
"Skor 83" sama sekali tidak memberi tahu 83 itu buruk atau bagus.
Sertakan denominatornya — "Risiko 83 dari 100". Klien acuan kami
melakukan persis itu.

Dua field yang **tidak boleh** sampai ke pengguna akhir:

| Field | Kenapa |
|---|---|
| `layers` | alat AUDIT — ia menjawab "dari lapisan mana skor ini datang", pertanyaan milik Anda dan auditor. Dan "Lokasi 0" gampang dibaca terbalik sebagai gagal, padahal itu hasil terbaik |
| `processing_ms` | mengukur kecepatan kami, bukan risiko pengguna |

Lihat `PROCESS-LOG.md` Keputusan 44.

### Kode kesalahan

| Kode | Sebab |
|---|---|
| `401` | kunci API tidak valid atau tidak disertakan |
| `413` | badan permintaan > 8 KB |
| `422` | field tidak lolos validasi, atau payload QRIS tidak bisa diurai |
| `429` | kuota terlampaui — lihat `Retry-After` |
| `503` | autentikasi belum dikonfigurasi di server |

### Header tanggapan

`X-RateLimit-Limit`, `X-RateLimit-Remaining`, dan pada `429`
`Retry-After`. Seluruh tanggapan membawa `X-Content-Type-Options`,
`X-Frame-Options`, `Referrer-Policy`, `Cache-Control`.

---

## `POST /api/v1/merchants`

Mendaftarkan ikatan merchant-lokasi. Yang mendaftarkan adalah PJP yang
meng-onboard merchant, jadi ia memang mengetahui NMID mana milik siapa.
Menutup cold start: merchant tidak perlu menunggu tiga pengamat selama
24 jam.

| Field | Tipe | Wajib | Catatan |
|---|---|---|---|
| `nmid` | string | ya | 3–32 karakter alfanumerik |
| `lat` | number | ya | |
| `lng` | number | ya | |
| `merchant_name` | string | tidak | maks 99 karakter |
| `is_mobile` | boolean | tidak | merchant keliling — ikatan lokasi tidak berlaku |

Mendaftarkan NMID yang sudah terdaftar oleh **PJP yang sama** berarti
memperbarui — inilah jalur relokasi merchant. Jangkar lama otomatis
berhenti berstatus resmi.

| Kode | Arti |
|---|---|
| `201` | terdaftar |
| `401` | kunci API tidak valid |
| `409` | NMID sudah didaftarkan penyelenggara lain |
| `422` | field tidak lolos validasi |

## `DELETE /api/v1/merchants/{nmid}`

Mencabut pendaftaran. **Hanya PJP yang mendaftarkan yang boleh.**

Pencabutan mengembalikan status, **tidak menghapus pengamatan** —
konsensus yang sudah terkumpul adalah bukti yang sah, terlepas dari
status pendaftaran.

| Kode | Arti |
|---|---|
| `200` | dicabut |
| `403` | bukan pendaftarnya |
| `404` | NMID tidak terdaftar |

### Catatan keamanan

Ini **jalur kepercayaan baru**. Kunci PJP yang bocor bisa dipakai
mendaftarkan stiker palsu sebagai `verified`. Itu tidak bisa dicegah
dari sisi Q-Shield — yang bisa dilakukan adalah membuatnya terlacak dan
bisa dibatalkan: tiap pendaftaran mencatat pendaftarnya, dan sinyal
`registered_merchant` selalu berbeda dari `established_binding`
sehingga auditor tahu sebuah verdict `verified` datang dari pernyataan
atau dari konsensus.

## `GET /api/v1/health`

Terbuka tanpa autentikasi, untuk monitoring.

```json
{ "status": "ok", "bindings": 5, "observations": 128, "merchants": 3 }
```

---

## Catatan untuk klien

1. **Abaikan field tanggapan yang tidak dikenal.** Field baru bisa
   muncul tanpa naik versi.
2. **Tampilkan `reasons` selalu.** `risk_score` boleh ikut, tapi hanya
   dengan skalanya ("Risiko 83 dari 100"), tidak pernah telanjang.
   `layers` dan `processing_ms` tidak pernah untuk pengguna akhir.
3. **Petakan `action`, bukan `verdict`,** ke perilaku UI. `verdict`
   menjawab "apa yang kami ketahui", `action` menjawab "apa yang
   sebaiknya dilakukan" — dan yang kedua itulah yang menentukan layar.
4. **Perlakukan `unknown` sebagai peringatan, bukan lampu hijau.**
   Ini invarian, bukan preferensi: ketiadaan bukti bukan kepercayaan.
5. **Verifikasi `verification_ticket` sebelum mengeksekusi**, dan
   sertakan payload yang hendak dibayar di langkah 4 algoritmanya.
   Tanpa langkah itu tiketnya hanya hiasan.
6. **Teruskan `coords.accuracy` apa adanya** dari Geolocation API.
   Jangan dibulatkan, jangan diisi nilai tetap — keduanya menghasilkan
   penilaian yang salah, dan nilai di bawah 1 m ditandai sebagai
   mustahil secara fisik.
