"""
Suite adversarial — sistem diuji dari sisi penyerang.

Berbeda dari test_binding.py yang menguji "apakah aturannya jalan",
berkas ini menguji "apakah aturannya bisa ditembus". Tiap skenario
ditulis sebagai serangan dengan tujuan yang jelas, lalu diperiksa
apakah sistem menahannya.

Bagian terakhir sengaja berisi serangan yang MEMANG BELUM ditahan.
Untuk itu yang diuji bukan "apakah tertangkap" melainkan "apakah
sistem tetap jujur" — batasan yang diketahui tidak boleh berubah
jadi klaim aman. Itu bentuk kegagalan yang paling berbahaya.

    python tests/test_adversarial.py
"""

import os

# Test ini sengaja membanjiri API, jadi pembatasan laju dimatikan di sini,
# begitu juga autentikasi klien — keduanya diuji tersendiri di
# tests/test_hardening.py.
os.environ["QSHIELD_RATE_LIMIT"] = "off"
os.environ["QSHIELD_AUTH"] = "off"


import sys
import tempfile
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from qshield import api, emvco
from qshield import binding as bd
from qshield.store import Store


def _iso_uji(dt):
    return dt.isoformat()

NOW = datetime.now(timezone.utc)

LAT, LNG = -6.914744, 107.609810
KORBAN = "ID1024365478912"
PENYERANG = "ID1099887766554"
TETANGGA = "ID1077778888999"

_hasil = []


def serangan(nama, ditahan=True):
    """Daftarkan satu skenario. ditahan=False untuk batasan yang diakui."""
    def deco(fn):
        try:
            _hasil.append((nama, ditahan, True, fn() or ""))
        except AssertionError as exc:
            _hasil.append((nama, ditahan, False, str(exc)))
        return fn
    return deco


def fresh_store():
    """Store baru berisi satu warung mapan sebagai korban."""
    s = Store(os.path.join(tempfile.mkdtemp(), "adv.db"))
    s.seed_binding(
        nmid=KORBAN, lat=LAT, lng=LNG, merchant_name="WARUNG BU SRI",
        observer_count=47,
        first_seen=NOW - timedelta(days=180),
        last_seen=NOW - timedelta(hours=6),
    )
    api.store = s
    return s, TestClient(api.app)


def qr(nmid, pan="936000149000000002", extra=None, nama="WARUNG BU SRI",
       statis=True):
    acct = emvco.build_tlv({
        "00": "ID.CO.QRIS.WWW", "01": pan, "02": nmid, "03": "UMI",
    })
    fields = {
        "00": "01", "01": "11" if statis else "12", "26": acct, "52": "5812",
        "53": "360", "58": "ID", "59": nama, "60": "BANDUNG", "61": "40257",
    }
    fields.update(extra or {})
    return emvco.build(fields)


# Klien sungguhan selalu punya coords.accuracy dari Geolocation API,
# jadi helper ini pun mengirimkannya secara bawaan.
AKURASI_WAJAR = 12.0


def scan(client, payload, lat=LAT, lng=LNG, device="penyerang-0001",
         acc=AKURASI_WAJAR):
    body = {"payload": payload, "lat": lat, "lng": lng,
            "device_anon_id": device, "accuracy_m": acc}
    return client.post("/api/v1/verify", json=body).json()


@serangan("Sticker swap di jangkar mapan")
def _a1():
    _, c = fresh_store()
    d = scan(c, qr(PENYERANG))
    assert d["verdict"] == "anomaly", f"swap lolos sebagai {d['verdict']}"
    assert d["action"] == "cooling_off", f"friksi cuma {d['action']}"
    assert "nmid_changed_at_anchor" in d["signals"]
    return f"skor {d['risk_score']} -> {d['action']}"


@serangan("Sticker swap sambil menggeser titik GPS 20-45 m")
def _a2():
    import math
    import random
    random.seed(3)
    _, c = fresh_store()
    lolos = 0
    for _ in range(60):
        jarak = random.uniform(0, 45)
        sudut = random.uniform(0, 2 * math.pi)
        dlat = (jarak * math.cos(sudut)) / 111320
        dlng = (jarak * math.sin(sudut)) / (111320 * math.cos(math.radians(LAT)))
        d = scan(c, qr(PENYERANG), lat=LAT + dlat, lng=LNG + dlng,
                 device="penyerang-0001")
        if d["verdict"] != "anomaly":
            lolos += 1
    assert lolos == 0, f"{lolos}/60 pergeseran berhasil menghindari deteksi"
    return "60 posisi dalam radius 45 m, tidak satu pun lolos"


@serangan("Membangun reputasi lewat pemindaian anomali berulang")
def _a3():
    s, c = fresh_store()
    sebelum = c.get("/api/v1/health").json()
    for i in range(25):
        scan(c, qr(PENYERANG), device=f"penyerang-{i:04d}")
    sesudah = c.get("/api/v1/health").json()

    assert sesudah["observations"] == sebelum["observations"], (
        f"observations naik jadi {sesudah['observations']}"
    )
    assert sesudah["bindings"] == sebelum["bindings"], (
        f"binding baru terbentuk: {sesudah['bindings']}"
    )
    # Dan setelah 25 percobaan, NMID penyerang tetap tidak dikenal.
    d = scan(c, qr(PENYERANG), device="penyerang-9999")
    assert d["verdict"] == "anomaly"
    return f"25 percobaan, observations tetap {sesudah['observations']}"


@serangan("Priming pelan di lokasi kosong lalu klaim verified")
def _a4():
    s = Store(os.path.join(tempfile.mkdtemp(), "prime.db"))
    api.store = s
    c = TestClient(api.app)
    # Lokasi perawan: tidak ada jangkar, jadi tidak ada konflik.
    jauh_lat, jauh_lng = -8.6500, 115.2167
    aksi = []
    for i in range(30):
        d = scan(c, qr(PENYERANG), lat=jauh_lat, lng=jauh_lng,
                 device=f"boneka-{i:04d}")
        aksi.append((d["verdict"], d["action"]))

    assert all(v != "verified" for v, _ in aksi), (
        "binding mencapai verified tanpa menunggu ambang usia"
    )
    assert all(a != "proceed" for _, a in aksi), (
        "status unknown diberi proceed — ketiadaan bukti jadi kepercayaan"
    )
    return f"30 device boneka: tetap {aksi[-1][0]}/{aksi[-1][1]}"


@serangan("Akurasi GPS dipalsukan tinggi untuk melewati Layer 1")
def _a5():
    _, c = fresh_store()
    for acc in (150, 900, 50000):
        d = scan(c, qr(PENYERANG), acc=acc)
        assert d["verdict"] != "verified", f"akurasi {acc} -> verified"
        assert d["action"] != "proceed", f"akurasi {acc} -> proceed"
    return "150/900/50000 m tidak satu pun menghasilkan proceed"


@serangan("Payload cacat disembunyikan di balik akurasi GPS buruk")
def _a6():
    _, c = fresh_store()
    d = scan(c, qr(PENYERANG, extra={"54": "500000.00"}), acc=800)
    assert d["verdict"] == "anomaly", (
        f"kontradiksi struktural ikut hilang saat GPS buruk ({d['verdict']})"
    )
    assert "static_qr_with_amount" in d["signals"]
    return "GPS buruk tidak menutupi cacat bentuk payload"


