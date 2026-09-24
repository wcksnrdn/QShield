"""
Kunci kecocokan frontend dengan API.

Frontend dan backend gampang menyimpang diam-diam: field diganti nama di
server, halaman tetap tampil, dan yang hilang cuma satu baris keterangan
yang tidak ada yang sadar sampai di depan juri.

Berkas ini membaca `web/index.html` dan memastikan:
  - halaman benar-benar mandiri (tidak ada permintaan ke luar)
  - badan permintaan yang disusun JS lolos validasi API
  - setiap field yang DIBACA JS memang ada di tanggapan
  - kosakata aksi/verdict yang dipetakan JS sama persis dengan API

    python tests/test_frontend.py
"""

import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone

os.environ["QSHIELD_AUTH"] = "off"
os.environ["QSHIELD_RATE_LIMIT"] = "off"

from fastapi.testclient import TestClient

from qshield import api, emvco
from qshield import binding as bd
from qshield.store import Store

NOW = datetime.now(timezone.utc)
LAT, LNG, NMID = -6.914744, 107.609810, "ID1024365478912"

HALAMAN = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "qshield", "web", "index.html")

_hasil = []


def cek(nama):
    def deco(fn):
        try:
            _hasil.append((nama, True, fn() or ""))
        except AssertionError as exc:
            _hasil.append((nama, False, str(exc)))
        return fn
    return deco


def klien():
    api.store = Store(os.path.join(tempfile.mkdtemp(), "fe.db"))
    api.store.seed_binding(
        nmid=NMID, lat=LAT, lng=LNG, merchant_name="WARUNG BU SRI",
        observer_count=47, first_seen=NOW - timedelta(days=180),
        last_seen=NOW - timedelta(hours=6))
    return TestClient(api.app)


def qr(nmid=NMID, pan="936000149000000001"):
    acct = emvco.build_tlv({
        "00": "ID.CO.QRIS.WWW", "01": pan, "02": nmid, "03": "UMI"})
    return emvco.build({
        "00": "01", "01": "11", "26": acct, "52": "5812", "53": "360",
        "58": "ID", "59": "WARUNG BU SRI", "60": "BANDUNG", "61": "40257"})


with open(HALAMAN) as f:
    HTML = f.read()
SCRIPT = HTML[HTML.index("<script>"):HTML.index("</script>")]


@cek("Halaman disajikan API dan benar-benar mandiri")
def _f1():
    r = klien().get("/")
    assert r.status_code == 200, f"GET / -> {r.status_code}"
    assert "text/html" in r.headers["content-type"]

    # Yang dicari adalah URL sungguhan, bukan kata "CDN" — halaman ini
    # justru memuat komentar yang menyebutnya, dan mencocokkan kata
    # membuat pemeriksaan gagal karena dokumentasinya sendiri.
    luar = re.findall(r'(?:src|href)\s*=\s*"(https?://[^"]+)"', r.text)
    assert not luar, f"halaman meminta sumber luar: {luar}"
    url = re.findall(r'https?://(?!127\.0\.0\.1|localhost)[^\s"\')<]+', r.text)
    assert not url, f"ada URL eksternal di halaman: {url[:3]}"
    assert "@import" not in r.text, "ada @import CSS yang menarik sumber luar"
    # Font Google akan gagal tanpa internet; harus ada fallback sistem.
    assert "-apple-system" in r.text, "tidak ada fallback font sistem"
    return f"{len(r.text)} byte, nol permintaan ke luar"


@cek("Badan permintaan yang disusun JS lolos validasi API")
def _f2():
    # Persis bentuk yang dibangun `verifikasi()` di halaman.
    body = {
        "payload": qr(),
        "device_anon_id": "550e8400-e29b-41d4-a716-446655440000",
        "lat": LAT, "lng": LNG, "accuracy_m": 8.5,
        "location_source": "live",
    }
    r = klien().post("/api/v1/verify", json=body)
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:160]}"

    # device_anon_id dari crypto.randomUUID() harus lolos pola server.
    pola = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
    assert pola.match(body["device_anon_id"]), (
        "UUID v4 tidak cocok dengan pola device_anon_id di server")
    return "UUID v4 + accuracy pecahan diterima"


