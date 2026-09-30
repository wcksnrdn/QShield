"""
Ubah laporan Markdown jadi satu berkas HTML siap cetak.

Alasan berkas ini ada: laporan ditulis sekali di Markdown supaya bisa
di-review lewat git diff, tapi yang dikumpulkan ke lomba berupa PDF.
Menyalin dengan tangan berarti dua sumber yang akan melenceng —
pelajaran yang sudah pernah kena di proyek ini.

    python scripts/report_to_html.py docs/report/QShield-Project-Report-v2.md

Menghasilkan .html DAN .pdf di sebelah berkas .md, lalu menghitung
halamannya terhadap batas lomba. HackNusa 2026 menuntut 8-10 halaman
di luar sampul; skrip ini keluar dengan status bukan-nol kalau
batasnya dilanggar, supaya ketahuan sekarang dan bukan saat submit.

Pakai --no-pdf kalau cuma mau HTML-nya.

Bukan pengurai Markdown umum. Ia menangani persis yang dipakai laporan
kita: judul, paragraf, tabel, daftar, blok kode, kutipan, tebal, miring,
kode sebaris, dan garis pemisah. Kalau laporannya memakai sesuatu yang
lain, TAMBAHKAN di sini — jangan tulis HTML dengan tangan.
"""

import html
import re
import sys
from pathlib import Path

GAYA = """
@page { size: A4; margin: 15mm 15mm 16mm; }
:root {
  --tinta: #16181d; --redup: #5b6270; --garis: #d5dae3;
  --aksen: #1d4ed8; --latar-kode: #f4f6f8;
}
* { box-sizing: border-box; }
body {
  font: 9.4pt/1.42 "Charter", "Georgia", "Times New Roman", serif;
  color: var(--tinta); background: #fff;
  max-width: 180mm; margin: 0 auto; padding: 0;
  -webkit-print-color-adjust: exact; print-color-adjust: exact;
  hyphens: auto;
}
h1, h2, h3 {
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  line-height: 1.2; page-break-after: avoid;
}
/* Bab TIDAK dipaksa mulai di halaman baru: dengan enam bab, itu
   membuang sampai tiga halaman dari jatah sepuluh. Pemisahnya visual. */
h1 {
  font-size: 13pt; margin: 1.5em 0 .5em; padding-top: .45em;
  border-top: 2.5px solid var(--tinta); letter-spacing: -.005em;
}
h2 { font-size: 10.4pt; margin: 1.15em 0 .35em; color: #0f172a; }
h3 { font-size: 9.4pt; margin: .9em 0 .3em; color: var(--aksen); }
p { margin: .5em 0; text-align: justify; }
p, ul, ol, table, pre, blockquote { page-break-inside: avoid; }
table {
  border-collapse: collapse; width: 100%; margin: .7em 0;
  font-size: 8.1pt; line-height: 1.32;
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
}
th, td { border: .6px solid var(--garis); padding: 3.5px 6px;
         text-align: left; vertical-align: top; }
th { background: #eaeef5; font-weight: 600; }
tr:nth-child(even) td { background: #fafbfc; }
pre {
  background: var(--latar-kode); border: .6px solid var(--garis);
  border-radius: 3px; padding: 6px 9px; margin: .7em 0; overflow-x: auto;
  font: 8pt/1.4 "SF Mono", Menlo, Consolas, monospace;
}
code { font: .86em "SF Mono", Menlo, Consolas, monospace;
       background: var(--latar-kode); padding: 0 3px; border-radius: 2px; }
pre code { background: none; padding: 0; font-size: 1em; }
blockquote {
  margin: .8em 0; padding: .45em .9em; border-left: 2.5px solid var(--aksen);
  background: #f5f8fd; color: #26303f;
}
blockquote p { margin: .25em 0; text-align: left; }
hr { border: 0; border-top: .6px solid var(--garis); margin: 1.2em 0; }
ul, ol { padding-left: 1.3em; margin: .5em 0; }
li { margin: .18em 0; }
a { color: var(--aksen); text-decoration: none; }

/* --- Halaman sampul: tidak dihitung dalam batas 8-10 halaman --- */
.cover {
  page-break-after: always; height: 258mm;
  display: flex; flex-direction: column; justify-content: center;
  text-align: center; border: none;
}
.cover h1 {
  font-size: 40pt; border: none; padding: 0; margin: 0 0 .1em;
  letter-spacing: -.02em; font-weight: 700;
}
.cover h2 {
  font-size: 15pt; font-weight: 500; color: #0f172a; margin: 0 0 .5em;
}
.cover h3 {
  font-size: 10.5pt; font-weight: 400; color: var(--redup);
  font-style: italic; margin: 0 0 3.2em;
}
.cover p { text-align: center; margin: .42em 0; font-size: 10pt; }
.cover p:first-of-type {
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-size: 9pt; letter-spacing: .09em; text-transform: uppercase;
  color: var(--aksen); margin-bottom: 2.6em;
}
.cover em { color: var(--redup); }

figure { margin: 1em 0 1.1em; page-break-inside: avoid; }
figure img { width: 100%; display: block;
             border: .6px solid var(--garis); border-radius: 3px; }
figcaption {
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-size: 7.8pt; color: var(--redup); margin-top: .45em; line-height: 1.35;
}
figcaption b { color: var(--tinta); font-weight: 600; }
"""