@serangan("Meracuni jangkar merchant jujur (denial of service)")
def _a7():
    s, c = fresh_store()
    s.seed_binding(
        nmid=TETANGGA, lat=LAT - 0.00007, lng=LNG, merchant_name="TOKO SEBELAH",
        observer_count=30,
        first_seen=NOW - timedelta(days=90), last_seen=NOW - timedelta(hours=2),
    )
    for i in range(15):
        scan(c, qr(PENYERANG), device=f"penyerang-{i:04d}")

    # Nama di QR harus cocok dengan nama di bindingnya. Versi pertama
    # pemeriksaan ini memakai nama bawaan helper untuk KEDUA merchant,
    # sehingga tetangganya tampak berganti nama — dan sinyal
    # nmid_name_inconsistent menandainya, dengan benar. Fixture yang
    # ceroboh, bukan kode yang salah.
    korban = scan(c, qr(KORBAN, pan="936000149000000001",
                        nama="WARUNG BU SRI"), device="pelanggan-0001")
    sebelah = scan(c, qr(TETANGGA, pan="936000149000000003",
                         nama="TOKO SEBELAH"),
                   lat=LAT - 0.00007, device="pelanggan-0002")

    assert korban["layers"]["behavior"] == 0, (
        f"merchant jujur kena skor Layer 2 {korban['layers']['behavior']}"
    )
    assert korban["action"] == "proceed", f"korban diberi {korban['action']}"
    assert sebelah["layers"]["behavior"] == 0, (
        f"merchant sebelah kena skor Layer 2 {sebelah['layers']['behavior']}"
    )
    assert sebelah["action"] == "proceed", f"tetangga diberi {sebelah['action']}"
    return "15 serangan, kedua merchant sah tetap proceed dengan L2 = 0"


@serangan("QR dicetak ulang: CRC ditambal agar cocok")
def _a8():
    _, c = fresh_store()
    # Penyerang menyusun ulang payload dan menghitung CRC yang benar,
    # jadi pemeriksaan CRC saja tidak akan menangkapnya.
    p = qr(PENYERANG)
    assert emvco.parse(p).crc_valid, "prasyarat: CRC memang valid"
    d = scan(c, p)
    assert d["verdict"] == "anomaly", "CRC valid membuat swap lolos"
    return "CRC valid tidak menyelamatkan swap — jangkar yang menangkap"


@serangan("Merchant ID dipalsukan agar tidak sesuai format QRIS")
def _a9():
    _, c = fresh_store()
    for buruk in ("ID99", "XX1024365478912", "ID10243654789123456"):
        d = scan(c, qr(buruk), lat=-8.65, lng=115.2167)
        assert d["verdict"] == "anomaly", f"NMID '{buruk}' lolos"
        assert "malformed_nmid" in d["signals"]
    return "tiga bentuk NMID cacat, semua ditolak"


@serangan("Kode negara cacat bentuk — tanpa menghakimi negaranya")
def _a14():
    _, c = fresh_store()

    # Parser sudah lama mengambil tag 58, dan MANDATORY_TAGS sudah
    # menuntut KEHADIRANNYA — tapi nilainya dulu tidak pernah dibaca
    # siapa pun, jadi tag yang hadir tapi cacat lolos tanpa sinyal.
    for buruk in ("IDN", "I", "1D", "I2", "ID1", ""):
        d = scan(c, qr(PENYERANG, extra={"58": buruk}),
                 lat=-8.65, lng=115.2167)
        assert d["verdict"] == "anomaly", f"kode negara '{buruk}' lolos"
        assert "malformed_country" in d["signals"], (
            f"'{buruk}' tidak memicu malformed_country: {d['signals']}")

    # Dan yang TIDAK boleh dihukum. Baris "SG" yang paling penting:
    # godaan besarnya adalah menuntut tag 58 == "ID", dan cek kebijakan
    # itu berbobot W_STRUCTURAL serta memaksa anomaly — ia akan
    # menghukum payload sah dengan bobot penuh. QRIS punya
    # keterhubungan lintas negara, jadi yang diperiksa BENTUKNYA saja.
    # Padding dan huruf kecil ikut ditoleransi: penyimpangan penulisan,
    # bukan kontradiksi.
    for wajar in ("ID", "ID ", " ID", "id", "SG"):
        d = scan(c, qr(KORBAN, pan="936000149000000001",
                       extra={"58": wajar}), device="pelanggan-0001")
        assert "malformed_country" not in d["signals"], (
            f"'{wajar}' dihukum padahal bentuknya sah: {d['signals']}")
    return ("enam bentuk cacat ditolak; padding, huruf kecil, dan "
            "negara lain lolos bersih")


@serangan("Layer 2 dipakai memutihkan lokasi yang mencurigakan")
def _a10():
    _, c = fresh_store()
    bersih = scan(c, qr(PENYERANG))
    # Payload yang sempurna bersih tidak boleh MENURUNKAN skor Layer 1.
    assert bersih["risk_score"] >= bersih["layers"]["location"], (
        "Layer 2 mengurangi skor Layer 1"
    )
    assert bersih["layers"]["behavior"] >= 0
    assert bersih["verdict"] == "anomaly", "Layer 2 mencabut anomaly Layer 1"
    return "payload bersih tidak menurunkan skor maupun mencabut anomaly"


@serangan("Akurasi GPS dikarang di bawah batas fisik perangkat")
def _a12():
    _, c = fresh_store()
    # Pemalsu yang mengarang angka sering lupa bahwa angkanya harus
    # mungkin. GNSS ponsel tidak pernah melaporkan radius di bawah 1 m.
    for acc in (0, 0.1, 0.5, 0.99):
        d = scan(c, qr(KORBAN, pan="936000149000000001"),
                 device="pemalsu-akurasi", acc=acc)
        assert "implausible_accuracy" in d["signals"], (
            f"akurasi {acc} m lolos tanpa sinyal"
        )
        assert d["verdict"] != "verified", f"akurasi {acc} m tetap verified"

    # Akurasi yang wajar tidak boleh ikut tertandai.
    for acc in (1.0, 3, 8, 25, 99):
        d = scan(c, qr(KORBAN, pan="936000149000000001"),
                 device="pengguna-jujur", acc=acc)
        assert "implausible_accuracy" not in d["signals"], (
            f"akurasi wajar {acc} m ditandai palsu"
        )
    return "0-0,99 m ditandai; 1-99 m lolos bersih"


@serangan("Akurasi dihilangkan untuk melewati invarian akurasi GPS")
def _a13():
    _, c = fresh_store()
    # Kalau accuracy_m opsional, penyerang yang fix-nya buruk tinggal
    # tidak mengirimkannya dan pemeriksaan ">100 m" tidak pernah jalan.
    r = c.post("/api/v1/verify", json={
        "payload": qr(KORBAN, pan="936000149000000001"),
        "lat": LAT, "lng": LNG, "device_anon_id": "penyembunyi-01"})
    assert r.status_code == 422, (
        f"permintaan tanpa accuracy_m diterima (HTTP {r.status_code}) — "
        f"pintu keluar dari invarian §6 terbuka"
    )
    return "permintaan tanpa accuracy_m ditolak 422 di batas sistem"


