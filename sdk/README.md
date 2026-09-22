# Tempat SDK native masuk

Dokumen ini untuk **penulis SDK Android**, bukan untuk PJP. Panduan PJP
ada di [`../docs/INTEGRATION.md`](../docs/INTEGRATION.md); yang ini soal batas
teknis antara SDK dan backend, dan cara bekerja di kedua sisi tanpa
saling menunggu.

Slot yang diisi SDK sudah ada di backend sejak Keputusan 31 — sengaja
dibangun **slotnya, bukan SDK-nya**, supaya kontraknya stabil lebih dulu.

---

## 1. Putuskan ini dulu: di mana kunci API tinggal

Ini keputusan arsitektur, bukan detail implementasi, dan ia menentukan
bentuk SDK-nya. **Jangan menulis kode jaringan sebelum ini dijawab.**

`README.md` menyatakan: *"Klien Q-Shield adalah PJP, bukan orang. Satu
kunci mewakili satu penyelenggara."* Kunci itu milik **server**.

```
  JALUR PRODUKSI (kunci aman)
  aplikasi ──► backend PJP ──► Q-Shield
     SDK        X-API-Key        verify
                (server-side)

  JALUR LANGSUNG (kunci bocor)
  aplikasi ─────────────────► Q-Shield
     SDK + X-API-Key di dalam APK
```

APK bisa dibongkar. Kunci yang dipanggang ke dalam aplikasi adalah kunci
yang bocor — dan karena kuota serta pencatatan Q-Shield dihitung
**per klien**, kunci bocor berarti pihak lain bisa memakai identitas PJP
itu untuk mendaftarkan merchant (`POST /api/v1/merchants`), bukan cuma
membaca putusan.

| Pilihan | Kapan wajar | Konsekuensi |
|---|---|---|
| SDK → backend PJP → Q-Shield | produksi | kunci tidak pernah meninggalkan server; SDK tidak perlu tahu Q-Shield ada |
| SDK → Q-Shield langsung | **demo/hackathon saja** | jalankan server dengan `QSHIELD_AUTH=off`, dan jangan pernah menyematkan kunci sungguhan |

Kalau SDK memanggil backend PJP (jalur produksi), maka yang perlu
disepakati dengan tim backend PJP adalah bentuk internal mereka — dan
bagian di bawah ini tetap berlaku, karena backend PJP akan meneruskan
field yang sama.

---

## 2. Yang sudah ada, dan yang jadi bagianmu

| Hal | Status | Di mana |
|---|---|---|
| Kontrak permintaan/tanggapan | **selesai, terkunci test** | `tests/test_contract.py` |
| Slot `device_integrity` | **selesai** | `src/qshield/api.py` `DeviceIntegrity` |
| Penilaian tiap nilai integritas | **selesai** | `src/qshield/behavior.py` `_device_signals` |
| Fixture untuk tiap tier & status | **selesai** | `sdk/contract/` |
| Validator payload offline | **selesai** | `scripts/sdk_contract.py check` |
| Pengumpulan lokasi + integritas di Android | **bagianmu** | `sdk/android/` |
| Pemanggilan HTTP + parsing tanggapan | **bagianmu** | `sdk/android/` |
| Pemetaan 4 tier ke UI | **bagianmu** | `../docs/INTEGRATION.md` §2 |
| Penerbitan tiket verifikasi | **selesai** | `src/qshield/ticket.py` |
| Pemeriksaan tiket saat eksekusi | **bagianmu / backend PJP** | §6 |
| Endpoint pemeriksa tiket | **selesai** | `POST /api/v1/tickets/verify` |

---

## 3. Bekerja tanpa backend hidup

Dua perintah. Keduanya jalan tanpa server, tanpa jaringan.

```bash
# Lihat bentuk permintaan + tanggapan untuk setiap keadaan
ls sdk/contract/

# Validasi satu permintaan yang DIHASILKAN SDK-mu
python scripts/sdk_contract.py check payload-dari-sdk.json
```

