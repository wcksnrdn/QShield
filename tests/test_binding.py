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

print()
print("=" * 66)
print("16. Pedagang yang pindah dua kali tidak dituduh menyebar stiker")
print("=" * 66)

# Kebuntuan kedua, diukur sebelum perbaikan: 500 pengamat di lokasi baru
# dan lokasi lama terakhir terlihat sepuluh tahun lalu pun tidak
# menyembuhkan, karena cabang scatter tidak menyaring binding usang.
# Yang terkena pedagang kaki lima dan food truck — segmen inti.
def lok(km, obs, mulai_hari, akhir_hari):
    return b.Binding(
        nmid=REAL, lat=WARUNG_LAT + km / 111.32, lng=WARUNG_LNG,
        merchant_name="WARUNG BU SRI", observer_count=obs,
        first_seen=NOW - timedelta(days=mulai_hari),
        last_seen=NOW - timedelta(days=akhir_hari))

# Berjualan di A, lalu B, lalu sekarang C. Periodenya berurutan.
pindah = [lok(0, 50, 400, 200), lok(3, 30, 180, 40)]
di_sini = (WARUNG_LAT + 6 / 111.32, WARUNG_LNG)

v = b.evaluate(REAL, *di_sini, [], pindah, now=NOW)
show("hari pertama, tanpa bukti", v)
# Harapan ini BERUBAH di Keputusan 80, dan perubahannya disengaja.
#
# Dulu di sini dituntut ANOMALY, dengan alasan "tanpa bukti, kehati-
# hatian harus menang". Kehati-hatiannya benar; labelnya yang salah.
# Tiga area dalam radius 6 km tanpa bukti kehadiran serentak sama
# persis bentuknya dengan gerobak kopi keliling yang sah — dan menyebut
# pedagang keliling "anomaly" adalah tuduhan, bukan kehati-hatian.
#
# Yang tetap dituntut: JANGAN pernah hijau. Gesekannya utuh — step_up
# tetap meminta verifikasi identitas — yang berubah hanya sistem
# berhenti mengaku tahu sesuatu yang tidak diketahuinya.
assert v.status != b.VERIFIED, "tanpa bukti tidak boleh hijau"
assert v.action in (b.STEP_UP, b.COOLING_OFF), f"gesekan hilang: {v.action}"
assert "nmid_multi_area" in v.signals, v.signals
assert "nmid_scatter" not in v.signals, "banyak area bukan bukti sebaran"

cukup = b.Challenge(devices=b.ADJACENT_MIN_DEVICES,
                    first_at=NOW - timedelta(days=5),
                    last_at=NOW - timedelta(days=5) + timedelta(hours=30))
v = b.evaluate(REAL, *di_sini, [], pindah, now=NOW, challenge=cukup)
show("setelah kepindahan terbukti", v)
assert "nmid_relocated" in v.signals, "kepindahan tidak diakui"
assert "nmid_scatter" not in v.signals
assert v.status != b.ANOMALY, "pedagang yang pindah tidak boleh jadi anomali"

mapan = b.Binding(nmid=REAL, lat=di_sini[0], lng=di_sini[1],
                  merchant_name="WARUNG BU SRI", observer_count=30,
                  first_seen=NOW - timedelta(days=20), last_seen=NOW)
v = b.evaluate(REAL, *di_sini, [mapan], pindah, now=NOW, challenge=cukup)
show("setelah mapan di lokasi baru", v)
assert v.action == b.PROCEED, f"pemulihan berhenti di {v.action}"
print("\n  pedagang yang pindah pulih penuh sampai proceed")

print()
print("=" * 66)
print("17. Stiker disebar bersamaan tetap tertahan walau jarang dipindai")
print("=" * 66)

# Kasus yang paling mudah keliru: dua stiker yang nyaris tidak pernah
# dipindai terlihat "sudah tidak aktif" kalau yang diperiksa hanya
# last_seen. Yang membedakan adalah rentang aktifnya beririsan —
# dipasang bersamaan, bukan ditinggali bergantian.
sebar = [lok(0, 3, 300, 298), lok(3, 2, 299, 297)]
banyak = b.Challenge(devices=b.ADJACENT_MIN_DEVICES * 5,
                     first_at=NOW - timedelta(days=5),
                     last_at=NOW - timedelta(days=2))
