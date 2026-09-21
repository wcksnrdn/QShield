"""
Parser payload QRIS (EMVCo Merchant Presented Mode).

Payload QRIS adalah rangkaian TLV: setiap field terdiri dari
tag 2 digit, panjang 2 digit, lalu value sepanjang itu.
Beberapa field adalah template yang isinya TLV lagi (nested).

Referensi tag yang dipakai:
  00  Payload format indicator
  01  Point of initiation: "11" statis, "12" dinamis
  26-51 Merchant account information (template, nested)
  52  Merchant category code
  53  Currency (360 = IDR)
  54  Transaction amount (hanya pada QR dinamis)
  58  Country code
  59  Merchant name
  60  Merchant city
  61  Postal code
  62  Additional data (template)
  63  CRC16
"""

from dataclasses import dataclass, field
from typing import Optional

QRIS_GUIDS = ("ID.CO.QRIS.WWW", "ID.CO.QRIS")

MERCHANT_TEMPLATE_TAGS = [f"{i:02d}" for i in range(26, 52)]

NESTED_TAGS = set(MERCHANT_TEMPLATE_TAGS) | {"62", "64"}

MERCHANT_CRITERIA = {
    "UMI": "Usaha Mikro",
    "UKE": "Usaha Kecil",
    "UME": "Usaha Menengah",
    "UBE": "Usaha Besar",
    "URE": "Usaha Regular",
}

# Tag 55 — "Tip or Convenience Indicator" EMVCo MPM. Nilainya menentukan
# tag mana yang membawa besarannya: "02" -> tag 56 (nominal tetap),
# "03" -> tag 57 (persentase). "01" tidak membawa besaran sama sekali;
# pembayar yang mengisinya.
#
# DIPARSE DAN DIUNGKAPKAN, TIDAK DISKOR. Kami belum memverifikasi
# apakah biaya layanan pada QR STATIS itu kontradiksi terhadap spec
# QRIS atau justru sah — dan menghukum sesuatu yang ternyata sah
# berbobot W_STRUCTURAL berarti memaksa `anomaly` pada payload yang
# benar. Pola yang sama dengan `postal_code` dan dengan kehati-hatian
# pada tag 58 di Keputusan 35: ungkapkan dulu, skor belakangan kalau
# ada dasarnya.
TIP_INDICATOR = {
    "01": "Pembayar diminta memasukkan tip",
    "02": "Biaya layanan nominal tetap",
    "03": "Biaya layanan persentase",
}


# --- Keterangan tag, untuk bedah TLV -------------------------------
#
# Dipakai HANYA untuk menjelaskan payload ke manusia; tidak satu pun
# dibaca oleh penilaian. Tag yang tidak ada di sini tetap ditampilkan
# apa adanya — penerbit yang memakai tag di luar daftar justru yang
# menarik untuk dilihat, jadi ia tidak boleh disembunyikan.
TAG_LABELS = {
    "00": "Indikator format payload",
    "01": "Metode inisiasi (11 statis, 12 dinamis)",
    "52": "Kategori merchant (MCC)",
    "53": "Mata uang transaksi",
    "54": "Nominal transaksi",
    "55": "Indikator tip / biaya layanan",
    "56": "Biaya layanan nominal tetap",
    "57": "Biaya layanan persentase",
    "58": "Kode negara",
    "59": "Nama merchant",
    "60": "Kota merchant",
    "61": "Kode pos",
    "62": "Data tambahan",
    "63": "Checksum CRC16",
    "64": "Template bahasa merchant",
}

# Sub-tag berbeda artinya tergantung induknya, jadi petanya dipisah
# per konteks — bukan satu peta datar yang akan salah label.
SUBTAG_LABELS = {
    "akun": {
        "00": "Pengenal global penyelenggara (GUID)",
        "01": "PAN / nomor akun merchant",
        "02": "Merchant ID nasional (NMID)",
        "03": "Kriteria usaha merchant",
    },
    "62": {
        "01": "Nomor tagihan",
        "02": "Nomor ponsel",
        "03": "Label toko",
        "04": "Nomor loyalitas",
        "05": "Label referensi",
        "06": "Label pelanggan",
        "07": "Label terminal",
        "08": "Tujuan transaksi",
        "09": "Permintaan data konsumen tambahan",
    },
    "64": {
        "00": "Preferensi bahasa",
        "01": "Nama merchant (alternatif)",
        "02": "Kota merchant (alternatif)",
    },
}