`check` memvalidasi terhadap model pydantic yang sungguhan dipakai
server, lalu menyebut constraint yang dilanggar beserta penyebab
khas Android-nya — bukan sekadar melempar `422`.

Sembilan fixture, dipilih supaya setiap keadaan yang mungkin dirender
SDK punya contohnya — plus satu yang memperlihatkan bentuk `tlv`:

| Berkas | Tier | `device_integrity` |
|---|---|---|
| `01-web-tanpa-integritas` | `proceed` | `not_provided` |
| `02-android-attested` | `proceed` | `attested` |
| `03-android-dilaporkan-tanpa-attestation` | `proceed` | `reported` |
| `04-android-perangkat-di-root` | `warn` | `failed` |
| `05-android-attestation-gagal` | `warn` | `failed` |
| `06-android-mock-location` | `step_up` | `failed` |
| `07-akurasi-gps-buruk` | `warn` | `attested` |
| `08-anomali-stiker-palsu` | `cooling_off` | `attested` |
| `09-bedah-tlv-mode-demo` | `proceed` | `attested` |

Fixture ini **dihasilkan dari kode**, bukan diketik tangan, dan
`tests/test_sdk_contract.py` membangunnya ulang lalu membandingkannya
tiap kali suite dijalankan. Fixture yang basi mustahil lolos diam-diam.

`processing_ms` dinormalkan ke `0` di fixture — nilainya asli bervariasi.

### Tiga field tanggapan yang PENGUNGKAPAN, bukan skor

Tidak satu pun menyentuh `risk_score`, `layers`, `action`, atau
`signals`. Perlakukan sebagai informasi yang ditampilkan, bukan sebagai
putusan.

| Field | Isi | Saran |
|---|---|---|
| `device_integrity` | `not_provided` / `reported` / `attested` / `failed` | `not_provided` berarti pemeriksaan **tidak pernah dijalankan**, bukan dijalankan lalu lolos |
| `fees` | biaya di luar nominal yang diminta payload (tag 55/56/57) | tampilkan ke pengguna bila `fees.present`, **sebelum** layar PIN, dan tampilkan netral — ini fakta, bukan tuduhan |
| `tlv` | bedah TLV per tag; kosong kecuali `include_tlv: true` | perkakas internal dan investigasi; **jangan** tampilkan ke nasabah |
| `verification_ticket` | putusan bertanda tangan, terikat ke sidik jari payload | **teruskan ke titik yang mengeksekusi pembayaran** — lihat §6 |

`tlv` berguna saat mengembangkan SDK: ia memperlihatkan apa yang
**server** baca dari payload yang kamu kirim, jadi kalau hasilnya tidak
seperti dugaanmu, selisihnya kelihatan tanpa menebak. Nilainya berasal
dari payload yang dikendalikan penyerang — escape sebelum dirender.

---

## 4. Bentuk permintaan

Acuan bentuk untuk Kotlin. **Belum pernah dikompilasi** — ia
mencerminkan `VerifyRequest` di `src/qshield/api.py`, silakan sesuaikan
dengan serializer yang kamu pakai.

```kotlin
@Serializable
data class VerifyRequest(
    val payload: String,          // QRIS mentah; 8..1024 char ASCII cetak
    val lat: Double,              // -90..90
    val lng: Double,              // -180..180
    @SerialName("device_anon_id")
    val deviceAnonId: String,     // ^[A-Za-z0-9_-]{8,64}$
    @SerialName("accuracy_m")
    val accuracyM: Double,        // WAJIB. meter.
    @SerialName("location_source")
    val locationSource: String = "live",   // "live" | "replay"
    @SerialName("device_integrity")
    val deviceIntegrity: DeviceIntegrity? = null,
    // Bedah TLV untuk perkakas debug SDK-mu sendiri. Biarkan false di
    // produksi: tanggapannya membengkak ~4x (533 -> 1984 byte diukur).
    @SerialName("include_tlv")
    val includeTlv: Boolean = false,
)

@Serializable
data class DeviceIntegrity(
    @SerialName("mock_location") val mockLocation: Boolean? = null,
    val rooted: Boolean? = null,
    val attested: Boolean? = null,
    val platform: String? = null,          // "android"
)
```

