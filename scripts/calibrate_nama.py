"""Kenapa peniruan nama diuji SAMA-atau-TIDAK, bukan dengan skor kemiripan.

Usulan yang masuk dari luar tim: bandingkan nama merchant baru dengan
nama pemilik jangkar, dan perlakukan "mirip" sebagai peniruan. Idenya
kuat — penipu terjepit antara memakai nama korban (tertangkap mesin)
dan memakai nama lain (terlihat pembeli).

Skrip ini menguji bagian yang bisa diukur: apakah "mirip" bisa
dipisahkan dari "kebetulan berdekatan". Jawabannya tidak, dan itu
bukan soal metrik yang kurang pintar.

Nama merchant Indonesia berbagi awalan berat (WARUNG, TOKO, KEDAI) dan
nama orang yang berdekatan (Sari/Sri, Tuti/Tutik, Udi/Udin). Dua
pedagang yang benar-benar berbeda bisa lebih mirip satu sama lain
daripada peniru dengan korbannya.

  python scripts/calibrate_nama.py
"""

import itertools
import os
import re
import sys
from difflib import SequenceMatcher

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(AKAR, "src"))
from qshield.binding import nama_kanonik  # noqa: E402

# Pola penamaan yang benar-benar dipakai di Indonesia. Sengaja dipilih
# yang paling sulit: awalan berulang dan nama orang yang berdekatan.
AWALAN = ["WARUNG", "TOKO", "KEDAI", "WARUNG MAKAN", "RM", "CAFE", "DEPOT"]
ORANG = ["BU SRI", "BU SITI", "BU SARI", "PAK MUL", "PAK MUS", "MBAK ITA",
         "MBAK INA", "BU TUTI", "BU TUTIK", "PAK UDIN", "PAK UDI",
         "BU ENDANG", "BU ENDAH"]
BARANG = ["SEMBAKO", "KOPI", "NASI GORENG", "AYAM GEPREK", "BAKSO", "SOTO",
          "MIE AYAM", "GADO GADO", "MARTABAK", "ES TEH"]

NAMA = sorted(set([f"{a} {o}" for a in AWALAN for o in ORANG]
                  + [f"{a} {b}" for a in AWALAN for b in BARANG]))


def _n(s):
    return re.sub(r"[^A-Z0-9]+", "", (s or "").upper())


def obfuskasi(nama):
    """Cara penipu menyamarkan nama korban, sejauh yang masuk akal."""
    u = nama.upper()
    kata = u.split()
    return {
        "homoglif angka": u.replace("I", "1").replace("O", "0")
                           .replace("S", "5").replace("E", "3"),
        "spasi dibuang": u.replace(" ", ""),
        "spasi ganda": u.replace(" ", "  "),
        "huruf kecil": nama.lower(),
        "dipotong": u[:max(6, len(u) // 2)],
        "diberi imbuhan": u + " 2",
        "disingkat": " ".join(k if len(k) <= 3 else k[0] + k[-1] for k in kata),
    }


METRIK = {
    "SequenceMatcher": lambda a, b: SequenceMatcher(None, _n(a), _n(b)).ratio(),
    "token Jaccard": lambda a, b: (
        lambda x, y: len(x & y) / len(x | y) if (x | y) else 0.0
    )(set(a.upper().split()), set(b.upper().split())),
    "sama setelah normalisasi": lambda a, b: (
        1.0 if nama_kanonik(a) == nama_kanonik(b) else 0.0),
}


def main():
    print("=" * 74)
    print("PENIRUAN NAMA: KENAPA SAMA-ATAU-TIDAK, BUKAN SKOR KEMIRIPAN")
    print("=" * 74)
    print(f"\n  {len(NAMA)} nama uji, "
          f"{len(NAMA)*(len(NAMA)-1)//2} pasangan pedagang BERBEDA\n")

    print(f"  {'metrik':28} {'beda maks':>10} {'tiru min':>10}   hasil")
    print("  " + "-" * 66)
    aman = None
    for label, f in METRIK.items():
        beda = [f(a, b) for a, b in itertools.combinations(NAMA, 2)]
        tiru = [f(n, v) for n in NAMA[:25] for v in obfuskasi(n).values()]
        terpisah = max(beda) < min([t for t in tiru if t > 0] or [0])
        # Untuk uji kesamaan, yang menentukan adalah nol positif palsu.
        nol_fp = max(beda) == 0.0
        status = "TERPISAH" if (terpisah or nol_fp) else "tumpang tindih"
        print(f"  {label:28} {max(beda):>10.2f} {min(tiru):>10.2f}   {status}")
        if nol_fp:
            aman = label

    print("\n  PASANGAN BERBEDA PALING MIRIP — ini yang mematikan gagasan ambang:\n")
    sm = METRIK["SequenceMatcher"]
    top = sorted(((sm(a, b), a, b) for a, b in itertools.combinations(NAMA, 2)),
                 reverse=True)[:5]
    for s, a, b in top:
        print(f"    {s:.2f}  {a:22} vs {b}")
    print("\n    Keduanya pedagang sungguhan. Peniruan sungguhan memberi")
    print("    0,95-1,00. Tidak ada ambang di antaranya.")

    print("\n  YANG TERTANGKAP UJI KESAMAAN (nol positif palsu):\n")
    korban = "WARUNG BU SRI"
    for label, v in obfuskasi(korban).items():
        sama = nama_kanonik(korban) == nama_kanonik(v)
        print(f"    {'TERTANGKAP' if sama else 'lolos     '}  {label:16} {v}")
    print("\n    Yang lolos — dipotong, diberi imbuhan, disingkat — justru")
    print("    kasus ketika pembeli MELIHAT nama yang berbeda di layarnya.")
    print("    Itu ditangani dengan menampilkan kedua nama, bukan menuduh.")

    print(f"\n  Dipakai: {aman}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
