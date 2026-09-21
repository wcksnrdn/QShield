"""
Tiket verifikasi — mengikat putusan ke QR yang diperiksa.

Masalah yang ditutup. Sekarang aplikasi memanggil `/verify`, menerima
putusan, lalu jeda: antara "diperiksa" dan "dieksekusi" tidak ada yang
menjaga bahwa keduanya menyangkut QR yang SAMA. Aplikasi — atau malware
di antaranya — bisa memverifikasi QR A lalu membayar ke QR B.

Tiket adalah pernyataan ringkas yang ditandatangani: *"pada waktu ini,
untuk payload dengan sidik jari ini, putusannya ini."* Pihak yang
mengeksekusi pembayaran menghitung ulang sidik jari payload yang
hendak dibayar dan menuntutnya cocok.

APA YANG TIKET INI LAKUKAN, DAN APA YANG TIDAK
==============================================

MENGIKAT. Putusan tidak bisa dipindahkan ke QR lain tanpa ketahuan.
Itu satu-satunya klaim yang dibuat berkas ini.

TIDAK MEMAKSA. Tiket hanya berguna kalau ada yang MEMERIKSANYA. Yang
mengeksekusi pembayaran adalah PJP sendiri; Q-Shield tidak ada di jalur
itu. PJP yang mengabaikan `cooling_off` juga akan mengabaikan tiketnya.
Penegakan sungguhan menuntut switch atau acquirer menolak menyelesaikan
transaksi tanpa tiket sah — perubahan tingkat infrastruktur, bukan
tingkat pustaka. Jangan pernah menuliskan klaim "aplikasi tidak bisa
mengabaikannya"; itu tidak benar.

TIDAK MENCEGAH REPLAY. Tiketnya stateless dan tidak disimpan, jadi QR
yang sama bisa dieksekusi dua kali dalam masa berlakunya. Idempotensi
transaksi milik PJP. Konsisten dengan R2, yang memang di luar jangkauan.

KENAPA HMAC, BUKAN TANDA TANGAN ASIMETRIS
==========================================

`hmac` dan `hashlib` ada di pustaka standar; RS256 menuntut
`cryptography` — dependensi native berat — plus PKI dan distribusi
kunci publik. Proyek ini punya tiga dependensi runtime dan nol berkas
data, dan satu field tidak sebanding dengan harga itu.

Konsekuensinya disebut terus terang, bukan disembunyikan:

1. Simetris berarti PJP BISA memalsukan tiketnya sendiri. Jadi tidak ada
   non-repudiation terhadap PJP. Yang dipertahankan adalah pertahanan
   terhadap PIHAK KETIGA — malware di antara aplikasi dan backend — dan
   itu tepat sasaran celah yang dimaksud.
2. Kuncinya diturunkan dari hash kunci API yang sudah tersimpan, jadi
   konfigurasi yang bocor kini BISA dipakai memalsukan tiket. Itu
   melemahkan properti yang diklaim README ("konfigurasi bocor tidak
   langsung memberi kunci yang bisa dipakai") dan tercatat sebagai R11
   di THREAT-MODEL.md.
"""

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone

# Masa berlaku. Cukup panjang untuk pengguna membaca kartu hasil dan
# memasukkan PIN, cukup pendek supaya tiket yang tercuri tidak berumur
# panjang. Menuntut jam kedua sisi tersinkron — jam yang meleset dua
# menit membuat tiket sah ditolak.
TTL_DETIK = 90

# Pemisah domain: kunci tiket tidak boleh sama dengan nilai apa pun yang
# dipakai untuk tujuan lain, sekalipun bahan dasarnya sama.
INFO_KUNCI = b"qshield-ticket-v1"

VERSI = "qs1"


class TicketError(Exception):
    """Tiket tidak sah: rusak, palsu, kedaluwarsa, atau tidak cocok."""


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(teks: str) -> bytes:
    return base64.urlsafe_b64decode(teks + "=" * (-len(teks) % 4))