def sebaris(t):
    """Tebal, miring, kode sebaris, pranala — setelah di-escape."""
    t = html.escape(t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)
    return t


def sel(baris):
    return [s.strip() for s in baris.strip().strip("|").split("|")]


def ubah(md):
    keluar, i, baris = [], 0, md.split("\n")
    while i < len(baris):
        b = baris[i]

        # HTML mentah satu baris (pembungkus halaman sampul) diteruskan
        # apa adanya. WAJIB berada sebelum penanganan paragraf: regex
        # penghenti paragraf ikut mengenali tag ini, jadi tanpa cabang
        # ini `i` tidak pernah maju dan pengurainya berputar selamanya.
        if re.match(r"^\s*</?(div|section|br|img|figure|figcaption)\b", b):
            keluar.append(b.strip()); i += 1; continue

        # Pagar kode boleh MENJOROK — di laporan kita ada satu di dalam
        # butir daftar bernomor. Menuntutnya rata kiri membuat blok itu
        # jatuh ke penanganan paragraf dan backtick-nya bocor ke keluaran.
        if b.lstrip().startswith("```"):
            jorok, isi, i = len(b) - len(b.lstrip()), [], i + 1
            while i < len(baris) and not baris[i].lstrip().startswith("```"):
                isi.append(baris[i][jorok:] if baris[i][:jorok].isspace()
                           or not baris[i].strip() else baris[i].lstrip())
                i += 1
            keluar.append("<pre><code>"
                          + html.escape("\n".join(isi).strip("\n"))
                          + "</code></pre>")
            i += 1; continue

        if re.match(r"^(-{3,}|\*{3,}|_{3,})\s*$", b):
            keluar.append("<hr>"); i += 1; continue

        m = re.match(r"^(#{1,6})\s+(.*)$", b)
        if m:
            n = len(m.group(1))
            keluar.append(f"<h{n}>{sebaris(m.group(2))}</h{n}>")
            i += 1; continue

        # Tabel: baris header, baris pemisah, lalu isi.
        if (b.strip().startswith("|") and i + 1 < len(baris)
                and re.match(r"^\s*\|[\s:|-]+\|\s*$", baris[i + 1])):
            kepala = sel(b); i += 2
            th = "".join(f"<th>{sebaris(c)}</th>" for c in kepala)
            tr = []
            while i < len(baris) and baris[i].strip().startswith("|"):
                td = "".join(f"<td>{sebaris(c)}</td>" for c in sel(baris[i]))
                tr.append(f"<tr>{td}</tr>"); i += 1
            keluar.append(f"<table><thead><tr>{th}</tr></thead>"
                          f"<tbody>{''.join(tr)}</tbody></table>")
            continue

        if b.startswith(">"):
            isi = []
            while i < len(baris) and baris[i].startswith(">"):
                isi.append(baris[i].lstrip(">").strip()); i += 1
            blok = "".join(f"<p>{sebaris(p)}</p>"
                           for p in "\n".join(isi).split("\n\n") if p.strip())
            keluar.append(f"<blockquote>{blok}</blockquote>")
            continue

        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", b)
        if m:
            urut = not m.group(2) in ("-", "*")
            tag = "ol" if urut else "ul"
            li = []
            while i < len(baris):
                mm = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", baris[i])
                if mm:
                    li.append(f"<li>{sebaris(mm.group(3))}"); i += 1
                # Baris lanjutan yang menjorok masuk ke butir terakhir.
                elif baris[i].lstrip().startswith("```"):
                    break
                elif li and baris[i].startswith("   ") and baris[i].strip():
                    li[-1] += " " + sebaris(baris[i].strip()); i += 1
                elif li and not baris[i].strip() and i + 1 < len(baris) and \
                        re.match(r"^\s*([-*]|\d+\.)\s+", baris[i + 1]):
                    i += 1
                else:
                    break
            keluar.append(f"<{tag}>" + "".join(x + "</li>" for x in li)
                          + f"</{tag}>")
            continue

        if not b.strip():
            i += 1; continue

        par = []
        while i < len(baris) and baris[i].strip() and not re.match(
                r"^(#{1,6}\s|```|>|\s*([-*]|\d+\.)\s|\||-{3,}\s*$|\s*</?(div|section)\b)",
                baris[i]):
            par.append(baris[i].strip()); i += 1
        if par:
            keluar.append(f"<p>{sebaris(' '.join(par))}</p>")

    return "\n".join(keluar)


