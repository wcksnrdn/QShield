"""
Kenapa pemindaian ini menghasilkan putusan itu?

Membongkar satu pemindaian sampai ke tiap sinyal beserta bobot dan
alasannya, lalu menunjukkan isi basis data yang memunculkannya. Dipakai
ketika hasil di layar tidak sesuai harapan dan kalian perlu tahu
sebabnya, bukan menebaknya.

  python scripts/diagnose.py PAYLOAD LAT LNG [AKURASI]
  python scripts/diagnose.py --last            pemindaian terakhir di audit log
  python scripts/diagnose.py --anchor LAT LNG  isi jangkar di titik itu
  python scripts/diagnose.py --struktur PAYLOAD   bentuk payload, nilai disamarkan

Contoh:
  python scripts/diagnose.py "00020101021126..." -6.1686 106.8724 15
"""

import json
import os
import sys
from datetime import datetime, timezone

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.environ.get("QSHIELD_DB", os.path.join(AKAR, "qshield.db"))


def store():
    from qshield.store import Store
    if not os.path.exists(DB):
        print(f"Basis data tidak ada: {DB}", file=sys.stderr)
        sys.exit(1)
    return Store(DB)


def cmd_anchor(argv):
    """Apa yang basis data ketahui tentang titik ini."""
    from qshield import binding as bd
    from qshield import geo

    if len(argv) < 2:
        print("--anchor LAT LNG", file=sys.stderr)
        return 2
    lat, lng = float(argv[0]), float(argv[1])
    s = store()

    print("=" * 74)
    print(f"JANGKAR DI {lat:.6f}, {lng:.6f}")
    print("=" * 74)
    print()

    dekat = s.nearby(lat, lng)
    di_jangkar = [b for b in dekat if b.at_same_anchor(lat, lng)]
    print(f"  {len(dekat)} binding di sel indeks, "
          f"{len(di_jangkar)} di dalam radius jangkar "
          f"({bd.ANCHOR_RADIUS_M} m):")
    print()
    for b in sorted(di_jangkar, key=lambda x: -x.observer_count):
        jarak = b.distance_m(lat, lng)
        sifat = []
        if b.is_registered:
            sifat.append("TERDAFTAR")
        if b.is_established:
            sifat.append("mapan")
        if b.is_mobile:
            sifat.append("keliling")
        print(f"    {str(b.merchant_name)[:24]:<26} {b.nmid}")
        print(f"      {jarak:>5.1f} m   {b.observer_count:>3} pengamat   "
              f"usia {b.age_hours:>6.0f} jam   {' '.join(sifat) or '-'}")

    aid, animid, st = s.anchor_state(lat, lng)
    print()
    print(f"  Agregat jangkar:")
    print(f"    pemilik      : {animid or '(belum ada)'}")
    print(f"    percobaan anomali: {st.anomaly_attempts}")
    if st.last_anomaly_at:
        umur = (datetime.now(timezone.utc) - st.last_anomaly_at).days
        from qshield import behavior as bh
        sisa = bh.W_ANOMALY_BASE * st.anomaly_attempts
        sisa = min(bh.W_ANOMALY_CAP, sisa) * (
            0.5 ** (umur / bh.ANOMALY_HALFLIFE_DAYS))
        print(f"    terakhir     : {umur} hari lalu "
              f"-> bobot tersisa {sisa:.0f} "
              f"({'masih berlaku' if sisa >= bh.ANOMALY_MIN_WEIGHT else 'sudah pudar'})")

    w = s.area_city(lat, lng)
    print()
    if w:
        kota, setuju, total = w
        cukup = (setuju >= bd.AREA_CITY_MIN_NMIDS
                 and setuju / total >= bd.AREA_CITY_MIN_SHARE)
        print(f"  Pengetahuan wilayah: {kota} ({setuju}/{total} NMID) "
              f"-> {'dipakai menilai' if cukup else 'BELUM cukup, sistem diam'}")
    else:
        print("  Pengetahuan wilayah: belum ada")
    s.close()
    return 0