@serangan("Satu QR dinamis disebar ke banyak korban")
def _a14():
    _, c = fresh_store()

    def dinamis(tagihan, nominal="250000.00"):
        acct = emvco.build_tlv({
            "00": "ID.CO.QRIS.WWW", "01": "936000149000000002",
            "02": PENYERANG, "03": "UMI"})
        return emvco.build({
            "00": "01", "01": "12", "26": acct, "52": "5812", "53": "360",
            "54": nominal, "58": "ID", "59": "TOKO ONLINE", "60": "BANDUNG",
            "62": emvco.build_tlv({"01": tagihan})})

    p = dinamis("INV-9999")
    lokasi = [(LAT, LNG), (-6.9200, 107.6150), (-6.9350, 107.6300),
              (-6.9000, 107.5900), (-6.8900, 107.6500)]
    hasil = [scan(c, p, lat=la, lng=ln, device=f"korban-{i:04d}")
             for i, (la, ln) in enumerate(lokasi)]

    # Korban PERTAMA tidak bisa dilindungi — QR itu belum punya riwayat
    # apa pun. Itu batasan yang sama dengan cold start, dan diakui.
    assert all(h["action"] == "cooling_off" for h in hasil[1:]), (
        f"korban berikutnya lolos: {[h['action'] for h in hasil[1:]]}")
    assert "dynamic_qr_spread" in hasil[1]["signals"]
    return (f"korban ke-1 lolos (tanpa riwayat), korban ke-2 dst "
            f"dihentikan — {len(lokasi) - 1} dari {len(lokasi)}")


@serangan("Stiker statis tidak ikut tertuduh dipakai ulang")
def _a15():
    _, c = fresh_store()
    # Stiker statis MEMANG dipindai ribuan kali. Kalau sinyal pemakaian
    # ulang bocor ke jalur statis, seluruh merchant sah tertuduh.
    p = qr(KORBAN, pan="936000149000000001")
    for i in range(40):
        d = scan(c, p, device=f"pelanggan-{i:04d}")
    dinamis = [s for s in d["signals"] if "dynamic" in s]
    assert not dinamis, f"stiker statis kena sinyal dinamis: {dinamis}"
    assert d["action"] == "proceed", f"40 pemindaian sah -> {d['action']}"
    return "40 pemindaian stiker statis, nol sinyal pemakaian ulang"


@serangan("QR dinamis sah yang dipindai ulang di kasir yang sama")
def _a16():
    _, c = fresh_store()
    acct = emvco.build_tlv({
        "00": "ID.CO.QRIS.WWW", "01": "936000149000000001",
        "02": KORBAN, "03": "UMI"})
    p = emvco.build({
        "00": "01", "01": "12", "26": acct, "52": "5812", "53": "360",
        "54": "50000.00", "58": "ID", "59": "WARUNG BU SRI", "60": "BANDUNG",
        "62": emvco.build_tlv({"01": "INV-0042"})})

    # Tiga percobaan di kasir yang sama: kamera gagal fokus, dibatalkan,
    # lalu berhasil. Galat GPS-nya belasan meter, bukan kilometer.
    for i in range(3):
        d = scan(c, p, lat=LAT + 0.00008 * i, device="pembeli-0001")
        assert d["action"] == "proceed", (
            f"percobaan ke-{i + 1} di kasir yang sama -> {d['action']}")
    return "3 percobaan di satu kasir tetap proceed"


@serangan("Stiker luar kota ditempel di warung — PEMINDAIAN PERTAMA")
def _a17():
    s_, c = fresh_store()

    def q(nmid, nama, kota):
        acct = emvco.build_tlv({
            "00": "ID.CO.QRIS.WWW", "01": "93600899" + nmid[-10:],
            "02": nmid, "03": "UMI"})
        return emvco.build({
            "00": "01", "01": "11", "26": acct, "52": "5812", "53": "360",
            "58": "ID", "59": nama, "60": kota, "61": "40257"})

    # Wilayah harus dikenal dulu. Sebelum itu sistem WAJIB diam —
    # ketiadaan pengetahuan bukan izin menuduh (invarian §2).
    d = scan(c, q("ID1000000000001", "ES BUAH", "JAKARTA"),
             lat=LAT + 0.03, device="warga-0001")
    assert "city_mismatch" not in d["signals"], (
        "menuduh padahal wilayahnya belum dikenal")

    for i in range(2, 10):
        scan(c, q(f"ID10000000000{i:02d}", f"TOKO {i}", "BANDUNG"),
             lat=LAT + 0.03 + i * 2e-4, device=f"warga-{i:04d}")

    # Sekarang: stiker luar kota, pemindaian PERTAMA, tanpa riwayat
    # apa pun tentang merchant itu.
    d = scan(c, q("ID1000000000099", "ES BUAH PAK ASEP", "JAKARTA"),
             lat=LAT + 0.03, device="warga-9999")
    assert "city_mismatch" in d["signals"], (
        f"stiker luar kota lolos pada scan pertama: {d['signals']}")
    assert d["action"] in ("step_up", "cooling_off"), (
        f"friksi cuma {d['action']}")

    # Merchant Bandung yang benar-benar baru TIDAK boleh ikut kena.
    bersih = scan(c, q("ID1000000000088", "WARUNG BARU", "BANDUNG"),
                  lat=LAT + 0.03, device="warga-8888")
    assert "city_mismatch" not in bersih["signals"], (
        "merchant sah yang baru ikut tertuduh")
    return f"tertangkap pada scan pertama -> {d['action']}; merchant sah bersih"


@serangan("Meracuni pengetahuan wilayah dengan pemindaian berulang")
def _a18():
    s_, c = fresh_store()

    def q(nmid, kota):
        acct = emvco.build_tlv({
            "00": "ID.CO.QRIS.WWW", "01": "93600899" + nmid[-10:],
            "02": nmid, "03": "UMI"})
        return emvco.build({
            "00": "01", "01": "11", "26": acct, "52": "5812", "53": "360",
            "58": "ID", "59": "X", "60": kota, "61": "40257"})

    for i in range(2, 10):
        scan(c, q(f"ID10000000000{i:02d}", "BANDUNG"),
             lat=LAT + 0.03 + i * 2e-4, device=f"warga-{i:04d}")

    # Penyerang membanjiri wilayah dengan satu stiker "JAKARTA".
    for i in range(400):
        scan(c, q("ID1000000000099", "JAKARTA"), lat=LAT + 0.03,
             device=f"racun-{i:05d}")

    kota, setuju, total = s_.area_city(LAT + 0.03, LNG)
    assert kota == "BANDUNG", (
        f"pengetahuan wilayah berhasil diracuni jadi {kota}")
    return (f"400 pemindaian racun, wilayah tetap {kota} "
            f"({setuju}/{total} NMID) — yang dihitung NMID, bukan pemindaian")


