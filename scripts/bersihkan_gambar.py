"""Hapus pengetahuan LOKASI yang terbentuk dari pemindaian gambar.

Sejak Keputusan 54 aturannya ditegakkan di kode: pemindaian dengan
location_source="replay" tidak membentuk binding, kota wilayah, atau
sidik jari WiFi. Skrip ini membersihkan yang terlanjur masuk SEBELUM
aturan itu ada.

Yang DIPERTAHANKAN: issuer_dialect dan merchant_feature. Bentuk payload
tidak berubah karena difoto, dan keragaman penerbit justru yang paling
sulit dikumpulkan sendiri di lapangan — itu alasan QRIS internet
dikumpulkan sejak awal.

Yang DIHAPUS: binding, pengamatan, sidik jari WiFi, dan kota wilayah
yang berasal dari pemindaian itu.

Penanda yang dipakai: kota tertulis di stiker berjauhan dari tempat
pemindaian. Bukan tebakan — QRIS yang dipindai di lapangan menuliskan
kota yang cocok dengan tempatnya.

  python scripts/bersihkan_gambar.py            lihat saja, tidak mengubah
  python scripts/bersihkan_gambar.py --terapkan benar-benar menghapus
"""

import os
import sqlite3
import sys
from datetime import datetime

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(AKAR, "src"))
from qshield import binding as bd  # noqa: E402
from qshield import geo  # noqa: E402

# Wilayah pemindaian -> kota yang wajar tertulis di stiker. Longgar
# dengan sengaja: yang dicari kesalahan yang mencolok, bukan ketepatan.
WILAYAH = {
    "qqguz": {"JAKARTA", "JAKARTA UTARA", "JAKARTA PUSAT", "JAKARTA BARAT",
              "JAKARTA TIMUR", "JAKARTA SELATAN", "JAKARTA TI", "JAKARTA UT",
              "JAKARTA SE", "JAKARTA BA", "JAKARTA PU"},
    "qqu8c": {"BANDUNG", "KOTA BANDUNG", "CIMAHI", "BANDUNG BARAT"},
}


def _umur_jam(r) -> float:
    try:
        f = datetime.fromisoformat(str(r["first_seen"]).replace("Z", "+00:00"))
        l = datetime.fromisoformat(str(r["last_seen"]).replace("Z", "+00:00"))
        return (l - f).total_seconds() / 3600
    except Exception:
        return 0.0


