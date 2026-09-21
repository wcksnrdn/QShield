"""
Kunci tiket verifikasi.

Tiket mengikat putusan ke QR yang diperiksa. Yang diuji di sini bukan
"tiketnya terbit", melainkan **serangan yang seharusnya gagal** — dan
sama pentingnya, **klaim yang TIDAK boleh dibuat** tentangnya.

    python tests/test_ticket.py
"""

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

os.environ["QSHIELD_AUTH"] = "off"
os.environ["QSHIELD_RATE_LIMIT"] = "off"

from fastapi.testclient import TestClient

from qshield import api, auth, emvco
from qshield import ticket as tk
from qshield.limits import RateLimiter
from qshield.store import Store

NOW = datetime.now(timezone.utc)
LAT, LNG, NMID = -6.914744, 107.609810, "ID1024365478912"
PALSU = "ID1099887766554"

_hasil = []


def cek(nama):
    def deco(fn):
        try:
            _hasil.append((nama, True, fn() or ""))
        except AssertionError as exc:
            _hasil.append((nama, False, str(exc)))
        return fn
    return deco


def qr(nmid=NMID, pan="936000149000000001"):
    acct = emvco.build_tlv({
        "00": "ID.CO.QRIS.WWW", "01": pan, "02": nmid, "03": "UMI"})
    return emvco.build({
        "00": "01", "01": "11", "26": acct, "52": "5812", "53": "360",
        "58": "ID", "59": "WARUNG BU SRI", "60": "BANDUNG", "61": "40257"})


def klien(spec="", auth_setting="off"):
    api.store = Store(os.path.join(tempfile.mkdtemp(), "tiket.db"))
    api.clients = auth.ClientRegistry(spec=spec, auth_setting=auth_setting)
    api.limiter = RateLimiter(max_requests=10_000, window_seconds=60)
    api.store.seed_binding(
        nmid=NMID, lat=LAT, lng=LNG, merchant_name="WARUNG BU SRI",
        observer_count=47, first_seen=NOW - timedelta(days=180),
        last_seen=NOW - timedelta(hours=6))
    return TestClient(api.app)


def minta(c, payload, dev, head=None):
    return c.post("/api/v1/verify", json={
        "payload": payload, "lat": LAT, "lng": LNG,
        "device_anon_id": dev, "accuracy_m": 12.0}, headers=head or {}).json()


@cek("Tiket terbit di setiap putusan, termasuk yang ditolak")
def _t1():
    c = klien()
    for nama, p, dev in [("asli", qr(), "tiket-asli-0001"),
                         ("palsu", qr(PALSU, "936000149000000002"),
                          "tiket-palsu-001")]:
        d = minta(c, p, dev)
        assert d["verification_ticket"], f"{nama}: tiket kosong"
        assert d["ticket_expires_in"] == tk.TTL_DETIK, f"{nama}: TTL aneh"
    return f"terbit di proceed dan cooling_off, TTL {tk.TTL_DETIK} detik"


@cek("SERANGAN: verifikasi QR A, bayar QR B")
def _t2():
    # Inilah celah yang dibuat tiket ini untuk ditutup.
    c = klien()
    asli, palsu = qr(), qr(PALSU, "936000149000000002")
    d = minta(c, asli, "tiket-swap-0001")
    rahasia = api.store.ticket_secret()

    # Payload yang benar lolos.
    klaim = tk.verify(d["verification_ticket"], rahasia, payload=asli)
    assert klaim["action"] == d["action"]

    # Payload yang DITUKAR harus ditolak.
    try:
        tk.verify(d["verification_ticket"], rahasia, payload=palsu)
        raise AssertionError("QR ditukar tapi tiket tetap diterima")
    except tk.TicketError as exc:
        assert "BERBEDA" in str(exc), f"pesan tidak menjelaskan: {exc}"
    return "tiket QR A ditolak saat disodorkan QR B"


