"""
Satukan jangkar yang terpecah karena bug penulisan berbasis sel geohash.

Sampai perbaikan di store.record(), sebuah pemindaian masuk ke jangkar
mana ditentukan sel geohash-7-nya, bukan jaraknya. Sel itu berukuran
~153 m, jadi dua pemindaian pedagang yang SAMA yang jatuh di sisi
berlawanan batas sel menjadi dua jangkar berbeda walau berjarak puluhan
meter — dan pengamatnya terpecah sehingga tidak satu pun mencapai
MIN_OBSERVERS.

Skrip ini membereskan data yang sudah telanjur begitu. Yang BARU tidak
akan terjadi lagi; ini hanya untuk yang lama.

Aturan penyatuannya sengaja sama dengan aturan penilaian: dua jangkar
digabung HANYA kalau NMID-nya sama DAN jaraknya <= ANCHOR_RADIUS_M.
Yang lebih jauh dibiarkan terpisah — pedagang bersebelahan memang harus
tetap terpisah, dan penyatuan yang terlalu rakus sama merusaknya dengan
pemecahan.

  python scripts/satukan_jangkar.py              # lihat saja, tidak menulis
  python scripts/satukan_jangkar.py --terapkan   # betulan menulis
"""

import os
import sys

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(AKAR, "src"))

from qshield import binding as bd  # noqa: E402
from qshield import geo  # noqa: E402
from qshield.store import Store  # noqa: E402

DB = os.environ.get("QSHIELD_DB", os.path.join(AKAR, "qshield.db"))


def pasangan(conn):
    """Kelompok jangkar satu NMID yang jaraknya <= ANCHOR_RADIUS_M."""
    per = {}
    for r in conn.execute(
            "SELECT id, nmid, merchant_name, lat, lng, observer_count, "
            "first_seen, last_seen FROM bindings ORDER BY id"):
        per.setdefault(r["nmid"], []).append(r)

    keluar = []
    for nmid, rows in per.items():
        if len(rows) < 2:
            continue
        # Kelompokkan transitif: A-B dekat, B-C dekat -> A,B,C satu
        # kelompok. Dipakai union-find sederhana karena jumlahnya kecil.
        induk = {r["id"]: r["id"] for r in rows}

        def akar(x):
            while induk[x] != x:
                induk[x] = induk[induk[x]]
                x = induk[x]
            return x

        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                d = geo.haversine_m(a["lat"], a["lng"], b["lat"], b["lng"])
                if d <= bd.ANCHOR_RADIUS_M:
                    induk[akar(a["id"])] = akar(b["id"])

        kel = {}
        for r in rows:
            kel.setdefault(akar(r["id"]), []).append(r)
        for anggota in kel.values():
            if len(anggota) > 1:
                keluar.append((nmid, anggota))
    return keluar


def satukan(conn, anggota, terapkan):
    """Gabungkan ke jangkar dengan pengamat terbanyak."""
    utama = max(anggota, key=lambda r: (r["observer_count"], -r["id"]))
    lain = [r for r in anggota if r["id"] != utama["id"]]

    nama = (utama["merchant_name"] or "-")[:30]
    print(f"\n  {nama}")
    print(f"    utama  id={utama['id']}  {utama['observer_count']} pengamat")
    for r in lain:
        d = geo.haversine_m(utama["lat"], utama["lng"], r["lat"], r["lng"])
        print(f"    digabung id={r['id']}  {r['observer_count']} pengamat"
              f"  ({d:.0f} m)")

    total = sum(r["observer_count"] for r in anggota)
    print(f"    hasil  {total} pengamat")

    if not terapkan:
        return total

    for r in lain:
        # Pengamatan dipindah APA ADANYA, termasuk stempel waktunya —
        # rentang pengamatan dan jejak kehadiran lintas-area membacanya.
        #
        # device_ref TIDAK bisa dihitung ulang: ia dilingkupi per binding
        # dan device_anon_id aslinya memang tidak pernah disimpan. Kalau
        # perangkat yang sama memindai lagi di jangkar utama, ia akan
        # membuat rujukan baru dan terhitung sekali lagi. Batasnya satu
        # pengamat per perangkat yang dipindahkan, dan itu dipilih sadar:
        # membuang barisnya berarti membuang stempel waktu yang benar.
        conn.execute("UPDATE observations SET binding_id = ? "
                     "WHERE binding_id = ?", (utama["id"], r["id"]))
        conn.execute(
            "INSERT INTO binding_ap (binding_id, ap_hash, seen_count) "
            "SELECT ?, ap_hash, seen_count FROM binding_ap WHERE binding_id = ? "
            "ON CONFLICT (binding_id, ap_hash) DO UPDATE SET "
            "seen_count = seen_count + excluded.seen_count",
            (utama["id"], r["id"]))
        conn.execute("DELETE FROM binding_ap WHERE binding_id = ?", (r["id"],))

    # Agregat dihitung di Python, bukan di SQL. Versi pertama berupa
    # subquery bersarang yang menjumlah termasuk barisnya sendiri —
    # betul sekilas, salah kalau dibaca dua kali.
    ids = ",".join("?" * len(anggota))
    ringkas = conn.execute(
        f"SELECT COALESCE(SUM(vouched_count), 0) v, "
        f"       COALESCE(SUM(anomaly_attempts), 0) a, "
        f"       MIN(first_seen) f, MAX(last_seen) l "
        f"FROM bindings WHERE id IN ({ids})",
        tuple(r["id"] for r in anggota)).fetchone()

    conn.execute(
        """UPDATE bindings SET
               observer_count = ?, vouched_count = ?,
               anomaly_attempts = ?, first_seen = ?, last_seen = ?
           WHERE id = ?""",
        (total, ringkas["v"], ringkas["a"], ringkas["f"], ringkas["l"],
         utama["id"]))

    for r in lain:
        conn.execute("DELETE FROM bindings WHERE id = ?", (r["id"],))
    return total


def main(argv):
    terapkan = "--terapkan" in argv
    if not os.path.exists(DB):
        print(f"Basis data tidak ada: {DB}", file=sys.stderr)
        return 1

    s = Store(DB)
    kelompok = pasangan(s.conn)

    print("=" * 70)
    print("JANGKAR TERPECAH" + ("" if terapkan else "  (mode lihat saja)"))
    print("=" * 70)
    print(f"\n  radius penyatuan: {bd.ANCHOR_RADIUS_M} m "
          f"(sama dengan yang dipakai penilaian)")
    if not kelompok:
        print("\n  Tidak ada yang perlu disatukan.")
        return 0

    if terapkan:
        s.conn.execute("BEGIN IMMEDIATE")
    try:
        for nmid, anggota in kelompok:
            satukan(s.conn, anggota, terapkan)
        if terapkan:
            s.conn.execute("COMMIT")
    except Exception:
        if terapkan:
            s.conn.execute("ROLLBACK")
        raise

    print(f"\n  {len(kelompok)} kelompok diproses.")
    if not terapkan:
        print("  Belum ada yang ditulis. Tambahkan --terapkan untuk menjalankan.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