def cmd_struktur(argv):
    """Cetak STRUKTUR payload, bukan isinya.

    Dipakai ketika struktur sebuah QRIS sungguhan perlu diperiksa tanpa
    membagikan identitas merchantnya. Nilai yang bukan struktural
    disamarkan panjangnya saja; yang ditampilkan apa adanya hanya yang
    memang menentukan bentuk — GUID penyelenggara, nomor tag, dan
    panjang tiap field.
    """
    from qshield import emvco

    if not argv:
        print("--struktur PAYLOAD", file=sys.stderr)
        return 2
    try:
        parsed = emvco.parse(argv[0])
    except emvco.ParseError as exc:
        print(f"Tidak bisa diurai: {exc}", file=sys.stderr)
        return 1

    TAMPIL = {"00", "01", "52", "53", "58", "61", "63"}
    print("=" * 62)
    print("STRUKTUR PAYLOAD  (nilai disamarkan)")
    print("=" * 62)
    print()
    print(f"  panjang total: {len(argv[0])} karakter")
    print()
    for tag in parsed.tags:
        nilai = parsed.tags[tag]
        if 26 <= int(tag) <= 51:
            print(f"  tag {tag}  template merchant, {len(nilai)} karakter")
            try:
                sub = emvco.parse_tlv(nilai)
            except emvco.ParseError:
                print("      (sub-TLV tidak bisa diurai)")
                continue
            for st, sv in sub.items():
                # GUID ditampilkan apa adanya: ia menentukan template
                # mana yang nasional dan mana yang milik acquirer.
                if st == "00":
                    print(f"      {st}  GUID          {sv}")
                else:
                    peran = {"01": "PAN", "02": "NMID",
                             "03": "kriteria"}.get(st, "?")
                    print(f"      {st}  {peran:<12}  {len(sv)} karakter")
        elif tag in TAMPIL:
            print(f"  tag {tag}  {nilai}")
        else:
            print(f"  tag {tag}  {len(nilai)} karakter")

    acc = parsed.primary_account
    print()
    print(f"  primary_account dipilih parser : tag "
          f"{acc.tag if acc else '-'}")
    print(f"    GUID     {acc.guid if acc else '-'}")
    print(f"    NMID ada {bool(acc and acc.nmid)}")
    print(f"    PAN ada  {bool(acc and acc.pan)}"
          f"{'   <- INI MASALAHNYA' if acc and not acc.pan else ''}")
    return 0


def cmd_last(argv):
    print("Audit log ditulis ke stdout server, bukan ke berkas.")
    print("Salin payload dari log itu, lalu jalankan:")
    print("  python scripts/diagnose.py PAYLOAD LAT LNG")
    return 2


