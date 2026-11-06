"""OCR review sheet: show every unacknowledged OCR disagreement beside its crop, and apply the reviewer's choices.

Usage (from the project root, through the uv execution template of section 3):
  ocr_sheet.py sheet <volume_id>
      writes work/review/ocr-sheet-<volume_id>.html from work/review/ocr-<volume_id>.yaml (run ocr-confirm first);
      open it in a browser, mark each line "keep" (the published text-layer reading is what the page draws)
      or "flag" (the vault may be wrong), then download ocr-decisions-<volume_id>.yaml.
  ocr_sheet.py apply <volume_id> <ocr-decisions file>
      adds the "keep" choices to decisions: in config/volumes/<volume_id>.yaml (existing decisions are never
      changed) and lists the flagged lines, which need a glyph repair or a source check, not a decision.

The sheet is a review aid in work/; it never changes Saudi-Principles/. Decisions take effect on the next build.
"""
from __future__ import annotations

import difflib
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import vault_emit as em  # noqa: E402
import vault_model as vm  # noqa: E402

# cause key -> (label, explanation); the order is the order of the sheet's sections
CAUSES: dict[str, tuple[str, str]] = {
    "digits": ("Number and page cells",
               "The page prints Arabic-Indic digits in MinionPro; Tesseract's Arabic model cannot read them "
               "(even one glyph at a time it confirms 51 of 316 digits). Compare the digits in the crop with the vault text."),
    "reference_line": ("Ruling-reference lines",
                       "A line holding only ruling references such as (ب/1752/1443): Tesseract misreads the Arabic-Indic digits."),
    "reference_digits": ("Wording with a trailing ruling reference",
                         "The words agree; only the digits of the ruling reference that closes the line differ."),
    "fi_ligature": ("Only the «في» ligature differs",
                    "The font draws «في» as a stacked ligature that Tesseract reads as #, 4, © or a stray letter."),
    "other_letters": ("Other letters differ, or OCR read nothing",
                      "Read these carefully: each line differs in one or more words, or Tesseract returned no text."),
}
RESOLUTIONS = {"keep"}  # "keep" = publish the text-layer reading; the pipeline implements no other OCR resolution
RE_REFERENCE_LINE = re.compile(r"^(\(\S+/[\d-]+/\d+\)\s*)+$")
RE_DATE = re.compile(r"^[0-3][0-9]/[01][0-9]/[0-9]{4}$")


def classify(item: dict) -> str:
    """The cause of one OCR disagreement (a key of CAUSES)."""
    loc, published = item["location"], item.get("published", "")
    first_reading = (item.get("ocr") or "").split(" | ")[0]
    if re.search(r":c[12]:", loc):
        return "digits"
    if RE_REFERENCE_LINE.match(published.strip()):
        return "reference_line"
    pub_words = [vm.skeleton(w) for w in published.split()]
    ocr_words = [vm.skeleton(w) for w in first_reading.split()]
    differing: list[str] = []
    for op, a1, a2, _b1, _b2 in difflib.SequenceMatcher(None, pub_words, ocr_words, autojunk=False).get_opcodes():
        if op != "equal":
            differing += pub_words[a1:a2] or ["+"]
    differing = [w for w in differing if w]
    if differing and all(w == "في" for w in differing):
        return "fi_ligature"
    if differing and all(re.search(r"\d", w) for w in differing):
        return "reference_digits"
    return "other_letters"


# ----------------------------------------------------------------------------
# sheet
# ----------------------------------------------------------------------------