def tag_label(tag: str) -> str:
    """Keterangan tag tingkat atas."""
    if tag in TAG_LABELS:
        return TAG_LABELS[tag]
    if tag in MERCHANT_TEMPLATE_TAGS:
        return f"Informasi akun merchant (template {tag})"
    return "Tag di luar daftar standar"


class ParseError(Exception):
    """Payload tidak sesuai struktur TLV EMVCo."""


@dataclass
class MerchantAccount:
    """Satu template merchant account (tag 26-51).

    Struktur sub-tag pada QRIS:
      00  GUID, mis. ID.CO.QRIS.WWW
      01  Merchant PAN (nomor kartu virtual, diawali kode PJP)
      02  NMID / National Merchant ID, diawali "ID"
      03  Kriteria usaha (UMI/UKE/UME/UBE)
    """

    tag: str
    guid: Optional[str] = None
    pan: Optional[str] = None
    nmid: Optional[str] = None
    criteria: Optional[str] = None
    raw: dict = field(default_factory=dict)

    @property
    def is_qris(self) -> bool:
        return bool(self.guid and self.guid.upper().startswith("ID.CO.QRIS"))

    @property
    def issuer_code(self) -> Optional[str]:
        """4 digit awal PAN menandakan PJP penerbit."""
        if self.pan and len(self.pan) >= 8:
            return self.pan[4:8]
        return None


@dataclass
class QrisPayload:
    raw: str
    tags: dict
    accounts: list
    crc_valid: bool
    crc_found: Optional[str] = None
    crc_expected: Optional[str] = None

    @property
    def is_static(self) -> bool:
        return self.tags.get("01", "11") == "11"

    @property
    def merchant_name(self) -> Optional[str]:
        return self.tags.get("59")

    @property
    def merchant_city(self) -> Optional[str]:
        return self.tags.get("60")

    @property
    def postal_code(self) -> Optional[str]:
        return self.tags.get("61")

    @property
    def mcc(self) -> Optional[str]:
        return self.tags.get("52")

    @property
    def currency(self) -> Optional[str]:
        return self.tags.get("53")

    @property
    def amount(self) -> Optional[str]:
        return self.tags.get("54")

    @property
    def country(self) -> Optional[str]:
        return self.tags.get("58")

    @property
    def tip_indicator(self) -> Optional[str]:
        """Tag 55 mentah. Lihat TIP_INDICATOR untuk artinya."""
        return self.tags.get("55")

    @property
    def tip_label(self) -> Optional[str]:
        kode = self.tip_indicator
        if kode is None:
            return None
        # Kode tak dikenal dikembalikan apa adanya, bukan dibuang:
        # penerbit yang memakai nilai di luar spec justru yang menarik
        # untuk dilihat auditor.
        return TIP_INDICATOR.get(kode, kode)

    @property
    def fee_fixed(self) -> Optional[str]:
        """Tag 56 — besaran biaya layanan tetap."""
        return self.tags.get("56")

    @property
    def fee_percent(self) -> Optional[str]:
        """Tag 57 — besaran biaya layanan dalam persen."""
        return self.tags.get("57")

    @property
    def has_fee(self) -> bool:
        """Payload meminta biaya di luar nominal transaksi."""
        return any(t in self.tags for t in ("55", "56", "57"))

    @property
    def primary_account(self) -> Optional[MerchantAccount]:
        for acc in self.accounts:
            if acc.is_qris and acc.nmid:
                return acc
        for acc in self.accounts:
            if acc.nmid:
                return acc
        return self.accounts[0] if self.accounts else None

    @property
    def nmid(self) -> Optional[str]:
        acc = self.primary_account
        return acc.nmid if acc else None

    @property
    def criteria_label(self) -> Optional[str]:
        acc = self.primary_account
        if acc and acc.criteria:
            return MERCHANT_CRITERIA.get(acc.criteria, acc.criteria)
        return None

    def breakdown(self) -> list:
        """Bedah TLV untuk dibaca manusia, termasuk tag bersarang.

        FORENSIK, BUKAN PENILAIAN. Tidak ada yang membaca hasil ini
        selain tampilan — ia menjawab "apa yang sistem baca sehingga
        memutuskan begini", bukan menghasilkan putusan apa pun.

        Urutannya urutan kemunculan di payload, bukan urut tag:
        `parse_tlv` menyisipkan sesuai kemunculan dan dict Python
        mempertahankannya. Urutan asli itu justru yang menarik secara
        forensik — sinyal `noncanonical_tag_order` membacanya juga.
        """
        keluar = []
        for tag, nilai in self.tags.items():
            entri = {
                "tag": tag,
                "length": len(nilai),
                "value": nilai,
                "label": tag_label(tag),
                "children": [],
            }
            if tag in NESTED_TAGS:
                konteks = "akun" if tag in MERCHANT_TEMPLATE_TAGS else tag
                peta = SUBTAG_LABELS.get(konteks, {})
                try:
                    sub = parse_tlv(nilai)
                except ParseError:
                    # Bersarang tapi tidak bisa dipecah: tampilkan apa
                    # adanya sebagai daun. Menyembunyikannya justru
                    # membuang bukti bahwa isinya cacat.
                    sub = {}
                for st, sv in sub.items():
                    entri["children"].append({
                        "tag": st,
                        "length": len(sv),
                        "value": sv,
                        "label": peta.get(st, "Sub-tag di luar daftar standar"),
                        "children": [],
                    })
            keluar.append(entri)
        return keluar

    def summary(self) -> dict:
        return {
            "nmid": self.nmid,
            "merchant_name": self.merchant_name,
            "merchant_city": self.merchant_city,
            "postal_code": self.postal_code,
            "mcc": self.mcc,
            "criteria": self.criteria_label,
            "is_static": self.is_static,
            "amount": self.amount,
            "currency": self.currency,
            "country": self.country,
            "tip_indicator": self.tip_indicator,
            "fee_fixed": self.fee_fixed,
            "fee_percent": self.fee_percent,
            "crc_valid": self.crc_valid,
        }


