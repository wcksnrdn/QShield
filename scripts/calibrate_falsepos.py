"""Berapa sering pedagang jujur keliru dicurigai.

Ini angka yang menentukan apakah Q-Shield layak dipakai. Deteksi yang
menangkap semua penipuan tapi ikut menuduh pedagang sah tidak akan
pernah dipasang PJP mana pun — kasir menolaknya lebih dulu.

Kami sudah pernah kena: tukang es kelapa yang sah direspons "butuh
verifikasi", dan penyebabnya bug atribusi anomali, bukan penyetelan
ambang. Skrip ini ada supaya kejadian seperti itu terukur, bukan
ketahuan dari kejengkelan pengguna.

Jalur kodenya sungguhan — HTTP ke API yang sama dengan yang dihubungi
HP — dengan QSHIELD_DB dialihkan ke berkas sementara, supaya korpus
lapangan tidak tersentuh.

  python scripts/calibrate_falsepos.py
"""

import json
import math
import os
import random
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
from qshield import emvco  # noqa: E402

random.seed(23)

PORT = 8911
DASAR = f"http://127.0.0.1:{PORT}/api/v1"

# Dua merchant yang sungguh dipindai di lapangan, dengan koordinat
# aslinya. Disimulasikan di sini, bukan disalin dari qshield.db, supaya
# skrip ini bisa dijalankan ulang kapan pun tanpa bergantung pada isi
# basis data saat itu.
MERCHANT = [
    ("ID1026542245422", "Es Kelapa Boga Rasa", -6.168600, 106.872500),
    ("ID2023254132939", "RESTORASI MESJID",    -6.168600, 106.872500),
]

PEMANASAN = 5          # pengamatan untuk memapankan binding (ambang 3)
KUNJUNGAN = 300        # kunjungan sah yang diukur, per merchant
SIGMA_GPS = 8.0        # sebaran galat satu pembacaan GPS, meter


def geser(lat, lng, utara, timur):
    return (lat + utara / 111320,
            lng + timur / (111320 * math.cos(math.radians(lat))))


def derau_gps(lat, lng, akurasi):
    """Sebaran posisi yang sepadan dengan akurasi yang dilaporkan.

    HP melaporkan akurasi sebagai radius keyakinan 68%, jadi simpangan
    sebenarnya kira-kira sebesar angka itu — bukan jauh lebih kecil.
    Memakai sigma tetap akan membuat hasilnya terlalu bagus.
    """
    sigma = max(SIGMA_GPS, akurasi * 0.7)
    r = abs(random.gauss(0, sigma))
    a = random.uniform(0, 2 * math.pi)
    return geser(lat, lng, r * math.cos(a), r * math.sin(a))