@cek("Setiap field yang dibaca JS ada di tanggapan")
def _f3():
    d = klien().post("/api/v1/verify", json={
        "payload": qr(), "device_anon_id": "frontend-uji-0001",
        "lat": LAT, "lng": LNG, "accuracy_m": 8.5}).json()

    # Field yang dirujuk kode halaman, dikumpulkan dari sumbernya.
    # `detail` dikecualikan: itu milik tanggapan GAGAL, dan halaman
    # membacanya hanya di cabang penanganan error.
    HANYA_ERROR = {"detail"}
    dibaca_akar = set(re.findall(r'\bd\.(\w+)', SCRIPT)) - HANYA_ERROR
    hilang = dibaca_akar - set(d)
    assert not hilang, f"JS membaca field yang tidak ada: {sorted(hilang)}"

    # Dan pastikan cabang error itu memang benar: server betul-betul
    # mengembalikan `detail` saat menolak.
    gagal = klien().post("/api/v1/verify", json={
        "payload": "bukan-qris", "device_anon_id": "frontend-uji-0002",
        "lat": LAT, "lng": LNG, "accuracy_m": 8.5})
    assert gagal.status_code == 422
    assert "detail" in gagal.json(), (
        "halaman membaca d.detail saat gagal, tapi server tidak mengirimnya")

    # Sub-objek yang dipakai halaman.
    for k in ("location", "behavior"):
        assert k in d["layers"], f"layers.{k} hilang"
    for k in ("name", "nmid", "city"):
        assert k in d["merchant"], f"merchant.{k} hilang"
    assert isinstance(d["reasons"], list) and d["reasons"], "reasons kosong"
    return f"{len(dibaca_akar)} field akar + layers + merchant cocok"


@cek("Kosakata aksi dan verdict dipetakan lengkap")
def _f4():
    aksi_js = set(re.findall(r'^\s*(\w+):\s*\{t:', SCRIPT, re.M))
    aksi_api = {bd.PROCEED, bd.WARN, bd.STEP_UP, bd.COOLING_OFF}
    assert aksi_js == aksi_api, (
        f"peta aksi tidak lengkap — hilang {aksi_api - aksi_js}, "
        f"asing {aksi_js - aksi_api}")

    blok = re.search(r'const VERDICT = \{([^}]+)\}', SCRIPT).group(1)
    verdict_js = {b.split(":")[0].strip() for b in blok.split(",") if ":" in b}
    verdict_api = {bd.VERIFIED, bd.UNKNOWN, bd.ANOMALY}
    assert verdict_js == verdict_api, (
        f"peta verdict tidak lengkap: {verdict_api ^ verdict_js}")
    return f"{len(aksi_js)} aksi, {len(verdict_js)} verdict terpetakan"


@cek("Empat tier menghasilkan tampilan yang berbeda")
def _f5():
    gaya = HTML[HTML.index("<style>"):HTML.index("</style>")]
    for aksi in (bd.PROCEED, bd.WARN, bd.STEP_UP, bd.COOLING_OFF):
        assert f".a-{aksi}" in gaya, f"tier {aksi} tidak punya gaya sendiri"
    # Cooling-off adalah PENUNDAAN, bukan penolakan — hitung mundurnya
    # bagian dari responsnya, bukan hiasan.
    assert "cool-timer" in gaya and "hitungMundur" in SCRIPT, (
        "cooling_off tidak menampilkan penundaan")
    return "empat tier punya warna sendiri; cooling_off menampilkan hitung mundur"


@cek("Halaman memberi tahu saat konteks tidak aman")
def _f6():
    # Kamera dan geolocation menuntut secure context. Kalau halaman
    # dibuka lewat http dari HP, keduanya diblokir — dan itu harus
    # dijelaskan lengkap dengan cara memperbaikinya, bukan gagal diam.
    assert "isSecureContext" in SCRIPT, "tidak memeriksa secure context"
    assert "make_cert.py" in SCRIPT, (
        "tidak memberi tahu cara memperbaiki konteks tidak aman")
    assert "replay" in SCRIPT, "tidak menawarkan jalan keluar replay"
    return "diperiksa di muka, dengan perintah perbaikannya"


@cek("Mode replay bisa dijalankan dari halaman")
def _f7():
    d = klien().post("/api/v1/verify", json={
        "payload": qr(), "device_anon_id": "frontend-replay-01",
        "lat": LAT, "lng": LNG, "accuracy_m": 8.0,
        "location_source": "replay"}).json()
    assert d["location_source"] == "replay"
    assert "replay" in HTML, "tidak ada elemen penanda replay"
    assert 'id="replay"' in HTML, "penanda replay tidak punya wadah"
    return "replay ditandai di tanggapan dan punya wadah di halaman"


@cek("Skenario demo utama tampil benar")
def _f8():
    c = klien()

    def minta(payload, dev):
        return c.post("/api/v1/verify", json={
            "payload": payload, "device_anon_id": dev,
            "lat": LAT, "lng": LNG, "accuracy_m": 8.0}).json()

    asli = minta(qr(), "frontend-asli-01")
    assert asli["action"] == "proceed", f"QR asli -> {asli['action']}"

    palsu = minta(qr("ID1099887766554", "936000149000000002"),
                  "frontend-palsu-01")
    assert palsu["action"] == "cooling_off", f"QR palsu -> {palsu['action']}"
    assert palsu["reasons"], "tidak ada alasan untuk ditampilkan"
    return (f"asli -> {asli['action']}, palsu -> {palsu['action']} "
            f"({len(palsu['reasons'])} alasan tampil)")


