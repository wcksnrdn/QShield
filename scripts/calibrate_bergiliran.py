"""Kalibrasi bukti BERGILIRAN — satu tempat dipakai bergantian waktu.

Es buah mangkal siang; sore ia pulang dan pedagang lain menempati titik
yang sama persis. Keduanya sah, dan keduanya punya QRIS sendiri.

Hari ini pedagang kedua dituduh menukar stiker selama 3-9 hari sampai
`kehadiran_terbukti` terpenuhi (8 perangkat berbeda + rentang 24 jam).
Ongkos itu ditanggung orang yang tidak bersalah.

GAGASANNYA. Bukti yang dipakai sekarang — "merchant lama MASIH
terpindai" — sudah benar arahnya tapi terlalu lemah bentuknya: ia cuma
menuntut satu pemindaian merchant lama setelah penantang muncul.

Yang jauh lebih kuat, dan gratis karena datanya sudah ada:
**berselang-seling**. Merchant lama terpindai, lalu penantang, lalu
merchant lama lagi, lalu penantang lagi.

Stiker yang MENUTUPI tidak bisa menghasilkan pola itu. Begitu ia
menutup, QR di bawahnya hilang dan tidak pernah muncul lagi. Untuk
berselang-seling, penyerang harus mencopot stikernya, membiarkan korban
dipindai, lalu memasangnya kembali — setiap hari, dua kali sehari, di
lapak orang. Itu berhenti menjadi serangan pasif.

Yang diukur di sini: berapa alternasi yang harus dituntut, dan berapa
perangkat yang masih perlu, supaya pedagang giliran yang sah diterima
CEPAT sementara penukar stiker sungguhan tidak pernah diterima.

  python scripts/calibrate_bergiliran.py
"""

import os
import random
import sys

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(AKAR, "src"))

random.seed(29)

JAM = 1.0
HARI = 24.0


def alternasi(lama, penantang):
    """Berapa kali merchant lama MUNCUL KEMBALI setelah penantang.

    Hanya perpindahan penantang -> lama yang dihitung, dan arah itu
    menentukan. Perpindahan lama -> penantang tidak membuktikan apa
    pun: itu justru bentuk serangan penukaran stiker, di mana merchant
    lama terpindai sampai suatu titik lalu berhenti selamanya.

    Yang membuktikan tidak ada yang tertutup adalah merchant lama
    muncul LAGI SESUDAH penantang ada — dan makin sering berulang,
    makin mustahil dijelaskan oleh stiker yang menutupi.

    Versi pertama fungsi ini menghitung kedua arah, dan akibatnya
    terlihat langsung di sapuan: penukaran-yang-menutupi lolos pada
    ambang 1, karena satu perpindahan lama -> penantang sudah cukup
    memenuhinya. Itu justru pola serangannya.
    """
    gabung = sorted([(t, "L") for t in lama] + [(t, "P") for t in penantang])
    n, sebelum = 0, None
    for _, sisi in gabung:
        if sisi == "L" and sebelum == "P":
            n += 1
        sebelum = sisi
    return n


def bergiliran(rng, hari, per_hari_lama, per_hari_penantang):
    """Es buah siang (08-16), pedagang malam (18-23). Keduanya sah."""
    lama, pen = [], []
    for d in range(hari):
        for _ in range(per_hari_lama):
            lama.append(d * HARI + rng.uniform(8, 16))
        for _ in range(per_hari_penantang):
            pen.append(d * HARI + rng.uniform(18, 23))
    return lama, pen


def tertutup(rng, hari, per_hari_lama, per_hari_penantang):
    """Penukaran sungguhan: stiker menutupi, merchant lama HILANG.

    Merchant lama masih terpindai beberapa hari SEBELUM stiker
    dipasang, lalu berhenti sama sekali.
    """
    lama, pen = [], []
    mulai_serang = 3
    for d in range(hari):
        if d < mulai_serang:
            for _ in range(per_hari_lama):
                lama.append(d * HARI + rng.uniform(8, 20))
        else:
            for _ in range(per_hari_penantang):
                pen.append(d * HARI + rng.uniform(8, 23))
    return lama, pen


def paruh_waktu(rng, hari, per_hari_lama, per_hari_penantang):
    """Penyerang yang memasang-mencopot stikernya tiap hari.

    SENGAJA dimasukkan, dan hasilnya memang tidak terpisahkan dari
    pedagang giliran yang sah — lihat kesimpulan di bawah.
    """
    return bergiliran(rng, hari, per_hari_lama, per_hari_penantang)


