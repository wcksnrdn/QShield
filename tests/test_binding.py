"""Test logika binding, termasuk kasus batas geohash yang sebelumnya gagal."""

import math
import random
from datetime import datetime, timedelta, timezone

from qshield import binding as b
from qshield import geo

random.seed(11)
NOW = datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc)

REAL = "ID1024365478912"
FAKE = "ID1099887766554"

WARUNG_LAT, WARUNG_LNG = -6.914744, 107.609810


def mk(nmid, lat, lng, observers, age_hours, name=None, last_seen=None):
    return b.Binding(
        nmid=nmid, lat=lat, lng=lng, merchant_name=name,
        observer_count=observers,
        first_seen=NOW - timedelta(hours=age_hours),
        last_seen=last_seen or NOW,
    )


def offset(lat, lng, dist_m, angle):
    dlat = (dist_m * math.cos(angle)) / 111320
    dlng = (dist_m * math.sin(angle)) / (111320 * math.cos(math.radians(lat)))
    return lat + dlat, lng + dlng


def show(label, v):
    print(f"\n{label}")
    print(f"  status {v.status}   action {v.action}   score {v.risk_score}")
    for r in v.reasons:
        print(f"  - {r}")


established = mk(REAL, WARUNG_LAT, WARUNG_LNG, 47, 2000, "WARUNG BU SRI")

print("=" * 66)
print("1. QR sah di jangkar mapan")
print("=" * 66)
v = b.evaluate(REAL, WARUNG_LAT, WARUNG_LNG, [established], [], now=NOW)
show("hasil", v)
assert v.status == b.VERIFIED and v.action == b.PROCEED

print()
print("=" * 66)
print("2. KASUS BATAS — scan 20 m dari titik binding")
print("=" * 66)
print("   (versi lama gagal di sini karena geohash berbeda)")

fails = 0
for i in range(2000):
    ang = random.uniform(0, 2 * math.pi)
    slat, slng = offset(WARUNG_LAT, WARUNG_LNG, random.uniform(0, 45), ang)
    cells = b.index_cells(slat, slng)
    visible = [established] if established.geohash_7 in cells else []
    r = b.evaluate(REAL, slat, slng, visible, [], now=NOW)
    if r.status != b.VERIFIED:
        fails += 1

print(f"  2000 scan dalam radius 45 m -> gagal verified: {fails}")
assert fails == 0, "masih ada scan yang lolos dari indeks"
print("  OK — indeks presisi 7 menutup seluruh kasus")

print()
print("=" * 66)
print("3. Scan jauh (300 m) tidak boleh dianggap jangkar sama")
print("=" * 66)
flat, flng = offset(WARUNG_LAT, WARUNG_LNG, 300, 1.0)
v = b.evaluate(REAL, flat, flng, [established], [], now=NOW)
show("hasil", v)
assert v.status == b.UNKNOWN
assert "first_observation" in v.signals

print()
print("=" * 66)
print("4. Stiker palsu di jangkar yang sama")
print("=" * 66)
v = b.evaluate(FAKE, WARUNG_LAT, WARUNG_LNG, [established], [], now=NOW)
show("hasil", v)
assert v.status == b.ANOMALY
assert "nmid_changed_at_anchor" in v.signals
assert v.action == b.COOLING_OFF

print()
print("=" * 66)
print("5. Stiker palsu, scan 30 m dari titik asli")
print("=" * 66)
slat, slng = offset(WARUNG_LAT, WARUNG_LNG, 30, 2.2)
v = b.evaluate(FAKE, slat, slng, [established], [], now=NOW)
show("hasil", v)
assert v.status == b.ANOMALY, "geser 30 m tidak boleh melewatkan deteksi"

print()
print("=" * 66)
print("6. NMID tersebar di banyak kota")
print("=" * 66)
scattered = [
    mk(FAKE, -6.2088, 106.8456, 2, 3),     # Jakarta
    mk(FAKE, -7.2575, 112.7521, 2, 5),     # Surabaya
    mk(FAKE, -6.5971, 106.8060, 1, 2),     # Bogor
]
v = b.evaluate(FAKE, WARUNG_LAT, WARUNG_LNG, [], scattered, now=NOW)
show("hasil", v)
assert v.status == b.ANOMALY and "nmid_scatter" in v.signals

print()
print("=" * 66)
print("7. Pengamatan sama, koordinat bergeser — tidak dihitung ganda")
print("=" * 66)
jitter = [
    mk(REAL, *offset(-6.2088, 106.8456, d, a), observers=3, age_hours=100)
    for d, a in [(0, 0), (25, 1.0), (40, 3.0), (15, 5.0)]
]
v = b.evaluate(REAL, WARUNG_LAT, WARUNG_LNG, [], jitter, now=NOW)
show("hasil", v)
assert "nmid_scatter" not in v.signals, "jitter GPS tidak boleh jadi alarm sebaran"
assert "nmid_second_location" in v.signals
print("\n  4 binding berdekatan dihitung sebagai 1 area")

print()
print("=" * 66)
print("8. Cold start")
print("=" * 66)
v = b.evaluate(REAL, -8.6500, 115.2167, [], [], now=NOW)
show("hasil", v)
assert v.status == b.UNKNOWN, "cold start tidak boleh diklaim aman"
assert v.action == b.WARN, "lokasi tak dikenal minimal diberi peringatan"
print("\n  UNKNOWN + WARN, bukan VERIFIED + PROCEED")

