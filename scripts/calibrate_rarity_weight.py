"""Kalibrasi W_RARE_PROFILE — berapa bobot yang benar untuk sinyal kelangkaan.

profile.py menyatakan niatnya sendiri: "sinyal ini tidak boleh cukup
sendirian". Ambang `proceed` adalah `score <= 25`, jadi bobot 30
melanggar niat itu — sinyal kelangkaan SENDIRIAN menurunkan merchant
yang sudah mapan dari `proceed` ke `warn`.

Yang ditimbang di sini: menurunkan bobot memperbaiki gesekan palsu,
tapi tidak boleh diam-diam menurunkan tier pada kombinasi yang memang
mencurigakan. Skrip ini menyapu SELURUH kombinasi bobot sampai tiga
sinyal dan melaporkan setiap kombinasi yang tiernya berubah.

  python scripts/calibrate_rarity_weight.py
"""

import itertools
import os
import sys

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(AKAR, "src"))

from qshield import behavior as bh  # noqa: E402
from qshield import binding as bd  # noqa: E402

# Sinyal lain yang bisa menemani kelangkaan, beserta bobotnya. Nama
# dipendekkan supaya tabelnya terbaca.
#
# Sinyal WiFi hanya berjalan di jalur akurasi rendah, yang selalu
# membawa 40 dasar — lihat komentar W_AP_FOREIGN_NMID. Kombinasi yang
# memuatnya tanpa 40 itu tidak pernah terjadi, dan menghitungnya akan
# melebih-lebihkan pelemahan.
DASAR_AKURASI = ("akurasi lokasi rendah (dasar)", 40)
BUTUH_DASAR = {"WiFi kenal tempat, NMID asing", "WiFi tidak cocok"}

LAIN = [
    DASAR_AKURASI,
    ("kontradiksi struktural", bh.W_STRUCTURAL),
    ("akurasi mustahil", bh.W_IMPLAUSIBLE_ACCURACY),
    ("nominal tagihan berubah", bh.W_BILL_AMOUNT_CHANGED),
    ("QR dinamis dipakai ulang", bh.W_DYNAMIC_REUSED),
    ("QR dinamis tersebar", bh.W_DYNAMIC_SPREAD),
    ("NMID cetak tidak cocok", bh.W_PRINTED_NMID_MISMATCH),
    ("nama cetak tidak cocok", bh.W_PRINTED_NAME_MISMATCH),
    ("WiFi kenal tempat, NMID asing", bh.W_AP_FOREIGN_NMID),
    ("WiFi tidak cocok", bh.W_AP_MISMATCH),
    ("perangkat di-root", bh.W_DEVICE_ROOTED),
    ("atestasi gagal", bh.W_ATTESTATION_FAILED),
    ("kota tidak cocok", bd.W_CITY_MISMATCH),
    ("nama tidak konsisten", bd.W_NAME_INCONSISTENT),
    ("dialek menyimpang 1 atribut", bd.W_ISSUER_DEVIATION),
    ("dialek menyimpang maksimum", bd.ISSUER_DEVIATION_CAP),
    ("konflik merchant terdaftar", bd.W_REGISTERED_CONFLICT),
    ("peniruan nama", bd.W_NAME_IMPERSONATION),
    ("tetangga belum terbukti", bd.W_ADJACENT_UNPROVEN),
    ("terbukti pindah", bd.W_RELOCATED),
    ("sidik jari encoding (batas)", bh.SOFT_FINGERPRINT_CAP),
    ("jejak percobaan (batas)", bh.W_ANOMALY_CAP),
]


def tier(score: int) -> str:
    return bd._action_for(min(100, score))


def main() -> int:
    lama = 30
    print("=" * 74)
    print("KENAPA 30 MELANGGAR NIAT MODULNYA SENDIRI")
    print("=" * 74)
    print(f"\n  Ambang tier: {bd.THRESHOLDS} lalu {bd.COOLING_OFF}\n")
    for w in (20, 25, 26, 30):
        print(f"  kelangkaan sendirian, bobot {w:>3}  ->  {tier(w)}")
    print("\n  Bobot berapa pun di atas 25 membuat sinyal ini cukup")
    print("  sendirian menggeser merchant mapan keluar dari proceed.")

    print("\n" + "=" * 74)
    print("YANG SEBENARNYA DIPERTARUHKAN: STATUS VERIFIED")
    print("=" * 74)
    print("""
  binding.py memberi status VERIFIED hanya bila:

      current.is_established and score <= 25

  Jadi bobot di atas 25 tidak sekadar menambah gesekan — ia membuat
  merchant sah KEHILANGAN status hijau dan jatuh ke unknown, berapa pun
  jumlah pengamatnya. Kelangkaan adalah sifat payload, bukan sifat
  lokasi: merchant sah dengan profil tidak biasa tidak akan pernah bisa
  menghapusnya dengan dipindai lebih sering.
""")
    for w in (25, 30):
        st = "VERIFIED" if w <= 25 else "UNKNOWN"
        print(f"  merchant mapan + kelangkaan bobot {w:>3}  ->  status {st:<9}"
              f" aksi {tier(w)}")

    for baru in (25, 20):
        print("\n" + "=" * 74)
        print(f"DAMPAK {lama} -> {baru} PADA SELURUH KOMBINASI")
        print("=" * 74)
        berubah = []
        # sendirian
        if tier(lama) != tier(baru):
            berubah.append(("(sendirian)", lama, tier(lama), tier(baru)))
        # ditemani satu sampai tiga sinyal lain
        for n in (1, 2, 3):
            for combo in itertools.combinations(LAIN, n):
                nama_combo = {k for k, _ in combo}
                if nama_combo & BUTUH_DASAR and DASAR_AKURASI[0] not in nama_combo:
                    continue
                dasar = sum(w for _, w in combo)
                t_lama, t_baru = tier(dasar + lama), tier(dasar + baru)
                if t_lama != t_baru:
                    berubah.append((" + ".join(k for k, _ in combo),
                                    dasar, t_lama, t_baru))
        total = 1
        for n in (1, 2, 3):
            for combo in itertools.combinations(LAIN, n):
                nama_combo = {k for k, _ in combo}
                if nama_combo & BUTUH_DASAR and DASAR_AKURASI[0] not in nama_combo:
                    continue
                total += 1
        print(f"\n  {len(berubah)} dari {total} kombinasi berubah tier.\n")
        if berubah:
            print(f"  {'ditemani':<48}{'dasar':>6}  {'jadi':>10}")
            print("  " + "-" * 70)
            for nama, dasar, t_lama, t_baru in berubah:
                print(f"  {nama[:46]:<48}{dasar:>6}  {t_lama} -> {t_baru}")

        turun = [b for b in berubah
                 if b[0] != "(sendirian)"
                 and TINGKAT[b[3]] < TINGKAT[b[2]]]
        print(f"\n  Yang MELEMAH (tier turun saat ditemani sinyal lain): "
              f"{len(turun)}")
        for nama, dasar, t_lama, t_baru in turun:
            print(f"    {nama[:50]:<52}{dasar:>5}  {t_lama} -> {t_baru}")
    return 0


TINGKAT = {bd.PROCEED: 0, bd.WARN: 1, bd.STEP_UP: 2, bd.COOLING_OFF: 3}

if __name__ == "__main__":
    sys.exit(main())
