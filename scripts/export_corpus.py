"""Ekspor korpus ciri merchant untuk evaluasi model kelangkaan.

Dipakai mengukur model terhadap merchant SUNGGUHAN yang dikumpulkan di
lapangan, bukan populasi sintetis. Keluarannya JSON ke stdout supaya
bisa diambil lewat `fly ssh console -C` tanpa perlu SFTP.

  python scripts/export_corpus.py > korpus.json

NMID TIDAK ikut keluar. Tiap merchant diberi nomor urut (m0001, m0002,
...) yang hanya berfungsi mengelompokkan ciri milik satu merchant.
Pemetaan nomor ke NMID tidak disimpan dan tidak bisa dibalik dari
berkas ini — lihat Invarian 8, tidak ada identitas yang keluar dari
sistem untuk keperluan analisis.
"""

import json
import os
import sqlite3
import sys

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.environ.get("QSHIELD_DB", os.path.join(AKAR, "qshield.db"))


def main() -> int:
    if not os.path.exists(DB):
        print(f"Basis data tidak ada: {DB}", file=sys.stderr)
        return 1
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    baris = conn.execute(
        "SELECT feature, value, nmid FROM merchant_feature "
        "ORDER BY nmid, feature").fetchall()

    samaran, per_merchant = {}, {}
    for r in baris:
        nm = r["nmid"]
        if nm not in samaran:
            samaran[nm] = f"m{len(samaran) + 1:04d}"
        per_merchant.setdefault(samaran[nm], {})[r["feature"]] = r["value"]

    dialek = {}
    for r in conn.execute(
            "SELECT pan_prefix, attribute, value, COUNT(DISTINCT nmid) n "
            "FROM issuer_dialect GROUP BY pan_prefix, attribute, value"):
        (dialek.setdefault(r["pan_prefix"], {})
               .setdefault(r["attribute"], {}))[r["value"]] = r["n"]
    conn.close()

    json.dump({"merchants": per_merchant, "dialect": dialek},
              sys.stdout, indent=1, sort_keys=True)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
