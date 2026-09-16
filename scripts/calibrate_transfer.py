"""Kalibrasi bobot penilaian transfer manual.

Yang ditimbang: menangkap pola rekayasa sosial tanpa menghukum
transfer sah yang kebetulan mirip.

Kesulitan utamanya ada pada `call_active`. Pola penipuan memang korban
sedang ditelepon PELAKU — tapi menelepon ORANG YANG DIBAYAR sambil
mentransfer adalah hal yang sangat wajar: "oke aku transfer sekarang
ya". Dari sisi sistem keduanya identik.

Karena itu sinyal panggilan tidak boleh cukup sendirian. Yang
dikalibrasi di sini adalah memastikan hal itu benar.
"""

import random

from qshield import transfer as tf

random.seed(53)
SAMPEL = 20000


def transfer_sah():
    """Satu transfer sah, dengan ciri-ciri yang benar-benar terjadi."""
    # Kebanyakan ke rekening yang sudah dikenal.
    pertama_kali = random.random() < 0.28
    # Umur rekening tujuan: kebanyakan lama.
    if random.random() < 0.06:
        umur = random.randint(1, 29)      # rekening yang memang baru
    else:
        umur = random.randint(30, 3000)
    # Menelepon orang yang dibayar sambil transfer — wajar.
    menelepon = random.random() < 0.12
    # Bayar beberapa tagihan berturut-turut.
    laju = random.choices([0, 1, 2, 3, 4], [0.62, 0.22, 0.10, 0.04, 0.02])[0]
    return tf.TransferTelemetry(
        first_time_beneficiary=pertama_kali,
        beneficiary_account_age_days=umur,
        call_active=menelepon,
        transfers_last_hour=laju)


def transfer_penipuan():
    """Pola rekayasa sosial: dituntun lewat telepon ke rekening baru."""
    return tf.TransferTelemetry(
        first_time_beneficiary=True,
        beneficiary_account_age_days=random.randint(1, 25),
        call_active=random.random() < 0.85,
        transfers_last_hour=random.choices([0, 1, 2, 3, 4, 5],
                                           [.30, .20, .18, .14, .10, .08])[0])


print("=" * 74)
print("1. SINYAL TUNGGAL — tidak satu pun boleh menghukum sendirian")
print("=" * 74)
print()
tunggal = [
    ("sedang menelepon saja", tf.TransferTelemetry(call_active=True)),
    ("rekening baru saja", tf.TransferTelemetry(beneficiary_account_age_days=5)),
    ("penerima baru saja", tf.TransferTelemetry(first_time_beneficiary=True)),
    ("4 transfer sejam saja", tf.TransferTelemetry(transfers_last_hour=4)),
]
for nama, t in tunggal:
    v = tf.evaluate(t)
    tanda = "ok" if v.action in ("proceed", "warn") else "TERLALU KERAS"
    print(f"  {nama:<28}{v.action:<12}skor {v.risk_score:>3}   {tanda}")

print()
print("  Menelepon orang yang dibayar sambil transfer adalah hal wajar.")
print("  Sinyal panggilan yang cukup sendirian akan menghukum mereka.")

print()
print("=" * 74)
print("2. LAJU PADA POPULASI")
print("=" * 74)
print()

def ukur(pembangkit, n=SAMPEL):
    hasil = {"proceed": 0, "warn": 0, "step_up": 0, "cooling_off": 0}
    for _ in range(n):
        hasil[tf.evaluate(pembangkit()).action] += 1
    return {k: 100 * v / n for k, v in hasil.items()}

sah = ukur(transfer_sah)
tipu = ukur(transfer_penipuan)

print(f"  {'aksi':<14}{'transfer SAH':>16}{'pola PENIPUAN':>18}")
print("  " + "-" * 50)
for a in ("proceed", "warn", "step_up", "cooling_off"):
    print(f"  {a:<14}{sah[a]:>15.1f}%{tipu[a]:>17.1f}%")

print()
friksi_sah = sah["step_up"] + sah["cooling_off"]
tangkap = tipu["step_up"] + tipu["cooling_off"]
print(f"  Transfer sah yang kena friksi berat : {friksi_sah:.1f}%")
print(f"  Pola penipuan yang tertangkap       : {tangkap:.1f}%")

print()
print("=" * 74)
print("3. PENGARUH LAPORAN LINTAS-PENYELENGGARA")
print("=" * 74)
print()
print("  Rekening yang sudah dilaporkan, pada transfer yang TIDAK punya")
print("  tanda lain sama sekali:")
print()
bersih = tf.TransferTelemetry(first_time_beneficiary=True,
                              beneficiary_account_age_days=200,
                              call_active=False, transfers_last_hour=0)
print(f"  {'pelapor':>10}{'aksi':>14}{'skor':>8}")
print("  " + "-" * 36)
for n in (0, 1, 2, 3, 5):
    h = tf.BeneficiaryHistory(reports=n, distinct_reporters=n) if n else None
    v = tf.evaluate(bersih, h)
    print(f"  {n:>10}{v.action:>14}{v.risk_score:>8}")

print()
print("  Satu penyelenggara yang melapor sudah cukup menaikkan ke")
print("  step_up. Itu disengaja: korban berikutnya tidak perlu menunggu")
print("  konsensus untuk dilindungi — berbeda dari jangkar lokasi, di")
print("  mana satu laporan bisa saja keliru. Laporan penipuan dibuat")
print("  penyelenggara setelah investigasi, bukan oleh pemindai anonim.")

print()
print("=" * 74)
print("KESIMPULAN")
print("=" * 74)
print()
print(f"  Tidak ada sinyal tunggal yang mencapai step_up. Kombinasi")
print(f"  ditelepon + rekening baru + penerima baru baru mencapainya —")
print(f"  dan itu memang pola yang dicari.")
print()
print(f"  {friksi_sah:.1f}% transfer sah kena friksi berat. Angka ini perlu")
print("  diturunkan dengan data lapangan penyelenggara, bukan simulasi")
print("  ini — profil transfer sah di sini adalah tebakan berdasar, bukan")
print("  pengukuran.")