## 5. Bentuk tanggapan

```kotlin
@Serializable
data class VerifyResponse(
    val verdict: String,          // verified | unknown | anomaly  (TERTUTUP)
    val action: String,           // proceed | warn | step_up | cooling_off (TERTUTUP)
    @SerialName("risk_score")
    val riskScore: Int,           // 0..100
    val reasons: List<String>,    // siap tampil, bahasa manusia
    val signals: List<String>,    // daftar TERBUKA — abaikan yang asing
    val layers: LayerScores,      // alat audit; JANGAN tampilkan ke pengguna
    val merchant: MerchantOut,
    val fees: FeeOut,
    val tlv: List<TlvOut> = emptyList(),   // kosong kecuali include_tlv
    @SerialName("location_source")
    val locationSource: String,   // live | replay
    @SerialName("device_integrity")
    val deviceIntegrity: String,  // not_provided | reported | attested | failed
    @SerialName("verification_ticket")
    val verificationTicket: String,   // putusan bertanda tangan
    @SerialName("ticket_expires_in")
    val ticketExpiresIn: Int,         // detik (90)
    @SerialName("processing_ms")
    val processingMs: Double,     // metrik kami; JANGAN tampilkan
)

@Serializable
data class LayerScores(val location: Int, val behavior: Int)

@Serializable
data class MerchantOut(
    val nmid: String?, val name: String?, val city: String?,
    val criteria: String?,
    @SerialName("is_static") val isStatic: Boolean,
)

@Serializable
data class FeeOut(
    val indicator: String? = null,   // tag 55
    val label: String? = null,
    val fixed: String? = null,       // tag 56
    val percent: String? = null,     // tag 57
    val present: Boolean = false,
)

@Serializable
data class TlvOut(
    val tag: String, val length: Int, val value: String, val label: String,
    val children: List<TlvOut> = emptyList(),
)
```

**Pakai serializer yang mengabaikan field tak dikenal** — di
kotlinx.serialization: `Json { ignoreUnknownKeys = true }`. Field baru
bisa muncul tanpa naik versi, dan parser yang ketat akan crash pada
tanggapan yang sebenarnya sah.

---

## 6. Tiket verifikasi — bagian yang paling mudah salah dipahami

Tanggapan membawa `verification_ticket`: putusan yang ditandatangani dan
diikat ke **sidik jari payload** yang diperiksa, berlaku 90 detik.

**SDK kemungkinan besar bukan tempat memverifikasinya.** Kuncinya
diturunkan dari kunci API PJP, dan kunci itu — sesuai §1 — tidak boleh
ada di dalam APK. Jadi tugas SDK biasanya cuma satu: **teruskan
tiketnya apa adanya** ke backend PJP bersama payload yang hendak
dibayar. Backend yang memeriksanya.

Kalau SDK memang perlu memeriksanya sendiri (misalnya arsitektur demo
yang memanggil Q-Shield langsung), algoritmanya tanpa pustaka tambahan:

```kotlin
// javax.crypto + java.security sudah ada di Android. Tanpa dependensi.
fun kunciTiket(bahanRahasia: String): ByteArray {
    val mac = Mac.getInstance("HmacSHA256")
    mac.init(SecretKeySpec(bahanRahasia.toByteArray(), "HmacSHA256"))
    return mac.doFinal("qshield-ticket-v1".toByteArray())
}

// bahanRahasia = sha256 hex dari kunci API mentah Anda
// tiket = "<badan>.<tanda>", keduanya base64url TANPA padding
// tandaHarap = base64url(HmacSHA256(kunciTiket, badan))
// Bandingkan dengan MessageDigest.isEqual(), BUKAN ==.
```

