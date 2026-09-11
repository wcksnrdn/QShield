"""
Kalibrasi lapangan — mengubah pemindaian nyata jadi parameter.

Hampir setiap konstanta di Q-Shield masih bertanda "titik awal untuk
demo, bukan hasil kalibrasi lapangan". Itu kelemahan paling sering
muncul di dokumen kami sendiri, dan satu-satunya cara menutupnya adalah
pergi memindai QRIS sungguhan.

  python scripts/fieldkit.py status              berapa data terkumpul
  python scripts/fieldkit.py analyse             turunkan parameternya
  python scripts/fieldkit.py add ...             tambah satu baris manual

Cara mengumpulkan datanya:

  QSHIELD_FIELD_MODE=on QSHIELD_AUTH=off \\
    uvicorn qshield.api:app --host 0.0.0.0 --port 8000 \\
      --ssl-certfile certs/cert.pem --ssl-keyfile certs/key.pem

Lalu buka scanner dari HP, nyalakan "Mode survei" di setelan, dan
berkeliling. Tiap pemindaian tersimpan lengkap dengan label yang kalian
ketik.

PENTING soal label. Label adalah kebenaran dasarnya, dan analisis ini
seluruhnya bergantung padanya:

  - pakai label SAMA untuk pemindaian berulang di merchant yang sama
  - pakai label BERBEDA untuk merchant yang berbeda, walau bersebelahan
  - untuk mengukur galat GPS, pindai satu stiker 10-20 kali berturut

Mode survei menyimpan payload mentah dan koordinat presisi. Itu memang
yang dibutuhkan, dan itu juga kenapa ia tidak boleh pernah menyala di
lingkungan yang melayani pengguna sungguhan.
"""

import json
import math
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BERKAS = os.environ.get("QSHIELD_FIELD_FILE",
                        os.path.join(AKAR, "fielddata.jsonl"))


def muat():
    if not os.path.exists(BERKAS):
        return []
    keluar = []
    with open(BERKAS) as f:
        for baris in f:
            baris = baris.strip()
            if baris:
                keluar.append(json.loads(baris))
    return keluar


def persentil(data, p):
    if not data:
        return float("nan")
    d = sorted(data)
    return d[min(len(d) - 1, int(len(d) * p / 100))]


# --- status --------------------------------------------------------

def cmd_status(argv):
    data = muat()
    if not data:
        print(f"Belum ada data di {BERKAS}.")
        print()
        print(__doc__.split("Cara mengumpulkan")[1].split("PENTING")[0].strip())
        return 1

    per_label = defaultdict(list)
    for d in data:
        per_label[d["label"]].append(d)

    berulang = {k: v for k, v in per_label.items() if len(v) >= 2}
    print(f"Berkas   : {BERKAS}")
    print(f"Pemindaian: {len(data)}")
    print(f"Label    : {len(per_label)}  ({len(berulang)} punya pemindaian berulang)")
    print()
    print("  Kecukupan untuk tiap parameter:")
    syarat = [
        ("galat GPS (sigma)", max((len(v) for v in per_label.values()), default=0), 10,
         "satu label dipindai >= 10 kali"),
        ("radius jangkar", len(berulang), 5, ">= 5 label dengan pemindaian berulang"),
        ("jarak antar-merchant", len(per_label), 8, ">= 8 label berbeda"),
        ("korpus payload (R7)", len({d["payload"][:60] for d in data}), 20,
         ">= 20 payload QRIS berbeda"),
    ]
    for nama, punya, butuh, cara in syarat:
        tanda = "cukup" if punya >= butuh else "kurang"
        print(f"    [{tanda:>6}] {nama:<24} {punya:>3}/{butuh:<3}  {cara}")
    return 0


# --- add -----------------------------------------------------------

def cmd_add(argv):
    if len(argv) < 5:
        print("add PAYLOAD LAT LNG ACCURACY LABEL [CATATAN]", file=sys.stderr)
        return 2
    baris = {
        "ts": datetime.now().astimezone().isoformat(),
        "surveyor": "manual",
        "payload": argv[0], "lat": float(argv[1]), "lng": float(argv[2]),
        "accuracy_m": float(argv[3]), "label": argv[4],
        "note": argv[5] if len(argv) > 5 else None,
    }
    with open(BERKAS, "a") as f:
        f.write(json.dumps(baris, ensure_ascii=False) + "\n")
    print(f"Tersimpan. Total {len(muat())} pemindaian.")
    return 0


# --- analyse -------------------------------------------------------

