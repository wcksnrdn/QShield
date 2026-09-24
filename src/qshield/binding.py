"""
Logika binding merchant-lokasi.

Jangkar ditentukan oleh JARAK, bukan oleh kesamaan sel geohash.
Geohash presisi 7 dipakai semata sebagai indeks untuk mempersempit
query; sel presisi 7 berukuran ~152 x 153 m sehingga sel itu
ditambah 8 tetangganya dijamin mencakup seluruh titik dalam
radius 100 m (diverifikasi di calibrate_geo.py).

Memakai kesamaan geohash sebagai jangkar adalah kesalahan:
sel presisi 8 hanya setinggi 19 m, sehingga dua pemindaian di
warung yang sama kerap jatuh di sel berbeda.
"""

import re

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import geo

# --- Parameter yang bisa dikalibrasi -------------------------------

ANCHOR_RADIUS_M = 50        # dua pemindaian dianggap satu jangkar

# Jangkar dihaluskan sebagai rata-rata berjalan, bukan dibekukan pada
# pembacaan pertama. Galat satu pembacaan GPS (sigma ~8 m) melekat
# permanen kalau dibekukan; dirata-ratakan, galatnya turun sebagai
# sigma/akar(n) — terukur 6,3 m menjadi 1,0 m pada 47 pengamatan.
#
# Batas geser ada karena penghalusan membuka serangan baru: pemindaian
# dari tepi radius menarik titik tengah, dan begitu jangkarnya bergeser,
# radius barunya menjangkau lebih jauh lagi. Penyerang berjalan menuntun
# jangkar keluar dari warung.
#
# 20 m dipilih dari calibrate_anchor.py: titik benar sendiri bisa
# berjarak ~16 m (2 sigma) dari pembacaan pertama, jadi batas di bawah
# itu mengunci jangkar pada galat awalnya dan membuang seluruh
# manfaatnya. Di atas itu, seretan tumbuh tanpa imbalan akurasi.
ANCHOR_MAX_DRIFT_M = 20

# Masa hidup jejak QR dinamis. QR dinamis dibuat untuk satu transaksi
# dan kedaluwarsa dalam hitungan menit sampai jam; 48 jam memberi ruang
# untuk pemindaian yang tertunda tanpa menyimpan apa pun berlama-lama.
DYNAMIC_QR_TTL_HOURS = 48

# --- Pengetahuan wilayah -------------------------------------------
#
# Tag 60 (kota) dan 61 (kode pos) ditetapkan ACQUIRER saat menerbitkan
# QR, dari alamat merchant yang terdaftar. Penipu memakai akun merchant
# miliknya sendiri — terdaftar di alamatnya sendiri — lalu menempel
# stikernya di tempat orang lain. Stiker bertuliskan JAKARTA yang
# menempel di warung Bandung ketahuan pada pemindaian PERTAMA, tanpa
# riwayat apa pun tentang merchant itu.
#
# Wilayahnya tidak ditanam sebagai tabel geografi — dipelajari dari
# data. Presisi 5 (~4,9 km) kira-kira seukuran kecamatan besar.
AREA_CITY_PRECISION = 5

# Berapa NMID BERBEDA yang harus setuju sebelum sebuah wilayah dianggap
# punya kota yang diketahui. Menghitung NMID, bukan pemindaian, supaya
# seribu pemindaian dari satu stiker palsu tetap satu suara.
AREA_CITY_MIN_NMIDS = 5

# Bagian suara minimum agar dianggap dominan. Wilayah di perbatasan kota
# akan terbelah, dan di situ sistem memang harus diam.
AREA_CITY_MIN_SHARE = 0.75

W_CITY_MISMATCH = 40

# Satu NMID membawa dua nama merchant berbeda. Penipu yang memakai satu
# akun untuk banyak korban harus mengganti tag 59 agar cocok dengan nama
# toko tiap korban.
W_NAME_INCONSISTENT = 45

# --- Dialek penerbit -----------------------------------------------
#
# Versi yang BEKERJA dari gagasan "hafalkan pola QRIS asli". Yang tidak
# bisa dihafal: pola yang membedakan stiker-swap dari stiker asli —
# penipu memakai akun merchant sungguhan, jadi payload-nya memang
# diterbitkan acquirer betulan dan nol fitur berbeda.
#
# Yang bisa dihafal: cara tiap PJP MENYUSUN payload-nya. Generatornya
# deterministik. Payload yang mengaku dari PJP tertentu tapi tidak
# mengikuti dialeknya berarti dibangkitkan ulang oleh orang lain.
#
# Serangan yang ditangkap BERBEDA dari sticker-swap: memodifikasi
# nominal, atau menyusun QR yang menunjuk rekening penipu sambil meniru
# nama merchant korban.
#
# Dikalibrasi di calibrate_issuer.py. min_share 0,90 membuat profil
# terbentuk untuk penerbit yang konsisten, dan TIDAK terbentuk untuk
# yang variasinya tinggi — dan itu benar, dialek yang tidak konsisten
# memang tidak ada yang bisa dihafal.
ISSUER_MIN_NMIDS = 5
ISSUER_MIN_SHARE = 0.90

# Bobot SEDANG dengan sengaja: penyimpangan dialek adalah petunjuk,
# bukan bukti. Positif palsu yang tersisa setara laju variasi sah
# penerbit itu sendiri — generator diperbarui, merchant lama memakai
# versi sebelumnya, integrator pihak ketiga.
W_ISSUER_DEVIATION = 18
ISSUER_DEVIATION_CAP = 45
INDEX_PRECISION = 7         # presisi geohash untuk indeks query
AREA_PRECISION = 6          # presisi untuk deteksi sebaran antar-area
SCATTER_MIN_KM = 1.0        # jarak minimum agar dianggap area berbeda