def crc16_ccitt(data: str) -> str:
    """CRC16/CCITT-FALSE: poly 0x1021, init 0xFFFF, tanpa refleksi."""
    crc = 0xFFFF
    for ch in data.encode("utf-8"):
        crc ^= ch << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def parse_tlv(data: str) -> dict:
    """Pecah string TLV jadi dict {tag: value}. Tidak rekursif."""
    result = {}
    i = 0
    n = len(data)
    while i < n:
        if i + 4 > n:
            raise ParseError(f"TLV terpotong pada posisi {i}")
        tag = data[i:i + 2]
        length_str = data[i + 2:i + 4]
        if not tag.isdigit() or not length_str.isdigit():
            raise ParseError(f"Tag/length bukan angka pada posisi {i}")
        length = int(length_str)
        start = i + 4
        end = start + length
        if end > n:
            raise ParseError(
                f"Value tag {tag} melebihi panjang payload "
                f"(butuh {length}, tersisa {n - start})"
            )
        result[tag] = data[start:end]
        i = end
    return result


def _parse_merchant_account(tag: str, value: str) -> MerchantAccount:
    try:
        sub = parse_tlv(value)
    except ParseError:
        return MerchantAccount(tag=tag, raw={"00": value})
    return MerchantAccount(
        tag=tag,
        guid=sub.get("00"),
        pan=sub.get("01"),
        nmid=sub.get("02"),
        criteria=sub.get("03"),
        raw=sub,
    )


def parse(payload: str) -> QrisPayload:
    """Parse payload QRIS lengkap beserta validasi CRC16."""
    payload = payload.strip()
    if not payload:
        raise ParseError("Payload kosong")

    tags = parse_tlv(payload)

    if "00" not in tags:
        raise ParseError("Tag 00 (payload format indicator) tidak ditemukan")

    crc_found = tags.get("63")
    crc_valid = False
    crc_expected = None
    idx = payload.rfind("6304")
    if crc_found and idx != -1:
        crc_expected = crc16_ccitt(payload[:idx + 4])
        crc_valid = crc_found.upper() == crc_expected

    accounts = [
        _parse_merchant_account(t, tags[t])
        for t in MERCHANT_TEMPLATE_TAGS
        if t in tags
    ]

    return QrisPayload(
        raw=payload,
        tags=tags,
        accounts=accounts,
        crc_valid=crc_valid,
        crc_found=crc_found,
        crc_expected=crc_expected,
    )


def build(fields: dict) -> str:
    """Susun payload QRIS dari dict {tag: value}, CRC dihitung otomatis.

    Dipakai untuk membuat data uji dan QR skenario demo.
    """
    parts = []
    for tag in sorted(fields.keys()):
        if tag == "63":
            continue
        value = fields[tag]
        parts.append(f"{tag}{len(value):02d}{value}")
    body = "".join(parts) + "6304"
    return body + crc16_ccitt(body)


def build_tlv(fields: dict) -> str:
    """Susun sub-TLV (untuk isi template merchant account)."""
    return "".join(f"{t}{len(v):02d}{v}" for t, v in sorted(fields.items()))