def hari_sampai_diterima(fn, min_alt, min_dev, per_lama, per_pen,
                         maks_hari=30):
    """Hari ke berapa syaratnya terpenuhi. None kalau tidak pernah."""
    for hari in range(1, maks_hari + 1):
        lama, pen = fn(random, hari, per_lama, per_pen)
        if not pen:
            continue
        # Satu perangkat berbeda per pemindaian penantang, batas atas
        # yang murah hati bagi penyerang.
        perangkat = len(pen)
        rentang = max(pen) - min(pen)
        if (alternasi(lama, pen) >= min_alt
                and perangkat >= min_dev
                and rentang >= 24):
            return hari
    return None


print("=" * 74)
print("1. ALTERNASI YANG DIHASILKAN TIAP POLA")
print("=" * 74)
print(f"\n  {'pola':<28}{'kemunculan kembali, 7 hari':>28}")
print("  " + "-" * 58)
for nama, fn in (("bergiliran (sah)", bergiliran),
                 ("stiker menutupi (serangan)", tertutup),
                 ("swap paruh waktu", paruh_waktu)):
    nilai = []
    for _ in range(200):
        lama, pen = fn(random, 7, 3, 3)
        nilai.append(alternasi(lama, pen))
    nilai.sort()
    print(f"  {nama:<28}{f'{nilai[len(nilai)//2]} (median)':>28}")

print("\n  Stiker yang menutupi menghasilkan NOL kemunculan kembali:")
print("  begitu ia menutup, QR di bawahnya hilang dan tidak pernah")
print("  muncul lagi. Itu batas struktural, bukan kebetulan statistik.")

print("\n" + "=" * 74)
print("2. SAPUAN AMBANG — berapa hari sampai pedagang giliran diterima")
print("=" * 74)
print(f"\n  {'kembali':>10}{'perangkat':>11}"
      f"{'giliran sah':>14}{'stiker menutupi':>18}")
print("  " + "-" * 55)
for min_alt in (1, 2, 3, 5):
    for min_dev in (3, 5, 8):
        sah = hari_sampai_diterima(bergiliran, min_alt, min_dev, 3, 3)
        srg = hari_sampai_diterima(tertutup, min_alt, min_dev, 3, 3)
        print(f"  {min_alt:>10}{min_dev:>11}"
              f"{(f'{sah} hari' if sah else 'tidak pernah'):>14}"
              f"{(f'{srg} hari' if srg else 'TIDAK PERNAH'):>18}")

print("\n" + "=" * 74)
print("3. LAPAK SEPI — berapa pembeli berbeda per hari")
print("=" * 74)
print(f"\n  kemunculan kembali >= 2, perangkat >= 4\n")
print(f"  {'pembeli/hari':>14}{'hari sampai diterima':>24}")
print("  " + "-" * 40)
for per in (1, 2, 3, 5, 10):
    h = hari_sampai_diterima(bergiliran, 2, 4, per, per)
    print(f"  {per:>14}{(f'{h} hari' if h else 'tidak pernah'):>24}")

print("\n" + "=" * 74)
print("KESIMPULAN")
print("=" * 74)
print("""
  Alternasi >= 3 menutup penukaran-yang-menutupi SECARA STRUKTURAL,
  bukan statistik: stiker yang menutup membuat merchant lama hilang,
  jadi giliran tidak pernah berpindah lebih dari sekali.

  Karena buktinya jauh lebih kuat, syarat perangkat bisa diturunkan
  dari 8 tanpa melemahkan apa pun — yang menjaga keamanan memang bukan
  jumlah perangkat, melainkan syarat merchant lama tetap terpindai.

  BATAS YANG HARUS DISEBUT TERUS TERANG: penyerang yang memasang lalu
  MENCOPOT stikernya tiap hari menghasilkan pola yang sama persis
  dengan pedagang giliran yang sah. Tidak ada di data yang bisa
  memisahkan keduanya, dan tidak ada yang akan kami klaim bisa.

  Yang berubah adalah ONGKOSNYA: dari "tempel sekali lalu pergi"
  menjadi "hadir dua kali sehari di lapak orang, setiap hari, selamanya"
  — sambil membiarkan korbannya menerima pembayaran di separuh waktu.
  Itu berhenti menjadi serangan pasif, dan mulai menjadi pekerjaan.
""")