# Konflik di jangkar TERDAFTAR. Datar, bukan berskala dengan jumlah
# pengamat — pendaftaran bukan bukti yang menumpuk seiring waktu,
# melainkan pernyataan pihak yang meng-onboard merchant. Kekuatannya
# tidak bertambah karena lebih banyak orang memindai.
#
# Nilainya dipilih supaya sendirian pun mendarat di cooling_off (>=76),
# setara konflik konsensus 50 pengamat. Alasannya: penyelenggara
# menyatakan merchant INI yang ada di sini, dan yang dipindai bukan dia.
W_REGISTERED_CONFLICT = 85

# Bobot peniruan nama di jangkar yang sudah bertuan.
#
# Sengaja DI ATAS 60+confidence milik nmid_changed_at_anchor, karena
# urutan alasan mengikuti bobot (Keputusan 47): yang menentukan harus
# terbaca lebih dulu. "Kode ini memakai nama yang sama dengan merchant
# di sini" adalah fakta yang membuat orang berhenti; "Merchant ID
# berbeda dari 47 pengamatan" tidak.
W_NAME_IMPERSONATION = 90

# Bobot tetangga yang BELUM terbukti mapan tapi jelas sedang tumbuh
# bersama. Ditambah young_binding (15) menghasilkan 35 — `warn`, dengan
# margin ke `step_up` di 50.
#
# Sengaja TIDAK mencapai proceed. Tenant ini boleh dibayar, tapi
# pembelinya harus membaca namanya dulu.
W_ADJACENT_UNPROVEN = 20

# Homoglif yang dipakai memalsukan nama: angka yang menyerupai huruf.
# Dipetakan balik sebelum dibandingkan, sehingga "WARUNG BU SR1" dan
# "W4RUNG BU 5RI" mengerucut ke bentuk yang sama.
_HOMOGLIF = str.maketrans({
    "0": "O", "1": "I", "3": "E", "4": "A", "5": "S", "7": "T", "8": "B",
    "$": "S", "@": "A",
})

MIN_OBSERVERS = 3           # device unik sebelum binding dianggap mapan
ADJACENT_MIN_RATIO = 0.10   # basis pengamat minimum relatif tetangga
# Berapa perangkat BERBEDA harus menemui sebuah NMID di jangkar yang sudah
# dikuasai merchant lain sebelum kehadirannya diakui nyata.
#
# Dikalibrasi di calibrate_kehadiran.py. Hari sampai lapak sah diakui:
#
#        N     1/hari  2/hari  3/hari  5/hari  20/hari
#        5         6       4       3       3        3
#        8         9       5       4       3        3
#       12        14       7       5       4        3
#
# Dipilih 8. Nilai 5 tidak menaikkan biaya penyerang sama sekali — itu
# sudah biaya R10 yang berlaku lewat ADJACENT_MIN_RATIO. Nilai 12
# membuat lapak yang sangat sepi tertahan dua minggu penuh, dan itu
# tidak jauh lebih baik dari kebuntuan yang sedang diperbaiki.
#
# Yang menentukan keamanan BUKAN angka ini, melainkan syarat merchant
# lama harus tetap terpindai. Penukaran sungguhan diuji pada semua N
# dengan 280 korban berbeda selama 14 hari: tidak ada satu pun yang
# lolos, karena QR yang tertutup membuat merchant lama diam.
#
# Jalan cepatnya tetap ada dan memang seharusnya begitu: merchant yang
# didaftarkan penyelenggara lolos seketika lewat is_registered.
ADJACENT_MIN_DEVICES = 8
# Selisih minimal antara pemindaian terakhir merchant lama dan percobaan
# pertama penantang. Membuktikan QR lama masih bisa dipindai, artinya ia
# tidak tertutup — jadi ini bukan penempelan di atasnya.
INCUMBENT_PROOF_HOURS = 1.0
# Bobot untuk merchant yang TERBUKTI pindah, menggantikan 60 milik
# nmid_scatter. Dikalibrasi di calibrate_relokasi.py.
W_RELOCATED = 25
MIN_AGE_HOURS = 24          # rentang minimal pengamatan pertama ke terakhir
SCATTER_MIN_AREAS = 2       # jumlah area lain yang memicu alarm sebaran
STALE_DAYS = 90             # binding tak terlihat selama ini dianggap usang

# Sinyal yang berarti "seseorang membawa stiker ke SINI yang bukan
# miliknya". Hanya ini yang boleh menaikkan anomaly_attempts jangkar.
#
# Sebelumnya anomali APA PUN menaikkannya — termasuk cacat payload yang
# tidak ada hubungannya dengan lokasi. Akibatnya memindai satu QR scam
# bercacat di meja kerja menandai MEJA ITU sebagai diserang, dan tiap
# merchant sah yang dipindai di situ mewarisi kecurigaannya.
#
# Ditemukan dari lapangan: tujuh merchant sungguhan di satu titik, tidak
# satu pun mapan, tapi jangkarnya punya empat percobaan anomali — semua
# berasal dari QR scam yang cacat payload-nya, bukan dari percobaan
# pertukaran stiker.
ANOMALI_LOKASI = frozenset({
    "nmid_changed_at_anchor",
    "nmid_changed_at_registered_anchor",
    "nmid_scatter",
    "printed_nmid_mismatch",
})

VERIFIED = "verified"
UNKNOWN = "unknown"
ANOMALY = "anomaly"

PROCEED = "proceed"
WARN = "warn"
STEP_UP = "step_up"
COOLING_OFF = "cooling_off"

THRESHOLDS = [(25, PROCEED), (50, WARN), (75, STEP_UP)]


@dataclass
class Challenge:
    """Jejak pemindaian yang DITOLAK untuk satu NMID di satu jangkar.

    Bukan reputasi: tidak pernah menaikkan kepercayaan, hanya dipakai
    memutuskan apakah dua merchant benar-benar berdampingan.
    """

    devices: int = 0
    first_at: Optional[datetime] = None
    last_at: Optional[datetime] = None

    @property
    def span_hours(self) -> float:
        if not self.first_at or not self.last_at:
            return 0.0
        return (self.last_at - self.first_at).total_seconds() / 3600


