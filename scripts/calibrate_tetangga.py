"""Seberapa timpang dua pedagang bersebelahan sebelum yang sepi dituduh.

calibrate_adjacency.py memilih ADJACENT_MIN_RATIO memakai tata letak
yang diakuinya sendiri "model kasar, bukan survei". Skrip ini mengukur
kasus yang benar-benar kami temui di lapangan: dua pedagang sah pada
koordinat yang sama persis — tukang es kelapa dan kotak donasi masjid
di sebelahnya, terekam GPS pada titik yang tak terbedakan.

Yang penting di sini bukan jaraknya, melainkan ketimpangan lalu
lintasnya. Aturan tetangga mensyaratkan pengamat >= 10% tetangga
terkuat. Warung ramai di sebelah lapak sepi melanggar itu secara
alami, tanpa ada penipuan sama sekali.

  python scripts/calibrate_tetangga.py
"""

import json
import math
import os
import random
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
from qshield import binding as bd  # noqa: E402
from qshield import emvco  # noqa: E402

random.seed(23)
PORT = 8912
DASAR = f"http://127.0.0.1:{PORT}/api/v1"

RAMAI = ("ID1026542245422", "Es Kelapa Boga Rasa")
SEPI = ("ID2023254132939", "RESTORASI MESJID")
TITIK = (-6.168600, 106.872500)

# Tetangga yang ramai terus bertambah SETELAH keduanya mapan — itu
# keadaan sehari-hari, bukan kasus sudut. Versi pertama skrip ini
# menumbuhkan keduanya bersamaan lalu menyimpulkan "aman" pada semua
# rasio; kesimpulan itu keliru karena skenarionya tidak pernah terjadi.
PEMANASAN = 5
LANJUTAN_RAMAI = 300
UKUR = 100
AKURASI = [(4, 8), (5, 12), (6, 20), (8, 26), (10, 32), (12, 39), (15, 50)]


def geser(lat, lng, u, t):
    return (lat + u / 111320, lng + t / (111320 * math.cos(math.radians(lat))))


def derau(lat, lng, akurasi):
    sigma = max(8.0, akurasi * 0.7)
    r = abs(random.gauss(0, sigma))
    a = random.uniform(0, 2 * math.pi)
    return geser(lat, lng, r * math.cos(a), r * math.sin(a))


def payload_untuk(nmid, nama):
    acct = emvco.build_tlv({"00": "ID.CO.QRIS.WWW", "01": "936000149000000001",
                            "02": nmid, "03": "UMI"})
    return emvco.build({"00": "01", "01": "11", "26": acct, "52": "5812",
                        "53": "360", "58": "ID", "59": nama,
                        "60": "JAKARTA", "61": "10110"})


def verify(body):
    req = urllib.request.Request(f"{DASAR}/verify", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=10).read())
    except urllib.error.HTTPError as e:
        return {"action": f"HTTP{e.code}", "reasons": []}