@serangan("Satu NMID dipakai untuk banyak korban dengan nama berbeda")
def _a19():
    s_, c = fresh_store()

    def q(nmid, nama):
        acct = emvco.build_tlv({
            "00": "ID.CO.QRIS.WWW", "01": "93600899" + nmid[-10:],
            "02": nmid, "03": "UMI"})
        return emvco.build({
            "00": "01", "01": "11", "26": acct, "52": "5812", "53": "360",
            "58": "ID", "59": nama, "60": "BANDUNG", "61": "40257"})

    N = "ID1000000000077"
    scan(c, q(N, "LAUNDRY KILAT"), lat=LAT + 0.02, device="korban-0001")
    d = scan(c, q(N, "ES BUAH PAK ASEP"), lat=LAT + 0.05, device="korban-0002")
    assert "nmid_name_inconsistent" in d["signals"], (
        f"satu NMID dua nama lolos: {d['signals']}")
    assert d["action"] == "cooling_off"

    # Merchant sah yang namanya konsisten tidak boleh kena.
    scan(c, q("ID1000000000066", "TOKO KONSISTEN"), lat=LAT + 0.07,
         device="warga-0001")
    bersih = scan(c, q("ID1000000000066", "TOKO KONSISTEN"), lat=LAT + 0.07,
                  device="warga-0002")
    assert "nmid_name_inconsistent" not in bersih["signals"]
    return "dua nama -> cooling_off; nama konsisten tetap bersih"


@serangan("Cacat payload tidak menandai LOKASI sebagai diserang")
def _a27():
    s_, c = fresh_store()

    # Memindai QR yang cacat payload-nya di suatu titik tidak boleh
    # membuat titik itu tercatat sebagai sasaran serangan — cacat
    # payload tidak mengatakan apa pun tentang tempatnya.
    #
    # Ditemukan dari lapangan: tujuh merchant sungguhan di satu meja,
    # dan satu QR scam bercacat membuat keenam merchant sah lainnya
    # berakhir "butuh verifikasi".
    JAUH = (-8.6500, 115.2167)
    for i in range(4):
        cacat = qr(f"ID{i}", pan="936000149000000009")   # NMID cacat bentuk
        d = scan(c, cacat, lat=JAUH[0], lng=JAUH[1], device=f"scam-{i:04d}")
        assert d["verdict"] == "anomaly", f"QR cacat lolos: {d['signals']}"

    baris = s_.conn.execute(
        "SELECT COALESCE(SUM(anomaly_attempts), 0) n FROM bindings").fetchone()
    assert baris["n"] == 0, (
        f"{baris['n']} percobaan tercatat dari cacat payload — merchant sah "
        f"di titik itu akan ikut tertuduh")

    # Merchant sungguhan di titik yang sama harus bersih. NMID-nya
    # dibuat baru — memakai KORBAN akan memicu nmid_second_location
    # karena ia sudah diseed di tempat lain, dan itu mengaburkan apa
    # yang sedang diukur di sini.
    sah = scan(c, qr("ID1055500000001", pan="936000149000000007",
                     nama="ES KELAPA"),
               lat=JAUH[0], lng=JAUH[1], device="warga-jauh-01")
    assert "repeated_anomaly_at_anchor" not in sah["signals"], (
        f"merchant sah mewarisi kecurigaan dari cacat payload: "
        f"{sah['signals']}")
    assert sah["action"] == "warn", f"-> {sah['action']}, bukan warn biasa"
    assert sah["signals"] == ["first_observation"], (
        f"sinyal tak terduga: {sah['signals']}")
    return "4 QR cacat, nol percobaan tercatat, merchant sah bersih"


@serangan("Percobaan pertukaran TETAP menandai lokasinya")
def _a28():
    s_, c = fresh_store()
    # Yang benar-benar berkaitan dengan lokasi harus tetap tercatat.
    for i in range(3):
        d = scan(c, qr(PENYERANG), device=f"penyerang-{i:04d}")
        assert "nmid_changed_at_anchor" in d["signals"]

    baris = s_.conn.execute(
        "SELECT SUM(anomaly_attempts) n FROM bindings").fetchone()
    assert baris["n"] == 3, f"{baris['n']} tercatat, harusnya 3"
    return "3 percobaan pertukaran tercatat di jangkarnya"


@serangan("Jejak serangan lama tidak menghukum merchant baru selamanya")
def _a20():
    from datetime import timedelta as _td

    from qshield import behavior as _bh

    # Jangkar pernah diserang, lalu penyerangnya pergi dan merchant sah
    # membuka usaha di titik yang sama berbulan-bulan kemudian. Ia tidak
    # boleh menanggung sejarah yang bukan miliknya.
    baru = NOW
    for hari, harus_ada in ((0, True), (7, True), (30, False), (90, False)):
        st = _bh.AnchorState(anomaly_attempts=3,
                             last_anomaly_at=baru - _td(days=hari))
        # anchor_has_owner=True: pemeriksaan ini tentang PELURUHAN, dan
        # sinyalnya memang hanya berlaku di jangkar yang sudah bertuan.
        sig = _bh._behavioral_signals(st, False, baru, True)
        ada = any(x.name == "repeated_anomaly_at_anchor" for x in sig)
        assert ada == harus_ada, (
            f"{hari} hari setelah serangan: sinyal "
            f"{'masih ada' if ada else 'hilang'}, seharusnya "
            f"{'ada' if harus_ada else 'pudar'}")

    # Bobotnya harus menurun monoton, bukan melompat.
    bobot = []
    for hari in (0, 1, 3, 7, 14):
        st = _bh.AnchorState(anomaly_attempts=3,
                             last_anomaly_at=baru - _td(days=hari))
        sig = _bh._behavioral_signals(st, False, baru, True)
        bobot.append(sig[0].weight if sig else 0)
    assert bobot == sorted(bobot, reverse=True), f"bobot tidak menurun: {bobot}"
    return f"bobot {bobot} pada hari 0/1/3/7/14, pudar penuh sebelum 30 hari"


@serangan("QR dibangkitkan ulang oleh generator lain")
def _a21():
    s_, c = fresh_store()
    PJP = "93600899"

    def kanonik(nmid, nama):
        acct = emvco.build_tlv({
            "00": "ID.CO.QRIS.WWW", "01": PJP + "0000012345",
            "02": nmid, "03": "UMI"})
        return emvco.build({
            "00": "01", "01": "11", "26": acct, "52": "5812", "53": "360",
            "58": "ID", "59": nama, "60": "BANDUNG", "61": "40257"})

    # Dialek penerbit dipelajari dari merchant-merchant sahnya.
    for i in range(8):
        scan(c, kanonik(f"ID10000000000{i:02d}", f"TOKO {i}"),
             lat=LAT + 0.01 + i * 0.01, device=f"warga-{i:04d}")

    # Penyerang menyusun ulang payload dengan generatornya sendiri:
    # sub-tag beda urutan, CRC huruf kecil. PJP yang diakui sama.
    acct = "".join(f"{t}{len(v):02d}{v}" for t, v in
                   [("00", "ID.CO.QRIS.WWW"), ("02", "ID1000000000099"),
                    ("01", PJP + "0000012345"), ("03", "UMI")])
    body = "".join(f"{t}{len(v):02d}{v}" for t, v in
                   [("00", "01"), ("01", "11"), ("26", acct), ("52", "5812"),
                    ("53", "360"), ("58", "ID"), ("59", "ES BUAH"),
                    ("60", "BANDUNG"), ("61", "40257")]) + "6304"
    palsu = body + emvco.crc16_ccitt(body).lower()

    d = scan(c, palsu, lat=LAT + 0.01, device="penyerang-0001")
    assert "issuer_dialect_deviation" in d["signals"], (
        f"QR dibangkitkan ulang lolos: {d['signals']}")
    assert d["action"] == "cooling_off", f"friksi cuma {d['action']}"

    # Merchant SAH baru dari penerbit yang sama tidak boleh kena.
    bersih = scan(c, kanonik("ID1000000000088", "WARUNG BARU"),
                  lat=LAT + 0.01, device="warga-8888")
    assert "issuer_dialect_deviation" not in bersih["signals"], (
        "merchant sah dari penerbit yang sama ikut tertuduh")
    return "tertangkap pada scan pertama; merchant sah penerbit itu bersih"