def payload_untuk(nmid, nama):
    acct = emvco.build_tlv({"00": "ID.CO.QRIS.WWW",
                            "01": "936000149000000001",
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
        return {"action": f"HTTP{e.code}", "verdict": "-", "reasons": []}


def hidupkan(akar, env):
    proc = subprocess.Popen(
        [os.path.join(akar, ".venv/bin/uvicorn"), "qshield.api:app",
         "--host", "127.0.0.1", "--port", str(PORT)],
        env=env, cwd=akar, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        try:
            urllib.request.urlopen(f"{DASAR}/health", timeout=1)
            return proc
        except Exception:
            time.sleep(0.25)
    proc.terminate()
    return None


def majukan_waktu(db, jam):
    """Mundurkan seluruh cap waktu supaya binding tampak sudah berumur.

    Ambang umur 24 jam tidak bisa ditunggu dalam simulasi, dan
    menurunkannya khusus untuk pengujian berarti yang diukur bukan lagi
    sistem yang dikirim. Jadi yang digeser waktunya, bukan ambangnya.
    """
    import sqlite3
    c = sqlite3.connect(db)
    for tabel, kolom in [("bindings", ["first_seen", "last_seen", "registered_at"]),
                         ("observations", ["observed_at"])]:
        for k in kolom:
            try:
                c.execute(f"UPDATE {tabel} SET {k} = "
                          f"datetime({k}, '-{jam} hours') WHERE {k} IS NOT NULL")
            except sqlite3.OperationalError:
                pass
    c.commit()
    c.close()


def main():
    tmp = tempfile.mkdtemp(prefix="qshield-fp-")
    db = os.path.join(tmp, "sim.db")
    env = dict(os.environ, QSHIELD_DB=db, QSHIELD_AUTH="off",
           QSHIELD_RATE_LIMIT="off")
    akar = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = hidupkan(akar, env)
    if proc is None:
        print("server simulasi gagal hidup", file=sys.stderr)
        return 1
    try:
        # Fase 1 — memapankan binding, lalu waktunya dimajukan 48 jam.
        for nmid, nama, lat, lng in MERCHANT:
            payload = payload_untuk(nmid, nama)
            for i in range(PEMANASAN):
                akurasi = round(random.uniform(6, 14), 1)
                plat, plng = derau_gps(lat, lng, akurasi)
                verify({"payload": payload, "lat": plat, "lng": plng,
                        "accuracy_m": akurasi,
                        "device_anon_id": f"warm-{nmid[-4:]}-{i:03d}",
                        "device_integrity": {"mock_location": False,
                                             "rooted": False,
                                             "platform": "android"}})
        proc.terminate(); proc.wait(timeout=10)
        majukan_waktu(db, 48)
        proc = hidupkan(akar, env)
        if proc is None:
            print("server simulasi gagal hidup setelah waktu dimajukan",
                  file=sys.stderr)
            return 1

        print("=" * 72)
        print("FALSE POSITIVE — pedagang jujur, kunjungan wajar")
        print("=" * 72)
        print(f"\n  binding dimapankan {PEMANASAN} pengamat, lalu berumur 48 jam")
        print(f"  {KUNJUNGAN} kunjungan diukur per merchant, perangkat berbeda-beda,")
        print(f"  galat GPS sigma >= {SIGMA_GPS:.0f} m mengikuti akurasi yang dilaporkan\n")

        total = {"proceed": 0, "warn": 0, "step_up": 0, "cooling_off": 0}
        per_merchant = []

        for nmid, nama, lat, lng in MERCHANT:
            payload = payload_untuk(nmid, nama)
            hitung = {"proceed": 0, "warn": 0, "step_up": 0, "cooling_off": 0}
            alasan_gangguan = {}

            for i in range(KUNJUNGAN):
                akurasi = round(random.choice(
                    [5, 6, 8, 10, 12, 15, 18, 22, 30]) * random.uniform(0.8, 1.3), 1)
                plat, plng = derau_gps(lat, lng, akurasi)
                d = verify({
                    "payload": payload, "lat": plat, "lng": plng,
                    "accuracy_m": akurasi,
                    "device_anon_id": f"sim-{nmid[-4:]}-{i:04d}",
                    "device_integrity": {"mock_location": False, "rooted": False,
                                         "platform": "android"},
                })
                aksi = d.get("action", "?")
                hitung[aksi] = hitung.get(aksi, 0) + 1
                if aksi in ("step_up", "cooling_off"):
                    for r in d.get("reasons", []):
                        alasan_gangguan[r] = alasan_gangguan.get(r, 0) + 1

            for k, v in hitung.items():
                total[k] = total.get(k, 0) + v
            per_merchant.append((nama, hitung, alasan_gangguan))

        # Respons yang bukan salah satu dari empat aksi berarti harness ini
        # yang rusak, bukan produknya. Pernah terjadi: pembatas laju
        # memotong di permintaan ke-60 dan sisanya jadi 429, menghasilkan
        # angka false-positive yang kelihatan sempurna karena sebagian
        # besar kunjungan tidak pernah benar-benar dinilai.
        aneh = {k: v for k, v in total.items()
                if k not in ("proceed", "warn", "step_up", "cooling_off")}
        if aneh:
            print("  HARNESS RUSAK — respons bukan aksi:", aneh, file=sys.stderr)
            return 1

        for nama, h, alasan in per_merchant:
            n = sum(h.values())
            print(f"  {nama}")
            for aksi in ("proceed", "warn", "step_up", "cooling_off"):
                v = h.get(aksi, 0)
                bar = "#" * int(v / n * 40)
                print(f"    {aksi:12} {v:5}  {v/n*100:5.1f}%  {bar}")
            if alasan:
                print("    alasan gangguan:")
                for r, c in sorted(alasan.items(), key=lambda x: -x[1])[:3]:
                    print(f"      {c:4}x  {r}")
            print()

        n = sum(total.values())
        gangguan = total.get("step_up", 0) + total.get("cooling_off", 0)
        print("=" * 72)
        print(f"  gesekan berat (step_up / cooling_off) : {gangguan/n*100:5.2f}%")
        print(f"  gesekan apa pun (bukan proceed)       : "
              f"{(n - total.get('proceed', 0))/n*100:5.2f}%")
        print("=" * 72)
        print("""
  CARA MEMBACA. "warn" bukan gesekan berat: pengguna tetap bisa
  membayar, hanya melihat catatan. Yang benar-benar menghentikan orang
  adalah step_up dan cooling_off — itu yang harus mendekati nol untuk
  pedagang sah.

  Tingginya angka "warn" di awal wajar dan memang dirancang begitu:
  binding baru berstatus unknown sampai 3 perangkat berbeda
  mengamatinya dan 24 jam berlalu. Invarian §2 melarang unknown
  menjadi proceed.""")
        return 0
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == "__main__":
    sys.exit(main())