@cek("Cold start tampil netral, kejanggalan tetap amber")
def _f9():
    import re as _re
    blok = _re.search(r'BELUM_KENAL = new Set\(\[([^\]]+)\]', HTML).group(1)
    belum = {x.strip().strip('"') for x in blok.split(",") if x.strip()}

    def polos(d):
        sig = d.get("signals") or []
        return d["action"] == "warn" and sig and all(x in belum for x in sig)

    c = klien()

    def minta(payload, lat, lng, dev, acc=9.0):
        return c.post("/api/v1/verify", json={
            "payload": payload, "lat": lat, "lng": lng,
            "device_anon_id": dev, "accuracy_m": acc}).json()

    # Merchant sungguhan yang belum dikenal: netral, bukan alarm.
    baru = minta(qr("ID1055555555555", "936000149000005"), -6.95, 107.65, "ui-baru-0001")
    assert baru["action"] == "warn", "tier berubah — invarian §2 tersentuh?"
    assert polos(baru), f"cold start tidak tampil netral: {baru['signals']}"

    # Kejanggalan sungguhan harus TETAP amber, bukan ikut dilunakkan.
    janggal = minta(qr(), LAT, LNG, "ui-janggal-001", acc=0.4)
    assert not polos(janggal), (
        f"sinyal janggal ikut dilunakkan jadi netral: {janggal['signals']}")

    # Anomaly tidak boleh tersentuh sama sekali.
    palsu = minta(qr("ID1099887766554", "936000149000000002"), LAT, LNG, "ui-palsu-0001")
    assert palsu["action"] == "cooling_off" and not polos(palsu)

    # Dan yang paling penting: keadaan netral TIDAK BOLEH menyiratkan aman.
    teks = _re.search(r'nb\.innerHTML = ([^;]+);', SCRIPT).group(1)
    assert "tidak akan menyatakan aman" in teks, (
        "keterangan cold start tidak menegaskan bahwa ini bukan klaim aman")
    assert "cocokkan nama merchant" in teks.lower(), (
        "tidak memberi pengguna pemeriksaan yang bisa dilakukan sendiri")
    return "cold start netral; kejanggalan & anomaly tidak ikut dilunakkan"


@cek("Layar PIN tidak pernah dirender saat cooling_off")
def _f10():
    import re as _re
    fn = _re.search(r'function bukaPembayaran\(d\)\{(.+?)\n\}',
                    SCRIPT, _re.S).group(1)

    # Cabang cooling_off harus berakhir TANPA memanggil layarPin().
    cabang = fn.split('if (d.action === "cooling_off")')[1]
    cabang_cool = cabang.split('} else if')[0]
    assert "layarPin" not in cabang_cool, (
        "cabang cooling_off masih memanggil layarPin — layar PIN-nya "
        "disembunyikan, bukan tidak pernah ada")
    assert "PIN-nya tidak pernah dimasukkan" in cabang_cool, (
        "kalimat terpenting pitch tidak muncul di layarnya")

    # step_up boleh sampai ke PIN, tapi HANYA lewat klik konfirmasi —
    # bukan otomatis. Yang diperiksa: tidak ada panggilan layarPin yang
    # berdiri sendiri di cabang itu, hanya yang terpasang sebagai handler.
    cabang_step = cabang.split('} else if')[1].split("} else {")[0]
    panggilan = _re.findall(r'(\S*)\s*layarPin\(', cabang_step)
    assert panggilan, "step_up tidak punya jalan ke PIN sama sekali"
    for sebelum in panggilan:
        assert sebelum.endswith("=>"), (
            f"step_up memanggil layarPin langsung, bukan lewat klik: "
            f"{sebelum!r}")
    assert "onclick" in cabang_step, "tidak ada konfirmasi yang harus diklik"

    # Cabang terakhir (proceed) memang boleh langsung.
    cabang_lolos = cabang.split("} else {")[1]
    assert "layarPin" in cabang_lolos, "proceed tidak sampai ke PIN"
    return ("cooling_off berhenti sebelum PIN; step_up hanya lewat klik; "
            "proceed langsung")


