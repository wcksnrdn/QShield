"""Kalibrasi konstanta Layer 2, diuji secara empiris.

Mengikuti pola calibrate_geo.py: setiap angka di behavior.py harus bisa
ditunjuk dasarnya. Yang tidak lolos pemeriksaan di sini tidak boleh
tinggal di kode hanya karena kedengarannya masuk akal.

Dua hal yang diperiksa:
  1. eskalasi percobaan anomali berulang
  2. laju positif palsu sinyal struktural terhadap payload yang sah

Dulu ada bagian ketiga di paling depan: kalibrasi ambang LONJAKAN
PEMINDAIAN. Bagian itu sudah DIBUANG bersama sinyalnya di Keputusan 13 —
tidak ada satu pun ambang yang menangkap serangan tanpa menghukum warung
laris, karena membangun reputasi palsu hanya butuh MIN_OBSERVERS device
dalam rentang MIN_AGE_HOURS jam, jadi serangannya pelan, bukan meledak.
Tabel yang membatalkannya tersimpan di PROCESS-LOG.md Keputusan 13.

Kodenya ikut dibuang, bukan dikomentari, karena ia memanggil
`bh.SCAN_BURST_WINDOW_MIN` yang sudah tidak ada — dan skrip yang crash
lebih buruk daripada skrip yang tidak ada: ia membuat bagian yang MASIH
SAHIH di bawahnya (bobot struktural, batas eskalasi) ikut tidak pernah
dijalankan, padahal justru itu yang dikutip THREAT-MODEL sebagai bukti.
"""

import random

from qshield import behavior as bh
from qshield import binding as bd
from qshield import emvco

random.seed(7)

print()
print("=" * 72)
print("1. ESKALASI PERCOBAAN ANOMALI BERULANG")
print("=" * 72)
print()
print("  Naik hanya bila yang memindai BUKAN merchant mapan di jangkar ini,")
print("  supaya penyerang tidak bisa memakainya menyerang merchant jujur.")
print()
print(f"  {'percobaan':>10}{'bobot L2':>10}{'L1 cold start':>16}{'gabungan':>10}  aksi")
for n in (1, 2, 3, 5, 10):
    bobot = min(bh.W_ANOMALY_CAP, bh.W_ANOMALY_BASE * n)
    # Skenario terburuk yang wajar: jangkar tak dikenal (L1 = 35).
    gabungan = min(100, 35 + bobot)
    print(f"  {n:>10}{bobot:>10}{35:>16}{gabungan:>10}  {bd._action_for(gabungan)}")
print()
print(f"  Batas {bh.W_ANOMALY_CAP} dipilih supaya sinyal ini sendirian tidak pernah")
print("  cukup menyeret pemindaian bersih sampai cooling_off — ia mempertajam")
print("  bukti lain, bukan menggantikannya.")

print()
print("=" * 72)
print("2. POSITIF PALSU SINYAL STRUKTURAL")
print("=" * 72)
print()

KOTA = ["BANDUNG", "JAKARTA PUSAT", "SURABAYA", "KOTA BOGOR", "DENPASAR"]
MCC = ["5812", "5411", "5814", "5999", "7230"]
KRITERIA = ["UMI", "UKE", "UME", "UBE"]
PJP = ["93600014", "93600911", "93600520", "93600768"]

palsu = 0
CONTOH = 20000
for _ in range(CONTOH):
    nmid = "ID" + "".join(random.choice("0123456789") for _ in range(13))
    pan = random.choice(PJP) + "".join(random.choice("0123456789") for _ in range(10))
    fields = {
        "00": "01",
        "01": "11",
        "26": emvco.build_tlv({
            "00": "ID.CO.QRIS.WWW", "01": pan, "02": nmid,
            "03": random.choice(KRITERIA),
        }),
        "52": random.choice(MCC),
        "53": "360",
        "58": "ID",
        "59": random.choice(["WARUNG BU SRI", "TOKO SEJAHTERA", "KOPI KENANGAN"]),
        "60": random.choice(KOTA),
    }
    # Field opsional memang boleh ada atau tidak.
    if random.random() < 0.7:
        fields["61"] = str(random.randint(10000, 99999))
    if random.random() < 0.3:
        fields["62"] = emvco.build_tlv({"01": str(random.randint(1, 999999))})

    hasil = bh.evaluate(emvco.parse(emvco.build(fields)))
    if hasil.score or hasil.hard_violation:
        palsu += 1

print(f"  {CONTOH} payload sah dan bervariasi -> {palsu} positif palsu "
      f"({100 * palsu / CONTOH:.3f}%)")
print()
print("  Nol positif palsu memang diharapkan: sinyal struktural menguji")
print("  KONTRADIKSI terhadap spec, bukan kemiripan statistik. Yang tidak")
print("  bisa dijamin skrip ini adalah laju positif palsu sinyal SIDIK JARI")
print("  (urutan tag, huruf CRC) terhadap generator acquirer sungguhan —")
print("  itu butuh korpus payload QRIS asli yang belum kami punya, dan")
print("  karena itu bobotnya kecil serta dibatasi bersama.")
