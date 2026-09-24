"""
API Q-Shield.

Endpoint utama POST /api/v1/verify menerima payload QRIS mentah
beserta koordinat, lalu mengembalikan verdict dengan alasan yang
bisa dibaca manusia.
"""

import json
import os
import time
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import audit
from . import auth
from . import config
from . import behavior as bh
from . import binding as bd
from . import emvco
from . import geo
from . import ticket as tk
from . import transfer as tf
from .limits import RateLimiter
from .store import Store

app = FastAPI(title="Q-Shield API", version="0.1.0")

# --- Batas permukaan serangan --------------------------------------
#
# Payload QRIS adalah untrusted input, dan ukurannya yang membuatnya
# berbahaya. Diukur: QR demo 148-158 karakter; QR yang dimuati semaksimal
# mungkin tapi masih sah 503. Batas 1024 memberi kelonggaran dua kali
# lipat sambil menolak sampah sebelum sempat menyentuh parser — tanpa
# batas ini, payload 16 MB menghabiskan ~1,9 detik CPU sebelum ditolak.
MAX_PAYLOAD_CHARS = 1024

# Badan permintaan dipotong lebih awal lagi, di lapisan HTTP, supaya
# CPU tidak terpakai hanya untuk membaca sesuatu yang pasti ditolak.
MAX_BODY_BYTES = 8 * 1024

# Akurasi di atas ini bukan lagi galat GPS, melainkan data ngawur.
MAX_ACCURACY_M = 100_000

