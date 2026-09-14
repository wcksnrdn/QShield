"""Kalibrasi peluruhan sinyal percobaan anomali.

`last_anomaly_at` disimpan sejak Keputusan 11 dan tidak pernah dibaca.
Akibatnya serangan tiga minggu lalu menghukum sekeras serangan satu jam
lalu — dan merchant yang baru pindah ke lokasi itu ikut menanggungnya.

Pertanyaan yang dikalibrasi di sini: berapa lama sebuah jangkar yang
pernah diserang pantas tetap "panas"?

Dua sisi yang ditimbang:
  terlalu lama   merchant sah yang baru muncul di titik itu dihukum
                 berbulan-bulan untuk sesuatu yang terjadi sebelum
                 mereka ada (aset A4 — kredibilitas)
  terlalu cepat  penyerang cukup menunggu, lalu kembali
"""

import math

from qshield import behavior as bh
from qshield import binding as bd

HALFLIFE_DIUJI = [1, 3, 7, 14, 30, 90]

# Berapa lama stiker palsu bertahan sebelum dicabut atau ketahuan.
# Rentangnya sengaja lebar — angkanya tidak diketahui pasti.
UMUR_STIKER_HARI = [1, 3, 7, 14]


def bobot(attempts, hari, halflife):
    dasar = min(bh.W_ANOMALY_CAP, bh.W_ANOMALY_BASE * attempts)
    return dasar * (0.5 ** (hari / halflife))


print("=" * 74)
print("1. BIAYA BAGI MERCHANT SAH YANG BARU MUNCUL DI JANGKAR ITU")
print("=" * 74)
print()
print("  Jangkar pernah diserang 3 kali. Lalu penyerangnya pergi dan")
print("  merchant sah membuka usaha di titik yang sama.")
print()
print(f"  {'halflife':>10}", "".join(f"{f'+{h}h':>9}" for h in (1, 7, 30, 90)))
print("  " + "-" * 60)
for hl in HALFLIFE_DIUJI:
    baris = []
    for hari in (1, 7, 30, 90):
        b = bobot(3, hari, hl)
        # Merchant baru: first_observation 35 + bobot ini.
        total = min(100, 35 + b)
        baris.append(f"{bd._action_for(int(total))[:8]:>9}")
    print(f"  {hl:>6} hari", "".join(baris))

print()
print("  Kolom yang berisi 'warn' berarti merchant sah itu diperlakukan")
print("  sama seperti merchant baru biasa — tidak dihukum ekstra.")

print()
print("=" * 74)
print("2. BERAPA LAMA PENYERANG HARUS MENUNGGU")
print("=" * 74)
print()
print("  Supaya bobotnya turun di bawah 5 poin (praktis tidak berarti):")
print()
print(f"  {'halflife':>10}{'setelah 3 percobaan':>24}{'setelah 10 percobaan':>24}")
print("  " + "-" * 60)
for hl in HALFLIFE_DIUJI:
    tunggu = []
    for att in (3, 10):
        dasar = min(bh.W_ANOMALY_CAP, bh.W_ANOMALY_BASE * att)
        hari = hl * math.log2(dasar / 5) if dasar > 5 else 0
        tunggu.append(f"{hari:>19.0f} hari")
    print(f"  {hl:>6} hari", "".join(tunggu))

print()
print("  Menunggu itu sendiri mahal bagi penyerang: stikernya tidak")
print("  menghasilkan apa pun selama itu, dan binding merchant sah terus")
print("  menguat — tiap pengamat baru menaikkan bobot konflik lewat")
print(f"  rumus 60 + min(25, n//2) (invarian §5).")

print()
print("=" * 74)
print("KESIMPULAN")
print("=" * 74)
print()
print("  Halflife 7 hari:")
print("    - merchant sah yang muncul sebulan kemudian tidak dihukum lagi")
print("    - penyerang harus menunggu ~3 minggu agar jejaknya pudar")
print("    - selama menunggu, stikernya mati dan korbannya menguat")
print()
print("  Di bawah 3 hari, jejaknya hilang terlalu cepat untuk berguna.")
print("  Di atas 30 hari, merchant yang baru pindah menanggung sejarah")
print("  yang bukan miliknya — persis keluhan yang memunculkan kalibrasi")
print("  ini.")
