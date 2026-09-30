"""
Ubah laporan Markdown jadi satu berkas HTML siap cetak.

Alasan berkas ini ada: laporan ditulis sekali di Markdown supaya bisa
di-review lewat git diff, tapi yang dikumpulkan ke lomba berupa PDF.
Menyalin dengan tangan berarti dua sumber yang akan melenceng —
pelajaran yang sudah pernah kena di proyek ini.

    python scripts/report_to_html.py docs/report/QShield-Project-Report-v2.md

Keluarannya berkas .html di sebelah berkas .md. Buka di Chrome lalu
Cmd+P -> Save as PDF; gaya cetaknya sudah diatur untuk A4.

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
@page { size: A4; margin: 18mm 16mm; }
:root {
  --tinta: #16181d; --redup: #5b6270; --garis: #d9dde5;
  --aksen: #1d4ed8; --latar-kode: #f5f6f8;
}
* { box-sizing: border-box; }
body {
  font: 10.5pt/1.55 "Charter", "Georgia", "Times New Roman", serif;
  color: var(--tinta); background: #fff;
  max-width: 178mm; margin: 0 auto; padding: 10mm 0;
  -webkit-print-color-adjust: exact; print-color-adjust: exact;
}
h1, h2, h3, h4 {
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  line-height: 1.25; margin: 1.6em 0 .6em;
}
h1 { font-size: 20pt; letter-spacing: -.01em; page-break-before: always; }
h1:first-of-type { page-break-before: avoid; }
h2 { font-size: 13.5pt; border-bottom: 1px solid var(--garis); padding-bottom: .25em; }
h3 { font-size: 11.5pt; color: var(--aksen); }
h4 { font-size: 10.5pt; color: var(--redup); text-transform: uppercase;
     letter-spacing: .06em; }
h1, h2, h3, h4 { page-break-after: avoid; }
p, ul, ol, table, pre, blockquote { page-break-inside: avoid; }
table {
  border-collapse: collapse; width: 100%; margin: 1em 0;
  font-size: 9pt; font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
}
th, td { border: 1px solid var(--garis); padding: 5px 8px; text-align: left;
         vertical-align: top; }
th { background: #eef1f6; font-weight: 600; }
tr:nth-child(even) td { background: #fafbfc; }
pre {
  background: var(--latar-kode); border: 1px solid var(--garis);
  border-radius: 4px; padding: 9px 11px; overflow-x: auto;
  font: 8.5pt/1.45 "SF Mono", Menlo, Consolas, monospace;
}
code {
  font: .88em "SF Mono", Menlo, Consolas, monospace;
  background: var(--latar-kode); padding: 1px 4px; border-radius: 3px;
}
pre code { background: none; padding: 0; font-size: 1em; }
blockquote {
  margin: 1em 0; padding: .55em 1em; border-left: 3px solid var(--aksen);
  background: #f6f8fd; color: #2c3340;
}
blockquote p:first-child { margin-top: 0; }
blockquote p:last-child { margin-bottom: 0; }
hr { border: 0; border-top: 1px solid var(--garis); margin: 1.8em 0; }
ul, ol { padding-left: 1.4em; }
li { margin: .25em 0; }
a { color: var(--aksen); text-decoration: none; }
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
                r"^(#{1,6}\s|```|>|\s*([-*]|\d+\.)\s|\||-{3,}\s*$)", baris[i]):
            par.append(baris[i].strip()); i += 1
        if par:
            keluar.append(f"<p>{sebaris(' '.join(par))}</p>")

    return "\n".join(keluar)


def main():
    if len(sys.argv) != 2:
        print(__doc__.strip(), file=sys.stderr); sys.exit(2)
    sumber = Path(sys.argv[1])
    md = sumber.read_text(encoding="utf-8")
    judul = next((l.lstrip("# ").strip() for l in md.split("\n")
                  if l.startswith("# ")), sumber.stem)
    tujuan = sumber.with_suffix(".html")
    tujuan.write_text(
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(judul)}</title><style>{GAYA}</style></head>"
        f"<body>{ubah(md)}</body></html>", encoding="utf-8")
    print(f"  {sumber}  ->  {tujuan}")
    print(f"  {tujuan.stat().st_size / 1024:.0f} KB")
    print("\n  Buka di Chrome, lalu Cmd+P -> Save as PDF (A4, margin default).")


if __name__ == "__main__":
    main()