_CSS = """
:root{--bg:#f7f6f3;--panel:#fff;--ink:#1d1d1f;--muted:#6b6b70;--line:#e3e1dc;--accent:#1f6f5c;--accent-ink:#fff;
--keep:#1f6f5c;--keep-bg:#e5f2ee;--flag:#a33a2c;--flag-bg:#f8e7e4;--crop-bg:#fff;--chip:#efede8}
@media (prefers-color-scheme:dark){:root{--bg:#161618;--panel:#1f1f22;--ink:#ececee;--muted:#9a9aa2;--line:#323236;
--accent:#4fb39a;--accent-ink:#0d1f1a;--keep:#62c4aa;--keep-bg:#1b2f2a;--flag:#ee8a7b;--flag-bg:#3a2321;--crop-bg:#fff;--chip:#2a2a2e}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--panel);border-bottom:1px solid var(--line);padding:12px 16px}
.bar{max-width:1100px;margin:0 auto;display:flex;flex-wrap:wrap;gap:10px 16px;align-items:center}
h1{font-size:17px;margin:0 auto 0 0}
.counts{display:flex;gap:8px;flex-wrap:wrap}
.chip{background:var(--chip);border-radius:999px;padding:2px 10px;font-size:13px;color:var(--muted)}
.chip b{color:var(--ink)}
button{font:inherit;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:8px;padding:6px 12px;cursor:pointer}
button.primary{background:var(--accent);border-color:var(--accent);color:var(--accent-ink);font-weight:600}
button:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
main{max-width:1100px;margin:0 auto;padding:16px}
.intro{color:var(--muted);margin:4px 0 18px}
section{margin:0 0 28px}
.sec-head{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:baseline;border-bottom:1px solid var(--line);padding-bottom:8px;margin-bottom:10px}
.sec-head h2{font-size:16px;margin:0}
.sec-head p{flex-basis:100%;margin:0;color:var(--muted);font-size:14px}
.sec-head .actions{margin-inline-start:auto;display:flex;gap:6px}
.item{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:0 0 10px;border-inline-start:4px solid var(--line)}
.item.keep{border-inline-start-color:var(--keep);background:linear-gradient(0deg,var(--keep-bg),var(--keep-bg)) padding-box}
.item.flag{border-inline-start-color:var(--flag);background:linear-gradient(0deg,var(--flag-bg),var(--flag-bg)) padding-box}
.crop{background:var(--crop-bg);border-radius:6px;padding:4px;overflow-x:auto}
.crop img{display:block;max-width:100%;height:auto;margin-inline-start:auto}
.rows{display:grid;grid-template-columns:auto 1fr;gap:2px 10px;margin:8px 0 6px}
.rows dt{color:var(--muted);font-size:13px;padding-top:2px}
.rows dd{margin:0;font-size:18px;line-height:1.6;font-family:"Segoe UI","Noto Naskh Arabic",Tahoma,sans-serif;overflow-wrap:anywhere}
.ocr{color:var(--muted)}
.meta{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;font-size:13px;color:var(--muted)}
.meta code{font-size:12px}
.choice{margin-inline-start:auto;display:flex;gap:4px}
.choice label{border:1px solid var(--line);border-radius:6px;padding:3px 10px;cursor:pointer;color:var(--ink);background:var(--panel)}
.choice input{position:absolute;opacity:0;pointer-events:none}
.choice input:checked+span{font-weight:700}
.choice label:has(input[value=keep]:checked){border-color:var(--keep);color:var(--keep)}
.choice label:has(input[value=flag]:checked){border-color:var(--flag);color:var(--flag)}
.choice label:has(input:focus-visible){outline:2px solid var(--accent);outline-offset:2px}
.hidden{display:none}
@media (max-width:640px){.rows{grid-template-columns:1fr}.rows dt{padding-top:6px}.choice{margin-inline-start:0}}
"""

_JS = r"""
const VID = document.body.dataset.volume;
const KEY = "ocr-sheet:" + VID;
let state = {};
try { state = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { state = {}; }
function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }
function paint(el) {
  const v = state[el.dataset.id] || "open";
  el.classList.toggle("keep", v === "keep"); el.classList.toggle("flag", v === "flag");
  const r = el.querySelector(`input[value="${v}"]`); if (r) r.checked = true;
}
function counts() {
  const all = document.querySelectorAll(".item");
  let k = 0, f = 0;
  all.forEach(el => { const v = state[el.dataset.id]; if (v === "keep") k++; else if (v === "flag") f++; });
  document.getElementById("n-keep").textContent = k;
  document.getElementById("n-flag").textContent = f;
  document.getElementById("n-open").textContent = all.length - k - f;
}
document.querySelectorAll(".item").forEach(el => {
  paint(el);
  el.querySelectorAll("input[type=radio]").forEach(r => r.addEventListener("change", () => {
    if (r.value === "open") delete state[el.dataset.id]; else state[el.dataset.id] = r.value;
    save(); paint(el); counts();
  }));
});
document.querySelectorAll("[data-group]").forEach(b => b.addEventListener("click", () => {
  const sec = document.getElementById(b.dataset.group);
  sec.querySelectorAll(".item").forEach(el => {
    if (b.dataset.set === "open") delete state[el.dataset.id]; else state[el.dataset.id] = b.dataset.set;
    paint(el);
  });
  save(); counts();
}));
document.getElementById("only-open").addEventListener("change", e => {
  document.querySelectorAll(".item").forEach(el => el.classList.toggle("hidden", e.target.checked && !!state[el.dataset.id]));
});
function q(s) { return JSON.stringify(String(s)); }
document.getElementById("download").addEventListener("click", () => {
  const d = new Date(), p = n => String(n).padStart(2, "0");
  const today = `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`;
  const keep = [], flag = [];
  document.querySelectorAll(".item").forEach(el => {
    const v = state[el.dataset.id];
    if (v === "keep") keep.push(el); else if (v === "flag") flag.push(el);
  });
  let y = `volume_id: ${q(VID)}\nreviewed_on: ${q(today)}\ndecisions:` + (keep.length ? "\n" : " {}\n");
  keep.forEach(el => {
    y += `  ${q(el.dataset.id)}:\n    resolution: "keep"\n    decided_on: ${q(today)}\n` +
         `    note: ${q(el.dataset.loc + ": crop reviewed; OCR misread (" + el.dataset.cause + ")")}\n`;
  });
  y += "flagged:" + (flag.length ? "\n" : " []\n");
  flag.forEach(el => { y += `  - item_id: ${q(el.dataset.id)}\n    location: ${q(el.dataset.loc)}\n`; });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([y], {type: "text/yaml;charset=utf-8"}));
  a.download = `ocr-decisions-${VID}.yaml`;
  document.body.appendChild(a); a.click(); a.remove();
});
counts();
"""