@dataclass
class Binding:
    """Satu pasangan (merchant, jangkar lokasi) yang pernah diamati."""

    nmid: str
    lat: float
    lng: float
    geohash_7: str = ""
    geohash_6: str = ""
    merchant_name: Optional[str] = None
    observer_count: int = 0
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    registered_at: Optional[datetime] = None
    is_mobile: bool = False

    def __post_init__(self):
        if not self.geohash_7:
            self.geohash_7 = geo.encode(self.lat, self.lng, INDEX_PRECISION)
        if not self.geohash_6:
            self.geohash_6 = geo.encode(self.lat, self.lng, AREA_PRECISION)

    @property
    def age_hours(self) -> float:
        if not self.first_seen or not self.last_seen:
            return 0.0
        return (self.last_seen - self.first_seen).total_seconds() / 3600

    @property
    def is_registered(self) -> bool:
        return self.registered_at is not None

    @property
    def is_established(self) -> bool:
        """Cukup bukti untuk dianggap mapan.

        Pendaftaran oleh penyelenggara memenuhinya tanpa menunggu
        konsensus: itu pernyataan pihak yang meng-onboard merchant, dan
        pernyataan adalah BUKTI — bukan ketiadaan bukti, sehingga
        invarian §2 tidak dilanggar.

        Yang tidak boleh hilang: sumbernya tetap bisa dibedakan lewat
        is_registered, dan penilaian memakai sinyal yang berbeda untuk
        keduanya. "Terverifikasi karena terdaftar" dan "terverifikasi
        karena diamati banyak orang" adalah dua klaim yang berbeda
        kekuatannya, dan auditor berhak tahu yang mana.
        """
        if self.is_registered:
            return True
        return (
            self.observer_count >= MIN_OBSERVERS
            and self.age_hours >= MIN_AGE_HOURS
        )

    def is_stale(self, now: datetime) -> bool:
        if not self.last_seen:
            return False
        return (now - self.last_seen) > timedelta(days=STALE_DAYS)

    def distance_m(self, lat: float, lng: float) -> float:
        return geo.haversine_m(self.lat, self.lng, lat, lng)

    def at_same_anchor(self, lat: float, lng: float,
                       radius_m: float = ANCHOR_RADIUS_M) -> bool:
        return self.distance_m(lat, lng) <= radius_m


@dataclass
class Verdict:
    status: str
    action: str
    risk_score: int
    reasons: list = field(default_factory=list)
    signals: list = field(default_factory=list)
    # Bobot tiap alasan, sejajar dengan reasons. Dibawa keluar supaya
    # compose() bisa mengurutkan alasan kedua layer bersama-sama —
    # memperkirakannya dari posisi tidak cukup, karena alasan Layer 2
    # bisa lebih menentukan daripada alasan Layer 1 mana pun.
    reason_weights: list = field(default_factory=list)
    matched_binding: Optional[Binding] = None

    def to_dict(self) -> dict:
        return {
            "verdict": self.status,
            "action": self.action,
            "risk_score": self.risk_score,
            "reasons": self.reasons,
            "signals": self.signals,
        }


def index_cells(lat: float, lng: float) -> list:
    """Sel geohash yang harus dicari untuk menemukan binding di sekitar."""
    return geo.neighbors(geo.encode(lat, lng, INDEX_PRECISION))


def _action_for(score: int) -> str:
    for limit, action in THRESHOLDS:
        if score <= limit:
            return action
    return COOLING_OFF


def nama_kanonik(nama: Optional[str]) -> str:
    """Bentuk baku nama merchant, untuk perbandingan SAMA-atau-TIDAK.

    Sengaja bukan skor kemiripan. Diukur pada 150 nama merchant dengan
    pola penamaan Indonesia — yang berbagi awalan berat dan nama orang
    yang berdekatan — dan hasilnya jelas:

        WARUNG MAKAN BU SARI  vs  WARUNG MAKAN BU SRI   0,97
        WARUNG BU TUTI        vs  WARUNG BU TUTIK       0,96
        KEDAI PAK UDI         vs  KEDAI PAK UDIN        0,96

    Itu pedagang yang BENAR-BENAR BERBEDA. Peniruan sungguhan memberi
    0,95-1,00. Rentangnya tumpang tindih, jadi tidak ada ambang
    kemiripan yang bisa memisahkan keduanya — dan ambang mana pun yang
    menangkap peniru juga akan menuduh Bu Sari sebagai peniru Bu Sri.

    Metrik yang lebih pintar tidak menolong. Membandingkan hanya bagian
    pembeda justru lebih buruk: "WARUNG SEMBAKO" dan "TOKO SEMBAKO"
    mengerucut ke kata yang sama.

    Yang TERPISAH bersih hanyalah kesamaan persis setelah normalisasi:
    nol positif palsu dari 11.175 pasangan, sementara homoglif, spasi,
    dan beda huruf besar-kecil tetap tertangkap.

    Selebihnya — pemotongan, imbuhan, singkatan — ditangani dengan
    MENAMPILKAN kedua nama kepada pembeli, bukan dengan menghakiminya.
    """
    if not nama:
        return ""
    return re.sub(r"[^A-Z0-9]+", "", nama.upper().translate(_HOMOGLIF))