v = b.evaluate(REAL, *di_sini, [], sebar, now=NOW, challenge=banyak)
show("40 perangkat, stiker lama jarang dipindai", v)
# Kepindahan tetap DITOLAK — itu bagian yang harus tidak boleh berubah.
assert "nmid_relocated" not in v.signals, "penyebaran lolos jadi kepindahan"
assert v.status != b.VERIFIED and v.action in (b.STEP_UP, b.COOLING_OFF)

# Tapi ia juga tidak lagi disebut `nmid_scatter`, dan ini HARGA yang
# dibayar sadar di Keputusan 80 — bukan bug.
#
# Pada data sebinding ini, stiker yang dipasang bersamaan dan gerobak
# keliling berbentuk identik: periode aktif beririsan, tiga area dalam
# radius 6 km. Periode beririsan memang menolak cerita "pindah", tapi ia
# TIDAK memisahkan sebaran dari keliling — gerobak yang bolak-balik juga
# punya periode beririsan. Tanpa jejak waktu yang lebih halus, tidak ada
# informasi yang memisahkan keduanya, dan menuduh berarti menuduh
# pedagang keliling juga.
#
# Yang memulihkan ketegasan: `jejak_kehadiran` — diuji di
# tests/test_keliling.py, dan selalu terisi di jalur API sungguhan.
assert "nmid_multi_area" in v.signals, v.signals
print("\n  periode beririsan tetap menolak 'pindah'; pemisahan sebaran vs")
print("  keliling menunggu jejak waktu (Keputusan 80, R21)")

print()
print("=" * 66)
print("18. Peniruan nama membatalkan pengecualian koeksistensi")
print("=" * 66)

# Usulan dari luar tim: bandingkan nama merchant baru dengan nama
# pemilik jangkar. Idenya benar, tapi hanya separuh yang bisa dipakai
# mesin — lihat calibrate_nama.py untuk kenapa skor kemiripan gagal.
tuan = mk(REAL, WARUNG_LAT, WARUNG_LNG, 47, 4000, "WARUNG BU SRI")
bukti = b.Challenge(devices=b.ADJACENT_MIN_DEVICES,
                    first_at=NOW - timedelta(hours=30), last_at=NOW)
LAIN = "ID9988776655443"

# Tetangga sah dengan bukti kehadiran: lolos, dan pembeli DIBERI
# kedua nama untuk dibandingkan sendiri.
v = b.evaluate(LAIN, WARUNG_LAT, WARUNG_LNG, [tuan], [], now=NOW,
               challenge=bukti, merchant_name="TOKO SEJAHTERA")
show("tetangga sah, nama berbeda", v)
assert v.status != b.ANOMALY, "tetangga sah dituduh"
assert any("TOKO SEJAHTERA" in r and "WARUNG BU SRI" in r for r in v.reasons), (
    "pembeli tidak diberi kontras nama pada cabang yang MELOLOSKAN — "
    "padahal di situ pertahanannya berpindah ke matanya")

# Nama yang sama persis: bukti kehadiran sebanyak apa pun tidak menolong.
v = b.evaluate(LAIN, WARUNG_LAT, WARUNG_LNG, [tuan], [], now=NOW,
               challenge=b.Challenge(devices=b.ADJACENT_MIN_DEVICES * 10,
                                     first_at=NOW - timedelta(hours=40),
                                     last_at=NOW),
               merchant_name="WARUNG BU SRI")
show("nama sama, bukti kehadiran berlimpah", v)
assert "anchor_name_impersonation" in v.signals
assert v.status == b.ANOMALY, "peniru nama lolos lewat bukti kehadiran"
assert v.reasons[0].startswith("Kode ini memakai nama yang sama"), (
    "alasan yang menentukan tidak dibaca lebih dulu")
print("\n  peniru tertahan; tetangga sah lolos dengan kontras nama terbaca")

print()
print("=" * 66)
print("19. Homoglif tertangkap, tetangga yang kebetulan mirip tidak")
print("=" * 66)

