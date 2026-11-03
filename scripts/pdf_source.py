"""Glyph-geometry reader for the Board of Grievances principle-collection PDFs.

The text layer of the reviewed sample is defective (master prompt, section 5,
TEXT LAYER PROTOCOL): hamza letters are drawn as a zero-width letter glyph
over an alef glyph, the letters seen/sheen/sad/dad are drawn as a head glyph
(unmapped, carrying the letter's identity) plus a shared tail glyph (mapped
to an arbitrary letter), a lam-alef ligature glyph is mapped to a bare lam,
ligature glyphs map to two code points and are followed by a zero-width
continuation glyph, one font is embedded twice with conflicting CMaps, and
glyphs arrive in visual order.

This module reads every glyph with its glyph id, bounding box and font
(PyMuPDF text trace), resolves its text through the ToUnicode CMap of the font
object used on that page, applies the configured glyph repairs, forms lines
from glyph geometry inside each table cell, orders them right to left,
restores digit runs, attaches combining marks, and normalizes to NFC with
Western digits.  It also reads the drawn table rulings so that the index
tables can be segmented into rows and cells.

Volume-specific facts (repairs, thresholds, joiners) come from the volume
configuration; nothing here hard-codes sample values.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable

import pymupdf

# ----------------------------------------------------------------------------
# Character classes
# ----------------------------------------------------------------------------

ARABIC_INDIC = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
ARABIC_INDIC.update({ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")})
COMBINING_MARKS = set(
    "ًٌٍَُِّْٰٕٖٜٟٓٔٗ٘ٙٚٛٝٞ"
)
BELOW_MARKS = set("ٍِٕٖ")
HAMZA_LETTERS = {"أ", "إ", "آ", "ٱ", "ؤ", "ئ"}
# zero-width hamza-letter glyph -> the carrier glyph texts it composes with
HAMZA_CARRIERS = {
    "أ": ("ا", "لا"), "إ": ("ا", "لا"), "آ": ("ا", "لا"), "ٱ": ("ا", "لا"),
    "ؤ": ("و",), "ئ": ("ي", "ى"),
}
LAM_ALEF_WITH_HAMZA = {"أ": "لأ", "إ": "لإ", "آ": "لآ", "ٱ": "لٱ"}
REPLACEMENT = "�"
DIGITS = set("0123456789")
PUA_LO, PUA_HI = 0xE000, 0xF8FF


def western_digits(text: str) -> str:
    return text.translate(ARABIC_INDIC)


def nfkc_presentation_forms(text: str) -> str:
    """Map Arabic presentation forms to base letters, per character."""
    out = []
    for ch in text:
        o = ord(ch)
        if 0xFB50 <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFC:
            mapped = unicodedata.normalize("NFKC", ch)
            if len(mapped) == 2 and mapped[0] in (" ", "ـ") and mapped[1] in COMBINING_MARKS:
                mapped = mapped[1]
            out.append(mapped)
        else:
            out.append(ch)
    return "".join(out)


def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFC", western_digits(nfkc_presentation_forms(text)))


def is_pua(text: str) -> bool:
    return bool(text) and all(PUA_LO <= ord(c) <= PUA_HI for c in text)


# ----------------------------------------------------------------------------
# ToUnicode CMaps, per font object
# ----------------------------------------------------------------------------

_HEX = re.compile(r"<([0-9A-Fa-f]+)>")
_SECTION = re.compile(r"begin(bfchar|bfrange)(.*?)end\1", re.S)
_RANGE = re.compile(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(\[[^\]]*\]|<[0-9A-Fa-f]+>)", re.S)


def _utf16be_to_str(hexstr: str) -> str:
    if len(hexstr) % 2:
        hexstr = "0" + hexstr
    raw = bytes.fromhex(hexstr)
    if len(raw) % 2:
        raw = b"\x00" + raw
    return raw.decode("utf-16-be", errors="replace")


def parse_tounicode(cmap_text: str) -> dict[int, str]:
    """Parse the bfchar/bfrange sections of a ToUnicode CMap, in file order."""
    mapping: dict[int, str] = {}
    for section in _SECTION.finditer(cmap_text):
        kind, body = section.group(1), section.group(2)
        if kind == "bfchar":
            tokens = _HEX.findall(body)
            for i in range(0, len(tokens) - 1, 2):
                mapping[int(tokens[i], 16)] = _utf16be_to_str(tokens[i + 1])
        else:
            for m in _RANGE.finditer(body):
                lo, hi, dst = int(m.group(1), 16), int(m.group(2), 16), m.group(3)
                if dst.startswith("["):
                    for k, item in enumerate(_HEX.findall(dst)):
                        if lo + k <= hi:
                            mapping[lo + k] = _utf16be_to_str(item)
                else:
                    base = _utf16be_to_str(dst.strip("<>"))
                    for k in range(hi - lo + 1):
                        mapping[lo + k] = base[:-1] + chr(ord(base[-1]) + k) if base else ""
    return mapping


@dataclass
class FontObject:
    xref: int
    base: str  # font name without subset prefix (as the text trace reports it)
    full_name: str
    encoding: str
    cmap: dict[int, str]
    kind: str  # identity | simple | none
    pages: list[int] = field(default_factory=list)


@dataclass
class FontMaps:
    fonts: dict[int, FontObject]
    by_page: dict[int, dict[str, list[int]]]  # page -> base name -> xrefs

    def shared(self, base: str) -> list[FontObject]:
        return [f for f in self.fonts.values() if f.base == base]


def load_font_maps(doc: pymupdf.Document) -> FontMaps:
    fonts: dict[int, FontObject] = {}
    by_page: dict[int, dict[str, list[int]]] = {}
    for pno in range(1, len(doc) + 1):
        page_fonts: dict[str, list[int]] = {}
        for entry in doc[pno - 1].get_fonts(full=True):
            xref, _ext, _ftype, name, _ref, encoding = entry[:6]
            base = name.split("+", 1)[-1]
            if xref not in fonts:
                cmap: dict[int, str] = {}
                kind = "none"
                tu = doc.xref_get_key(xref, "ToUnicode")
                if tu[0] == "xref":
                    tu_xref = int(tu[1].split()[0])
                    try:
                        cmap = parse_tounicode(doc.xref_stream(tu_xref).decode("latin-1", errors="replace"))
                    except Exception:  # pragma: no cover - defensive
                        cmap = {}
                    kind = "identity" if "Identity" in (encoding or "") else "simple"
                fonts[xref] = FontObject(xref, base, name, encoding or "", cmap, kind)
            fonts[xref].pages.append(pno)
            page_fonts.setdefault(base, [])
            if xref not in page_fonts[base]:
                page_fonts[base].append(xref)
        by_page[pno] = page_fonts
    return FontMaps(fonts, by_page)


# ----------------------------------------------------------------------------
# Glyphs
# ----------------------------------------------------------------------------


@dataclass
class Glyph:
    page: int  # 1-based physical page
    seq: int  # order in the content stream
    font: str
    gid: int
    raw_uni: int  # PyMuPDF's own unicode guess (never published)
    text: str  # resolved text ("" = dropped glyph)
    x0: float
    y0: float
    x1: float
    y1: float
    ox: float  # origin x
    oy: float  # origin y (baseline)
    size: float
    bidi: int
    status: str = "cmap"
    note: str = ""
    cell: tuple[int, int] | None = None  # (row, col) once assigned to a table cell

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def is_mark(self) -> bool:
        return self.text != "" and all(c in COMBINING_MARKS for c in self.text)

    @property
    def is_zero_width(self) -> bool:
        return self.x1 - self.x0 < 0.05

    @property
    def bold(self) -> bool:
        return "bold" in self.font.lower()

    @property
    def dropped(self) -> bool:
        return self.status.startswith("drop")

    @property
    def unresolved(self) -> bool:
        return self.status.startswith("unresolved")


@dataclass
class RepairRule:
    """A configured treatment for one (font, glyph id)."""

    text: str
    role: str  # letter | alef_body | lam_alef | head | tail | mark | punctuation
    basis: str = ""


@dataclass
class ReaderSettings:
    space_gap_ratio: float = 0.3  # gap/size above which a space is inserted when no space glyph is drawn
    baseline_tolerance_ratio: float = 0.25
    digit_run_joiners: tuple[str, ...] = ()  # characters that keep digit groups in one left-to-right run
    hamza_x_tolerance: float = 0.6
    head_tail_tolerance: float = 0.8
    page_overrides: tuple = ()  # ({pages: [..], digit_run_joiners: [..]}, ...)

    @classmethod
    def from_config(cls, cfg: dict | None) -> "ReaderSettings":
        cfg = cfg or {}
        return cls(
            space_gap_ratio=float(cfg.get("space_gap_ratio", 0.3)),
            baseline_tolerance_ratio=float(cfg.get("baseline_tolerance_ratio", 0.25)),
            digit_run_joiners=tuple(cfg.get("digit_run_joiners", []) or []),
            hamza_x_tolerance=float(cfg.get("hamza_x_tolerance", 0.6)),
            head_tail_tolerance=float(cfg.get("head_tail_tolerance", 0.8)),
            page_overrides=tuple(cfg.get("page_overrides", []) or []),
        )

    def for_page(self, pno: int) -> "ReaderSettings":
        """Settings with the overrides configured for this physical page applied."""
        out = self
        for ov in self.page_overrides:
            if pno in (ov.get("pages") or []):
                out = ReaderSettings(out.space_gap_ratio, out.baseline_tolerance_ratio,
                                     tuple(ov.get("digit_run_joiners", out.digit_run_joiners)),
                                     out.hamza_x_tolerance, out.head_tail_tolerance, ())
        return out


def build_repairs(config_fonts: Iterable[dict]) -> dict[tuple[str, int], RepairRule]:
    repairs: dict[tuple[str, int], RepairRule] = {}
    for font in config_fonts or []:
        for gid, rule in (font.get("glyph_repairs") or {}).items():
            repairs[(font["name"], int(gid))] = RepairRule(
                text=str(rule.get("text", "")), role=str(rule.get("role", "letter")), basis=str(rule.get("basis", ""))
            )
    return repairs


def resolve_glyph_text(fm: FontMaps, pno: int, font: str, gid: int) -> tuple[str | None, str]:
    """Return (text, status) for a glyph from the CMaps, without repairs."""
    xrefs = fm.by_page.get(pno, {}).get(font, [])
    own = [fm.fonts[x] for x in xrefs]
    if len(own) > 1:
        return None, "unresolved:ambiguous_font_object"
    text = own[0].cmap.get(gid) if own else None
    if text is not None and not is_pua(text) and REPLACEMENT not in text:
        return text, "cmap"
    for other in fm.shared(font):
        if own and other.xref == own[0].xref:
            continue
        t = other.cmap.get(gid)
        if t is not None and not is_pua(t) and REPLACEMENT not in t:
            return t, "cmap_shared"
    if text is not None and is_pua(text) and len(text) == 1 and 0xF030 <= ord(text) <= 0xF039:
        return chr(ord(text) - 0xF000), "symbol_digit"
    if text is None:
        return None, "unresolved:no_cmap_entry"
    return None, "unresolved:cmap_maps_to_fffd" if REPLACEMENT in text else "unresolved:cmap_maps_to_pua"


def page_glyphs(doc: pymupdf.Document, pno: int, fm: FontMaps, repairs: dict[tuple[str, int], RepairRule],
                settings: ReaderSettings | None = None) -> list[Glyph]:
    """Read every glyph of physical page pno (1-based) with its resolved text."""
    settings = settings or ReaderSettings()
    page = doc[pno - 1]
    glyphs: list[Glyph] = []
    seq = 0
    seen: set[tuple] = set()
    for span in page.get_texttrace():
        font = span["font"]
        size = float(span["size"])
        for ch in span["chars"]:
            uni, gid, origin, bbox = ch
            seq += 1
            key = (font, gid, uni, round(float(bbox[0]), 2), round(float(origin[1]), 2))
            if key in seen:
                continue  # the same glyph drawn twice
            seen.add(key)
            if (font, gid) in repairs:
                rule = repairs[(font, gid)]
                text, status = rule.text, "repair:" + rule.role
            else:
                text, status = resolve_glyph_text(fm, pno, font, gid)
                if text is None:
                    text = REPLACEMENT
            if text == " ":
                status = "space"
            glyphs.append(Glyph(pno, seq, font, gid, uni, text, float(bbox[0]), float(bbox[1]), float(bbox[2]),
                                float(bbox[3]), float(origin[0]), float(origin[1]), size, int(span["bidi_lvl"]), status))
    _drop_continuations(glyphs)
    _compose_hamza(glyphs, settings)
    _drop_tails(glyphs, settings)
    return glyphs


def _drop_continuations(glyphs: list[Glyph]) -> None:
    """A zero-width glyph with id -1 right after a multi-character glyph is the
    text trace's continuation of that ligature: its letter is already in the
    ligature's text."""
    for i, g in enumerate(glyphs):
        if g.gid == -1 and g.is_zero_width and i > 0:
            prev = glyphs[i - 1]
            if len(prev.text) >= 2 and chr(g.raw_uni) in prev.text[1:]:
                g.text = ""
                g.status = "drop:ligature_continuation"
                g.note = f"continuation of gid {prev.gid} {prev.text!r}"
            elif g.unresolved:
                g.note = "zero-width glyph without id"


