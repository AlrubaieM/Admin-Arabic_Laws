r"""Render USAGE.md to USAGE.pdf with PyMuPDF Story (HarfBuzz shaping for Arabic; fonts from C:\Windows\Fonts).

Usage: uv run --no-project --no-managed-python --no-python-downloads --python .venv\Scripts\python.exe scripts\render_usage_pdf.py USAGE.md USAGE.pdf
"""
import html
import re
import sys
from pathlib import Path

import pymupdf

src, out = Path(sys.argv[1]), Path(sys.argv[2])
lines = src.read_text(encoding="utf-8").splitlines()

AR = re.compile(r"[\u0600-\u06FF]")


def inline(t: str) -> str:
    t = html.escape(t)
    # Arabic runs inside an English sentence are laid out right to left
    t = re.sub(r"[\u0600-\u06FF][\u0600-\u06FF0-9 ()/\-]*[\u0600-\u06FF)]|[\u0600-\u06FF]", lambda m: f'<span dir="rtl">{m.group(0)}</span>', t)
    t = re.sub(r"`([^`]+)`", lambda m: f'<code>{m.group(1)}</code>', t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    return t


def cell(t: str) -> str:
    t = inline(t.strip())
    return f'<span dir="rtl">{t}</span>' if AR.search(t) and not re.search(r"[A-Za-z]", re.sub(r"<[^>]+>", "", t)) else t


parts, i = [], 0
while i < len(lines):
    l = lines[i]
    if l.startswith("```"):
        j = i + 1
        block = []
        while not lines[j].startswith("```"):
            block.append(lines[j])
            j += 1
        parts.append("<pre>" + html.escape("\n".join(block)) + "</pre>")
        i = j + 1
        continue
    if l.startswith("|"):
        rows = []
        while i < len(lines) and lines[i].startswith("|"):
            rows.append([c for c in lines[i].strip().strip("|").split("|")])
            i += 1
        head, body = rows[0], [r for r in rows[2:]]
        t = "<table><tr>" + "".join(f"<th>{cell(c)}</th>" for c in head) + "</tr>"
        t += "".join("<tr>" + "".join(f"<td>{cell(c)}</td>" for c in r) + "</tr>" for r in body) + "</table>"
        parts.append(t)
        continue
    m = re.match(r"^(#{1,3}) (.*)$", l)
    if m:
        n = len(m.group(1))
        parts.append(f"<h{n}>{inline(m.group(2))}</h{n}>")
    elif re.match(r"^\d+\. ", l):
        parts.append(f'<p class="li">{inline(l)}</p>')
    elif l.strip():
        parts.append(f"<p>{inline(l)}</p>")
    i += 1

css = """
@font-face {font-family: body; src: url(tahoma.ttf);}
@font-face {font-family: body; src: url(tahomabd.ttf); font-weight: bold;}
@font-face {font-family: mono; src: url(consola.ttf);}
body {font-family: body; font-size: 9.5pt; line-height: 1.35; color: #1d1d1f;}
h1 {font-size: 17pt; color: #1f4e5f; margin: 0 0 8pt 0;}
h2 {font-size: 12.5pt; color: #1f4e5f; margin: 14pt 0 4pt 0; border-bottom: 1px solid #c9d6db;}
p {margin: 3pt 0;}
p.li {margin: 3pt 0 3pt 10pt;}
code {font-family: mono; font-size: 8.5pt; background-color: #eef2f4;}
pre {font-family: mono; font-size: 7.8pt; background-color: #f2f5f7; border: 1px solid #d5dee2; padding: 5pt; margin: 4pt 0; white-space: pre-wrap;}
table {border-collapse: collapse; margin: 4pt 0;}
th {text-align: left; font-size: 8.8pt; padding: 3pt; border: 1px solid #9fb3ba; border-bottom: 2px solid #1f4e5f;}
td {font-size: 8.8pt; padding: 3pt; border: 1px solid #d5dee2;}
"""
archive = pymupdf.Archive(r"C:\Windows\Fonts")
story = pymupdf.Story(html="<body>" + "\n".join(parts) + "</body>", user_css=css, archive=archive)
tmp = out.with_suffix(".raw.pdf")
writer = pymupdf.DocumentWriter(str(tmp))
mediabox = pymupdf.paper_rect("a4")
where = mediabox + (42, 42, -42, -48)
page_no = 0
more = True
while more:
    dev = writer.begin_page(mediabox)
    more, _ = story.place(where)
    story.draw(dev)
    writer.end_page()
    page_no += 1
writer.close()
# page numbers
doc = pymupdf.open(str(tmp))
for k, page in enumerate(doc, 1):
    page.insert_text((mediabox.width / 2 - 10, mediabox.height - 24), f"{k} / {len(doc)}", fontsize=8, color=(0.4, 0.4, 0.4))
doc.set_metadata({"title": "USAGE: building the principles memory vault with uv", "author": "Admin-Pr project"})
doc.save(str(out), garbage=3, deflate=True)
doc.close()
tmp.unlink()
print(out, page_no, "pages")
