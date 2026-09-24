"""Evaluasi model kelangkaan terhadap korpus merchant SUNGGUHAN.

`calibrate_rarity.py` menyetel ambang memakai populasi sintetis yang
meniru sebaran merchant Indonesia. Skrip ini menguji setelan itu
terhadap merchant yang benar-benar dipindai tim di lapangan.

Metodenya leave-one-out: tiap merchant dinilai terhadap korpus yang
dibentuk 121 merchant lainnya — merchant itu sendiri tidak ikut
membentuk sebaran yang menilainya. Setiap merchant di sini SAH, jadi
setiap yang tertandai adalah positif palsu.

  python scripts/export_corpus.py > korpus.json     # di mesin produksi
  python scripts/evaluate_rarity.py korpus.json
"""

import json
import os
import sys

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(AKAR, "src"))

from qshield import profile as pf  # noqa: E402


def korpus_tanpa(merchants: dict, kecuali: str) -> dict:
    """Sebaran ciri dari semua merchant kecuali satu."""
    korpus = {"_total": 0}
    for mid, ciri in merchants.items():
        if mid == kecuali:
            continue
        korpus["_total"] += 1
        for f, v in ciri.items():
            korpus.setdefault(f, {})[v] = korpus.setdefault(f, {}).get(v, 0) + 1
    return korpus


def jalankan(merchants: dict, ambang: float, min_fitur: int):
    """(jumlah tertandai, berapa kali tiap fitur disebut langka)."""
    t0, n0 = pf.RARE_THRESHOLD, pf.MIN_RARE_FEATURES
    pf.RARE_THRESHOLD, pf.MIN_RARE_FEATURES = ambang, min_fitur
    try:
        tertandai, penyebab, langka_per_merchant = 0, {}, []
        for mid, ciri in merchants.items():
            bobot, langka = pf.score_features(ciri, korpus_tanpa(merchants, mid))
            if bobot:
                tertandai += 1
                for f in langka:
                    penyebab[f.feature] = penyebab.get(f.feature, 0) + 1
            langka_per_merchant.append(len(langka))
        return tertandai, penyebab, langka_per_merchant
    finally:
        pf.RARE_THRESHOLD, pf.MIN_RARE_FEATURES = t0, n0


def main(argv) -> int:
    if not argv:
        print(__doc__)
        return 2
    data = json.load(open(argv[0]))
    merchants = data["merchants"]
    n = len(merchants)

    print("=" * 74)
    print("KORPUS LAPANGAN")
    print("=" * 74)
    print(f"\n  {n} merchant sungguhan, dipindai tim di lapangan.")
    print(f"  Ambang MIN_CORPUS = {pf.MIN_CORPUS} — terlampaui.\n")

    print("  Kardinalitas tiap fitur (jumlah nilai berbeda):\n")
    print(f"  {'fitur':<14}{'nilai':>7}{'rata2 merchant/nilai':>24}   catatan")
    print("  " + "-" * 70)
    mati = []
    for f in pf.FEATURES:
        nilai = {}
        for ciri in merchants.values():
            v = ciri.get(f, "?")
            nilai[v] = nilai.get(v, 0) + 1
        rata = n / len(nilai)
        if len(nilai) < 2:
            catatan = "SERAGAM — tidak dipakai menilai"
            mati.append(f)
        elif rata < n * pf.RARE_THRESHOLD:
            catatan = "hampir semua nilainya di bawah ambang langka"
        else:
            catatan = ""
        print(f"  {f:<14}{len(nilai):>7}{rata:>24.1f}   {catatan}")

    hidup = [f for f in pf.FEATURES if f not in mati]
    print(f"\n  Fitur yang benar-benar menilai: {len(hidup)} dari "
          f"{len(pf.FEATURES)} — {', '.join(hidup)}")
    print(f"  Sisanya seragam di seluruh korpus, dan dilewati oleh penjaga")
    print(f"  'len(terlihat) < 2' di profile.score_features().")

    print("\n" + "=" * 74)
    print("LEAVE-ONE-OUT PADA SETELAN YANG BERLAKU SEKARANG")
    print("=" * 74)
    tertandai, penyebab, dist = jalankan(
        merchants, pf.RARE_THRESHOLD, pf.MIN_RARE_FEATURES)
    print(f"\n  RARE_THRESHOLD    {pf.RARE_THRESHOLD}")
    print(f"  MIN_RARE_FEATURES {pf.MIN_RARE_FEATURES}")
    print(f"\n  Merchant sah tertandai: {tertandai} dari {n} "
          f"({tertandai / n * 100:.2f}%)")
    if penyebab:
        print("\n  Fitur yang paling sering disebut langka:\n")
        for f, c in sorted(penyebab.items(), key=lambda x: -x[1]):
            print(f"    {pf.LABEL.get(f, f):<22} {c:>4} kali")

    _, _, dist = jalankan(merchants, pf.RARE_THRESHOLD, 0)
    sebaran = {}
    for k in dist:
        sebaran[k] = sebaran.get(k, 0) + 1
    print("\n  Sebaran jumlah fitur langka per merchant sah:\n")
    for k in sorted(sebaran):
        bar = "#" * min(50, sebaran[k])
        tanda = "  <- tertandai" if k >= pf.MIN_RARE_FEATURES else ""
        print(f"    {k} fitur langka  {sebaran[k]:>4} merchant  {bar}{tanda}")

    print("\n" + "=" * 74)
    print("SAPUAN AMBANG PADA KORPUS NYATA")
    print("=" * 74)
    print(f"\n  {'ambang':>8}{'min fitur':>11}{'sah tertandai':>16}"
          f"{'jumlah':>9}")
    print("  " + "-" * 44)
    for ambang in (0.02, 0.05, 0.08, 0.12):
        for min_f in (3, 4):
            t, _, _ = jalankan(merchants, ambang, min_f)
            tanda = ""
            if (abs(ambang - pf.RARE_THRESHOLD) < 1e-9
                    and min_f == pf.MIN_RARE_FEATURES):
                tanda = "   <- berlaku sekarang"
            print(f"  {ambang:>8.2f}{min_f:>11}{t / n * 100:>15.2f}%"
                  f"{t:>9}{tanda}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
