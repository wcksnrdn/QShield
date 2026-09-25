"""
Kunci klaim yang menjadi dasar seluruh arsitektur Q-Shield.

Klaim itu: analisis payload tidak bisa memisahkan stiker penipu dari
stiker korban, karena stiker penipu MEMANG diterbitkan acquirer
sungguhan. Kalau klaim ini salah, seluruh alasan kami mengikat
identitas ke TEMPAT ikut runtuh — jadi ia tidak boleh cuma hidup
sebagai kalimat di dokumen pitch.

Sebelum berkas ini ada, klaim itu muncul di empat dokumen dan tidak ada
satu pun yang menguncinya. Siapa pun bisa mengubah ekstraktor ciri dan
membuatnya diam-diam tidak benar lagi.

    PYTHONPATH=scripts python3 tests/test_enam_belas.py
"""

import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from qshield import emvco

from enam_belas_ciri import CIRI, ambil

_hasil = []


def cek(nama):
    def deco(fn):
        try:
            _hasil.append((nama, True, fn() or ""))
        except AssertionError as exc:
            _hasil.append((nama, False, str(exc)))
        return fn
    return deco


def qr(nmid="ID1024365478912", pan_ekor="0000000001",
       nama="WARUNG BU SRI", kota="BANDUNG", mcc="5812",
       kriteria="UMI", prefiks="93600914", **tambahan):
    acct = emvco.build_tlv({
        "00": "ID.CO.QRIS.WWW", "01": prefiks + pan_ekor,
        "02": nmid, "03": kriteria})
    isi = {"00": "01", "01": "11", "26": acct, "52": mcc, "53": "360",
           "58": "ID", "59": nama, "60": kota}
    isi.update(tambahan)
    return emvco.build(isi)


def selisih(a, b):
    """(struktural, deskriptif) — berapa ciri yang berbeda."""
    ca, _ = ambil(a)
    cb, _ = ambil(b)
    s = d = 0
    for (nama, kel, va), (_, _, vb) in zip(ca, cb):
        if va != vb:
            if kel == "struktural":
                s += 1
            else:
                d += 1
    return s, d


@cek("Cirinya tepat enam belas, dan pengelompokannya utuh")
def _t1():
    assert len(CIRI) == 16, f"{len(CIRI)} ciri, klaim di dokumen 16"
    kel = {k for _, k, _ in CIRI}
    assert kel == {"struktural", "deskriptif"}, kel
    s = sum(1 for _, k, _ in CIRI if k == "struktural")
    return f"{s} struktural + {16 - s} deskriptif"


@cek("Penipu dan korban dari acquirer yang sama: NOL ciri struktural beda")
def _t2():
    """Inti klaimnya. Usahanya berbeda, penerbitnya sama."""
    korban = qr()
    penipu = qr(nmid="ID1099887766554", pan_ekor="0000000002",
                nama="TOKO MAJU JAYA", kota="JAKARTA PUSAT", mcc="5999")
    s, d = selisih(korban, penipu)
    assert s == 0, f"{s} ciri struktural berbeda — klaim pitch tidak lagi benar"
    return f"struktural {s}, deskriptif {d} (usaha memang beda)"


@cek("Penipu yang TELITI: nol dari enam belas, seluruhnya")
def _t3():
    """Bentuk terkuat klaimnya, dan yang paling jujur.

    Penipu mengisi sendiri kolom deskriptif saat mendaftar. Yang
    mencocokkannya dengan korban tidak meninggalkan satu pun jejak di
    payload — nol dari enam belas."""
    korban = qr()
    penipu = qr(nmid="ID1099887766554", pan_ekor="0000000002",
                nama="WARUNG BU SRI", kota="BANDUNG", mcc="5812")
    s, d = selisih(korban, penipu)
    assert (s, d) == (0, 0), f"struktural {s}, deskriptif {d}"
    return "0 dari 16 — tidak ada yang bisa dipelajari classifier di sini"


