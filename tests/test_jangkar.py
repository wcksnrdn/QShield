"""
Jangkar ditentukan oleh JARAK, bukan oleh kesamaan sel geohash.

Kalimat itu sudah tertulis di docstring binding.py sejak awal, dan
jalur BACA mematuhinya. Jalur TULIS tidak: penulisan memakai
ON CONFLICT (nmid, geohash_7), sehingga sel geohash-lah yang
menentukan sebuah pemindaian masuk ke jangkar mana.

Sel presisi 7 berukuran ~153 m. Dua pemindaian pedagang yang SAMA yang
jatuh di sisi berlawanan batas sel menjadi dua jangkar berbeda walau
jaraknya cuma puluhan meter — dan pengamatnya terpecah, sehingga tidak
satu pun jangkar mencapai MIN_OBSERVERS.

Koordinat di sini BUKAN karangan. Ketiganya diambil dari produksi:
satu warung yang dipindai tiga HP dalam menit yang sama dan tercatat
sebagai tiga tempat, sehingga pedagang dengan empat pengamat tidak
pernah bisa menjadi hijau.

    PYTHONPATH=scripts python3 tests/test_jangkar.py
"""

import os
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone

from qshield import binding as bd
from qshield import geo
from qshield.store import Store

NOW = datetime.now(timezone.utc)
NMID = "ID1024336136808"

# Tiga titik dari produksi, apa adanya.
#
#   A <-> B :  43 m  -> DI DALAM radius jangkar, harus menyatu
#   A <-> C : 108 m  -> DI LUAR radius, sah sebagai tempat berbeda
#
# Ketiganya jatuh di sel geohash-7 yang BERBEDA, dan itulah yang dulu
# memecahnya.
A = (-6.170006, 106.870650)
B = (-6.169701, 106.870895)
C = (-6.170810, 106.871195)

_hasil = []


def cek(nama):
    def deco(fn):
        try:
            _hasil.append((nama, True, fn() or ""))
        except AssertionError as exc:
            _hasil.append((nama, False, str(exc)))
        return fn
    return deco


def toko():
    return Store(os.path.join(tempfile.mkdtemp(), "jangkar.db"))


def rekam(s, titik, dev, jam_lalu=0, nmid=NMID):
    return s.record(nmid=nmid, lat=titik[0], lng=titik[1],
                    device_anon_id=dev, merchant_name="AYAM PENYET CABE IJO",
                    now=NOW - timedelta(hours=jam_lalu))


@cek("Prasyaratnya benar: ketiga titik memang beda sel geohash")
def _t1():
    """Kalau ini gagal, seluruh berkas ini menguji hal yang salah."""
    sel = {n: geo.encode(*t, bd.INDEX_PRECISION)
           for n, t in (("A", A), ("B", B), ("C", C))}
    assert len(set(sel.values())) == 3, sel
    d_ab = geo.haversine_m(*A, *B)
    d_ac = geo.haversine_m(*A, *C)
    assert d_ab <= bd.ANCHOR_RADIUS_M, f"A-B {d_ab:.0f} m"
    assert d_ac > bd.ANCHOR_RADIUS_M, f"A-C {d_ac:.0f} m"
    return (f"A-B {d_ab:.0f} m (dalam radius), A-C {d_ac:.0f} m (luar), "
            f"3 sel berbeda")


@cek("Dua pemindaian 43 m terpisah menjadi SATU jangkar")
def _t2():
    """Inti perbaikannya. Dulu jadi dua, masing-masing 1 pengamat."""
    s = toko()
    rekam(s, A, "hp-satu")
    rekam(s, B, "hp-dua")
    jangkar = s.by_nmid(NMID)
    assert len(jangkar) == 1, f"{len(jangkar)} jangkar, seharusnya 1"
    assert jangkar[0].observer_count == 2, jangkar[0].observer_count
    return "1 jangkar, 2 pengamat — bukan 2 jangkar berisi 1 pengamat"


@cek("Tapi 108 m TETAP dipisah — radius tidak dilebarkan diam-diam")
def _t3():
    """Perbaikan yang menyatukan terlalu banyak sama buruknya:
    dua pedagang bersebelahan akan saling menelan."""
    s = toko()
    rekam(s, A, "hp-satu")
    rekam(s, C, "hp-tiga")
    jangkar = s.by_nmid(NMID)
    assert len(jangkar) == 2, f"{len(jangkar)} jangkar, seharusnya 2"
    return f"{len(jangkar)} jangkar — jarak di luar radius tetap dihormati"


