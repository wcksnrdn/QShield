"""
Pemindaian dari GAMBAR — pembayaran jarak jauh.

Kasusnya sehari-hari: seseorang memfoto QR di warung, mengirimkannya
lewat pesan, dan orang lain membayar dari tempat yang sama sekali
berbeda. Koordinat pembayar nyata, tapi tidak mengatakan apa pun
tentang di mana stiker itu berada.

Yang diuji di sini bukan "field-nya ada", melainkan tiga hal yang
harus tetap benar:

  1. pedagang yang sah tidak dituduh gara-gara pembayarnya jauh
  2. tidak ada jangkar hantu yang ditanam di lokasi pembayar
  3. field ini tidak bisa dipakai MELONGGARKAN penilaian

    python tests/test_gambar.py
"""

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

os.environ["QSHIELD_AUTH"] = "off"
os.environ["QSHIELD_RATE_LIMIT"] = "off"

from fastapi.testclient import TestClient

from qshield import api, emvco
from qshield.store import Store

NOW = datetime.now(timezone.utc)
LAT, LNG = -6.914744, 107.609810           # warung
JAUH_LAT, JAUH_LNG = -6.960000, 107.700000  # pembayar, ~11 km
NMID = "ID1024365478912"
PALSU = "ID1099887766554"

_hasil = []


def cek(nama):
    def deco(fn):
        try:
            _hasil.append((nama, True, fn() or ""))
        except AssertionError as exc:
            _hasil.append((nama, False, str(exc)))
        return fn
    return deco


def qr(nmid=NMID, nama="WARUNG MADURA", pan="936000149000000001"):
    acct = emvco.build_tlv({
        "00": "ID.CO.QRIS.WWW", "01": pan, "02": nmid, "03": "UMI"})
    return emvco.build({
        "00": "01", "01": "11", "26": acct, "52": "5812", "53": "360",
        "58": "ID", "59": nama, "60": "BANDUNG", "61": "40257"})


def klien():
    """Klien baru dengan warung mapan di LAT,LNG."""
    db = os.path.join(tempfile.mkdtemp(), "gambar.db")
    api.store = Store(db)
    api.store.seed_binding(
        nmid=NMID, lat=LAT, lng=LNG, merchant_name="WARUNG MADURA",
        observer_count=47, first_seen=NOW - timedelta(days=180),
        last_seen=NOW - timedelta(hours=6))
    api.store.learn_city(LAT, LNG, "BANDUNG", NMID)
    return TestClient(api.app), api.store


def pindai(c, payload, from_image, lat=JAUH_LAT, lng=JAUH_LNG,
           dev="pembayar-0001", **extra):
    badan = {"payload": payload, "lat": lat, "lng": lng,
             "device_anon_id": dev, "accuracy_m": 12.0,
             "from_image": from_image}
    badan.update(extra)
    r = c.post("/api/v1/verify", json=badan)
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
    return r.json()


@cek("Tanpa penanda, pembayar jauh menuduh pedagang yang sah")
def _t1():
    """Ini perilaku LAMA, dikunci sebagai pembanding — bukan sebagai
    sesuatu yang benar. Kalau suatu saat ia berubah, yang di bawahnya
    ikut kehilangan makna."""
    c, _ = klien()
    j = pindai(c, qr(), from_image=False)
    assert j["action"] == "step_up", j["action"]
    assert "nmid_second_location" in j["signals"], j["signals"]
    return f"{j['verdict']}/{j['action']} skor {j['risk_score']} — pedagang sah, pembayar 11 km"


@cek("Dengan penanda, pedagang sah tidak lagi dituduh")
def _t2():
    c, _ = klien()
    j = pindai(c, qr(), from_image=True)
    assert j["action"] == "warn", j["action"]
    assert j["verdict"] == "unknown", j["verdict"]
    assert "scanned_from_image" in j["signals"], j["signals"]
    assert j["layers"]["location"] == 0, "Layer 1 seharusnya tidak dijalankan"
    return f"{j['verdict']}/{j['action']} — mengaku tidak tahu, bukan menuduh"


@cek("Tidak ada jangkar hantu yang ditanam di lokasi pembayar")
def _t3():
    c, store = klien()
    for i in range(5):
        pindai(c, qr(), from_image=True, dev=f"pembayar-{i:04d}")
    baris = store.conn.execute("SELECT COUNT(*) n FROM bindings").fetchone()
    assert baris["n"] == 1, f"{baris['n']} jangkar; seharusnya tetap 1"
    b = store.by_nmid(NMID)[0]
    assert b.observer_count == 47, f"observer {b.observer_count}, seharusnya 47"
    return "5 pembayaran jarak jauh; 1 jangkar, 47 pengamat — tak bergerak"


