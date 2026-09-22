"""
Tulis prompt Android Studio dengan nilai yang sudah terisi.

Alamat laptop berubah tiap pindah jaringan — sudah tiga kali berubah
selama proyek ini. Menuliskannya sekali di dokumen berarti dokumen itu
basi beberapa jam kemudian, dan yang menanggung adalah orang yang
menempelkannya ke agent lalu bingung kenapa aplikasinya tidak
terhubung.

Jadi diisi di sini, tiap kali dijalankan.

  python scripts/make_android_prompt.py
  python scripts/make_android_prompt.py --app-id com.namakalian.qshield
  python scripts/make_android_prompt.py --host 10.0.0.5

Keluarannya docs/panduan/PROMPT-ANDROID.md — salin seluruh isinya ke agent.
"""

import os
import re
import socket
import subprocess
import sys

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KELUARAN = os.path.join(AKAR, "docs", "panduan", "PROMPT-ANDROID.md")
APP_ID_BAWAAN = "id.qshield.scanner"
PROYEK_ANDROID = os.path.expanduser("~/AndroidStudioProjects/QShield")


def ip_lan() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def cert_cocok(ip: str):
    """Apakah sertifikat yang ada masih berlaku untuk IP ini."""
    cert = os.path.join(AKAR, "certs", "cert.pem")
    if not os.path.exists(cert):
        return False, "certs/cert.pem belum ada"
    hasil = subprocess.run(
        ["openssl", "x509", "-in", cert, "-noout", "-text"],
        capture_output=True, text=True)
    # SAN yang mencakup seluruh rentang jaringan memuat ribuan alamat dan
    # terbungkus ke banyak baris, jadi dicari di seluruh teks.
    alamat = set(re.findall(r"IP Address:([0-9.]+)", hasil.stdout))
    if not alamat:
        return False, "sertifikat tidak punya SAN"
    if ip not in alamat:
        contoh = sorted(alamat)[:2]
        return False, f"sertifikat tidak mencakup {ip} (mis. {', '.join(contoh)})"
    return True, f"mencakup {len(alamat)} alamat"