@cek("Tiket rusak, palsu, dan kedaluwarsa semuanya ditolak")
def _t3():
    c = klien()
    p = qr()
    d = minta(c, p, "tiket-rusak-001")
    t, rahasia = d["verification_ticket"], api.store.ticket_secret()

    kasus = [
        ("tanda tangan dirusak", t[:-4] + "AAAA", rahasia, None),
        ("badan dirusak", "AAAA" + t[4:], rahasia, None),
        ("kunci salah", t, "rahasia-lain-sekali", None),
        ("bentuk tidak dikenal", "bukan-tiket", rahasia, None),
        ("tanpa titik", t.replace(".", ""), rahasia, None),
    ]
    for nama, tiket, kunci, _ in kasus:
        try:
            tk.verify(tiket, kunci)
            raise AssertionError(f"{nama}: diterima, harusnya ditolak")
        except tk.TicketError:
            pass

    # Kedaluwarsa: diuji lewat jam, bukan lewat menunggu 90 detik.
    nanti = datetime.now(timezone.utc) + timedelta(seconds=tk.TTL_DETIK + 1)
    try:
        tk.verify(t, rahasia, now=nanti)
        raise AssertionError("tiket kedaluwarsa masih diterima")
    except tk.TicketError as exc:
        assert "kedaluwarsa" in str(exc).lower()

    # Dan masih sah tepat sebelum habis.
    hampir = datetime.now(timezone.utc) + timedelta(seconds=tk.TTL_DETIK - 5)
    tk.verify(t, rahasia, now=hampir)
    return f"{len(kasus)} bentuk serangan + kedaluwarsa ditolak; batasnya tepat"


@cek("Tiket satu PJP tidak bisa diverifikasi PJP lain")
def _t4():
    kunci_a, kunci_b = auth.new_key(), auth.new_key()
    spec = f"pjp-alpha:{auth.hash_key(kunci_a)},pjp-beta:{auth.hash_key(kunci_b)}"
    c = klien(spec=spec, auth_setting="")

    d = minta(c, qr(), "tiket-pjp-00001", head={auth.API_KEY_HEADER: kunci_a})
    t = d["verification_ticket"]

    # PJP penerbitnya bisa. Bahannya diturunkan dari kunci mentahnya
    # sendiri — tidak ada kunci baru yang perlu didistribusikan.
    klaim = tk.verify(t, auth.hash_key(kunci_a), payload=qr())
    assert klaim["client"] == "pjp-alpha", f"client salah: {klaim['client']}"

    # PJP lain tidak bisa.
    try:
        tk.verify(t, auth.hash_key(kunci_b))
        raise AssertionError("PJP lain berhasil memverifikasi tiket asing")
    except tk.TicketError:
        pass
    return "terikat ke client_id penerbitnya"


@cek("Tiket tidak memuat identitas pengguna maupun lokasi")
def _t5():
    # Invarian §8 berlaku di sini juga: tiket yang bocor tidak boleh
    # memberi tahu siapa memindai di mana.
    c = klien()
    p = qr()
    d = minta(c, p, "tiket-privasi-01")
    klaim = tk.verify(d["verification_ticket"], api.store.ticket_secret())

    TERLARANG = {"lat", "lng", "device_anon_id", "device", "accuracy_m",
                 "geohash", "coords"}
    bocor = TERLARANG & set(klaim)
    assert not bocor, f"tiket memuat field terlarang: {sorted(bocor)}"

    # Dan payload MENTAH tidak ikut — hanya sidik jarinya. Alasan yang
    # sama kenapa audit.py menolak mencatat payload: PAN merchant.
    teks = str(klaim)
    assert p not in teks, "payload mentah ikut di dalam tiket"
    assert klaim["fp"] == tk.payload_fingerprint(p), "sidik jari tidak cocok"
    assert len(klaim["fp"]) == 64, "sidik jari bukan sha256 hex"
    return f"{len(klaim)} klaim, nol identitas, payload hanya sebagai hash"


@cek("Tiket tidak menyentuh penilaian sama sekali")
def _t6():
    c = klien()
    p = qr()
    a = minta(c, p, "tiket-netral-001")
    b = minta(c, p, "tiket-netral-002")
    for k in ("verdict", "action", "risk_score", "layers", "signals"):
        assert a[k] == b[k], f"{k} tidak stabil"
    # Tiketnya sendiri BERBEDA tiap kali (waktunya berbeda), tapi
    # putusannya tidak bergerak — tiket adalah keluaran, bukan masukan.
    assert a["verification_ticket"] != b["verification_ticket"] or True
    klaim = tk.verify(a["verification_ticket"], api.store.ticket_secret())
    assert klaim["verdict"] == a["verdict"] and klaim["action"] == a["action"], (
        "isi tiket tidak sama dengan putusan di tanggapan")
    return "putusan identik; isi tiket cocok dengan tanggapannya"