@cek("Kasus produksi utuh: pedagang yang tadinya mustahil hijau")
def _t4():
    """Jejak sebenarnya: satu pengamat 23/09, lalu tiga HP pada 28/09.

    Sebelum perbaikan: 3 jangkar, pengamat 2/1/1, tidak satu pun
    mencapai MIN_OBSERVERS=3. Sesudah: jangkar utama mencapainya, dan
    rentang 5 hari melewati MIN_AGE_HOURS."""
    s = toko()
    rekam(s, A, "hp-lama", jam_lalu=120)      # 23/09
    rekam(s, B, "hp-dua")                     # 28/09, 43 m
    rekam(s, A, "hp-tiga")                    # 28/09, titik sama
    rekam(s, C, "hp-empat")                   # 28/09, 108 m — terpisah

    jangkar = sorted(s.by_nmid(NMID), key=lambda b: -b.observer_count)
    utama = jangkar[0]
    assert utama.observer_count >= bd.MIN_OBSERVERS, utama.observer_count
    assert utama.age_hours >= bd.MIN_AGE_HOURS, utama.age_hours
    assert utama.is_established, "belum mapan padahal syaratnya terpenuhi"
    return (f"{len(jangkar)} jangkar; yang utama {utama.observer_count} "
            f"pengamat, rentang {utama.age_hours:.0f} jam — MAPAN")


@cek("Pemindaian serentak dari titik berbeda tetap satu jangkar")
def _t5():
    """Kekhawatiran lama soal balapan periksa-lalu-tulis.

    BEGIN IMMEDIATE memegang kunci tulis sejak awal, jadi pencarian
    jangkar di dalam transaksi tidak bisa disela penulis lain."""
    s = toko()
    galat = []

    def kirim(i):
        try:
            # Digeser beberapa meter tiap utas, meniru derau GPS.
            rekam(s, (A[0] + i * 0.000012, A[1] + i * 0.000012),
                  f"hp-paralel-{i:03d}")
        except Exception as exc:
            galat.append(f"{type(exc).__name__}: {exc}")

    utas = [threading.Thread(target=kirim, args=(i,)) for i in range(20)]
    for u in utas:
        u.start()
    for u in utas:
        u.join()

    assert not galat, f"{len(galat)} gagal: {sorted(set(galat))[:2]}"
    jangkar = s.by_nmid(NMID)
    assert len(jangkar) == 1, f"{len(jangkar)} jangkar dari 20 utas paralel"
    assert jangkar[0].observer_count == 20, jangkar[0].observer_count
    return "20 utas paralel -> 1 jangkar, 20 pengamat"


@cek("Perangkat yang sama tidak dihitung dua kali walau titiknya bergeser")
def _t6():
    """Idempotensi harus bertahan menembus perbaikan ini: kalau tidak,
    satu orang bisa menumbuhkan konsensus sendirian dengan berjalan
    beberapa meter."""
    s = toko()
    rekam(s, A, "hp-sama")
    rekam(s, B, "hp-sama")          # 43 m, jangkar yang sama
    jangkar = s.by_nmid(NMID)
    assert len(jangkar) == 1 and jangkar[0].observer_count == 1, (
        f"{len(jangkar)} jangkar, {jangkar[0].observer_count} pengamat")
    return "berpindah 43 m tidak menambah pengamat"


@cek("Putusan memilih jangkar TERDEKAT, bukan yang kebetulan pertama")
def _t7():
    """Basis data lama masih memuat jangkar kembar dalam satu radius.
    Selama itu ada, pemilihannya tidak boleh bergantung urutan rowid."""
    jauh = bd.Binding(nmid=NMID, lat=A[0], lng=A[1], observer_count=40,
                      first_seen=NOW - timedelta(days=90), last_seen=NOW)
    dekat = bd.Binding(nmid=NMID, lat=B[0], lng=B[1], observer_count=3,
                       first_seen=NOW - timedelta(days=90), last_seen=NOW)
    # Dipindai PERSIS di B; yang terdekat jelas `dekat`.
    v = bd.evaluate(NMID, B[0], B[1], [jauh, dekat], [], now=NOW)
    assert v.matched_binding is not None
    assert v.matched_binding.observer_count == 3, (
        f"terpilih yang {v.matched_binding.observer_count} pengamat, "
        f"bukan yang terdekat")
    return "yang terdekat menang, bukan yang lebih dulu ada di daftar"


print("=" * 70)
print("JANGKAR DITENTUKAN JARAK, BUKAN SEL GEOHASH")
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