BATAS_MIN, BATAS_MAKS = 8, 10        # HackNusa 2026, di luar sampul

CHROME = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
          "/Applications/Chromium.app/Contents/MacOS/Chromium",
          "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")


def ke_pdf(html: Path):
    """Cetak lewat Chrome headless. Mengembalikan jumlah halaman."""
    import subprocess

    peramban = next((c for c in CHROME if Path(c).exists()), None)
    if peramban is None:
        print("  (Chrome tidak ditemukan — lewati PDF; cetak manual dari HTML)")
        return None

    pdf = html.with_suffix(".pdf")
    # --no-pdf-header-footer, BUKAN --print-to-pdf-no-header: yang kedua
    # sudah tidak berfungsi di Chrome sekarang, dan kalau keduanya dipasang
    # ia justru menghidupkan kembali header yang mau dibuang.
    subprocess.run(
        [peramban, "--headless", "--disable-gpu", "--no-sandbox",
         "--no-pdf-header-footer", f"--print-to-pdf={pdf}",
         html.resolve().as_uri()],
        capture_output=True, timeout=180)
    if not pdf.exists():
        print("  (Chrome gagal mencetak — cetak manual dari HTML)")
        return None

    try:
        from pypdf import PdfReader
        n = len(PdfReader(str(pdf)).pages)
    except ImportError:
        print(f"  {pdf}  (pasang pypdf untuk menghitung halaman)")
        return None
    print(f"  {pdf}  ->  {n} halaman (sampul 1 + isi {n - 1})")
    return n - 1


def main():
    arg = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(arg) != 1:
        print(__doc__.strip(), file=sys.stderr); sys.exit(2)
    sumber = Path(arg[0])
    md = sumber.read_text(encoding="utf-8")
    judul = next((l.lstrip("# ").strip() for l in md.split("\n")
                  if l.startswith("# ")), sumber.stem)
    tujuan = sumber.with_suffix(".html")
    tujuan.write_text(
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(judul)}</title><style>{GAYA}</style></head>"
        f"<body>{ubah(md)}</body></html>", encoding="utf-8")
    print(f"  {sumber}  ->  {tujuan}  ({tujuan.stat().st_size / 1024:.0f} KB)")

    if "--no-pdf" in sys.argv:
        return
    isi = ke_pdf(tujuan)
    if isi is None:
        return
    if not BATAS_MIN <= isi <= BATAS_MAKS:
        print(f"\n  BATAS DILANGGAR: isi {isi} halaman, "
              f"seharusnya {BATAS_MIN}-{BATAS_MAKS} di luar sampul.")
        sys.exit(1)
    print(f"  batas lomba {BATAS_MIN}-{BATAS_MAKS} halaman: LOLOS")


if __name__ == "__main__":
    main()