# Origin dibatasi lewat env supaya demo lokal tetap gampang tanpa
# menyisakan allow_origins=["*"] di kode.
ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get(
        "QSHIELD_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

limiter = RateLimiter()
clients = auth.ClientRegistry()
store = Store(os.environ.get("QSHIELD_DB", "qshield.db"))

# Sakelar yang dipasang untuk gladi bersih lalu lupa dicabut adalah cara
# paling umum sebuah sistem berangkat ke produksi dalam keadaan terbuka.
# Karena itu setiap lapis yang sedang mati diteriakkan saat start, bukan
# didiamkan.
for _tingkat, _pesan in config.warnings():
    if _tingkat == "BAHAYA":
        audit.get_logger().warning(
            json.dumps({"event": "config_warning", "level": _tingkat,
                        "message": _pesan}, ensure_ascii=False))

VERIFY_PATH = "/api/v1/verify"

# Endpoint yang boleh diakses tanpa kunci. SEMUA jalur /api/ lain
# dilindungi — daftar putih, bukan daftar hitam. Endpoint baru yang
# lupa didaftarkan jadi tertutup, bukan terbuka; kebalikannya adalah
# cara paling umum sebuah API bocor saat berkembang.
JALUR_TERBUKA = {"/api/v1/health"}


def _butuh_kunci(path: str) -> bool:
    return path.startswith("/api/") and path not in JALUR_TERBUKA


# Middleware terdaftar dari yang PALING DALAM ke yang paling luar:
# Starlette menjalankan yang terakhir didaftarkan lebih dulu. Urutan
# eksekusinya jadi:
#
#   header_keamanan      pasang header di SEMUA respons, termasuk 401/429
#   batasi_ukuran_badan  buang yang kebesaran sebelum apa pun membacanya
#   autentikasi          tetapkan siapa kliennya
#   batasi_laju          kuota dihitung PER KLIEN, memakai hasil di atas
#   handler
#
# Autentikasi sengaja di luar pembatas laju: tanpa itu kuota terpaksa
# dikunci ke alamat IP, dan di balik NAT satu alamat mewakili seluruh
# ruangan (batasan R8).


@app.middleware("http")
async def batasi_laju(request: Request, call_next):
    """Jendela geser. Dikunci per klien kalau autentikasi aktif."""
    if _butuh_kunci(request.url.path):
        client_id = getattr(request.state, "client_id", None)
        if client_id:
            kunci = f"client:{client_id}"
        else:
            alamat = request.client.host if request.client else ""
            kunci = limiter.key_for(alamat)

        izin, sisa, reset = limiter.check(kunci)
        if not izin:
            audit.record_rejected("rate_limited", f"reset dalam {reset:.0f}s")
            return JSONResponse(
                status_code=429,
                content={"detail": "Terlalu banyak permintaan"},
                headers={
                    "Retry-After": str(int(reset) + 1),
                    "X-RateLimit-Limit": str(limiter.max_requests),
                    "X-RateLimit-Remaining": "0",
                },
            )
        respons = await call_next(request)
        respons.headers["X-RateLimit-Limit"] = str(limiter.max_requests)
        respons.headers["X-RateLimit-Remaining"] = str(sisa)
        return respons
    return await call_next(request)


@app.middleware("http")
async def autentikasi(request: Request, call_next):
    """Hanya PJP terdaftar yang boleh meminta putusan.

    Gagal TERTUTUP: kalau tidak ada kunci terkonfigurasi dan autentikasi
    tidak dimatikan secara eksplisit, permintaan ditolak. Ketiadaan
    konfigurasi bukan izin — logika yang sama dengan invarian §2.
    """
    request.state.client_id = None

    if not _butuh_kunci(request.url.path):
        return await call_next(request)

    if clients.disabled:
        # Dimatikan secara sadar, bukan karena lupa dikonfigurasi.
        request.state.client_id = "anonymous"
        return await call_next(request)

    if not clients.configured:
        audit.record_rejected("auth_not_configured")
        return JSONResponse(
            status_code=503,
            content={"detail": "Autentikasi belum dikonfigurasi di server"},
        )

    disodorkan = request.headers.get(auth.API_KEY_HEADER, "")
    client_id = clients.authenticate(disodorkan)
    if not client_id:
        # Alasannya sengaja tidak dibedakan antara "tidak ada kunci" dan
        # "kunci salah", dan kuncinya sendiri tidak pernah ikut dicatat.
        audit.record_rejected("auth_failed")
        return JSONResponse(
            status_code=401,
            content={"detail": "Kunci API tidak valid atau tidak disertakan"},
            headers={"WWW-Authenticate": auth.API_KEY_HEADER},
        )

    request.state.client_id = client_id
    return await call_next(request)


@app.middleware("http")
async def batasi_ukuran_badan(request: Request, call_next):
    """Tolak badan permintaan kebesaran sebelum dibaca."""
    panjang = request.headers.get("content-length")
    if panjang and panjang.isdigit() and int(panjang) > MAX_BODY_BYTES:
        audit.record_rejected("body_too_large", f"{panjang} bytes")
        return JSONResponse(
            status_code=413,
            content={"detail": "Badan permintaan terlalu besar"},
        )
    return await call_next(request)


@app.middleware("http")
async def header_keamanan(request: Request, call_next):
    respons = await call_next(request)
    respons.headers["X-Content-Type-Options"] = "nosniff"
    respons.headers["X-Frame-Options"] = "DENY"
    respons.headers["Referrer-Policy"] = "no-referrer"
    respons.headers["Cache-Control"] = "no-store"
    return respons


class DeviceIntegrity(BaseModel):
    """Laporan integritas dari klien NATIVE.

    Browser sengaja tidak membocorkan hal-hal ini ke halaman web, jadi
    klien web akan selalu mengosongkannya. Itu bukan kekurangan yang
    disembunyikan — ketiadaannya diungkapkan di tanggapan.

    Rantai kepercayaannya: Q-Shield TIDAK bisa memverifikasi field ini.
    Yang membuatnya berarti adalah `attested` — hasil Play Integrity
    (Android) atau App Attest (iOS) yang diverifikasi PJP di sisi
    mereka, lalu dipertanggungkan lewat kunci API mereka. Kami tidak
    memercayai perangkatnya; kami memercayai PJP yang menyatakan sudah
    memeriksanya.
    """

    mock_location: Optional[bool] = Field(
        None, description="OS melaporkan lokasi berasal dari mock provider")
    rooted: Optional[bool] = Field(
        None, description="perangkat di-root / jailbreak")
    attested: Optional[bool] = Field(
        None, description="Play Integrity / App Attest lolos")
    platform: Optional[Literal["android", "ios", "web", "other"]] = None


class PrintedLabel(BaseModel):
    """Teks yang TERCETAK di stiker fisik, di samping kodenya.

    Stiker QRIS resmi mencetak nama merchant dan NMID dalam huruf yang
    bisa dibaca manusia. Penipu jarang mencetak ulang seluruh standee —
    yang paling sering adalah menempel stiker QR kecil menutupi area
    kodenya saja, meninggalkan teks asli tetap terlihat.

    Diisi dari yang diketik pengguna, atau dari OCR bila klien punya.
    Ketiadaannya tidak dihukum: stiker yang teksnya tidak terbaca bukan
    kesalahan siapa pun.
    """

    nmid: Optional[str] = Field(
        None, max_length=32, pattern=r"^[A-Za-z0-9]*$",
        description="NMID yang tercetak di stiker")
    merchant_name: Optional[str] = Field(
        None, max_length=99,
        description="nama merchant yang tercetak di stiker")


class AmbientWifi(BaseModel):
    """Sidik jari WiFi sekitar, diisi klien NATIVE.

    Daftar titik akses di sekeliling adalah penanda tempat yang jauh
    lebih tajam daripada GPS: bekerja di dalam gedung, dan memisahkan
    dua lapak berdempetan yang koordinatnya tidak bisa dibedakan.

    Browser sengaja tidak menyediakan API-nya — justru karena setajam
    itu — sehingga klien web akan selalu mengosongkannya.

    **Klien yang melakukan hashing.** BSSID mentah tidak boleh dikirim.
    Pakai SHA-256 atas BSSID yang dinormalisasi huruf kecil, lalu ambil
    32 karakter pertama. Server tidak pernah melihat alamat aslinya.
    """

    ap_hashes: list = Field(
        default_factory=list, max_length=64,
        description="hash titik akses sekitar; BSSID mentah ditolak")


class VerifyRequest(BaseModel):
    """Seluruh field divalidasi di batas sistem, bukan di dalam logika.

    Payload QRIS datang dari kamera dan bisa berisi apa saja; polanya
    dibatasi ke ASCII yang bisa dicetak supaya null byte dan karakter
    kendali tidak pernah sampai ke parser maupun ke basis data.
    """

    payload: str = Field(
        ..., min_length=8, max_length=MAX_PAYLOAD_CHARS,
        pattern=r"^[\x20-\x7E]+$",
        description="String QRIS mentah hasil scan",
    )
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    device_anon_id: str = Field(
        ..., min_length=8, max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Pengenal acak per perangkat, bukan identitas pengguna",
    )
    # WAJIB, bukan opsional. Menjadikannya opsional membuka pintu keluar
    # dari invarian §6: penyerang yang akurasinya buruk tinggal tidak
    # mengirimkannya, dan pemeriksaan ">100 m" tidak pernah berjalan.
    #
    # Tanpa tahu seberapa bagus fix-nya, jangkar tidak bisa dinilai sama
    # sekali — jadi ini bukan sinyal risiko melainkan syarat masuk.
    # Geolocation API browser selalu memberikan coords.accuracy bersama
    # koordinatnya, jadi klien mana pun sudah memegangnya.
    accuracy_m: float = Field(..., ge=0, le=MAX_ACCURACY_M)

    # Jalur cadangan demo. GPS di dalam gedung kerap melaporkan akurasi
    # >100 m, dan invarian §6 akan menolak memberi putusan — sistemnya
    # benar, tapi demonya mati. Mode ini memutar ulang koordinat yang
    # direkam di luar gedung.
    #
    # Penandanya ada di PERMINTAAN dan ikut keluar di TANGGAPAN, dan
    # tidak mengubah penilaian sedikit pun. Kejujurannya disengaja:
    # replay yang disamarkan seolah live adalah kebohongan kecil yang
    # akan dicium juri, dan mengakuinya justru menguatkan — penolakan
    # memberi putusan saat sinyal buruk memang fitur, bukan bug.
    location_source: Literal["live", "replay"] = Field(
        "live", description="'replay' bila koordinat berasal dari rekaman")

    # Pemindaian dari GAMBAR, bukan dari stiker di depan mata.
    #
    # Kasusnya sehari-hari dan bukan sudut sempit: seseorang memfoto QR
    # di warung, mengirimkannya lewat pesan, dan orang lain yang
    # membayar dari tempat yang sama sekali berbeda. Koordinat pembayar
    # NYATA — GPS-nya tidak berbohong — tapi tidak mengatakan apa pun
    # tentang di mana stiker itu berada. Itu sebabnya field ini terpisah
    # dari `location_source`: bukan soal dari mana koordinatnya berasal,
    # melainkan soal APA yang diwakilinya.
    #
    # Akibatnya dua, dan keduanya perlu:
    #
    #   1. Layer 1 tidak dijalankan. Menilai jangkar dengan koordinat
    #      pembayar akan menuduh pedagang yang sah — persis yang terjadi
    #      hari ini: pemindaian dari jauh menghasilkan `step_up` pada
    #      warung yang tidak bersalah sama sekali.
    #
    #   2. Tidak ada yang dipelajari tentang TEMPAT. Tanpa ini tiap
    #      pembayaran jarak jauh menanam jangkar hantu di rumah pembayar,
    #      dan tiap jangkar hantu berjarak >1 km menambah
    #      `nmid_second_location` +25 PERMANEN ke merchant yang sah.
    #      Di skala PJP itu merusak korpus secara sistematis.
    #
    # Pengetahuan tingkat PAYLOAD tetap dipelajari — dialek penerbit dan
    # kelangkaan ciri tidak berubah karena difoto.
    #
    # Field ini diisi klien, dan klien bisa berbohong. Aman karena hanya
    # bisa MENGETATKAN: menyalakannya membuang verifikasi penempatan,
    # tidak pernah menerbitkannya. Prinsip yang sama dengan nama
    # merchant — nilai yang dikendalikan penyerang boleh mengetatkan,
    # tidak pernah melonggarkan.
    from_image: bool = Field(
        False,
        description="true bila payload dibaca dari gambar/galeri, "
                    "sehingga koordinat pemindai tidak mewakili lokasi QR")

    device_integrity: Optional[DeviceIntegrity] = Field(
        None, description="diisi klien native; klien web mengosongkannya")

    printed_label: Optional[PrintedLabel] = Field(
        None, description="teks yang terbaca di stiker fisik")

    ambient_wifi: Optional[AmbientWifi] = Field(
        None, description="sidik jari WiFi sekitar; hanya klien native")

    # Bedah TLV untuk panel forensik. OPT-IN dengan sengaja: hasilnya
    # beberapa kali lipat ukuran tanggapan normal, dan hanya mode demo
    # yang memerlukannya. Memaksakannya ke setiap panggilan PJP berarti
    # membebani jalur panas demi fitur yang tidak mereka pakai.
    #
    # Tidak ada paparan baru: seluruh isinya turunan dari `payload`,
    # yang WAJIB dikirim pemanggil — jadi ia hanya menguraikan sesuatu
    # yang sudah dipegang pemanggil itu sendiri. Berbeda dengan jejak
    # audit, yang soal PENYIMPANAN dan tetap menolak payload mentah.
    include_tlv: bool = Field(
        False, description="sertakan bedah TLV di tanggapan (mode demo)")


class MerchantOut(BaseModel):
    nmid: Optional[str]
    name: Optional[str]
    city: Optional[str]
    criteria: Optional[str]
    is_static: bool


class AttributionOut(BaseModel):
    """Apa yang Q-Shield KETAHUI tentang sebuah Merchant ID.

    Dipisahkan tegas dari `MerchantOut`, dan bedanya menentukan:
    `MerchantOut` mengutip apa yang TERTULIS di payload — nama dan kota
    yang bisa diketik siapa saja saat mendaftar. `AttributionOut`
    melaporkan apa yang sudah PERNAH DIAMATI atas Merchant ID itu.
    Nama di QR bisa dikarang; riwayat pengamatan tidak bisa.

    Gunanya di pembayaran jarak jauh. Ketika seseorang memfoto QR lalu
    mengirimkannya lewat pesan, pembayar tidak berada di tempat itu dan
    penempatan stiker MUSTAHIL diverifikasi dari sisinya. Yang masih bisa
    diberikan: apakah Merchant ID ini dikenal, dengan nama apa, di kota
    mana. Pembayar mencocokkannya sendiri dengan yang ia ketahui —
    keputusan diserahkan ke manusia, bukan diklaim sistem.

    Sengaja TIDAK memuat koordinat. Kota adalah resolusi paling halus
    yang boleh keluar dari sini; titik persis lapak seorang pedagang
    bukan milik siapa pun yang kebetulan memegang payload-nya
    (invarian §8).

    Sengaja TIDAK memuat putusan maupun aksi. Mengenali Merchant ID
    bukan verifikasi penempatan, dan menyajikannya sebagai tier akan
    persis menjadi kebohongan yang dihindari endpoint ini.

    Sengaja TIDAK memuat field kecurigaan apa pun — tidak ada "pernah
    ditandai", tidak ada hitungan percobaan. Dua alasan, keduanya sudah
    pernah menggigit kami. `anomaly_attempts` menempel pada JANGKAR,
    jadi nilainya tinggi justru pada pedagang yang DISERANG: melaporkannya
    akan menuduh korban. Dan catatan penantang di `anchor_challenge`
    ikut terisi oleh tetangga yang sah — pelajaran R11. Endpoint ini
    melaporkan pengenalan, bukan kecurigaan.
    """

    known: bool = Field(..., description="Merchant ID ini pernah diamati")
    names: list = Field([], description="nama yang pernah dipakai NMID ini")
    city: Optional[str] = Field(None, description="kota, bukan koordinat")
    observer_count: int = Field(0, description="total pengamat di semua lokasi")
    locations: int = Field(0, description="berapa tempat NMID ini teramati")
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    registered: bool = Field(False, description="didaftarkan PJP")
    name_matches: Optional[bool] = Field(
        None,
        description="nama di payload sama dengan yang pernah diamati; "
                    "null kalau belum ada pembanding")


class EvidenceOut(BaseModel):
    """Di atas APA putusan ini berdiri.

    `verdict` menjawab "boleh dibayar atau tidak". Field ini menjawab
    pertanyaan yang berbeda dan sama pentingnya: **seberapa mahal
    memalsukan dasar putusan itu.**

    Sebelum ini keduanya tidak bisa dibedakan dari luar. "verified" yang
    berdiri di atas tiga pemindaian anonim terbaca sama persis dengan
    yang berdiri di atas lima puluh pemindaian yang dijamin PJP —
    padahal yang pertama bisa dibuat siapa saja dengan tiga string
    karangan dan kesabaran 24 jam (R22).

    `vouched_observers` adalah angka yang TIDAK bisa ditumbuhkan
    penyerang: ia menghitung pengamat yang atestasi perangkatnya
    diperiksa penyelenggara lalu dipertanggungkan lewat kunci API
    mereka. `observers` bisa.

    Pengungkapan, bukan skor. Tidak satu pun field di sini menyentuh
    penilaian — PJP yang memutuskan kebijakannya sendiri di atas angka
    ini, dan auditor bisa melihat dasar tiap putusan.
    """

    observers: int = Field(0, description="pengamat berbeda di jangkar ini")
    vouched_observers: int = Field(
        0, description="di antaranya yang dijamin penyelenggara")
    registered: bool = Field(False, description="didaftarkan PJP di titik ini")
    established: bool = Field(
        False, description="sudah melewati ambang konsensus dan umur")
    span_hours: float = Field(
        0.0, description="rentang pengamatan pertama ke terakhir")


class FeeOut(BaseModel):
    """Biaya di luar nominal yang DIMINTA payload — tag 55, 56, 57.

    PENGUNGKAPAN, BUKAN SKOR. Tidak satu pun field di sini menyentuh
    penilaian: `behavior.py` tidak membacanya, dan tidak ada sinyal yang
    lahir darinya. Alasannya disebut terus terang — kami belum
    memverifikasi apakah biaya layanan pada QR STATIS itu kontradiksi
    terhadap spec QRIS atau justru sah, dan menghukum yang ternyata sah
    dengan bobot struktural berarti memaksa `anomaly` pada payload yang
    benar. Itu persis kelas positif palsu yang membuat Keputusan 13
    membuang sebuah sinyal.

    Yang dilakukan sebagai gantinya: ditampilkan apa adanya, supaya
    pengguna dan auditor bisa melihat bahwa stiker ini meminta biaya
    tambahan SEBELUM PIN dimasukkan. Pola yang sama dengan
    `location_source` dan `device_integrity` — pengungkapan, bukan skor.
    """

    indicator: Optional[str] = None   # tag 55 mentah
    label: Optional[str] = None       # artinya, untuk dibaca manusia
    fixed: Optional[str] = None       # tag 56
    percent: Optional[str] = None     # tag 57
    present: bool = False             # ada salah satu dari ketiganya


class TlvOut(BaseModel):
    """Satu entri bedah TLV. FORENSIK, BUKAN PENILAIAN.

    Tidak satu pun field di sini dibaca `binding.py` maupun
    `behavior.py`. Ia menjawab "apa yang sistem baca sehingga
    memutuskan begini" — pertanyaan sesudah putusan, bukan masukan
    baginya.
    """

    tag: str
    length: int
    value: str
    label: str
    children: list["TlvOut"] = []


TlvOut.model_rebuild()


class LayerScores(BaseModel):
    """Rincian per layer.

    Dipisah supaya auditor bisa melihat sumbangan tiap layer, bukan cuma
    angka gabungan — dan supaya jelas Layer 2 melengkapi, bukan
    menggantikan, putusan Layer 1.
    """

    location: int      # Layer 1 — ikatan merchant-lokasi
    behavior: int      # Layer 2 — perilaku artefak QR


class VerifyResponse(BaseModel):
    verdict: str
    action: str
    risk_score: int
    reasons: list
    signals: list
    layers: LayerScores
    merchant: MerchantOut
    # Diisi HANYA pada pemindaian dari gambar. Di pemindaian biasa
    # jawabannya sudah ada di `verdict`: penempatan memang terverifikasi,
    # dan atribusi tidak menambah apa-apa selain dua kueri.
    known: Optional[AttributionOut] = None
    # Di atas apa putusan ini berdiri. Null pada jalur yang memang tidak
    # menilai jangkar — GPS palsu, akurasi buruk, pemindaian dari gambar.
    evidence: Optional[EvidenceOut] = None
    fees: FeeOut
    # Putusan ini, ditandatangani dan diikat ke sidik jari payload yang
    # diperiksa. MENGIKAT, bukan memaksa: ia mencegah putusan dipindah
    # ke QR lain, TIDAK mencegah PJP mengabaikannya. Lihat ticket.py.
    verification_ticket: str
    ticket_expires_in: int
    # Kosong kecuali permintaan menyetel include_tlv. Field-nya SELALU
    # ada supaya bentuk tanggapan tidak berubah-ubah antar panggilan.
    tlv: list = []
    location_source: str
    # Pengungkapan, bukan skor: "not_provided" berarti pemeriksaan
    # integritas TIDAK PERNAH DIJALANKAN — bukan dijalankan lalu lolos.
    device_integrity: str
    processing_ms: float


REPLAY_NOTICE = ("Koordinat diputar ulang dari rekaman lokasi — bukan GPS "
                 "langsung. Penilaian berjalan apa adanya.")

IMAGE_NOTICE = ("Dipindai dari gambar — penempatan stiker TIDAK dapat "
                "diverifikasi dari sini. Yang diperiksa hanya bentuk "
                "payload dan riwayat Merchant ID-nya.")

MOCK_NOTICE = ("Sistem operasi melaporkan lokasi ini berasal dari mock "
               "provider — jangkar tidak dapat dinilai")


def _bahan_tiket(client_id: Optional[str]) -> str:
    """Bahan rahasia untuk menandatangani tiket permintaan ini.

    Kunci PJP kalau ada; kalau autentikasi dimatikan, rahasia server
    yang tersimpan. Yang kedua tidak bisa diverifikasi PJP mana pun —
    dan memang tidak perlu, karena di mode itu tidak ada PJP.
    """
    bahan = clients.secret_material(client_id) if client_id else None
    return bahan or store.ticket_secret()


def _bedah(parsed, diminta: bool) -> list:
    """Bedah TLV, hanya kalau diminta. Tidak menilai apa pun."""
    if not diminta:
        return []
    return [TlvOut(**e) for e in parsed.breakdown()]


def _bukti(binding) -> EvidenceOut:
    """Di atas apa putusan ini berdiri. Pengungkapan, bukan skor."""
    if binding is None:
        return EvidenceOut()
    return EvidenceOut(
        observers=binding.observer_count,
        vouched_observers=binding.vouched_count,
        registered=binding.is_registered,
        established=binding.is_established,
        span_hours=round(binding.age_hours, 1),
    )


def _atribusi(nmid: str, parsed) -> AttributionOut:
    """Apa yang sudah kita amati tentang Merchant ID ini.

    Tidak membaca koordinat pemindai sama sekali — inilah yang membuatnya
    sah dipakai ketika pemindainya jauh dari merchant.
    """
    bindings = store.by_nmid(nmid)
    if not bindings:
        return AttributionOut(known=False)

    nama = sorted({n for n in store.names_for_nmid(nmid) if n})

    # Kota disimpulkan dari pengetahuan WILAYAH, bukan dibaca dari
    # payload: yang tertulis di QR justru bagian yang bisa dikarang.
    kota = None
    for b in bindings:
        hasil = store.area_city(b.lat, b.lng)
        if hasil:
            kota = hasil[0]
            break

    awal = [b.first_seen for b in bindings if b.first_seen]
    akhir = [b.last_seen for b in bindings if b.last_seen]

    cocok = None
    if nama and parsed.merchant_name:
        kanonik = bd.nama_kanonik(parsed.merchant_name)
        cocok = any(kanonik == bd.nama_kanonik(n) for n in nama)

    return AttributionOut(
        known=True,
        names=nama,
        city=kota,
        observer_count=sum(b.observer_count for b in bindings),
        locations=len(bindings),
        first_seen=min(awal).isoformat() if awal else None,
        last_seen=max(akhir).isoformat() if akhir else None,
        registered=any(b.is_registered for b in bindings),
        name_matches=cocok,
    )


def _biaya(parsed) -> FeeOut:
    """Ringkas tag 55/56/57 jadi satu objek. Tidak menilai apa pun."""
    return FeeOut(
        indicator=parsed.tip_indicator,
        label=parsed.tip_label,
        fixed=parsed.fee_fixed,
        percent=parsed.fee_percent,
        present=parsed.has_fee,
    )


def _status_integritas(di) -> str:
    """Ringkas laporan integritas jadi satu kata untuk tanggapan."""
    if di is None:
        return "not_provided"
    if di.mock_location is True or di.rooted is True or di.attested is False:
        return "failed"
    if di.attested is True:
        return "attested"
    return "reported"


def _tandai_replay(verdict, req):
    """Sisipkan penanda replay di paling depan daftar alasan."""
    if req.location_source == "replay":
        verdict.reasons = [REPLAY_NOTICE] + list(verdict.reasons)
        verdict.signals = list(verdict.signals) + ["replayed_location"]
    return verdict


# Frontend disajikan dari proses yang sama, bukan dari dev server
# terpisah. Dua alasan, keduanya soal hari-H: satu origin berarti tidak
# ada urusan CORS sama sekali, dan satu proses berarti satu hal yang
# bisa mati, bukan dua.
WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


@app.get("/", include_in_schema=False)
def scanner():
    return FileResponse(os.path.join(WEB, "index.html"),
                        media_type="text/html")


@app.get("/api/v1/health")
def health():
    return {"status": "ok", **store.stats()}


# --- Survei kalibrasi lapangan -------------------------------------
#
# Mode ini sengaja MELANGGAR model privasi sistem: ia menyimpan payload
# mentah dan koordinat presisi ke berkas. Itu memang yang dibutuhkan
# untuk menurunkan ulang parameter dari data nyata — dan itu juga
# alasan ia harus mustahil menyala tanpa sengaja.
#
# Tiga pagar:
#   1. mati kecuali QSHIELD_FIELD_MODE=on disetel eksplisit
#   2. tetap menuntut kunci API seperti endpoint lain
#   3. diteriakkan sebagai BAHAYA oleh config.warnings() saat start
#
# Datanya masuk berkas terpisah, tidak pernah ke basis data produksi.
FIELD_MODE = os.environ.get("QSHIELD_FIELD_MODE", "").strip().lower() == "on"
FIELD_FILE = os.environ.get("QSHIELD_FIELD_FILE", "fielddata.jsonl")


class FieldSample(BaseModel):
    payload: str = Field(..., min_length=8, max_length=MAX_PAYLOAD_CHARS,
                         pattern=r"^[\x20-\x7E]+$")
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    accuracy_m: float = Field(..., ge=0, le=MAX_ACCURACY_M)
    # Label yang diketik surveyor: nama tempat, atau penanda bahwa ini
    # pemindaian berulang di titik yang sama. Inilah kebenaran dasar
    # yang membuat datanya bisa dipakai mengkalibrasi.
    label: str = Field(..., min_length=1, max_length=64,
                       pattern=r"^[A-Za-z0-9 _.-]+$")
    note: Optional[str] = Field(None, max_length=200)


@app.post("/api/v1/field", status_code=201)
def survei(sample: FieldSample, request: Request, response: Response):
    if not FIELD_MODE:
        response.status_code = 404
        return {"detail": "Mode survei tidak aktif"}

    baris = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "surveyor": getattr(request.state, "client_id", None) or "anonymous",
        "payload": sample.payload,
        "lat": sample.lat, "lng": sample.lng,
        "accuracy_m": sample.accuracy_m,
        "label": sample.label,
        "note": sample.note,
    }
    with open(FIELD_FILE, "a") as f:
        f.write(json.dumps(baris, ensure_ascii=False) + "\n")

    jumlah = sum(1 for _ in open(FIELD_FILE))
    return {"ok": True, "tersimpan": jumlah, "label": sample.label}