def cmd_scan(argv):
    from qshield import behavior as bh
    from qshield import binding as bd
    from qshield import emvco, geo

    payload = argv[0]
    lat, lng = float(argv[1]), float(argv[2])
    acc = float(argv[3]) if len(argv) > 3 else 15.0

    print("=" * 74)
    print("PEMBONGKARAN SATU PEMINDAIAN")
    print("=" * 74)

    try:
        parsed = emvco.parse(payload)
    except emvco.ParseError as exc:
        print(f"\n  Payload tidak bisa diurai: {exc}")
        print("  -> API akan menjawab 422, bukan memberi putusan.")
        return 1

    print()
    print("1. ISI STIKER")
    print("-" * 74)
    print(f"     NMID          {parsed.nmid}")
    print(f"     nama          {parsed.merchant_name}")
    print(f"     kota (tag 60) {parsed.merchant_city}")
    print(f"     kode pos      {parsed.postal_code}")
    print(f"     tipe          {'statis' if parsed.is_static else 'DINAMIS'}")
    print(f"     nominal       {parsed.amount or '(tidak ada)'}")
    print(f"     CRC valid     {parsed.crc_valid}")

    s = store()
    nmid = parsed.nmid
    dekat = s.nearby(lat, lng)
    lain = s.by_nmid(nmid)
    wilayah = s.area_city(lat, lng)
    nama_lain = s.names_for_nmid(nmid)
    aid, animid, st = s.anchor_state(lat, lng)

    lokasi = bd.evaluate(nmid=nmid, lat=lat, lng=lng, nearby=dekat,
                         same_nmid_elsewhere=lain,
                         crc_valid=parsed.crc_valid)
    pemilik = (lokasi.matched_binding is not None
               and lokasi.matched_binding.is_established)
    perilaku = bh.evaluate(parsed, state=st, nmid_matches_anchor=pemilik,
                           accuracy_m=acc, has_coords=True,
                           area=wilayah, other_names=nama_lain)
    verdict = bd.compose(lokasi, perilaku)

    print()
    print("2. LAYER 1 — ikatan merchant-lokasi")
    print("-" * 74)
    print(f"     skor {lokasi.risk_score}")
    for sig in lokasi.signals:
        print(f"       {sig}")
    for r in lokasi.reasons:
        print(f"         {r}")

    print()
    print("3. LAYER 2 — perilaku artefak")
    print("-" * 74)
    print(f"     skor {perilaku.score}")
    if not perilaku.signals:
        print("       (tidak ada sinyal)")
    for sig, r in zip(perilaku.signals, perilaku.reasons):
        print(f"       {sig}")
        print(f"         {r}")

    print()
    print("4. PUTUSAN GABUNGAN")
    print("-" * 74)
    BELUM = {"first_observation", "young_binding", "low_gps_accuracy"}
    polos = (verdict.action == "warn" and verdict.signals
             and all(x in BELUM for x in verdict.signals))
    label = ("Lokasi belum dikenal (NETRAL, biru)" if polos else {
        "proceed": "Aman dilanjutkan (HIJAU)",
        "warn": "Periksa dulu (AMBER)",
        "step_up": "Butuh verifikasi (ORANYE)",
        "cooling_off": "Berhenti dulu (MERAH)"}[verdict.action])
    print(f"     {verdict.status} / {verdict.action}   "
          f"skor {lokasi.risk_score} + {perilaku.score} = {verdict.risk_score}")
    print(f"     Tampil di layar sebagai: \"{label}\"")

    print()
    print("5. KENAPA BUKAN 'AMAN DILANJUTKAN'")
    print("-" * 74)
    if verdict.action == "proceed":
        print("     Memang proceed.")
    else:
        for sig in verdict.signals:
            if sig in BELUM:
                print(f"     {sig}")
                print(f"       -> belum cukup bukti. Ini BUKAN tuduhan, dan")
                print(f"          invarian §2 melarang status ini jadi proceed.")
            else:
                print(f"     {sig}")
                print(f"       -> sinyal risiko sungguhan, bukan sekadar")
                print(f"          ketiadaan bukti.")
        if lokasi.matched_binding is None:
            print()
            print("     Merchant ini belum punya binding di titik ini.")
            print("     Butuh MIN_OBSERVERS="
                  f"{bd.MIN_OBSERVERS} perangkat berbeda DAN rentang "
                  f"MIN_AGE_HOURS={bd.MIN_AGE_HOURS} jam,")
            print("     ATAU didaftarkan PJP lewat POST /api/v1/merchants.")
        elif not lokasi.matched_binding.is_established:
            b = lokasi.matched_binding
            print()
            print(f"     Binding ada tapi belum mapan: {b.observer_count} "
                  f"pengamat (butuh {bd.MIN_OBSERVERS}), "
                  f"usia {b.age_hours:.0f} jam (butuh {bd.MIN_AGE_HOURS}).")

    s.close()
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        sys.exit(0)
    if argv[0] == "--struktur":
        sys.exit(cmd_struktur(argv[1:]))
    if argv[0] == "--anchor":
        sys.exit(cmd_anchor(argv[1:]))
    if argv[0] == "--last":
        sys.exit(cmd_last(argv[1:]))
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    sys.exit(cmd_scan(argv))