TEMPLATE = '''# Prompt untuk AI agent di Android Studio

Dibuat otomatis oleh `scripts/make_android_prompt.py`. Alamat laptop
dan application id sudah terisi.

    alamat server : {base_url}
    application id: {app_id}
    sertifikat    : {status_cert}

Kalau berpindah jaringan, jalankan ulang skrip itu — alamatnya berubah.

**Salin seluruh blok di bawah ini ke agent.** Ditulis dalam bahasa
Inggris karena agent coding umumnya lebih akurat begitu.

---

```
Build an Android app in Kotlin called "Q-Shield Scanner", application
id {app_id}. It is a reference client for an existing QRIS anti-fraud
API. The API already exists and is fully specified below — do not
invent endpoints or fields.

## What the app is for

Indonesian QRIS payment stickers can be covered with a fraudster's own
sticker. The backend detects this by checking whether a merchant ID
belongs at a given location. A web client already exists, but browsers
withhold three signals that only a native app can collect:

  1. ambient WiFi BSSIDs      — sharper location fingerprint than GPS
  2. mock-location detection  — is the GPS fix fake
  3. device integrity         — is the device rooted / app tampered

This app collects those and sends them to the existing API.

## Requirements

Language Kotlin, Jetpack Compose, minSdk 26, targetSdk 35.
Architecture: single Activity, ViewModel + StateFlow, Retrofit + OkHttp
+ kotlinx.serialization. No other third-party dependencies beyond
CameraX and ML Kit barcode scanning.

## Screens

ONE screen with three states:

1. SCANNING  — camera preview filling the screen, a square guide frame
               in the middle, and a small text hint below it.
2. RESULT    — a card showing the verdict. Colours:
                 proceed      green
                 warn         amber
                 step_up      orange
                 cooling_off  red
               Show every string from `reasons` as a bulleted list in
               the order received — the API already sorts them by
               importance, do not re-sort.
               Show `merchant.name` and `merchant.nmid` prominently.
               Below the NMID show the text "Cocokkan dengan Merchant
               ID yang tercetak di stiker", a text field for what is
               printed, and a "Periksa" button that re-submits with
               that value in printed_label.nmid.
3. ERROR     — network or permission failure, with a retry button.

Display language is Indonesian. Keep the Indonesian strings exactly as
given.

## Permissions

CAMERA, ACCESS_FINE_LOCATION, ACCESS_WIFI_STATE, CHANGE_WIFI_STATE.
Request at runtime with a rationale screen. The app must still work if
WiFi permission is denied — it simply omits that field.

## Data collection, in this exact order

When a QR is detected:

1. Stop the camera immediately so the same code is not read twice.
2. Get location via FusedLocationProviderClient, high accuracy,
   10 second timeout.
3. Detect mock location:
      Build.VERSION.SDK_INT >= 31  -> location.isMock
      otherwise                    -> location.isFromMockProvider
4. Scan WiFi via WifiManager.scanResults. Since Android 9 scanning is
   throttled to about 4 calls per 2 minutes, cache the last result for
   60 seconds and reuse it instead of scanning every time.
   Hash each BSSID and send ONLY the hash:

      val normalised = bssid.lowercase()
      val digest = MessageDigest.getInstance("SHA-256")
          .digest(normalised.toByteArray())
      val hex = digest.joinToString("") {{ "%02x".format(it) }}.take(32)

   NEVER send the raw BSSID or SSID. Take at most 32 access points,
   sorted by signal level descending.
5. Detect root with a simple heuristic: existence of
   /system/app/Superuser.apk, /sbin/su, /system/bin/su,
   /system/xbin/su, and whether Build.TAGS contains "test-keys".
   Report the boolean; do not attempt to bypass anything.
6. Device id: generate a random UUID on first launch, store it in
   DataStore, reuse it forever. Must match ^[A-Za-z0-9_-]{{8,64}}$.
   Never use ANDROID_ID, IMEI, or any hardware identifier.

## The API

Base URL configurable in a settings screen, default {base_url}

POST /api/v1/verify
Header: X-API-Key: <configurable, may be empty during local testing>
Content-Type: application/json

Request body — every field named here is real, nothing else is
accepted:

{{
  "payload": "<raw QRIS string from the QR>",
  "lat": -6.914744,
  "lng": 107.609810,
  "accuracy_m": 8.5,
  "device_anon_id": "<the stored UUID>",
  "device_integrity": {{
    "mock_location": false,
    "rooted": false,
    "attested": null,
    "platform": "android"
  }},
  "ambient_wifi": {{
    "ap_hashes": ["a1b2c3...", "d4e5f6..."]
  }},
  "printed_label": {{
    "nmid": "<only when the user typed it>",
    "merchant_name": null
  }}
}}

Rules that matter:
- payload, lat, lng, accuracy_m, device_anon_id are REQUIRED.
- device_integrity, ambient_wifi, printed_label are optional. Omit the
  whole object rather than sending an object full of nulls. Omitting is
  not penalised by the server.
- accuracy_m must be the real value from the Location object. Do not
  round it and do not substitute a constant — the server treats values
  below 1.0 as physically impossible and raises the risk score.
- Set "attested" to null. Play Integrity is a later step.

Response 200:

{{
  "verdict": "verified" | "unknown" | "anomaly",
  "action": "proceed" | "warn" | "step_up" | "cooling_off",
  "risk_score": 0,
  "reasons": ["...", "..."],
  "signals": ["..."],
  "layers": {{"location": 0, "behavior": 0}},
  "merchant": {{
    "nmid": "...", "name": "...", "city": "...",
    "criteria": "...", "is_static": true
  }},
  "location_source": "live",
  "device_integrity": "not_provided" | "reported" | "attested" | "failed",
  "processing_ms": 2.8
}}

Map `action` to the UI, not `verdict`. Ignore unknown response fields —
new ones are added without a version bump.

Error codes and the Indonesian message to show:
  401 "Kunci API tidak valid"
  413 "Kode terlalu panjang"
  422 "Kode ini bukan QRIS yang sah"
  429 "Terlalu banyak permintaan, tunggu sebentar"
  503 "Server belum dikonfigurasi"
  other "Tidak bisa menghubungi server"

## Self-signed certificate

The server runs with a self-signed certificate on the local network.
Add a network security config that trusts user-added CAs for debug
builds only, and document that release builds must use a real
certificate. Do not disable certificate validation in code.

## Privacy constraints — not negotiable

- Never send raw BSSID, SSID, IMEI, ANDROID_ID, phone number, or any
  account identifier.
- The device UUID is random and app-local. It is not an identity.
- Do not log the QRIS payload or the device UUID in release builds.
- Do not add analytics, crash reporting, or any third-party SDK.

## What to deliver

A complete, compiling project: Gradle files, manifest with permissions,
Compose UI, ViewModel, Retrofit service, serializable data classes,
WiFi and location helpers, and a README with build instructions.

Unit tests for: the BSSID hashing function (same input gives the same
32-character lowercase hex), the request builder (optional objects
omitted when empty, never sent as objects full of nulls), and the
action-to-colour mapping.

Do not implement: payment flow, user accounts, merchant registration,
or anything not listed above.
```

---

## Setelah agent selesai — periksa empat hal ini

Agent tidak bisa memeriksanya sendiri, dan keempatnya kesalahan yang
sering terjadi.

1. **Hash BSSID yang dikirim, bukan BSSID mentah.** Cek Logcat atau
   proxy — jangan sampai ada yang berbentuk `aa:bb:cc:...`
2. **`accuracy_m` nilai asli**, bukan konstanta. Server memperlakukan
   nilai di bawah 1,0 sebagai mustahil secara fisik.
3. **Aplikasi tetap jalan saat izin WiFi ditolak** — field-nya
   dihilangkan, bukan dikirim kosong.
4. **Tidak ada SDK pihak ketiga** yang diam-diam ditambahkan.

## Menjalankan server untuk mengujinya

```bash
{perintah_cert}.venv/bin/uvicorn qshield.api:app \\
  --host 0.0.0.0 --port 8000 \\
  --ssl-certfile certs/cert.pem --ssl-keyfile certs/key.pem
```

`QSHIELD_AUTH=off` mematikan pemeriksaan kunci API — cukup untuk
menguji di jaringan sendiri, jangan dipakai saat demo.

Pindai `props/01-asli.png` — harus `proceed`.
Pindai `props/02-swap.png` — harus `cooling_off`.

Untuk memastikan sidik jari WiFi benar-benar masuk:

```bash
python3 scripts/diagnose.py --anchor <lat> <lng>
```
'''