**Atau panggil endpointnya.** `POST /api/v1/tickets/verify` dengan
`{ticket, payload}` melakukan pemeriksaan yang sama di sisi server —
dan `payload` di sana **wajib**, jadi langkah 4 tidak bisa dilewati.
Endpoint itu menuntut `X-API-Key`, jadi berlaku batasan §1 yang sama:
kalau kuncinya tidak boleh ada di APK, yang memanggilnya adalah backend
PJP, bukan SDK.

**Empat langkah, dan yang keempat yang menentukan:**

1. Cocokkan tanda tangan dengan perbandingan **waktu-tetap**
2. Decode `badan` sebagai JSON; tolak bila `v != "qs1"`
3. Tolak bila `exp <= sekarang`, atau `iat > sekarang + 60`
4. **Hitung `sha256` payload yang HENDAK DIBAYAR, tuntut sama dengan
   `fp`**

Tanpa langkah 4, Anda hanya membuktikan tiketnya asli — bukan bahwa ia
menyangkut QR yang sedang dieksekusi. Itu persis celah yang tiket ini
dibuat untuk menutup, dan melewatkannya membuat seluruhnya hiasan.

**Yang tidak boleh diklaim ke siapa pun:** tiket **mengikat**, ia tidak
**memaksa**. Ia mencegah putusan dipindahkan ke QR lain; ia tidak
mencegah aplikasi atau backend mengabaikannya. Dan ia tidak mencegah
replay dalam 90 detik — idempotensi transaksi milik PJP.

Di fixture, `verification_ticket` dinormalkan jadi
`<base64url-klaim>.<base64url-hmac-sha256>` karena nilainya berubah tiap
permintaan.

---

## 7. Kesalahan yang paling sering terjadi

Empat hal yang paling sering salah, semuanya ditangkap `check`:

- **`accuracy_m` wajib.** Bukan opsional. Menghilangkannya adalah pintu
  keluar dari invarian §6, jadi ditolak di batas sistem alih-alih
  diberi skor. `Location.getAccuracy()` sudah dalam meter.
- **`device_anon_id` bukan identitas.** `UUID.randomUUID().toString()`
  yang disimpan per pemasangan. **Jangan** `ANDROID_ID`, jangan IMEI,
  jangan apa pun yang menempel pada orangnya — seluruh argumen privasi
  di `../docs/THREAT-MODEL.md` §7 bersandar pada ini.
- **`payload` apa adanya.** Jangan di-trim, jangan di-decode ulang,
  jangan diubah huruf besar-kecilnya. Sinyal sidik jari encoding di
  Layer 2 membaca bentuk aslinya.
- **Semua field `DeviceIntegrity` nullable.** Kirim `null` untuk yang
  tidak bisa kamu baca, bukan `false`. `false` berarti "sudah diperiksa,
  hasilnya bersih"; `null` berarti "tidak diperiksa". Keduanya berbeda.

---

## 8. Dari mana tiap nilai diambil di Android

| Field | Sumber | Catatan |
|---|---|---|
| `mock_location` | `Location.isMock()` (API 31+), sebelumnya `Location.isFromMockProvider()` (API 18+, deprecated di 31) | perlu cabang per level API |
| `rooted` | heuristikmu sendiri | tidak ada API resmi; kirim `null` kalau tidak memeriksa |
| `attested` | **Play Integrity — lihat §9** | jangan tetapkan dari dalam aplikasi |
| `platform` | konstanta `"android"` | |
| `accuracy_m` | `Location.getAccuracy()` | meter |
| `lat` / `lng` | `Location.getLatitude()` / `getLongitude()` | |

Akurasi di bawah **1,0 m** ditandai `implausible_accuracy` (bobot 45):
GNSS ponsel tidak pernah melaporkan radius sekecil itu, jadi nilai
seperti itu dianggap dikarang. Kalau emulator atau mock provider-mu
mengembalikan `0.0`, itu bukan bug backend.

---

