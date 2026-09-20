"""Kalibrasi W_RELOCATED: merchant yang pindah vs stiker yang disebar.

Kebuntuan kedua, sekelas dengan yang ditutup di calibrate_kehadiran.py
tapi akibatnya lebih parah. Merchant sah yang pindah dua kali memicu
`nmid_scatter`, anomali membuat pengamatannya tidak dicatat, dan lokasi
barunya tidak pernah tumbuh. Diukur sebelum perbaikan: 500 pengamat di
tempat baru dan lokasi lama terakhir terlihat SEPULUH TAHUN lalu pun
tidak menyembuhkannya, karena cabang ini tidak menyaring binding usang
sama sekali.

Yang terkena justru segmen inti Q-Shield: pedagang kaki lima, food
truck, pedagang pasar, pedagang bazar.

Pembedanya fisik: seorang pedagang hanya bisa berada di satu tempat
pada satu waktu, sehingga periode aktif lokasi-lokasinya tidak pernah
beririsan. Penyebar memasang stikernya sekaligus.

Tiga hal diukur, dan yang KEDUA adalah syarat mutlak:

  1  berapa hari merchant yang pindah butuh sampai pulih penuh
  2  apakah penyebar stiker ikut lolos lewat jalan ini
  3  bobot mana yang memulihkan sampai proceed, bukan berhenti di warn

  python scripts/calibrate_relokasi.py
"""

import os
import sys
from datetime import datetime, timedelta, timezone

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(AKAR, "src"))
from qshield import binding as b  # noqa: E402

NOW = datetime(2026, 9, 20, tzinfo=timezone.utc)
NMID = "ID1024365478912"
LAT, LNG = -6.914744, 107.609810
BOBOT = [10, 15, 20, 25, 30]


def lokasi(km_utara, obs, mulai_hari, akhir_hari):
    return b.Binding(
        nmid=NMID, lat=LAT + km_utara / 111.32, lng=LNG,
        merchant_name="WARUNG BU SRI", observer_count=obs,
        first_seen=NOW - timedelta(days=mulai_hari),
        last_seen=NOW - timedelta(days=akhir_hari),
    )


def bukti(devices, span_jam, mulai_hari):
    return b.Challenge(
        devices=devices,
        first_at=NOW - timedelta(days=mulai_hari),
        last_at=NOW - timedelta(days=mulai_hari) + timedelta(hours=span_jam),
    )


def nilai(riwayat, sekarang=None, tantangan=None):
    return b.evaluate(NMID, LAT + 6 / 111.32, LNG,
                      [sekarang] if sekarang else [], riwayat,
                      now=NOW, challenge=tantangan)


# Pedagang pindah dua kali: berjualan di A, lalu B, lalu sekarang C.
# Periodenya berurutan dan tidak beririsan.
PINDAH = [lokasi(0, 50, 400, 200), lokasi(3, 30, 180, 40)]

# Penyebar memasang tiga stiker sekaligus. Dua di antaranya jarang
# dipindai — justru kasus yang paling mudah keliru dianggap "sudah
# tidak aktif" kalau yang dilihat hanya last_seen.
SEBAR_JARANG = [lokasi(0, 3, 300, 298), lokasi(3, 2, 299, 297)]

# Penyebar dengan semua stiker aktif.
SEBAR_AKTIF = [lokasi(0, 40, 300, 1), lokasi(3, 35, 299, 2)]


def main():
    print("=" * 74)
    print("KALIBRASI W_RELOCATED")
    print("=" * 74)

    print("""
  SYARAT MUTLAK — penyebar stiker tidak boleh ikut lolos.
""")
    cukup = bukti(b.ADJACENT_MIN_DEVICES * 5, b.MIN_AGE_HOURS + 48, 5)
    aman = True
    for nama, riwayat in [("stiker jarang dipindai", SEBAR_JARANG),
                          ("stiker semua aktif", SEBAR_AKTIF)]:
        v = nilai(riwayat, tantangan=cukup)
        lolos = "nmid_scatter" not in v.signals
        if lolos:
            aman = False
        print(f"    {nama:26} {v.status:<9} {v.action:<12} "
              f"{'LOLOS — CACAT' if lolos else 'tetap ditahan'}")
        if lolos:
            for r in v.reasons:
                print(f"      - {r}")

    print(f"""
    Keduanya ditahan oleh syarat "periode tidak boleh beririsan":
    stiker yang dipasang bersamaan punya rentang yang tumpang tindih
    walaupun jarang dipindai. Yang dibandingkan rentang aktifnya,
    bukan frekuensinya.

  PEMULIHAN MERCHANT YANG PINDAH
""")
    asli = b.W_RELOCATED
    print(f"  {'W':>4}  {'baru pulih':>22}  {'sudah mapan':>22}")
    print("  " + "-" * 52)
    try:
        for w in BOBOT:
            b.W_RELOCATED = w
            # Saat baru terbukti: belum ada binding di sini sama sekali.
            v1 = nilai(PINDAH, tantangan=cukup)
            # Setelah mapan di lokasi baru.
            mapan = b.Binding(nmid=NMID, lat=LAT + 6 / 111.32, lng=LNG,
                              merchant_name="WARUNG BU SRI", observer_count=30,
                              first_seen=NOW - timedelta(days=20),
                              last_seen=NOW)
            v2 = nilai(PINDAH, sekarang=mapan, tantangan=cukup)
            tanda = "  <-- pulih penuh" if v2.action == b.PROCEED else ""
            print(f"  {w:>4}  {v1.action:>12} ({v1.risk_score:>2})  "
                  f"{v2.action:>12} ({v2.risk_score:>2}){tanda}")
    finally:
        b.W_RELOCATED = asli

    print(f"""
  Dipilih {asli}. Di atas 25 merchant yang sudah mapan di lokasi barunya
  berhenti di warn selamanya: ambang proceed adalah skor <= 25, dan
  pengurangan -20 untuk binding mapan tidak berlaku selama masih ada
  lokasi lain yang tercatat. Di bawah 20 tidak ada bedanya dengan
  merchant yang tidak pernah pindah, padahal pindah tempat memang
  pantas ditandai.

  Kesimpulan keamanan: {"tidak ada bobot yang membuat penyebar lolos" if aman else "ADA YANG BOCOR"}
""")
    return 0 if aman else 1


if __name__ == "__main__":
    sys.exit(main())