class TransferTelemetryIn(BaseModel):
    """Telemetri yang hanya PJP bisa isi.

    Seluruhnya opsional, dan ketiadaannya TIDAK dihukum — pola yang sama
    dengan device_integrity, dan alasan yang sama. Yang dilakukan
    sebagai gantinya: ketiadaannya diungkapkan di tanggapan.
    """

    first_time_beneficiary: Optional[bool] = Field(
        None, description="pembayar belum pernah mengirim ke rekening ini")
    beneficiary_account_age_days: Optional[int] = Field(
        None, ge=0, le=36500, description="umur rekening tujuan, hari")
    call_active: Optional[bool] = Field(
        None, description="pembayar sedang menelepon saat transfer")
    transfers_last_hour: Optional[int] = Field(
        None, ge=0, le=10000, description="transfer dalam 60 menit terakhir")


class AssessTransferRequest(BaseModel):
    """Rencana transfer bank manual yang hendak dinilai.

    Tidak ada payload, tidak ada koordinat — transfer manual tidak punya
    artefak fisik yang bisa diperiksa. Yang dinilai adalah bentuk
    transaksinya dan reputasi rekening tujuannya.

    Identitas PEMBAYAR tidak diminta dan tidak akan diterima.
    """

    beneficiary_account: str = Field(
        ..., min_length=4, max_length=34, pattern=r"^[A-Za-z0-9]+$",
        description="nomor rekening tujuan; disimpan sebagai hash saja")
    amount: Optional[float] = Field(None, ge=0)
    telemetry: Optional[TransferTelemetryIn] = None