def payload_fingerprint(payload: str) -> str:
    """Sidik jari payload QRIS. Hash, BUKAN payloadnya.

    Yang diikat adalah sidik jarinya, bukan isinya — payload memuat PAN
    merchant, dan itu alasan yang sama kenapa `audit.py` menolak
    mencatat payload mentah.
    """
    return hashlib.sha256(payload.strip().encode("utf-8")).hexdigest()


def derive_key(secret_material: str) -> bytes:
    """Turunkan kunci tiket dari bahan rahasia milik satu klien.

    Bahannya adalah hash kunci API yang sudah tersimpan: Q-Shield
    memilikinya, dan PJP bisa menurunkannya sendiri dari kunci
    mentahnya. Nol kunci baru untuk didistribusikan.
    """
    return hmac.new(secret_material.encode("utf-8"), INFO_KUNCI,
                    hashlib.sha256).digest()


def issue(payload: str, verdict: str, action: str, nmid, client_id: str,
          secret_material: str, now=None, ttl: int = TTL_DETIK) -> dict:
    """Terbitkan tiket untuk satu putusan.

    Sengaja TIDAK memuat: koordinat, `device_anon_id`, akurasi, maupun
    payload mentah. Invarian §8 berlaku di sini seperti di mana pun —
    tiket yang bocor tidak boleh memberi tahu siapa memindai di mana.
    """
    now = now or datetime.now(timezone.utc)
    iat = int(now.timestamp())
    isi = {
        "v": VERSI,
        "fp": payload_fingerprint(payload),
        "verdict": verdict,
        "action": action,
        "nmid": nmid,
        "client": client_id,
        "iat": iat,
        "exp": iat + ttl,
    }
    badan = _b64(json.dumps(isi, separators=(",", ":"),
                            sort_keys=True).encode("utf-8"))
    tanda = _b64(hmac.new(derive_key(secret_material), badan.encode("ascii"),
                          hashlib.sha256).digest())
    return {"ticket": f"{badan}.{tanda}", "expires_in": ttl, "claims": isi}


def verify(tiket: str, secret_material: str, payload: str = None,
           now=None) -> dict:
    """Periksa tiket. Kembalikan klaimnya, atau lempar TicketError.

    `payload` opsional TAPI itulah gunanya: tanpa menyodorkan payload
    yang HENDAK DIBAYAR, pemeriksaan ini hanya membuktikan tiketnya
    asli — bukan bahwa ia menyangkut QR yang sedang dieksekusi. Celah
    "verifikasi QR A, bayar QR B" baru tertutup kalau payload ikut.
    """
    if not isinstance(tiket, str) or tiket.count(".") != 1:
        raise TicketError("Bentuk tiket tidak dikenal")
    badan, tanda = tiket.split(".", 1)

    harap = _b64(hmac.new(derive_key(secret_material), badan.encode("ascii"),
                          hashlib.sha256).digest())
    # compare_digest, bukan ==: lama eksekusinya tidak boleh membocorkan
    # berapa byte awal tanda tangan yang sudah benar.
    if not hmac.compare_digest(tanda, harap):
        raise TicketError("Tanda tangan tiket tidak cocok")

    try:
        isi = json.loads(_unb64(badan))
    except Exception:
        raise TicketError("Isi tiket tidak bisa dibaca")

    if isi.get("v") != VERSI:
        raise TicketError(f"Versi tiket tidak didukung: {isi.get('v')}")

    sekarang = int((now or datetime.now(timezone.utc)).timestamp())
    if sekarang >= isi.get("exp", 0):
        raise TicketError("Tiket sudah kedaluwarsa")
    # Tiket dari masa depan menandakan jam yang tidak sinkron — dan
    # diam-diam menerimanya berarti memperpanjang masa berlakunya.
    if sekarang < isi.get("iat", 0) - 60:
        raise TicketError("Tiket terbit di masa depan; periksa sinkronisasi jam")

    if payload is not None:
        if not hmac.compare_digest(payload_fingerprint(payload),
                                   isi.get("fp", "")):
            raise TicketError(
                "Tiket ini untuk QR yang BERBEDA dari yang hendak dibayar")

    return isi
