"""Kalibrasi: membedakan pedagang KELILING dari stiker yang DISEBAR.

Keduanya menghasilkan gejala yang sama persis di `bindings`: satu
Merchant ID muncul di banyak area berjauhan. Aturan `nmid_scatter`
sekarang menghukum gejala itu (+60, "pola khas stiker yang disebar"),
sehingga gerobak kopi keliling yang sah divonis anomaly.

Pembedanya bukan statistik melainkan FISIK:

    satu gerobak hanya bisa berada di satu tempat pada satu waktu;
    lima stiker yang ditempel bersamaan hidup di lima tempat sekaligus.

Yang diuji di sini: apakah jejak `observations` yang kita punya — satu
stempel waktu per (tempat, pengamat berbeda) — cukup rapat untuk
memperlihatkan perbedaan itu.

Statistiknya: urutkan seluruh pengamatan satu NMID menurut waktu. Untuk
tiap pasangan BERURUTAN yang jatuh di area BERBEDA, hitung kecepatan
yang diperlukan untuk berpindah. Gerobak menghasilkan kecepatan wajar;
stiker yang hidup bersamaan memaksa kecepatan mustahil.

  python scripts/calibrate_keliling.py
"""

import os
import random
import sys

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(AKAR, "src"))

from qshield import geo  # noqa: E402

random.seed(11)

JAM = 3600.0
HARI = 24 * JAM


def titik_acak(rng, n, sebar=0.05):
    """n titik dalam satu kota, berjarak minimal 1 km satu sama lain.

    `sebar` derajat; 0,05 kira-kira radius 5 km (kota), 0,20 radius 22 km
    (metropolitan seperti Jabodetabek).
    """
    dasar_lat, dasar_lng = -6.9147, 107.6098
    keluar = []
    while len(keluar) < n:
        lat = dasar_lat + rng.uniform(-sebar, sebar)
        lng = dasar_lng + rng.uniform(-sebar, sebar)
        if all(geo.haversine_m(lat, lng, a, b) > 1000 for a, b in keluar):
            keluar.append((lat, lng))
    return keluar


def rentang_km(titik):
    """Jarak terjauh antar dua titik yang disinggahi."""
    return max(
        (geo.haversine_m(*a, *b) / 1000
         for i, a in enumerate(titik) for b in titik[i + 1:]),
        default=0.0)


def keliling(rng):
    """Satu gerobak. Tiap sesi ia berada di SATU titik saja."""
    titik = titik_acak(rng, rng.randint(3, 7))
    obs, t = [], 0.0
    for _ in range(rng.randint(8, 20)):          # sesi mangkal
        idx = rng.randrange(len(titik))
        lama = rng.uniform(2 * JAM, 6 * JAM)     # lama mangkal
        for _ in range(rng.randint(1, 5)):       # pembeli berbeda
            obs.append((t + rng.uniform(0, lama), idx))
        # pindah: makan waktu, dan sisa harinya tidak dipakai
        t += lama + rng.uniform(1 * JAM, 20 * JAM)
    return titik, obs


def keliling_motor(rng):
    """Kopi keliling BERMOTOR — kasus terberat untuk ambang kecepatan.

    Berbeda dari gerobak dorong: titiknya lebih jauh, perpindahannya
    cepat, dan ia bisa singgah di beberapa titik dalam satu jam. Kalau
    ambangnya sampai menuduh profil ini, ambangnya salah.
    """
    titik = titik_acak(rng, rng.randint(4, 8))
    obs, t = [], 0.0
    for _ in range(rng.randint(15, 30)):
        idx = rng.randrange(len(titik))
        lama = rng.uniform(10 * 60, 45 * 60)       # singgah 10-45 menit
        for _ in range(rng.randint(1, 3)):
            obs.append((t + rng.uniform(0, lama), idx))
        # pindah cepat: 5-20 menit antar titik, lalu lanjut
        t += lama + rng.uniform(5 * 60, 20 * 60)
    return titik, obs


def keliling_metropolitan(rng):
    """Bermotor, jangkauan METROPOLITAN — profil terluas yang masih wajar."""
    titik = titik_acak(rng, rng.randint(4, 8), sebar=0.20)
    obs, t = [], 0.0
    for _ in range(rng.randint(15, 30)):
        idx = rng.randrange(len(titik))
        lama = rng.uniform(20 * 60, 60 * 60)
        for _ in range(rng.randint(1, 3)):
            obs.append((t + rng.uniform(0, lama), idx))
        t += lama + rng.uniform(20 * 60, 60 * 60)
    return titik, obs


def disebar_antarkota(rng):
    """Stiker disebar ANTAR KOTA — Bandung, Jakarta, Surabaya, Medan."""
    kota = [(-6.9147, 107.6098), (-6.2000, 106.8167),
            (-7.2575, 112.7521), (3.5952, 98.6722), (-6.5971, 106.8060)]
    rng.shuffle(kota)
    titik = kota[:rng.randint(3, 5)]
    obs = []
    for idx in range(len(titik)):
        for _ in range(rng.randint(1, 5)):
            obs.append((rng.uniform(0, 20 * HARI), idx))
    return titik, obs


def disebar(rng):
    """Stiker ditempel di banyak tempat, lalu HIDUP BERSAMAAN."""
    titik = titik_acak(rng, rng.randint(3, 7))
    obs = []
    for idx in range(len(titik)):
        for _ in range(rng.randint(1, 5)):
            obs.append((rng.uniform(0, 20 * HARI), idx))
    return titik, obs


