"""
Angka yang dikutip docs/KALIBRASI-BOBOT.md dikunci di sini.

Dokumen itu menjawab "kenapa yang fatal cuma +75, bukan 100" dengan
angka hasil menjalankan compose() sungguhan. Tanpa berkas ini angkanya
akan basi diam-diam begitu ada bobot yang digeser — dan dokumen yang
angkanya salah lebih buruk daripada tidak ada dokumen.

Pelajaran yang sama sudah pernah kena: demonstrasi yang punya
ekstraktornya sendiri melenceng dari model yang didemonstrasikannya.

    PYTHONPATH=src python3 tests/test_bobot.py
"""

import sys
from datetime import datetime, timedelta, timezone

from qshield import behavior as bh
from qshield import binding as bd
from qshield import profile as pf

NOW = datetime(2026, 9, 30, 10, 0, tzinfo=timezone.utc)
LAT, LNG = -6.914744, 107.609810
NM = "ID1099887766554"

_hasil = []


def cek(nama):
    def deco(fn):
        try:
            _hasil.append((nama, True, fn() or ""))
        except AssertionError as exc:
            _hasil.append((nama, False, str(exc)))
        return fn
    return deco


def l2(bobot, hard=False, nama="s"):
    return bh.BehaviorResult(score=bobot, signals=[nama], reasons=["x"],
                             weights=[bobot], hard_violation=hard)


def jangkar(obs=47, umur_hari=180):
    return bd.Binding(nmid=NM, lat=LAT, lng=LNG, merchant_name="WARUNG",
                      observer_count=obs,
                      first_seen=NOW - timedelta(days=umur_hari),
                      last_seen=NOW - timedelta(hours=6))


def l1(nearby):
    return bd.evaluate(NM, LAT, LNG, nearby, [], now=NOW,
                       merchant_name="WARUNG")


@cek("Bobot tidak menentukan status; hard_violation yang menentukan")
def _t1():
    """Klaim inti dokumen. Kalau ini jebol, seluruh alasan 'kenapa
    bukan 100' ikut jebol."""
    dasar = l1([])
    for bobot in (1, 10, 70, 75, 100):
        v = bd.compose(dasar, l2(bobot, hard=True))
        assert v.status == bd.ANOMALY, (
            f"bobot {bobot} dengan hard_violation -> {v.status}")
    return "anomaly pada bobot 1 sampai 100, tanpa kecuali"


@cek("Di atas 65, skornya jenuh — 70/75/100 tidak terbedakan")
def _t2():
    """Alasan kedua kenapa menaikkan ke 100 tidak membeli apa pun."""
    dasar = l1([])
    assert dasar.risk_score == 35, f"first_observation = {dasar.risk_score}"
    hasil = {b: bd.compose(dasar, l2(b, hard=True)) for b in (70, 75, 100)}
    tier = {v.action for v in hasil.values()}
    skor = {v.risk_score for v in hasil.values()}
    assert tier == {bd.COOLING_OFF}, tier
    assert skor == {100}, skor
    return "35 + 70/75/100 -> semuanya 100/cooling_off"


@cek("Selisih 75 vs 100 hanya terasa di jangkar mapan milik sendiri")
def _t3():
    """Inilah yang dibeli angka 75: QR yang dikonfirmasi 47 pengamatan
    dengan label tercetak tidak cocok mendapat step_up, bukan
    cooling_off. Yang paling mungkin salah di situ OCR-nya."""
    dasar = l1([jangkar()])
    assert dasar.risk_score == 0, f"L1 terendah = {dasar.risk_score}"
    v = bd.compose(dasar, l2(bh.W_PRINTED_NMID_MISMATCH, hard=True))
    assert v.status == bd.ANOMALY and v.action == bd.STEP_UP, (
        f"{v.status}/{v.action} skor {v.risk_score}")
    penuh = bd.compose(dasar, l2(100, hard=True))
    assert penuh.action == bd.COOLING_OFF, penuh.action
    return f"75 -> {v.action}; 100 -> {penuh.action} (selisihnya nyata)"


