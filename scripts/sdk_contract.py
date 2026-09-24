"""Seam SDK native <-> backend Q-Shield.

Dua perintah, dan keduanya dibuat supaya penulis SDK bisa bekerja
TANPA menunggu tim backend:

    python scripts/sdk_contract.py generate
        Menulis ulang sdk/contract/ dari kode yang sedang berjalan.
        Fixture-nya bukan contoh yang diketik tangan — ia keluaran
        server sungguhan, jadi tidak bisa basi diam-diam.

    python scripts/sdk_contract.py check berkas.json
        Memvalidasi satu permintaan yang DIHASILKAN SDK terhadap model
        pydantic sungguhan, offline, tanpa server hidup. Pesannya
        menyebut constraint yang dilanggar, bukan sekadar "422".

tests/test_sdk_contract.py menjalankan `generate` di memori lalu
membandingkannya dengan isi sdk/contract/. Kalau kontraknya bergeser
tanpa fixture diperbarui, test itu merah — seam-nya menjaga dirinya
sendiri, pola yang sama dengan tests/test_frontend.py.
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

os.environ.setdefault("QSHIELD_AUTH", "off")
os.environ.setdefault("QSHIELD_RATE_LIMIT", "off")

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TUJUAN = os.path.join(AKAR, "sdk", "contract")

LAT, LNG = -6.914744, 107.609810
NMID = "ID1024365478912"
NMID_PALSU = "ID1099887766554"

# Dua field yang TIDAK PERNAH sama dua kali: processing_ms mengukur
# waktu jam dinding, dan verification_ticket memuat cap waktu beserta
# tanda tangannya. Dinormalkan supaya perbandingan drift bermakna;
# bentuk dan tipenya tetap terlihat penulis SDK, dan formatnya
# dijelaskan di sdk/README.md.
NONDETERMINISTIK = ("processing_ms",)
TIKET_CONTOH = "<base64url-klaim>.<base64url-hmac-sha256>"

# `known.last_seen` ikut bergerak: ia mencatat pengamatan TERAKHIR, dan
# skenario ini sendiri yang menjadi pengamatan itu. Dinormalkan dengan
# alasan yang sama seperti tiket — yang perlu dilihat penulis SDK adalah
# bentuk dan tipenya, bukan jam berapa fixture dibuat.
WAKTU_CONTOH = "<iso-8601-utc>"


def _qr(nmid=NMID, pan="936000149000000001", nama="WARUNG BU SRI"):
    from qshield import emvco
    acct = emvco.build_tlv({
        "00": "ID.CO.QRIS.WWW", "01": pan, "02": nmid, "03": "UMI"})
    return emvco.build({
        "00": "01", "01": "11", "26": acct, "52": "5812", "53": "360",
        "58": "ID", "59": nama, "60": "BANDUNG", "61": "40257"})


def _klien():
    """Store yang di-seed persis sama setiap kali, supaya deterministik."""
    from fastapi.testclient import TestClient
    from qshield import api
    from qshield.store import Store

    sekarang = datetime(2026, 1, 1, tzinfo=timezone.utc)
    api.store = Store(os.path.join(tempfile.mkdtemp(), "sdk.db"))
    api.store.seed_binding(
        nmid=NMID, lat=LAT, lng=LNG, merchant_name="WARUNG BU SRI",
        observer_count=47,
        first_seen=sekarang - timedelta(days=180),
        last_seen=sekarang - timedelta(hours=6))
    return TestClient(api.app)


# Tiap skenario: (nama berkas, keterangan, badan permintaan).
# Dipilih supaya penulis SDK punya satu fixture untuk SETIAP tier aksi
# dan SETIAP status integritas yang mungkin dikembalikan.
def _skenario():
    dasar = {"payload": _qr(), "lat": LAT, "lng": LNG,
             "device_anon_id": "11111111-2222-4333-8444-555555555555",
             "accuracy_m": 8.5}

    def dengan(**ubah):
        b = dict(dasar)
        b.update(ubah)
        return b

    return [
        ("01-web-tanpa-integritas",
         "Klien web. Blok device_integrity tidak dikirim sama sekali — "
         "TIDAK ada penalti, dan ketiadaannya diungkapkan sebagai "
         "'not_provided'.",
         dengan()),

        ("02-android-attested",
         "Jalur bahagia SDK Android: bersih, dan attestation sudah "
         "diverifikasi DI SERVER PJP sebelum nilai ini dikirim.",
         dengan(device_integrity={
             "mock_location": False, "rooted": False,
             "attested": True, "platform": "android"})),

        ("03-android-dilaporkan-tanpa-attestation",
         "SDK melaporkan apa yang bisa dibacanya, tapi attestation "
         "belum diverifikasi. Status 'reported', bukan 'attested'.",
         dengan(device_integrity={
             "mock_location": False, "rooted": False, "platform": "android"})),

        ("04-android-perangkat-di-root",
         "rooted: true -> status 'failed' dan skor Layer 2 naik.",
         dengan(device_integrity={
             "mock_location": False, "rooted": True,
             "attested": True, "platform": "android"})),

        ("05-android-attestation-gagal",
         "attested: false -> 'failed'. Berbeda dari tidak mengirim "
         "field-nya sama sekali, yang tidak dihukum.",
         dengan(device_integrity={
             "mock_location": False, "rooted": False,
             "attested": False, "platform": "android"})),

        ("06-android-mock-location",
         "mock_location: true -> putusan LOKASI ditolak sama sekali, "
         "bukan sekadar diberi skor. Invarian §6.",
         dengan(device_integrity={
             "mock_location": True, "rooted": False,
             "attested": True, "platform": "android"})),

        ("07-akurasi-gps-buruk",
         "accuracy_m > 100 -> Layer 1 tidak dijalankan. Sistem menolak "
         "memberi putusan lokasi; itu fitur, bukan kegagalan.",
         dengan(accuracy_m=250.0, device_integrity={
             "mock_location": False, "rooted": False,
             "attested": True, "platform": "android"})),

        ("10-dipindai-dari-gambar",
         "from_image: true — payload dibaca dari GAMBAR, jadi koordinat "
         "pemindai tidak mewakili lokasi QR. Layer 1 tidak dijalankan, "
         "tidak ada jangkar yang ditanam, dan `known` berisi apa yang "
         "sudah diamati atas Merchant ID ini. Pakai ini untuk alur "
         "scan-dari-galeri; tanpanya tiap pembayaran jarak jauh menanam "
         "jangkar palsu di lokasi pembayar.",
         dengan(from_image=True, device_integrity={
             "mock_location": False, "rooted": False,
             "attested": True, "platform": "android"})),

        ("09-bedah-tlv-mode-demo",
         "include_tlv: true — bedah TLV lengkap, termasuk tag bersarang "
         "26 yang terurai jadi GUID/PAN/NMID/kriteria. Biarkan false di "
         "build produksi: tanggapannya membengkak ~4x.",
         dengan(include_tlv=True, device_integrity={
             "mock_location": False, "rooted": False,
             "attested": True, "platform": "android"})),

        ("08-anomali-stiker-palsu",
         "NMID berbeda di jangkar mapan -> cooling_off. Fixture untuk "
         "menguji tier paling keras di UI SDK.",
         dengan(payload=_qr(nmid=NMID_PALSU, pan="936000149000000002"),
                device_integrity={
                    "mock_location": False, "rooted": False,
                    "attested": True, "platform": "android"})),
    ]


def bangun():
    """Hasilkan seluruh pasangan permintaan-tanggapan, sebagai dict."""
    c = _klien()
    keluar = {}
    for nama, keterangan, badan in sorted(_skenario()):
        r = c.post("/api/v1/verify", json=badan)
        d = r.json()
        for k in NONDETERMINISTIK:
            if k in d:
                d[k] = 0
        if d.get("verification_ticket"):
            d["verification_ticket"] = TIKET_CONTOH
        if d.get("known") and d["known"].get("last_seen"):
            d["known"]["last_seen"] = WAKTU_CONTOH
        keluar[nama] = {
            "_keterangan": keterangan,
            "status_http": r.status_code,
            "permintaan": badan,
            "tanggapan": d,
        }
    return keluar


def _tulis(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def generate():
    os.makedirs(TUJUAN, exist_ok=True)
    data = bangun()
    for nama, isi in data.items():
        _tulis(os.path.join(TUJUAN, f"{nama}.json"), isi)

    from qshield.api import app
    skema = app.openapi()["components"]["schemas"]
    _tulis(os.path.join(TUJUAN, "skema-openapi.json"),
           {n: skema[n] for n in
            ("VerifyRequest", "DeviceIntegrity", "VerifyResponse",
             "MerchantOut", "LayerScores") if n in skema})

    print(f"{len(data)} fixture + skema ditulis ke sdk/contract/")
    for nama in sorted(data):
        d = data[nama]["tanggapan"]
        print(f"  {nama:<42} {d.get('action', '-'):<12} "
              f"integritas={d.get('device_integrity', '-')}")
    return 0


# --- Pemeriksa payload SDK -----------------------------------------
#
# Kesalahan yang PALING SERING dibuat klien Android, masing-masing
# dengan kalimat yang menyebut penyebabnya — bukan sekadar melempar
# ulang pesan pydantic.
PETUNJUK = {
    "device_anon_id": (
        "UUID acak per perangkat. Pola ^[A-Za-z0-9_-]{8,64}$ — "
        "UUID.randomUUID().toString() cocok. JANGAN pakai ANDROID_ID, "
        "IMEI, atau apa pun yang menempel pada orangnya."),
    "accuracy_m": (
        "WAJIB, bukan opsional. Location.getAccuracy() dalam meter. "
        "Menghilangkannya adalah pintu keluar dari invarian §6, jadi "
        "permintaannya ditolak di batas sistem, bukan diberi skor."),
    "payload": (
        "String QRIS mentah apa adanya dari kamera, maksimal 1024 "
        "karakter ASCII yang bisa dicetak. Jangan di-trim, jangan "
        "di-decode ulang, jangan diubah huruf besar-kecilnya."),
    "lat": "Derajat desimal, -90..90.",
    "lng": "Derajat desimal, -180..180.",
    "location_source": "'live' atau 'replay' saja.",
    "device_integrity": (
        "Objek opsional. platform harus salah satu dari "
        "android/ios/web/other."),
}


def check(path):
    from pydantic import ValidationError
    from qshield.api import VerifyRequest

    try:
        with open(path, encoding="utf-8") as f:
            badan = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"GAGAL membaca {path}: {exc}")
        return 2

    try:
        req = VerifyRequest(**badan)
    except ValidationError as exc:
        print(f"DITOLAK — {len(exc.errors())} masalah di {path}:\n")
        for e in exc.errors():
            field = ".".join(str(b) for b in e["loc"]) or "(akar)"
            print(f"  {field}")
            print(f"      {e['msg']}")
            akar = str(e["loc"][0]) if e["loc"] else ""
            if akar in PETUNJUK:
                print(f"      -> {PETUNJUK[akar]}")
            print()
        return 1

    print(f"DITERIMA — {path} lolos validasi VerifyRequest.\n")

    di = req.device_integrity
    if di is None:
        print("  Catatan: blok device_integrity tidak dikirim. Itu SAH dan "
              "tidak dihukum;\n  tanggapan akan menyebut "
              "device_integrity: \"not_provided\".")
    elif di.attested is True:
        # Peringatan terpenting di berkas ini. Tidak bisa ditegakkan
        # backend — Q-Shield tidak punya cara memverifikasinya — jadi
        # satu-satunya tempat ia bisa disebut adalah di sini.
        print("  PERIKSA ULANG: attested=true.\n"
              "  Nilai ini TIDAK BOLEH ditetapkan dari dalam aplikasi. Token "
              "Play Integrity\n"
              "  harus diverifikasi di server PJP lebih dulu, dan baru "
              "server itu yang berhak\n"
              "  menyatakan true. Mengirim true langsung dari perangkat "
              "memindahkan risiko\n"
              "  ke pengguna Anda sendiri — lihat docs/INTEGRATION.md §3.")
    return 0


def main(argv):
    if len(argv) >= 2 and argv[1] == "generate":
        return generate()
    if len(argv) >= 3 and argv[1] == "check":
        return check(argv[2])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