@serangan("Nominal QR dinamis diubah, nomor tagihan tetap")
def _a23():
    _, c = fresh_store()

    def dinamis(nominal, tagihan="INV-0042"):
        acct = emvco.build_tlv({
            "00": "ID.CO.QRIS.WWW", "01": "936008990000012345",
            "02": "ID1098765432109", "03": "UMI"})
        return emvco.build({
            "00": "01", "01": "12", "26": acct, "52": "5812", "53": "360",
            "54": nominal, "58": "ID", "59": "TOKO ONLINE", "60": "BANDUNG",
            "62": emvco.build_tlv({"01": tagihan})})

    # Pelanggan memindai QR sah dari kasir.
    sah = scan(c, dinamis("50000.00"), device="pembeli-0001")
    assert "bill_amount_changed" not in sah["signals"]

    # Penipu mencegat, mengubah nominal saja. Hash payload berubah —
    # jadi deteksi pemakaian ulang melewatkannya — tapi nomor
    # tagihannya tetap, dan itu yang menangkapnya.
    d = scan(c, dinamis("500000.00"), device="korban-0001")
    assert "bill_amount_changed" in d["signals"], (
        f"perubahan nominal lolos: {d['signals']}")
    # Alasannya harus menyebut KEDUA nominalnya — itu yang membuat
    # pengguna bisa memeriksanya sendiri ke layar kasir.
    alasan = " ".join(d["reasons"])
    assert "50000.00" in alasan and "500000.00" in alasan, (
        "alasan tidak menyebut kedua nominalnya")

    # Tagihan berbeda dengan nominal berbeda adalah hal normal.
    normal = scan(c, dinamis("75000.00", "INV-0043"), device="pembeli-0002")
    assert "bill_amount_changed" not in normal["signals"], (
        "tagihan berbeda ikut tertuduh")
    return "perubahan nominal tertangkap; tagihan berbeda tetap bersih"


@serangan("Sinyal tagihan tidak menyentuh stiker statis")
def _a24():
    _, c = fresh_store()
    # Stiker statis tidak punya nomor tagihan maupun nominal.
    p = qr(KORBAN, pan="936000149000000001", nama="WARUNG BU SRI")
    for i in range(5):
        d = scan(c, p, device=f"pelanggan-{i:04d}")
    assert "bill_amount_changed" not in d["signals"]
    assert "dynamic_qr_reused" not in d["signals"]
    return "5 pemindaian stiker statis, nol sinyal jalur dinamis"


@serangan("Stiker QR ditempel menutupi standee, teks asli tertinggal")
def _a25():
    s_, c = fresh_store()

    def minta(nmid, printed, dev, lat=LAT):
        body = {"payload": qr(nmid, pan="936000149000000002",
                              nama="WARUNG BU SRI"),
                "lat": lat, "lng": LNG, "device_anon_id": dev,
                "accuracy_m": 12.0}
        if printed:
            body["printed_label"] = printed
        return c.post("/api/v1/verify", json=body).json()

    # Ini modus yang paling sering terjadi: mencetak ulang seluruh
    # standee mahal dan mencolok, jadi penipu menempel stiker QR kecil
    # menutupi kodenya saja. Teks tercetak yang asli tetap terlihat.
    d = minta(PENYERANG, {"nmid": KORBAN}, "korban-0001")
    assert "printed_nmid_mismatch" in d["signals"], (
        f"ketidakcocokan teks tercetak lolos: {d['signals']}")
    assert d["action"] == "cooling_off"

    # Yang paling penting: bekerja di lokasi yang BELUM DIKENAL, pada
    # pemindaian pertama, tanpa riwayat apa pun tentang merchant itu.
    baru = minta(PENYERANG, {"nmid": KORBAN}, "korban-0002", lat=-8.6500)
    assert "printed_nmid_mismatch" in baru["signals"]
    assert baru["action"] == "cooling_off", (
        f"di lokasi baru cuma {baru['action']} — cold start belum tertutup")
    assert "tercetak" in baru["reasons"][0], (
        "alasan terkuat bukan di baris pertama")
    return "tertangkap pada scan pertama di lokasi yang belum dikenal"


@serangan("Teks tercetak yang cocok tidak menimbulkan tuduhan")
def _a26():
    s_, c = fresh_store()

    def minta(printed, dev):
        body = {"payload": qr(KORBAN, pan="936000149000000001",
                              nama="WARUNG BU SRI"),
                "lat": LAT, "lng": LNG, "device_anon_id": dev,
                "accuracy_m": 12.0}
        if printed:
            body["printed_label"] = printed
        return c.post("/api/v1/verify", json=body).json()

    for label, printed in (
            ("cocok persis", {"nmid": KORBAN, "merchant_name": "WARUNG BU SRI"}),
            ("tanpa awalan ID", {"nmid": KORBAN[2:]}),
            ("nama beda kapital", {"merchant_name": "warung  bu sri"}),
            ("tidak diisi", None)):
        d = minta(printed, f"warga-{abs(hash(label)) % 9999:04d}")
        salah = [x for x in d["signals"] if "printed" in x]
        assert not salah, f"{label}: tertuduh padahal cocok — {salah}"
    return "cocok persis, tanpa awalan ID, beda kapital, kosong — semua bersih"


@serangan("Menang balapan cold start dengan modal murah (R10)")
def _a11():
    s, c = fresh_store()

    # Jangkar yang korbannya sudah mapan tidak bisa dibajak lewat API:
    # tiap pemindaian jadi anomaly, dan anomaly tidak pernah dicatat.
    for i in range(10):
        scan(c, qr(PENYERANG), device=f"penyerang-{i:04d}")
    milik_penyerang = s.conn.execute(
        "SELECT COUNT(*) c FROM bindings WHERE nmid = ?", (PENYERANG,)
    ).fetchone()["c"]
    assert milik_penyerang == 0, (
        f"penyerang berhasil membuat {milik_penyerang} binding lewat API"
    )

    # Skenario R10 yang murah: penyerang menang balapan cold start dan
    # memupuk binding sampai mapan dengan modal seminimal mungkin.
    s.seed_binding(
        nmid=PENYERANG, lat=LAT, lng=LNG, merchant_name="WARUNG BU SRI",
        observer_count=bd.MIN_OBSERVERS,
        first_seen=NOW - timedelta(days=90), last_seen=NOW - timedelta(hours=1),
    )
    d = scan(c, qr(PENYERANG), device="penyerang-9999")
    assert d["verdict"] == "anomaly", (
        f"basis {bd.MIN_OBSERVERS} vs 47 lolos sebagai {d['verdict']} — "
        f"ADJACENT_MIN_RATIO tidak bekerja"
    )
    assert "adjacent_merchant" not in d["signals"], (
        "penyerang modal minimum masih dapat pengecualian koeksistensi"
    )
    return (f"basis {bd.MIN_OBSERVERS} vs 47 tidak lagi lolos sebagai "
            f"merchant bersebelahan (rasio {bd.ADJACENT_MIN_RATIO})")



