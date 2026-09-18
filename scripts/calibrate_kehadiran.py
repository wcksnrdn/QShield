"""Kalibrasi ADJACENT_MIN_DEVICES: berapa orang membuktikan sebuah lapak nyata.

calibrate_tetangga.py menunjukkan kebuntuannya. Merchant sah yang sepi di
sebelah tetangga ramai diberi cooling_off pada 100% kunjungan, dan tidak
punya jalan keluar: pemindaian yang ditolak tidak menambah pengamat, dan
ia ditolak justru karena pengamatnya sedikit.

Jalan keluarnya memakai bukti fisik, bukan pelonggaran ambang. Stiker yang
ditempel MENUTUPI membuat QR di bawahnya tidak bisa dipindai lagi, sehingga
merchant lama berhenti terlihat. Kalau merchant lama TERUS terlihat setelah
penantang muncul, tidak ada yang tertutup — keduanya nyata-nyata di sana.

Tiga hal diukur, dan yang KEDUA adalah syarat mutlak:

  1  berapa hari lapak sah yang sepi butuh sampai diakui
  2  apakah penukaran SUNGGUHAN ikut lolos lewat jalan ini
  3  berapa perangkat yang harus dikeluarkan penyerang

CATATAN MODEL. Dijalankan langsung terhadap Store dan binding.evaluate(),
bukan lewat HTTP: yang diukur murni keputusan Layer 1, dan 350 kali
menyalakan server untuk pertanyaan ini tidak menambah apa-apa selain
waktu. Layer 2 tidak ikut — untuk merchant sah skornya nol, dan untuk
penukaran ia hanya MENAMBAH risiko, tidak pernah mengurangi, sehingga
angka di sini adalah batas bawah keamanan. Jalur HTTP lengkap
diverifikasi terpisah oleh calibrate_tetangga.py.

  python scripts/calibrate_kehadiran.py
"""

import math
import os
import random
import sys
import tempfile
from datetime import datetime, timedelta, timezone

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(AKAR, "src"))
from qshield import binding as bd  # noqa: E402
from qshield import emvco  # noqa: E402
from qshield.store import Store  # noqa: E402

TITIK = (-6.168600, 106.872500)
LAMA = ("ID1026542245422", "Es Kelapa Boga Rasa")
BARU = ("ID2023254132939", "RESTORASI MESJID")

N_DIUJI = [3, 5, 8, 12, 20]
LARIS_LAMA = 25
HARI_MAKS = 14
PELANGGAN = (2, 5, 10, 20)
MULAI = datetime(2026, 1, 1, tzinfo=timezone.utc)


def geser(la, ln, u, t):
    return (la + u / 111320, ln + t / (111320 * math.cos(math.radians(la))))


def derau(la, ln):
    akurasi = random.uniform(5, 15)
    sigma = max(8.0, akurasi * 0.7)
    r = abs(random.gauss(0, sigma))
    a = random.uniform(0, 2 * math.pi)
    return geser(la, ln, r * math.cos(a), r * math.sin(a))


def payload_untuk(nmid, nama):
    acct = emvco.build_tlv({"00": "ID.CO.QRIS.WWW", "01": "936000149000000001",
                            "02": nmid, "03": "UMI"})
    return emvco.build({"00": "01", "01": "11", "26": acct, "52": "5812",
                        "53": "360", "58": "ID", "59": nama,
                        "60": "JAKARTA", "61": "10110"})


def satu_pindai(store, payload, nmid, device_id, saat):
    """Cermin urutan api.verify() untuk jalur Layer 1.

    Kalau urutan di api.py berubah, yang ini harus ikut — perbedaannya
    akan terlihat sebagai selisih antara skrip ini dan calibrate_tetangga.py,
    yang menembak HTTP sungguhan.
    """
    parsed = emvco.parse(payload)
    lat, lng = derau(*TITIK)
    v = bd.evaluate(
        nmid=nmid, lat=lat, lng=lng,
        nearby=store.nearby(lat, lng),
        same_nmid_elsewhere=store.by_nmid(nmid),
        crc_valid=parsed.crc_valid,
        now=saat,
        challenge=store.challenge_state(lat, lng, nmid),
    )
    if v.status != bd.ANOMALY:
        store.record(nmid, lat, lng, device_id, parsed.merchant_name, now=saat)
    elif "nmid_changed_at_anchor" in v.signals:
        store.note_challenge(lat, lng, nmid, device_id, now=saat)
    return v


