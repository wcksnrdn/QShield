"""
Dari mana reputasi sebuah jangkar berasal.

`observer_count` adalah angka yang DIKENDALIKAN PENYERANG: ia tumbuh
dari `device_anon_id`, dan `device_anon_id` diisi klien. Prinsip yang
kita pegang di seluruh sistem ini — nilai yang dikendalikan penyerang
boleh MENGETATKAN, tidak pernah MELONGGARKAN — justru dilanggar di
titik paling inti, dan tidak ada yang menyadarinya sampai diuji.

Yang dikunci di sini:

  1. serangannya nyata, dan angkanya dicatat apa adanya
  2. sejak sekarang serangan itu SELALU terungkap di tanggapan
  3. `vouched_observers` tidak bisa ditumbuhkan penyerang
  4. pengungkapan ini tidak menggeser putusan sedikit pun

    python tests/test_konsensus.py
"""

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

os.environ["QSHIELD_AUTH"] = "off"
os.environ["QSHIELD_RATE_LIMIT"] = "off"

from fastapi.testclient import TestClient

from qshield import api, auth, binding as bd, emvco
from qshield.store import Store

NOW = datetime.now(timezone.utc)
PENIPU = "ID1055500022233"
# Titik kosong: belum ada jangkar siapa pun di sini.
LAT, LNG = -6.888000, 107.640000

KUNCI = auth.new_key()
ATESTASI = {"mock_location": False, "rooted": False,
            "attested": True, "platform": "android"}

_hasil = []


def cek(nama):
    def deco(fn):
        try:
            _hasil.append((nama, True, fn() or ""))
        except AssertionError as exc:
            _hasil.append((nama, False, str(exc)))
        return fn
    return deco


def qr(nmid=PENIPU, nama="WARUNG SEJAHTERA"):
    acct = emvco.build_tlv({
        "00": "ID.CO.QRIS.WWW", "01": "936000149000000555",
        "02": nmid, "03": "UMI"})
    return emvco.build({
        "00": "01", "01": "11", "26": acct, "52": "5499", "53": "360",
        "58": "ID", "59": nama, "60": "BANDUNG"})


def klien(pakai_auth=False):
    db = os.path.join(tempfile.mkdtemp(), "konsensus.db")
    api.store = Store(db)
    if pakai_auth:
        api.clients = auth.ClientRegistry(
            spec=f"pjp-alpha:{auth.hash_key(KUNCI)}", auth_setting="")
    else:
        api.clients = auth.ClientRegistry(spec="", auth_setting="off")
    return TestClient(api.app), api.store


def karang_konsensus(store, vouched=False):
    """Tiga identitas perangkat karangan, direntang lebih dari 24 jam."""
    for i, jam in enumerate((25, 12, 0)):
        store.record(nmid=PENIPU, lat=LAT, lng=LNG,
                     device_anon_id=f"karangan-{i:08d}",
                     merchant_name="WARUNG SEJAHTERA",
                     now=NOW - timedelta(hours=jam), vouched=vouched)


def pindai(c, dev="korban-pertama-01", **extra):
    badan = {"payload": qr(), "lat": LAT, "lng": LNG,
             "device_anon_id": dev, "accuracy_m": 10.0}
    badan.update(extra.pop("badan", {}))
    r = c.post("/api/v1/verify", json=badan, **extra)
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
    return r.json()


@cek("Konsensus memang bisa dikarang — ini diukur, bukan diperdebatkan")
def _t1():
    c, store = klien()
    karang_konsensus(store)
    j = pindai(c)
    b = store.by_nmid(PENIPU)[0]
    assert b.is_established, "serangan gagal; skenarionya yang perlu diperbaiki"
    assert j["verdict"] == "verified", j["verdict"]
    return (f"{bd.MIN_OBSERVERS} string karangan + menunggu "
            f"{bd.MIN_AGE_HOURS} jam -> {j['verdict']}/{j['action']}")


@cek("Sejak sekarang serangan itu SELALU terungkap di tanggapan")
def _t2():
    c, store = klien()
    karang_konsensus(store)
    j = pindai(c)
    assert "consensus_unvouched" in j["signals"], j["signals"]
    teks = " ".join(j["reasons"])
    assert "pemindaian anonim" in teks, teks
    assert j["evidence"]["vouched_observers"] == 0, j["evidence"]
    return "sinyal + alasan + evidence.vouched_observers=0"