class AssessTransferResponse(BaseModel):
    action: str
    risk_score: int
    reasons: list
    signals: list
    telemetry: str
    processing_ms: float


@app.post("/api/v1/assess-transfer", response_model=AssessTransferResponse)
def nilai_transfer(req: AssessTransferRequest, request: Request):
    """Layer 2 pada jalur transfer manual.

    Jalur QRIS punya artefak yang bisa diperiksa. Jalur ini tidak —
    korban mengetik nomor rekening yang didiktekan seseorang di telepon.
    Yang tersisa untuk dinilai adalah bentuk transaksinya, dan apa yang
    diketahui lapisan bersama tentang rekening tujuannya.
    """
    started = time.perf_counter()
    client_id = getattr(request.state, "client_id", None)

    t = req.telemetry
    telemetri = tf.TransferTelemetry(
        first_time_beneficiary=t.first_time_beneficiary if t else None,
        beneficiary_account_age_days=(
            t.beneficiary_account_age_days if t else None),
        call_active=t.call_active if t else None,
        transfers_last_hour=t.transfers_last_hour if t else None,
    )
    riwayat = store.beneficiary_history(req.beneficiary_account)
    v = tf.evaluate(telemetri, riwayat)

    elapsed = round((time.perf_counter() - started) * 1000, 2)
    audit.get_logger().info(json.dumps({
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": "assess_transfer",
        "client": client_id,
        # Nomor rekeningnya TIDAK dicatat — hanya hash-nya, dan itu pun
        # dipotong. Cukup untuk menelusuri putusan, tidak cukup untuk
        # memulihkan nomornya.
        "beneficiary": store.account_hash(req.beneficiary_account)[:16],
        "action": v.action,
        "risk_score": v.risk_score,
        "signals": v.signals,
        "telemetry": v.telemetry_status,
        "processing_ms": elapsed,
    }, ensure_ascii=False))

    return AssessTransferResponse(
        action=v.action, risk_score=v.risk_score, reasons=v.reasons,
        signals=v.signals, telemetry=v.telemetry_status,
        processing_ms=elapsed)


class ReportBeneficiaryRequest(BaseModel):
    beneficiary_account: str = Field(
        ..., min_length=4, max_length=34, pattern=r"^[A-Za-z0-9]+$")