# ==================================================================
# Batasan yang diakui — di sini yang diuji adalah KEJUJURAN sistem
# ==================================================================

@serangan("Dialek penerbit TIDAK dipakai menuduh sticker-swap", ditahan=False)
def _a22():
    s_, c = fresh_store()
    PJP = "93600899"

    def kanonik(nmid, nama):
        acct = emvco.build_tlv({
            "00": "ID.CO.QRIS.WWW", "01": PJP + "0000012345",
            "02": nmid, "03": "UMI"})
        return emvco.build({
            "00": "01", "01": "11", "26": acct, "52": "5812", "53": "360",
            "58": "ID", "59": nama, "60": "BANDUNG", "61": "40257"})

    for i in range(8):
        scan(c, kanonik(f"ID10000000000{i:02d}", f"TOKO {i}"),
             lat=LAT + 0.01 + i * 0.01, device=f"warga-{i:04d}")

    # Penipu sticker-swap memakai akun merchant SUNGGUHAN dari penerbit
    # yang sama. Payload-nya diterbitkan resmi, jadi dialeknya cocok
    # sempurna — dan sinyal ini memang tidak boleh menangkapnya.
    d = scan(c, kanonik("ID1000000000077", "WARUNG BU SRI"),
             lat=LAT + 0.01, device="penipu-0001")
    assert "issuer_dialect_deviation" not in d["signals"], (
        "prasyarat berubah — dialek kini menandai payload yang sah "
        "diterbitkan? Periksa ulang, itu positif palsu.")
    return ("BUKAN KELEMAHAN: stiker-swap diterbitkan acquirer sungguhan "
            "sehingga dialeknya cocok. Yang menangkapnya adalah jangkar "
            "lokasi, bukan sinyal payload")


@serangan("Koordinat GPS dipalsukan (mock location)", ditahan=False)
def _b1():
    _, c = fresh_store()
    # Penyerang mengaku berada di warung padahal tidak. Server tidak
    # punya cara memverifikasi ini — lihat Batasan 2 di PROCESS-LOG.
    d = scan(c, qr(KORBAN, pan="936000149000000001"), device="pemalsu-0001")
    assert d["verdict"] == "verified", (
        "prasyarat batasan berubah — koordinat palsu kini tertangkap?"
    )
    # Yang penting: batasannya tidak bertambah parah. Koordinat palsu
    # tidak memberi penyerang apa pun untuk NMID YANG BUKAN MILIKNYA.
    d2 = scan(c, qr(PENYERANG), device="pemalsu-0002")
    assert d2["verdict"] == "anomaly", (
        "spoof koordinat memberi keuntungan untuk NMID asing"
    )
    return ("BELUM DITAHAN: butuh device integrity. Tapi spoof tidak "
            "memberi keuntungan untuk NMID asing")


@serangan("Replay QR dinamis yang sudah dipakai", ditahan=False)
def _b2():
    _, c = fresh_store()
    dinamis = qr(KORBAN, pan="936000149000000001",
                 extra={"54": "25000.00"}, statis=False)
    a = scan(c, dinamis, device="pelanggan-0001")
    b = scan(c, dinamis, device="pelanggan-0002")
    assert a["verdict"] == b["verdict"], "prasyarat: tidak ada pelacakan nonce"
    # Sistem tidak mengklaim bisa mendeteksinya, dan tidak boleh
    # memberi sinyal palsu seolah bisa.
    assert "replay" not in " ".join(a["signals"]), "mengklaim deteksi replay"
    return ("BELUM DITAHAN: butuh nonce per transaksi di sisi PJP, "
            "di luar jangkauan lapisan pra-pembayaran")


@serangan("Merchant sah pindah lokasi", ditahan=False)
def _b3():
    _, c = fresh_store()
    d = scan(c, qr(KORBAN, pan="936000149000000001"),
             lat=-6.9000, lng=107.6200, device="pelanggan-0001")
    # Relokasi memicu peringatan sekali — itu memang perilaku yang diakui.
    assert d["verdict"] != "verified", "lokasi baru langsung diklaim verified"
    assert d["action"] != "proceed", "lokasi baru langsung diberi proceed"
    return (f"memicu {d['verdict']}/{d['action']} seperti didokumentasikan — "
            f"perlu jalur konfirmasi merchant")


@serangan("Cold start dengan modal besar (sisa R10)", ditahan=False)
def _b4():
    s, c = fresh_store()
    # Penyerang yang mau mengeluarkan device sebanyak merchant korban
    # tetap lolos. ADJACENT_MIN_RATIO menaikkan biaya, tidak menutup celah.
    s.seed_binding(
        nmid=PENYERANG, lat=LAT, lng=LNG, merchant_name="WARUNG BU SRI",
        observer_count=40,
        first_seen=NOW - timedelta(days=90), last_seen=NOW - timedelta(hours=1),
    )
    d = scan(c, qr(PENYERANG), device="penyerang-kaya-01")
    assert d["verdict"] == "verified", (
        "prasyarat batasan berubah — apakah R10 sudah tertutup penuh? "
        "Perbarui docs/THREAT-MODEL.md R10 dan catatan ini."
    )

    # Ambang biayanya harus persis seperti yang dikalibrasi.
    batas = bd.ADJACENT_MIN_RATIO * 47
    assert bd.MIN_OBSERVERS < batas <= 40, (
        f"biaya penyerang bergeser: butuh >{batas:.0f} device"
    )
    return (f"BELUM DITAHAN SEPENUHNYA: penyerang butuh >{batas:.0f} device "
            f"(naik dari {bd.MIN_OBSERVERS}); penutupan sungguhan menuntut "
            f"deteksi integritas perangkat")


@serangan("Jalur kehadiran tidak membangun reputasi (invarian §3)")
def _a30():
    """Pemindaian yang ditolak tidak boleh menaikkan observer_count.

    Jalur kehadiran menambah tabel baru yang ikut tumbuh saat pemindaian
    ditolak. Kalau suatu saat ia keliru disambungkan ke observer_count,
    stiker palsu akan bisa memupuk reputasi lewat percobaan berulang —
    persis yang dilarang invarian §3.
    """
    s, c = fresh_store()
    for i in range(30):
        d = scan(c, qr(PENYERANG), device=f"korban-{i:05d}")
        assert d["verdict"] == "anomaly", f"swap lolos di percobaan {i}"
    baris = s.conn.execute(
        "SELECT observer_count FROM bindings WHERE nmid = ?", (PENYERANG,)
    ).fetchone()
    punya = baris["observer_count"] if baris else 0
    assert punya == 0, f"reputasi terbangun dari penolakan: {punya} pengamat"
    tantangan = s.conn.execute(
        "SELECT COUNT(*) AS n FROM anchor_challenge WHERE nmid = ?",
        (PENYERANG,)).fetchone()["n"]
    assert tantangan == 30, f"buku tantangan tidak lengkap: {tantangan}"
    return (f"{tantangan} percobaan tercatat, observer_count tetap 0 — "
            f"buku tantangan terpisah dari reputasi")


