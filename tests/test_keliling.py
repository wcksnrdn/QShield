"""
Pedagang keliling vs stiker yang disebar.

Keduanya menghasilkan gejala yang SAMA PERSIS di `bindings`: satu
Merchant ID muncul di banyak area berjauhan. Sebelum Keputusan 80,
gejala itu sendiri yang dihukum (+60, anomaly), sehingga gerobak kopi
keliling yang sah divonis penyebar stiker.

Yang memisahkan keduanya fisika, bukan statistik:

    satu gerobak hanya bisa berada di satu tempat pada satu waktu;
    lima stiker yang ditempel bersamaan hidup di lima tempat sekaligus.

Yang diuji di sini: pedagang keliling tidak lagi dituduh, DAN sebaran
yang meninggalkan bukti tetap tertangkap.

    python tests/test_keliling.py
"""

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

os.environ["QSHIELD_AUTH"] = "off"
os.environ["QSHIELD_RATE_LIMIT"] = "off"

from fastapi.testclient import TestClient

from qshield import api, binding as bd, emvco
from qshield.store import Store

NOW = datetime.now(timezone.utc)
NMID = "ID1077700088811"

# Enam titik mangkal di Bandung, semuanya >1 km satu sama lain.
TITIK = [
    ("depan kampus",    -6.914744, 107.609810),
    ("pasar kosambi",   -6.917500, 107.625000),
    ("alun-alun",       -6.921500, 107.606000),
    ("jalan riau",      -6.900000, 107.618000),
    ("dago atas",       -6.880000, 107.613000),
    ("terminal ledeng", -6.860000, 107.600000),
]

_hasil = []


def cek(nama):
    def deco(fn):
        try:
            _hasil.append((nama, True, fn() or ""))
        except AssertionError as exc:
            _hasil.append((nama, False, str(exc)))
        return fn
    return deco


def qr(nmid=NMID, nama="KOPI JAGO"):
    acct = emvco.build_tlv({
        "00": "ID.CO.QRIS.WWW", "01": "936000149000000777",
        "02": nmid, "03": "UMI"})
    return emvco.build({
        "00": "01", "01": "11", "26": acct, "52": "5499", "53": "360",
        "58": "ID", "59": nama, "60": "BANDUNG"})


def klien():
    db = os.path.join(tempfile.mkdtemp(), "keliling.db")
    api.store = Store(db)
    return TestClient(api.app), api.store


def gerobak(store, titik=TITIK, hari_awal=28):
    """Satu gerobak menyinggahi tiap titik pada HARI YANG BERBEDA.

    Pengamatannya dicatat lewat store.record dengan waktu eksplisit,
    jadi jejaknya sama bentuknya dengan hasil pemindaian sungguhan.
    """
    hari = hari_awal
    for nama, lat, lng in titik:
        for d in range(4):
            store.record(nmid=NMID, lat=lat, lng=lng,
                         device_anon_id=f"pembeli-{nama[:4]}-{d:03d}",
                         merchant_name="KOPI JAGO",
                         now=NOW - timedelta(days=hari, hours=d))
        hari -= 4


def pindai(c, lat, lng, payload=None, dev="pembeli-baru-0001"):
    r = c.post("/api/v1/verify", json={
        "payload": payload or qr(), "lat": lat, "lng": lng,
        "device_anon_id": dev, "accuracy_m": 10.0})
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
    return r.json()


@cek("Gerobak keliling tidak lagi divonis penyebar stiker")
def _t1():
    c, store = klien()
    gerobak(store)
    j = pindai(c, *TITIK[0][1:])
    assert j["verdict"] != "anomaly", f"{j['verdict']}: {j['reasons']}"
    assert "nmid_scatter" not in j["signals"], j["signals"]
    assert "nmid_multi_area" in j["signals"], j["signals"]
    return f"{j['verdict']}/{j['action']} skor {j['risk_score']} — 6 titik, 24 pengamat"


@cek("Tapi ia juga tidak pernah hijau — ketidaktahuan bukan kepercayaan")
def _t2():
    c, store = klien()
    gerobak(store)
    j = pindai(c, *TITIK[0][1:])
    assert j["verdict"] != "verified", j["verdict"]
    assert j["action"] != "proceed", j["action"]
    return f"{j['action']} — gesekan utuh, tuduhan hilang (invarian §2)"


@cek("Alasannya menyebut ketidaktahuan, bukan tuduhan")
def _t3():
    c, store = klien()
    gerobak(store)
    j = pindai(c, *TITIK[0][1:])
    teks = " ".join(j["reasons"])
    assert "pola khas stiker yang disebar" not in teks, teks
    assert "pedagang keliling" in teks, teks
    return "kata 'pola khas stiker yang disebar' tidak muncul"