@app.post("/api/v1/beneficiary-reports", status_code=201)
def laporkan_rekening(req: ReportBeneficiaryRequest, request: Request):
    """Laporkan rekening tujuan sebagai penerima penipuan.

    Idempoten per penyelenggara: satu PJP yang melapor seratus kali
    tetap satu suara. Bobotnya berskala dengan jumlah PENYELENGGARA yang
    melapor, bukan jumlah laporan — pola yang sama dengan invarian §5.
    """
    client_id = getattr(request.state, "client_id", None) or "anonymous"
    hasil = store.report_beneficiary(req.beneficiary_account, client_id)

    audit.get_logger().info(json.dumps({
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": "beneficiary_reported",
        "reporter": client_id,
        "beneficiary": store.account_hash(req.beneficiary_account)[:16],
        "distinct_reporters": hasil["reporters"],
    }, ensure_ascii=False))
    return {"ok": True, "reporters": hasil["reporters"]}


class RegisterRequest(BaseModel):
    """Pernyataan penyelenggara tentang ikatan merchant-lokasi.

    Yang mendaftarkan adalah PJP yang meng-onboard merchant, jadi ia
    memang mengetahui NMID mana milik siapa. Ini menutup cold start:
    merchant tidak perlu menunggu tiga pengamat selama 24 jam.

    Konsekuensinya jujur — ini jalur kepercayaan baru, dan kunci PJP
    yang bocor bisa dipakai mendaftarkan stiker palsu. Karena itu tiap
    pendaftaran dicatat beserta pendaftarnya, bisa dicabut, dan
    menghasilkan sinyal yang berbeda dari konsensus.
    """

    nmid: str = Field(..., min_length=3, max_length=32,
                      pattern=r"^[A-Za-z0-9]+$")
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    merchant_name: Optional[str] = Field(None, max_length=99)
    is_mobile: bool = Field(
        False, description="merchant keliling — ikatan lokasi tidak berlaku")


class RegisterResponse(BaseModel):
    ok: bool
    nmid: str
    registrar: Optional[str] = None
    registered_at: Optional[str] = None
    is_mobile: bool = False
    detail: Optional[str] = None


@app.post("/api/v1/merchants", response_model=RegisterResponse, status_code=201)
def daftarkan(req: RegisterRequest, request: Request, response: Response):
    client_id = getattr(request.state, "client_id", None) or "anonymous"
    hasil = store.register(
        nmid=req.nmid, registrar=client_id, lat=req.lat, lng=req.lng,
        merchant_name=req.merchant_name, is_mobile=req.is_mobile)

    if not hasil.get("ok"):
        response.status_code = 409
        audit.record_rejected("register_conflict", f"{req.nmid}:{hasil['reason']}")
        return RegisterResponse(
            ok=False, nmid=req.nmid,
            detail="NMID ini sudah didaftarkan penyelenggara lain")

    audit.get_logger().info(json.dumps({
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": "merchant_registered",
        "nmid": req.nmid,
        "registrar": client_id,
        "geohash_7": geo.encode(req.lat, req.lng, bd.INDEX_PRECISION),
        "is_mobile": req.is_mobile,
    }, ensure_ascii=False))

    return RegisterResponse(ok=True, nmid=req.nmid, registrar=client_id,
                            registered_at=hasil["registered_at"],
                            is_mobile=req.is_mobile)


@app.delete("/api/v1/merchants/{nmid}", response_model=RegisterResponse)
def cabut(nmid: str, request: Request, response: Response):
    client_id = getattr(request.state, "client_id", None) or "anonymous"
    hasil = store.revoke(nmid=nmid, registrar=client_id)

    if not hasil.get("ok"):
        response.status_code = 404 if hasil["reason"] == "tidak_terdaftar" else 403
        audit.record_rejected("revoke_denied", f"{nmid}:{hasil['reason']}")
        pesan = {"tidak_terdaftar": "NMID ini tidak terdaftar",
                 "bukan_pendaftarnya": "Hanya pendaftarnya yang boleh mencabut"}
        return RegisterResponse(ok=False, nmid=nmid,
                                detail=pesan[hasil["reason"]])

    audit.get_logger().info(json.dumps({
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": "merchant_revoked", "nmid": nmid, "registrar": client_id,
    }, ensure_ascii=False))
    return RegisterResponse(ok=True, nmid=nmid, registrar=client_id)


class TicketVerifyRequest(BaseModel):
    """Permintaan memeriksa tiket di titik eksekusi pembayaran.

    `payload` WAJIB, dan itu keputusan desain. Tanpa payload yang
    HENDAK DIBAYAR, pemeriksaan ini hanya membuktikan tiketnya asli —
    bukan bahwa ia menyangkut QR yang sedang dieksekusi. Menjadikannya
    opsional berarti menyediakan cara memakai endpoint ini yang terasa
    benar tapi tidak menutup celah apa pun, dan itu kesalahan paling
    mungkin dilakukan integrator. Ditutup secara struktural di sini.
    """

    ticket: str = Field(..., min_length=16, max_length=4096)
    payload: str = Field(
        ..., min_length=8, max_length=MAX_PAYLOAD_CHARS,
        pattern=r"^[\x20-\x7E]+$",
        description="payload QRIS yang HENDAK DIBAYAR, bukan yang diverifikasi")


class TicketVerifyResponse(BaseModel):
    valid: bool
    verdict: Optional[str] = None
    action: Optional[str] = None
    nmid: Optional[str] = None
    issued_at: Optional[str] = None
    expires_at: Optional[str] = None
    detail: Optional[str] = None


class InspectRequest(BaseModel):
    """Periksa isi satu payload. TIDAK ada lokasi, dan itu inti bedanya.

    `/verify` menjawab "apakah stiker ini sah DI SINI" — pertanyaan yang
    mustahil dijawab tanpa tahu di mana "sini". Endpoint ini menjawab
    pertanyaan yang berbeda: "payload ini isinya apa, dan bentuknya
    wajar atau tidak".

    Dipisahkan karena menggabungkannya merusak keduanya. Seseorang yang
    mengkatalogkan QRIS dari gambar sambil duduk di satu tempat akan
    membuat tempat itu tampak seperti jangkar yang berkali-kali
    diserang — dan pedagang sungguhan di sekitarnya ikut tertuduh.
    Itu bukan skenario hipotetis; itu yang terjadi.
    """

    payload: str = Field(
        ..., min_length=8, max_length=MAX_PAYLOAD_CHARS,
        pattern=r"^[\x20-\x7E]+$",
        description="string QRIS mentah; tidak ada koordinat yang diminta")
    include_tlv: bool = Field(
        False, description="sertakan bedah TLV di tanggapan")


class InspectResponse(BaseModel):
    """Hasil pemeriksaan payload.

    SENGAJA tidak memuat `action`, `verdict`, maupun tiket. Tidak ada
    putusan lokasi yang bisa diberikan tanpa lokasi, dan menerbitkan
    tiket dari sini berarti menyediakan cara memperoleh "izin" untuk
    QR yang tidak pernah diperiksa tempatnya.
    """

    merchant: MerchantOut
    known: AttributionOut
    fees: FeeOut
    structural_signals: list
    structural_reasons: list
    tlv: list = []
    processing_ms: float


@app.post("/api/v1/inspect", response_model=InspectResponse)
def inspect(req: InspectRequest, request: Request):
    """Baca satu payload QRIS. Tidak menyentuh pengetahuan lokasi.

    Yang dipelajari dari sini HANYA tingkat payload — dialek penerbit
    dan kelangkaan ciri merchant. Bentuk payload tidak berubah karena
    difoto, jadi keduanya tetap sah dipelajari; koordinat pemindainya
    tidak mengatakan apa pun tentang merchant dan memang tidak diminta.
    """
    started = time.perf_counter()
    try:
        parsed = emvco.parse(req.payload)
    except emvco.ParseError as exc:
        audit.record_rejected("parse_error", str(exc))
        raise HTTPException(status_code=422, detail=f"Payload tidak valid: {exc}")
    if not parsed.nmid:
        audit.record_rejected("nmid_missing")
        raise HTTPException(status_code=422,
                            detail="Merchant ID tidak ditemukan dalam payload")

    # has_coords=False: sinyal yang bergantung pada posisi dimatikan,
    # bukan dijalankan dengan nilai karangan.
    struktural = bh.evaluate(
        parsed, state=None, has_coords=False,
        issuer_profile=(store.dialect_profile(parsed.merchant_pan[:8])
                        if parsed.merchant_pan and len(parsed.merchant_pan) >= 8
                        else None),
        feature_corpus=store.feature_corpus(),
    )

    if parsed.crc_valid:
        store.learn_dialect(parsed, parsed.nmid)
        store.learn_features(parsed, parsed.nmid)

    elapsed = round((time.perf_counter() - started) * 1000, 2)
    return InspectResponse(
        merchant=MerchantOut(
            nmid=parsed.nmid, name=parsed.merchant_name,
            city=parsed.merchant_city, criteria=parsed.criteria_label,
            is_static=parsed.is_static),
        known=_atribusi(parsed.nmid, parsed),
        fees=_biaya(parsed),
        structural_signals=[s.name for s in struktural.signals],
        structural_reasons=[s.reason for s in struktural.signals],
        tlv=_bedah(parsed, req.include_tlv),
        processing_ms=elapsed,
    )