@cek("Alur bayar ditandai simulasi secara permanen")
def _f11():
    # Halaman yang meniru layar bayar sungguhan tanpa penanda adalah
    # templat phishing, terlepas dari niat pembuatnya.
    assert "SIMULASI" in HTML, "tidak ada penanda simulasi"
    assert 'class="simbar"' in HTML, "penanda simulasi tidak punya wadah tetap"
    # Penandanya harus di markup, bukan disuntik JS yang bisa dilewati.
    markup = HTML[:HTML.index("<script>")]
    assert "SIMULASI" in markup, "penanda simulasi hanya ada di JS"
    assert "Tidak ada dana yang berpindah" in SCRIPT, (
        "layar berhasil tidak menegaskan ini simulasi")
    return "penanda ada di markup, bukan disuntik JS"


@cek("Empat tier memetakan ke perlakuan bayar yang berbeda")
def _f12():
    c = klien()

    def minta(payload, lat, lng, dev, acc=9.0):
        return c.post("/api/v1/verify", json={
            "payload": payload, "lat": lat, "lng": lng,
            "device_anon_id": dev, "accuracy_m": acc}).json()

    asli = minta(qr(), LAT, LNG, "pay-asli-0001")
    palsu = minta(qr("ID1099887766554", "936000149000000002"),
                  LAT, LNG, "pay-palsu-001")
    assert asli["action"] == "proceed"
    assert palsu["action"] == "cooling_off"

    # Tombol lanjut berubah kalimat saat dihentikan — pengguna tidak
    # boleh disodori tombol yang seolah bisa meneruskan pembayaran.
    assert "Lihat apa yang terjadi berikutnya" in SCRIPT
    return f"asli -> {asli['action']} (PIN), palsu -> {palsu['action']} (tanpa PIN)"


@cek("Payload diurai di perangkat sebelum dikirim")
def _f13():
    # Kode yang bukan QRIS ditolak di perangkat dan tidak pernah
    # dikirim — payload QRIS memuat identitas merchant.
    assert "function parseQris" in SCRIPT, "tidak ada parser di halaman"
    assert "function crc16ccitt" in SCRIPT, "tidak ada CRC16 di halaman"

    blok = SCRIPT[SCRIPT.index("async function verifikasi"):]
    blok = blok[:blok.index("function tampilkan")]
    assert "parseQris(payload)" in blok, "parser tidak dipanggil sebelum kirim"
    # Cabang gagal parse harus berhenti tanpa memanggil fetch.
    cabang = blok[blok.index("catch (e)"):blok.index("let loc")]
    assert "return" in cabang, "payload cacat tetap diteruskan ke jaringan"
    assert "fetch" not in cabang, "cabang gagal parse memanggil jaringan"
    return "parse lokal dulu; yang cacat berhenti sebelum fetch"


@cek("Parser perangkat dan parser server sepakat")
def _f14():
    import shutil
    import subprocess
    import tempfile as _tf

    node = shutil.which("node")
    if not node:
        return "(node tidak ada — pemeriksaan silang dilewati)"

    # Parser di halaman diekstrak apa adanya, lalu diuji terhadap
    # parser Python. Kalau keduanya menyimpang, klien bisa menampilkan
    # merchant yang berbeda dari yang dinilai server.
    # Batasnya tepat di ujung parser. Mengambil lebih jauh ikut
    # menyeret kode khusus browser (localStorage) yang tidak ada di node.
    awal = SCRIPT.index("const QRIS_NESTED")
    akhir = SCRIPT.index("const AKSI = {")
    js = SCRIPT[awal:akhir]

    kasus = []
    for i, statis in enumerate([True, False] * 6):
        nmid = f"ID10{i:011d}"
        acct = emvco.build_tlv({"00": "ID.CO.QRIS.WWW",
                                "01": f"9360089900000{i:05d}",
                                "02": nmid, "03": "UMI"})
        f = {"00": "01", "01": "11" if statis else "12", "26": acct,
             "52": "5812", "53": "360", "58": "ID",
             "59": f"MERCHANT {i}", "60": "BANDUNG", "61": "40257"}
        if not statis:
            f["54"] = f"{1000 * (i + 1)}.00"
            f["62"] = emvco.build_tlv({"01": f"INV-{i:04d}"})
        p = emvco.build(f)
        d = emvco.parse(p)
        kasus.append({"payload": p, "nmid": d.nmid,
                      "name": d.merchant_name, "city": d.merchant_city,
                      "amount": d.amount, "static": d.is_static,
                      "crc": d.crc_valid, "bill": d.bill_ref})
    # Payload yang tidak bisa diurai sama sekali.
    for rusak in ("", "bukan-qris", "0002010102"):
        kasus.append({"payload": rusak, "error": True})

    with _tf.TemporaryDirectory() as d:
        js_path = os.path.join(d, "p.js")
        json_path = os.path.join(d, "k.json")
        with open(js_path, "w") as fh:
            fh.write(js + "\nmodule.exports={parseQris};\n")
        with open(json_path, "w") as fh:
            json.dump(kasus, fh)
        skrip = (
            f"const {{parseQris}}=require({js_path!r});"
            f"const K=require({json_path!r});"
            "let beda=[];"
            "for(const k of K){let r;"
            "try{r=parseQris(k.payload);}catch(e){"
            "if(!k.error)beda.push('galat tak terduga');continue;}"
            "if(k.error){beda.push('tidak melempar galat');continue;}"
            "const c=[[r.nmid,k.nmid],[r.merchantName,k.name],"
            "[r.merchantCity,k.city],[r.amount,k.amount],"
            "[r.isStatic,k.static],[r.crcValid,k.crc],[r.billRef,k.bill]];"
            "for(const [a,b] of c)if((a??null)!==(b??null))beda.push([a,b]);}"
            "console.log(JSON.stringify(beda));")
        hasil = subprocess.run([node, "-e", skrip], capture_output=True,
                               text=True, timeout=30)
    assert hasil.returncode == 0, f"node gagal: {hasil.stderr[:200]}"
    beda = json.loads(hasil.stdout.strip())
    assert not beda, f"parser menyimpang: {beda[:3]}"
    return f"{len(kasus)} payload, kedua parser sepakat"

