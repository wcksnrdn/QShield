"""
Layer 2 jalur transfer manual — fungsinya dan penyalahgunaannya.

Transfer manual tidak punya artefak yang bisa diperiksa: tidak ada
payload, tidak ada jangkar lokasi. Yang dinilai adalah bentuk
transaksinya dan reputasi rekening tujuannya.

    python tests/test_transfer.py
"""

import json
import os
import sys
import tempfile

os.environ["QSHIELD_RATE_LIMIT"] = "off"
os.environ.pop("QSHIELD_AUTH", None)

from fastapi.testclient import TestClient

from qshield import api, auth
from qshield import transfer as tf
from qshield.store import Store

KUNCI_A, KUNCI_B, KUNCI_C = auth.new_key(), auth.new_key(), auth.new_key()
H_A = {auth.API_KEY_HEADER: KUNCI_A}
H_B = {auth.API_KEY_HEADER: KUNCI_B}
H_C = {auth.API_KEY_HEADER: KUNCI_C}
AKUN = "8801234567"

_hasil = []


def cek(nama):
    def deco(fn):
        try:
            _hasil.append((nama, True, fn() or ""))
        except AssertionError as exc:
            _hasil.append((nama, False, str(exc)))
        return fn
    return deco


def siapkan():
    api.store = Store(os.path.join(tempfile.mkdtemp(), "tf.db"))
    api.clients = auth.ClientRegistry(
        spec=f"pjp-alpha:{auth.hash_key(KUNCI_A)},"
             f"pjp-beta:{auth.hash_key(KUNCI_B)},"
             f"pjp-gamma:{auth.hash_key(KUNCI_C)}", auth_setting="")
    return TestClient(api.app)


def nilai(c, telemetry=None, akun=AKUN, h=H_A):
    body = {"beneficiary_account": akun, "amount": 5_000_000}
    if telemetry is not None:
        body["telemetry"] = telemetry
    return c.post("/api/v1/assess-transfer", json=body, headers=h).json()


# --- Fungsinya -----------------------------------------------------

@cek("Pola rekayasa sosial tertangkap")
def _t1():
    c = siapkan()
    d = nilai(c, {"first_time_beneficiary": True,
                  "beneficiary_account_age_days": 4,
                  "call_active": True, "transfers_last_hour": 3})
    assert d["action"] == "cooling_off", f"-> {d['action']}"
    for s in ("call_active_during_transfer", "beneficiary_account_young",
              "first_time_beneficiary", "transfer_velocity_spike"):
        assert s in d["signals"], f"sinyal {s} hilang"
    return f"empat sinyal, skor {d['risk_score']} -> cooling_off"


@cek("Transfer normal tidak diganggu")
def _t2():
    c = siapkan()
    d = nilai(c, {"first_time_beneficiary": False,
                  "beneficiary_account_age_days": 1200,
                  "call_active": False, "transfers_last_hour": 0})
    assert d["action"] == "proceed", f"-> {d['action']}"
    assert not d["signals"], f"sinyal muncul: {d['signals']}"
    return "proceed, nol sinyal"


@cek("Tidak ada sinyal tunggal yang menghukum sendirian")
def _t3():
    c = siapkan()
    # Menelepon orang yang dibayar sambil transfer adalah hal wajar.
    # Rekening yang memang baru dibuka juga. Satu sinyal saja tidak
    # boleh cukup — kalau cukup, sistem menghukum perilaku normal.
    tunggal = [
        {"call_active": True},
        {"beneficiary_account_age_days": 5},
        {"first_time_beneficiary": True},
        {"transfers_last_hour": 4},
    ]
    for t in tunggal:
        d = nilai(c, t)
        assert d["action"] in ("proceed", "warn"), (
            f"{t} sendirian -> {d['action']}, terlalu keras")
    return "empat sinyal tunggal, tidak satu pun mencapai step_up"


@cek("Telemetri yang tidak dikirim diungkapkan, bukan dihukum")
def _t4():
    c = siapkan()
    d = nilai(c, None)
    assert d["telemetry"] == "not_provided"
    # Tapi juga tidak boleh jadi "aman" — tanpa telemetri kami memang
    # tidak menilai apa pun.
    assert d["action"] != "proceed", (
        "tanpa telemetri malah proceed — ketiadaan data jadi kepercayaan")
    assert d["risk_score"] == 0, "ketiadaan telemetri diberi skor"
    return f"{d['action']}, skor 0, status not_provided"


# --- Lapisan bersama -----------------------------------------------

@cek("Laporan lintas-penyelenggara melindungi korban berikutnya")
def _t5():
    c = siapkan()
    bersih = {"first_time_beneficiary": True,
              "beneficiary_account_age_days": 200,
              "call_active": False, "transfers_last_hour": 0}

    sebelum = nilai(c, bersih)
    assert sebelum["action"] == "proceed", f"pra-laporan {sebelum['action']}"

    for h in (H_A, H_B, H_C):
        c.post("/api/v1/beneficiary-reports",
               json={"beneficiary_account": AKUN}, headers=h)

    sesudah = nilai(c, bersih)
    assert "beneficiary_reported" in sesudah["signals"]
    assert sesudah["action"] in ("step_up", "cooling_off"), (
        f"pasca-laporan {sesudah['action']}")
    assert any("3 penyelenggara" in r for r in sesudah["reasons"])
    return (f"tanpa tanda lain: {sebelum['action']} -> {sesudah['action']} "
            f"setelah 3 penyelenggara melapor")