for nama, harus_tiru in [("WARUNG BU SR1", True), ("W4RUNG BU 5RI", True),
                         ("warung  bu  sri", True), ("WARUNG BU SARI", False),
                         ("WARUNG BU SRI 2", False), ("TOKO SEJAHTERA", False)]:
    v = b.evaluate(LAIN, WARUNG_LAT, WARUNG_LNG, [tuan], [], now=NOW,
                   merchant_name=nama)
    tiru = "anchor_name_impersonation" in v.signals
    print(f"  {nama:18} peniruan={str(tiru):5} (harus {harus_tiru})")
    assert tiru == harus_tiru, f"{nama} salah diklasifikasi"
print("\n  'BU SARI' dan 'BU SRI' adalah dua pedagang sungguhan, dan")
print("  metrik kemiripan mana pun akan menuduh salah satunya peniru")

print()
print("=" * 66)
print("20. Tenant yang tertinggal beberapa jam tidak dituduh menukar stiker")
print("=" * 66)

# Diukur dari korpus lapangan: di kantin dengan tiga tenant berjarak
# 3-9 meter, tenant yang melewati ambang umur beberapa MENIT lebih dulu
# mengunci tetangganya selama dua hari penuh. Beberapa menit tidak boleh
# menjadi selisih antara "tetangga" dan "stiker tukar".
def tenant(nmid, nama, obs, mulai_jam, akhir_jam):
    return b.Binding(nmid=nmid, lat=WARUNG_LAT, lng=WARUNG_LNG,
                     merchant_name=nama, observer_count=obs,
                     first_seen=NOW - timedelta(hours=mulai_jam),
                     last_seen=NOW - timedelta(hours=akhir_jam))

# Eka Putri mapan (4 pengamat, rentang 25 jam) dan masih terus dipindai.
tuan = tenant("ID1111111111111", "Kantin Eka Putri", 4, 25, 0)
# Suka Suka tertinggal DUA JAM saja: 3 pengamat, rentang 23 jam.
sebelah = tenant("ID2222222222222", "Kantin Suka Suka", 3, 23, 1)

v = b.evaluate("ID2222222222222", WARUNG_LAT, WARUNG_LNG, [tuan, sebelah], [],
               now=NOW, merchant_name="Kantin Suka Suka")
show("tertinggal 2 jam dari tetangga", v)
assert "adjacent_merchant_unproven" in v.signals
assert v.status != b.ANOMALY, "tetangga sah yang tertinggal 2 jam dituduh"
assert v.action == b.WARN, f"seharusnya warn, bukan {v.action}"
assert v.reasons[0].startswith("Di titik ini tercatat"), (
    "kontras nama tidak dibaca lebih dulu — padahal cabang ini "
    "MELOLOSKAN, jadi penilaiannya diserahkan kepada pembeli")
print("\n  tidak diblokir, tidak dihijaukan, dan kedua nama terbaca")

print()
print("=" * 66)
print("21. Kelonggaran itu dicabut kalau namanya tidak bisa ditampilkan")
print("=" * 66)

# Cabang di atas menyerahkan penilaian kepada mata pembeli. Pembeli
# hanya bisa menilai kalau kedua nama benar-benar terlihat — jadi klien
# yang tidak mengirim nama merchant tidak boleh mendapat kelonggaran
# atas dasar sesuatu yang tidak bisa diperlihatkan.
v = b.evaluate("ID2222222222222", WARUNG_LAT, WARUNG_LNG, [tuan, sebelah], [],
               now=NOW, merchant_name=None)
show("klien tidak mengirim nama merchant", v)
assert "adjacent_merchant_unproven" not in v.signals
assert v.status == b.ANOMALY, "kelonggaran diberikan tanpa bisa menampilkan nama"

# Dan nama yang DITIRU tetap ditahan, berapa pun pengamatnya.
for nama in ["Kantin Eka Putri", "Kantin Eka Putr1", "kantin  eka  putri"]:
    v = b.evaluate("ID2222222222222", WARUNG_LAT, WARUNG_LNG, [tuan, sebelah],
                   [], now=NOW, merchant_name=nama)
    assert "anchor_name_impersonation" in v.signals, f"{nama} lolos"
    assert v.status == b.ANOMALY
print("\n  tanpa nama: ditahan; nama ditiru: ditahan, termasuk homoglif")

print("\n\nSemua assertion lolos.")