@cek("Membayar menuntut ditahan, dan namanya ada di tombolnya")
def _f13():
    import re as _re

    badan = _re.search(r'function pasangTombolLanjut\(d\)\{(.+?)\n\}',
                       SCRIPT, _re.S).group(1)
    tahan = badan.split('t.className = "btn hold"')[1]

    # Satu ketukan tidak boleh cukup. Yang dilarang adalah TOMBOL
    # BAYARNYA punya handler klik — bukan setiap onclick di sekitarnya;
    # tombol simulasi serangan di mode demo memang memakai onclick, dan
    # itu bukan jalur bayar.
    assert "t.onclick" not in tahan, (
        "tombol bayar punya onclick — satu ketukan masih cukup")
    # Dan jalur menuju pembayaran hanya boleh dicapai dari tik() yang
    # menghitung durasi tahanan, bukan dari handler mana pun.
    for pemanggil in _re.findall(r"(\S*)\s*periksaTiketLaluBayar\(", tahan):
        assert not pemanggil.endswith("=>"), (
            f"pembayaran dipicu langsung dari handler: {pemanggil!r}")
    assert "pointerdown" in tahan, "tidak ada gerakan tahan sama sekali"
    assert "keydown" in tahan and "keyup" in tahan, (
        "papan ketik tidak punya jalur tahan — pengguna keyboard terkunci")

    # Tahanannya harus cukup lama untuk sempat dibaca.
    ms = int(_re.search(r"const TAHAN_MS = (\d+)", SCRIPT).group(1))
    assert ms >= 800, f"tahanan {ms} ms terlalu singkat untuk membaca nama"

    # Yang ditahan adalah pembayaran KE SIAPA — nama merchantnya ikut
    # di label, bukan kata generik "pembayaran".
    assert "Tahan untuk membayar ke" in tahan, "label tidak menyebut tindakannya"
    assert "namaMerchant(d)" in tahan, "nama merchant tidak ikut di tombol"

    # Nama itu berasal dari QR, yang dikendalikan penyerang. Jadi
    # tombolnya tidak boleh berhenti di situ: pengguna harus disuruh
    # mencocokkannya dengan dunia nyata.
    assert "cocokkan nama" in badan.lower(), (
        "tidak menyuruh mencocokkan nama dengan toko tempat pengguna berdiri")

    # Dan namanya di-escape — ia masuk lewat innerHTML.
    assert "esc(namaMerchant(d))" in tahan, (
        "nama merchant dari QR masuk innerHTML tanpa di-escape")

    # cooling_off TIDAK memakai tombol tahan: tombolnya tidak meneruskan
    # pembayaran, jadi "tahan untuk membayar" di sana menyesatkan.
    cool = badan.split('if (d.action === "cooling_off")')[1].split(
        't.className = "btn hold"')[0]
    assert "Tahan untuk membayar" not in cool
    return f"tahan {ms} ms, nama merchant di label, klik biasa tidak cukup"