@cek("evidence melaporkan dasar putusan apa adanya")
def _t3():
    c, store = klien()
    karang_konsensus(store)
    j = pindai(c)
    e = j["evidence"]
    # Tiga, bukan empat: yang dilaporkan adalah keadaan yang menjadi
    # DASAR putusan ini, bukan keadaan sesudah pemindaian ini ikut
    # dicatat. Putusannya memang berdiri di atas tiga pengamatan.
    assert e["observers"] == 3, e
    assert e["vouched_observers"] == 0, e
    assert e["registered"] is False and e["established"] is True, e
    assert e["span_hours"] >= bd.MIN_AGE_HOURS, e
    return (f"{e['observers']} pengamat, {e['vouched_observers']} dijamin, "
            f"rentang {e['span_hours']} jam")


@cek("Pengamat yang dijamin PJP terhitung terpisah")
def _t4():
    c, store = klien(pakai_auth=True)
    karang_konsensus(store)
    # Satu pengguna PJP sungguhan memindai lebih dulu; atestasinya
    # diperiksa PJP dan dipertanggungkan lewat kunci API mereka.
    j1 = pindai(c, dev="pengguna-pjp-01",
                headers={auth.API_KEY_HEADER: KUNCI},
                badan={"device_integrity": ATESTASI})
    assert j1["evidence"]["vouched_observers"] == 0, "belum tercatat saat itu"
    # Pembeli berikutnya melihat dasar yang sudah berubah.
    j = pindai(c, dev="pembeli-berikutnya-01",
               headers={auth.API_KEY_HEADER: KUNCI})
    e = j["evidence"]
    assert e["vouched_observers"] == 1, e
    assert "consensus_unvouched" not in j["signals"], j["signals"]
    return f"{e['observers']} pengamat, {e['vouched_observers']} dijamin penyelenggara"


@cek("Klien ANONIM yang mengaku attested tidak pernah terhitung dijamin")
def _t5():
    """Inti pertahanannya. Atestasi dilaporkan klien dan tidak bisa kami
    verifikasi — yang membuatnya berarti PJP yang memeriksanya lalu
    mempertanggungkannya lewat kunci API. Tanpa kunci itu, pengakuan
    `attested: true` cuma klaim penyerang tentang dirinya sendiri."""
    c, store = klien()                      # tanpa auth
    karang_konsensus(store)
    j = pindai(c, dev="penyerang-mengaku-01",
               badan={"device_integrity": ATESTASI})
    assert j["evidence"]["vouched_observers"] == 0, j["evidence"]
    assert "consensus_unvouched" in j["signals"], j["signals"]
    return "mengaku attested tanpa kunci PJP -> tetap 0 dijamin"


@cek("Penyerang tidak bisa menumbuhkan vouched_count dari sisi klien")
def _t6():
    c, store = klien()
    for i in range(20):
        store.record(nmid=PENIPU, lat=LAT, lng=LNG,
                     device_anon_id=f"karangan-massal-{i:08d}",
                     merchant_name="WARUNG SEJAHTERA", now=NOW)
    b = store.by_nmid(PENIPU)[0]
    assert b.observer_count == 20, b.observer_count
    assert b.vouched_count == 0, b.vouched_count
    return "20 identitas karangan -> 20 pengamat, 0 dijamin"


@cek("Pengungkapan tidak menggeser putusan sedikit pun")
def _t7():
    """Kalau baris ini mengubah skor, ia berhenti jadi pengungkapan dan
    berubah jadi penilaian diam-diam."""
    c, store = klien()
    karang_konsensus(store)
    j = pindai(c)
    bobot = dict(zip(j["reasons"], j.get("signals", [])))
    assert j["risk_score"] == 0, f"skor bergeser jadi {j['risk_score']}"
    assert j["action"] == "proceed", j["action"]
    return f"skor {j['risk_score']}, aksi {j['action']} — tidak bergeser"


@cek("Basis data lama tanpa kolomnya tetap terbaca")
def _t8():
    import sqlite3
    db = os.path.join(tempfile.mkdtemp(), "lama.db")
    s1 = Store(db)
    s1.record(nmid=PENIPU, lat=LAT, lng=LNG, device_anon_id="lama-0001",
              merchant_name="WARUNG SEJAHTERA", now=NOW)
    s1.close()
    # Jatuhkan kolomnya, tirukan basis data versi sebelumnya.
    cc = sqlite3.connect(db)
    cc.execute("ALTER TABLE bindings DROP COLUMN vouched_count")
    cc.commit()
    cc.close()
    s2 = Store(db)                       # migrasi menambahkannya kembali
    b = s2.by_nmid(PENIPU)[0]
    assert b.vouched_count == 0, b.vouched_count
    return "kolom ditambahkan lewat migrasi, baris lama jadi 0 — bukan crash"


print("=" * 70)
print("ASAL-USUL KONSENSUS")
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
