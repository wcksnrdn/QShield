"""Kalibrasi model kelangkaan tak-terawasi.

Yang ditimbang: menangkap kombinasi ciri yang tidak pernah terjadi pada
merchant sungguhan, tanpa menandai merchant sah yang kebetulan tidak
biasa.

Model ini tidak dilatih dengan contoh penipuan — memang tidak ada.
Yang dipelajari adalah bentuk normal, dan penyimpangan dikenali dari
situ. Itulah arti tak-terawasi di sini.
"""

import random

from qshield import emvco
from qshield import profile as pf

random.seed(89)

# Sebaran yang meniru populasi merchant Indonesia: beberapa kategori
# mendominasi, sisanya panjang-ekor.
MCC = (["5812"] * 30 + ["5411"] * 25 + ["5499"] * 15 + ["5814"] * 12 +
       ["5999"] * 8 + ["7230"] * 4 + ["8099"] * 3 + ["7996"] * 2 + ["4121"])
KRITERIA = ["UMI"] * 70 + ["UKE"] * 22 + ["UME"] * 6 + ["UBE"] * 2
KOTA = (["BANDUNG"] * 40 + ["JAKARTA PUSAT"] * 20 + ["SURABAYA"] * 15 +
        ["KOTA BOGOR"] * 10 + ["SEMARANG"] * 8 + ["DENPASAR"] * 5 +
        ["MEDAN"] * 2)
PAN_LEN = [18] * 85 + [16] * 12 + [19] * 3


def merchant(rng, mcc=None, kriteria=None, kota=None, pan_len=None,
             pos=None, statis=None):
    pan = "".join(rng.choice("0123456789")
                  for _ in range(pan_len or rng.choice(PAN_LEN)))
    acct = emvco.build_tlv({
        "00": "ID.CO.QRIS.WWW", "01": pan,
        "02": "ID" + "".join(rng.choice("0123456789") for _ in range(13)),
        "03": kriteria or rng.choice(KRITERIA)})
    f = {"00": "01", "01": "11" if (statis if statis is not None
                                    else rng.random() < 0.9) else "12",
         "26": acct, "52": mcc or rng.choice(MCC), "53": "360", "58": "ID",
         "59": "MERCHANT", "60": kota or rng.choice(KOTA)}
    ada_pos = pos if pos is not None else rng.random() < 0.75
    if ada_pos:
        f["61"] = str(rng.randint(10000, 99999))
    if f["01"] == "12":
        f["54"] = "50000.00"
    return emvco.parse(emvco.build(f))


def korpus_dari(rng, n):
    k = {"_total": n}
    for i in range(n):
        for f, v in pf.features_of(merchant(rng)).items():
            k.setdefault(f, {})[v] = k.setdefault(f, {}).get(v, 0) + 1
    return k


print("=" * 74)
print("1. POSITIF PALSU PADA MERCHANT SAH")
print("=" * 74)
print()
print("  Model dilatih pada populasi, lalu merchant SAH dari populasi")
print("  yang sama dinilai. Berapa yang tertandai?")
print()
print(f"  {'korpus':>10}{'merchant sah tertandai':>26}")
print("  " + "-" * 40)
for n in (20, 40, 100, 400, 1500):
    rng = random.Random(n)
    k = korpus_dari(rng, n)
    salah = sum(1 for _ in range(3000) if pf.score(merchant(rng), k)[0])
    print(f"  {n:>10}{100 * salah / 3000:>25.2f}%")

print()
print("  Di bawah MIN_CORPUS model diam sepenuhnya — itu sebabnya")
print(f"  korpus {pf.MIN_CORPUS} ke bawah menghasilkan 0%.")