def build_sheet(vid: str, data: dict, decisions: dict) -> tuple[str, dict[str, int]]:
    """The review page for the unacknowledged OCR items of one volume, and the count per cause."""
    # lines the pipeline already kept on positive evidence (resolution auto_keep) need no review
    items = [it for it in data.get("items") or [] if it["item_id"] not in decisions and it.get("resolution") != "auto_keep"]
    groups: dict[str, list[dict]] = {k: [] for k in CAUSES}
    for it in items:
        groups[classify(it)].append(it)
    esc = html.escape
    parts = [
        "<!doctype html>", '<html lang="en">', "<head>", '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>OCR review sheet</title>", f"<style>{_CSS}</style>", "</head>",
        f'<body data-volume="{esc(vid)}">',
        "<header><div class=\"bar\">",
        f"<h1>OCR review — {esc(vid)}</h1>",
        '<div class="counts"><span class="chip">keep <b id="n-keep">0</b></span>'
        '<span class="chip">flag <b id="n-flag">0</b></span><span class="chip">open <b id="n-open">0</b></span></div>',
        '<label class="chip"><input type="checkbox" id="only-open"> show open only</label>',
        '<button class="primary" id="download">Download decisions</button>',
        "</div></header>", "<main>",
        f'<p class="intro">{len(items)} lines where Tesseract disagrees with the published text, out of '
        f'{int(data.get("confirmed", 0)) + int(data.get("disagreeing", 0)) + int(data.get("decided", 0))} lines read. '
        "Each crop is the page as printed. Choose <b>keep</b> when the published text matches the crop, "
        "<b>flag</b> when it does not. Choices are kept in this browser until you download them.</p>",
    ]
    for cause, rows in groups.items():
        if not rows:
            continue
        label, explanation = CAUSES[cause]
        sid = f"sec-{cause}"
        parts += [f'<section id="{sid}">', '<div class="sec-head">', f"<h2>{esc(label)} · {len(rows)}</h2>",
                  '<div class="actions">'
                  f'<button data-group="{sid}" data-set="keep">Keep all</button>'
                  f'<button data-group="{sid}" data-set="open">Clear</button></div>',
                  f"<p>{esc(explanation)}</p>", "</div>"]
        for it in rows:
            iid, loc = it["item_id"], it["location"]
            crop = Path(it.get("crop", "")).name
            parts += [
                f'<article class="item" data-id="{esc(iid)}" data-loc="{esc(loc)}" data-cause="{esc(label)}">',
                f'<div class="crop"><img loading="lazy" src="crops/{esc(vid)}/{esc(crop)}" alt="crop of {esc(loc)}"></div>',
                '<dl class="rows">',
                f'<dt>vault</dt><dd dir="rtl">{esc(it.get("published", ""))}</dd>',
                f'<dt>OCR</dt><dd dir="rtl" class="ocr">{esc(it.get("ocr", "")) or "<i>(no text)</i>"}</dd>',
                "</dl>",
                '<div class="meta">', f"<code>{esc(loc)}</code>", f"<code>{esc(iid)}</code>",
                '<div class="choice" role="radiogroup" aria-label="decision">',
                f'<label><input type="radio" name="d-{esc(iid)}" value="keep"><span>keep</span></label>',
                f'<label><input type="radio" name="d-{esc(iid)}" value="flag"><span>flag</span></label>',
                f'<label><input type="radio" name="d-{esc(iid)}" value="open"><span>open</span></label>',
                "</div></div></article>",
            ]
        parts.append("</section>")
    parts += ["</main>", f"<script>{_JS}</script>", "</body>", "</html>", ""]
    return "\n".join(parts), {k: len(v) for k, v in groups.items()}


# ----------------------------------------------------------------------------
# apply
# ----------------------------------------------------------------------------