def kecepatan_maks(titik, obs, hanya_berurutan=False):
    """km/jam tertinggi yang dituntut jejak ini. None kalau tak terhitung.

    SELURUH pasangan lintas-area diperiksa, bukan hanya yang berurutan
    dalam waktu. Pasangan paling memberatkan justru sering terpisah oleh
    pengamatan di area ketiga, sehingga pemeriksaan berurutan
    melewatkannya. Ongkosnya O(n^2) pada n pengamatan satu NMID — dan n
    di sini puluhan, bukan ribuan.
    """
    obs = sorted(obs)
    pasangan = (zip(obs, obs[1:]) if hanya_berurutan
                else ((a, b) for i, a in enumerate(obs) for b in obs[i + 1:]))
    puncak = None
    for (t1, a1), (t2, a2) in pasangan:
        if a1 == a2:
            continue
        jarak_km = geo.haversine_m(*titik[a1], *titik[a2]) / 1000
        jam = abs(t2 - t1) / JAM
        if jam <= 0:
            return float("inf")
        v = jarak_km / jam
        puncak = v if puncak is None else max(puncak, v)
    return puncak


def sebaran(fn, n=600):
    """Dua statistik di atas JEJAK YANG SAMA, supaya sebanding.

    Membangkitkan ulang untuk tiap statistik akan membandingkan dua
    sampel acak yang berbeda — dan selisihnya lalu terbaca sebagai
    perbedaan metode, padahal cuma derau.
    """
    semua, berurutan = [], []
    for _ in range(n):
        titik, obs = fn(random)
        a = kecepatan_maks(titik, obs, hanya_berurutan=False)
        b = kecepatan_maks(titik, obs, hanya_berurutan=True)
        if a is not None and b is not None:
            semua.append(a)
            berurutan.append(b)
    return sorted(semua), sorted(berurutan)


def persen(xs, p):
    return xs[min(len(xs) - 1, int(p * len(xs)))]


k, k_ber = sebaran(keliling)
m, _ = sebaran(keliling_motor)
mm, _ = sebaran(keliling_metropolitan)
d, d_ber = sebaran(disebar)

print("=" * 74)
print("KECEPATAN YANG DITUNTUT JEJAK — km/jam")
print("=" * 74)
print(f"\n  {'':16}{'p50':>10}{'p75':>10}{'p90':>10}{'p95':>10}{'p99':>10}")
print("  " + "-" * 66)
for nama, xs in (("gerobak dorong", k), ("keliling bermotor", m),
                 ("keliling metropolitan", mm), ("stiker disebar", d)):
    print(f"  {nama:<16}" + "".join(
        f"{persen(xs, p):>10.1f}" for p in (0.50, 0.75, 0.90, 0.95, 0.99)))

print("\n" + "=" * 74)
print("SAPUAN AMBANG")
print("=" * 74)
print(f"\n  {'ambang':>8}{'dorong tertuduh':>18}{'bermotor tertuduh':>20}"
      f"{'stiker tertangkap':>20}")
print("  " + "-" * 66)
for ambang in (20, 40, 60, 80, 120, 200):
    s1 = sum(1 for v in k if v > ambang) / len(k)
    s2 = sum(1 for v in m if v > ambang) / len(m)
    t = sum(1 for v in d if v > ambang) / len(d)
    print(f"  {ambang:>8}{s1 * 100:>17.1f}%{s2 * 100:>19.1f}%{t * 100:>19.1f}%")

print("\n  Pembanding — kalau hanya pasangan BERURUTAN yang diperiksa:\n")
print(f"  {'ambang km/jam':>14}{'gerobak tertuduh':>20}{'stiker tertangkap':>20}")
print("  " + "-" * 56)
for ambang in (20, 40, 60, 80, 120, 200):
    salah = sum(1 for v in k_ber if v > ambang) / len(k_ber)
    tangkap = sum(1 for v in d_ber if v > ambang) / len(d_ber)
    print(f"  {ambang:>14}{salah * 100:>19.1f}%{tangkap * 100:>19.1f}%")


print("\n" + "=" * 74)
print("RENTANG JARAK — sejauh apa satu NMID menyebar")
print("=" * 74)


def rentang_sebaran(fn, n=600):
    return sorted(rentang_km(fn(random)[0]) for _ in range(n))


print(f"\n  {'':24}{'p50':>9}{'p90':>9}{'p99':>9}{'maks':>10}   (km)")
print("  " + "-" * 62)
for nama, fn in (("gerobak dorong", keliling),
                 ("keliling bermotor", keliling_motor),
                 ("keliling metropolitan", keliling_metropolitan),
                 ("stiker sekota", disebar),
                 ("stiker ANTAR KOTA", disebar_antarkota)):
    xs = rentang_sebaran(fn)
    print(f"  {nama:<24}{persen(xs, .50):>9.1f}{persen(xs, .90):>9.1f}"
          f"{persen(xs, .99):>9.1f}{xs[-1]:>10.1f}")

print("\n  Pedagang keliling bekerja dalam satu kota. Satu NMID yang muncul")
print("  di kota berbeda bukan gerobak — berapa pun waktunya berselang.")
print(f"\n  {'ambang rentang':>16}{'metropolitan tertuduh':>24}"
      f"{'antar kota tertangkap':>24}")
print("  " + "-" * 64)
for ambang in (30, 50, 80, 120):
    a = rentang_sebaran(keliling_metropolitan)
    b = rentang_sebaran(disebar_antarkota)
    s1 = sum(1 for v in a if v > ambang) / len(a)
    s2 = sum(1 for v in b if v > ambang) / len(b)
    print(f"  {ambang:>13} km{s1 * 100:>23.1f}%{s2 * 100:>23.1f}%")