@serangan("Jangkar TERDAFTAR ditembus lewat jalur kehadiran")
def _a31():
    """Pernyataan penyelenggara tidak boleh dikalahkan akumulasi pemindaian.

    Kalau jangkarnya terdaftar, jalan keluar bagi merchant sah adalah
    ikut mendaftar — jalur yang punya pencatatan dan pencabutan. Membiarkan
    pemindaian mengalahkannya berarti siapa pun dengan cukup perangkat
    bisa menggusur merchant yang sudah dinyatakan resmi.
    """
    s = Store(os.path.join(tempfile.mkdtemp(), "adv31.db"))
    s.seed_binding(nmid=KORBAN, lat=LAT, lng=LNG, merchant_name="WARUNG BU SRI",
                   observer_count=47,
                   first_seen=NOW - timedelta(days=180),
                   last_seen=NOW - timedelta(hours=1))
    s.conn.execute("UPDATE bindings SET registered_at = ? WHERE nmid = ?",
                   (_iso_uji(NOW - timedelta(days=180)), KORBAN))
    api.store = s
    c = TestClient(api.app)

    # Penyerang memupuk buku tantangan jauh melebihi ambang.
    for i in range(bd.ADJACENT_MIN_DEVICES * 5):
        s.note_challenge(LAT, LNG, PENYERANG, f"device-{i:05d}",
                         now=NOW - timedelta(hours=bd.MIN_AGE_HOURS + 5))
    d = scan(c, qr(PENYERANG), device="penyerang-akhir-1")
    assert d["verdict"] == "anomaly", (
        f"jangkar terdaftar ditembus: {d['verdict']} / {d['action']}")
    assert "adjacent_merchant" not in d["signals"]
    return (f"{bd.ADJACENT_MIN_DEVICES * 5} perangkat tidak cukup — "
            f"pendaftaran tetap lebih otoritatif")


@serangan("Stiker tukar di dalam ruangan, GPS tidak berguna")
def _a32():
    """Serangan yang sebelumnya tidak bisa dilihat sama sekali.

    Di dalam ruko, basement, atau lantai atas, akurasi GPS jatuh ke
    ratusan meter. Invarian §6 menolak menilai jangkar dari koordinat
    seburuk itu, dan sebelumnya jalur itu berhenti di situ: SEMUA
    pemindaian akurasi rendah menghasilkan `warn` datar, baik stikernya
    asli maupun tukar.

    Titik akses di sekitar tidak terpengaruh akurasi GPS, dan lebih
    sulit dipalsukan: memalsukan koordinat cukup satu sakelar di opsi
    pengembang, memalsukan daftar titik akses menuntut kehadiran fisik
    di jangkauan radio yang sama.
    """
    s, c = fresh_store()
    bid = s.conn.execute("SELECT id FROM bindings WHERE nmid = ?",
                         (KORBAN,)).fetchone()["id"]
    ap = [f"{i:032x}" for i in range(32)]
    s.learn_ap(bid, ap)

    def dalam_ruangan(payload, wifi):
        body = {"payload": payload, "lat": LAT, "lng": LNG,
                "device_anon_id": "korban-dalam-ruangan", "accuracy_m": 400.0}
        if wifi:
            body["ambient_wifi"] = {"ap_hashes": wifi}
        return c.post("/api/v1/verify", json=body).json()

    tukar = dalam_ruangan(qr(PENYERANG), ap)
    assert tukar["verdict"] == "anomaly", (
        f"stiker tukar lolos di dalam ruangan sebagai {tukar['verdict']}")
    assert tukar["action"] in ("step_up", "cooling_off"), (
        f"friksi cuma {tukar['action']}")
    assert "ambient_wifi_foreign_nmid" in tukar["signals"]
    # location_source tetap apa adanya: ia menyatakan bagaimana KLIEN
    # memperoleh posisinya, bukan kesimpulan server soal tempatnya.
    assert tukar["location_source"] == "live"

    # Merchant sah di tempat yang sama tidak boleh ikut kena.
    sah = dalam_ruangan(qr(KORBAN), ap)
    assert sah["verdict"] != "anomaly", "merchant sah ikut tertuduh"
    assert "ambient_wifi_confirms_place" in sah["signals"]

    # Klien yang tidak mengirim WiFi sama sekali tidak boleh dihukum.
    tanpa = dalam_ruangan(qr(PENYERANG), None)
    assert tanpa["action"] == "warn", (
        f"klien tanpa WiFi dihukum: {tanpa['action']}")

    return (f"tukar {tukar['action']} / sah {sah['action']} / "
            f"tanpa WiFi {tanpa['action']} — sebelumnya ketiganya warn datar")


@serangan("Sidik jari WiFi dipakai MEMBERI kepercayaan", ditahan=False)
def _a33():
    """Batasan yang disengaja, diuji agar tidak berubah diam-diam.

    Sidik jari WiFi hanya menaikkan kecurigaan, tidak pernah
    menerbitkan kepercayaan. Merchant sah di dalam ruangan tetap
    berhenti di `warn`, bukan `proceed`, walau titik aksesnya cocok
    100%.

    Alasannya ada di korpus: pengukuran lapangan baru memuat tempat
    SAMA (irisan 0,66-0,80) dan tempat SANGAT JAUH (0,00). Kasus tengah
    — ruko sebelah yang berbagi titik akses — belum terukur. Sampai itu
    ada, WiFi tidak boleh jadi dasar memberi izin.
    """
    s, c = fresh_store()
    bid = s.conn.execute("SELECT id FROM bindings WHERE nmid = ?",
                         (KORBAN,)).fetchone()["id"]
    ap = [f"{i:032x}" for i in range(32)]
    s.learn_ap(bid, ap)
    d = c.post("/api/v1/verify", json={
        "payload": qr(KORBAN), "lat": LAT, "lng": LNG,
        "device_anon_id": "pelanggan-dalam-ruangan", "accuracy_m": 400.0,
        "ambient_wifi": {"ap_hashes": ap}}).json()
    assert d["action"] == "warn", (
        f"WiFi menerbitkan kepercayaan: {d['action']}")
    return ("DISENGAJA: WiFi cocok 100% tetap berhenti di warn — kasus "
            "beda-tempat-berdekatan belum terukur, jadi belum boleh "
            "jadi dasar memberi izin")