def _q(s: str) -> str:
    return json.dumps(str(s), ensure_ascii=False)  # a JSON string is a valid YAML double-quoted scalar


def merge_decisions(config_text: str, new: dict[str, dict]) -> tuple[str, list[str], list[str]]:
    """Add `new` decisions to the configuration text without rewriting the rest of the file.

    Returns (text, added ids, skipped ids); an id that already has a decision is skipped, never changed."""
    for iid, d in new.items():
        if str(d.get("resolution", "")).lower() not in RESOLUTIONS:
            raise ValueError(f"{iid}: resolution {d.get('resolution')!r} is not one of {sorted(RESOLUTIONS)}")
        if not RE_DATE.match(str(d.get("decided_on", ""))):
            raise ValueError(f"{iid}: decided_on {d.get('decided_on')!r} is not DD/MM/YYYY")
    existing = (em.load_yaml(config_text) or {}).get("decisions") or {}
    added = [i for i in new if i not in existing]
    skipped = [i for i in new if i in existing]
    if not added:
        return config_text, added, skipped
    block = ""
    for iid in added:
        d = new[iid]
        block += f"  {_q(iid)}:\n    resolution: {_q(d['resolution'])}\n    decided_on: {_q(d['decided_on'])}\n"
        if d.get("note"):
            block += f"    note: {_q(d['note'])}\n"
    if re.search(r"^decisions: \{\}[ \t]*$", config_text, re.MULTILINE):
        out = re.sub(r"^decisions: \{\}[ \t]*$\n?", lambda _m: "decisions:\n" + block, config_text, count=1, flags=re.MULTILINE)
    elif re.search(r"^decisions:[ \t]*$", config_text, re.MULTILINE):
        out = re.sub(r"^decisions:[ \t]*$\n", lambda m: m.group(0) + block, config_text, count=1, flags=re.MULTILINE)
    elif not re.search(r"^decisions:", config_text, re.MULTILINE):
        out = config_text.rstrip("\n") + "\n\ndecisions:\n" + block
    else:
        raise ValueError("decisions: is written in a form this tool does not edit; add the entries by hand")
    check = (em.load_yaml(out) or {}).get("decisions") or {}
    if any(i not in check for i in added) or any(check[i] != existing[i] for i in existing):
        raise ValueError("merged configuration does not hold the expected decisions")
    return out, added, skipped


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in ("sheet", "apply") or (argv[0] == "apply" and len(argv) != 3):
        print(__doc__)
        return 2
    vid = argv[1]
    cfg_path = ROOT / "config" / "volumes" / f"{vid}.yaml"
    ocr_path = ROOT / "work" / "review" / f"ocr-{vid}.yaml"
    if not ocr_path.exists():
        print(f"{ocr_path.relative_to(ROOT).as_posix()} not found: run pipeline.py ocr-confirm --volume {vid} first")
        return 1
    cfg_text = cfg_path.read_text(encoding="utf-8")
    decisions = (em.load_yaml(cfg_text) or {}).get("decisions") or {}
    data = em.load_yaml(ocr_path.read_text(encoding="utf-8"))
    if argv[0] == "sheet":
        page, counts = build_sheet(vid, data, decisions)
        out = ROOT / "work" / "review" / f"ocr-sheet-{vid}.html"
        out.write_text(page, encoding="utf-8", newline="\n")
        auto = sum(1 for it in data.get("items") or [] if it.get("resolution") == "auto_keep")
        by_cause = ", ".join(f"{k} {v}" for k, v in counts.items() if v)
        print(f"{out.relative_to(ROOT).as_posix()}: {sum(counts.values())} OCR lines need review" + (f" ({by_cause})" if by_cause else "") +
              f"; {auto} kept automatically (confirmed by the second reader)")
        return 0
    exported = em.load_yaml(Path(argv[2]).read_text(encoding="utf-8")) or {}
    if exported.get("volume_id") != vid:
        print(f"the decisions file is for {exported.get('volume_id')!r}, not {vid!r}")
        return 1
    known = {it["item_id"] for it in data.get("items") or []}
    chosen = exported.get("decisions") or {}
    unknown = [i for i in chosen if i not in known]
    new = {i: d for i, d in chosen.items() if i in known}
    text, added, skipped = merge_decisions(cfg_text, new)
    if added:
        cfg_path.write_text(text, encoding="utf-8", newline="\n")
    print(f"{cfg_path.relative_to(ROOT).as_posix()}: {len(added)} decisions added, {len(skipped)} already decided (unchanged), "
          f"{len(unknown)} not in the current OCR record (ignored)")
    for f in exported.get("flagged") or []:
        print(f"flagged for a source check: {f.get('item_id')} {f.get('location')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