@cek("Sinyal Layer 2 apa pun mencabut verified, berapa pun bobotnya")
def _t4():
    """Menahan klaim dokumen supaya tidak berlebihan: bukan bobot >25
    yang mencabut verifikasi, melainkan kehadiran sinyalnya."""
    dasar = l1([jangkar()])
    assert dasar.status == bd.VERIFIED, dasar.status
    for bobot in (1, 25, 30):
        v = bd.compose(dasar, l2(bobot))
        assert v.status == bd.UNKNOWN, f"bobot {bobot} -> {v.status}"
    return "verified -> unknown pada bobot 1 sekalipun"


@cek("Kelangkaan pada 25 tidak pernah menggeser tier sendirian")
def _t5():
    """Klaim yang MENGGANTIKAN 'veto permanen' di dokumen — yang ini
    benar dan yang itu terlalu kuat."""
    assert pf.W_RARE_PROFILE == 25, pf.W_RARE_PROFILE
    assert pf.W_RARE_PROFILE <= bd.THRESHOLDS[0][0], (
        "kelangkaan melewati batas atas pita proceed")
    dasar = l1([jangkar()])
    sendiri = bd.compose(dasar, l2(pf.W_RARE_PROFILE))
    assert sendiri.action == bd.WARN, sendiri.action

    # Selisih 25 vs 30 muncul begitu ada sinyal kedua.
    duo25 = bd.compose(dasar, l2(25 + 25))
    duo30 = bd.compose(dasar, l2(30 + 25))
    assert duo25.action == bd.WARN, duo25.action
    assert duo30.action == bd.STEP_UP, duo30.action
    return f"sendiri {sendiri.action}; +25 lain: 25->{duo25.action}, 30->{duo30.action}"


@cek("Layer 2 tidak punya satu pun bobot negatif")
def _t6():
    """Ketiadaan sinyal Layer 2 bukan bukti keabsahan (invarian §2)."""
    bobot = [(n, v) for n, v in vars(bh).items()
             if n.startswith("W_") and isinstance(v, (int, float))]
    assert bobot, "tidak ada konstanta bobot yang terbaca"
    negatif = [(n, v) for n, v in bobot if v < 0]
    assert not negatif, f"bobot negatif: {negatif}"
    return f"{len(bobot)} konstanta W_* di behavior.py, semuanya >= 0"


@cek("Sidik jari encoding tidak pernah menggeser tier sendirian")
def _t7():
    """Satu-satunya pengaman untuk dua bobot yang diakui UNCALIBRATED."""
    assert bh.W_TAG_ORDER + bh.W_CRC_CASE >= bh.SOFT_FINGERPRINT_CAP, (
        "cap lebih besar dari jumlahnya — cap tidak berfungsi")
    assert bh.SOFT_FINGERPRINT_CAP <= bd.THRESHOLDS[0][0], (
        f"cap {bh.SOFT_FINGERPRINT_CAP} melewati batas atas pita proceed")
    dasar = l1([jangkar()])
    v = bd.compose(dasar, l2(bh.SOFT_FINGERPRINT_CAP))
    assert v.action == bd.WARN, v.action
    return f"cap {bh.SOFT_FINGERPRINT_CAP} <= batas proceed {bd.THRESHOLDS[0][0]}"


@cek("Konflik jangkar TERDAFTAR sendirian mendarat di cooling_off")
def _t8():
    """Alasan angka 85 dipilih, dikutip apa adanya di dokumen."""
    assert bd.W_REGISTERED_CONFLICT >= bd.THRESHOLDS[-1][0] + 1, (
        f"{bd.W_REGISTERED_CONFLICT} tidak mencapai cooling_off")
    return (f"{bd.W_REGISTERED_CONFLICT} > {bd.THRESHOLDS[-1][0]} "
            f"-> cooling_off tanpa bantuan sinyal lain")


@cek("Tetangga belum terbukti + binding muda mendarat tepat di warn")
def _t9():
    """Aritmetika tier yang jadi alasan angka 20."""
    total = bd.W_ADJACENT_UNPROVEN + 15
    assert total == 35, total
    assert bd.THRESHOLDS[0][0] < total <= bd.THRESHOLDS[1][0], (
        f"{total} tidak jatuh di pita warn")
    return f"20 + 15 = {total}, di dalam pita warn ({bd.THRESHOLDS[1][0]} batas atas)"


print("=" * 70)
print("KALIBRASI BOBOT — angka yang dikutip dokumen")
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