@serangan("Pemindaian dari gambar meracuni pengetahuan lokasi")
def _a34():
    """Bukan serangan dari luar — kecelakaan dari dalam, dan itu terjadi.

    Tim memindai tujuh QRIS dari internet di rumah salah satu anggota,
    untuk menambah keragaman penerbit. Ketujuhnya terekam sebagai
    binding di satu titik di Jakarta, dengan kota tertulis Karanganyar,
    Pangkal Pinang, Sleman, sampai Mandailing Natal. Pengetahuan
    wilayah untuk lingkungan itu jadi campur aduk dan tidak akan pernah
    mencapai konsensus.

    Prinsipnya sudah ditetapkan di Keputusan 49, tapi dulu hanya
    diterapkan dengan tangan saat pemulihan data. Sekarang ditegakkan
    di kode.
    """
    s, c = fresh_store()
    sebelum = {
        t: s.conn.execute(f"SELECT COUNT(*) n FROM {t}").fetchone()["n"]
        for t in ("bindings", "observations", "area_city", "binding_ap")
    }
    dialek_awal = s.conn.execute(
        "SELECT COUNT(*) n FROM issuer_dialect").fetchone()["n"]

    # Titik yang belum dikuasai siapa pun. Kalau dipindai di jangkar
    # milik merchant lain, hasilnya anomali — dan anomali memang tidak
    # mengajari apa pun, sehingga yang teruji bukan aturan gambarnya.
    JAUH_LAT, JAUH_LNG = LAT + 0.5, LNG + 0.5
    for i in range(3):
        c.post("/api/v1/verify", json={
            "payload": qr(f"ID10265030375{i:02d}", nama="TOKO JAUH"),
            "lat": JAUH_LAT, "lng": JAUH_LNG, "accuracy_m": 8.0,
            "device_anon_id": f"pemindai-gambar-{i:04d}",
            "location_source": "replay",
            "ambient_wifi": {"ap_hashes": [f"{j:032x}" for j in range(20)]}})

    for t, awal in sebelum.items():
        kini = s.conn.execute(f"SELECT COUNT(*) n FROM {t}").fetchone()["n"]
        assert kini == awal, (
            f"pemindaian gambar menambah {t}: {awal} -> {kini}")

    dialek = s.conn.execute(
        "SELECT COUNT(*) n FROM issuer_dialect").fetchone()["n"]
    assert dialek > dialek_awal, (
        "pengetahuan payload ikut diblokir — keragaman penerbit hilang "
        "padahal itu justru yang paling sulit dikumpulkan di lapangan")

    return (f"nol pengetahuan lokasi terbentuk; dialek penerbit "
            f"{dialek_awal} -> {dialek} tetap dipelajari")


@serangan("Mengkatalogkan QRIS menuduh pedagang di sekitarnya")
def _a35():
    """Bukan serangan — pekerjaan tim sendiri, dan itu yang membuatnya berbahaya.

    Dilaporkan dari lapangan: seorang anggota tim duduk di kantornya dan
    mengkatalogkan QRIS satu per satu lewat /verify. Setiap pemindaian
    dijawab `anomaly`, dan setiap jawaban itu menandai jangkar pedagang
    di sekitarnya sebagai "berkali-kali menjadi sasaran". Pedagang
    sungguhan ikut tertuduh oleh aktivitas yang bukan serangan.

    Sebabnya struktural: /verify hanya bisa menjawab "apakah stiker ini
    sah DI SINI", dan orang yang mengkatalogkan tidak sedang bertanya
    itu. /inspect menjawab pertanyaan yang berbeda dan tidak menyentuh
    pengetahuan lokasi sama sekali.
    """
    s, c = fresh_store()
    sebelum = {
        t: s.conn.execute(f"SELECT COUNT(*) n FROM {t}").fetchone()["n"]
        for t in ("bindings", "observations", "anchor_challenge")
    }
    anomali_awal = s.conn.execute(
        "SELECT COALESCE(SUM(anomaly_attempts),0) n FROM bindings").fetchone()["n"]
    dialek_awal = s.conn.execute(
        "SELECT COUNT(*) n FROM issuer_dialect").fetchone()["n"]

    for i in range(5):
        d = c.post("/api/v1/inspect", json={
            "payload": qr(f"ID10265030375{i:02d}", nama=f"TOKO {i}")}).json()
        assert "merchant" in d, f"inspect gagal: {d}"
        assert "action" not in d, "inspect menerbitkan tier aksi"
        assert "verification_ticket" not in d, "inspect menerbitkan tiket"

    for t, awal in sebelum.items():
        kini = s.conn.execute(f"SELECT COUNT(*) n FROM {t}").fetchone()["n"]
        assert kini == awal, f"inspect menyentuh {t}: {awal} -> {kini}"
    anomali = s.conn.execute(
        "SELECT COALESCE(SUM(anomaly_attempts),0) n FROM bindings").fetchone()["n"]
    assert anomali == anomali_awal, (
        f"inspect menandai jangkar sebagai sasaran: {anomali_awal} -> {anomali}")

    dialek = s.conn.execute(
        "SELECT COUNT(*) n FROM issuer_dialect").fetchone()["n"]
    assert dialek > dialek_awal, (
        "pengetahuan payload ikut diblokir — itu justru yang dikumpulkan")

    return (f"nol pengetahuan lokasi tersentuh; dialek penerbit "
            f"{dialek_awal} -> {dialek} tetap terkumpul")


@serangan("Pemindaian gambar menandai jangkar tetangga sebagai sasaran")
def _a36():
    """Celah yang tersisa dari versi pertama Keputusan 54.

    Penjaganya dulu hanya menahan PEMBELAJARAN. Pencatatan anomali
    berjalan terus, jadi jangkar pedagang sungguhan tetap terhitung
    "diserang" oleh pemindaian yang jelas-jelas dinyatakan bukan dari
    lapangan.
    """
    s, c = fresh_store()
    awal = s.conn.execute(
        "SELECT COALESCE(SUM(anomaly_attempts),0) n FROM bindings").fetchone()["n"]
    tantangan_awal = s.conn.execute(
        "SELECT COUNT(*) n FROM anchor_challenge").fetchone()["n"]

    for i in range(5):
        c.post("/api/v1/verify", json={
            "payload": qr(PENYERANG), "lat": LAT, "lng": LNG,
            "accuracy_m": 8.0, "device_anon_id": f"katalog-{i:04d}",
            "location_source": "replay"})

    kini = s.conn.execute(
        "SELECT COALESCE(SUM(anomaly_attempts),0) n FROM bindings").fetchone()["n"]
    tantangan = s.conn.execute(
        "SELECT COUNT(*) n FROM anchor_challenge").fetchone()["n"]
    assert kini == awal, f"jangkar ditandai diserang: {awal} -> {kini}"
    assert tantangan == tantangan_awal, (
        f"buku tantangan tumbuh dari pemindaian gambar: "
        f"{tantangan_awal} -> {tantangan}")
    return "lokasi yang tidak tepercaya tidak menandai apa pun"


print("=" * 72)
print("SUITE ADVERSARIAL")
print("=" * 72)
print()

gagal = 0
print("Serangan yang harus ditahan")
print("-" * 72)
for nama, ditahan, ok, detail in _hasil:
    if not ditahan:
        continue
    print(f"  [{'DITAHAN' if ok else 'JEBOL  '}]  {nama}")
    if detail:
        print(f"             {detail}")
    if not ok:
        gagal += 1

print()
print("Batasan yang diakui — diuji agar sistem tetap jujur")
print("-" * 72)
for nama, ditahan, ok, detail in _hasil:
    if ditahan:
        continue
    print(f"  [{'JUJUR  ' if ok else 'REGRESI'}]  {nama}")
    if detail:
        print(f"             {detail}")
    if not ok:
        gagal += 1

print()
print("-" * 72)
if gagal:
    print(f"{gagal} dari {len(_hasil)} skenario GAGAL.")
    sys.exit(1)
print(f"Seluruh {len(_hasil)} skenario sesuai harapan.")