@cek("Tapi tidak buta: QR yang DIBANGKITKAN ULANG tetap ketahuan")
def _t4():
    """Kalau klaimnya 'payload tidak berguna', ini harus gagal.

    Yang benar: payload berguna untuk menangkap QR yang disusun ulang
    orang lain — bukan untuk menangkap sticker-swap."""
    korban = qr()
    # Disusun ulang: urutan field berbeda dari generator acquirer.
    acct = emvco.build_tlv({
        "00": "ID.CO.QRIS.WWW", "01": "936009140000000002",
        "02": "ID1099887766554", "03": "UMI"})
    ulang = ("000201" + "010211" + f"5204{'5812'}" + f"5303{'360'}"
             + f"26{len(acct):02d}{acct}" + "5802ID"
             + f"5913{'WARUNG BU SRI'}" + f"6007{'BANDUNG'}")
    ulang = ulang + "6304" + emvco.crc16_ccitt(ulang + "6304")
    s, _ = selisih(korban, ulang)
    assert s > 0, "QR yang disusun ulang harus meninggalkan jejak struktural"
    return f"{s} ciri struktural berbeda — dialek penerbit bekerja di sini"


@cek("Ciri kota memang berbeda — dan itu dipakai, bukan diabaikan")
def _t5():
    """Menutup kontradiksi yang sempat ada di dokumen pitch.

    Dokumen menulis 'payload tidak memberi tahu apa-apa', sementara
    binding.py menskor ketidakcocokan kota. Dua-duanya benar, asal
    dikatakan dengan presisi: kota adalah ciri DESKRIPTIF yang diisi
    penipu sendiri, jadi selisihnya adalah kesalahan penipu, bukan
    deteksi struktural."""
    from qshield import binding as bd
    from enam_belas_ciri import DI_LUAR

    # Kota TIDAK termasuk enam belas — dan itu harus tetap begitu,
    # karena ia teks bebas, bukan ciri struktural.
    nama_ciri = {n for n, _, _ in CIRI}
    assert not any("kota" in n for n in nama_ciri), nama_ciri

    # Tapi ia juga tidak boleh disembunyikan: harus tampil di daftar
    # "di luar enam belas", supaya tidak terlihat seperti ciri yang
    # dibuang karena kebetulan bekerja.
    luar = {n for n, _ in DI_LUAR}
    assert "kota merchant" in luar, luar

    # Dan sinyalnya harus benar-benar ada di penilaian.
    assert bd.W_CITY_MISMATCH > 0, "sinyal kota hilang; klaim ikut berubah"

    a = qr(kota="BANDUNG")
    b = qr(nmid="ID1099887766554", pan_ekor="0000000002",
           kota="JAKARTA PUSAT")
    s, _ = selisih(a, b)
    assert s == 0, f"{s} ciri struktural berbeda"
    return (f"di luar 16, ditampilkan terpisah, diskor {bd.W_CITY_MISMATCH} "
            f"— struktural tetap {s}")


@cek("Ekstraktor peragaan memakai emvco, bukan salinan sendiri")
def _t6():
    """Peragaan yang punya ekstraktor sendiri bisa melenceng dari model
    yang diperagakannya — dan itu sudah pernah terjadi di berkas ini:
    checksum yang seluruhnya angka terbaca 'huruf kecil'."""
    p = emvco.parse(qr())
    nilai = dict((n, f(p)) for n, _, f in CIRI)
    dialek = emvco.dialect(p)
    harus = {"upper": "huruf besar", "lower": "huruf kecil"}[dialek["crc_case"]]
    assert nilai["gaya penulisan checksum"] == harus, nilai
    assert nilai["prefiks nomor akun"] == p.merchant_pan[:8]
    return "gaya checksum dibaca dari emvco.dialect(), tidak dihitung ulang"


print("=" * 70)
print("ENAM BELAS CIRI — KLAIM DASAR ARSITEKTUR")
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