@app.post("/api/v1/tickets/verify", response_model=TicketVerifyResponse)
def periksa_tiket(req: TicketVerifyRequest, request: Request,
                  response: Response):
    """Periksa tiket terhadap payload yang hendak dibayar.

    Ini yang dilakukan backend PJP di titik eksekusi. Disediakan sebagai
    endpoint karena kuncinya tinggal di server — klien tidak boleh
    memegangnya — dan supaya integrator di bahasa apa pun bisa memakai
    jalur yang sama tanpa menulis ulang HMAC. Yang punya `hmac` di
    pustaka standarnya sebaiknya memeriksanya sendiri, tanpa perjalanan
    jaringan tambahan; algoritmanya ada di docs/API.md.
    """
    client_id = getattr(request.state, "client_id", None)
    try:
        klaim = tk.verify(req.ticket, _bahan_tiket(client_id),
                          payload=req.payload)
    except tk.TicketError as exc:
        # 200, bukan 4xx: "tiket tidak sah" adalah JAWABAN yang benar
        # atas pertanyaan yang sah, bukan kesalahan pemanggil. Klien
        # yang memperlakukan non-200 sebagai gangguan jaringan lalu
        # mencoba lagi tidak boleh diam-diam melewatkan penolakan.
        audit.record_rejected("ticket_invalid", str(exc))
        return TicketVerifyResponse(valid=False, detail=str(exc))

    def _waktu(detik):
        return datetime.fromtimestamp(detik, timezone.utc).isoformat()

    return TicketVerifyResponse(
        valid=True, verdict=klaim["verdict"], action=klaim["action"],
        nmid=klaim.get("nmid"), issued_at=_waktu(klaim["iat"]),
        expires_at=_waktu(klaim["exp"]))