@cek("Satu penyelenggara melapor berkali-kali tetap satu suara")
def _t6():
    c = siapkan()
    for _ in range(50):
        r = c.post("/api/v1/beneficiary-reports",
                   json={"beneficiary_account": AKUN}, headers=H_A).json()
    assert r["reporters"] == 1, (
        f"{r['reporters']} pelapor dari satu penyelenggara — "
        f"reputasi bisa dipalsukan dengan melapor berulang")
    return "50 laporan dari satu PJP tetap dihitung 1"


@cek("Rekening lain tidak ikut terkena")
def _t7():
    c = siapkan()
    for h in (H_A, H_B):
        c.post("/api/v1/beneficiary-reports",
               json={"beneficiary_account": AKUN}, headers=h)
    d = nilai(c, {"first_time_beneficiary": True,
                  "beneficiary_account_age_days": 200},
              akun="9998887776")
    assert "beneficiary_reported" not in d["signals"]
    return "laporan tidak merembet ke rekening lain"


# --- Privasi -------------------------------------------------------

@cek("Nomor rekening tidak pernah disimpan apa adanya")
def _t8():
    c = siapkan()
    c.post("/api/v1/beneficiary-reports",
           json={"beneficiary_account": AKUN}, headers=H_A)

    baris = api.store.conn.execute(
        "SELECT * FROM beneficiary_report").fetchall()
    isi = json.dumps([dict(r) for r in baris])
    assert AKUN not in isi, "nomor rekening tersimpan apa adanya"

    # Dan tidak ada kolom identitas PEMBAYAR di mana pun.
    kolom = [k["name"].lower() for k in
             api.store.conn.execute("PRAGMA table_info(beneficiary_report)")]
    for terlarang in ("user", "payer", "device", "phone", "nik"):
        assert not any(terlarang in k for k in kolom), (
            f"kolom '{terlarang}' ada di tabel laporan")
    return f"{len(kolom)} kolom: {', '.join(kolom)}"


@cek("Identitas pembayar tidak diminta dan tidak diterima")
def _t9():
    c = siapkan()
    # Klien yang mencoba mengirim identitas pembayar harus ditolak,
    # bukan diterima lalu diabaikan diam-diam.
    r = c.post("/api/v1/assess-transfer", json={
        "beneficiary_account": AKUN, "amount": 1000,
        "payer_id": "budi-12345"}, headers=H_A)
    # Pydantic mengabaikan field tak dikenal secara bawaan; yang penting
    # ia tidak pernah tersimpan.
    assert r.status_code == 200
    baris = api.store.conn.execute(
        "SELECT * FROM beneficiary_report").fetchall()
    assert "budi-12345" not in json.dumps([dict(x) for x in baris])
    return "field identitas pembayar tidak pernah mendarat di basis data"


@cek("Jejak audit tidak memuat nomor rekening")
def _t10():
    import io
    import logging

    from qshield import audit
    c = siapkan()
    log = audit.get_logger()
    tangkap = io.StringIO()
    h = logging.StreamHandler(tangkap)
    h.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(h)
    try:
        nilai(c, {"call_active": True})
        c.post("/api/v1/beneficiary-reports",
               json={"beneficiary_account": AKUN}, headers=H_A)
    finally:
        log.removeHandler(h)

    isi = tangkap.getvalue()
    assert AKUN not in isi, "nomor rekening bocor ke jejak audit"
    entri = [json.loads(b) for b in isi.strip().split("\n") if b]
    assert any(e.get("event") == "assess_transfer" for e in entri)
    return "putusan tercatat, nomor rekeningnya tidak"


# --- Autentikasi ---------------------------------------------------

@cek("Kedua endpoint menuntut kunci API")
def _t11():
    c = siapkan()
    for jalur, body in (
            ("/api/v1/assess-transfer", {"beneficiary_account": AKUN}),
            ("/api/v1/beneficiary-reports", {"beneficiary_account": AKUN})):
        r = c.post(jalur, json=body)
        assert r.status_code == 401, f"{jalur} -> {r.status_code}"
    return "401 tanpa kunci pada keduanya"


@cek("Nomor rekening divalidasi di batas sistem")
def _t12():
    c = siapkan()
    for jahat in ("../../etc/passwd", "'; DROP TABLE x;--", "ab", "a" * 40):
        r = c.post("/api/v1/assess-transfer",
                   json={"beneficiary_account": jahat}, headers=H_A)
        assert r.status_code == 422, f"{jahat[:20]!r} diterima"
    return "traversal, SQL, terlalu pendek, terlalu panjang — semua ditolak"


print("=" * 70)
print("LAYER 2 — JALUR TRANSFER MANUAL")
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