def _compose_hamza(glyphs: list[Glyph], settings: ReaderSettings) -> None:
    """Compose a zero-width hamza-letter glyph with the alef (or lam-alef) at its position."""
    carriers = {t for texts in HAMZA_CARRIERS.values() for t in texts}
    candidates = [g for g in glyphs if not g.is_zero_width and g.text in carriers]
    for g in glyphs:
        if g.is_zero_width and g.text in HAMZA_LETTERS and not g.dropped:
            partner, best = None, None
            for b in candidates:
                if b.status == "compose" or b.text not in HAMZA_CARRIERS[g.text] or abs(b.oy - g.oy) > max(1.0, 0.3 * g.size):
                    continue
                d = abs(b.x0 - g.x0)
                if d <= settings.hamza_x_tolerance and (best is None or d < best):
                    best, partner = d, b
            if partner is not None:
                partner.text = LAM_ALEF_WITH_HAMZA[g.text] if partner.text == "لا" else g.text
                partner.status = "compose"
                partner.note = f"hamza letter from glyph {g.seq} (gid {g.gid})"
                g.text = ""
                g.status = "drop:hamza_mark"
                g.note = f"composed into glyph {partner.seq} (gid {partner.gid})"
            else:
                g.status = "unresolved:hamza_without_body"