def normalize_city(city: Optional[str]) -> str:
    """Samakan bentuk penulisan nama kota sebelum dibandingkan.

    Acquirer menulis kota dengan gaya berbeda-beda. Bentuk di bawah
    diambil dari korpus QRIS SUNGGUHAN, bukan dari tebakan:

        "JAKARTA TIMUR ("   terpotong di tengah kurung
        "LEBAK (KAB)"       jenis wilayah ditaruh di belakang
        "KOTA BANDUNG"      jenis wilayah di depan
        "Kab. Bandung"      disingkat dengan titik

    Membandingkan apa adanya membuat merchant sah saling bertentangan
    tanpa sebab, suaranya terpecah, dan ambang kesepakatan tidak pernah
    tercapai.

    Yang SENGAJA tidak ditangani: pemotongan di tengah kata, seperti
    "JAKARTA TI" untuk "JAKARTA TIMUR". Menggabungkannya lewat
    pencocokan awalan akan ikut menggabungkan "JAKARTA" dengan "JAKARTA
    BARAT" — dua kota yang benar-benar berbeda. Batasan ini diakui dan
    dicatat, bukan ditambal dengan tebakan.
    """
    if not city:
        return ""
    k = " ".join(str(city).upper().split())

    # Buang kurung yang tidak pernah ditutup — sisa pemotongan field.
    if k.count("(") > k.count(")"):
        k = k[:k.rindex("(")].strip()

    # Jenis wilayah di belakang: "LEBAK (KAB)", "BOGOR (KOTA)".
    for akhiran in ("(KAB)", "(KOTA)", "(KABUPATEN)", "(KOTA ADM)"):
        if k.endswith(akhiran):
            k = k[:-len(akhiran)].strip()
            break

    # Jenis wilayah di depan.
    for awalan in ("KOTA ADM ", "KOTA ADMINISTRASI ", "KOTA ", "KAB. ",
                   "KABUPATEN ", "KAB "):
        if k.startswith(awalan):
            k = k[len(awalan):]
            break

    return k.strip(" .,-").strip()


def _floor_action(status: str, action: str) -> str:
    """Invarian §2: "unknown" tidak pernah berarti aman.

    Binding yang belum mapan bisa berskor rendah (mis. young_binding = 15)
    dan jatuh ke proceed — itu mengubah ketiadaan bukti jadi kepercayaan,
    dan penyerang mengendalikan jalurnya: cukup pindai stikernya sendiri
    sekali agar skornya turun dari 35 ke 15.

    Dijaga struktural di sini, bukan lewat penyetelan bobot, supaya sinyal
    baru mana pun — termasuk Layer 2 — tidak bisa membuka celah yang sama.
    """
    if status == UNKNOWN and action == PROCEED:
        return WARN
    return action


# Bobot semu untuk alasan yang bukan penilaian risiko, dipakai
# mengurutkan apa yang dibaca pengguna lebih dulu.
#
# Pengguna membaca dari atas dan sering berhenti di baris pertama.
# Sebelum ini, alasan disusun menurut urutan kode dijalankan — sehingga
# "lokasi ini belum pernah tercatat" (+35, paling lemah) muncul di atas
# "format Merchant ID tidak sesuai standar" (+70, yang menentukan).
# Yang paling tidak penting dibaca duluan, yang menuduh tersembunyi.
PRIORITAS_PENGUNGKAPAN = 1000   # penanda replay dan sejenisnya
PRIORITAS_INFORMASI = -1        # konteks yang menenangkan, bukan risiko


def urutkan_alasan(berbobot: list) -> tuple:
    """Susun alasan dari yang paling menentukan ke yang paling lemah.

    Menerima daftar (bobot, alasan), mengembalikan (alasan, bobot)
    yang sudah terurut. Pengurutannya stabil: alasan berbobot sama
    tetap pada urutan aslinya.
    """
    urut = sorted(enumerate(berbobot), key=lambda x: (-x[1][0], x[0]))
    return ([a for _, (_, a) in urut], [b for _, (b, _) in urut])


def _berurutan(areas: list) -> bool:
    """Apakah lokasi-lokasi ini ditempati BERGANTIAN, bukan bersamaan.

    Seorang pedagang hanya bisa berada di satu tempat pada satu waktu.
    Kalau ia pindah A -> B -> C, periode aktif ketiganya tidak pernah
    beririsan. Penyebar stiker memasang QR-nya sekaligus, jadi periode
    lokasinya tumpang tindih — termasuk ketika sebagian stikernya jarang
    dipindai, karena yang dibandingkan adalah RENTANG aktifnya, bukan
    seberapa sering.

    Penyerang bisa menghindarinya dengan memasang stiker satu per satu
    dan menunggu di antaranya — tapi itu persis sama lambatnya dengan
    benar-benar pindah, dan itulah biaya yang memang ingin dikenakan.
    """
    rentang = sorted(
        ((a.first_seen, a.last_seen) for a in areas
         if a.first_seen and a.last_seen),
        key=lambda r: r[0],
    )
    if len(rentang) < 2:
        return True
    for (_, akhir), (mulai_berikut, _) in zip(rentang, rentang[1:]):
        if mulai_berikut <= akhir:
            return False
    return True


def _distinct_areas(bindings: list, lat: float, lng: float) -> list:
    """Kelompokkan binding jadi area yang benar-benar berjauhan.

    Mencegah satu lokasi dihitung berkali-kali hanya karena
    koordinatnya bergeser sedikit antar pengamatan.
    """
    clusters = []
    for b in sorted(bindings, key=lambda x: -x.observer_count):
        if b.distance_m(lat, lng) <= SCATTER_MIN_KM * 1000:
            continue
        if any(
            geo.haversine_m(b.lat, b.lng, c.lat, c.lng) <= SCATTER_MIN_KM * 1000
            for c in clusters
        ):
            continue
        clusters.append(b)
    return clusters