def hidupkan(akar, env):
    p = subprocess.Popen(
        [os.path.join(akar, ".venv/bin/uvicorn"), "qshield.api:app",
         "--host", "127.0.0.1", "--port", str(PORT)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=akar)
    for _ in range(40):
        try:
            urllib.request.urlopen(f"{DASAR}/health", timeout=1)
            return p
        except Exception:
            time.sleep(0.25)
    p.terminate()
    return None


def majukan(db, jam):
    c = sqlite3.connect(db)
    for tabel, kolom in [("bindings", ["first_seen", "last_seen", "registered_at"]),
                         ("observations", ["observed_at"])]:
        for k in kolom:
            try:
                c.execute(f"UPDATE {tabel} SET {k}=datetime({k},'-{jam} hours') "
                          f"WHERE {k} IS NOT NULL")
            except sqlite3.OperationalError:
                pass
    c.commit()
    c.close()


def kunjungi(nmid, nama, n, tanda, amin, amax):
    payload = payload_untuk(nmid, nama)
    hasil = []
    for i in range(n):
        akurasi = round(random.uniform(amin, amax), 1)
        lat, lng = derau(*TITIK, akurasi)
        hasil.append(verify({
            "payload": payload, "lat": lat, "lng": lng, "accuracy_m": akurasi,
            "device_anon_id": f"sim-{tanda}-{i:04d}",
            "device_integrity": {"mock_location": False, "rooted": False,
                                 "platform": "android"}}))
    return hasil


def jumlah_pengamat(db, nmid):
    c = sqlite3.connect(db)
    n = sum(r[0] for r in c.execute(
        "SELECT observer_count FROM bindings WHERE nmid=?", (nmid,)))
    c.close()
    return n


def main():
    akar = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print("=" * 74)
    print("PEDAGANG BERSEBELAHAN — kapan yang sepi dituduh menukar stiker")
    print("=" * 74)
    print(f"""
  '{RAMAI[1]}' dan '{SEPI[1]}' berdiri pada koordinat yang sama —
  keduanya sah, keduanya benar-benar ada. Keduanya dimapankan
  {PEMANASAN} pengamat, lalu yang ramai bertambah {LANJUTAN_RAMAI}
  pengamat lagi sementara yang sepi tidak. Setelah itu {UKUR}
  kunjungan ke yang sepi diukur.

  Tidak ada penipuan di mana pun dalam pengujian ini.
""")
    print(f"  {'akurasi GPS':>13}  {'proceed':>8} {'warn':>6} "
          f"{'step_up':>8} {'cooling':>8}   vonis")
    print("  " + "-" * 62)

    buntu = None
    for amin, amax in AKURASI:
        random.seed(23)
        tmp = tempfile.mkdtemp(prefix="qshield-tt-")
        db = os.path.join(tmp, "sim.db")
        env = dict(os.environ, QSHIELD_DB=db, QSHIELD_AUTH="off",
                   QSHIELD_RATE_LIMIT="off")
        proc = hidupkan(akar, env)
        if proc is None:
            print("server gagal hidup", file=sys.stderr)
            return 1
        try:
            kunjungi(*RAMAI, PEMANASAN, "warm-a", amin, amax)
            kunjungi(*SEPI, PEMANASAN, "warm-b", amin, amax)
            proc.terminate(); proc.wait(timeout=10)
            majukan(db, 48)
            proc = hidupkan(akar, env)
            if proc is None:
                return 1
            kunjungi(*RAMAI, LANJUTAN_RAMAI, "lanjut-a", amin, amax)
            sebelum = jumlah_pengamat(db, SEPI[0])
            hasil = kunjungi(*SEPI, UKUR, "ukur-b", amin, amax)
            sesudah = jumlah_pengamat(db, SEPI[0])
        finally:
            proc.terminate(); proc.wait(timeout=10)

        h = {}
        for d in hasil:
            h[d.get("action", "?")] = h.get(d.get("action", "?"), 0) + 1
        aneh = {k: v for k, v in h.items()
                if k not in ("proceed", "warn", "step_up", "cooling_off")}
        if aneh:
            print(f"  HARNESS RUSAK: {aneh}", file=sys.stderr)
            return 1
        berat = h.get("step_up", 0) + h.get("cooling_off", 0)
        vonis = "DITUDUH" if berat > UKUR * 0.5 else (
            "sebagian" if berat else "aman")
        print(f"  {amin:>4}-{amax:<3} m     {h.get('proceed',0):>8} "
              f"{h.get('warn',0):>6} {h.get('step_up',0):>8} "
              f"{h.get('cooling_off',0):>8}   {vonis}")
        if buntu is None and berat > UKUR * 0.5:
            buntu = (sebelum, sesudah)

    print(f"""
  KEBUNTUAN. Pada baris yang dituduh, pengamat merchant sepi bergerak
  dari {buntu[0]} ke {buntu[1]} setelah {UKUR} kunjungan sah — tidak
  bertambah sama sekali.

  Sebabnya melingkar: pengamatan pada binding yang dinilai anomali
  tidak dihitung, sedangkan binding itu dinilai anomali karena
  pengamatnya terlalu sedikit dibanding tetangga. Merchant tidak
  punya jalan keluar lewat pemakaian normal.

  Perhatikan arah kolomnya: makin AKURAT GPS-nya, makin parah. Galat
  besar justru mengaburkan jangkar sehingga aturan tetangga terpicu.
  Ketelitian memperburuk, bukan memperbaiki.

  Skrip ini TIDAK mengusulkan perbaikan. Invarian §5 mengunci rumus
  konsensus, dan setiap konstanta baru wajib dikalibrasi lebih dulu.
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
