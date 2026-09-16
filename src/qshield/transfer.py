"""
Layer 2 — jalur transfer bank manual.

Jalur QRIS punya artefak yang bisa diperiksa: stiker, payload, jangkar
lokasi. Transfer manual tidak punya satu pun. Korban mengetik nomor
rekening yang didiktekan seseorang di telepon, dan tidak ada benda
fisik yang bisa diverifikasi.

Yang bisa dinilai adalah BENTUK transaksinya dan apa yang diketahui
penyelenggara tentang rekening tujuan. Itu sebabnya modul ini menerima
telemetri dari PJP alih-alih mengumpulkannya sendiri: PJP tahu umur
rekening, riwayat penerima, dan laju transaksi. Kami tidak, dan memang
tidak seharusnya.

Pola yang dikenali adalah pola rekayasa sosial, bukan pola satu orang:
korban dituntun lewat telepon, diburu-buru, mengirim ke rekening yang
belum pernah ditujunya, yang baru dibuka beberapa hari lalu.

Privasi. Modul ini menilai REKENING TUJUAN — pihak yang menerima uang,
yang dalam skenario penipuan adalah pelakunya. Identitas PEMBAYAR tidak
pernah masuk ke mana pun, sama seperti invarian §8 pada jalur QRIS.
Nomor rekening tujuan disimpan sebagai hash, bukan apa adanya.

Seperti binding.py dan behavior.py, modul ini tidak mengimpor store.py:
seluruh aturannya bisa diuji tanpa I/O.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .binding import COOLING_OFF, PROCEED, STEP_UP, WARN, _action_for

# --- Parameter yang bisa dikalibrasi -------------------------------
#
# Angka di bawah dikalibrasi di scripts/calibrate_transfer.py.

# Rekening tujuan yang belum pernah dikirimi. Sendirian ini sangat
# lemah — orang mengirim ke rekening baru setiap hari. Yang membuatnya
# berarti adalah kombinasinya dengan sinyal lain.
W_FIRST_TIME_BENEFICIARY = 15

# Rekening penampung ("mule") biasanya baru dibuka. Ambangnya rendah
# dengan sengaja: rekening berumur sebulan sudah cukup wajar.
BENEFICIARY_YOUNG_DAYS = 30
W_BENEFICIARY_YOUNG = 25

# Korban sedang menelepon saat mengirim. Ini pola paling khas rekayasa
# sosial — pelaku harus menuntun korban langkah demi langkah — dan
# paling sulit dipalsukan penyerang, karena ia justru yang menelepon.
W_CALL_ACTIVE = 35

# Lonjakan transaksi. Korban yang dituntun sering mengirim beberapa kali
# berturut-turut karena pelaku menaikkan jumlahnya bertahap.
VELOCITY_WINDOW_MIN = 60
VELOCITY_THRESHOLD = 3
W_VELOCITY_SPIKE = 20

# Rekening yang sudah pernah dilaporkan penyelenggara lain. Inilah
# lapisan bersamanya: rekening penampung tidak berhenti di batas satu
# PJP, persis seperti stiker penipu tidak berhenti di batas satu PJP.
W_BENEFICIARY_REPORTED_BASE = 40
W_BENEFICIARY_REPORTED_CAP = 70


@dataclass
class TransferTelemetry:
    """Apa yang diketahui PJP tentang transaksi ini.

    Seluruhnya opsional. Klien yang tidak bisa mengisinya tidak dihukum
    — ketiadaannya diungkapkan, bukan diberi skor. Pola yang sama
    dengan device_integrity pada jalur QRIS, dan alasan yang sama:
    menghukum sesuatu yang klien memang tidak bisa berikan berarti
    menghukum penggunanya untuk hal yang bukan kesalahan mereka.
    """

    first_time_beneficiary: Optional[bool] = None
    beneficiary_account_age_days: Optional[int] = None
    call_active: Optional[bool] = None
    transfers_last_hour: Optional[int] = None

    @property
    def provided(self) -> bool:
        return any(v is not None for v in (
            self.first_time_beneficiary, self.beneficiary_account_age_days,
            self.call_active, self.transfers_last_hour))


@dataclass
class BeneficiaryHistory:
    """Apa yang lapisan bersama ketahui tentang rekening tujuan ini."""

    reports: int = 0
    last_report_at: Optional[datetime] = None
    distinct_reporters: int = 0


@dataclass
class TransferSignal:
    name: str
    weight: int
    reason: str


@dataclass
class TransferVerdict:
    action: str
    risk_score: int
    reasons: list = field(default_factory=list)
    signals: list = field(default_factory=list)
    telemetry_status: str = "not_provided"

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "risk_score": self.risk_score,
            "reasons": self.reasons,
            "signals": self.signals,
            "telemetry": self.telemetry_status,
        }


def _telemetry_signals(t: TransferTelemetry) -> list:
    out = []

    if t.call_active is True:
        out.append(TransferSignal(
            name="call_active_during_transfer",
            weight=W_CALL_ACTIVE,
            reason=(
                "Anda sedang dalam panggilan telepon saat melakukan "
                "transfer ini. Penipuan pembayaran hampir selalu dipandu "
                "lewat telepon — petugas bank yang asli tidak pernah "
                "meminta Anda mentransfer sambil ditelepon"
            ),
        ))

    if t.beneficiary_account_age_days is not None and \
            t.beneficiary_account_age_days < BENEFICIARY_YOUNG_DAYS:
        out.append(TransferSignal(
            name="beneficiary_account_young",
            weight=W_BENEFICIARY_YOUNG,
            reason=(
                f"Rekening tujuan baru dibuka "
                f"{t.beneficiary_account_age_days} hari lalu — rekening "
                f"penampung biasanya berumur pendek"
            ),
        ))

    if t.first_time_beneficiary is True:
        out.append(TransferSignal(
            name="first_time_beneficiary",
            weight=W_FIRST_TIME_BENEFICIARY,
            reason="Anda belum pernah mengirim ke rekening ini sebelumnya",
        ))

    if t.transfers_last_hour is not None and \
            t.transfers_last_hour >= VELOCITY_THRESHOLD:
        out.append(TransferSignal(
            name="transfer_velocity_spike",
            weight=W_VELOCITY_SPIKE,
            reason=(
                f"{t.transfers_last_hour} transfer dalam "
                f"{VELOCITY_WINDOW_MIN} menit terakhir — pelaku sering "
                f"menaikkan jumlahnya bertahap"
            ),
        ))

    return out


def _history_signals(h: Optional[BeneficiaryHistory]) -> list:
    if h is None or h.reports <= 0:
        return []

    # Berskala dengan jumlah PENYELENGGARA yang melaporkan, bukan jumlah
    # laporan — pola yang sama dengan invarian §5. Satu penyelenggara
    # yang melapor seratus kali bukan bukti yang lebih kuat daripada
    # lima penyelenggara yang masing-masing melapor sekali.
    pelapor = max(1, h.distinct_reporters)
    bobot = min(W_BENEFICIARY_REPORTED_CAP,
                W_BENEFICIARY_REPORTED_BASE + 10 * (pelapor - 1))
    return [TransferSignal(
        name="beneficiary_reported",
        weight=bobot,
        reason=(
            f"Rekening tujuan ini sudah dilaporkan sebagai penerima "
            f"penipuan oleh {pelapor} penyelenggara pembayaran"
        ),
    )]


def evaluate(
    telemetry: Optional[TransferTelemetry] = None,
    history: Optional[BeneficiaryHistory] = None,
    now: Optional[datetime] = None,
) -> TransferVerdict:
    """Nilai satu rencana transfer manual.

    Tidak ada artefak yang diperiksa di sini — tidak ada payload, tidak
    ada jangkar lokasi. Yang dinilai adalah bentuk transaksinya dan
    reputasi rekening tujuannya.
    """
    now = now or datetime.now(timezone.utc)
    t = telemetry or TransferTelemetry()

    signals = _telemetry_signals(t) + _history_signals(history)
    score = min(100, sum(s.weight for s in signals))

    reasons = [s.reason for s in signals]
    if not reasons:
        reasons.append(
            "Tidak ada tanda yang mencurigakan pada transfer ini"
            if t.provided else
            "Belum ada informasi yang cukup untuk menilai transfer ini"
        )

    # Ketiadaan telemetri diungkapkan, bukan diberi skor — sama seperti
    # device_integrity. Tapi ia juga tidak boleh menghasilkan "aman":
    # tanpa telemetri kami memang tidak menilai apa pun.
    if t.provided:
        status = "provided"
        action = _action_for(score)
    else:
        status = "not_provided"
        action = max(WARN, _action_for(score), key=lambda a: [
            PROCEED, WARN, STEP_UP, COOLING_OFF].index(a))

    return TransferVerdict(
        action=action,
        risk_score=score,
        reasons=reasons,
        signals=[s.name for s in signals],
        telemetry_status=status,
    )