@cek("Pengguna dapat SATU angka bersekala; rinciannya tinggal di API")
def _f14():
    import re as _re
    meta = _re.search(r'\$\("meta"\)\.innerHTML =(.+?);', SCRIPT, _re.S).group(1)

    # "Skor 83" tidak bisa dibaca tanpa tahu 83 dari berapa.
    assert "risk_score" in meta, "skor risiko tidak ditampilkan"
    assert "dari 100" in meta, "skor tampil tanpa nilai maksimumnya"

    # Rincian per-lapisan adalah alat audit, bukan bahan keputusan
    # pengguna — dan "Lokasi 0" gampang dibaca terbalik sebagai gagal,
    # padahal 0 justru hasil terbaik. processing_ms mengukur kecepatan
    # kami, bukan risiko pengguna.
    for bocor in ("layers", "processing_ms"):
        assert bocor not in meta, (
            f"{bocor} kembali ke tampilan pengguna — itu alat audit, "
            f"dan angkanya gampang dibaca terbalik")

    # Tapi keduanya TETAP ada di tanggapan: PJP memakainya, dan
    # test_contract.py menguncinya di tingkat skema maupun respons.
    d = klien().post("/api/v1/verify", json={
        "payload": qr(), "device_anon_id": "frontend-skor-01",
        "lat": LAT, "lng": LNG, "accuracy_m": 8.0}).json()
    assert "processing_ms" in d, "processing_ms hilang dari kontrak API"
    assert set(d["layers"]) == {"location", "behavior"}, (
        "rincian layer hilang dari kontrak API")
    assert 0 <= d["risk_score"] <= 100, "skor di luar skala 0-100"
    return "satu chip 'N dari 100'; layers & processing_ms tinggal di API"


@cek("Klaim stiker dan putusan Q-Shield tidak dicampur")
def _f15():
    import re as _re

    # Kota (tag 60) diteruskan apa adanya dari payload: tidak pernah
    # dinilai, tidak pernah dibandingkan dengan koordinat. Ia KLAIM,
    # setara nama merchant.
    d = klien().post("/api/v1/verify", json={
        "payload": qr(), "device_anon_id": "frontend-kota-01",
        "lat": LAT, "lng": LNG, "accuracy_m": 8.0}).json()
    assert d["merchant"]["city"] == "BANDUNG", (
        f"kota tidak diteruskan dari tag 60: {d['merchant']['city']!r}")

    baris = _re.search(r'\$\("merchant"\)\.innerHTML =(.+?);', SCRIPT,
                       _re.S).group(1)
    meta = _re.search(r'\$\("meta"\)\.innerHTML =(.+?);', SCRIPT, _re.S).group(1)

    # Kota tinggal bersama nama merchant, BUKAN di baris chip putusan.
    # Kalau ia naik ke sana, string yang dikendalikan penyerang tampil
    # dengan bobot visual yang sama seperti angka yang kami hitung.
    assert "m.city" in baris, "kota tidak lagi tampil bersama nama merchant"
    assert "city" not in meta, (
        "kota naik ke baris putusan — klaim stiker mewarisi otoritas "
        "angka yang dihitung Q-Shield")

    # Dan ia tidak lagi menyamar jadi identifier teknis.
    assert 'class="city"' in baris, "kota tidak punya gaya sendiri"
    kota = _re.search(r"m\.city \? '<span class=\"(\w+)\"", baris).group(1)
    assert kota != "id", "kota masih memakai gaya monospace milik NMID"

    gaya = HTML[HTML.index("<style>"):HTML.index("</style>")]
    blok = _re.search(r"\.merchant \.city\{([^}]+)\}", gaya).group(1)
    assert "monospace" not in blok, "kota masih dirender monospace"

    # Ditampilkan apa adanya: menyunting huruf besar-kecilnya berarti
    # mengubah klaim yang justru sedang disuruh diperiksa pengguna.
    assert "toUpperCase" not in baris and "toLowerCase" not in baris, (
        "klaim kota disunting sebelum ditampilkan")
    return "kota sebaris nama (klaim), baris chip murni putusan"


@cek("Biaya layanan diungkapkan ke pengguna, netral dan bersyarat")
def _f16():
    import re as _re
    c = klien()

    def minta(extra, dev):
        acct = emvco.build_tlv({
            "00": "ID.CO.QRIS.WWW", "01": "936000149000000001",
            "02": NMID, "03": "UMI"})
        f = {"00": "01", "01": "11", "26": acct, "52": "5812", "53": "360",
             "58": "ID", "59": "WARUNG BU SRI", "60": "BANDUNG", "61": "40257"}
        f.update(extra or {})
        return c.post("/api/v1/verify", json={
            "payload": emvco.build(f), "lat": LAT, "lng": LNG,
            "device_anon_id": dev, "accuracy_m": 8.0}).json()

    polos = minta(None, "fe-biaya-000")
    berbiaya = minta({"55": "03", "57": "2.50"}, "fe-biaya-001")
    assert polos["fees"]["present"] is False
    assert berbiaya["fees"]["present"] is True
    assert berbiaya["fees"]["percent"] == "2.50"

    # Halaman membacanya, dan hanya merendernya kalau memang ada —
    # mayoritas pemindaian tidak membawa tag ini, jadi biaya visualnya
    # nol di kasus normal.
    blok = _re.search(r'const fee = \$\("fee"\)(.+?)else fee\.style\.display',
                      SCRIPT, _re.S).group(1)
    assert "F.present" in blok, "notice biaya tidak bersyarat"
    assert 'id="fee"' in HTML, "wadah biaya tidak ada di markup"

    # Netral, BUKAN alarm. Pelajaran Keputusan 29: yang bukan tuduhan
    # tidak boleh tampil seperti peringatan, atau peringatan sungguhan
    # ikut diabaikan.
    gaya = HTML[HTML.index("<style>"):HTML.index("</style>")]
    css = _re.search(r"\.fee\{([^}]+)\}", gaya).group(1)
    for alarm in ("240,116,44", "229,72,77"):   # amber & merah
        assert alarm not in css, f"notice biaya memakai warna alarm {alarm}"
    assert "var(--bg2)" in css, "notice biaya tidak memakai latar netral"

    # Dan yang terpenting: pengungkapan, bukan skor.
    assert berbiaya["risk_score"] == polos["risk_score"], (
        "tag biaya menggeser skor — itu bukan pengungkapan lagi")
    assert berbiaya["signals"] == polos["signals"]
    return "muncul hanya bila ada; netral; skor tidak bergerak"