@cek("Atribusi menyebut apa yang DIAMATI, bukan yang tertulis di QR")
def _t4():
    c, _ = klien()
    j = pindai(c, qr(), from_image=True)
    k = j["known"]
    assert k["known"] is True
    assert k["names"] == ["WARUNG MADURA"], k["names"]
    assert k["city"] == "BANDUNG", k["city"]
    assert k["name_matches"] is True
    return f"dikenal sebagai {k['names'][0]} di {k['city']}, {k['observer_count']} pengamatan"


@cek("NMID yang belum pernah diamati dilaporkan apa adanya")
def _t5():
    c, _ = klien()
    j = pindai(c, qr(nmid=PALSU), from_image=True)
    k = j["known"]
    assert k["known"] is False, k
    assert k["names"] == [] and k["city"] is None
    assert any("belum pernah" in a for a in j["reasons"]), j["reasons"]
    return "nama di QR bisa dikarang; riwayat pengamatan tidak"


@cek("Nama yang tidak cocok diungkapkan, tanpa menuduh lewat tier")
def _t6():
    c, _ = klien()
    j = pindai(c, qr(nama="TOKO EMAS SEJAHTERA"), from_image=True)
    assert j["known"]["name_matches"] is False, j["known"]
    assert any("berbeda dari" in a for a in j["reasons"]), j["reasons"]
    return "diungkapkan sebagai alasan; korpus masih tipis untuk memberi bobot"


@cek("Koordinat merchant TIDAK PERNAH keluar lewat atribusi")
def _t7():
    c, _ = klien()
    j = pindai(c, qr(), from_image=True)
    teks = repr(j["known"])
    for jejak in ("lat", "lng", "6.914", "107.609", "geohash"):
        assert jejak not in teks, f"{jejak!r} bocor di atribusi: {teks}"
    return "kota adalah resolusi paling halus yang keluar (invarian §8)"


@cek("Penanda hanya bisa MENGETATKAN, tidak pernah melonggarkan")
def _t8():
    """Payload cacat tetap anomaly walau mengaku dipindai dari gambar.

    Ini pagarnya: field diisi klien, dan klien bisa berbohong."""
    c, _ = klien()
    acct = emvco.build_tlv({
        "00": "ID.CO.QRIS.WWW", "01": "936000149000000001",
        "02": NMID, "03": "UMI"})
    cacat = emvco.build({
        "00": "01", "01": "11", "26": acct, "52": "5812", "53": "360",
        "54": "250000.00",  # QR statis bernominal — kontradiksi spec
        "58": "ID", "59": "WARUNG MADURA", "60": "BANDUNG"})
    j = pindai(c, cacat, from_image=True)
    assert j["verdict"] == "anomaly", j["verdict"]
    assert j["action"] == "cooling_off", j["action"]
    return f"{j['verdict']}/{j['action']} — Layer 2 tetap berjalan penuh"


@cek("Pengetahuan payload tetap dipelajari, pengetahuan tempat tidak")
def _t9():
    c, store = klien()
    sebelum_kota = store.conn.execute(
        "SELECT COUNT(*) n FROM area_city").fetchone()["n"]
    pindai(c, qr(nmid=PALSU), from_image=True)
    sesudah_kota = store.conn.execute(
        "SELECT COUNT(*) n FROM area_city").fetchone()["n"]
    fitur = store.conn.execute(
        "SELECT COUNT(*) n FROM merchant_feature WHERE nmid = ?",
        (PALSU,)).fetchone()["n"]
    assert sesudah_kota == sebelum_kota, "kota ikut dipelajari; seharusnya tidak"
    assert fitur > 0, "ciri merchant tidak dipelajari; seharusnya iya"
    return f"{fitur} ciri payload dipelajari; pengetahuan wilayah tidak bertambah"


@cek("/inspect juga membawa atribusi, tanpa koordinat sama sekali")
def _t10():
    c, _ = klien()
    r = c.post("/api/v1/inspect", json={"payload": qr()})
    assert r.status_code == 200, r.text[:200]
    k = r.json()["known"]
    assert k["known"] is True and k["city"] == "BANDUNG", k
    assert "action" not in r.json() and "verdict" not in r.json()
    return "dikenal + kota, tanpa putusan dan tanpa tier"


print("=" * 70)
print("PEMINDAIAN DARI GAMBAR")
print("=" * 70)
print()
gagal = 0
for nama, ok, detail in _hasil:
    print(f"  [{'OK   ' if ok else 'GAGAL'}]  {nama}")
    if detail:
        print(f"           {detail}")
    if not ok:
        gagal += 1
print()
print("-" * 70)
if gagal:
    print(f"{gagal} dari {len(_hasil)} pemeriksaan GAGAL.")
    sys.exit(1)
print(f"Seluruh {len(_hasil)} pemeriksaan lolos.")