@app.post(VERIFY_PATH, response_model=VerifyResponse)
def verify(req: VerifyRequest, request: Request):
    started = time.perf_counter()
    client_id = getattr(request.state, "client_id", None)

    try:
        parsed = emvco.parse(req.payload)
    except emvco.ParseError as exc:
        audit.record_rejected("parse_error", str(exc))
        raise HTTPException(status_code=422, detail=f"Payload tidak valid: {exc}")

    nmid = parsed.nmid
    if not nmid:
        audit.record_rejected("nmid_missing")
        raise HTTPException(
            status_code=422,
            detail="Merchant ID tidak ditemukan dalam payload",
        )

    di = req.device_integrity
    status_integritas = _status_integritas(di)

    # GPS yang DIAKUI palsu menempatkan kita di posisi yang sama persis
    # dengan akurasi buruk: jangkarnya tidak layak dinilai. Ditangani
    # dengan menolak memberi putusan lokasi, bukan dengan menambah skor —
    # perlakuan yang sama seperti invarian §6, karena masalahnya sama.
    #
    # Bedanya satu: akurasi buruk itu nasib, mock location itu sengaja.
    # Karena itu skor dasarnya lebih tinggi.
    if di is not None and di.mock_location is True:
        palsu = bd.Verdict(
            status=bd.UNKNOWN, action=bd.STEP_UP, risk_score=65,
            reasons=[MOCK_NOTICE], signals=["mock_location_reported"],
        )
        struktural = bh.evaluate(parsed, state=None,
                                 accuracy_m=req.accuracy_m, has_coords=True)
        palsu = _tandai_replay(bd.compose(palsu, struktural), req)
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        # status_integritas WAJIB ikut. Tanpanya parameternya jatuh ke
        # default "not_provided", dan jejak audit mencatat peristiwa
        # integritas PALING SERIUS yang kita punya — GPS yang diakui
        # palsu — seolah pemeriksaannya tidak pernah dijalankan.
        # Tanggapan ke klien selalu benar; yang keliru hanya jejaknya,
        # dan justru jejak itulah yang dipakai auditor merekonstruksi
        # insiden (aset A5).
        audit.record_verdict(
            palsu, nmid, req.lat, req.lng,
            {"location": 65, "behavior": struktural.score},
            elapsed, req.accuracy_m, parsed.merchant_name,
            req.location_source, client_id, status_integritas,
            tk.payload_fingerprint(req.payload),
        )
        _tiket = tk.issue(
            req.payload, palsu.status, palsu.action, nmid,
            client_id or "anonymous", _bahan_tiket(client_id))
        return VerifyResponse(
            verdict=palsu.status, action=palsu.action,
            risk_score=palsu.risk_score, reasons=palsu.reasons,
            signals=palsu.signals,
            layers=LayerScores(location=65, behavior=struktural.score),
            location_source=req.location_source,
            device_integrity=status_integritas,
            merchant=MerchantOut(
                nmid=nmid, name=parsed.merchant_name,
                city=parsed.merchant_city, criteria=parsed.criteria_label,
                is_static=parsed.is_static),
            fees=_biaya(parsed),
            tlv=_bedah(parsed, req.include_tlv),
            verification_ticket=_tiket["ticket"],
            ticket_expires_in=_tiket["expires_in"],
            processing_ms=elapsed,
        )

    # Pemindaian dari gambar. Koordinat pembayar NYATA, tapi tidak
    # mewakili tempat stiker itu berada — jadi jangkar tidak layak
    # dinilai, persis seperti invarian §6, dengan sebab yang berbeda.
    #
    # Ditempatkan SEBELUM cabang akurasi rendah dengan sengaja: kalau
    # koordinatnya memang tidak mewakili apa pun, seberapa akurat
    # koordinat itu sama sekali tidak relevan.
    if req.from_image:
        gambar = bd.Verdict(
            status=bd.UNKNOWN,
            action=bd.WARN,
            risk_score=0,
            reasons=[IMAGE_NOTICE],
            signals=["scanned_from_image"],
        )
        # has_coords=False: sinyal yang bergantung posisi dimatikan,
        # bukan dijalankan dengan nilai karangan. Struktural, dialek
        # penerbit, dan kelangkaan tetap penuh — bentuk payload tidak
        # berubah karena difoto.
        struktural = bh.evaluate(
            parsed, state=None, has_coords=False,
            issuer_profile=(store.dialect_profile(parsed.merchant_pan[:8])
                            if parsed.merchant_pan
                            and len(parsed.merchant_pan) >= 8 else None),
            feature_corpus=store.feature_corpus(),
        )
        gambar = _tandai_replay(bd.compose(gambar, struktural), req)

        # PAGAR. Tanpa Layer 1, kontradiksi struktural berhenti di skor
        # 70 — dan 70 memetakan ke `step_up`, bukan `cooling_off`. Di
        # jalur biasa sisanya disumbang Layer 1, yang di sini sengaja
        # tidak dijalankan. Akibatnya, menyalakan `from_image` akan
        # MELONGGARKAN putusan dari cooling_off jadi step_up — persis
        # tuas yang tidak boleh ada pada field yang diisi klien.
        #
        # Kontradiksi spec adalah sifat PAYLOAD. Ia tidak menjadi kurang
        # pasti karena payload-nya sampai lewat gambar, jadi tier-nya
        # tidak boleh ikut melunak. Diperbaiki secara struktural di
        # sini, bukan dengan menaikkan W_STRUCTURAL — bobot itu sudah
        # dikalibrasi terhadap 20.000 payload sah dan tidak boleh
        # digeser demi satu jalur.
        if struktural.hard_violation:
            gambar.action = bd.COOLING_OFF

        atribusi = _atribusi(nmid, parsed)

        # Atribusi masuk sebagai ALASAN, tanpa bobot. Mengenali Merchant
        # ID bukan bukti penempatan, jadi ia tidak boleh menggerakkan
        # tier ke arah mana pun — yang dilakukannya memberi pembayar
        # sesuatu yang bisa ia cocokkan sendiri.
        if atribusi.known:
            bagian = ", ".join(atribusi.names) or "tanpa nama tercatat"
            if atribusi.city:
                bagian += f" di {atribusi.city}"
            gambar.reasons.append(
                f"Merchant ID ini dikenal: {bagian} — "
                f"{atribusi.observer_count} pengamatan")
            if atribusi.name_matches is False:
                gambar.reasons.append(
                    f"Nama di QR ini ({parsed.merchant_name}) berbeda dari "
                    f"nama yang pernah diamati untuk Merchant ID tersebut")
        else:
            gambar.reasons.append(
                "Merchant ID ini belum pernah kami amati di mana pun")

        # Pengetahuan tingkat PAYLOAD tetap dipelajari; pengetahuan
        # LOKASI tidak ada satu pun yang disentuh. Tidak ada binding
        # dibuat, tidak ada kota dipelajari, tidak ada percobaan anomali
        # dicatat — jangkar hantu justru yang dicegah di sini.
        if gambar.status != bd.ANOMALY and parsed.crc_valid:
            store.learn_dialect(parsed, nmid)
            store.learn_features(parsed, nmid)

        elapsed = round((time.perf_counter() - started) * 1000, 2)
        audit.record_verdict(
            gambar, nmid, req.lat, req.lng,
            {"location": 0, "behavior": struktural.score},
            elapsed, req.accuracy_m, parsed.merchant_name,
            req.location_source, client_id, status_integritas,
            tk.payload_fingerprint(req.payload),
        )
        _tiket = tk.issue(
            req.payload, gambar.status, gambar.action, nmid,
            client_id or "anonymous", _bahan_tiket(client_id))
        return VerifyResponse(
            verdict=gambar.status, action=gambar.action,
            risk_score=gambar.risk_score, reasons=gambar.reasons,
            signals=gambar.signals,
            layers=LayerScores(location=0, behavior=struktural.score),
            location_source=req.location_source,
            device_integrity=status_integritas,
            merchant=MerchantOut(
                nmid=nmid, name=parsed.merchant_name,
                city=parsed.merchant_city, criteria=parsed.criteria_label,
                is_static=parsed.is_static),
            known=atribusi,
            fees=_biaya(parsed),
            tlv=_bedah(parsed, req.include_tlv),
            verification_ticket=_tiket["ticket"],
            ticket_expires_in=_tiket["expires_in"],
            processing_ms=elapsed,
        )

    # Akurasi GPS buruk membuat jangkar tidak dapat dipercaya, jadi
    # Layer 1 tidak dijalankan sama sekali (invarian §6).
    #
    # Sinyal STRUKTURAL Layer 2 tetap berlaku: cacat bentuk payload sama
    # sekali tidak bergantung pada GPS, dan mengabaikannya berarti
    # membuang bukti yang masih sehat. Sinyal perilaku dimatikan
    # (state=None) karena jangkarnya justru yang tidak bisa dipercaya.
    if req.accuracy_m > 100:
        low = bd.Verdict(
            status=bd.UNKNOWN,
            action=bd.WARN,
            risk_score=40,
            reasons=[
                f"Akurasi lokasi rendah ({req.accuracy_m:.0f} m) — "
                f"verifikasi lokasi tidak dapat dilakukan"
            ],
            signals=["low_gps_accuracy"],
        )
        # GPS tidak bisa dipercaya, tapi titik akses di sekitar masih
        # bisa. Inilah keadaan di dalam ruko, basement, dan lantai atas —
        # dan justru di situ koordinat paling sering menyesatkan.
        #
        # Titik akses lebih sulit dipalsukan daripada koordinat:
        # memalsukan GPS cukup satu sakelar di opsi pengembang,
        # memalsukan daftar titik akses menuntut kehadiran fisik di
        # jangkauan radio yang sama.
        #
        # Yang TIDAK dilakukan di sini: memberi proceed. Sidik jari WiFi
        # dipakai menaikkan kecurigaan dan memberi konteks, tidak pernah
        # menerbitkan kepercayaan. Invarian §6 tetap utuh — jangkar GPS
        # tetap tidak dinilai; yang dipakai saluran bukti yang berbeda.
        # location_source TIDAK disentuh di sini. Field itu digemakan dari
        # permintaan: ia menyatakan bagaimana KLIEN memperoleh posisinya,
        # bukan bagaimana server menyimpulkan tempatnya. Menimpanya
        # mengubah arti field, bukan sekadar menambah nilai — dan docs/API.md
        # sudah menyatakan `location_source` kosakata tertutup yang
        # menuntut versi baru kalau nilainya bertambah.
        #
        # Yang dipakai `signals`, yang memang daftar terbuka dan memang
        # disediakan untuk ini.
        if req.ambient_wifi and req.ambient_wifi.ap_hashes:
            cocok, irisan = store.locate_by_ap(
                req.ambient_wifi.ap_hashes, bh.AP_LOCATE_MIN_OVERLAP)
            if cocok is not None:
                if cocok.nmid == nmid:
                    low.reasons.insert(0,
                        f"Tempat ini dikenali dari {len(req.ambient_wifi.ap_hashes)} "
                        f"jaringan WiFi di sekitar ({irisan:.0%} cocok) dan "
                        f"memang tercatat atas merchant ini")
                    low.signals.append("ambient_wifi_confirms_place")
                elif cocok.is_established:
                    low.risk_score += bh.W_AP_FOREIGN_NMID
                    low.status = bd.ANOMALY
                    low.action = bd._action_for(low.risk_score)
                    low.reasons.insert(0,
                        f"Jaringan WiFi di sekitar mengenali tempat ini sebagai "
                        f"{cocok.merchant_name or cocok.nmid} ({irisan:.0%} cocok), "
                        f"tapi kode yang dipindai milik merchant lain")
                    low.signals.append("ambient_wifi_foreign_nmid")

        struktural = bh.evaluate(parsed, state=None,
                                 accuracy_m=req.accuracy_m, has_coords=True,
                                 integrity=di)
        low = _tandai_replay(bd.compose(low, struktural), req)
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        audit.record_verdict(
            low, nmid, req.lat, req.lng,
            {"location": low.risk_score, "behavior": struktural.score},
            elapsed, req.accuracy_m, parsed.merchant_name,
            req.location_source, client_id, status_integritas,
            tk.payload_fingerprint(req.payload),
        )
        _tiket = tk.issue(
            req.payload, low.status, low.action, nmid,
            client_id or "anonymous", _bahan_tiket(client_id))
        return VerifyResponse(
            verdict=low.status,
            action=low.action,
            risk_score=low.risk_score,
            reasons=low.reasons,
            signals=low.signals,
            layers=LayerScores(location=low.risk_score,
                               behavior=struktural.score),
            location_source=req.location_source,
            device_integrity=status_integritas,
            merchant=MerchantOut(
                nmid=nmid,
                name=parsed.merchant_name,
                city=parsed.merchant_city,
                criteria=parsed.criteria_label,
                is_static=parsed.is_static,
            ),
            fees=_biaya(parsed),
            tlv=_bedah(parsed, req.include_tlv),
            verification_ticket=_tiket["ticket"],
            ticket_expires_in=_tiket["expires_in"],
            processing_ms=elapsed,
        )

    # Jejak QR dinamis dicatat lebih dulu supaya pemindaian ini sendiri
    # ikut terhitung — kalau tidak, korban pertama sebuah QR yang disebar
    # tidak pernah melihat angka apa pun.
    riwayat_dinamis = riwayat_tagihan = None
    if not parsed.is_static:
        riwayat_dinamis = store.note_dynamic_qr(
            req.payload, nmid, req.lat, req.lng)
        if parsed.bill_ref and parsed.amount:
            riwayat_tagihan = store.note_bill(
                nmid, parsed.bill_ref, parsed.amount, req.lat, req.lng)

    nearby = store.nearby(req.lat, req.lng)
    elsewhere = store.by_nmid(nmid)
    wilayah = store.area_city(req.lat, req.lng)
    nama_lain = store.names_for_nmid(nmid)
    korpus = store.feature_corpus()
    # Prefiks PAN menandai penyelenggara, dan PAN itu ada di template
    # acquirer — bukan selalu template yang sama dengan NMID.
    pan_merchant = parsed.merchant_pan
    dialek = (store.dialect_profile(pan_merchant[:8])
              if pan_merchant and len(pan_merchant) >= 8 else None)
    anchor_id, anchor_nmid, anchor_state = store.anchor_state(req.lat, req.lng)
    jangkar_bertuan = getattr(store, "_anchor_has_owner", False)

    tantangan = store.challenge_state(req.lat, req.lng, nmid)

    # Jejak kehadiran memisahkan pedagang keliling dari stiker yang
    # disebar, dan hanya relevan kalau NMID ini memang punya jangkar di
    # lebih dari satu tempat. Mayoritas merchant punya satu, dan tidak
    # perlu ikut membayar kuerinya.
    jejak_hadir = (store.jejak_lintas_area(nmid)
                   if len(elsewhere) >= bd.SCATTER_MIN_AREAS else None)

    # Layer 1 — ikatan merchant-lokasi.
    lokasi = bd.evaluate(
        nmid=nmid,
        lat=req.lat,
        lng=req.lng,
        nearby=nearby,
        same_nmid_elsewhere=elsewhere,
        crc_valid=parsed.crc_valid,
        challenge=tantangan,
        merchant_name=parsed.merchant_name,
        jejak_kehadiran=jejak_hadir,
    )

    # Layer 2 — perilaku artefak QR.
    # "Pemilik sah jangkar" diambil dari putusan Layer 1, bukan dari
    # tebakan siapa binding dominan di sini. Bedanya nyata di food court:
    # jangkar dominan bisa milik Toko A, tapi pelanggan yang memindai QR
    # Toko B yang sama-sama mapan juga berhak tidak kena sinyal serangan
    # yang ditujukan ke tetangganya.
    pemilik_sah = (lokasi.matched_binding is not None
                   and lokasi.matched_binding.is_established)

    perilaku = bh.evaluate(
        parsed,
        state=anchor_state,
        nmid_matches_anchor=pemilik_sah,
        anchor_has_owner=jangkar_bertuan,
        accuracy_m=req.accuracy_m,
        has_coords=True,
        integrity=di,
        printed=req.printed_label,
        ambient_ap=(req.ambient_wifi.ap_hashes if req.ambient_wifi else None),
        known_ap=(store.ap_fingerprint(anchor_id) if anchor_id else None),
        dynamic_history=riwayat_dinamis,
        bill_history=riwayat_tagihan,
        area=wilayah,
        other_names=nama_lain,
        issuer_profile=dialek,
        feature_corpus=korpus,
    )

    verdict = _tandai_replay(bd.compose(lokasi, perilaku), req)

    # Pemindaian dari GAMBAR tidak boleh membentuk pengetahuan lokasi.
    #
    # Prinsip ini ditetapkan di Keputusan 49 tapi dulu hanya diterapkan
    # dengan tangan saat pemulihan data — tidak pernah ditegakkan di
    # sini. Akibatnya terukur: tujuh QRIS dari internet, dengan kota
    # Karanganyar sampai Mandailing Natal, semuanya terekam di satu
    # titik di Jakarta. Pengetahuan wilayah untuk lingkungan itu jadi
    # campur aduk dan tidak akan pernah mencapai konsensus.
    #
    # Yang dipisahkan bukan "boleh belajar" vs "tidak boleh", melainkan
    # APA yang boleh dipelajari:
    #
    #   pengetahuan LOKASI   binding, kota wilayah, sidik jari WiFi
    #                        -> hanya dari pemindaian di tempatnya
    #   pengetahuan PAYLOAD  dialek penerbit, kelangkaan ciri merchant
    #                        -> boleh dari gambar; bentuk payload tidak
    #                           berubah karena difoto
    #
    # Pembagian itu yang membuat QRIS dari internet tetap berguna:
    # keragaman penerbit adalah justru yang paling sulit dikumpulkan
    # sendiri di lapangan.
    lokasi_tepercaya = req.location_source != "replay"

    # Pengamatan dicatat hanya kalau tidak terindikasi anomali,
    # supaya stiker palsu tidak ikut membangun reputasi.
    if verdict.status != bd.ANOMALY and lokasi_tepercaya:
        store.record(
            nmid=nmid,
            lat=req.lat,
            lng=req.lng,
            device_anon_id=req.device_anon_id,
            merchant_name=parsed.merchant_name,
            # Dijamin hanya kalau DUA-DUANYA ada: atestasi perangkat DAN
            # klien yang terautentikasi. Atestasi sendiri tidak cukup —
            # ia dilaporkan klien dan tidak bisa kami verifikasi; yang
            # membuatnya berarti adalah PJP yang memeriksanya lalu
            # mempertanggungkannya lewat kunci API mereka. Pemindai
            # anonim yang mengaku `attested: true` tidak dijamin siapa
            # pun, dan tidak boleh terhitung begitu.
            vouched=(status_integritas == "attested" and client_id is not None),
        )
        # Pengetahuan wilayah dibangun HANYA dari pemindaian yang tidak
        # ditolak — alasan yang sama dengan invarian §3.
        store.learn_city(req.lat, req.lng, parsed.merchant_city, nmid)
        if req.ambient_wifi and req.ambient_wifi.ap_hashes:
            # Sidik jari menempel pada BINDING merchant ini, bukan pada
            # jangkar umum — supaya dua lapak berdempetan bisa punya
            # sidik jari masing-masing.
            _b = store.conn.execute(
                "SELECT id FROM bindings WHERE nmid = ? AND geohash_7 = ?",
                (nmid, geo.encode(req.lat, req.lng, bd.INDEX_PRECISION))
            ).fetchone()
            if _b:
                store.learn_ap(_b["id"], req.ambient_wifi.ap_hashes)
    if verdict.status != bd.ANOMALY:
        # Pengetahuan tingkat payload tidak bergantung pada tempat
        # pemindaian, jadi berlaku untuk gambar maupun lapangan.
        store.learn_dialect(parsed, nmid)
        store.learn_features(parsed, nmid)

    # `lokasi_tepercaya` WAJIB ikut di sini, bukan hanya di cabang
    # pembelajaran di atas.
    #
    # Versi pertama Keputusan 54 hanya menahan pembelajaran, dan
    # akibatnya terlihat di lapangan: seorang anggota tim mengkatalogkan
    # QRIS dari gambar sambil duduk di kantor, dan tiap pemindaian
    # menandai jangkar di sekitarnya sebagai "berkali-kali jadi sasaran".
    # Jangkar milik pedagang sungguhan jadi tampak diserang oleh
    # aktivitas yang bukan serangan sama sekali.
    if (verdict.status == bd.ANOMALY and lokasi_tepercaya
            and anchor_id is not None and (
            set(verdict.signals) & bd.ANOMALI_LOKASI)):
        # Jangkar ini jadi sasaran. Dicatat sebagai PERCOBAAN, bukan
        # pengamatan: observer_count tidak disentuh, jadi invarian §3
        # tetap utuh — reputasi palsu tidak bisa dibangun dari sini.
        #
        # Hanya anomali yang BERKAITAN DENGAN LOKASI yang dicatat.
        # Cacat payload — NMID salah bentuk, QR statis bernominal, QR
        # dinamis dipakai ulang — tidak mengatakan apa pun tentang
        # tempat ini, dan mencatatnya membuat merchant sah di sekitar
        # ikut tertuduh.
        store.note_anomaly(anchor_id)

        # Sisi lain dari catatan yang sama: dari sudut pandang NMID yang
        # DITOLAK. Merchant sah yang sepi di sebelah tetangga ramai
        # mengumpulkan barisnya di sini, dan begitu cukup banyak orang
        # berbeda menemuinya — sementara merchant lama TERUS terpindai,
        # bukti bahwa tidak ada yang tertutup — kehadirannya diakui.
        #
        # Hanya untuk konflik jangkar TAK TERDAFTAR. Kalau jangkarnya
        # terdaftar atas nama merchant lain, jalan keluarnya adalah
        # mendaftar ke penyelenggara, bukan mengakumulasi pemindaian.
        # nmid_scatter ikut dicatat: merchant sah yang pindah tempat
        # memakai buku yang sama untuk membuktikan ia benar-benar berada
        # di lokasi barunya.
        if {"nmid_changed_at_anchor", "nmid_scatter"} & set(verdict.signals):
            store.note_challenge(req.lat, req.lng, nmid, req.device_anon_id)

    elapsed = round((time.perf_counter() - started) * 1000, 2)
    lapisan = {"location": lokasi.risk_score, "behavior": perilaku.score}
    audit.record_verdict(
        verdict, nmid, req.lat, req.lng, lapisan, elapsed,
        req.accuracy_m, parsed.merchant_name, req.location_source,
        client_id, status_integritas,
        tk.payload_fingerprint(req.payload),
    )

    _tiket = tk.issue(
        req.payload, verdict.status, verdict.action, nmid,
        client_id or "anonymous", _bahan_tiket(client_id))
    return VerifyResponse(
        verdict=verdict.status,
        action=verdict.action,
        risk_score=verdict.risk_score,
        reasons=verdict.reasons,
        signals=verdict.signals,
        layers=LayerScores(**lapisan),
        location_source=req.location_source,
        device_integrity=status_integritas,
        merchant=MerchantOut(
            nmid=nmid,
            name=parsed.merchant_name,
            city=parsed.merchant_city,
            criteria=parsed.criteria_label,
            is_static=parsed.is_static,
        ),
        evidence=_bukti(lokasi.matched_binding),
        fees=_biaya(parsed),
        tlv=_bedah(parsed, req.include_tlv),
        verification_ticket=_tiket["ticket"],
        ticket_expires_in=_tiket["expires_in"],
        processing_ms=elapsed,
    )
