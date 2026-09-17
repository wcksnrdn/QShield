"""
Model kelangkaan tak-terawasi (unsupervised) untuk profil merchant.

Aturan yang ditulis tangan hanya menangkap hal yang sudah terpikirkan.
Modul ini menangkap yang tidak: **kombinasi yang tidak pernah terjadi
pada merchant sungguhan**, tanpa ada yang perlu menuliskan kombinasinya
lebih dulu.

Cara kerjanya. Sistem mencatat seberapa sering tiap nilai muncul pada
merchant yang diamati — kategori usaha, kriteria, kota, panjang nomor
akun, dan seterusnya. Nilai yang langka dikenali sebagai langka, dan
payload yang membawa BEBERAPA nilai langka sekaligus ditandai.

Ini tak-terawasi dalam arti sebenarnya: tidak ada satu pun contoh
penipuan yang dipakai melatihnya. Yang dipelajari adalah bentuk
"normal", dan penyimpangan dikenali dari situ. Itu penting karena
contoh penipuan terkonfirmasi memang tidak ada — dan classifier
terawasi mustahil dilatih tanpanya.

Yang membedakannya dari model buram: **ia menyebut fitur mana yang
langka dan seberapa langka.** Putusan yang tidak bisa dijelaskan tidak
punya tempat di sistem pembayaran, dan model ini tidak menuntutnya.

Batasnya diakui: merchant sah yang memang tidak biasa akan tertandai.
Karena itu bobotnya sedang, dan butuh beberapa fitur langka sekaligus —
satu keanehan bukan apa-apa.
"""

from dataclasses import dataclass
from typing import Optional

# --- Parameter yang bisa dikalibrasi -------------------------------

# Korpus minimum sebelum model ini berani berpendapat. Di bawah ini
# "langka" tidak punya arti — semuanya langka kalau datanya sedikit.
MIN_CORPUS = 40

# Sebuah nilai disebut langka bila muncul pada kurang dari sekian
# bagian merchant yang diamati.
#
# Dipilih dari sapuan di calibrate_rarity.py. Tebakan awal 0,02 terlalu
# ketat: nilai yang sungguh-sungguh langka pada populasi nyata duduk
# persis di ambang itu, sehingga model hanya menangkap nilai yang sama
# sekali tidak pernah muncul — yaitu sekadar deteksi "nilai tak dikenal",
# bukan deteksi kelangkaan.
#
#   ambang  min fitur   sah tertandai   kombinasi langka   payload ngawur
#     0,02          3           0,00%                 0%             100%
#     0,05          3           0,07%               100%             100%
#     0,08          3           0,13%               100%             100%
#     0,12          3           3,23%               100%             100%
RARE_THRESHOLD = 0.05

# Berapa fitur langka yang harus muncul bersamaan sebelum ditandai.
# Satu keanehan adalah merchant yang tidak biasa; beberapa sekaligus
# adalah pola yang tidak pernah terjadi.
MIN_RARE_FEATURES = 3

W_RARE_PROFILE = 30

# Fitur yang diamati. Sengaja hanya yang kategorikal dan berkardinalitas
# rendah — sesuatu seperti nama merchant akan selalu langka dan tidak
# memberi informasi apa pun.
FEATURES = ("mcc", "criteria", "city", "pan_len", "has_postal",
            "static", "currency", "country")


def features_of(parsed) -> dict:
    """Ciri kategorikal satu payload, untuk dipelajari dan dinilai."""
    acc = parsed.primary_account
    pan_acc = parsed.acquirer_account
    return {
        "mcc": parsed.mcc or "?",
        "criteria": (acc.criteria if acc else None) or "?",
        "city": (parsed.merchant_city or "?").strip().upper(),
        "pan_len": (str(len(pan_acc.pan))
                    if pan_acc and pan_acc.pan else "0"),
        "has_postal": "1" if parsed.postal_code else "0",
        "static": "1" if parsed.is_static else "0",
        "currency": parsed.currency or "?",
        "country": parsed.country or "?",
    }


@dataclass
class RarityFinding:
    feature: str
    value: str
    share: float


LABEL = {
    "mcc": "kategori usaha",
    "criteria": "skala usaha",
    "city": "kota",
    "pan_len": "panjang nomor akun",
    "has_postal": "keberadaan kode pos",
    "static": "tipe kode",
    "currency": "mata uang",
    "country": "kode negara",
}


def score(parsed, corpus: Optional[dict]) -> tuple:
    """Nilai kelangkaan satu payload terhadap korpus yang dipelajari.

    corpus  {fitur: {nilai: jumlah_nmid}} beserta kunci "_total"

    Mengembalikan (bobot, daftar RarityFinding). Bobot 0 berarti tidak
    ada yang perlu dikatakan — termasuk ketika korpusnya belum cukup.
    """
    if not corpus:
        return 0, []
    total = corpus.get("_total", 0)
    if total < MIN_CORPUS:
        return 0, []

    punya = features_of(parsed)
    langka = []
    for f in FEATURES:
        terlihat = corpus.get(f)
        if not terlihat:
            continue
        # Fitur yang nilainya nyaris seragam tidak memberi informasi:
        # kalau 100% merchant memakai mata uang yang sama, nilai lain
        # akan selalu "langka" tanpa berarti apa-apa.
        if len(terlihat) < 2:
            continue
        n = terlihat.get(punya[f], 0)
        bagian = n / total
        if bagian < RARE_THRESHOLD:
            langka.append(RarityFinding(f, punya[f], bagian))

    if len(langka) < MIN_RARE_FEATURES:
        return 0, []
    return W_RARE_PROFILE, langka


def explain(langka: list) -> str:
    """Kalimat yang menyebut fitur mana yang langka dan seberapa."""
    bagian = ", ".join(
        f"{LABEL.get(t.feature, t.feature)} {t.value} "
        f"({t.share * 100:.1f}% merchant)"
        for t in langka[:3])
    return (
        f"Kombinasi ciri merchant ini jarang terjadi bersamaan: {bagian}"
        + ("" if len(langka) <= 3 else f", dan {len(langka) - 3} lainnya")
    )
