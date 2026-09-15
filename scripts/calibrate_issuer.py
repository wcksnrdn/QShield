"""Kalibrasi profil penerbit — versi yang bekerja dari gagasan
"hafalkan pola QRIS asli".

Yang TIDAK bisa dihafal: pola yang membedakan stiker-swap dari stiker
asli. Penipu sticker-swap memakai akun merchant sungguhan, jadi
payload-nya memang diterbitkan acquirer betulan. Nol fitur berbeda.

Yang BISA dihafal: DIALEK tiap penerbit. Generator QR tiap PJP
deterministik — urutan tag, gaya penulisan CRC, panjang PAN, sub-tag di
dalam template merchant. Payload yang MENGAKU dari PJP tertentu tapi
tidak mengikuti dialeknya berarti dibangkitkan ulang oleh orang lain.

Itu serangan yang BERBEDA dari sticker-swap, dan nyata: memodifikasi
nominal, atau menyusun QR yang menunjuk rekening penipu sambil meniru
nama merchant korban.

Yang dikalibrasi di sini: berapa banyak bukti sebelum sebuah dialek
boleh dipercaya, dan seberapa keras penyimpangan dihukum.
"""

import random

random.seed(41)

# Model: tiap acquirer punya dialek dominan, tapi sebagian kecil
# payload menyimpang karena alasan sah — generator diperbarui,
# merchant lama diterbitkan versi sebelumnya, integrator pihak ketiga.
VARIASI_SAH = [0.0, 0.02, 0.05, 0.10, 0.20]

MIN_NMIDS_DIUJI = [3, 5, 8, 12]
MIN_SHARE_DIUJI = [0.80, 0.90, 0.95, 1.00]

SAMPEL = 4000


def simulasi(n_nmid, laju_variasi, min_nmids, min_share):
    """Kembalikan (profil_terbentuk, positif_palsu).

    positif_palsu = payload SAH yang ditandai menyimpang.
    """
    # Bangun korpus: n_nmid merchant dari satu acquirer.
    nilai = ["dominan" if random.random() > laju_variasi else "varian"
             for _ in range(n_nmid)]
    hitung = {}
    for v in nilai:
        hitung[v] = hitung.get(v, 0) + 1

    total = len(nilai)
    dominan = max(hitung, key=hitung.get)
    setuju = hitung[dominan]

    terbentuk = (setuju >= min_nmids and setuju / total >= min_share)
    if not terbentuk:
        return False, 0

    # Payload sah berikutnya yang menyimpang akan ditandai.
    palsu = laju_variasi
    return True, palsu


print("=" * 74)
print("1. KAPAN SEBUAH DIALEK BOLEH DIPERCAYA")
print("=" * 74)
print()
print("  Acquirer dengan 20 merchant terpindai. Berapa sering profilnya")
print("  terbentuk, dan berapa payload SAH yang lalu ditandai menyimpang?")
print()
print(f"  {'variasi sah':>12}", "".join(f"{f'n>={n}':>22}" for n in MIN_NMIDS_DIUJI))
print(f"  {'':>12}", "".join(f"{'terbentuk/salah':>22}" for _ in MIN_NMIDS_DIUJI))
print("  " + "-" * 72)

for laju in VARIASI_SAH:
    baris = []
    for mn in MIN_NMIDS_DIUJI:
        jadi = salah = 0
        for _ in range(SAMPEL):
            t, p = simulasi(20, laju, mn, 0.90)
            if t:
                jadi += 1
                salah += p
        pj = 100 * jadi / SAMPEL
        ps = 100 * (salah / jadi) if jadi else 0
        baris.append(f"{pj:>12.0f}% /{ps:>6.1f}%")
    print(f"  {laju * 100:>10.0f}% ", "".join(baris))

print()
print("=" * 74)
print("2. PENGARUH AMBANG KESEPAKATAN")
print("=" * 74)
print()
print("  Acquirer dengan variasi sah 5%, 20 merchant terpindai:")
print()
print(f"  {'min_share':>12}{'profil terbentuk':>22}{'positif palsu':>18}")
print("  " + "-" * 60)
for ms in MIN_SHARE_DIUJI:
    jadi = salah = 0
    for _ in range(SAMPEL):
        t, p = simulasi(20, 0.05, 5, ms)
        if t:
            jadi += 1
            salah += p
    print(f"  {ms:>12.2f}{100 * jadi / SAMPEL:>21.0f}%"
          f"{100 * (salah / jadi if jadi else 0):>17.1f}%")

print()
print("=" * 74)
print("KESIMPULAN")
print("=" * 74)
print()
print("  min_nmids = 5, min_share = 0,90")
print()
print("    - acquirer yang generatornya konsisten (variasi <= 5%)")
print("      profilnya terbentuk hampir selalu")
print("    - acquirer yang variasinya 20% profilnya TIDAK terbentuk,")
print("      dan itu benar — dialeknya memang tidak konsisten, jadi")
print("      tidak ada yang bisa dihafal")
print()
print("  Positif palsu yang tersisa setara laju variasi sah acquirer itu")
print("  sendiri. Itu sebabnya bobotnya harus SEDANG, bukan keras:")
print("  penyimpangan dialek adalah petunjuk, bukan bukti.")
print()
print("  Dan itu sebabnya sinyal ini TIDAK menangkap sticker-swap.")
print("  Stiker penipu diterbitkan acquirer sungguhan, jadi dialeknya")
print("  cocok sempurna. Yang ditangkap adalah QR yang DIBANGKITKAN ULANG.")