@cek("Kehadiran serentak tetap tertangkap sebagai sebaran")
def _t4():
    """Dua tempat berjauhan, dipindai terpaut dua menit.

    Angkanya sengaja dibuat mustahil, bukan sekadar cepat: 6,2 km dalam
    2 menit menuntut 186 km/jam. Percobaan pertama test ini memakai
    3,9 km dalam 6 menit — hanya 39 km/jam — dan memang SEHARUSNYA
    lolos: kopi keliling bermotor bisa secepat itu.
    """
    c, store = klien()
    gerobak(store)
    jauh = TITIK[5]          # terminal ledeng, 6,2 km dari depan kampus
    store.record(nmid=NMID, lat=jauh[1], lng=jauh[2],
                 device_anon_id="pembeli-serentak-1",
                 merchant_name="KOPI JAGO",
                 now=NOW - timedelta(minutes=2))
    j = pindai(c, *TITIK[0][1:], dev="pembeli-serentak-2")
    assert "nmid_scatter" in j["signals"], j["signals"]
    assert j["verdict"] == "anomaly", j["verdict"]
    alasan = next(a for a in j["reasons"] if "terpaut" in a)
    return alasan[:96]


@cek("Rentang antar kota tertangkap walau waktunya berjauhan")
def _t5():
    c, store = klien()
    kota = [("bandung", -6.914744, 107.609810),
            ("jakarta", -6.200000, 106.816700),
            ("surabaya", -7.257500, 112.752100)]
    hari = 300
    for nama, lat, lng in kota:
        for d in range(4):
            store.record(nmid=NMID, lat=lat, lng=lng,
                         device_anon_id=f"korban-{nama}-{d}",
                         merchant_name="KOPI JAGO",
                         now=NOW - timedelta(days=hari))
        hari -= 90
    j = pindai(c, kota[0][1], kota[0][2], dev="korban-akhir-0001")
    assert "nmid_scatter" in j["signals"], j["signals"]
    assert j["verdict"] == "anomaly", j["verdict"]
    alasan = next(a for a in j["reasons"] if "membentang" in a)
    return alasan[:96]


@cek("Ambang rentang tidak menuduh pedagang se-metropolitan")
def _t6():
    """Jabodetabek: Bogor-Jakarta ~50 km, masih satu wilayah kerja."""
    c, store = klien()
    metro = [("bogor", -6.597100, 106.806000),
             ("depok", -6.400000, 106.818000),
             ("jakarta", -6.200000, 106.816700)]
    hari = 24
    for nama, lat, lng in metro:
        for d in range(4):
            store.record(nmid=NMID, lat=lat, lng=lng,
                         device_anon_id=f"pembeli-{nama}-{d}",
                         merchant_name="KOPI JAGO",
                         now=NOW - timedelta(days=hari, hours=d))
        hari -= 8
    j = pindai(c, metro[0][1], metro[0][2], dev="pembeli-metro-baru")
    rentang = bd.rentang_area_km(
        [b for b in store.by_nmid(NMID)], metro[0][1], metro[0][2])
    assert "nmid_scatter" not in j["signals"], f"rentang {rentang:.0f} km: {j['signals']}"
    return f"rentang {rentang:.0f} km, di bawah MOBILITY_MAX_SPAN_KM={bd.MOBILITY_MAX_SPAN_KM:.0f}"


@cek("Merchant keliling terdaftar PJP tetap lolos seketika")
def _t7():
    c, store = klien()
    gerobak(store)
    store.register(nmid=NMID, registrar="pjp-uji", lat=TITIK[0][1],
                   lng=TITIK[0][2], merchant_name="KOPI JAGO",
                   is_mobile=True)
    j = pindai(c, *TITIK[0][1:], dev="pembeli-terdaftar")
    assert j["verdict"] == "verified" and j["action"] == "proceed", j
    assert "mobile_merchant" in j["signals"], j["signals"]
    return "jalur pendaftaran PJP tidak tersentuh perubahan ini"


@cek("Jejak kehadiran tidak pernah membocorkan pengenal perangkat")
def _t8():
    c, store = klien()
    gerobak(store)
    jejak = store.jejak_lintas_area(NMID)
    assert jejak and len(jejak) == 24, len(jejak)
    for baris in jejak:
        assert len(baris) == 3, baris
        assert isinstance(baris[2], datetime), baris
    teks = repr(jejak)
    for jejak_bocor in ("device", "ref", "pembeli"):
        assert jejak_bocor not in teks, f"{jejak_bocor!r} bocor: {teks[:120]}"
    return f"{len(jejak)} baris (lat, lng, waktu) — tanpa device_ref (invarian §8)"


@cek("Satu jangkar saja tidak membayar kueri jejak")
def _t9():
    """Mayoritas merchant tetap di jalur cepat."""
    c, store = klien()
    lat, lng = TITIK[0][1], TITIK[0][2]
    for d in range(5):
        store.record(nmid=NMID, lat=lat, lng=lng,
                     device_anon_id=f"pembeli-tunggal-{d}",
                     merchant_name="KOPI JAGO",
                     now=NOW - timedelta(days=3, hours=d))
    j = pindai(c, lat, lng, dev="pembeli-tunggal-baru")
    assert len(store.by_nmid(NMID)) < bd.SCATTER_MIN_AREAS
    assert "nmid_multi_area" not in j["signals"], j["signals"]
    return f"{j['verdict']}/{j['action']} — jalur satu-lokasi tidak berubah"


print("=" * 70)
print("PEDAGANG KELILING vs STIKER YANG DISEBAR")
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