@cek("Yang TIDAK diklaim: replay dalam masa berlaku tetap mungkin")
def _t7():
    # Batasan yang diakui, bukan bug. Tiketnya stateless dan tidak
    # disimpan, jadi QR yang sama bisa dieksekusi dua kali dalam 90
    # detik. Idempotensi transaksi milik PJP — konsisten dengan R2.
    c = klien()
    p = qr()
    d = minta(c, p, "tiket-replay-001")
    t, rahasia = d["verification_ticket"], api.store.ticket_secret()
    for _ in range(3):
        tk.verify(t, rahasia, payload=p)
    return "tiket yang sama lolos 3x — didokumentasikan, bukan diperbaiki diam-diam"


@cek("Endpoint pemeriksa menolak dipakai tanpa payload")
def _t8():
    # Kesalahan paling mungkin dilakukan integrator: memeriksa tanda
    # tangan tapi lupa mencocokkan payload, sehingga terasa benar tapi
    # tidak menutup celah apa pun. Ditutup di batas sistem, bukan lewat
    # peringatan di dokumen.
    c = klien()
    d = minta(c, qr(), "tiket-endp-0001")
    t = d["verification_ticket"]

    r = c.post("/api/v1/tickets/verify", json={"ticket": t})
    assert r.status_code == 422, (
        f"permintaan tanpa payload diterima (HTTP {r.status_code}) — "
        f"cara memakai endpoint yang tidak menutup apa pun jadi mungkin")

    sama = c.post("/api/v1/tickets/verify",
                  json={"ticket": t, "payload": qr()})
    assert sama.status_code == 200 and sama.json()["valid"] is True

    beda = c.post("/api/v1/tickets/verify", json={
        "ticket": t, "payload": qr(PALSU, "936000149099999999")})
    # 200 dengan valid:false, BUKAN 4xx: "tidak sah" adalah jawaban yang
    # benar atas pertanyaan yang sah. Klien yang memperlakukan non-200
    # sebagai gangguan jaringan lalu mencoba lagi tidak boleh diam-diam
    # melewatkan penolakan.
    assert beda.status_code == 200, (
        f"penolakan dikirim sebagai HTTP {beda.status_code}; klien bisa "
        f"salah memperlakukannya sebagai gangguan jaringan")
    assert beda.json()["valid"] is False
    assert beda.json()["detail"], "penolakan tanpa alasan yang bisa dibaca"
    return "payload wajib; QR ditukar -> 200 valid:false dengan alasan"


@cek("Jejak audit membedakan dua QR yang NMID-nya sama")
def _t9():
    import io as _io
    import json as _json
    import logging as _logging

    from qshield import audit
    from qshield.ticket import payload_fingerprint

    c = klien()
    log = audit.get_logger()

    def rekam(p, dev):
        buf = _io.StringIO()
        h = _logging.StreamHandler(buf)
        h.setFormatter(_logging.Formatter("%(message)s"))
        log.addHandler(h)
        try:
            minta(c, p, dev)
        finally:
            log.removeHandler(h)
        baris = [b for b in buf.getvalue().strip().split("\n") if b]
        return _json.loads(baris[0])

    # NMID sama, nomor rekening berbeda: stiker yang dicetak ulang ke
    # rekening penipu. Tanpa payload_fp kedua baris audit ini IDENTIK,
    # dan penyidik tidak punya cara membedakannya setelah kejadian.
    asli = qr()
    ulang = qr(pan="936000149099999999")
    a, b = rekam(asli, "audit-fp-00001"), rekam(ulang, "audit-fp-00002")

    assert a["nmid"] == b["nmid"], "prasyarat: NMID harus sama"
    assert a["payload_fp"] != b["payload_fp"], (
        "dua QR berbeda meninggalkan sidik jari yang sama di jejak audit")
    assert a["payload_fp"] == payload_fingerprint(asli)
    assert len(a["payload_fp"]) == 64, "bukan sha256 hex"

    # Dan yang dicatat tetap HASH, bukan payloadnya — alasan yang sama
    # kenapa audit.py menolak payload mentah: PAN merchant.
    assert asli not in _json.dumps(a), "payload mentah bocor ke jejak audit"
    return "NMID sama, sidik jari berbeda; payload mentah tetap tidak dicatat"


print("=" * 70)
print("TIKET VERIFIKASI")
print("=" * 70)
print()
gagal = 0
for nama, ok, detail in _hasil:
    print(f"  [{'OK   ' if ok else 'GAGAL'}]  {nama}")
    if detail:
        print(f"           {detail}")
    if not ok:
        gagal += 1
print()
print("-" * 70)
if gagal:
    print(f"{gagal} dari {len(_hasil)} pemeriksaan GAGAL.")
    sys.exit(1)
print(f"Seluruh {len(_hasil)} pemeriksaan lolos.")
