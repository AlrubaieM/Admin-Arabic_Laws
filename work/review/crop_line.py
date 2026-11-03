"""Render a 500 dpi crop of one source line (or a page region) for visual review.

Usage (from the project root, through the project venv):
  .venv/bin/python work/review/crop_line.py <volume_id> <page> "<substring of the line>" <out.png>
  .venv/bin/python work/review/crop_line.py <volume_id> <page> --rect x0 y0 x1 y1 <out.png>
Prints the line text, its location and the crop path.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import pymupdf  # noqa: E402
import pdf_source as ps  # noqa: E402
import vault_emit as em  # noqa: E402

vid, page = sys.argv[1], int(sys.argv[2])
cfg = em.load_yaml((ROOT / "config" / "volumes" / f"{vid}.yaml").read_text(encoding="utf-8"))
entry = [e for e in cfg["source_files"] if e["kind"] == "index"][0]
doc = pymupdf.open(str(ROOT / "Input" / vid / (entry.get("stored_name") or entry["original_name"])))
fm = ps.load_font_maps(doc)
rep = ps.build_repairs(cfg["fonts"])
st = ps.ReaderSettings.from_config(cfg.get("reader"))
if sys.argv[3] == "--rect":
    x0, y0, x1, y1 = map(float, sys.argv[4:8])
    out = sys.argv[8]
    ps.render_crop(doc, page, (x0, y0, x1, y1), out, dpi=500, pad=3)
    print("crop", out)
    sys.exit(0)
needle, out = sys.argv[3], sys.argv[4]
glyphs = ps.page_glyphs(doc, page, fm, rep, st)
table = ps.segment_table(page, ps.merge_rulings(ps.page_rulings(doc[page - 1])), glyphs, st)
lines = [l for r in table.rows for c in r.cells for l in c.lines] + table.outside if table else ps.form_lines(glyphs, st)
hits = [l for l in lines if needle in l.text]
if not hits:
    print("no line contains", repr(needle))
    sys.exit(1)
l = hits[0]
ps.render_crop(doc, page, (l.x0, l.y0, l.x1, l.y1), out, dpi=500, pad=3)
print("line:", l.text)
print("cell:", l.cell, "bbox: %.1f %.1f %.1f %.1f" % (l.x0, l.y0, l.x1, l.y1))
print("crop", out)
