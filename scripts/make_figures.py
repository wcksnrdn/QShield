"""
Gambar untuk laporan: arsitektur PoC dan gerbang friksi.

SVG, bukan PNG: laporan dicetak lewat Chrome, jadi vektor tetap tajam
pada perbesaran berapa pun dan berkasnya beberapa kilobyte.

Dibangkitkan, bukan digambar tangan, karena isinya harus ikut berubah
kalau ambangnya berubah. Angka di bawah diambil dari satu tempat —
lihat `ANGKA` — dan berkas ini memeriksanya terhadap kode sungguhan
sebelum menggambar. Kalau ada yang tidak cocok, ia berhenti.

    PYTHONPATH=src python scripts/make_figures.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from qshield import behavior as bh
from qshield import binding as bd

KELUARAN = Path(__file__).resolve().parent.parent / "docs" / "report"

TINTA, REDUP, GARIS = "#16181d", "#5b6270", "#c9d0da"
AKSEN, LATAR = "#1d4ed8", "#f4f6f8"
HIJAU, KUNING, JINGGA, MERAH = "#15803d", "#b45309", "#c2410c", "#b91c1c"
FONT = "Helvetica Neue, Helvetica, Arial, sans-serif"
MONO = "SF Mono, Menlo, Consolas, monospace"


def periksa():
    """Angka di gambar harus sama dengan angka di kode."""
    harus = [
        ("radius jangkar", bd.ANCHOR_RADIUS_M, 50),
        ("pengamat minimum", bd.MIN_OBSERVERS, 3),
        ("rentang minimum", bd.MIN_AGE_HOURS, 24),
        ("ambang tier", bd.THRESHOLDS, [(25, "proceed"), (50, "warn"),
                                        (75, "step_up")]),
        ("bobot struktural", bh.W_STRUCTURAL, 70),
    ]
    for nama, ada, diharapkan in harus:
        if ada != diharapkan:
            sys.exit(f"GAMBAR BASI: {nama} = {ada}, gambar menulis "
                     f"{diharapkan}. Perbarui make_figures.py.")


# --- Primitif ------------------------------------------------------

def esc(t):
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def teks(x, y, t, ukuran=9, warna=None, tebal=False, tengah=False,
         mono=False, miring=False):
    return (f'<text x="{x}" y="{y}" font-family="{MONO if mono else FONT}" '
            f'font-size="{ukuran}" fill="{warna or TINTA}"'
            + (' font-weight="600"' if tebal else "")
            + (' font-style="italic"' if miring else "")
            + (' text-anchor="middle"' if tengah else "")
            + f'>{esc(t)}</text>')


def kotak(x, y, w, h, isi="#fff", tepi=None, r=4, tebal=1, putus=False):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" '
            f'fill="{isi}" stroke="{tepi or GARIS}" stroke-width="{tebal}"'
            + (' stroke-dasharray="4 3"' if putus else "") + '/>')


def panah(x1, y1, x2, y2, warna=None, putus=False, lebar=1.4):
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{warna or REDUP}" stroke-width="{lebar}" '
            f'marker-end="url(#ujung)"'
            + (' stroke-dasharray="4 3"' if putus else "") + '/>')


def siku(titik, warna=None, putus=False):
    """Jalur bersiku dengan SATU kepala panah di ujung.

    Dua garis terpisah menghasilkan dua kepala panah di tengah jalur,
    dan itu terbaca seperti dua aliran yang berbeda.
    """
    d = " ".join(("M" if i == 0 else "L") + f"{x},{y}"
                 for i, (x, y) in enumerate(titik))
    return (f'<path d="{d}" fill="none" stroke="{warna or REDUP}" '
            f'stroke-width="1.4" marker-end="url(#ujung)"'
            + (' stroke-dasharray="4 3"' if putus else "") + '/>')


def bungkus(w, h, isi, judul):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'width="100%" role="img" aria-label="{esc(judul)}">'
            f'<defs><marker id="ujung" viewBox="0 0 10 10" refX="9" refY="5" '
            f'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
            f'<path d="M0,1 L9,5 L0,9 z" fill="{REDUP}"/></marker></defs>'
            f'<rect width="{w}" height="{h}" fill="#fff"/>'
            + "".join(isi) + '</svg>')


# --- Gambar 1: arsitektur -------------------------------------------

def arsitektur():
    W, H = 900, 545
    d = []

    def tajuk(x, y, t):
        d.append(teks(x, y, t, 8, AKSEN, tebal=True))

    # Baris 1 — klien, PJP, batas API
    d.append(kotak(20, 26, 240, 62, LATAR))
    tajuk(32, 42, "CLIENT")
    d.append(teks(32, 58, "Native SDK  ·  on-device TLV pre-parse,", 8.5))
    d.append(teks(32, 70, "non-EMVCo rejected locally, attestation", 8.5))
    d.append(teks(32, 82, "Web scanner  ·  verify / catalogue mode", 8.5))

    d.append(kotak(300, 26, 190, 62, LATAR))
    tajuk(312, 42, "PJP BACKEND")
    d.append(teks(312, 58, "attaches API key", 8.5))
    d.append(teks(312, 70, "owns the payment path", 8.5, REDUP))
    d.append(teks(312, 82, "enforces the verdict", 8.5, REDUP))

    d.append(kotak(530, 26, 350, 62))
    tajuk(542, 42, "Q-SHIELD API BOUNDARY")
    d.append(teks(542, 58, "API key auth  ·  per-client rate limit", 8.5))
    d.append(teks(542, 70, "body-size cap  ·  security headers", 8.5))
    d.append(teks(542, 82, "audit trail, no PII", 8.5))
    d.append(panah(262, 57, 298, 57))
    d.append(panah(492, 57, 528, 57))

    # Baris 2 — empat gerbang
    d.append(kotak(20, 110, 860, 66, "#fff", GARIS, 4, 1, True))
    tajuk(32, 126, "FOUR PRE-SCORING GATES   —   three of them stop Layer 1 from running at all")
    lebar, jarak = 206, 212
    gerbang = [("1  unparseable / no NMID", "422 — stop.", "nothing learned", MERAH),
               ("2  mock_location: true", "Layer 1 skipped", "location risk 65", JINGGA),
               ("3  from_image: true", "Layer 1 skipped", "location risk 0", KUNING),
               ("4  accuracy > 100 m", "Layer 1 skipped", "location risk 40", KUNING)]
    for i, (atas, tengah_, bawah, warna) in enumerate(gerbang):
        x = 26 + i * jarak
        d.append(kotak(x, 132, lebar, 38, "#fff", warna, 3, 1.2))
        d.append(teks(x + 8, 145, atas, 8.5, warna, tebal=True))
        d.append(teks(x + 8, 157, tengah_, 8, TINTA))
        d.append(teks(x + 8, 166, bawah, 7.5, REDUP))
    d.append(teks(450, 100, "scan payload  +  lat / lng  +  accuracy  +  anonymous device id",
                  8.5, REDUP, tengah=True))
    d.append(panah(450, 88, 450, 106))

    # Baris 3 — dua lapisan
    d.append(kotak(20, 196, 424, 150, "#fbfcfe", AKSEN, 4, 1.3))
    tajuk(34, 214, "LAYER 1 — MERCHANT-LOCATION BINDING")
    d.append(teks(34, 229, "Is this NMID established at these coordinates?", 8.5, TINTA))
    for i, t in enumerate([
            f"anchor = same NMID within {bd.ANCHOR_RADIUS_M} m, by distance",
            f"established at {bd.MIN_OBSERVERS} distinct devices over {bd.MIN_AGE_HOURS} h",
            "bounded running average — 6.9 m → 1.4 m at 47 obs",
            "",
            "four exemptions, each empirically calibrated:",
            "adjacent  ·  relocated  ·  roving  ·  alternating"]):
        if t:
            d.append(teks(34, 247 + i * 14, t, 8,
                          AKSEN if t.startswith(("four", "adjacent")) else TINTA))
    d.append(teks(34, 336, "skipped entirely by gates 2–4", 7.5, REDUP, miring=True))

    d.append(kotak(456, 196, 424, 150, "#fbfcfe", AKSEN, 4, 1.3))
    tajuk(470, 214, "LAYER 2 — ARTIFACT & BEHAVIOURAL SCORING")
    d.append(teks(470, 229, "Does this payload behave like a legitimate artefact?", 8.5))
    kiri = ["structural contradictions", "dynamic-QR trail", "printed label vs code",
            "ambient WiFi fingerprint"]
    kanan = ["device integrity", "provenance / area city", "merchant-profile rarity",
             "issuer dialect"]
    for i, (a, b) in enumerate(zip(kiri, kanan)):
        d.append(teks(470, 247 + i * 14, "· " + a, 8))
        d.append(teks(680, 247 + i * 14, "· " + b, 8))
    d.append(teks(470, 322, "two unsupervised models, zero fraud labels", 8, AKSEN))
    d.append(teks(470, 336, "runs in full even when Layer 1 is skipped", 7.5, REDUP,
                  miring=True))
    d.append(panah(232, 176, 232, 192))
    d.append(panah(668, 176, 668, 192))

    # Baris 4 — komposisi
    d.append(kotak(250, 366, 400, 42, LATAR, TINTA, 4, 1.2))
    d.append(teks(450, 382, "COMPOSE", 9, TINTA, tebal=True, tengah=True))
    d.append(teks(450, 399,
                  "scores add, clamp 0–100  ·  Layer 2 may only lower trust  ·  "
                  "reasons re-sorted by weight", 8, REDUP, tengah=True))
    d.append(siku([(232, 346), (232, 356), (350, 356), (350, 364)]))
    d.append(siku([(668, 346), (668, 356), (550, 356), (550, 364)]))

    # Baris 5 — tanggapan dan penyelesaian
    d.append(kotak(20, 432, 424, 92, "#fff"))
    tajuk(34, 450, "RESPONSE")
    d.append(teks(34, 466, "verdict  ·  action  ·  risk_score  ·  layer breakdown", 8.5))
    d.append(teks(34, 480, "human-readable reasons  ·  evidence provenance", 8.5))
    d.append(teks(34, 497, "HMAC-SHA256 ticket, 90 s", 8.5, AKSEN, tebal=True))
    d.append(teks(34, 510, "binds the verdict to this exact payload digest", 7.5, REDUP))

    d.append(kotak(456, 432, 424, 92, "#fff"))
    tajuk(470, 450, "PERSISTENCE  —  SQLite WAL, zero-PII")
    d.append(teks(470, 466, "bindings · observations · challenge ledger · anchors", 8.5))
    d.append(teks(470, 480, "issuer dialects · feature corpus · AP fingerprints", 8.5))
    d.append(teks(470, 497, "device_ref = sha256(salt ‖ binding_id ‖ device id)", 8, mono=True))
    d.append(teks(470, 510, "scoped per anchor — cannot be chained across places",
                  7.5, REDUP))
    d.append(panah(232, 408, 232, 428))

    # Umpan balik pembelajaran. Jalurnya turun di x=862, bukan di tepi
    # 880, supaya kepala panahnya tidak menempel pada bingkai.
    d.append(siku([(650, 397), (862, 397), (862, 428)], AKSEN, putus=True))
    d.append(f'<text x="856" y="388" font-family="{FONT}" font-size="7.5" '
             f'fill="{AKSEN}" text-anchor="end">learn — only when the verdict '
             f'is not anomaly</text>')
    d.append(f'<text x="856" y="377" font-family="{FONT}" font-size="7.5" '
             f'fill="{REDUP}" text-anchor="end">payload knowledge only for image and replay</text>')
    return bungkus(W, H, d, "Q-Shield proof-of-concept architecture")


# --- Gambar 2: gerbang friksi ----------------------------------------

def friksi():
    W, H = 900, 452
    d = []

    d.append(teks(20, 24, "FRICTION GATES — FROM SCORE TO WHAT THE APP DOES",
                  9.5, AKSEN, tebal=True))
    d.append(teks(20, 40, "One 0–100 score, four tiers, and one rule that cannot "
                  "be bypassed: a verdict of \u201cunknown\u201d never maps to "
                  "proceed.", 8.5, TINTA))

    # --- Pita skor ---
    x0, total_lebar, y = 20, 860, 66
    batas = [0, 25, 50, 75, 100]
    tier = [(HIJAU, "PROCEED", "pay normally",
             "PIN screen opens as usual"),
            (KUNING, "WARN", "allow, but show the reasons",
             "reasons shown above the PIN pad"),
            (JINGGA, "STEP_UP", "require additional verification",
             "confirmation required before PIN"),
            (MERAH, "COOLING_OFF", "hold — do not pay",
             "PIN screen never rendered; 30 s countdown")]
    for i, (w, nama, arti, klien) in enumerate(tier):
        a = x0 + total_lebar * batas[i] / 100
        b = x0 + total_lebar * batas[i + 1] / 100
        d.append(f'<rect x="{a}" y="{y}" width="{b - a}" height="30" '
                 f'fill="{w}" opacity="0.13"/>')
        d.append(f'<rect x="{a}" y="{y}" width="{b - a}" height="30" '
                 f'fill="none" stroke="{w}" stroke-width="1.2"/>')
        d.append(teks((a + b) / 2, y + 20, nama, 9.5, w, tebal=True, tengah=True))
        d.append(teks((a + b) / 2, y + 46, arti, 8, TINTA, tengah=True))
        d.append(teks((a + b) / 2, y + 59, klien, 7.5, REDUP, tengah=True))
    for v in batas:
        d.append(teks(x0 + total_lebar * v / 100, y - 6, str(v), 8, REDUP,
                      tengah=True))

    # --- Dua aturan yang menjaga pemetaan itu ---
    d.append(kotak(20, 148, 424, 76, "#fbfcfe", AKSEN, 4, 1.2))
    d.append(teks(34, 166, "THE FLOOR RULE   (invariant §2)", 8, AKSEN, tebal=True))
    d.append(teks(34, 182, "A young binding can score 15 — inside the proceed band.", 8.5))
    d.append(teks(34, 195, "Its verdict is unknown, so the action is floored to warn.", 8.5))
    d.append(teks(34, 213, "Absence of evidence is never converted into trust.", 8, AKSEN))

    d.append(kotak(456, 148, 424, 76, "#fbfcfe", AKSEN, 4, 1.2))
    d.append(teks(470, 166, "THE COMPOSITION RULE", 8, AKSEN, tebal=True))
    d.append(teks(470, 182, "Layer 2 holds no negative weight at all. A hard", 8.5))
    d.append(teks(470, 195, "contradiction forces anomaly; any other signal demotes", 8.5))
    d.append(teks(470, 208, "verified to unknown. An anomaly is never withdrawn.", 8.5))

    # --- Contoh terukur ---
    d.append(teks(20, 254, "WORKED EXAMPLES — produced by running the real evaluator",
                  9, AKSEN, tebal=True))
    KOL = (34, 470, 560, 646, 726)      # kasus, L1, L2, total, putusan
    kepala = ("SCAN", "LAYER 1", "LAYER 2", "TOTAL", "VERDICT / ACTION")
    baris = [("Established merchant, clean GPS", "0", "0", "0",
              "verified / proceed", HIJAU),
             ("Place never recorded before", "35", "0", "35",
              "unknown / warn", KUNING),
             ("GPS accuracy 800 m — Layer 1 refuses", "40", "0", "40",
              "unknown / warn", KUNING),
             ("Foreign sticker at an anchor of 6 observers", "63", "0", "63",
              "anomaly / step_up", JINGGA),
             ("Foreign sticker at an anchor of 47 observers", "83", "0", "83",
              "anomaly / cooling_off", MERAH)]
    y = 272
    for x, t in zip(KOL, kepala):
        d.append(teks(x, y, t, 7.5, AKSEN, tebal=True))
    d.append(f'<line x1="20" y1="{y + 6}" x2="880" y2="{y + 6}" '
             f'stroke="{GARIS}" stroke-width="1"/>')
    for i, (kasus, l1, l2, tot, hasil, w) in enumerate(baris):
        yy = y + 25 + i * 24
        if i % 2:
            d.append(f'<rect x="20" y="{yy - 15}" width="860" height="24" '
                     f'fill="{LATAR}"/>')
        d.append(teks(KOL[0], yy, kasus, 8.5))
        d.append(teks(KOL[1] + 18, yy, l1, 8.5, REDUP, mono=True, tengah=True))
        d.append(teks(KOL[2] + 18, yy, l2, 8.5, REDUP, mono=True, tengah=True))
        d.append(teks(KOL[3] + 14, yy, tot, 8.5, TINTA, mono=True, tebal=True,
                      tengah=True))
        d.append(teks(KOL[4], yy, hasil, 8.5, w, tebal=True))
    akhir_y = y + 25 + len(baris) * 24 - 15
    d.append(f'<line x1="20" y1="{akhir_y}" x2="880" y2="{akhir_y}" '
             f'stroke="{GARIS}" stroke-width="1"/>')
    d.append(teks(20, akhir_y + 24,
                  "The last two rows are the same attack on the same spot. What "
                  "differs is only how much evidence the system has gathered — "
                  "which is why the tier moves.", 8.5, REDUP, miring=True))
    return bungkus(W, H, d, "Q-Shield friction gates and tier mapping")


def main():
    periksa()
    for nama, isi in (("fig-1-architecture.svg", arsitektur()),
                      ("fig-2-friction-gates.svg", friksi())):
        (KELUARAN / nama).write_text(isi, encoding="utf-8")
        print(f"  {KELUARAN.name}/{nama}  ({len(isi) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