@cek("Panel TLV hanya hidup di mode demo, dan tidak mengubah putusan")
def _f17():
    import re as _re
    c = klien()

    def minta(flag, dev):
        return c.post("/api/v1/verify", json={
            "payload": qr(), "lat": LAT, "lng": LNG,
            "device_anon_id": dev, "accuracy_m": 8.0,
            "include_tlv": flag}).json()

    mati = minta(False, "fe-tlv-mati-01")
    hidup = minta(True, "fe-tlv-hidup-1")
    assert mati["tlv"] == [] and hidup["tlv"], "include_tlv tidak berfungsi"

    # Halaman hanya meminta bedahnya kalau sakelar demo menyala —
    # bukan selalu lalu disembunyikan lewat CSS.
    assert 'id="demo"' in HTML, "tidak ada sakelar mode demo di setelan"
    badan = _re.search(r'const body = Object\.assign\((.+?)\);', SCRIPT,
                       _re.S).group(1)
    assert "include_tlv: demo.checked" in badan, (
        "permintaan tidak mengikat include_tlv pada sakelar demo")

    # Panelnya ada di markup, memakai <details> supaya tertutup secara
    # bawaan tanpa JS — pengguna biasa tidak pernah melihat isinya.
    assert '<details class="tlv"' in HTML, "panel TLV bukan elemen lipat"
    assert 'id="tlvbody"' in HTML, "wadah isi panel TLV tidak ada"
    blok = _re.search(r'const tl = \$\("tlv"\)(.+?)const rp =', SCRIPT,
                      _re.S).group(1)
    assert "entri.length" in blok, "panel tidak bersyarat pada isi tlv"
    assert "tl.open = false" in blok, (
        "panel tidak tertutup ulang tiap pemindaian baru")

    # Nilai TLV masuk lewat innerHTML dan berasal dari payload yang
    # dikendalikan penyerang — wajib di-escape.
    assert blok.count("esc(") >= 4, "isi TLV tidak di-escape sebelum dirender"

    # Forensik, bukan penilaian.
    for k in ("verdict", "action", "risk_score", "signals"):
        assert hidup[k] == mati[k], f"include_tlv menggeser {k}"
    return f"{len(hidup['tlv'])} entri di mode demo; putusan tidak bergerak"