def salin_cert(proyek: str):
    """Taruh sertifikat di res/raw supaya aplikasi mempercayainya sendiri.

    Alternatifnya menyuruh orang memasang sertifikat lewat setelan HP:
    butuh kunci layar, memunculkan peringatan "jaringan mungkin
    dipantau", dan harus diulang tiap sertifikat dibuat ulang — yang
    di proyek ini terjadi tiap pindah jaringan.
    """
    if not os.path.isdir(proyek):
        return None
    raw = os.path.join(proyek, "app", "src", "main", "res", "raw")
    os.makedirs(raw, exist_ok=True)
    tujuan = os.path.join(raw, "qshield_ca.pem")
    with open(os.path.join(AKAR, "certs", "cert.pem")) as f:
        isi = f.read()
    with open(tujuan, "w") as f:
        f.write(isi)
    return tujuan


def main(argv):
    app_id = APP_ID_BAWAAN
    if "--app-id" in argv:
        app_id = argv[argv.index("--app-id") + 1]

    ip = argv[argv.index("--host") + 1] if "--host" in argv else ip_lan()
    base_url = f"https://{ip}:8000"

    ok, pesan = cert_cocok(ip)
    if not ok and "--tanpa-cert" not in argv:
        # Skrip ini sudah tahu sertifikatnya salah. Menyuruh orang
        # menjalankan perintah kedua untuk memperbaiki sesuatu yang
        # sudah kita ketahui hanya memindahkan pekerjaan, bukan
        # menyelesaikannya.
        print(f"  sertifikat tidak cocok ({pesan}) — dibuat ulang...")
        subprocess.run([sys.executable, os.path.join(AKAR, "scripts", "make_cert.py")],
                       cwd=AKAR, capture_output=True)
        ok, pesan = cert_cocok(ip)

    proyek = argv[argv.index("--proyek") + 1] if "--proyek" in argv else PROYEK_ANDROID
    disalin = salin_cert(proyek) if ok else None

    status = f"cocok untuk {ip}" if ok else f"PERLU DIPERIKSA — {pesan}"
    perintah = "QSHIELD_AUTH=off "

    with open(KELUARAN, "w") as f:
        f.write(TEMPLATE.format(base_url=base_url, app_id=app_id,
                                status_cert=status, perintah_cert=perintah))

    print("=" * 66)
    print("PROMPT SIAP")
    print("=" * 66)
    print()
    print(f"  berkas         : {os.path.relpath(KELUARAN, AKAR)}")
    print(f"  alamat server  : {base_url}")
    print(f"  application id : {app_id}")
    print(f"  sertifikat     : {status}")
    if disalin:
        print(f"  disalin ke     : {os.path.relpath(disalin, proyek)}")
        print("                   (build ulang APK — tidak perlu pasang di setelan HP)")
    elif os.path.isdir(proyek):
        print("  sertifikat tidak disalin — perbaiki dulu")
    print()
    print("  Buka berkasnya, salin blok di dalam ``` ke agent.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