def _drop_tails(glyphs: list[Glyph], settings: ReaderSettings) -> None:
    """A tail glyph carries no letter of its own when a head glyph touches its right edge."""
    heads = [g for g in glyphs if g.status == "repair:head"]
    for g in glyphs:
        if g.status == "repair:tail":
            touching = [h for h in heads if abs(h.oy - g.oy) < 1.0 and abs(h.x0 - g.x1) <= settings.head_tail_tolerance]
            if touching:
                g.text = ""
                g.status = "drop:tail"
                g.note = f"tail of head gid {touching[0].gid}"
            else:
                g.status = "unresolved:tail_without_head"


# ----------------------------------------------------------------------------
# Lines
# ----------------------------------------------------------------------------


@dataclass
class Line:
    page: int
    glyphs: list[Glyph]  # logical order, marks included
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    baseline: float
    size: float
    fonts: dict[str, int] = field(default_factory=dict)
    unresolved: int = 0
    gap_spaces: int = 0  # spaces inserted from geometry (no explicit space glyph)
    cell: tuple[int, int] | None = None

    @property
    def bold_ratio(self) -> float:
        total = sum(self.fonts.values()) or 1
        return sum(n for f, n in self.fonts.items() if "bold" in f.lower()) / total

    @property
    def xmid(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def ymid(self) -> float:
        return (self.y0 + self.y1) / 2


def _cluster_baselines(bases: list[Glyph], tol_ratio: float) -> list[list[Glyph]]:
    bases = sorted(bases, key=lambda g: g.oy)
    clusters: list[list[Glyph]] = []
    for g in bases:
        if clusters and abs(clusters[-1][-1].oy - g.oy) <= max(1.2, tol_ratio * g.size):
            clusters[-1].append(g)
        else:
            clusters.append([g])
    return clusters


def _is_word_glyph(g: Glyph) -> bool:
    t = g.text.strip()
    return bool(t) and (t[-1].isalnum() or t[-1] in COMBINING_MARKS)


def _is_digit_glyph(g: Glyph) -> bool:
    return g.text != "" and all(c in DIGITS for c in western_digits(g.text))


def _line_tokens(cluster: list[Glyph], settings: ReaderSettings) -> list[Glyph | None]:
    """Right-to-left glyph order with None where a space must be inserted, then
    digit runs (optionally joined by the configured joiners) restored to reading order."""
    ordered = sorted(cluster, key=lambda g: (-g.x1, -g.x0, g.seq))
    tokens: list[Glyph | None] = []
    prev: Glyph | None = None
    for g in ordered:
        if prev is not None and g.text != " " and prev.text != " ":
            gap = prev.x0 - g.x1
            # typographic spacing around punctuation is not a word space: a space is inserted from
            # geometry only between two word glyphs (letters or digits)
            if gap > settings.space_gap_ratio * max(g.size, prev.size) and _is_word_glyph(g) and _is_word_glyph(prev):
                tokens.append(None)
        if g.text != "":
            tokens.append(g)
        prev = g
    # restore digit runs: a run is digits, with joiner characters allowed between digits
    out: list[Glyph | None] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t is not None and _is_digit_glyph(t):
            j = i
            while j < len(tokens):
                u = tokens[j]
                if u is not None and _is_digit_glyph(u):
                    j += 1
                elif (u is not None and u.text in settings.digit_run_joiners and j + 1 < len(tokens)
                      and tokens[j + 1] is not None and _is_digit_glyph(tokens[j + 1])):
                    j += 1
                else:
                    break
            out.extend(reversed(tokens[i:j]))
            i = j
        else:
            out.append(t)
            i += 1
    return out


def _attach_marks(cluster: list[Glyph], marks: list[Glyph]) -> dict[int, list[Glyph]]:
    attached: dict[int, list[Glyph]] = {}
    for m in marks:
        best, best_d = None, None
        mx = m.ox if m.is_zero_width else (m.x0 + m.x1) / 2
        letters = [b for b in cluster if b.text not in ("", " ") and any("\u0600" <= c <= "\u06ff" for c in b.text)]
        for margin in (0.0, 0.5):
            for b in letters or [b for b in cluster if b.text not in ("", " ")]:
                if b.x0 - margin * b.size <= mx <= b.x1 + margin * b.size:
                    d = abs(((b.x0 + b.x1) / 2) - mx)
                    if best is None or d < best_d:
                        best, best_d = b, d
            if best is not None:
                break
        if best is None:
            m.status = "unresolved:mark_without_base"
            continue
        m.status = "mark"
        attached.setdefault(best.seq, []).append(m)
    return attached


def form_lines(glyphs: list[Glyph], settings: ReaderSettings | None = None, cell: tuple[int, int] | None = None) -> list[Line]:
    """Group glyphs (of one cell, or of the whole page) into lines and produce logical-order text."""
    settings = settings or ReaderSettings()
    if glyphs:
        settings = settings.for_page(glyphs[0].page)
    live = [g for g in glyphs if (not g.dropped and g.text != "") or g.status == "drop:tail"]
    bases = [g for g in live if not g.is_mark]  # silent tail glyphs stay for the gap computation
    marks = [g for g in live if g.is_mark]
    clusters = _cluster_baselines(bases, settings.baseline_tolerance_ratio)
    baselines = [sum(g.oy for g in c) / len(c) for c in clusters]
    # each mark goes to the line whose baseline is nearest to the mark's origin
    cluster_marks: dict[int, list[Glyph]] = {}
    for m in marks:
        if not baselines:
            m.status = "unresolved:mark_outside_lines"
            continue
        my = m.oy
        k = min(range(len(baselines)), key=lambda i: abs(baselines[i] - my))
        if abs(baselines[k] - my) > 1.2 * m.size:
            m.status = "unresolved:mark_outside_lines"
            continue
        cluster_marks.setdefault(k, []).append(m)
    lines: list[Line] = []
    for k, cluster in enumerate(clusters):
        attached = _attach_marks(cluster, cluster_marks.get(k, []))
        pieces: list[str] = []
        logical: list[Glyph] = []
        gap_spaces = 0
        for t in _line_tokens(cluster, settings):
            if t is None:
                pieces.append(" ")
                gap_spaces += 1
                continue
            pieces.append(t.text)
            logical.append(t)
            for m in attached.get(t.seq, []):
                pieces.append(m.text)
                logical.append(m)
        text = re.sub(r"[  ]+", " ", "".join(pieces)).strip()
        fonts: dict[str, int] = {}
        for g in cluster:
            if g.text != " ":
                fonts[g.font] = fonts.get(g.font, 0) + 1
        unresolved = sum(1 for g in logical if g.unresolved) + sum(1 for m in cluster_marks.get(k, []) if m.unresolved)
        lines.append(Line(cluster[0].page, logical, normalize_text(text), min(g.x0 for g in cluster), min(g.y0 for g in cluster),
                          max(g.x1 for g in cluster), max(g.y1 for g in cluster), baselines[k], max(g.size for g in cluster),
                          fonts, unresolved, gap_spaces, cell))
    lines.sort(key=lambda l: (l.baseline, -l.x1))
    return lines


# ----------------------------------------------------------------------------
# Rulings and table geometry
# ----------------------------------------------------------------------------


@dataclass
class Ruling:
    page: int
    orientation: str  # h | v
    pos: float  # y for horizontal, x for vertical
    start: float
    end: float
    dashed: bool
    width: float
    color: tuple


def _is_white(color) -> bool:
    return color is not None and all(c >= 0.98 for c in color)


def page_rulings(page: pymupdf.Page, min_len: float = 20.0) -> list[Ruling]:
    """Visible (non-white) straight strokes long enough to be table rulings."""
    rulings: list[Ruling] = []
    pno = page.number + 1
    for d in page.get_drawings():
        color = d.get("color")
        if color is None or _is_white(color):
            continue
        dashes = d.get("dashes")
        dashed = bool(dashes) and dashes.strip() not in ("[] 0", "[]0", "[ ] 0")
        width = float(d.get("width") or 0.0)
        for item in d["items"]:
            kind = item[0]
            if kind == "l":
                p1, p2 = item[1], item[2]
                if abs(p1.y - p2.y) < 0.6 and abs(p1.x - p2.x) >= min_len:
                    rulings.append(Ruling(pno, "h", (p1.y + p2.y) / 2, min(p1.x, p2.x), max(p1.x, p2.x), dashed, width, tuple(color)))
                elif abs(p1.x - p2.x) < 0.6 and abs(p1.y - p2.y) >= min_len:
                    rulings.append(Ruling(pno, "v", (p1.x + p2.x) / 2, min(p1.y, p2.y), max(p1.y, p2.y), dashed, width, tuple(color)))
            elif kind == "re":
                r = item[1]
                if r.height < 1.5 and r.width >= min_len:
                    rulings.append(Ruling(pno, "h", (r.y0 + r.y1) / 2, r.x0, r.x1, dashed, r.height, tuple(color)))
                elif r.width < 1.5 and r.height >= min_len:
                    rulings.append(Ruling(pno, "v", (r.x0 + r.x1) / 2, r.y0, r.y1, dashed, r.width, tuple(color)))
    return rulings


def merge_rulings(rulings: list[Ruling], tol: float = 1.5) -> list[Ruling]:
    """Merge collinear segments; a merged rule is dashed when any piece is dashed."""
    out: list[Ruling] = []
    for orient in ("h", "v"):
        segs = sorted([r for r in rulings if r.orientation == orient], key=lambda r: (r.pos, r.start))
        groups: list[list[Ruling]] = []
        for r in segs:
            if groups and abs(groups[-1][0].pos - r.pos) <= tol:
                groups[-1].append(r)
            else:
                groups.append([r])
        for grp in groups:
            grp.sort(key=lambda r: r.start)
            cur = None
            for r in grp:
                if cur is not None and r.start <= cur.end + 3 * tol:
                    cur.end = max(cur.end, r.end)
                    cur.dashed = cur.dashed or r.dashed
                else:
                    cur = Ruling(r.page, orient, grp[0].pos, r.start, r.end, r.dashed, r.width, r.color)
                    out.append(cur)
    return out


@dataclass
class Cell:
    page: int
    row: int
    col: int
    x0: float
    y0: float
    x1: float
    y1: float
    glyphs: list[Glyph] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)

    @property
    def text_lines(self) -> list[str]:
        return [l.text for l in self.lines]