@cek("QR yang ditukar tidak pernah sampai ke layar PIN")
def _f18():
    import re as _re
    c = klien()
    d = c.post("/api/v1/verify", json={
        "payload": qr(), "lat": LAT, "lng": LNG,
        "device_anon_id": "fe-tiket-00001", "accuracy_m": 8.0}).json()
    t = d["verification_ticket"]

    # Endpoint yang dipanggil halaman sebelum PIN.
    sama = c.post("/api/v1/tickets/verify", json={
        "ticket": t, "payload": qr()}).json()
    assert sama["valid"] is True, f"QR yang sama ditolak: {sama}"

    ditukar = c.post("/api/v1/tickets/verify", json={
        "ticket": t, "payload": qr("ID1099887766554", "936000149099999999")
    }).json()
    assert ditukar["valid"] is False, "QR ditukar tapi tiket tetap sah"

    # Halaman benar-benar memanggilnya, dan memanggilnya SEBELUM PIN.
    assert "/api/v1/tickets/verify" in SCRIPT, "halaman tidak memeriksa tiket"
    fn = _re.search(
        r'async function periksaTiketLaluBayar\(d\)\{(.+?)\n\}',
        SCRIPT, _re.S).group(1)
    assert "payloadDibayar" in fn, (
        "yang dikirim bukan payload yang hendak DIBAYAR — pemeriksaannya "
        "tidak menutup celah apa pun")

    # Cabang penolakan TIDAK BOLEH merender layar PIN. Pola yang sama
    # dengan cooling_off: bukan disembunyikan, memang tidak pernah dibuat.
    tolak = fn.split("if (r.ok && hasil.valid)")[1]
    assert "layarPin" not in tolak, (
        "cabang tolak masih memanggil layarPin — layar PIN-nya "
        "disembunyikan, bukan tidak pernah ada")
    assert "PIN-nya tidak pernah dimasukkan" in tolak, (
        "kalimat terpenting pitch tidak muncul di layar tolak")

    # Tombol simulasi serangan hanya hidup di mode demo, dan ia mengubah
    # yang DIBAYAR — bukan yang sudah diverifikasi.
    pasang = _re.search(r'function pasangTombolLanjut\(d\)\{(.+?)\n\}',
                        SCRIPT, _re.S).group(1)
    assert "demo.checked" in pasang, "tombol serangan bocor ke mode normal"
    tukar = _re.search(r'a\.onclick = \(\) => \{(.+?)\};', pasang,
                       _re.S).group(1)
    assert "payloadDibayar =" in tukar and "payloadDipindai =" not in tukar, (
        "simulasi serangan mengubah yang DIPERIKSA, bukan yang DIBAYAR")
    return "tiket diperiksa sebelum PIN; QR ditukar berhenti sebelum PIN"


@cek("Mode katalog tidak pernah mengirim koordinat")
def _f20():
    """Inti mode katalog, dan satu-satunya hal yang membuatnya aman.

    Mengkatalogkan QRIS sambil duduk di satu tempat lewat /verify
    membuat tempat itu tampak seperti jangkar yang berkali-kali
    diserang, dan pedagang sungguhan di sekitarnya ikut tertuduh. Itu
    bukan skenario hipotetis; itu yang terjadi di lapangan.

    Dikunci di sini supaya jalur katalog tidak pernah diam-diam
    memperoleh lokasi lagi.
    """
    blok = SCRIPT[SCRIPT.index("async function katalogkan"):]
    blok = blok[:blok.index("function tampilkanKatalog")]
    for terlarang in ("lokasi(", "geolocation", "lat", "lng", "accuracy"):
        assert terlarang not in blok, (
            f"jalur katalog menyentuh {terlarang!r} — ia tidak boleh "
            f"mengirim lokasi apa pun")
    assert "/api/v1/inspect" in blok, "katalog tidak memanggil /inspect"

    # Dan cabangnya harus BERHENTI sebelum lokasi diambil.
    v = SCRIPT[SCRIPT.index("async function verifikasi"):]
    potong = v.index("if (modeKatalog)")
    ambil = v.index("await lokasi()")
    assert potong < ambil, (
        "cabang katalog berada SETELAH lokasi diambil — koordinat sudah "
        "terlanjur diminta dari pengguna")
    return "nol koordinat di jalur katalog; cabangnya sebelum lokasi diambil"


@cek("Hasil katalog tidak menyamar jadi putusan")
def _f21():
    """Mode katalog tidak memeriksa lokasi, jadi tampilannya tidak boleh
    terlihat seperti sudah memeriksanya.

    Wadahnya terpisah dari hasil verifikasi dengan sengaja: berbagi slot
    membuat salah satu diam-diam mewarisi arti yang lain.
    """
    blok = SCRIPT[SCRIPT.index("function tampilkanKatalog"):]
    blok = blok[:blok.index("async function verifikasi")]
    for milik_putusan in ('$("band")', '$("title")', '$("reasons")',
                          '$("merchant")', '$("meta")'):
        assert milik_putusan not in blok, (
            f"renderer katalog menulis ke {milik_putusan}, yang dipesan "
            f"untuk hasil verifikasi")
    assert 'a-proceed' not in blok and 'a-cooling_off' not in blok, (
        "hasil katalog memakai warna putusan")
    assert "tidak diperiksa" in SCRIPT, (
        "pengguna tidak diberi tahu bahwa lokasi tidak diperiksa")
    return "wadah sendiri, warna netral, dan ketiadaan pemeriksaan disebut"


print("=" * 70)
print("FRONTEND <-> API")
print("=" * 70)
print()
gagal = 0
for nama, ok, detail in _hasil:
    print(f"  [{'OK   ' if ok else 'GAGAL'}]  {nama}")
    if detail:
        print(f"           {detail}")
    if not ok:
        gagal += 1
print()
print("-" * 70)
if gagal:
    print(f"{gagal} dari {len(_hasil)} pemeriksaan GAGAL.")
    sys.exit(1)
print(f"Seluruh {len(_hasil)} pemeriksaan lolos.")
