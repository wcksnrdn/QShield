"""
Penyimpanan binding.

SQLite untuk PoC. Skema sengaja dibuat portabel ke Postgres:
tidak ada fitur khusus SQLite selain tipe kolom.

Catatan privasi — ini keputusan desain, bukan detail teknis:
  - tidak ada kolom user_id di mana pun
  - tabel observations tidak menyimpan koordinat, sehingga tidak
    bisa dipakai merekonstruksi pergerakan seseorang
  - device_anon_id TIDAK PERNAH disimpan apa adanya; yang masuk tabel
    adalah hash yang dilingkupi per-binding, sehingga baris pengamatan
    tidak bisa dirangkai antar-lokasi menjadi jejak perjalanan

Agregat Layer 2 (anomaly_attempts) menempel pada baris
BINDING, bukan pada device. Isinya hitungan dan waktu, bukan siapa —
tidak ada baris per-device baru dan tidak ada koordinat tambahan, jadi
tidak ada jejak pergerakan yang bisa direkonstruksi darinya.
"""

import hashlib
import os
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import behavior as bh
from . import binding as bd
from . import geo

SCHEMA = """
CREATE TABLE IF NOT EXISTS bindings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nmid            TEXT    NOT NULL,
    lat             REAL    NOT NULL,
    lng             REAL    NOT NULL,
    geohash_7       TEXT    NOT NULL,
    geohash_6       TEXT    NOT NULL,
    merchant_name   TEXT,
    observer_count  INTEGER NOT NULL DEFAULT 0,
    registered_at   TEXT,
    is_mobile       INTEGER NOT NULL DEFAULT 0,
    -- Titik mula-mula, disimpan HANYA sebagai acuan batas geser.
    -- lat/lng di atas adalah jangkar yang dipakai: rata-rata berjalan
    -- dari pemindaian yang masuk radius.
    origin_lat      REAL,
    origin_lng      REAL,
    first_seen      TEXT    NOT NULL,
    last_seen       TEXT    NOT NULL,
    anomaly_attempts   INTEGER NOT NULL DEFAULT 0,
    last_anomaly_at    TEXT,
    UNIQUE (nmid, geohash_7)
);

-- device_ref = sha256(salt || binding_id || device_anon_id)
--
-- Dilingkupi per-binding DENGAN SENGAJA. Perangkat yang sama
-- menghasilkan nilai berbeda di tiap binding, sehingga:
--   - dedup per binding tetap bekerja (itu satu-satunya yang dibutuhkan)
--   - baris TIDAK BISA dirangkai antar-binding jadi jejak perjalanan
--
-- Versi sebelumnya menyimpan device_anon_id apa adanya, dan satu JOIN ke
-- bindings sudah cukup untuk memulihkan koordinat lengkap plus urutan
-- waktu satu perangkat. Klaim "tidak dapat dipakai merekonstruksi
-- pergerakan" jadi tidak benar. Sekarang benar.
CREATE TABLE IF NOT EXISTS observations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    binding_id      INTEGER NOT NULL REFERENCES bindings(id),
    device_ref      TEXT    NOT NULL,
    observed_at     TEXT    NOT NULL,
    UNIQUE (binding_id, device_ref)
);

-- Pemindaian yang DITOLAK di sebuah jangkar, dicatat per NMID penantang.
--
-- Bukan reputasi dan tidak pernah menyentuh observer_count — invarian §3
-- utuh. Gunanya satu: membuktikan KEHADIRAN FISIK yang berkelanjutan.
--
-- Pembedanya bersifat fisik, bukan statistik. Stiker yang ditempel
-- MENUTUPI membuat QR aslinya tidak bisa dipindai lagi, sehingga merchant
-- lama berhenti terlihat. Dua pedagang bersebelahan sungguhan terus
-- terlihat berdua. Penyerang tidak bisa memalsukan yang kedua tanpa
-- membatalkan serangannya sendiri.
--
-- device_ref dilingkupi per (jangkar, nmid) dengan alasan yang sama
-- seperti observations: baris tidak boleh bisa dirangkai antar-tempat
-- menjadi jejak perjalanan.
CREATE TABLE IF NOT EXISTS anchor_challenge (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    geohash_7     TEXT    NOT NULL,
    nmid          TEXT    NOT NULL,
    device_ref    TEXT    NOT NULL,
    attempted_at  TEXT    NOT NULL,
    UNIQUE (geohash_7, nmid, device_ref)
);

CREATE INDEX IF NOT EXISTS idx_challenge_lookup
    ON anchor_challenge (geohash_7, nmid);

CREATE TABLE IF NOT EXISTS meta (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

-- Pernyataan penyelenggara, bukan pengamatan pengguna. Sengaja tabel
-- TERPISAH dari bindings dan observations: keduanya berisi jejak
-- pengguna dan tunduk pada aturan privasi; yang ini berisi pernyataan
-- lembaga dan tunduk pada aturan akuntabilitas. Kita PERLU tahu PJP
-- mana yang mendaftarkan apa — kalau kuncinya bocor, itu satu-satunya
-- cara mencabut yang terlanjur didaftarkannya.
CREATE TABLE IF NOT EXISTS registrations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    nmid           TEXT    NOT NULL,
    registrar      TEXT    NOT NULL,   -- client_id PJP, bukan pengguna
    lat            REAL    NOT NULL,
    lng            REAL    NOT NULL,
    merchant_name  TEXT,
    is_mobile      INTEGER NOT NULL DEFAULT 0,
    registered_at  TEXT    NOT NULL,
    revoked_at     TEXT,
    UNIQUE (nmid)
);

-- Jejak pemakaian QR DINAMIS. Yang dilacak adalah ARTEFAKNYA, bukan
-- orangnya: tidak ada device apa pun di sini. Koordinat yang disimpan
-- adalah tempat QR itu pertama terlihat — properti mesin kasir, sama
-- kategorinya dengan koordinat di tabel bindings.
--
-- QR dinamis berumur pendek, jadi barisnya dipangkas berkala.
CREATE TABLE IF NOT EXISTS dynamic_qr (
    payload_hash   TEXT PRIMARY KEY,
    nmid           TEXT    NOT NULL,
    lat            REAL    NOT NULL,
    lng            REAL    NOT NULL,
    times_seen     INTEGER NOT NULL DEFAULT 1,
    max_spread_m   REAL    NOT NULL DEFAULT 0,
    first_seen     TEXT    NOT NULL,
    last_seen      TEXT    NOT NULL
);

-- Apa nama kota yang dilaporkan QRIS di suatu wilayah.
--
-- Yang dihitung adalah NMID BERBEDA, bukan jumlah pemindaian. Itu yang
-- membuatnya sulit diracuni: penipu punya segelintir NMID, sedangkan
-- wilayah sungguhan punya puluhan merchant. Seribu pemindaian dari satu
-- stiker palsu tetap terhitung satu suara.
CREATE TABLE IF NOT EXISTS area_city (
    geohash_5  TEXT NOT NULL,
    city       TEXT NOT NULL,
    nmid       TEXT NOT NULL,
    PRIMARY KEY (geohash_5, city, nmid)
);

-- Dialek penerbit: bagaimana tiap PJP MENYUSUN payload-nya.
--
-- Dikunci pada prefiks PAN (8 digit awal = kode penyelenggara), bukan
-- pada merchant. Yang dihitung NMID berbeda, dengan alasan yang sama
-- seperti area_city: satu stiker yang dipindai seribu kali tetap satu
-- suara.
CREATE TABLE IF NOT EXISTS issuer_dialect (
    pan_prefix  TEXT NOT NULL,
    attribute   TEXT NOT NULL,
    value       TEXT NOT NULL,
    nmid        TEXT NOT NULL,
    PRIMARY KEY (pan_prefix, attribute, value, nmid)
);

-- Reputasi rekening tujuan transfer manual.
--
-- Inilah lapisan bersama untuk jalur non-QRIS: rekening penampung tidak
-- berhenti di batas satu penyelenggara, persis seperti stiker penipu
-- tidak berhenti di batas satu penyelenggara.
--
-- Yang disimpan adalah HASH nomor rekening, bukan nomornya. Cukup untuk
-- mengenali rekening yang sama dilaporkan lagi, tidak cukup untuk
-- memulihkan daftar nomor rekening dari basis data yang bocor.
--
-- Yang dinilai adalah PENERIMA uang — pihak yang dalam skenario
-- penipuan adalah pelakunya. Identitas PEMBAYAR tidak pernah masuk ke
-- sini, sama seperti invarian §8 pada jalur QRIS.
CREATE TABLE IF NOT EXISTS beneficiary_report (
    account_hash  TEXT NOT NULL,
    reporter      TEXT NOT NULL,
    reported_at   TEXT NOT NULL,
    PRIMARY KEY (account_hash, reporter)
);

-- Sebaran ciri merchant, untuk model kelangkaan tak-terawasi.
--
-- Yang dihitung NMID berbeda, bukan jumlah pemindaian — alasan yang
-- sama dengan area_city dan issuer_dialect. Tidak ada satu pun ciri di
-- sini yang khas satu merchant: hanya kategori, skala, kota, dan
-- bentuk-bentuk yang dipakai bersama oleh banyak merchant.
CREATE TABLE IF NOT EXISTS merchant_feature (
    feature  TEXT NOT NULL,
    value    TEXT NOT NULL,
    nmid     TEXT NOT NULL,
    PRIMARY KEY (feature, value, nmid)
);

-- Sidik jari WiFi sekitar milik sebuah jangkar.
--
-- Yang disimpan adalah HASH titik akses yang dikirim klien — klien
-- yang melakukan hashing, jadi BSSID mentah tidak pernah sampai ke
-- sini. Menempel pada BINDING, yaitu properti lokasi merchant, bukan
-- pada pengamat: sekategori dengan koordinat, dan tunduk aturan yang
-- sama (Keputusan 6).
--
-- Gunanya memisahkan dua lapak berdempetan yang GPS-nya tidak sanggup
-- membedakan, dan menguatkan jangkar saat sinyal GPS buruk di dalam
-- gedung — dua hal yang selama ini jadi batasan R3.
CREATE TABLE IF NOT EXISTS binding_ap (
    binding_id  INTEGER NOT NULL REFERENCES bindings(id),
    ap_hash     TEXT    NOT NULL,
    seen_count  INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (binding_id, ap_hash)
);

CREATE INDEX IF NOT EXISTS idx_bap ON binding_ap(binding_id);
CREATE INDEX IF NOT EXISTS idx_mfeat ON merchant_feature(feature);
CREATE INDEX IF NOT EXISTS idx_benef ON beneficiary_report(account_hash);
CREATE INDEX IF NOT EXISTS idx_dialect ON issuer_dialect(pan_prefix, attribute);
CREATE INDEX IF NOT EXISTS idx_areacity ON area_city(geohash_5);
-- Nominal yang pernah muncul untuk satu nomor tagihan.
--
-- Tagihan yang sama seharusnya tidak berganti nominal. Penipu yang
-- mencegat QR dinamis lalu mengubah nominalnya menghasilkan hash
-- payload berbeda — sehingga lolos dari deteksi pemakaian ulang — tapi
-- nomor tagihannya tetap.
CREATE TABLE IF NOT EXISTS dynamic_bill (
    nmid        TEXT NOT NULL,
    bill_ref    TEXT NOT NULL,
    amount      TEXT NOT NULL,
    lat         REAL NOT NULL,
    lng         REAL NOT NULL,
    seen_at     TEXT NOT NULL,
    PRIMARY KEY (nmid, bill_ref, amount)
);

CREATE INDEX IF NOT EXISTS idx_bill_seen ON dynamic_bill(seen_at);
CREATE INDEX IF NOT EXISTS idx_dynqr_last ON dynamic_qr(last_seen);
CREATE INDEX IF NOT EXISTS idx_reg_nmid ON registrations(nmid);
CREATE INDEX IF NOT EXISTS idx_bindings_gh7  ON bindings(geohash_7);
CREATE INDEX IF NOT EXISTS idx_bindings_nmid ON bindings(nmid);
"""