def haversine_m(lat1, lng1, lat2, lng2):
    from qshield import geo
    return geo.haversine_m(lat1, lng1, lat2, lng2)


def cmd_analyse(argv):
    from qshield import behavior as bh
    from qshield import binding as bd
    from qshield import emvco, geo

    data = muat()
    if len(data) < 5:
        print(f"Data terlalu sedikit ({len(data)} pemindaian).", file=sys.stderr)
        print("Jalankan `fieldkit.py status` untuk melihat yang masih kurang.",
              file=sys.stderr)
        return 1

    per_label = defaultdict(list)
    for d in data:
        per_label[d["label"]].append(d)

    print("=" * 74)
    print(f"KALIBRASI LAPANGAN — {len(data)} pemindaian, {len(per_label)} lokasi")
    print("=" * 74)

    # --- 1. akurasi yang dilaporkan perangkat ----------------------
    akurasi = [d["accuracy_m"] for d in data]
    print()
    print("1. AKURASI GPS YANG DILAPORKAN PERANGKAT")
    print("-" * 74)
    for p in (5, 50, 90, 99):
        print(f"     p{p:<3} {persentil(akurasi, p):>8.1f} m")
    print(f"     min  {min(akurasi):>8.1f} m        maks {max(akurasi):>8.1f} m")
    print()
    di_bawah = sum(1 for a in akurasi if a < bh.MIN_PLAUSIBLE_ACCURACY_M)
    di_atas = sum(1 for a in akurasi if a > 100)
    print(f"     MIN_PLAUSIBLE_ACCURACY_M = {bh.MIN_PLAUSIBLE_ACCURACY_M} m")
    print(f"       {di_bawah} dari {len(akurasi)} pemindaian jatuh di bawahnya "
          f"({100 * di_bawah / len(akurasi):.1f}%)")
    if di_bawah:
        print("       PERIKSA: perangkat sungguhan melaporkan nilai di bawah")
        print("       ambang ini. Ambangnya terlalu tinggi.")
    else:
        print("       aman — tidak ada perangkat sungguhan yang menyentuhnya")
    print()
    print(f"     Ambang tolak-putusan = 100 m")
    print(f"       {di_atas} dari {len(akurasi)} pemindaian melewatinya "
          f"({100 * di_atas / len(akurasi):.1f}%)")

    # --- 2. sebaran di satu titik ----------------------------------
    print()
    print("2. SEBARAN PEMINDAIAN DI SATU LOKASI YANG SAMA")
    print("-" * 74)
    sebaran = []
    for label, titik in sorted(per_label.items()):
        if len(titik) < 2:
            continue
        clat = statistics.fmean(t["lat"] for t in titik)
        clng = statistics.fmean(t["lng"] for t in titik)
        jarak = [haversine_m(clat, clng, t["lat"], t["lng"]) for t in titik]
        sebaran.extend(jarak)
        print(f"     {label[:26]:<28} {len(titik):>3} scan   "
              f"rerata {statistics.fmean(jarak):>5.1f} m   maks {max(jarak):>5.1f} m")

    if sebaran:
        print()
        sigma = statistics.pstdev(sebaran) if len(sebaran) > 1 else 0.0
        print(f"     Sebaran gabungan: rerata {statistics.fmean(sebaran):.1f} m, "
              f"p95 {persentil(sebaran, 95):.1f} m, maks {max(sebaran):.1f} m")
        print(f"     Sigma terukur   : {sigma:.1f} m   "
              f"(dipakai calibrate_anchor.py: 8,0 m)")
        print()
        cukup = persentil(sebaran, 99) <= bd.ANCHOR_RADIUS_M
        print(f"     ANCHOR_RADIUS_M = {bd.ANCHOR_RADIUS_M} m")
        print(f"       {'aman' if cukup else 'PERIKSA'} — p99 sebaran "
              f"{persentil(sebaran, 99):.1f} m")
        if not cukup:
            print("       Pemindaian di merchant yang sama jatuh di luar radius.")
            print("       Binding tidak akan terakumulasi. Naikkan radiusnya.")
    else:
        print("     (belum ada label dengan pemindaian berulang)")

    # --- 3. jarak antar-merchant -----------------------------------
    print()
    print("3. JARAK ANTAR-MERCHANT BERBEDA")
    print("-" * 74)
    pusat = {}
    for label, titik in per_label.items():
        pusat[label] = (statistics.fmean(t["lat"] for t in titik),
                        statistics.fmean(t["lng"] for t in titik))
    pasangan = []
    nama = sorted(pusat)
    for i in range(len(nama)):
        for j in range(i + 1, len(nama)):
            d = haversine_m(*pusat[nama[i]], *pusat[nama[j]])
            pasangan.append((d, nama[i], nama[j]))
    pasangan.sort()
    if pasangan:
        for d, a, b in pasangan[:6]:
            tanda = "  <-- di bawah radius jangkar" if d <= bd.ANCHOR_RADIUS_M else ""
            print(f"     {d:>7.1f} m   {a[:20]:<22} {b[:20]:<22}{tanda}")
        dekat = sum(1 for d, _, _ in pasangan if d <= bd.ANCHOR_RADIUS_M)
        print()
        print(f"     {dekat} dari {len(pasangan)} pasangan berada dalam satu jangkar.")
        print("     Pasangan itulah yang mengandalkan aturan adjacent_merchant.")
    else:
        print("     (butuh minimal 2 label berbeda)")

    # --- 4. korpus payload: menutup R7 -----------------------------
    print()
    print("4. KORPUS PAYLOAD QRIS SUNGGUHAN  (batasan R7)")
    print("-" * 74)
    unik = {}
    for d in data:
        unik[d["payload"]] = d
    print(f"     {len(unik)} payload berbeda")
    print()

    rusak = []
    urutan_tidak_naik = 0
    crc_kecil = 0
    guid = defaultdict(int)
    pjp = defaultdict(int)
    panjang = []
    for p in unik:
        try:
            parsed = emvco.parse(p)
        except emvco.ParseError as exc:
            rusak.append((p[:40], str(exc)))
            continue
        panjang.append(len(p))
        tags = list(parsed.tags)
        if tags != sorted(tags):
            urutan_tidak_naik += 1
        if parsed.crc_found and parsed.crc_found != parsed.crc_found.upper():
            crc_kecil += 1
        acc = parsed.primary_account
        if acc:
            guid[acc.guid or "?"] += 1
            if acc.pan and len(acc.pan) >= 8:
                pjp[acc.pan[:8]] += 1

    if panjang:
        print(f"     Panjang payload: min {min(panjang)}, maks {max(panjang)}, "
              f"p95 {persentil(panjang, 95)}")
        print(f"       MAX_PAYLOAD_CHARS = 1024 -> "
              f"{'aman' if max(panjang) < 1024 else 'PERIKSA, ada yang melewati'}")
    print(f"     GUID penyelenggara: {dict(guid)}")
    print(f"     Prefiks PAN (PJP) : {len(pjp)} berbeda")
    if rusak:
        print(f"     GAGAL DIURAI: {len(rusak)}")
        for p, e in rusak[:3]:
            print(f"       {p}...  {e}")

    print()
    print(f"     Sinyal sidik jari encoding (yang selama ini UNCALIBRATED):")
    print(f"       urutan tag tidak menaik : {urutan_tidak_naik} dari {len(panjang)}")
    print(f"       CRC huruf kecil         : {crc_kecil} dari {len(panjang)}")
    if panjang and (urutan_tidak_naik or crc_kecil):
        print()
        print("       PERIKSA: penerbit SUNGGUHAN menghasilkan pola ini.")
        print("       Sinyalnya akan menandai merchant sah. Turunkan bobotnya")
        print("       atau buang sinyalnya — lihat Keputusan 13 untuk polanya.")
    elif panjang:
        print()
        print(f"       Nol positif palsu dari {len(panjang)} payload sungguhan.")
        print("       Belum cukup untuk menutup R7, tapi ini bukti pertama")
        print("       yang bukan dari generator kami sendiri.")

    # --- 4b. kota vs lokasi sesungguhnya ---------------------------
    print()
    print("4b. KOTA DI STIKER vs LOKASI SESUNGGUHNYA  (sinyal city_mismatch)")
    print("-" * 74)
    from collections import Counter
    per_area = defaultdict(Counter)
    kota_label = {}
    for d in data:
        try:
            parsed = emvco.parse(d["payload"])
        except emvco.ParseError:
            continue
        kota = bd.normalize_city(parsed.merchant_city)
        if not kota:
            continue
        gh5 = geo.encode(d["lat"], d["lng"], bd.AREA_CITY_PRECISION)
        nm = parsed.nmid or d["payload"][:20]
        per_area[gh5][kota] = per_area[gh5][kota]
        kota_label.setdefault((gh5, kota), set()).add(nm)

    if not kota_label:
        print("     (belum ada payload yang bisa diurai)")
    else:
        beda = 0
        for gh5 in sorted({k[0] for k in kota_label}):
            suara = {kota: len(nmids) for (g, kota), nmids
                     in kota_label.items() if g == gh5}
            total = sum(suara.values())
            dominan = max(suara, key=suara.get)
            cukup = (suara[dominan] >= bd.AREA_CITY_MIN_NMIDS
                     and suara[dominan] / total >= bd.AREA_CITY_MIN_SHARE)
            lain = {k: v for k, v in suara.items() if k != dominan}
            beda += sum(lain.values())
            tanda = "cukup" if cukup else "belum cukup"
            print(f"     sel {gh5}  {dominan:<18} {suara[dominan]:>3}/{total:<3} "
                  f"({tanda})")
            for k, v in sorted(lain.items(), key=lambda x: -x[1]):
                print(f"                    berbeda: {k:<18} {v:>3} NMID")

        print()
        print(f"     AREA_CITY_MIN_NMIDS = {bd.AREA_CITY_MIN_NMIDS}, "
              f"MIN_SHARE = {bd.AREA_CITY_MIN_SHARE}")
        if beda:
            print(f"     {beda} NMID menyebut kota BERBEDA dari wilayahnya.")
            print("     PERIKSA satu per satu: kalau itu merchant sah (franchise,")
            print("     kantor pusat di kota lain, merchant yang pindah), maka")
            print("     city_mismatch akan menandai merchant jujur dan bobotnya")
            print("     harus turun — atau sinyalnya dibuang, seperti Keputusan 13.")
        else:
            print("     Nol merchant sah yang menyebut kota berbeda.")
            print("     Belum membuktikan apa-apa kalau sampelnya kecil, tapi")
            print("     ini data pertama yang menguji sinyalnya.")

    # --- 5. ringkasan ----------------------------------------------
    print()
    print("=" * 74)
    print("YANG BERUBAH DARI ANGKA INI")
    print("=" * 74)
    print()
    usul = []
    if sebaran:
        sigma = statistics.pstdev(sebaran) if len(sebaran) > 1 else 0.0
        if abs(sigma - 8.0) > 3:
            usul.append(f"sigma GPS terukur {sigma:.1f} m, bukan 8,0 m — "
                        f"jalankan ulang calibrate_anchor.py dengan angka ini")
        if persentil(sebaran, 99) > bd.ANCHOR_RADIUS_M:
            usul.append(f"ANCHOR_RADIUS_M perlu naik ke >= "
                        f"{math.ceil(persentil(sebaran, 99) / 10) * 10} m")
    if di_bawah:
        usul.append(f"MIN_PLAUSIBLE_ACCURACY_M perlu turun di bawah "
                    f"{min(akurasi):.2f} m")
    if urutan_tidak_naik or crc_kecil:
        usul.append("sinyal sidik jari encoding menandai payload sungguhan — "
                    "turunkan bobot atau buang")
    if kota_label:
        salah_kota = sum(
            v for gh5 in {k[0] for k in kota_label}
            for k, v in {kk: len(vv) for (g, kk), vv in kota_label.items()
                         if g == gh5}.items()
            if k != max({kk: len(vv) for (g, kk), vv in kota_label.items()
                         if g == gh5}, key=lambda x: len(
                            kota_label[(gh5, x)])))
        if salah_kota:
            usul.append(f"{salah_kota} merchant menyebut kota berbeda dari "
                        f"wilayahnya — periksa apakah mereka sah sebelum "
                        f"memercayai city_mismatch")

    if usul:
        for u in usul:
            print(f"  - {u}")
    else:
        print("  Tidak ada parameter yang perlu digeser dari data ini.")
        print("  Itu hasil yang sah dan layak disebut: nilai demo ternyata")
        print("  bertahan terhadap pengukuran lapangan pertama.")
    print()
    print(f"  Dasar bukti: {len(data)} pemindaian, {len(per_label)} lokasi, "
          f"{len(unik)} payload.")
    print("  Sebutkan angka ini apa adanya — kalibrasi dari 30 pemindaian")
    print("  adalah kalibrasi dari 30 pemindaian, bukan dari data produksi.")
    return 0


PERINTAH = {"status": cmd_status, "analyse": cmd_analyse, "add": cmd_add}

if __name__ == "__main__":
    argv = sys.argv[1:]
    if not argv or argv[0] not in PERINTAH:
        print(__doc__)
        print(f"Perintah: {', '.join(PERINTAH)}")
        sys.exit(0 if not argv else 2)
    sys.exit(PERINTAH[argv[0]](argv[1:]))