@dataclass
class Row:
    page: int
    index: int
    y0: float
    y1: float
    dashed_top: bool
    cells: list[Cell]
    full_width: bool


@dataclass
class Table:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    column_bounds: list[float]  # x positions of the vertical rules, left to right
    rows: list[Row]
    outside: list[Line] = field(default_factory=list)  # lines outside the frame (page furniture)


def segment_table(page_no: int, rulings: list[Ruling], glyphs: list[Glyph], settings: ReaderSettings | None = None,
                  min_row_height: float = 4.0) -> Table | None:
    """Build rows and cells from the rulings, assign every glyph inside the frame
    to a cell, and form lines per cell.  Columns are numbered right to left
    (column 0 is the rightmost), matching the source's reading order."""
    settings = settings or ReaderSettings()
    hs = sorted([r for r in rulings if r.orientation == "h"], key=lambda r: r.pos)
    vs = sorted([r for r in rulings if r.orientation == "v"], key=lambda r: r.pos)
    if len(hs) < 2 or len(vs) < 2:
        return None
    x0 = min(r.start for r in hs)
    x1 = max(r.end for r in hs)
    y0 = hs[0].pos
    y1 = hs[-1].pos
    col_x: list[float] = []
    for v in vs:
        if not col_x or abs(col_x[-1] - v.pos) > 2.0:
            col_x.append(v.pos)
    rows: list[Row] = []
    for i in range(len(hs) - 1):
        top, bottom = hs[i], hs[i + 1]
        if bottom.pos - top.pos < min_row_height:
            continue
        inner = [x for x in col_x[1:-1] if any(abs(v.pos - x) <= 2.0 and v.start <= top.pos + 2 and v.end >= bottom.pos - 2 for v in vs)]
        bounds = [col_x[0]] + inner + [col_x[-1]]
        spans = list(zip(bounds[:-1], bounds[1:]))[::-1]
        cells = [Cell(page_no, len(rows), ci, cx0, top.pos, cx1, bottom.pos) for ci, (cx0, cx1) in enumerate(spans)]
        rows.append(Row(page_no, len(rows), top.pos, bottom.pos, top.dashed, cells, not inner))
    outside: list[Glyph] = []
    for g in glyphs:
        if g.dropped or g.text == "":
            continue
        gx = g.ox if g.is_zero_width else (g.x0 + g.x1) / 2
        gy = g.oy
        placed = False
        if x0 - 2 <= gx <= x1 + 2 and y0 - 1 <= gy <= y1 + 1:
            for row in rows:
                if row.y0 - 0.5 <= gy <= row.y1 + 0.5:
                    for cell in row.cells:
                        if cell.x0 - 0.5 <= gx <= cell.x1 + 0.5:
                            cell.glyphs.append(g)
                            g.cell = (row.index, cell.col)
                            placed = True
                            break
                    break
        if not placed:
            outside.append(g)
    for row in rows:
        for cell in row.cells:
            cell.lines = form_lines(cell.glyphs, settings, (row.index, cell.col))
    table = Table(page_no, x0, y0, x1, y1, col_x, rows, form_lines(outside, settings))
    return table


# ----------------------------------------------------------------------------
# Rendering helpers (crops for calibration and review)
# ----------------------------------------------------------------------------


def render_crop(doc: pymupdf.Document, pno: int, rect, path, dpi: int = 300, pad: float = 2.0) -> None:
    page = doc[pno - 1]
    clip = pymupdf.Rect(rect[0] - pad, rect[1] - pad, rect[2] + pad, rect[3] + pad) & page.rect
    page.get_pixmap(dpi=dpi, clip=clip).save(str(path))


def render_page(doc: pymupdf.Document, pno: int, path, dpi: int = 150) -> None:
    doc[pno - 1].get_pixmap(dpi=dpi).save(str(path))