def jalankan(n_devices, pelanggan_per_hari, lama_tetap_dipindai):
    """Kembalikan hari saat penantang berhenti dituduh, atau None."""
    asli = bd.ADJACENT_MIN_DEVICES
    bd.ADJACENT_MIN_DEVICES = n_devices
    tmp = tempfile.mkdtemp(prefix="qshield-kh-")
    store = Store(os.path.join(tmp, "sim.db"))
    try:
        p_lama = payload_untuk(*LAMA)
        p_baru = payload_untuk(*BARU)

        # Merchant lama dimapankan dan dibiarkan berumur dua hari.
        for i in range(40):
            satu_pindai(store, p_lama, LAMA[0], f"sim-lama-awal-{i:05d}",
                        MULAI + timedelta(hours=i * 1.2))

        sembuh = None
        for hari in range(1, HARI_MAKS + 1):
            hari_ini = MULAI + timedelta(days=2 + hari)
            if lama_tetap_dipindai:
                for i in range(LARIS_LAMA):
                    satu_pindai(store, p_lama, LAMA[0],
                                f"sim-lama-h{hari}-{i:05d}",
                                hari_ini + timedelta(minutes=i * 20))
            berat = 0
            for i in range(pelanggan_per_hari):
                v = satu_pindai(store, p_baru, BARU[0],
                                f"sim-baru-h{hari}-{i:05d}",
                                hari_ini + timedelta(minutes=30 + i * 25))
                if v.action in (bd.STEP_UP, bd.COOLING_OFF):
                    berat += 1
            if sembuh is None and berat == 0:
                sembuh = hari
        return sembuh
    finally:
        store.close() if hasattr(store, "close") else None
        bd.ADJACENT_MIN_DEVICES = asli


def main():
    print("=" * 74)
    print("KALIBRASI ADJACENT_MIN_DEVICES")
    print("=" * 74)
    print(f"""
  Merchant lama dipindai {LARIS_LAMA}x/hari dan tetap terlihat. Penantang
  adalah lapak sah di sebelahnya. Angka = hari ke berapa penantang
  berhenti diberi step_up/cooling_off; '-' berarti tidak pernah dalam
  {HARI_MAKS} hari.
""")
    print(f"  {'N':>4}   " + "".join(f"{k:>3}/hari" for k in PELANGGAN))
    print("  " + "-" * 34)
    for n in N_DIUJI:
        baris = []
        for k in PELANGGAN:
            random.seed(23)
            h = jalankan(n, k, lama_tetap_dipindai=True)
            baris.append(f"{h}" if h else "-")
        print(f"  {n:>4}   " + "".join(f"{b:>7}" for b in baris))

    print(f"""
  SYARAT MUTLAK — penukaran sungguhan tidak boleh ikut lolos.

  Stiker ditempel MENUTUPI, jadi merchant lama berhenti dipindai sama
  sekali. Korban yang berdatangan semuanya perangkat berbeda, sehingga
  jumlah perangkat penantang tumbuh persis seperti lapak sah. Yang
  membedakan cuma satu: merchant lama diam.
""")
    aman = True
    for n in N_DIUJI:
        random.seed(23)
        h = jalankan(n, 20, lama_tetap_dipindai=False)
        if h:
            aman = False
            print(f"    N={n:<3} 20 korban/hari x {HARI_MAKS} hari  ->  "
                  f"LOLOS pada hari {h} — CACAT")
        else:
            print(f"    N={n:<3} 20 korban/hari x {HARI_MAKS} hari  ->  "
                  f"tetap ditahan")
    print(f"""
  BIAYA PENYERANG. Untuk memakai jalan ini, penyerang harus membiarkan
  QR korban TETAP bisa dipindai — artinya stikernya ditempel di
  SEBELAHNYA, bukan menutupinya. Serangan itu kelas lain: korban
  melihat dua stiker, dan pencocokan NMID tercetak menangkapnya.
  Di atas itu ia masih butuh N perangkat berbeda dan menunggu
  {bd.MIN_AGE_HOURS} jam.

  Kesimpulan keamanan: {"tidak ada N yang bocor" if aman else "ADA N YANG BOCOR — JANGAN DIPAKAI"}
""")
    return 0 if aman else 1


if __name__ == "__main__":
    sys.exit(main())