def main(argv):
    terapkan = "--terapkan" in argv
    db_path = os.path.join(AKAR, "qshield.db")
    if not os.path.exists(db_path):
        print("qshield.db tidak ada", file=sys.stderr)
        return 1

    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row

    # Binding MAPAN tidak mungkin lahir dari pemindaian gambar: sebuah
    # burst gambar menghasilkan satu pengamat dengan riwayat nol jam.
    # Penjaga ini wajib — versi pertama skrip ini nyaris menghapus
    # binding demo dengan 149 pengamat dan riwayat 181 hari.
    def lahir_dari_burst(r):
        return r["observer_count"] <= 2 and _umur_jam(r) < 1.0

    tersangka = []
    for r in db.execute("SELECT id, nmid, merchant_name, lat, lng, geohash_7, "
                        "observer_count, first_seen, last_seen FROM bindings"):
        gh5 = geo.encode(r["lat"], r["lng"], bd.AREA_CITY_PRECISION)
        wajar = WILAYAH.get(gh5)
        if wajar is None:
            continue
        # Kota dicari pada geohash BINDING ITU SENDIRI. Satu NMID bisa
        # punya baris di beberapa wilayah, dan mengambil sembarang baris
        # membuat binding yang sah tertuduh oleh baris milik tempat lain.
        kota = db.execute(
            "SELECT city FROM area_city WHERE nmid = ? AND geohash_5 = ?",
            (r["nmid"], gh5)).fetchone()
        kota = (kota["city"] or "").strip().upper() if kota else ""
        if kota and kota not in wajar and lahir_dari_burst(r):
            tersangka.append((dict(r), kota))

    print("=" * 70)
    print("PEMINDAIAN GAMBAR YANG MEMBENTUK PENGETAHUAN LOKASI")
    print("=" * 70)
    if not tersangka:
        print("\n  Tidak ada. Korpus bersih.\n")
        return 0

    print(f"\n  {'merchant':28} {'kota stiker':18} wilayah pindai")
    print("  " + "-" * 64)
    for r, kota in tersangka:
        gh5 = geo.encode(r["lat"], r["lng"], bd.AREA_CITY_PRECISION)
        print(f"  {(r['merchant_name'] or r['nmid'])[:27]:28} {kota[:17]:18} {gh5}")

    # Aturan kedua, terpisah: baris area_city yang kotanya tidak masuk
    # akal untuk wilayahnya. Sumbernya bisa apa saja — termasuk skrip
    # diagnostik yang tidak sengaja menembak basis data kerja. Yang
    # dihapus HANYA barisnya, tidak pernah bindingnya.
    kota_ngawur = []
    for r in db.execute("SELECT rowid, geohash_5, city, nmid FROM area_city"):
        wajar = WILAYAH.get(r["geohash_5"])
        if wajar and (r["city"] or "").strip().upper() not in wajar:
            kota_ngawur.append(dict(r))
    milik_tersangka = {r["nmid"] for r, _ in tersangka}
    kota_ngawur = [k for k in kota_ngawur if k["nmid"] not in milik_tersangka]
    if kota_ngawur:
        print("\n  Baris kota yang tidak masuk akal untuk wilayahnya")
        print("  (hanya barisnya yang dihapus, bindingnya tidak disentuh):")
        for k in kota_ngawur:
            print(f"    {k['geohash_5']}  {k['city']:16} {k['nmid']}")

    ids = [r["id"] for r, _ in tersangka]
    nmids = [r["nmid"] for r, _ in tersangka]
    tanda_i = ",".join("?" * len(ids))
    tanda_n = ",".join("?" * len(nmids))

    hitung = {
        "bindings": len(ids),
        "observations": db.execute(
            f"SELECT COUNT(*) n FROM observations WHERE binding_id IN ({tanda_i})",
            ids).fetchone()["n"],
        "binding_ap": db.execute(
            f"SELECT COUNT(*) n FROM binding_ap WHERE binding_id IN ({tanda_i})",
            ids).fetchone()["n"],
        "area_city": db.execute(
            f"SELECT COUNT(*) n FROM area_city WHERE nmid IN ({tanda_n})",
            nmids).fetchone()["n"],
    }
    simpan = {
        "issuer_dialect": db.execute(
            f"SELECT COUNT(*) n FROM issuer_dialect WHERE nmid IN ({tanda_n})",
            nmids).fetchone()["n"],
        "merchant_feature": db.execute(
            f"SELECT COUNT(*) n FROM merchant_feature WHERE nmid IN ({tanda_n})",
            nmids).fetchone()["n"],
    }

    print("\n  DIHAPUS — pengetahuan lokasi:")
    for t, n in hitung.items():
        print(f"    {t:20} {n:>5} baris")
    print("\n  DIPERTAHANKAN — pengetahuan payload:")
    for t, n in simpan.items():
        print(f"    {t:20} {n:>5} baris")

    if not terapkan:
        print("\n  Belum ada yang diubah. Jalankan ulang dengan --terapkan.\n")
        return 0

    cadangan = os.path.join(
        AKAR, f"qshield.db.cadangan-{datetime.now():%Y%m%d-%H%M%S}")
    # VACUUM INTO, bukan menyalin berkasnya.
    #
    # Basis data ini berjalan dengan WAL: perubahan terbaru bisa masih
    # berada di qshield.db-wal dan belum masuk ke berkas utama. Menyalin
    # qshield.db saja menghasilkan cadangan yang SOBEK — merekam keadaan
    # lama sambil tampak utuh. Sudah terjadi: sebuah cadangan memuat 13
    # binding padahal basis datanya berisi 8, dan selisih itu baru
    # ketahuan saat dibandingkan.
    db.execute("VACUUM INTO ?", (cadangan,))
    db.close()
    db = sqlite3.connect(db_path)

    db.execute(f"DELETE FROM observations WHERE binding_id IN ({tanda_i})", ids)
    db.execute(f"DELETE FROM binding_ap WHERE binding_id IN ({tanda_i})", ids)
    db.execute(f"DELETE FROM area_city WHERE nmid IN ({tanda_n})", nmids)
    db.execute(f"DELETE FROM anchor_challenge WHERE nmid IN ({tanda_n})", nmids)
    db.execute(f"DELETE FROM bindings WHERE id IN ({tanda_i})", ids)
    for k in kota_ngawur:
        db.execute("DELETE FROM area_city WHERE rowid = ?", (k["rowid"],))
    db.commit()
    db.close()

    print(f"\n  Selesai. Cadangan: {os.path.basename(cadangan)}")
    print("  Kembalikan dengan: cp <cadangan> qshield.db\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
