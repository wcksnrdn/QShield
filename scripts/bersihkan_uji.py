"""Buang jejak pemindaian UJI dari korpus.

Menguji server berarti memindai, dan tiap pemindaian yang diterima
menambah pengamat. Perangkat uji bukan orang yang benar-benar berdiri
di depan stiker, jadi ia menggelembungkan konsensus dengan sesuatu yang
tidak nyata — dan konsensus itu satu-satunya dasar sebuah stiker
disebut `verified`.

Sudah dibutuhkan tiga kali. Dijadikan alat supaya tidak ditulis ulang
setiap kali dengan bentuk yang sedikit berbeda.

  python scripts/bersihkan_uji.py --lihat uji-01 uji-02
  python scripts/bersihkan_uji.py --terapkan uji-01 uji-02
  python scripts/bersihkan_uji.py --terapkan --reset-anomali uji-01

`--reset-anomali` juga menolkan penghitung "jangkar ini jadi sasaran"
dan mengosongkan buku tantangan. Pakai itu setelah menguji skenario
stiker palsu: yang memicunya kita sendiri, dan pedagang sungguhan di
jangkar itu tidak boleh menanggungnya.
"""

import hashlib
import os
import sqlite3
import sys

DB = os.environ.get("QSHIELD_DB", "qshield.db")


def main(argv):
    terapkan = "--terapkan" in argv
    reset = "--reset-anomali" in argv
    perangkat = [a for a in argv if not a.startswith("--")]
    if not perangkat and not reset:
        print(__doc__)
        return 2

    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    baris = db.execute(
        "SELECT value FROM meta WHERE key = 'device_salt'").fetchone()
    if not baris:
        print("garam perangkat tidak ada — basis data ini belum terpakai",
              file=sys.stderr)
        return 1
    garam = baris["value"]

    temuan = []
    for b in db.execute("SELECT id, nmid, merchant_name FROM bindings").fetchall():
        for dev in perangkat:
            # device_ref dilingkupi per-binding, jadi hash-nya harus
            # dihitung ulang untuk setiap binding — tidak bisa dicari
            # dengan LIKE.
            ref = hashlib.sha256(
                f"{garam}|{b['id']}|{dev}".encode("utf-8")).hexdigest()
            ada = db.execute(
                "SELECT COUNT(*) n FROM observations "
                "WHERE binding_id = ? AND device_ref = ?",
                (b["id"], ref)).fetchone()["n"]
            if ada:
                temuan.append((b, dev, ref, ada))

    print("=" * 66)
    print("JEJAK PEMINDAIAN UJI")
    print("=" * 66)
    if temuan:
        print()
        for b, dev, _ref, n in temuan:
            print(f"  {(b['merchant_name'] or b['nmid'])[:28]:29} {dev:24} {n}")
    else:
        print("\n  Tidak ada pengamatan dari perangkat yang disebut.")

    if reset:
        n_a = db.execute("SELECT COUNT(*) n FROM bindings "
                         "WHERE anomaly_attempts > 0").fetchone()["n"]
        n_t = db.execute("SELECT COUNT(*) n FROM anchor_challenge").fetchone()["n"]
        print(f"\n  jangkar dengan penghitung serangan : {n_a}")
        print(f"  baris buku tantangan               : {n_t}")

    if not terapkan:
        print("\n  Belum ada yang diubah. Tambahkan --terapkan.\n")
        return 0

    hapus = 0
    for b, _dev, ref, _n in temuan:
        c = db.execute("DELETE FROM observations "
                       "WHERE binding_id = ? AND device_ref = ?",
                       (b["id"], ref)).rowcount
        if c:
            db.execute("UPDATE bindings SET observer_count = observer_count - ? "
                       "WHERE id = ?", (c, b["id"]))
            hapus += c
    if reset:
        db.execute("UPDATE bindings SET anomaly_attempts = 0, "
                   "last_anomaly_at = NULL WHERE anomaly_attempts > 0")
        db.execute("DELETE FROM anchor_challenge")
    # Binding yang lahir HANYA dari perangkat uji tidak punya alasan ada.
    kosong = db.execute(
        "DELETE FROM bindings WHERE observer_count <= 0 "
        "AND registered_at IS NULL").rowcount
    db.commit()

    print(f"\n  pengamatan uji dihapus : {hapus}")
    print(f"  binding tanpa pengamat : {kosong}")
    print("\n  KORPUS SESUDAH:")
    for r in db.execute(
            "SELECT merchant_name m, nmid, observer_count o, anomaly_attempts a, "
            "ROUND((julianday(last_seen)-julianday(first_seen))*24,1) j "
            "FROM bindings ORDER BY o DESC"):
        mapan = r["o"] >= 3 and (r["j"] or 0) >= 24
        print(f"    {(r['m'] or r['nmid'])[:26]:27} {r['o']:>4} pengamat  "
              f"{r['a']} anomali  {'VERIFIED' if mapan else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
