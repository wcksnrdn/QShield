"""
Impor korpus payload QRIS — belajar bentuk kode, bukan lokasi.

Mengumpulkan QRIS dari berbagai kota itu benar dan dibutuhkan: dialek
penerbit, sebaran kategori usaha, dan format penulisan kota hanya bisa
dipelajari dari keragaman yang nyata.

Tapi memindainya lewat `/api/v1/verify` mencampurkan dua hal yang
berbeda. Payload-nya benar di mana pun ia dipindai; LOKASINYA tidak.
Memindai QR Samarinda sambil duduk di Jakarta mengajarkan sistem bahwa
merchant di titik Jakarta itu menyebut kotanya Samarinda — dan itu
bukan sekadar tidak berguna, itu salah.

Skrip ini memisahkannya. Yang dipelajari:

    dialek penerbit        cara tiap PJP menyusun payload
    sebaran ciri merchant  kategori usaha, skala, panjang akun

Yang TIDAK disentuh sama sekali:

    bindings               jangkar merchant
    observations           konsensus pengamat
    area_city              kota yang berlaku di suatu wilayah

  python scripts/import_corpus.py payloads.txt      satu payload per baris
  python scripts/import_corpus.py --from-field      dari fielddata.jsonl
  python scripts/import_corpus.py --status          apa yang sudah dipelajari
  python scripts/import_corpus.py --purge-area      bersihkan area_city
"""

import json
import os
import sys

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(AKAR, "src"))
DB = os.environ.get("QSHIELD_DB", os.path.join(AKAR, "qshield.db"))


def store():
    from qshield.store import Store
    return Store(DB)


def _muat(argv):
    """Kumpulkan payload dari berkas atau dari data survei."""
    if "--from-field" in argv:
        berkas = os.environ.get(
            "QSHIELD_FIELD_FILE", os.path.join(AKAR, "fielddata.jsonl"))
        if not os.path.exists(berkas):
            print(f"{berkas} tidak ada.", file=sys.stderr)
            return []
        with open(berkas) as f:
            return [json.loads(b)["payload"] for b in f if b.strip()]

    berkas = next((a for a in argv if not a.startswith("--")), None)
    if not berkas:
        return []
    if not os.path.exists(berkas):
        print(f"{berkas} tidak ada.", file=sys.stderr)
        return []
    with open(berkas) as f:
        return [b.strip() for b in f if b.strip() and not b.startswith("#")]


def cmd_import(argv):
    from qshield import emvco

    payloads = _muat(argv)
    if not payloads:
        print(__doc__)
        return 2

    s = store()
    masuk = gagal = ulang = 0
    terlihat = set()
    rusak = []

    for p in payloads:
        try:
            parsed = emvco.parse(p)
        except emvco.ParseError as exc:
            gagal += 1
            rusak.append((p[:44], str(exc)))
            continue
        nmid = parsed.nmid
        if not nmid:
            gagal += 1
            rusak.append((p[:44], "tidak ada Merchant ID"))
            continue
        if nmid in terlihat:
            ulang += 1
            continue
        terlihat.add(nmid)

        s.learn_dialect(parsed, nmid)
        s.learn_features(parsed, nmid)
        masuk += 1

    print("=" * 70)
    print("IMPOR KORPUS")
    print("=" * 70)
    print()
    print(f"  payload dibaca   : {len(payloads)}")
    print(f"  merchant baru    : {masuk}")
    print(f"  NMID berulang    : {ulang}")
    print(f"  gagal diurai     : {gagal}")
    for p, e in rusak[:5]:
        print(f"      {p}...  {e}")
    print()
    print("  bindings, observations, dan area_city TIDAK disentuh.")
    s.close()
    return cmd_status([])


def cmd_status(argv):
    from qshield import binding as bd
    from qshield import profile as pf

    s = store()
    korpus = s.feature_corpus()
    total = korpus.get("_total", 0)

    print()
    print("=" * 70)
    print("APA YANG SUDAH DIPELAJARI")
    print("=" * 70)
    print()
    print(f"  Korpus ciri merchant: {total} NMID "
          f"(model kelangkaan aktif pada {pf.MIN_CORPUS})")
    print()
    for f in pf.FEATURES:
        nilai = korpus.get(f)
        if not nilai:
            continue
        urut = sorted(nilai.items(), key=lambda x: -x[1])
        isi = ", ".join(f"{v}={n}" for v, n in urut[:5])
        lebih = f" (+{len(urut) - 5})" if len(urut) > 5 else ""
        print(f"    {pf.LABEL.get(f, f):<22} {len(urut):>2} nilai  {isi}{lebih}")

    baris = s.conn.execute(
        "SELECT pan_prefix, COUNT(DISTINCT nmid) n FROM issuer_dialect "
        "GROUP BY pan_prefix ORDER BY n DESC").fetchall()
    print()
    print(f"  Dialek penerbit: {len(baris)} penyelenggara")
    for r in baris:
        cukup = r["n"] >= bd.ISSUER_MIN_NMIDS
        print(f"    {r['pan_prefix']}  {r['n']:>3} NMID   "
              f"{'profil terbentuk' if cukup else 'belum cukup'}")
    if not baris:
        print("    (belum ada — payload tanpa nomor akun tidak terekam)")

    print()
    kurang = max(0, pf.MIN_CORPUS - total)
    if kurang:
        print(f"  Butuh {kurang} merchant lagi agar model kelangkaan aktif.")
    else:
        print("  Model kelangkaan sudah aktif.")
    s.close()
    return 0


def cmd_purge_area(argv):
    """Kosongkan pengetahuan wilayah yang terkumpul dari pemindaian gambar."""
    s = store()
    n = s.conn.execute("SELECT COUNT(*) n FROM area_city").fetchone()["n"]
    if "--yes" not in argv:
        print(f"Akan menghapus {n} baris dari area_city.")
        print()
        print("Ini yang perlu dilakukan kalau korpus dikumpulkan dengan")
        print("memindai QR dari gambar: pengetahuan wilayah yang terbentuk")
        print("darinya salah, karena kotanya milik merchant sementara")
        print("koordinatnya milik tempat kalian memindai.")
        print()
        print("Jalankan ulang dengan --yes untuk melanjutkan.")
        s.close()
        return 1
    s.conn.execute("DELETE FROM area_city")
    print(f"{n} baris dihapus. Pengetahuan wilayah dimulai dari nol.")
    print()
    print("Isi ulang HANYA dengan pemindaian di tempat merchant berada.")
    s.close()
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--status" in argv:
        sys.exit(cmd_status(argv))
    if "--purge-area" in argv:
        sys.exit(cmd_purge_area(argv))
    if not argv:
        print(__doc__)
        sys.exit(0)
    sys.exit(cmd_import(argv))