## 9. `attested` — satu-satunya hal yang bisa salah secara serius

**Aplikasi tidak boleh memutuskan `attested`.**

Play Integrity mengembalikan **token**, bukan boolean. Token itu harus
diverifikasi di server, dan hanya server yang berhak menyatakan
`attested: true`. Aplikasi yang memutuskannya sendiri bisa dipaksa
mengirim `true` oleh siapa pun yang memegang perangkat itu — dan justru
perangkat yang dikuasai penyerang adalah yang ingin kita tangkap.

```
  BENAR                                   SALAH
  app: minta token Play Integrity         app: panggil Play Integrity
  app ──token──► server PJP               app: kalau sukses -> attested=true
  server: verifikasi token                app ──attested=true──► Q-Shield
  server ──attested=true──► Q-Shield
```

Q-Shield **tidak bisa mendeteksi** pelanggaran ini — rantai
kepercayaannya memang berhenti di PJP (`../docs/INTEGRATION.md` §3, dan T34 di
`../docs/THREAT-MODEL.md`). Karena itu satu-satunya tempat aturan ini bisa
ditegakkan adalah di kepala penulis SDK, dan `sdk_contract.py check`
akan memperingatkanmu setiap kali melihat `attested: true`.

Kalau attestation belum diverifikasi: kirim `null`, bukan `false`.
`false` berarti attestation **gagal** dan menaikkan skor 30.

---

## 10. Yang menjaga seam ini

```bash
python tests/test_sdk_contract.py   # fixture tidak basi; tiap keadaan terwakili
python tests/test_contract.py       # bentuk API v1 tidak bergeser diam-diam
python scripts/sdk_contract.py generate   # setelah perubahan kontrak yang DISENGAJA
```

Kalau `test_sdk_contract.py` merah, kontraknya bergeser. Regenerasi
fixture-nya **dan beri tahu penulis SDK** — bagian kedua itu yang tidak
bisa diotomatiskan.

`signals` dan `reasons` adalah **daftar terbuka**: nilai baru bisa
muncul tanpa naik versi, jadi abaikan yang tidak dikenali. Contoh nyata
dari 21 Sep 2026 — `malformed_country` ditambahkan tanpa naik versi, dan
klien yang memetakan sinyal secara eksklusif akan rusak karenanya.
`verdict`, `action`, dan `device_integrity` adalah **kosakata tertutup**:
nilai baru di sana berarti versi API baru.

---

## 11. Checklist sebelum SDK dianggap siap

- [ ] Keputusan §1 diambil: kunci API tidak ada di dalam APK
- [ ] `accuracy_m` selalu dikirim, tidak pernah dihilangkan
- [ ] `device_anon_id` acak per pemasangan, bukan pengenal perangkat
- [ ] Field integritas yang tidak diperiksa dikirim `null`, bukan `false`
- [ ] `attested` hanya diisi setelah verifikasi server-side
- [ ] Keempat tier `action` punya perlakuan UI sendiri
- [ ] `cooling_off` **menunda**, bukan menolak — jeda itu responsnya
- [ ] `unknown` tidak pernah dirender sebagai lampu hijau
- [ ] `reasons` selalu ditampilkan
- [ ] `risk_score` hanya tampil dengan skalanya, tidak pernah telanjang
- [ ] `layers` dan `processing_ms` tidak pernah sampai ke pengguna akhir
- [ ] `fees` ditampilkan bila `fees.present`, netral, sebelum layar PIN
- [ ] `include_tlv` **false** di build produksi
- [ ] Sinyal yang tidak dikenali diabaikan, bukan bikin crash
- [ ] `verification_ticket` diteruskan ke titik eksekusi, tidak dibuang
- [ ] Pemeriksaan tiket menyertakan payload (langkah 4), bukan hanya tanda tangan
- [ ] Tidak ada klaim "aplikasi tidak bisa mengabaikannya" di materi mana pun
- [ ] Payload keluaran SDK lolos `scripts/sdk_contract.py check`
