"""Kalibrasi deteksi QR dinamis yang dipakai berulang.

QR dinamis dibuat untuk SATU transaksi. Yang diukur di sini: seberapa
sering QR dinamis yang SAH dipindai lebih dari sekali, dan seberapa
jauh titik pemindaiannya berpencar — supaya ambangnya memisahkan
pengguna yang mengulang scan dari QR yang disebar ke banyak korban.

Yang TIDAK diklaim: ini bukan proteksi replay kriptografis. Itu menuntut
nonce sekali pakai di sisi PJP. Yang dideteksi di sini adalah artefak
sekali pakai yang dipakai berkali-kali — irisan besar dari modusnya,
bukan seluruhnya.
"""

import math
import random

from qshield import geo

random.seed(31)
PERCOBAAN = 20000

SIGMA_M = 8.0


def derau(lat, lng, sigma=SIGMA_M):
    r = abs(random.gauss(0, sigma))
    a = random.uniform(0, 2 * math.pi)
    return (lat + (r * math.cos(a)) / 111320,
            lng + (r * math.sin(a)) / (111320 * math.cos(math.radians(lat))))


def scan_sah():
    """Berapa kali satu QR dinamis yang sah benar-benar dipindai.

    Kebanyakan sekali. Sebagian kecil diulang: kamera gagal fokus,
    pengguna membatalkan lalu mencoba lagi, aplikasi force close.
    Sangat jarang lebih dari tiga.
    """
    r = random.random()
    if r < 0.82:
        return 1
    if r < 0.96:
        return 2
    if r < 0.995:
        return 3
    return 4


print("=" * 74)
print("1. BERAPA KALI QR DINAMIS SAH DIPINDAI")
print("=" * 74)
print()
hitung = {}
for _ in range(PERCOBAAN):
    n = scan_sah()
    hitung[n] = hitung.get(n, 0) + 1
kum = 0
print(f"  {'kali dipindai':>15}{'bagian':>12}{'kumulatif':>12}")
print("  " + "-" * 45)
for n in sorted(hitung):
    p = 100 * hitung[n] / PERCOBAAN
    kum += p
    print(f"  {n:>15}{p:>11.2f}%{kum:>11.2f}%")

print()
print(f"  {'ambang':>10}{'QR sah tertandai':>22}")
print("  " + "-" * 45)
for ambang in (2, 3, 4, 5, 6):
    salah = 100 * sum(v for k, v in hitung.items() if k >= ambang) / PERCOBAAN
    print(f"  {ambang:>10}{salah:>21.2f}%")

print()
print("=" * 74)
print("2. SEBERAPA JAUH TITIK PEMINDAIANNYA BERPENCAR")
print("=" * 74)
print()
print("  QR dinamis yang sah ditampilkan di satu mesin kasir. Pemindaian")
print("  berulang terjadi di tempat yang sama — yang berbeda hanya galat")
print("  GPS. QR yang disebar lewat pesan dipindai di rumah masing-masing.")
print()

POS = (-6.914744, 107.609810)
jarak_sah = []
for _ in range(PERCOBAAN):
    a = derau(*POS)
    b = derau(*POS)
    jarak_sah.append(geo.haversine_m(a[0], a[1], b[0], b[1]))
jarak_sah.sort()

def persentil(data, p):
    return data[min(len(data) - 1, int(len(data) * p / 100))]

print(f"  Jarak antar-pemindaian QR SAH (dua pembacaan di kasir yang sama):")
for p in (50, 90, 99, 99.9):
    print(f"      p{p:<5} {persentil(jarak_sah, p):>7.1f} m")

print()
print(f"  {'ambang jarak':>14}{'QR sah tertandai':>22}")
print("  " + "-" * 45)
for ambang in (50, 100, 150, 300, 500):
    salah = 100 * sum(1 for d in jarak_sah if d > ambang) / len(jarak_sah)
    print(f"  {ambang:>12} m{salah:>21.3f}%")

print()
print("=" * 74)
print("KESIMPULAN")
print("=" * 74)
print()
print("  Ambang pemakaian ulang: 4 kali.")
print(f"      menandai {100 * sum(v for k, v in hitung.items() if k >= 4) / PERCOBAAN:.2f}% QR sah")
print("      QR yang disebar ke puluhan korban jauh melewatinya")
print()
print("  Ambang sebaran jarak: 150 m.")
print(f"      menandai {100 * sum(1 for d in jarak_sah if d > 150) / len(jarak_sah):.3f}% QR sah")
print("      cukup longgar untuk galat GPS terburuk di dalam gedung,")
print("      cukup ketat untuk memisahkan dua rumah yang berbeda")
print()
print("  Sebaran jarak adalah sinyal yang lebih kuat: satu QR yang")
print("  dipindai di dua tempat berjauhan tidak punya penjelasan wajar,")
print("  sementara empat kali pemindaian masih mungkin terjadi.")