SALT_KEY = "device_salt"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _row_to_binding(row: sqlite3.Row) -> bd.Binding:
    return bd.Binding(
        nmid=row["nmid"],
        lat=row["lat"],
        lng=row["lng"],
        geohash_7=row["geohash_7"],
        geohash_6=row["geohash_6"],
        merchant_name=row["merchant_name"],
        observer_count=row["observer_count"],
        first_seen=_parse(row["first_seen"]),
        last_seen=_parse(row["last_seen"]),
        registered_at=_parse(row["registered_at"]),
        is_mobile=bool(row["is_mobile"]),
    )


class Store:
    # Pembuatan skema pertama kali menjalankan DDL, dan DDL di SQLite
    # menuntut kunci eksklusif. Kalau beberapa proses membuka basis data
    # yang BELUM ADA secara bersamaan — persis yang terjadi saat
    # `uvicorn --workers N` start dingin — salah satunya bisa kena
    # "database is locked" meski busy_timeout sudah terpasang, karena
    # timeout tidak berlaku untuk sebagian jalur DDL.
    #
    # Terukur: pada 12 proses serentak, satu gagal start. Retry terbatas
    # menutupnya tanpa menyembunyikan kesalahan yang sesungguhnya —
    # setelah percobaan habis, galatnya dilempar apa adanya.
    INIT_RETRIES = 5
    INIT_BACKOFF_S = 0.15

    def __init__(self, path: str = "qshield.db"):
        # isolation_level=None mematikan transaksi implisit sqlite3 supaya
        # record() bisa membuka transaksinya sendiri secara eksplisit.
        self.conn = sqlite3.connect(
            path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row

        # Satu koneksi dipakai bersama oleh seluruh thread — dan uvicorn
        # menjalankan endpoint sync di threadpool, jadi permintaan yang
        # datang bersamaan benar-benar menyentuh koneksi ini serentak.
        # Tanpa kunci, sqlite3 melempar InterfaceError / "another row
        # available" dan hitungan pengamat hilang. Terukur: 25 dari 60
        # permintaan paralel gagal, observations 41 dari 60.
        self._lock = threading.RLock()

        # busy_timeout HARUS lebih dulu dari pragma dan DDL apa pun.
        # Peralihan ke WAL sendiri butuh kunci eksklusif sesaat, dan
        # kalau timeout-nya belum terpasang saat itu, proses kedua yang
        # membuka basis data yang sama langsung kena "database is
        # locked" alih-alih menunggu. Terukur: 5 dari 6 proses gagal
        # start hanya karena urutan dua baris ini terbalik.
        self.conn.execute("PRAGMA busy_timeout = 5000")
        self.conn.execute("PRAGMA foreign_keys = ON")
        # WAL membuat pembaca tidak memblokir penulis.
        self.conn.execute("PRAGMA journal_mode = WAL")
        terakhir = None
        for percobaan in range(self.INIT_RETRIES):
            try:
                self.conn.executescript(SCHEMA)
                self._salt = self._ensure_salt()
                self._migrate()
                break
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc) and "busy" not in str(exc):
                    raise
                terakhir = exc
                time.sleep(self.INIT_BACKOFF_S * (percobaan + 1))
        else:
            raise terakhir

    def _ensure_salt(self) -> str:
        """Garam untuk device_ref, stabil sepanjang umur basis data.

        Diambil dari QSHIELD_DEVICE_SALT kalau disetel; kalau tidak,
        dibangkitkan sekali lalu disimpan. Harus stabil — mengubahnya
        membuat hash lama tidak lagi cocok, sehingga perangkat yang
        pernah tercatat terhitung ulang sebagai pengamat baru.

        Garamnya tidak menyembunyikan apa pun dari pemegang basis data;
        yang mencegah perangkaian jejak adalah pelingkupan per-binding.
        Garam menambah lapisan terhadap komputasi awal (precomputation).
        """
        dari_env = os.environ.get("QSHIELD_DEVICE_SALT", "").strip()
        if dari_env:
            return dari_env

        baris = self.conn.execute(
            "SELECT value FROM meta WHERE key = ?", (SALT_KEY,)).fetchone()
        if baris:
            return baris["value"]

        garam = secrets.token_hex(16)
        self.conn.execute(
            "INSERT OR IGNORE INTO meta (key, value) VALUES (?, ?)",
            (SALT_KEY, garam))
        baris = self.conn.execute(
            "SELECT value FROM meta WHERE key = ?", (SALT_KEY,)).fetchone()
        return baris["value"]

    def device_ref(self, binding_id: int, device_anon_id: str) -> str:
        """Rujukan perangkat yang hanya berlaku di dalam satu binding."""
        bahan = f"{self._salt}|{binding_id}|{device_anon_id}".encode("utf-8")
        return hashlib.sha256(bahan).hexdigest()

    def _migrate(self):
        """Tambahkan kolom agregat Layer 2 ke database lama.

        SQLite tidak punya ADD COLUMN IF NOT EXISTS, jadi kolom yang ada
        diperiksa dulu. Semua kolom baru punya DEFAULT sehingga baris
        lama tetap sah tanpa backfill.
        """
        ada = {c["name"] for c in
               self.conn.execute("PRAGMA table_info(bindings)").fetchall()}
        tambahan = {
            "anomaly_attempts": "INTEGER NOT NULL DEFAULT 0",
            "last_anomaly_at": "TEXT",
            "registered_at": "TEXT",
            "is_mobile": "INTEGER NOT NULL DEFAULT 0",
            "origin_lat": "REAL",
            "origin_lng": "REAL",
        }
        for nama, tipe in tambahan.items():
            if nama not in ada:
                self.conn.execute(
                    f"ALTER TABLE bindings ADD COLUMN {nama} {tipe}")

        self._migrate_device_ref()

    def _migrate_device_ref(self):
        """Ganti kolom device_anon_id lama dengan device_ref berlingkup.

        Basis data lama menyimpan pengenal perangkat apa adanya, dan itu
        bisa di-JOIN jadi jejak perjalanan. Nilai lamanya di-hash di
        tempat lalu kolomnya dibuang — bukan sekadar berhenti dipakai,
        karena data yang masih ada tetap bisa dibaca siapa pun yang
        memegang berkasnya.
        """
        kolom = {c["name"] for c in
                 self.conn.execute("PRAGMA table_info(observations)").fetchall()}
        if "device_anon_id" not in kolom:
            return

        lama = self.conn.execute(
            "SELECT id, binding_id, device_anon_id, observed_at "
            "FROM observations").fetchall()

        self.conn.execute("""
            CREATE TABLE observations_baru (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                binding_id  INTEGER NOT NULL REFERENCES bindings(id),
                device_ref  TEXT    NOT NULL,
                observed_at TEXT    NOT NULL,
                UNIQUE (binding_id, device_ref)
            )""")
        for r in lama:
            self.conn.execute(
                """INSERT OR IGNORE INTO observations_baru
                   (id, binding_id, device_ref, observed_at)
                   VALUES (?, ?, ?, ?)""",
                (r["id"], r["binding_id"],
                 self.device_ref(r["binding_id"], r["device_anon_id"]),
                 r["observed_at"]),
            )
        self.conn.execute("DROP TABLE observations")
        self.conn.execute(
            "ALTER TABLE observations_baru RENAME TO observations")

    def close(self):
        with self._lock:
            self.conn.close()

    # --- pembacaan -------------------------------------------------

    def nearby(self, lat: float, lng: float) -> list:
        """Binding di sel indeks sekitar titik ini.

        Penyaringan jarak dilakukan di binding.evaluate(), bukan di sini.
        """
        cells = bd.index_cells(lat, lng)
        marks = ",".join("?" * len(cells))
        with self._lock:
            rows = self.conn.execute(
                f"SELECT * FROM bindings WHERE geohash_7 IN ({marks})", cells
            ).fetchall()
        return [_row_to_binding(r) for r in rows]

    def by_nmid(self, nmid: str) -> list:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM bindings WHERE nmid = ?", (nmid,)
            ).fetchall()
        return [_row_to_binding(r) for r in rows]

    def anchor_state(self, lat: float, lng: float,
                     now: Optional[datetime] = None):
        """Agregat Layer 2 milik jangkar di titik ini.

        Jangkar diwakili binding paling kuat buktinya di radius jangkar:
        yang sudah mapan kalau ada, kalau tidak yang paling banyak
        pengamatnya. Mengembalikan (binding_id, nmid, AnchorState);
        binding_id None kalau belum ada binding di sini sama sekali.
        """
        now = now or datetime.now(timezone.utc)
        cells = bd.index_cells(lat, lng)
        marks = ",".join("?" * len(cells))
        with self._lock:
            rows = self.conn.execute(
                f"SELECT * FROM bindings WHERE geohash_7 IN ({marks})", cells
            ).fetchall()

        di_jangkar = [
            r for r in rows
            if geo.haversine_m(r["lat"], r["lng"], lat, lng) <= bd.ANCHOR_RADIUS_M
        ]
        if not di_jangkar:
            return None, None, bh.AnchorState()

        mapan = [r for r in di_jangkar if _row_to_binding(r).is_established]
        dipilih = max(mapan or di_jangkar, key=lambda r: r["observer_count"])
        self._anchor_has_owner = bool(mapan)

        return dipilih["id"], dipilih["nmid"], bh.AnchorState(
            anomaly_attempts=dipilih["anomaly_attempts"],
            last_anomaly_at=_parse(dipilih["last_anomaly_at"]),
        )

    def stats(self) -> dict:
        with self._lock:
            b = self.conn.execute(
                "SELECT COUNT(*) c FROM bindings").fetchone()["c"]
            o = self.conn.execute(
                "SELECT COUNT(*) c FROM observations").fetchone()["c"]
            n = self.conn.execute(
                "SELECT COUNT(DISTINCT nmid) c FROM bindings").fetchone()["c"]
        return {"bindings": b, "observations": o, "merchants": n}

    # --- penulisan -------------------------------------------------

    def record(
        self,
        nmid: str,
        lat: float,
        lng: float,
        device_anon_id: str,
        merchant_name: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> bd.Binding:
        """Catat satu pengamatan. Idempoten per (binding, device).

        Seluruh urutannya berjalan dalam SATU transaksi. Versi lama
        melakukan SELECT lalu INSERT/UPDATE terpisah — dua permintaan yang
        datang bersamaan bisa sama-sama membaca state yang sama, lalu
        sama-sama menulis. Akibatnya terukur: 25 dari 60 permintaan
        paralel gagal dan observer_count berhenti di 40, bukan 60.

        Perlu dicatat, ini bukan kelemahan SQLite. Urutan baca-ubah-tulis
        yang sama akan balapan di Postgres juga; yang menyelesaikannya
        adalah upsert atomik di bawah, bukan pindah database.
        """
        now = now or datetime.now(timezone.utc)
        gh7 = geo.encode(lat, lng, bd.INDEX_PRECISION)
        gh6 = geo.encode(lat, lng, bd.AREA_PRECISION)
        waktu = _iso(now)

        with self._lock:
            # IMMEDIATE mengambil kunci tulis sejak awal, bukan menunggu
            # sampai penulisan pertama — mencegah dua transaksi sama-sama
            # maju lalu salah satunya gagal di tengah jalan.
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                # Upsert: baris dibuat kalau belum ada, diperbarui kalau
                # sudah. Tidak ada celah antara memeriksa dan menulis.
                # merchant_name hanya diisi kalau sebelumnya kosong.
                row = self.conn.execute(
                    """INSERT INTO bindings
                       (nmid, lat, lng, geohash_7, geohash_6, merchant_name,
                        observer_count, first_seen, last_seen)
                       VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
                       ON CONFLICT (nmid, geohash_7) DO UPDATE SET
                           last_seen = excluded.last_seen,
                           merchant_name = COALESCE(bindings.merchant_name,
                                                    excluded.merchant_name)
                       RETURNING id""",
                    (nmid, lat, lng, gh7, gh6, merchant_name, waktu, waktu),
                ).fetchone()
                binding_id = row["id"]

                # Satu device hanya dihitung sekali per binding. Yang
                # disimpan adalah rujukan berlingkup, bukan pengenalnya.
                inserted = self.conn.execute(
                    """INSERT OR IGNORE INTO observations
                       (binding_id, device_ref, observed_at)
                       VALUES (?, ?, ?)""",
                    (binding_id, self.device_ref(binding_id, device_anon_id),
                     waktu),
                ).rowcount

                if inserted:
                    # Penambahan dilakukan di dalam SQL, bukan di Python,
                    # supaya tidak ada nilai lama yang dibaca lebih dulu.
                    self.conn.execute(
                        """UPDATE bindings
                           SET observer_count = observer_count + 1
                           WHERE id = ?""",
                        (binding_id,),
                    )
                    # Jangkar dihaluskan HANYA saat ada pengamat baru.
                    # Pemindaian berulang dari device yang sama tidak
                    # menggeser apa pun — menyeret jangkar sejauh N
                    # langkah menuntut N pengenal perangkat berbeda,
                    # ongkos yang sama dengan memalsukan konsensus.
                    self._haluskan_jangkar(binding_id, lat, lng)

                hasil = self.conn.execute(
                    "SELECT * FROM bindings WHERE id = ?", (binding_id,)
                ).fetchone()
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise

        return _row_to_binding(hasil)

    # --- pendaftaran merchant --------------------------------------

    def register(self, nmid: str, registrar: str, lat: float, lng: float,
                 merchant_name: Optional[str] = None, is_mobile: bool = False,
                 now: Optional[datetime] = None) -> dict:
        """Catat pernyataan PJP tentang ikatan merchant-lokasi.

        Ini BUKAN pengamatan: observer_count tidak disentuh sama sekali,
        jadi pendaftaran tidak bisa dipakai memalsukan konsensus. Yang
        dilakukannya adalah menandai binding sebagai terdaftar, dan
        penandaan itu punya sinyal sendiri di penilaian — supaya
        verified-karena-terdaftar selalu bisa dibedakan dari
        verified-karena-diamati.
        """
        now = now or datetime.now(timezone.utc)
        gh7 = geo.encode(lat, lng, bd.INDEX_PRECISION)
        gh6 = geo.encode(lat, lng, bd.AREA_PRECISION)
        waktu = _iso(now)

        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                lama = self.conn.execute(
                    "SELECT registrar, revoked_at FROM registrations "
                    "WHERE nmid = ?", (nmid,)).fetchone()
                # Satu PJP tidak boleh membajak pendaftaran PJP lain.
                if lama and lama["registrar"] != registrar and not lama["revoked_at"]:
                    self.conn.execute("ROLLBACK")
                    return {"ok": False, "reason": "terdaftar_pjp_lain"}

                self.conn.execute(
                    """INSERT INTO registrations
                       (nmid, registrar, lat, lng, merchant_name, is_mobile,
                        registered_at, revoked_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                       ON CONFLICT (nmid) DO UPDATE SET
                           registrar = excluded.registrar,
                           lat = excluded.lat, lng = excluded.lng,
                           merchant_name = excluded.merchant_name,
                           is_mobile = excluded.is_mobile,
                           registered_at = excluded.registered_at,
                           revoked_at = NULL""",
                    (nmid, registrar, lat, lng, merchant_name,
                     int(is_mobile), waktu))

                # Relokasi sah: jangkar lama milik NMID ini berhenti
                # dianggap terdaftar, supaya tidak ada dua tempat resmi.
                self.conn.execute(
                    "UPDATE bindings SET registered_at = NULL WHERE nmid = ?",
                    (nmid,))

                self.conn.execute(
                    """INSERT INTO bindings
                       (nmid, lat, lng, geohash_7, geohash_6, merchant_name,
                        observer_count, first_seen, last_seen,
                        registered_at, is_mobile)
                       VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
                       ON CONFLICT (nmid, geohash_7) DO UPDATE SET
                           registered_at = excluded.registered_at,
                           is_mobile = excluded.is_mobile,
                           merchant_name = COALESCE(excluded.merchant_name,
                                                    bindings.merchant_name)""",
                    (nmid, lat, lng, gh7, gh6, merchant_name, waktu, waktu,
                     waktu, int(is_mobile)))
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise
        return {"ok": True, "nmid": nmid, "registered_at": waktu,
                "registrar": registrar, "is_mobile": is_mobile}

    def revoke(self, nmid: str, registrar: str,
               now: Optional[datetime] = None) -> dict:
        """Cabut pendaftaran. Hanya PJP yang mendaftarkan yang boleh."""
        now = now or datetime.now(timezone.utc)
        with self._lock:
            baris = self.conn.execute(
                "SELECT registrar, revoked_at FROM registrations WHERE nmid = ?",
                (nmid,)).fetchone()
            if not baris:
                return {"ok": False, "reason": "tidak_terdaftar"}
            if baris["registrar"] != registrar:
                return {"ok": False, "reason": "bukan_pendaftarnya"}

            self.conn.execute(
                "UPDATE registrations SET revoked_at = ? WHERE nmid = ?",
                (_iso(now), nmid))
            # Bindingnya TIDAK dihapus: pengamatan yang sudah terkumpul
            # tetap sah sebagai bukti konsensus. Yang dicabut hanya
            # status terdaftarnya.
            self.conn.execute(
                "UPDATE bindings SET registered_at = NULL WHERE nmid = ?",
                (nmid,))
        return {"ok": True, "nmid": nmid, "revoked_at": _iso(now)}

    def registration(self, nmid: str):
        with self._lock:
            r = self.conn.execute(
                "SELECT * FROM registrations WHERE nmid = ? AND revoked_at IS NULL",
                (nmid,)).fetchone()
        return dict(r) if r else None

    # --- jejak QR dinamis ------------------------------------------

    def note_dynamic_qr(self, payload: str, nmid: str, lat: float, lng: float,
                        now: Optional[datetime] = None) -> dict:
        """Catat satu kemunculan QR dinamis, kembalikan riwayatnya.

        Dicatat TERLEPAS dari verdict — ini bukan pengamatan yang
        membangun reputasi (invarian §3 tidak tersentuh), melainkan
        penghitung pemakaian sebuah artefak sekali pakai. Angkanya hanya
        pernah menaikkan risiko, tidak pernah menurunkan.

        Yang disimpan adalah hash payload, bukan payloadnya: cukup untuk
        mengenali QR yang sama muncul lagi, tidak cukup untuk memulihkan
        identitas merchant dari basis data yang bocor.
        """
        now = now or datetime.now(timezone.utc)
        h = hashlib.sha256(f"{self._salt}|{payload}".encode("utf-8")).hexdigest()
        waktu = _iso(now)

        # Pemangkasan dititipkan ke jalur tulis alih-alih penjadwal
        # terpisah: satu proses lebih sedikit yang bisa mati diam-diam,
        # dan tabel ini hanya tumbuh saat ada yang menulisinya.
        self._dyn_writes = getattr(self, "_dyn_writes", 0) + 1
        if self._dyn_writes % 500 == 0:
            self.prune_dynamic_qr(now)

        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                baris = self.conn.execute(
                    "SELECT * FROM dynamic_qr WHERE payload_hash = ?", (h,)
                ).fetchone()

                if baris is None:
                    self.conn.execute(
                        """INSERT INTO dynamic_qr
                           (payload_hash, nmid, lat, lng, times_seen,
                            max_spread_m, first_seen, last_seen)
                           VALUES (?, ?, ?, ?, 1, 0, ?, ?)""",
                        (h, nmid, lat, lng, waktu, waktu))
                    hasil = {"times_seen": 1, "max_spread_m": 0.0,
                             "first_seen": now}
                else:
                    sebar = max(
                        baris["max_spread_m"],
                        geo.haversine_m(baris["lat"], baris["lng"], lat, lng))
                    self.conn.execute(
                        """UPDATE dynamic_qr
                           SET times_seen = times_seen + 1,
                               max_spread_m = ?, last_seen = ?
                           WHERE payload_hash = ?""",
                        (sebar, waktu, h))
                    hasil = {"times_seen": baris["times_seen"] + 1,
                             "max_spread_m": sebar,
                             "first_seen": _parse(baris["first_seen"])}
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise
        return hasil

    def note_bill(self, nmid: str, bill_ref: str, amount: str,
                  lat: float, lng: float,
                  now: Optional[datetime] = None) -> list:
        """Catat nominal untuk satu tagihan, kembalikan nominal lain
        yang pernah muncul untuk tagihan yang sama.

        Dibatasi masa hidup yang sama dengan jejak QR dinamis: sebagian
        mesin kasir mengulang penomoran tagihan tiap hari, jadi tagihan
        yang sama minggu depan bukan tagihan yang sama.
        """
        now = now or datetime.now(timezone.utc)
        batas = _iso(now - timedelta(hours=bd.DYNAMIC_QR_TTL_HOURS))
        with self._lock:
            lama = self.conn.execute(
                "SELECT amount, lat, lng FROM dynamic_bill "
                "WHERE nmid = ? AND bill_ref = ? AND amount != ? "
                "AND seen_at >= ?",
                (nmid, bill_ref, amount, batas)).fetchall()
            self.conn.execute(
                "INSERT INTO dynamic_bill "
                "(nmid, bill_ref, amount, lat, lng, seen_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (nmid, bill_ref, amount) DO UPDATE SET "
                "seen_at = excluded.seen_at",
                (nmid, bill_ref, amount, lat, lng, _iso(now)))
        return [dict(r) for r in lama]

    def prune_dynamic_qr(self, now: Optional[datetime] = None) -> int:
        """Buang jejak QR dinamis yang sudah lewat masa hidupnya."""
        now = now or datetime.now(timezone.utc)
        batas = _iso(now - timedelta(hours=bd.DYNAMIC_QR_TTL_HOURS))
        with self._lock:
            cur = self.conn.execute(
                "DELETE FROM dynamic_qr WHERE last_seen < ?", (batas,))
            self.conn.execute(
                "DELETE FROM dynamic_bill WHERE seen_at < ?", (batas,))
        return cur.rowcount

    # --- pengetahuan wilayah ---------------------------------------

    def learn_city(self, lat: float, lng: float, city: Optional[str],
                   nmid: str) -> None:
        """Catat bahwa satu merchant di wilayah ini menyebut kotanya begini.

        Dipanggil HANYA untuk pemindaian yang tidak anomali, dengan
        alasan yang sama seperti invarian §3: pemindaian yang ditolak
        tidak boleh ikut membentuk pengetahuan sistem.
        """
        kota = bd.normalize_city(city)
        if not kota:
            return
        gh5 = geo.encode(lat, lng, bd.AREA_CITY_PRECISION)
        with self._lock:
            self.conn.execute(
                "INSERT OR IGNORE INTO area_city (geohash_5, city, nmid) "
                "VALUES (?, ?, ?)", (gh5, kota, nmid))

    def learn_dialect(self, parsed, nmid: str) -> None:
        """Catat gaya penyusunan payload ini atas nama penerbitnya."""
        from . import emvco

        # Prefiks PAN menandai penyelenggara penerbit, dan PAN itu ada
        # di template acquirer — bukan selalu di template yang sama
        # dengan NMID. Lihat emvco.acquirer_account.
        pan = parsed.merchant_pan
        if not pan or len(pan) < 8:
            return
        prefix = pan[:8]
        with self._lock:
            for atribut, nilai in emvco.dialect(parsed).items():
                self.conn.execute(
                    "INSERT OR IGNORE INTO issuer_dialect "
                    "(pan_prefix, attribute, value, nmid) VALUES (?, ?, ?, ?)",
                    (prefix, atribut, nilai, nmid))

    def learn_ap(self, binding_id: int, ap_hashes) -> None:
        """Catat titik akses yang terlihat di jangkar ini."""
        if not ap_hashes:
            return
        with self._lock:
            for h in set(ap_hashes):
                self.conn.execute(
                    "INSERT INTO binding_ap (binding_id, ap_hash, seen_count) "
                    "VALUES (?, ?, 1) ON CONFLICT (binding_id, ap_hash) "
                    "DO UPDATE SET seen_count = seen_count + 1",
                    (binding_id, str(h)[:64]))

    def ap_fingerprint(self, binding_id: int) -> set:
        """Titik akses yang pernah terlihat di jangkar ini."""
        with self._lock:
            baris = self.conn.execute(
                "SELECT ap_hash FROM binding_ap WHERE binding_id = ?",
                (binding_id,)).fetchall()
        return {r["ap_hash"] for r in baris}

    def locate_by_ap(self, ap_hashes, min_overlap: float):
        """Jangkar mana yang sidik jari WiFi-nya paling cocok dengan pemindaian ini.

        Kebalikan arah dari ap_fingerprint(): di sana kita sudah tahu
        jangkarnya dan ingin membandingkan; di sini justru jangkarnya yang
        dicari. Dipakai ketika GPS tidak bisa dipercaya — di dalam ruko,
        basement, atau lantai atas — sehingga koordinat tidak bisa
        menunjukkan tempatnya.

        Titik akses lebih sulit dipalsukan daripada koordinat: memalsukan
        GPS cukup satu sakelar di opsi pengembang, sedangkan memalsukan
        daftar titik akses menuntut kehadiran fisik di jangkauan radio
        yang sama.

        Kembalikan (binding, irisan). Binding None kalau tidak ada yang
        cukup meyakinkan.
        """
        diamati = {str(a)[:64] for a in (ap_hashes or ())}
        if len(diamati) < bh.AP_MIN_KNOWN:
            return None, 0.0

        tanda = ",".join("?" * len(diamati))
        with self._lock:
            kandidat = self.conn.execute(
                f"""SELECT binding_id, COUNT(*) AS irisan
                    FROM binding_ap WHERE ap_hash IN ({tanda})
                    GROUP BY binding_id""",
                tuple(diamati)).fetchall()

            terbaik, skor_terbaik = None, 0.0
            for k in kandidat:
                total = self.conn.execute(
                    "SELECT COUNT(*) AS n FROM binding_ap WHERE binding_id = ?",
                    (k["binding_id"],)).fetchone()["n"]
                gabungan = len(diamati) + total - k["irisan"]
                skor = k["irisan"] / gabungan if gabungan else 0.0
                if skor > skor_terbaik:
                    terbaik, skor_terbaik = k["binding_id"], skor

            if terbaik is None or skor_terbaik < min_overlap:
                return None, skor_terbaik

            baris = self.conn.execute(
                "SELECT * FROM bindings WHERE id = ?", (terbaik,)).fetchone()
        return (_row_to_binding(baris) if baris else None), skor_terbaik

    def learn_features(self, parsed, nmid: str) -> None:
        """Catat ciri merchant ini ke sebaran yang dipelajari."""
        from . import profile as pf

        with self._lock:
            for f, v in pf.features_of(parsed).items():
                self.conn.execute(
                    "INSERT OR IGNORE INTO merchant_feature "
                    "(feature, value, nmid) VALUES (?, ?, ?)", (f, v, nmid))

    def feature_corpus(self) -> dict:
        """Sebaran ciri yang sudah diamati, siap dipakai profile.score()."""
        with self._lock:
            baris = self.conn.execute(
                "SELECT feature, value, COUNT(DISTINCT nmid) n "
                "FROM merchant_feature GROUP BY feature, value").fetchall()
            total = self.conn.execute(
                "SELECT COUNT(DISTINCT nmid) n FROM merchant_feature"
            ).fetchone()["n"]
        korpus = {"_total": total}
        for r in baris:
            korpus.setdefault(r["feature"], {})[r["value"]] = r["n"]
        return korpus

    def account_hash(self, account: str) -> str:
        """Hash nomor rekening. Nomornya sendiri tidak pernah disimpan."""
        bahan = f"{self._salt}|benef|{account.strip()}".encode("utf-8")
        return hashlib.sha256(bahan).hexdigest()

    def report_beneficiary(self, account: str, reporter: str,
                           now: Optional[datetime] = None) -> dict:
        """Laporkan rekening tujuan sebagai penerima penipuan.

        Idempoten per (rekening, pelapor): satu penyelenggara yang
        melapor seratus kali tetap satu suara — pola yang sama dengan
        invarian §5.
        """
        now = now or datetime.now(timezone.utc)
        h = self.account_hash(account)
        with self._lock:
            self.conn.execute(
                "INSERT INTO beneficiary_report "
                "(account_hash, reporter, reported_at) VALUES (?, ?, ?) "
                "ON CONFLICT (account_hash, reporter) DO UPDATE SET "
                "reported_at = excluded.reported_at",
                (h, reporter, _iso(now)))
            n = self.conn.execute(
                "SELECT COUNT(DISTINCT reporter) n FROM beneficiary_report "
                "WHERE account_hash = ?", (h,)).fetchone()["n"]
        return {"ok": True, "reporters": n}

    def beneficiary_history(self, account: str):
        """Riwayat laporan untuk rekening ini, atau None."""
        from . import transfer as tf

        h = self.account_hash(account)
        with self._lock:
            baris = self.conn.execute(
                "SELECT COUNT(*) total, COUNT(DISTINCT reporter) pelapor, "
                "MAX(reported_at) terakhir FROM beneficiary_report "
                "WHERE account_hash = ?", (h,)).fetchone()
        if not baris or not baris["total"]:
            return None
        return tf.BeneficiaryHistory(
            reports=baris["total"],
            distinct_reporters=baris["pelapor"],
            last_report_at=_parse(baris["terakhir"]))

    def dialect_profile(self, pan_prefix: str) -> dict:
        """Dialek dominan penerbit ini, per atribut.

        Mengembalikan {atribut: (nilai, setuju, total)}. Penyaringan
        apakah buktinya cukup dilakukan di behavior.py, bukan di sini —
        store hanya melaporkan apa adanya.
        """
        with self._lock:
            baris = self.conn.execute(
                "SELECT attribute, value, COUNT(DISTINCT nmid) n "
                "FROM issuer_dialect WHERE pan_prefix = ? "
                "GROUP BY attribute, value", (pan_prefix,)).fetchall()
        per_atribut = {}
        for r in baris:
            per_atribut.setdefault(r["attribute"], []).append((r["value"], r["n"]))
        keluar = {}
        for atribut, nilai in per_atribut.items():
            total = sum(n for _, n in nilai)
            v, n = max(nilai, key=lambda x: x[1])
            keluar[atribut] = (v, n, total)
        return keluar

    def area_city(self, lat: float, lng: float):
        """Kota dominan di wilayah ini, kalau buktinya cukup.

        Mengembalikan (kota, jumlah_nmid_setuju, jumlah_nmid_total) atau
        None kalau wilayahnya belum dikenal. Ketiadaan pengetahuan
        dikembalikan sebagai ketiadaan — bukan sebagai izin.
        """
        gh5 = geo.encode(lat, lng, bd.AREA_CITY_PRECISION)
        with self._lock:
            baris = self.conn.execute(
                "SELECT city, COUNT(DISTINCT nmid) n FROM area_city "
                "WHERE geohash_5 = ? GROUP BY city ORDER BY n DESC", (gh5,)
            ).fetchall()
        if not baris:
            return None
        total = sum(r["n"] for r in baris)
        return baris[0]["city"], baris[0]["n"], total

    def names_for_nmid(self, nmid: str) -> list:
        """Semua nama merchant yang pernah dipakai NMID ini."""
        with self._lock:
            baris = self.conn.execute(
                "SELECT DISTINCT merchant_name FROM bindings "
                "WHERE nmid = ? AND merchant_name IS NOT NULL", (nmid,)
            ).fetchall()
        return [r["merchant_name"] for r in baris]

    def note_challenge(self, lat: float, lng: float, nmid: str,
                       device_anon_id: str,
                       now: Optional[datetime] = None) -> None:
        """Catat satu pemindaian yang ditolak, per (jangkar, NMID penantang).

        Idempoten per perangkat: seratus pemindaian dari satu HP tetap
        terhitung satu. Yang diukur adalah berapa ORANG berbeda yang
        menemui stiker ini di sini, bukan berapa kali ia dipindai —
        penyerang bisa mengulang, tapi tidak bisa menggandakan dirinya
        jadi banyak pelanggan.
        """
        now = now or datetime.now(timezone.utc)
        gh7 = geo.encode(lat, lng, bd.INDEX_PRECISION)
        bahan = f"{self._salt}|tantangan|{gh7}|{nmid}|{device_anon_id}"
        ref = hashlib.sha256(bahan.encode("utf-8")).hexdigest()
        with self._lock:
            self.conn.execute(
                """INSERT OR IGNORE INTO anchor_challenge
                   (geohash_7, nmid, device_ref, attempted_at)
                   VALUES (?, ?, ?, ?)""",
                (gh7, nmid, ref, _iso(now)),
            )

    def challenge_state(self, lat: float, lng: float,
                        nmid: str) -> Optional[bd.Challenge]:
        """Berapa perangkat berbeda menemui NMID ini di jangkar ini, sejak kapan."""
        gh7 = geo.encode(lat, lng, bd.INDEX_PRECISION)
        row = self.conn.execute(
            """SELECT COUNT(*) AS n, MIN(attempted_at) AS awal,
                      MAX(attempted_at) AS akhir
               FROM anchor_challenge
               WHERE geohash_7 = ? AND nmid = ?""",
            (gh7, nmid),
        ).fetchone()
        if not row or not row["n"]:
            return None
        return bd.Challenge(
            devices=row["n"],
            first_at=_parse(row["awal"]),
            last_at=_parse(row["akhir"]),
        )

    def note_anomaly(self, binding_id: int,
                     now: Optional[datetime] = None) -> None:
        """Catat bahwa jangkar ini menjadi sasaran pemindaian yang ditolak.

        Ini BUKAN observation dan tidak menyentuh observer_count: binding
        palsu tetap tidak bisa membangun reputasi lewat percobaan
        berulang (invarian §3). Counter ini hanya pernah menaikkan risiko,
        tidak pernah menurunkannya, dan diabaikan saat yang memindai
        adalah pemilik sah jangkar — lihat behavior._behavioral_signals().
        """
        now = now or datetime.now(timezone.utc)
        with self._lock:
            self.conn.execute(
                """UPDATE bindings
                   SET anomaly_attempts = anomaly_attempts + 1,
                       last_anomaly_at  = ?
                   WHERE id = ?""",
                (_iso(now), binding_id),
            )

    def _haluskan_jangkar(self, binding_id: int, lat: float,
                          lng: float) -> None:
        """Tarik jangkar ke rata-rata berjalan pengamatan yang masuk radius.

        Dipanggil di dalam transaksi record(), dan hanya ketika seorang
        pengamat BARU tercatat.
        """
        b = self.conn.execute(
            "SELECT lat, lng, origin_lat, origin_lng, observer_count, "
            "registered_at FROM bindings WHERE id = ?", (binding_id,)
        ).fetchone()

        # Jangkar TERDAFTAR tidak dihaluskan: koordinatnya pernyataan
        # penyelenggara, bukan taksiran dari pengamatan. Membiarkan
        # pemindai menggesernya berarti membiarkan mereka memindahkan
        # merchant yang sudah dinyatakan resmi berada di suatu titik.
        if b["registered_at"]:
            return

        asal_lat = b["origin_lat"] if b["origin_lat"] is not None else b["lat"]
        asal_lng = b["origin_lng"] if b["origin_lng"] is not None else b["lng"]

        # Di luar radius jangkar tidak ikut menggeser sama sekali.
        if geo.haversine_m(b["lat"], b["lng"], lat, lng) > bd.ANCHOR_RADIUS_M:
            self.conn.execute(
                "UPDATE bindings SET origin_lat = ?, origin_lng = ? WHERE id = ?",
                (asal_lat, asal_lng, binding_id))
            return

        n = max(1, b["observer_count"])
        baru_lat = b["lat"] + (lat - b["lat"]) / n
        baru_lng = b["lng"] + (lng - b["lng"]) / n

        if geo.haversine_m(asal_lat, asal_lng, baru_lat, baru_lng) > \
                bd.ANCHOR_MAX_DRIFT_M:
            # Sudah menyentuh batas geser. Jangkar ditahan di tempat.
            self.conn.execute(
                "UPDATE bindings SET origin_lat = ?, origin_lng = ? WHERE id = ?",
                (asal_lat, asal_lng, binding_id))
            return

        gh7 = geo.encode(baru_lat, baru_lng, bd.INDEX_PRECISION)
        gh6 = geo.encode(baru_lat, baru_lng, bd.AREA_PRECISION)
        self.conn.execute(
            """UPDATE bindings
               SET lat = ?, lng = ?, geohash_7 = ?, geohash_6 = ?,
                   origin_lat = ?, origin_lng = ?
               WHERE id = ?""",
            (baru_lat, baru_lng, gh7, gh6, asal_lat, asal_lng, binding_id))

    def seed_binding(
        self,
        nmid: str,
        lat: float,
        lng: float,
        merchant_name: str,
        observer_count: int,
        first_seen: datetime,
        last_seen: datetime,
    ) -> None:
        """Sisipkan binding dengan riwayat siap pakai, untuk demo."""
        gh7 = geo.encode(lat, lng, bd.INDEX_PRECISION)
        gh6 = geo.encode(lat, lng, bd.AREA_PRECISION)
        with self._lock:
            self.conn.execute(
                """INSERT OR REPLACE INTO bindings
                   (nmid, lat, lng, geohash_7, geohash_6, merchant_name,
                    observer_count, first_seen, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (nmid, lat, lng, gh7, gh6, merchant_name, observer_count,
                 _iso(first_seen), _iso(last_seen)),
            )
