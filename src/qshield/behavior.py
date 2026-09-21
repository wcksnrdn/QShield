"""
Layer 2 — penilaian perilaku pada jalur QR.

Layer 1 menjawab "apakah merchant ini memang yang seharusnya ada di
lokasi ini". Layer 2 menjawab pertanyaan yang berbeda: "apakah artefak
yang barusan dipindai berperilaku seperti QR yang sah". Keduanya bisa
gagal sendiri-sendiri — stiker palsu di lokasi yang belum punya jangkar
lolos Layer 1, tapi payload-nya sering mengkhianati dirinya sendiri.

Dua kelas sinyal:

  struktural   turunan murni dari payload, deterministik, tanpa state.
               Sebagian adalah KONTRADIKSI: payload yang melanggarnya
               tidak mungkin diterbitkan acquirer yang patuh spec.

  perilaku     turunan dari agregat pada baris binding. Tidak ada baris
               per-device baru, tidak ada koordinat — lihat Keputusan 6
               dan invarian §8. Yang diingat sistem adalah properti
               jangkar, bukan kunjungan orang.

Aturan yang tidak boleh dilanggar: Layer 2 HANYA MENAIKKAN risiko,
tidak pernah menurunkan. Tidak adanya sinyal Layer 2 bukan bukti
keabsahan — logika yang sama dengan invarian §2. Karena itu tidak ada
satu pun bobot negatif di berkas ini.

Seperti binding.py, modul ini tidak mengimpor store.py: agregat
diserahkan lewat AnchorState supaya aturannya bisa diuji tanpa I/O.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# --- Parameter yang bisa dikalibrasi -------------------------------
#
# Angka di bawah dikalibrasi lewat scripts/calibrate_layer2.py.
# Yang belum punya dasar empiris ditandai UNCALIBRATED secara eksplisit
# supaya tidak ada konstanta yang menyelinap masuk tanpa alasan.

# Kontradiksi struktural: payload melanggar spec EMVCo/QRIS. Bukan
# probabilistik — acquirer yang patuh tidak bisa menerbitkannya.
W_STRUCTURAL = 70

# Sidik jari encoding. Lemah dan UNCALIBRATED: memisahkan "dicetak ulang
# oleh penyerang" dari "diterbitkan generator yang rewel" butuh korpus
# payload QRIS asli yang belum kami punya. Bobotnya sengaja kecil dan
# totalnya dibatasi agar tidak pernah bisa menggerakkan tier sendirian.
W_TAG_ORDER = 15
W_CRC_CASE = 10
SOFT_FINGERPRINT_CAP = 25

# Percobaan anomali berulang di satu jangkar. Berskala dengan kekuatan
# bukti, pola yang sama dengan invarian §5.
W_ANOMALY_BASE = 12
W_ANOMALY_CAP = 30

# Jejak serangan memudar. `last_anomaly_at` disimpan sejak Keputusan 11
# dan — sampai ditemukan lewat keluhan lapangan — tidak pernah dibaca,
# sehingga serangan tiga minggu lalu menghukum sekeras serangan satu jam
# lalu. Merchant yang baru pindah ke titik itu ikut menanggung sejarah
# yang bukan miliknya.
#
# 7 hari dipilih dari calibrate_decay.py: merchant sah yang muncul
# sebulan kemudian tidak lagi dihukum, sementara penyerang harus
# menunggu ~3 minggu agar jejaknya pudar — dan selama menunggu itu
# stikernya tidak menghasilkan apa pun sedangkan binding korbannya
# terus menguat.
ANOMALY_HALFLIFE_DAYS = 7.0

# Di bawah ini sinyalnya tidak lagi berarti dan dibuang sepenuhnya,
# supaya tidak menyisakan alasan yang membingungkan pengguna karena
# menyebut serangan yang bobotnya sudah nol.
ANOMALY_MIN_WEIGHT = 3

# Sinyal "lonjakan pemindaian" pernah ada di sini dan sudah DIBUANG.
# calibrate_layer2.py menunjukkan alasannya: membangun reputasi palsu
# hanya butuh MIN_OBSERVERS=3 device dalam rentang MIN_AGE_HOURS=24 jam,
# jadi serangannya pelan — puncaknya 3 pemindaian. Ambang mana pun yang
# masih bisa ditoleransi warung laris (>=120/jam) melewatkan 100%
# serangan, sementara ambang yang cukup rendah untuk menangkapnya
# menandai 100% merchant sibuk. Volume tidak memisahkan keduanya.
# Pertahanan yang benar untuk probing otomatis adalah rate limiting,
# bukan skor risiko.

# --- Klaim lokasi --------------------------------------------------
#
# Koordinat dan akurasi datang dari klien, dan server tidak punya cara
# memverifikasinya (R1). Yang BISA diperiksa adalah apakah klaimnya
# masuk akal secara fisik — pembohong yang malas sering lupa berbohong
# dengan konsisten.
#
# GNSS ponsel konsumen tidak pernah melaporkan radius keyakinan di bawah
# satu meter; yang terbaik pun berhenti di sekitar 3 m, dan itu butuh
# dual-frequency di bawah langit terbuka. Nilai 0 sama sekali mustahil.
# Ambang 1,0 m sengaja dipasang jauh di bawah kemampuan perangkat asli
# supaya nyaris tidak mungkin menandai pemindaian sah.
MIN_PLAUSIBLE_ACCURACY_M = 1.0
W_IMPLAUSIBLE_ACCURACY = 45

# Catatan: "akurasi tidak dikirim" pernah jadi sinyal risiko di sini dan
# sudah DIBUANG. Menghukum absennya sebuah field sambil mendeklarasikan
# field itu opsional adalah desain yang tidak koheren — dan absennya
# membuka pintu keluar dari invarian §6, yang terlalu serius untuk
# diselesaikan dengan menambah skor. Sekarang accuracy_m wajib, dan
# permintaan tanpanya ditolak 422 di batas sistem.

# --- Pemakaian ulang QR dinamis ------------------------------------
#
# QR dinamis dibuat untuk SATU transaksi: satu nominal, satu nomor
# tagihan, ditampilkan di satu mesin kasir. Stiker statis memang
# dipindai ribuan kali — itu gunanya — jadi sinyal ini hanya berlaku
# untuk yang dinamis.
#
# Yang dideteksi BUKAN replay kriptografis. Itu menuntut nonce sekali
# pakai di sisi PJP dan memang di luar jangkauan lapisan pra-pembayaran.
# Yang dideteksi: artefak sekali pakai yang dipakai berkali-kali —
# modus "satu QR disebar ke puluhan korban lewat pesan".
#
# Dikalibrasi di calibrate_dynamic.py:
#   ambang 4 kali    menandai 0,60% QR dinamis yang sah
#   ambang 150 m     menandai 0,000% (galat GPS p99,9 hanya 34 m)
#
# Sebaran jarak diberi bobot lebih berat karena ia sinyal yang jauh
# lebih kuat: empat kali pemindaian masih punya penjelasan wajar,
# sedangkan satu QR yang dipindai di dua tempat berjauhan tidak.
DYNAMIC_REUSE_THRESHOLD = 4
DYNAMIC_SPREAD_M = 150

# Nominal berubah untuk nomor tagihan yang sama. Serius — korban
# membayar jumlah yang bukan seharusnya — tapi TIDAK dijadikan
# kontradiksi keras, karena ada kasus sah: pesanan ditambah di restoran,
# kasir menerbitkan ulang QR untuk tagihan yang sama dengan nominal
# lebih tinggi.
#
# Yang membuat sinyal ini tetap berguna meski begitu: alasannya
# menyebutkan KEDUA nominalnya. Pengguna tinggal melihat layar kasir dan
# memutuskan sendiri — pemeriksaan yang tidak bergantung pada data kami.
W_BILL_AMOUNT_CHANGED = 35

W_DYNAMIC_REUSED = 30
W_DYNAMIC_SPREAD = 55

# --- Yang TERCETAK di stiker vs yang ada di dalam QR ---------------
#
# Stiker QRIS resmi mencetak nama merchant dan NMID dalam huruf yang
# bisa dibaca manusia, di samping kodenya.
#
# Penipu jarang mencetak ulang seluruh standee — mahal dan mencolok.
# Yang paling sering: menempel stiker QR kecil menutupi area kodenya
# saja, meninggalkan teks tercetak yang asli tetap terlihat.
#
# Akibatnya NMID tercetak tidak lagi cocok dengan NMID di dalam QR —
# dan itu bukti pertukaran yang langsung, tanpa perlu riwayat apa pun
# tentang merchant itu. Bekerja pada pemindaian PERTAMA.
#
# Bobotnya tinggi karena tidak ada penjelasan wajar untuk stiker resmi
# yang teksnya bertentangan dengan kodenya sendiri.
W_PRINTED_NMID_MISMATCH = 75
W_PRINTED_NAME_MISMATCH = 45

# --- Sidik jari WiFi sekitar ---------------------------------------
#
# Daftar titik akses di sekeliling adalah penanda tempat yang jauh lebih
# tajam daripada GPS: ia bekerja di dalam gedung dan memisahkan dua
# lapak berdempetan. Browser sengaja tidak menyediakannya — justru
# karena setajam itu — sehingga hanya klien native yang bisa mengisinya.
#
# Klien yang melakukan hashing, jadi BSSID mentah tidak pernah sampai
# ke server.
#
# AMBANGNYA BELUM DIKALIBRASI LAPANGAN. Berapa banyak titik akses yang
# wajar berubah antara dua kunjungan ke warung yang sama tidak bisa
# ditebak dari simulasi — itu bergantung pada kepadatan WiFi, jam buka,
# dan perangkat yang lalu-lalang. Nilai di bawah adalah titik awal yang
# sengaja longgar, dan sinyalnya hanya berlaku bila jangkar sudah punya
# sidik jari yang cukup besar.
AP_MIN_KNOWN = 4          # titik akses minimum sebelum sidik jari dipakai
AP_MIN_OVERLAP = 0.15     # irisan di bawah ini dianggap tempat berbeda
# Irisan minimum untuk MENGENALI tempat, bukan sekadar tidak menolaknya.
#
# Diukur dari sidik jari lapangan sungguhan yang dikumpulkan tim:
#
#     tempat sama (jarak 1-3 m)    irisan 0,66 - 0,80
#     tempat berbeda (116 km)      irisan 0,00
#
# Ambang 0,45 duduk di celah itu dengan margin ke dua arah: masih
# mengenali walau 45% titik akses berganti sejak sidik jarinya dibuat,
# dan masih jauh di atas nol.
#
# BATASAN YANG DIAKUI. Korpusnya belum memuat kasus tengah — tempat
# BERBEDA yang BERDEKATAN, misalnya ruko sebelah atau lantai atas, yang
# berbagi sebagian titik akses. Angka ini akan berubah begitu kasus itu
# terukur. Karena itu sidik jari WiFi TIDAK PERNAH dipakai memberi
# proceed; ia hanya dipakai menaikkan kecurigaan dan memberi konteks.
AP_LOCATE_MIN_OVERLAP = 0.45
# Bobot ketika sidik jari WiFi mengenali sebuah tempat, tapi QR yang
# dipindai milik merchant LAIN. Ditambahkan ke 40 dasar jalur akurasi
# rendah, menghasilkan 65 -> step_up.
#
# Sengaja step_up, bukan cooling_off. Pelajaran dari R11: tuduhan palsu
# terhadap pedagang sah mahal harganya, dan korpus sidik jari ini belum
# memuat kasus beda-tempat-tapi-berdekatan — ruko sebelah yang berbagi
# titik akses persis akan terlihat seperti ini. Meminta verifikasi
# adalah tindakan yang benar untuk bukti sekuat ini; memblokir belum.
W_AP_FOREIGN_NMID = 25
W_AP_MISMATCH = 30

# --- Integritas perangkat ------------------------------------------
#
# Diisi klien NATIVE; klien web tidak akan pernah bisa mengisinya karena
# browser sengaja tidak membocorkan konfigurasi sistem ke halaman.
#
# Rantai kepercayaannya penting dan harus disebut terus terang: field
# ini dilaporkan klien dan TIDAK BISA diverifikasi Q-Shield. Yang
# membuatnya berarti adalah `attested` — hasil Play Integrity / App
# Attest yang diverifikasi PJP di sisi mereka, lalu dipertanggungkan
# lewat kunci API mereka. Jadi kami tidak memercayai perangkatnya; kami
# memercayai PJP yang menyatakan sudah memeriksanya.
#
# Bobot mock_location tidak ada di sini: GPS yang diakui palsu membuat
# jangkarnya tidak layak dinilai sama sekali, jadi ia ditangani seperti
# akurasi buruk di api.py — menolak memberi putusan lokasi, bukan
# menambah skor. Lihat invarian §6.
W_DEVICE_ROOTED = 25
W_ATTESTATION_FAILED = 30

# NMID QRIS: "ID" + 13 digit.
NMID_LENGTH = 15
NMID_PREFIX = "ID"

# Tag wajib EMVCo Merchant Presented Mode.
MANDATORY_TAGS = ("00", "53", "58", "59", "63")

# Tag 54 (nominal) tidak boleh ada pada QR statis (tag 01 = "11").
TAG_POINT_OF_INITIATION = "01"
TAG_AMOUNT = "54"
STATIC_INDICATOR = "11"


@dataclass
class AnchorState:
    """Agregat perilaku milik satu jangkar.

    Sengaja hanya berisi hitungan dan waktu. Tidak ada device, tidak ada
    koordinat, tidak ada apa pun yang bisa dirangkai jadi jejak seseorang.
    """

    anomaly_attempts: int = 0
    last_anomaly_at: Optional[datetime] = None


@dataclass
class Signal:
    name: str
    weight: int
    reason: str
    hard: bool = False


@dataclass
class BehaviorResult:
    score: int = 0
    signals: list = field(default_factory=list)
    reasons: list = field(default_factory=list)
    # Bobot tiap alasan, sejajar dengan reasons. Dipakai compose()
    # untuk mengurutkan apa yang dibaca pengguna lebih dulu.
    weights: list = field(default_factory=list)
    hard_violation: bool = False

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "signals": self.signals,
            "reasons": self.reasons,
            "hard_violation": self.hard_violation,
        }


def _location_claim_signals(accuracy_m, has_coords: bool) -> list:
    """Sinyal dari klaim lokasi, tanpa memercayai isinya.

    Tidak satu pun sinyal di sini membuktikan koordinatnya benar — itu
    mustahil dari sisi server (R1). Yang diperiksa hanya apakah klaimnya
    konsisten dengan perangkat yang sungguh-sungguh ada.
    """
    out = []
    if not has_coords or accuracy_m is None:
        return out

    if accuracy_m < MIN_PLAUSIBLE_ACCURACY_M:
        out.append(Signal(
            name="implausible_accuracy",
            weight=W_IMPLAUSIBLE_ACCURACY,
            reason=(
                f"Akurasi lokasi {accuracy_m:.2f} m berada di bawah batas "
                f"fisik GNSS ponsel — nilai ini tidak berasal dari "
                f"penerima sungguhan"
            ),
        ))
    return out


def _dynamic_qr_signals(parsed, riwayat, nominal_lain=None) -> list:
    """Sinyal dari jejak pemakaian satu QR dinamis."""
    from . import binding as bd

    if parsed.is_static:
        return []

    out = []

    # --- Nominal berubah untuk tagihan yang sama --------------------
    #
    # Penipu yang mencegat QR dinamis lalu mengubah nominalnya
    # menghasilkan hash payload berbeda, sehingga lolos dari deteksi
    # pemakaian ulang. Nomor tagihannya tetap — dan itu yang menangkapnya.
    if nominal_lain:
        sebelumnya = nominal_lain[0].get("amount")
        out.append(Signal(
            name="bill_amount_changed",
            weight=W_BILL_AMOUNT_CHANGED,
            reason=(
                f"Nomor tagihan yang sama sebelumnya menunjukkan "
                f"Rp{sebelumnya}, sekarang Rp{parsed.amount} — "
                f"cocokkan dengan jumlah di layar kasir"
            ),
        ))

    if riwayat is None:
        return out
    sebar = riwayat.get("max_spread_m", 0.0)
    kali = riwayat.get("times_seen", 1)

    if sebar > DYNAMIC_SPREAD_M:
        out.append(Signal(
            name="dynamic_qr_spread",
            weight=W_DYNAMIC_SPREAD,
            reason=(
                f"Kode pembayaran sekali-pakai ini sudah dipindai di tempat "
                f"lain berjarak {sebar / 1000:.1f} km — kode dinamis yang sah "
                f"hanya muncul di satu kasir"
            ),
        ))

    if kali >= DYNAMIC_REUSE_THRESHOLD:
        out.append(Signal(
            name="dynamic_qr_reused",
            weight=W_DYNAMIC_REUSED,
            reason=(
                f"Kode pembayaran ini sudah dipakai {kali} kali — kode "
                f"dinamis dibuat untuk satu transaksi saja"
            ),
        ))

    return out


def _origin_signals(parsed, area, nama_lain) -> list:
    """Sinyal yang bekerja tanpa riwayat merchant itu sendiri.

    Keduanya memakai data yang sudah ada di dalam payload dan selama ini
    tidak pernah dinilai — inilah yang membuat pemindaian PERTAMA sebuah
    stiker palsu tetap bisa tertangkap.
    """
    from . import binding as bd

    out = []

    # --- Kota di stiker bertentangan dengan kota wilayahnya ---------
    if area is not None:
        kota_wilayah, setuju, total = area
        kota_qr = bd.normalize_city(parsed.merchant_city)
        cukup = (setuju >= bd.AREA_CITY_MIN_NMIDS
                 and setuju / total >= bd.AREA_CITY_MIN_SHARE)
        if cukup and kota_qr and kota_qr != kota_wilayah:
            out.append(Signal(
                name="city_mismatch",
                weight=bd.W_CITY_MISMATCH,
                reason=(
                    f"Stiker ini terdaftar di {parsed.merchant_city}, "
                    f"sedangkan {setuju} merchant lain di sekitar sini "
                    f"terdaftar di {kota_wilayah}"
                ),
            ))

    # --- Satu NMID, dua nama merchant -------------------------------
    nama_qr = (parsed.merchant_name or "").strip().upper()
    berbeda = [n for n in (nama_lain or [])
               if n and n.strip().upper() != nama_qr]
    if nama_qr and berbeda:
        out.append(Signal(
            name="nmid_name_inconsistent",
            weight=bd.W_NAME_INCONSISTENT,
            reason=(
                f"Merchant ID ini sebelumnya tercatat sebagai "
                f"{berbeda[0]}, sekarang mengaku {parsed.merchant_name}"
            ),
        ))

    return out


def _dialect_signals(parsed, profil) -> list:
    """Payload mengaku dari penerbit X tapi tidak menyusun seperti X.

    Tidak menangkap sticker-swap — stiker penipu diterbitkan acquirer
    sungguhan, jadi dialeknya cocok sempurna. Yang ditangkap adalah QR
    yang DIBANGKITKAN ULANG oleh orang lain.
    """
    from . import binding as bd
    from . import emvco

    if not profil:
        return []

    punya = emvco.dialect(parsed)
    menyimpang = []
    for atribut, (nilai, setuju, total) in profil.items():
        cukup = (setuju >= bd.ISSUER_MIN_NMIDS
                 and setuju / total >= bd.ISSUER_MIN_SHARE)
        if cukup and punya.get(atribut) != nilai:
            menyimpang.append(atribut)

    if not menyimpang:
        return []

    bobot = min(bd.ISSUER_DEVIATION_CAP,
                bd.W_ISSUER_DEVIATION * len(menyimpang))
    LABEL = {
        "tag_order": "urutan field",
        "acct_tag": "nomor template merchant",
        "acct_subtag_order": "susunan data merchant",
        "crc_case": "penulisan checksum",
        "pan_len": "panjang nomor akun",
        "nmid_len": "panjang Merchant ID",
    }
    rinci = ", ".join(LABEL.get(a, a) for a in menyimpang)
    return [Signal(
        name="issuer_dialect_deviation",
        weight=bobot,
        reason=(
            f"Kode ini mengaku diterbitkan penyelenggara yang sama dengan "
            f"merchant lain, tapi cara penyusunannya berbeda ({rinci}) — "
            f"pola khas kode yang dibangkitkan ulang"
        ),
    )]


def _rarity_signals(parsed, corpus) -> list:
    """Model kelangkaan tak-terawasi — lihat profile.py."""
    from . import profile as pf

    bobot, langka = pf.score(parsed, corpus)
    if not bobot:
        return []
    return [Signal(
        name="rare_merchant_profile",
        weight=bobot,
        reason=pf.explain(langka),
    )]


def _printed_signals(parsed, printed) -> list:
    """Bandingkan teks tercetak di stiker dengan isi QR-nya.

    `printed` berisi apa yang dibaca dari stiker fisik — diketik
    pengguna, atau hasil OCR klien. Ketiadaannya tidak dihukum: stiker
    yang teksnya tidak terbaca bukan kesalahan siapa pun.
    """
    if not printed:
        return []

    out = []

    tercetak_nmid = (getattr(printed, "nmid", None) or "").strip().upper()
    if tercetak_nmid:
        qr_nmid = (parsed.nmid or "").strip().upper()
        # Sebagian stiker mencetak NMID tanpa awalan "ID".
        cocok = (tercetak_nmid == qr_nmid
                 or tercetak_nmid == qr_nmid.removeprefix("ID")
                 or "ID" + tercetak_nmid == qr_nmid)
        if not cocok:
            out.append(Signal(
                name="printed_nmid_mismatch",
                weight=W_PRINTED_NMID_MISMATCH,
                hard=True,
                reason=(
                    f"Merchant ID yang tercetak di stiker ({tercetak_nmid}) "
                    f"berbeda dari yang ada di dalam kode QR "
                    f"({parsed.nmid}) — kode ini kemungkinan ditempel "
                    f"menutupi stiker aslinya"
                ),
            ))

    tercetak_nama = (getattr(printed, "merchant_name", None) or "").strip()
    if tercetak_nama:
        qr_nama = (parsed.merchant_name or "").strip()
        # Dibandingkan longgar: stiker sering memakai huruf besar semua,
        # dan spasi ganda lazim terjadi pada cetakan.
        def rapikan(x):
            return " ".join(x.upper().split())
        if rapikan(tercetak_nama) != rapikan(qr_nama):
            out.append(Signal(
                name="printed_name_mismatch",
                weight=W_PRINTED_NAME_MISMATCH,
                reason=(
                    f"Nama yang tercetak di stiker ({tercetak_nama}) "
                    f"berbeda dari nama di dalam kode QR ({qr_nama})"
                ),
            ))

    return out


def _ap_signals(ambient, known) -> list:
    """Bandingkan titik akses sekitar dengan yang dikenal di jangkar ini.

    Irisan Jaccard: berapa banyak titik akses yang sama antara
    pemindaian ini dan yang pernah terlihat di sini.
    """
    from . import binding as bd

    if not ambient or not known or len(known) < AP_MIN_KNOWN:
        return []

    sekarang = set(str(a)[:64] for a in ambient)
    if not sekarang:
        return []

    irisan = len(sekarang & known)
    gabungan = len(sekarang | known)
    skor = irisan / gabungan if gabungan else 0.0

    if skor >= AP_MIN_OVERLAP:
        return []

    return [Signal(
        name="ambient_wifi_mismatch",
        weight=W_AP_MISMATCH,
        reason=(
            f"Jaringan WiFi di sekitar tidak cocok dengan yang biasa "
            f"terlihat di lokasi ini ({irisan} dari {len(known)} titik "
            f"akses dikenali) — koordinatnya cocok tapi tempatnya "
            f"kemungkinan berbeda"
        ),
    )]


def _device_signals(integrity) -> list:
    """Sinyal dari laporan integritas perangkat.

    Ketiadaan laporan TIDAK diberi skor. Setiap klien web akan selalu
    kosong di sini, dan menghukumnya berarti menghukum seluruh pengguna
    web untuk sesuatu yang bukan kesalahan mereka — kesalahan yang sama
    yang pernah dibuat lalu dicabut pada `accuracy_missing`.

    Yang dilakukan sebagai gantinya: ketiadaannya DIUNGKAPKAN di
    tanggapan (`device_integrity: "not_provided"`), supaya jelas
    pemeriksaan itu tidak pernah dijalankan — bukan dijalankan lalu
    lolos. Ketiadaan bukti bukan bukti ketiadaan, invarian §2.
    """
    if integrity is None:
        return []

    out = []
    if getattr(integrity, "rooted", None) is True:
        out.append(Signal(
            name="device_rooted",
            weight=W_DEVICE_ROOTED,
            reason=(
                "Perangkat dilaporkan sudah di-root atau di-jailbreak — "
                "perlindungan sistem operasinya tidak lagi bisa diandalkan"
            ),
        ))
    if getattr(integrity, "attested", None) is False:
        out.append(Signal(
            name="attestation_failed",
            weight=W_ATTESTATION_FAILED,
            reason=(
                "Pemeriksaan keaslian perangkat tidak lolos — aplikasi atau "
                "perangkatnya mungkin telah dimodifikasi"
            ),
        ))
    return out


def _structural_signals(parsed) -> list:
    """Sinyal yang seluruhnya turunan dari payload."""
    out = []
    tags = parsed.tags

    # --- Kontradiksi 1: QR statis membawa nominal -------------------
    # Stiker statis dicetak sekali dan dipajang; nominalnya diisi
    # pembayar. Payload statis yang sudah membawa tag 54 berarti ada
    # yang membangkitkan ulang kode itu.
    if tags.get(TAG_POINT_OF_INITIATION, STATIC_INDICATOR) == STATIC_INDICATOR:
        if TAG_AMOUNT in tags:
            out.append(Signal(
                name="static_qr_with_amount",
                weight=W_STRUCTURAL,
                hard=True,
                reason=(
                    f"QR statis membawa nominal terkunci "
                    f"Rp{tags[TAG_AMOUNT]} — stiker statis yang sah tidak "
                    f"pernah mencantumkan nominal"
                ),
            ))

    # --- Kontradiksi 2: tag wajib hilang ----------------------------
    hilang = [t for t in MANDATORY_TAGS if t not in tags]
    if hilang:
        out.append(Signal(
            name="missing_mandatory_tags",
            weight=W_STRUCTURAL,
            hard=True,
            reason=(
                f"Tag wajib EMVCo tidak ada: {', '.join(hilang)} — "
                f"payload tidak diterbitkan penyelenggara yang patuh"
            ),
        ))

    # --- Kontradiksi 3: NMID cacat bentuk ---------------------------
    nmid = parsed.nmid
    if nmid is not None:
        badan = nmid[len(NMID_PREFIX):]
        if (len(nmid) != NMID_LENGTH
                or not nmid.startswith(NMID_PREFIX)
                or not badan.isdigit()):
            out.append(Signal(
                name="malformed_nmid",
                weight=W_STRUCTURAL,
                hard=True,
                reason=(
                    f"Format Merchant ID tidak sesuai standar QRIS "
                    f"('{nmid}' — seharusnya {NMID_PREFIX} + "
                    f"{NMID_LENGTH - len(NMID_PREFIX)} digit)"
                ),
            ))

    # --- Sidik jari encoding (lemah, UNCALIBRATED) ------------------
    # parse_tlv menyisipkan tag sesuai urutan kemunculan, dan dict
    # Python mempertahankan urutan sisip — jadi ini urutan asli payload.
    urutan = list(tags.keys())
    if urutan != sorted(urutan):
        out.append(Signal(
            name="noncanonical_tag_order",
            weight=W_TAG_ORDER,
            reason=(
                "Urutan field payload tidak menaik — pola khas kode yang "
                "dibongkar lalu disusun ulang"
            ),
        ))

    if parsed.crc_found and parsed.crc_found != parsed.crc_found.upper():
        out.append(Signal(
            name="noncanonical_crc_case",
            weight=W_CRC_CASE,
            reason=(
                "Checksum ditulis huruf kecil — penyimpangan dari bentuk "
                "yang diterbitkan acquirer"
            ),
        ))

    return out


def _behavioral_signals(state: Optional[AnchorState], nmid_matches_anchor: bool,
                        now: datetime, anchor_has_owner: bool = False) -> list:
    """Sinyal dari agregat jangkar."""
    if state is None:
        return []
    out = []

    # --- Jangkar ini pernah diserang --------------------------------
    #
    # Penting: hanya berlaku kalau NMID yang dipindai BUKAN pemilik sah
    # jangkar. Tanpa syarat itu, penyerang bisa menaikkan risiko merchant
    # jujur cukup dengan menempel stiker palsu berkali-kali di depannya —
    # penolakan layanan lewat counter kami sendiri.
    # Hanya berlaku bila jangkar ini punya pemilik yang MAPAN. Kalau
    # belum ada yang mapan di sini, kita tidak tahu tempat ini milik
    # siapa — dan percobaan anomali masa lalu tidak mengatakan apa pun
    # tentang merchant yang baru muncul.
    if (state.anomaly_attempts > 0 and not nmid_matches_anchor
            and anchor_has_owner):
        bobot = min(W_ANOMALY_CAP, W_ANOMALY_BASE * state.anomaly_attempts)

        # Peluruhan eksponensial sejak serangan terakhir.
        if state.last_anomaly_at is not None:
            hari = (now - state.last_anomaly_at).total_seconds() / 86400
            if hari > 0:
                bobot *= 0.5 ** (hari / ANOMALY_HALFLIFE_DAYS)

        if bobot >= ANOMALY_MIN_WEIGHT:
            out.append(Signal(
                name="repeated_anomaly_at_anchor",
                weight=int(round(bobot)),
                reason=(
                    f"Lokasi ini {state.anomaly_attempts} kali menjadi sasaran "
                    f"pemindaian yang ditolak dalam waktu dekat"
                ),
            ))

    return out


def evaluate(
    parsed,
    state: Optional[AnchorState] = None,
    nmid_matches_anchor: bool = False,
    anchor_has_owner: bool = False,
    now: Optional[datetime] = None,
    accuracy_m: Optional[float] = None,
    has_coords: bool = False,
    integrity=None,
    dynamic_history=None,
    bill_history=None,
    printed=None,
    ambient_ap=None,
    known_ap=None,
    area=None,
    other_names=None,
    issuer_profile=None,
    feature_corpus=None,
) -> BehaviorResult:
    """Nilai perilaku satu pemindaian.

    parsed               QrisPayload hasil emvco.parse()
    state                agregat jangkar yang cocok, kalau ada
    nmid_matches_anchor  True bila NMID yang dipindai adalah pemilik sah
                         jangkar ini (mematikan sinyal yang bisa
                         disalahgunakan untuk menyerang merchant jujur)
    accuracy_m           akurasi yang DIKLAIM klien, tidak dipercaya
    has_coords           True bila permintaan memang menyertakan koordinat
    printed              teks yang terbaca di stiker fisik, kalau ada
    integrity            laporan integritas dari klien native, kalau ada
    dynamic_history      jejak pemakaian QR dinamis ini, kalau ada
    bill_history         nominal lain untuk nomor tagihan yang sama
    area                 (kota, nmid_setuju, nmid_total) wilayah ini
    other_names          nama merchant lain yang pernah dipakai NMID ini
    issuer_profile       dialek dominan penerbit payload ini
    """
    now = now or datetime.now(timezone.utc)

    signals = (_structural_signals(parsed)
               + _location_claim_signals(accuracy_m, has_coords)
               + _printed_signals(parsed, printed)
               + _ap_signals(ambient_ap, known_ap)
               + _device_signals(integrity)
               + _dynamic_qr_signals(parsed, dynamic_history, bill_history)
               + _origin_signals(parsed, area, other_names)
               + _dialect_signals(parsed, issuer_profile)
               + _rarity_signals(parsed, feature_corpus)
               + _behavioral_signals(state, nmid_matches_anchor, now,
                                     anchor_has_owner))

    # Sidik jari encoding dibatasi bersama-sama: sekumpulan sinyal lemah
    # tidak boleh menumpuk sampai setara satu bukti kuat.
    soft = [s for s in signals if not s.hard
            and s.name.startswith("noncanonical")]
    soft_total = min(SOFT_FINGERPRINT_CAP, sum(s.weight for s in soft))
    lain = [s for s in signals if s not in soft]

    score = min(100, soft_total + sum(s.weight for s in lain))

    return BehaviorResult(
        score=score,
        signals=[s.name for s in signals],
        reasons=[s.reason for s in signals],
        weights=[s.weight for s in signals],
        hard_violation=any(s.hard for s in signals),
    )