def evaluate(
    nmid: str,
    lat: float,
    lng: float,
    nearby: list,
    same_nmid_elsewhere: list,
    crc_valid: bool = True,
    now: Optional[datetime] = None,
    challenge: Optional["Challenge"] = None,
    merchant_name: Optional[str] = None,
) -> Verdict:
    """Nilai satu pemindaian.

    nearby               binding hasil query indeks di sekitar titik ini,
                         belum disaring jarak
    same_nmid_elsewhere  binding dengan NMID sama di mana pun
    challenge            jejak pemindaian NMID ini yang pernah DITOLAK di
                         jangkar ini; bukan reputasi, hanya bukti kehadiran
    merchant_name        nama merchant di payload yang dipindai, untuk
                         dibandingkan dengan nama pemilik jangkar
    """
    now = now or datetime.now(timezone.utc)
    score = 0
    reasons = []
    signals = []

    if not crc_valid:
        return Verdict(
            status=ANOMALY,
            action=COOLING_OFF,
            risk_score=95,
            reasons=["Checksum QR tidak valid — kode kemungkinan dicetak ulang"],
            signals=["crc_invalid"],
        )

    # Saring berdasarkan jarak sebenarnya, bukan kesamaan sel.
    at_anchor = [b for b in nearby if b.at_same_anchor(lat, lng)]
    current = next((b for b in at_anchor if b.nmid == nmid), None)
    others = [b for b in at_anchor if b.nmid != nmid]

    # --- Merchant keliling yang terdaftar ----------------------------
    #
    # Model jangkar mengandaikan lokasi tetap, dan itu tidak berlaku
    # untuk pedagang keliling. Hanya PJP yang bisa menandainya, jadi
    # pengecualian ini adalah tanggung jawab penyelenggara yang
    # menyatakannya — bukan sesuatu yang bisa diklaim pemindai.
    kandidat = ([current] if current else []) + list(same_nmid_elsewhere)
    keliling = next((b for b in kandidat if b.is_registered and b.is_mobile), None)
    if keliling is not None:
        reasons.append((PRIORITAS_INFORMASI,
            f"Terdaftar sebagai merchant keliling"
            + (f" — {keliling.merchant_name}" if keliling.merchant_name else "")))
        signals.append("mobile_merchant")
        alasan, bobot = urutkan_alasan(reasons)
        return Verdict(
            status=VERIFIED, action=PROCEED, risk_score=0,
            reasons=alasan, reason_weights=bobot, signals=signals,
            matched_binding=current,
        )

    # --- Sinyal 1: NMID berubah di jangkar yang sudah mapan ---------
    # Merchant keliling TIDAK mengklaim lokasi, jadi bindingnya tidak
    # boleh membuat merchant lain terlihat seperti pertukaran stiker.
    # Gerobak siomay yang pernah mangkal di suatu titik tidak menjadikan
    # titik itu miliknya. Tanpa pengecualian ini, satu pendaftaran
    # keliling bisa meracuni setiap jangkar yang pernah disinggahinya.
    conflicting = [b for b in others
                   if b.is_established and not b.is_stale(now)
                   and not (b.is_registered and b.is_mobile)]
    if conflicting:
        # Yang terdaftar didahulukan sebagai pembanding: pernyataan
        # penyelenggara lebih otoritatif daripada akumulasi pengamatan,
        # berapa pun jumlahnya.
        strongest = max(
            conflicting, key=lambda b: (b.is_registered, b.observer_count))
        # Bobot naik seiring kekuatan bukti: binding dengan 40+ pengamat
        # adalah bukti jauh lebih kuat daripada yang baru mencapai ambang.
        confidence = min(25, strongest.observer_count // 2)

        # Pertukaran stiker berarti binding lama berhenti terlihat.
        # Kalau NMID yang discan JUGA sudah mapan dan masih aktif,
        # keduanya hidup berdampingan — ciri merchant bersebelahan
        # (ruko, food court), bukan penggantian.
        #
        # Tapi "mapan" saja tidak cukup, dan itu celah R10: penyerang yang
        # menang balapan cold start bisa memupuk binding palsu sampai
        # mapan dengan MIN_OBSERVERS device saja, lalu ikut menikmati
        # pengecualian ini selamanya.
        #
        # Karena itu basis pengamatnya harus SEBANDING dengan tetangga.
        # Merchant yang benar-benar bersebelahan menghisap lalu lintas
        # kaki yang sama, jadi jumlah pengamatnya sepadan; penyerang yang
        # memupuk 3 device di sebelah merchant 47 pengamat tidak.
        #
        # Rasio 0,10 dikalibrasi di calibrate_adjacency.py: 3,5% pasangan
        # merchant sah tertolak, dan biaya penyerang naik dari 3 ke 5
        # device. Perbandingan dipilih, bukan jarak — opsi berbasis jarak
        # gugur karena galat GPS membuat sebaran jangkar swap dan merchant
        # bersebelahan tumpang tindih 72-79% pada 2,5-8 m.
        #
        # Jujur soal batasnya: ini MENAIKKAN biaya penyerang, bukan
        # menutup celahnya. Penutupan sungguhan menuntut integritas
        # perangkat atau autentikasi klien.
        # Binding TERDAFTAR lolos uji rasio tanpa syarat: buktinya adalah
        # pernyataan penyelenggara, bukan jumlah pengamat. Merchant yang
        # baru didaftarkan punya nol pengamat, dan tanpa pengecualian ini
        # ia langsung dituduh menggusur tetangganya sendiri.
        #
        # Ini tidak membuka lagi celah R10: yang ditutup ADJACENT_MIN_RATIO
        # adalah penyerang yang memupuk binding dengan tiga device murah,
        # dan jalur itu tidak melewati pendaftaran. Untuk mendaftar,
        # penyerang butuh kunci PJP — jalur kepercayaan yang berbeda,
        # yang punya pencatatan dan pencabutannya sendiri.
        basis_sebanding = current is not None and (
            current.is_registered
            or current.observer_count
            >= ADJACENT_MIN_RATIO * strongest.observer_count
        )

        # Uji rasio di atas punya kebuntuan yang terukur: merchant sah
        # yang sepi di sebelah tetangga ramai tidak akan pernah lolos,
        # karena pemindaiannya ditolak sehingga observer_count-nya
        # membeku, dan ia membeku justru karena observer_count-nya
        # kecil. Diukur di calibrate_tetangga.py: 100% kunjungan sah
        # diberi cooling_off, dan 100 kunjungan berikutnya tidak
        # menaikkan pengamat satu pun. Lapak baru yang buka di food
        # court kena sejak pemindaian pertama, dengan nol pengamatan.
        #
        # Jalan keluarnya tidak boleh berupa pelonggaran ambang — itu
        # akan membuka lagi R10. Yang dipakai adalah bukti FISIK.
        #
        # Stiker yang ditempel MENUTUPI membuat QR di bawahnya tidak
        # bisa dipindai lagi; sejak saat itu merchant lama berhenti
        # terlihat. Kalau merchant lama TERUS terlihat setelah
        # penantang muncul, berarti tidak ada yang tertutup — keduanya
        # benar-benar ada di sana berdampingan.
        #
        # Penyerang tidak bisa memalsukan ini tanpa membatalkan
        # serangannya sendiri: membiarkan QR korban tetap terpindai
        # berarti tidak menggantikannya.
        #
        # observer_count tidak disentuh di mana pun oleh jalur ini,
        # jadi invarian §3 tetap utuh: yang ditolak tidak membangun
        # reputasi. Rumus konsensus juga tidak diubah — invarian §5
        # utuh. Yang berubah hanya syarat pengecualian koeksistensi.
        lama_masih_terpindai = (
            challenge is not None
            and challenge.first_at is not None
            and strongest.last_seen is not None
            and strongest.last_seen
            >= challenge.first_at + timedelta(hours=INCUMBENT_PROOF_HOURS)
        )
        kehadiran_terbukti = (
            lama_masih_terpindai
            and challenge.devices >= ADJACENT_MIN_DEVICES
            and challenge.span_hours >= MIN_AGE_HOURS
        )

        # Nama yang SAMA PERSIS dengan pemilik jangkar membatalkan
        # pengecualian koeksistensi, berapa pun bukti kehadirannya.
        #
        # Alasannya dari sisi penyerang. Ia harus memilih nama di QR-nya,
        # dan kedua pilihannya merugikan:
        #
        #   pakai nama korban  -> tetangga sah TIDAK PERNAH melakukan itu,
        #                         jadi ini tertangkap mesin di sini
        #   pakai nama lain    -> pembeli yang berdiri di depan warung
        #                         melihat nama yang salah di layarnya
        #
        # Yang kedua tidak bisa dihakimi mesin — "WARUNG BU SARI" dan
        # "WARUNG BU SRI" adalah dua pedagang sungguhan. Karena itu yang
        # kedua ditangani dengan MENAMPILKAN kedua nama, bukan dengan
        # menuduh. Lihat nama_kanonik() untuk angkanya.
        #
        # Perhatikan arah pemakaiannya: nama dipakai MENGETATKAN, tidak
        # pernah MELONGGARKAN. Nama adalah nilai yang dipilih penyerang;
        # melonggarkan atas dasar itu berarti menyerahkan pintu keluar
        # kepada orang yang paling berkepentingan memakainya.
        meniru_nama = bool(
            merchant_name and strongest.merchant_name
            and nama_kanonik(merchant_name)
            == nama_kanonik(strongest.merchant_name)
        )

        coexisting = (
            (current is not None and current.is_established
             and basis_sebanding)
            or kehadiran_terbukti
        ) and not meniru_nama

        # Tetangga yang sedang tumbuh bersama, tapi belum melewati umur
        # 24 jam. Diukur di lapangan dan hasilnya tidak bisa dibiarkan:
        # di kantin dengan tiga tenant berjarak 3-9 meter, tenant yang
        # melewati ambang umur beberapa MENIT lebih dulu — hanya karena
        # kebetulan dipindai pertama — mengunci tetangganya selama dua
        # hari penuh.
        #
        # Beberapa menit tidak boleh menjadi selisih antara "tetangga"
        # dan "stiker tukar".
        #
        # Yang membedakannya dari penukaran tetap fisik: merchant lama
        # HARUS masih terpindai. Stiker yang ditempel menutupi membuat
        # QR di bawahnya diam, dan penyerang tidak bisa memalsukan itu
        # tanpa membatalkan serangannya.
        #
        # KEDUA NAMA WAJIB ADA. Cabang ini tidak memblokir, jadi
        # pertahanannya berpindah ke mata pembeli — dan pembeli hanya
        # bisa menilai kalau kedua nama benar-benar ditampilkan. Klien
        # yang tidak mengirim nama merchant tidak mendapat kelonggaran
        # atas dasar sesuatu yang tidak bisa diperlihatkan.
        nama_bisa_dibandingkan = bool(merchant_name and strongest.merchant_name)

        # "Merchant lama masih terpindai" diukur terhadap kemunculan
        # PERTAMA tenant ini, bukan terhadap buku tantangan.
        #
        # Memakai buku tantangan menuntut satu penolakan terjadi lebih
        # dulu — tenant sah harus ditolak sekali sebelum diakui, dan itu
        # tidak menambah keamanan apa pun. Cabang ini mensyaratkan
        # `current` punya pengamat sendiri, jadi first_seen-nya selalu
        # ada.
        #
        # Sifat yang menahan penukaran tetap sama: stiker yang ditempel
        # MENUTUPI membuat QR lama berhenti terpindai, sehingga
        # last_seen-nya membeku sebelum penantang muncul.
        lama_masih_aktif = (
            current is not None
            and current.first_seen is not None
            and strongest.last_seen is not None
            and strongest.last_seen
            >= current.first_seen + timedelta(hours=INCUMBENT_PROOF_HOURS)
        )
        tumbuh_bersama = (
            not coexisting
            and not meniru_nama
            and nama_bisa_dibandingkan
            and current is not None
            and current.observer_count >= MIN_OBSERVERS
            and basis_sebanding
            and lama_masih_aktif
        )

        if coexisting:
            score += 20
            signals.append("adjacent_merchant")
            reasons.append((20,
                f"Terdapat merchant lain dalam radius "
                f"{strongest.distance_m(lat, lng):.0f} m yang juga aktif "
                f"— kemungkinan lokasi bersebelahan"))
            # Justru DI SINI kontras nama paling penting.
            #
            # Cabang ini MELOLOSKAN pemindaian, jadi pertahanannya
            # berpindah ke mata pembeli. Orang yang berdiri di depan
            # warungnya tahu nama mana yang benar; sistem tidak. Yang
            # bisa dilakukan sistem adalah menaruh kedua nama
            # berdampingan supaya perbandingannya tidak menuntut siapa
            # pun mengingat apa pun.
            if merchant_name and strongest.merchant_name:
                reasons.append((PRIORITAS_PENGUNGKAPAN,
                    f"Di titik ini tercatat {strongest.merchant_name}. "
                    f"Kode yang dipindai atas nama {merchant_name} — "
                    f"pastikan cocok dengan yang tertulis di stikernya."))
        elif tumbuh_bersama:
            score += W_ADJACENT_UNPROVEN
            signals.append("adjacent_merchant_unproven")
            # Kontras nama ditaruh PALING ATAS dan bukan sekadar
            # pelengkap: ia satu-satunya hal yang bisa dinilai pembeli,
            # dan cabang ini memang menyerahkan penilaiannya kepadanya.
            reasons.append((PRIORITAS_PENGUNGKAPAN,
                f"Di titik ini tercatat {strongest.merchant_name}. "
                f"Kode yang dipindai atas nama {merchant_name} — "
                f"pastikan cocok dengan yang tertulis di stikernya."))
            reasons.append((W_ADJACENT_UNPROVEN,
                f"Merchant ini baru tercatat {current.observer_count} "
                f"pengamatan di titik ini dan belum cukup lama untuk "
                f"dipastikan — periksa namanya sebelum membayar"))

        elif strongest.is_registered:
            # Sinyal TERPISAH, bukan rumus konsensus yang diubah —
            # invarian §5 mengunci rumus itu apa adanya.
            score += W_REGISTERED_CONFLICT
            signals.append("nmid_changed_at_registered_anchor")
            reasons.append((W_REGISTERED_CONFLICT,
                "Lokasi ini terdaftar resmi atas merchant lain oleh "
                "penyelenggara pembayaran"))
        else:
            score += 60 + confidence
            signals.append("nmid_changed_at_anchor")
            reasons.append((60 + confidence,
                f"Merchant ID berbeda dari {strongest.observer_count} pengamatan "
                f"sebelumnya di lokasi ini"))

            if meniru_nama:
                score += W_NAME_IMPERSONATION
                signals.append("anchor_name_impersonation")
                reasons.append((W_NAME_IMPERSONATION,
                    f"Kode ini memakai nama yang sama dengan merchant yang "
                    f"tercatat di titik ini ({strongest.merchant_name}) tapi "
                    f"Merchant ID-nya berbeda — pola khas stiker yang ditempel "
                    f"menyamar"))
            elif strongest.merchant_name:
                # Bukan skor, melainkan pengungkapan. Pembeli yang berdiri
                # di depan warungnya tahu nama mana yang benar; sistem
                # tidak. Yang bisa dilakukan sistem adalah menaruh kedua
                # nama berdampingan supaya perbandingannya tidak menuntut
                # orang mengingat apa pun.
                if merchant_name:
                    reasons.append((PRIORITAS_PENGUNGKAPAN,
                        f"Di titik ini tercatat {strongest.merchant_name}. "
                        f"Kode yang dipindai atas nama {merchant_name}."))
                else:
                    reasons.append((PRIORITAS_INFORMASI,
                        f"Lokasi ini konsisten terdaftar sebagai "
                        f"{strongest.merchant_name}"))

    # --- Sinyal 2: satu NMID tersebar di banyak area ----------------
    elsewhere = [
        b for b in same_nmid_elsewhere
        if b.distance_m(lat, lng) > SCATTER_MIN_KM * 1000
    ]
    areas = _distinct_areas(elsewhere, lat, lng)

    # Merchant sah yang PINDAH memicu sinyal yang sama dengan penyebar
    # stiker, dan akibatnya permanen: anomali membuat pengamatan tidak
    # dicatat, sehingga lokasi barunya tidak pernah tumbuh. Diukur:
    # 500 pengamat di tempat baru dan lokasi lama terakhir terlihat
    # sepuluh tahun lalu pun tidak menyembuhkannya, karena cabang ini —
    # berbeda dari cabang konflik jangkar — tidak menyaring binding
    # usang sama sekali.
    #
    # Yang terkena justru segmen inti: pedagang kaki lima, food truck,
    # pedagang pasar. Satu-satunya jalan keluar yang ada adalah
    # is_registered + is_mobile, dan itu menuntut integrasi PJP.
    #
    # Pembedanya fisik: seorang pedagang hanya bisa berada di satu
    # tempat pada satu waktu. Tiga syarat, semuanya harus terpenuhi:
    #
    #   1  cukup banyak orang BERBEDA menemuinya di sini (challenge),
    #      jadi ini bukan klaim sepihak satu perangkat
    #   2  semua lokasi lain sudah diam sebelum tempat ini ramai
    #   3  periode aktif lokasi-lokasi lama tidak pernah beririsan
    #
    # Syarat 3 yang menahan penyebar bermodal sabar: stiker yang dipasang
    # bersamaan punya rentang yang tumpang tindih walau jarang dipindai.
    pindah_terbukti = (
        challenge is not None
        and challenge.devices >= ADJACENT_MIN_DEVICES
        and challenge.span_hours >= MIN_AGE_HOURS
        and all(a.last_seen is None or a.last_seen < challenge.first_at
                for a in areas)
        and _berurutan(areas)
    )

    if len(areas) >= SCATTER_MIN_AREAS and not pindah_terbukti:
        score += 60
        signals.append("nmid_scatter")
        farthest = max(areas, key=lambda b: b.distance_m(lat, lng))
        reasons.append((60,
            f"Merchant ID yang sama terdeteksi di {len(areas) + 1} area berbeda, "
            f"terjauh {farthest.distance_m(lat, lng) / 1000:.0f} km — "
            f"pola khas stiker yang disebar"))
    elif len(areas) >= SCATTER_MIN_AREAS:
        score += W_RELOCATED
        signals.append("nmid_relocated")
        reasons.append((W_RELOCATED,
            f"Merchant ID ini pernah tercatat di {len(areas)} lokasi lain, "
            f"semuanya sudah tidak aktif — pola pindah tempat, "
            f"bukan stiker yang disebar"))
    elif len(areas) == 1:
        score += 25
        signals.append("nmid_second_location")
        reasons.append((25,
            f"Merchant ID ini juga tercatat di lokasi lain berjarak "
            f"{areas[0].distance_m(lat, lng) / 1000:.1f} km"))

    # --- Riwayat jangkar ini sendiri --------------------------------
    if current and current.is_registered:
        # Dibedakan dari konsensus dengan sengaja: "terdaftar" dan
        # "diamati banyak orang" adalah dua klaim berbeda kekuatannya,
        # dan auditor berhak tahu yang mana yang berlaku.
        if not conflicting and not areas:
            score = max(0, score - 20)
        signals.append("registered_merchant")
        reasons.append((PRIORITAS_INFORMASI,
            "Terdaftar resmi di lokasi ini oleh penyelenggara pembayaran"
            + (f" sebagai {current.merchant_name}"
               if current.merchant_name else "")))
    elif current and current.is_established:
        if not conflicting and not areas:
            score = max(0, score - 20)
        signals.append("established_binding")
        reasons.append((PRIORITAS_INFORMASI,
            f"Konsisten dengan {current.observer_count} pengamatan sebelumnya "
            f"di lokasi ini"))
    elif current:
        score += 15
        signals.append("young_binding")
        reasons.append((15,
            f"Binding baru — baru {current.observer_count} pengamatan, "
            f"belum cukup untuk diverifikasi"))
    elif not conflicting:
        score += 35
        signals.append("first_observation")
        reasons.append((35, "Lokasi ini belum pernah tercatat sebelumnya"))

    score = max(0, min(100, score))

    if ("nmid_changed_at_anchor" in signals
            or "nmid_changed_at_registered_anchor" in signals
            or "nmid_scatter" in signals):
        status = ANOMALY
    elif current and current.is_established and score <= 25:
        status = VERIFIED
    else:
        status = UNKNOWN

    if not reasons:
        reasons.append(
            (PRIORITAS_INFORMASI,
             "Belum ada cukup data untuk memverifikasi lokasi ini"))

    alasan, bobot = urutkan_alasan(reasons)
    return Verdict(
        status=status,
        action=_floor_action(status, _action_for(score)),
        risk_score=score,
        reasons=alasan,
        reason_weights=bobot,
        signals=signals,
        matched_binding=current,
    )


# --- Komposisi Layer 1 + Layer 2 -----------------------------------


def compose(verdict: "Verdict", behavior) -> "Verdict":
    """Gabungkan putusan Layer 1 dengan hasil Layer 2 jadi satu putusan.

    Layer 1 menjawab "apakah merchant ini memang yang seharusnya di sini".
    Layer 2 menjawab "apakah artefak yang dipindai berperilaku seperti QR
    yang sah". Keduanya bisa gagal sendiri-sendiri, jadi Layer 2
    MELENGKAPI, bukan menggantikan.

    Tiga aturan, dan ketiganya searah:

    1. Skor dijumlah lalu dijepit 0-100. Layer 2 tidak punya bobot negatif
       sama sekali — tidak adanya sinyal Layer 2 bukan bukti keabsahan,
       logika yang sama dengan invarian §2.

    2. Layer 2 tidak pernah bisa MENAIKKAN status ke arah verified.
       Ia hanya bisa menurunkan:
         - kontradiksi struktural  -> anomaly
         - sinyal lain apa pun     -> verified turun jadi unknown,
           karena jangkarnya boleh jadi benar tapi artefaknya diragukan
       Status anomaly dari Layer 1 tidak pernah dicabut Layer 2.

    3. Aksi tetap dipetakan ke empat tier yang sama lewat ambang yang
       sama (invarian §4). Layer 2 tidak memperkenalkan skala baru.
    """
    if behavior is None or (behavior.score == 0 and not behavior.hard_violation):
        return verdict

    score = max(0, min(100, verdict.risk_score + behavior.score))

    if behavior.hard_violation:
        status = ANOMALY
    elif verdict.status == VERIFIED:
        status = UNKNOWN
    else:
        status = verdict.status

    # Alasan dari kedua layer digabung lalu diurutkan ulang menurut
    # bobot SEBENARNYA. Tanpa ini, seluruh alasan Layer 1 selalu
    # mendahului Layer 2 — termasuk ketika yang menentukan justru ada
    # di Layer 2, seperti NMID cacat bentuk (+70) yang kalah posisi
    # dari cold start (+35).
    bobot_l1 = verdict.reason_weights or [0] * len(verdict.reasons)
    berbobot = list(zip(bobot_l1, verdict.reasons))
    berbobot += list(zip(behavior.weights, behavior.reasons))
    alasan, bobot = urutkan_alasan(berbobot)

    return Verdict(
        status=status,
        action=_floor_action(status, _action_for(score)),
        risk_score=score,
        reasons=alasan,
        reason_weights=bobot,
        signals=verdict.signals + behavior.signals,
        matched_binding=verdict.matched_binding,
    )