print()
print("=" * 66)
print("9. Binding muda")
print("=" * 66)
young = mk(REAL, WARUNG_LAT, WARUNG_LNG, 2, 3)
v = b.evaluate(REAL, WARUNG_LAT, WARUNG_LNG, [young], [], now=NOW)
show("hasil", v)
assert v.status == b.UNKNOWN

print()
print("=" * 66)
print("10. CRC tidak valid")
print("=" * 66)
v = b.evaluate(REAL, WARUNG_LAT, WARUNG_LNG, [established], [],
               crc_valid=False, now=NOW)
show("hasil", v)
assert v.status == b.ANOMALY

print()
print("=" * 66)
print("11. Merchant pindah — binding lama usang")
print("=" * 66)
stale = mk(REAL, WARUNG_LAT, WARUNG_LNG, 40, 5000, "WARUNG LAMA",
           last_seen=NOW - timedelta(days=200))
v = b.evaluate("ID1055556666777", WARUNG_LAT, WARUNG_LNG, [stale], [], now=NOW)
show("hasil", v)
assert v.status != b.ANOMALY

print()
print("=" * 66)
print("12. Merchant sah ganti QR — binding lama masih aktif")
print("=" * 66)
v = b.evaluate("ID1055556666777", WARUNG_LAT, WARUNG_LNG, [established], [], now=NOW)
show("hasil", v)
assert v.status == b.ANOMALY
print("\n  benar terdeteksi anomali; dipulihkan lewat konfirmasi merchant")

print()
print("=" * 66)
print("13. Dua merchant bersebelahan (ruko)")
print("=" * 66)
neighbor_lat, neighbor_lng = offset(WARUNG_LAT, WARUNG_LNG, 8, 0.5)
neighbor = mk("ID1077778888999", neighbor_lat, neighbor_lng, 30, 1500, "TOKO SEBELAH")
v = b.evaluate(REAL, WARUNG_LAT, WARUNG_LNG, [established, neighbor], [], now=NOW)
show("hasil", v)
assert "adjacent_merchant" in v.signals, "koeksistensi harus dibedakan dari swap"
assert v.status != b.ANOMALY, "merchant bersebelahan tidak boleh jadi anomali keras"
print("\n  dikenali sebagai merchant bersebelahan, bukan pertukaran stiker")

print()
print("=" * 66)
print("14. Lapak sepi di sebelah warung ramai bisa keluar dari tuduhan")
print("=" * 66)

# Kebuntuan yang diukur di calibrate_tetangga.py: uji rasio membuat lapak
# sah yang sepi ditolak, penolakan membuat pengamatnya tidak bertambah,
# dan ia ditolak justru karena pengamatnya sedikit. Diuji di sini supaya
# tidak bisa kembali tanpa ketahuan.
ramai = mk(REAL, WARUNG_LAT, WARUNG_LNG, 300, 4000, "WARUNG RAMAI",
           last_seen=NOW)
SEPI = "ID2023254132939"

# Hari pertama: belum ada bukti apa pun. Tuduhan memang benar di sini —
# pada titik ini sistem tidak punya cara membedakannya dari penukaran.
v = b.evaluate(SEPI, WARUNG_LAT, WARUNG_LNG, [ramai], [], now=NOW)
show("hari pertama, tanpa bukti", v)
assert v.status == b.ANOMALY, "tanpa bukti, kehati-hatian harus menang"

# Setelah cukup orang berbeda menemuinya, sementara warung ramai TERUS
# terpindai — bukti bahwa tidak ada QR yang tertutup.
bukti = b.Challenge(
    devices=b.ADJACENT_MIN_DEVICES,
    first_at=NOW - timedelta(hours=b.MIN_AGE_HOURS + 2),
    last_at=NOW,
)
v = b.evaluate(SEPI, WARUNG_LAT, WARUNG_LNG, [ramai], [], now=NOW,
               challenge=bukti)
show("setelah kehadiran terbukti", v)
assert "adjacent_merchant" in v.signals, "kehadiran terbukti harus diakui"
assert v.status != b.ANOMALY, "lapak sah tidak boleh tetap dituduh"
print("\n  lapak sah keluar dari kebuntuan tanpa mengubah rumus konsensus")

print()
print("=" * 66)
print("15. Bukti kehadiran ditolak kalau merchant lama berhenti terpindai")
print("=" * 66)

# Inilah pembedanya. Stiker yang ditempel MENUTUPI membuat QR lama tidak
# bisa dipindai lagi, jadi last_seen-nya berhenti sebelum penantang
# muncul. Korban yang berdatangan semuanya perangkat berbeda, sehingga
# jumlahnya tumbuh persis seperti lapak sah — yang membedakan hanya
# diamnya merchant lama.
tertutup = mk(REAL, WARUNG_LAT, WARUNG_LNG, 300, 4000, "WARUNG RAMAI",
              last_seen=NOW - timedelta(hours=b.MIN_AGE_HOURS + 10))
banyak_korban = b.Challenge(
    devices=b.ADJACENT_MIN_DEVICES * 10,
    first_at=NOW - timedelta(hours=b.MIN_AGE_HOURS + 5),
    last_at=NOW,
)
v = b.evaluate(SEPI, WARUNG_LAT, WARUNG_LNG, [tertutup], [], now=NOW,
               challenge=banyak_korban)
show("80 korban, merchant lama diam", v)
assert v.status == b.ANOMALY, "penukaran sungguhan lolos lewat jalur kehadiran"
assert "adjacent_merchant" not in v.signals
print("\n  penukaran tetap ditahan walau korbannya jauh lebih banyak")

print("\n\nSemua assertion lolos.")