print()
print("=" * 74)
print("1b. SAPUAN AMBANG — kenapa 0,05 dan bukan 0,02")
print("=" * 74)
print()
print("  Tebakan awal 0,02 terlalu ketat: nilai yang sungguh langka pada")
print("  populasi nyata duduk persis di ambang itu, sehingga model hanya")
print("  menangkap nilai yang tidak pernah muncul sama sekali.")
print()
_rng = random.Random(7)
_k = korpus_dari(_rng, 1200)
_aneh = dict(mcc="7996", kriteria="UBE", kota="MEDAN", pan_len=19, pos=False)
_ngawur = dict(mcc="9999", kriteria="XXX", kota="ANTAH BERANTAH",
               pan_len=12, pos=False, statis=False)
_t0, _n0 = pf.RARE_THRESHOLD, pf.MIN_RARE_FEATURES
print(f"  {'ambang':>8}{'min fitur':>11}{'sah tertandai':>16}"
      f"{'kombinasi langka':>19}{'payload ngawur':>17}")
print("  " + "-" * 72)
for _t in (0.02, 0.05, 0.08, 0.12):
    for _n in (2, 3):
        pf.RARE_THRESHOLD, pf.MIN_RARE_FEATURES = _t, _n
        _r = random.Random(11)
        _s = sum(1 for _ in range(3000) if pf.score(merchant(_r), _k)[0])
        _a = sum(1 for _ in range(300)
                 if pf.score(merchant(_r, **_aneh), _k)[0])
        _g = sum(1 for _ in range(300)
                 if pf.score(merchant(_r, **_ngawur), _k)[0])
        print(f"  {_t:>8.2f}{_n:>11}{100 * _s / 3000:>15.2f}%"
              f"{100 * _a / 300:>18.0f}%{100 * _g / 300:>16.0f}%")
pf.RARE_THRESHOLD, pf.MIN_RARE_FEATURES = _t0, _n0
print()
print("  0,05 dengan 3 fitur: positif palsu 0,07%, menangkap keduanya.")

print()
print("=" * 74)
print("2. APA YANG TERTANGKAP")
print("=" * 74)
print()
rng = random.Random(7)
k = korpus_dari(rng, 1200)
uji = [
    ("merchant biasa", {}),
    ("warung besar (kriteria tidak biasa)", {"kriteria": "UBE"}),
    ("klinik di kota kecil", {"mcc": "8099", "kota": "MEDAN"}),
    ("kombinasi tak pernah terjadi",
     {"mcc": "7996", "kriteria": "UBE", "kota": "MEDAN",
      "pan_len": 19, "pos": False}),
    ("payload disusun asal",
     {"mcc": "9999", "kriteria": "XXX", "kota": "ANTAH BERANTAH",
      "pan_len": 12, "pos": False, "statis": False}),
]
print(f"  {'kasus':<40}{'bobot':>8}  fitur langka")
print("  " + "-" * 70)
for nama, kw in uji:
    bobot, langka = pf.score(merchant(rng, **kw), k)
    ciri = ", ".join(t.feature for t in langka) or "—"
    print(f"  {nama:<40}{bobot:>8}  {ciri}")

print()
bobot, langka = pf.score(merchant(rng, mcc="9999", kriteria="XXX",
                                  kota="ANTAH BERANTAH", pan_len=12,
                                  pos=False, statis=False), k)
if langka:
    print("  Alasan yang ditampilkan untuk kasus terakhir:")
    print(f"    {pf.explain(langka)}")

print()
print("=" * 74)
print("KESIMPULAN")
print("=" * 74)
print()
print("  Model ini menangkap kombinasi, bukan nilai tunggal. Merchant")
print("  dengan satu ciri tidak biasa dibiarkan; yang punya tiga ciri")
print("  langka sekaligus ditandai.")
print()
print("  Bobotnya sedang dengan sengaja. Merchant sah yang memang tidak")
print("  biasa tetap ada, dan sinyal ini tidak boleh cukup sendirian.")
print()
print("  Yang membedakannya dari model buram: ia menyebut fitur mana")
print("  yang langka dan seberapa. Putusan yang tidak bisa dijelaskan")
print("  tidak punya tempat di sistem pembayaran.")
