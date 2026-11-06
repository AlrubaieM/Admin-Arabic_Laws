"""Index-page parser: turns the segmented tables of an index file into records.

Page classes, row classes and entry blocks follow the master prompt, section 5
(INDEX FILES).  Every source line receives exactly one class so that the
coverage check (section 14) can account for it; every exclusion (page
furniture, images, drawings) is logged per page.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pymupdf

import pdf_source as ps

# Arabic ordinals as sub-topic labels: simple (أولاً … عاشراً), compound (حادي عشر … تاسع عشر) and tens
# (العشرون، الحادي والعشرون …), with or without the article and tanween, followed by «/» or «:» as printed
_ORD_UNIT = r"(?:أول|ثان|ثالث|رابع|خامس|سادس|سابع|ثامن|تاسع|عاشر|حادي)(?:اً|ًا|ا|ياً|يًا|يا|ي)?"
_ORD_TENS = r"(?:عشر|ثلاث|أربع|خمس|ست|سبع|ثمان|تسع)(?:ون|ين)"  # العشرون / وعشرين …
_ORD = rf"(?:(?:ال)?{_ORD_UNIT}(?:\s+عشر(?:اً|ًا|ا)?|\s+و\s*(?:ال)?{_ORD_TENS})?|(?:ال)?{_ORD_TENS})"
RE_ORDINAL_LINE = re.compile(rf"^(?P<ord>{_ORD})\s*(?P<sep>[/:])\s*(?P<rest>.*)$")
RE_LETTER = re.compile(r"^حرف\s*\(\s*(?P<letter>[ء-يـ]{1,2})\s*\)\s*:?\s*$")  # «حرف (أ)» or «حرف (أ):»
RE_HEADER = {"المبدأ", "الرقم", "ص"}
# a ruling reference: (prefix/number/year); the prefix is one letter, or two letters joined by «/» («د/س»), and the
# number may follow the prefix after «/», a space, or directly («(أ/س2272/1437)»)
RE_REF = re.compile(r"\(\s*(?P<prefix>[ء-ي]ـ?(?:\s*/\s*[ء-ي]ـ?)?)\s*(?:/\s*|\s+)?(?P<num>[0-9]+(?:-[0-9]+)?)\s*/\s*(?P<year>[0-9]{3,4})\s*\)")
RE_SEE_ALSO = re.compile(r"^راجع\s*:")
RE_NUMBER_LIST = re.compile(r"^[0-9]+(?:\s*،\s*[0-9]+)*\s*،?\s*$")
BULLET = "•"
# an index cell is one paragraph: a semicolon or comma at a line end is a layout wrap (revision of 03/11/2026)
SENTENCE_END = set(".:!؟")
PAGE_CLASSES = {"cover", "cataloging", "basmala", "half_title", "divider", "blank", "index_summary", "index_detailed", "principle", "other"}


@dataclass
class SourceLine:
    page: int
    row: int | None
    col: int | None
    k: int
    text: str
    bold: float
    gap_spaces: int
    unresolved: int
    cls: str = "unclassified"
    note: str = ""
    tatweel_removed: int = 0

    @property
    def loc(self) -> str:
        if self.row is None:
            return f"page[{self.page}]:L{self.k}"
        return f"page[{self.page}]:r{self.row}:c{self.col}:L{self.k}"


@dataclass
class RulingRef:
    ref_ar: str
    prefix_ar: str
    number: str
    year_hijri: str
    loc: str


@dataclass
class Hierarchy:
    letter: str | None = None
    letter_label: str | None = None
    topic: str | None = None
    subtopic_label: str | None = None
    subtopic_title: str | None = None


@dataclass
class EntryBlock:
    """One block of the detailed index (a facet of one or more principles)."""

    page: int
    row: int
    kind: str  # entry | sibling | continuation | see_also
    hierarchy: Hierarchy
    opener_lines: list[SourceLine] = field(default_factory=list)
    title_lines: list[SourceLine] = field(default_factory=list)
    wording_lines: list[SourceLine] = field(default_factory=list)
    reference_lines: list[SourceLine] = field(default_factory=list)
    number_lines: list[SourceLine] = field(default_factory=list)
    label_lines: list[SourceLine] = field(default_factory=list)
    title_ar: str | None = None
    title_basis: str = "none"
    wording_paragraphs: list[str] = field(default_factory=list)
    wrap_joins: list[str] = field(default_factory=list)
    reference_separations: list[str] = field(default_factory=list)  # wording lines whose trailing reference was separated
    references: list[RulingRef] = field(default_factory=list)
    numbers: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    see_also_text: str | None = None
    continues_block: int | None = None  # index of the block whose title this one shares
    issues: list[str] = field(default_factory=list)

    @property
    def loc(self) -> str:
        return f"page[{self.page}]:r{self.row}"


@dataclass
class TopicRecord:
    letter: str
    letter_label: str
    title_ar: str
    page: int
    row: int
    outline: list[str] = field(default_factory=list)
    outline_locs: list[str] = field(default_factory=list)
    title_loc: str = ""
    subtopics: list[dict] = field(default_factory=list)  # {label, title, loc}


@dataclass
class LetterRecord:
    letter: str
    label: str
    page: int
    row: int
    loc: str
    topics: list[TopicRecord] = field(default_factory=list)


@dataclass
class IndexParse:
    file: str
    page_classes: dict[int, str]
    lines: list[SourceLine]
    letters: list[LetterRecord]
    blocks: list[EntryBlock]
    summary_rows: list[dict]  # {page, row, letter_label, topics_text, locs}
    detailed_tables: dict[int, list[list[list[str]]]]  # page -> rows -> cells -> lines
    summary_tables: dict[int, list[list[list[str]]]]
    page_labels: dict[int, str]
    issues: list[dict]
    glyph_status: dict[str, int] = field(default_factory=dict)
    unresolved_glyphs: list = field(default_factory=list)
    page_apparatus: dict[int, dict] = field(default_factory=dict)  # per page: images, drawings, bands
    font_objects: list[dict] = field(default_factory=list)
    summary_coverage: dict = field(default_factory=dict)  # letters fully/partially covered by the detailed pages
    tatweel_removed: int = 0
    # other ruled index tables of the file (rulings, decisions, instruments indexes), read verbatim:
    # [{page, headings: [text], header: [cell text] | None, rows: [[cell text]], row_locs: [loc]}]
    table_pages: list[dict] = field(default_factory=list)


def _strip_bullet(text: str) -> str:
    t = text.strip()
    if t.startswith(BULLET):
        t = t[1:].strip()
    return t


# a title marker: the bullet, or a dash (hyphen or en dash) followed by a space
RE_TITLE_MARKER = re.compile(r"^\s*(?:•|[-–]\s)")
TITLE_MAX_LINES = 4  # a title wraps over at most this many lines before its closing colon


def _strip_marker(text: str) -> str:
    return re.sub(r"^\s*(?:•|[-–])\s*", "", text).strip()


def _ends_with_colon(text: str) -> bool:
    return text.rstrip().endswith(":")


def classify_page(table: ps.Table | None, lines: list[ps.Line], declared: str | None = None, has_images: bool = False,
                  has_drawings: bool = False) -> str:
    """Page class of the fixed vocabulary (master prompt, section 5).  A page without
    a text layer (only a hidden folio at most) takes the class declared for it in the
    configuration, checked against what the page carries: a cover, half-title or
    divider must carry an image or a drawing, a blank page neither."""
    texts = [l.text for l in lines]
    if table is not None and not any(c.lines for r in table.rows for c in r.cells):
        table = None  # a ruled frame with no text in any cell (e.g. an empty box left by an editor) is a drawing
    if table is None:
        if any("رقم الإيداع" in t or "ردمك" in t for t in texts):
            return "cataloging"
        if all(t.isdigit() for t in texts):
            if declared in ("cover", "basmala", "half_title", "divider") and (has_images or has_drawings):
                return declared
            if declared == "blank" and not (has_images or has_drawings):
                return declared
            if declared is None and not texts and not has_images and not has_drawings:
                return "blank"
            return "other"
        return "other"
    first_cells = [c.text_lines for r in table.rows[:1] for c in r.cells]
    header = {t for cell in first_cells for t in cell}
    if header & RE_HEADER and len(header & RE_HEADER) >= 2:
        return "index_detailed"
    if table.rows and all(len(r.cells) == 2 for r in table.rows) and all(
        any(RE_LETTER.match(t) for t in r.cells[0].text_lines) for r in table.rows if any(c.lines for c in r.cells)
    ):
        return "index_summary"
    entry_rows = [r for r in table.rows if len(r.cells) == 3 and r.cells[1].lines]
    if entry_rows and all(RE_NUMBER_LIST.match(" ".join(r.cells[1].text_lines)) for r in entry_rows):
        return "index_detailed"
    if any("رقم الإيداع" in t or "ردمك" in t for t in texts):
        return "cataloging"
    filled = [r for r in table.rows if sum(1 for c in r.cells if c.lines) >= 2]
    if len(filled) >= 2:
        return "index_table"  # another ruled index of the file (rulings, decisions, instruments): read verbatim
    return "other"


def _page_apparatus(page: pymupdf.Page, table: ps.Table | None) -> dict:
    """Images and non-ruling drawings of a page, classed by position (header band, footer band, body)."""
    h = page.rect.height
    images = []
    for info in page.get_images(full=True):
        for r in page.get_image_rects(info[0]):
            images.append({"bbox": [round(r.x0, 1), round(r.y0, 1), round(r.x1, 1), round(r.y1, 1)], "band": _band(r, h, table)})
    drawings = 0
    bands = {"header": 0, "footer": 0, "body": 0}
    for d in page.get_drawings():
        r = d.get("rect")
        if r is None:
            continue
        if table is not None and table.y0 - 2 <= r.y0 and r.y1 <= table.y1 + 2 and (r.width < 1.5 or r.height < 1.5):
            continue  # a table ruling
        drawings += 1
        bands[_band(r, h, table)] += 1
    out = {"images": images, "drawings": drawings, "drawing_bands": bands}
    off_page = ps.off_page_glyphs(page)
    if off_page:
        out["glyphs_outside_page"] = off_page  # text drawn beyond the visible page box: not read
    return out


def _band(r, page_height: float, table: ps.Table | None) -> str:
    if table is not None:
        if r.y1 <= table.y0 + 1:
            return "header"
        if r.y0 >= table.y1 - 1:
            return "footer"
        return "body"
    if r.y1 <= 0.2 * page_height:
        return "header"
    if r.y0 >= 0.85 * page_height:
        return "footer"
    return "body"


def last_block_of_page(blocks: list, pno: int):
    """The last block of detailed page `pno`, or None when the page produced no block: a continuation
    at the top of the next page continues only a block of the page just before it."""
    return blocks[-1] if blocks and blocks[-1].page == pno else None


def parse_index_file(doc: pymupdf.Document, file_name: str, fm: ps.FontMaps, repairs, settings: ps.ReaderSettings,
                     page_label_offset: int | None, declared_classes: dict[int, str] | None = None) -> IndexParse:
    declared_classes = declared_classes or {}
    glyph_status: dict[str, int] = {}
    unresolved_glyphs: list = []
    page_classes: dict[int, str] = {}
    page_apparatus: dict[int, dict] = {}
    all_lines: list[SourceLine] = []
    letters: list[LetterRecord] = []
    blocks: list[EntryBlock] = []
    summary_rows: list[dict] = []
    detailed_tables: dict[int, list] = {}
    summary_tables: dict[int, list] = {}
    table_pages: list[dict] = []
    page_labels: dict[int, str] = {}
    issues: list[dict] = []
    hier = Hierarchy()
    current_topic: TopicRecord | None = None
    last_block_prev_page: EntryBlock | None = None
    tatweel_total = 0

    def issue(kind: str, loc: str, text: str, note: str = "", options: list[str] | None = None) -> None:
        issues.append({"issue_type": kind, "location": loc, "observed": text, "note": note, "options": options or []})

    def source_line(pno: int, row: int | None, col: int | None, k: int, l: ps.Line, cls: str = "unclassified") -> SourceLine:
        nonlocal tatweel_total
        tatweel_total += l.tatweel_removed
        return SourceLine(pno, row, col, k, l.text, l.bold_ratio, l.gap_spaces, l.unresolved, cls, "", l.tatweel_removed)

    for pno in range(1, len(doc) + 1):
        page = doc[pno - 1]
        glyphs = ps.page_glyphs(doc, pno, fm, repairs, settings)
        for g in glyphs:
            key = g.status if g.status.startswith("drop") else g.status.split(":")[0]
            glyph_status[key] = glyph_status.get(key, 0) + 1
            if g.unresolved:
                unresolved_glyphs.append(g)
        rulings = ps.merge_rulings(ps.page_rulings(page))
        table = ps.segment_table(pno, rulings, glyphs, settings)
        page_lines = table.outside if table is not None else ps.form_lines(glyphs, settings)
        cls = classify_page(table, page_lines if table is None else [l for r in table.rows for c in r.cells for l in c.lines] + table.outside,
                            declared_classes.get(pno), bool(page.get_images()), bool(page.get_drawings()))
        page_classes[pno] = cls
        page_apparatus[pno] = _page_apparatus(page, table)
        if cls == "other":
            issue("other", f"page[{pno}]", "", "page class could not be established; declare it in the configuration (page_classes)")
        for k, l in enumerate(page_lines):
            sl = source_line(pno, None, None, k, l)
            if l.text.isdigit():
                sl.cls = "apparatus:page_number" if cls.startswith("index") else "apparatus:hidden_folio"
                if cls.startswith("index"):
                    page_labels[pno] = l.text
                    if page_label_offset is not None and int(l.text) != pno - int(page_label_offset):
                        issue("number", sl.loc, l.text, f"printed page label does not equal the physical page minus the configured offset {page_label_offset}")
            elif cls == "cataloging":
                sl.cls = "cataloging_text"
            elif cls in ("blank", "cover", "basmala", "half_title", "divider"):
                sl.cls = "apparatus:" + cls
            elif cls == "index_table":
                sl.cls = "table_heading"  # a section heading printed above the table (e.g. «ثانياً/ الأحكام الصادرة في الاعتراضات»)
                if l.unresolved or "�" in l.text:
                    sl.cls = "review"
                    issue("glyph", sl.loc, l.text, "table heading with an unresolved glyph; not published until the glyph is repaired",
                          ["repair the glyph in the configuration"])
            else:
                sl.cls = "review"
                issue("other", sl.loc, l.text, "line outside any table on a page of class " + cls)
            all_lines.append(sl)
        if table is None:
            continue
        if cls == "cataloging":
            for r in table.rows:
                for c in r.cells:
                    for k, l in enumerate(c.lines):
                        all_lines.append(source_line(pno, r.index, c.col, k, l, "cataloging_text"))
            continue
        if cls == "index_table":
            # verbatim: every cell's lines joined as one paragraph (a cell is one paragraph, section 4), in column
            # order right to left; the first row is the column header when none of its cells holds a digit
            headings = [l.text for l in page_lines if l.text and not l.text.isdigit() and not (l.unresolved or "�" in l.text)]
            rows = [r for r in table.rows if any(c.lines for c in r.cells)]
            header = None
            if rows and not any(re.search(r"[0-9]", " ".join(c.text_lines)) for c in rows[0].cells):
                header = rows[0]
                if any(l.unresolved or "�" in l.text for c in header.cells for l in c.lines):
                    header = None  # held with the rows below: a header with an unresolved glyph is never published
            cells_rows, row_locs = [], []
            for r in rows:
                cls_r = "table_header" if r is header else "table_cell"
                if any(l.unresolved or "�" in l.text for c in r.cells for l in c.lines):
                    # held like a principle: a row is never published with an unresolved glyph
                    for c in r.cells:
                        for k, l in enumerate(c.lines):
                            all_lines.append(source_line(pno, r.index, c.col, k, l, "review"))
                    issue("glyph", f"page[{pno}]:r{r.index}", " | ".join(" ".join(c.text_lines) for c in r.cells),
                          "table row with an unresolved glyph; not published until the glyph is repaired", ["repair the glyph in the configuration"])
                    continue
                texts = []
                for c in sorted(r.cells, key=lambda c: c.col):
                    for k, l in enumerate(c.lines):
                        all_lines.append(source_line(pno, r.index, c.col, k, l, cls_r))
                    texts.append(" ".join(l.text for l in c.lines).strip())
                if r is not header:
                    cells_rows.append(texts)
                    row_locs.append(f"page[{pno}]:r{r.index}")
            table_pages.append({"page": pno, "headings": headings,
                                "header": [" ".join(c.text_lines).strip() for c in sorted(header.cells, key=lambda c: c.col)] if header else None,
                                "rows": cells_rows, "row_locs": row_locs})
            continue
        if cls == "index_summary":
            summary_tables[pno] = [[c.text_lines for c in r.cells] for r in table.rows]
            for r in table.rows:
                cells = r.cells
                for c in cells:
                    for k, l in enumerate(c.lines):
                        all_lines.append(source_line(pno, r.index, c.col, k, l, "summary_letter" if c.col == 0 else "summary_topics"))
                if len(cells) >= 2 and (cells[0].lines or cells[1].lines):
                    summary_rows.append({"page": pno, "row": r.index, "letter_label": " ".join(cells[0].text_lines),
                                         "topics_text": " ".join(cells[1].text_lines),
                                         "locs": [f"page[{pno}]:r{r.index}:c0", f"page[{pno}]:r{r.index}:c1"]})
            continue
        if cls != "index_detailed":
            for r in table.rows:
                for c in r.cells:
                    for k, l in enumerate(c.lines):
                        sl = source_line(pno, r.index, c.col, k, l, "review")
                        all_lines.append(sl)
                        issue("other", sl.loc, l.text, "table line on a page of class " + cls)
            continue
        # ---------------- detailed index page ----------------
        detailed_tables[pno] = [[c.text_lines for c in r.cells] for r in table.rows]
        first_entry_on_page = True
        for r in table.rows:
            if not any(c.lines for c in r.cells):
                continue
            texts0 = r.cells[0].text_lines
            if r.index == 0 and set(texts0) <= RE_HEADER and texts0:
                for c in r.cells:
                    for k, l in enumerate(c.lines):
                        all_lines.append(source_line(pno, r.index, c.col, k, l, "header_row"))
                continue
            if r.full_width:
                first_entry_on_page = False  # a titleless block after a letter or topic row is not a continuation
                for k, l in enumerate(r.cells[0].lines):
                    sl = source_line(pno, r.index, 0, k, l)
                    m = RE_LETTER.match(l.text)
                    if m:
                        sl.cls = "letter"
                        hier = Hierarchy(letter=m.group("letter"), letter_label=l.text)
                        current_topic = None
                        letters.append(LetterRecord(m.group("letter"), l.text, pno, r.index, sl.loc))
                    elif RE_ORDINAL_LINE.match(l.text) and current_topic is not None:
                        sl.cls = "outline"
                        current_topic.outline.append(l.text)
                        current_topic.outline_locs.append(sl.loc)
                    else:
                        sl.cls = "topic"
                        if hier.letter is None:
                            issue("boundary", sl.loc, l.text, "topic row before any letter row")
                            hier = Hierarchy(letter="?", letter_label="?")
                            letters.append(LetterRecord("?", "?", pno, r.index, sl.loc))
                        current_topic = TopicRecord(hier.letter, hier.letter_label, l.text, pno, r.index, title_loc=sl.loc)
                        letters[-1].topics.append(current_topic)
                        hier = Hierarchy(letter=hier.letter, letter_label=hier.letter_label, topic=l.text)
                    all_lines.append(sl)
                continue
            c0, c1, c2 = r.cells[0], (r.cells[1] if len(r.cells) > 1 else None), (r.cells[2] if len(r.cells) > 2 else None)
            lines0 = [source_line(pno, r.index, 0, k, l) for k, l in enumerate(c0.lines)]
            block = EntryBlock(pno, r.index, "entry", Hierarchy(**vars(hier)))
            i = 0
            if i < len(lines0) and RE_ORDINAL_LINE.match(lines0[i].text):
                j = i
                while j < len(lines0) and not _ends_with_colon(lines0[j].text):
                    j += 1
                if j < len(lines0):
                    for q in range(i, j + 1):
                        lines0[q].cls = "subtopic_opener"
                        block.opener_lines.append(lines0[q])
                    opener = " ".join(l.text for l in lines0[i:j + 1]).rstrip().rstrip(":").strip()
                    m = RE_ORDINAL_LINE.match(opener)
                    block.hierarchy.subtopic_label = m.group("ord") + m.group("sep")
                    block.hierarchy.subtopic_title = m.group("rest").strip()
                    hier = Hierarchy(**vars(block.hierarchy))
                    if current_topic is not None:
                        current_topic.subtopics.append({"label": block.hierarchy.subtopic_label, "title": block.hierarchy.subtopic_title, "loc": lines0[i].loc})
                    i = j + 1
                else:
                    issue("boundary", lines0[i].loc, lines0[i].text, "ordinal line without a closing colon")
            bullet_wording = False
            if i < len(lines0) and RE_TITLE_MARKER.match(lines0[i].text):
                # a title: a marker line («•», «-», «–») in the title font whose run ends with «:» within a few lines;
                # otherwise a «•» opens the wording itself (layouts that print each principle as a bullet paragraph)
                j = i
                # a one-line title ends with its own colon (any weight); a wrapped title is in the title font throughout
                one_line = _ends_with_colon(lines0[i].text)
                while not one_line and j < len(lines0) and j - i < TITLE_MAX_LINES and lines0[j].bold >= 0.5 and not _ends_with_colon(lines0[j].text):
                    j += 1
                if one_line or (j < len(lines0) and j - i < TITLE_MAX_LINES and lines0[j].bold >= 0.5 and lines0[i].bold >= 0.5
                                and _ends_with_colon(lines0[j].text)):
                    for q in range(i, j + 1):
                        lines0[q].cls = "title"
                        block.title_lines.append(lines0[q])
                    title = " ".join(_strip_marker(l.text) if q == i else l.text for q, l in enumerate(lines0[i:j + 1], start=i))
                    block.title_ar = title.rstrip().rstrip(":").strip()  # wraps joined by one space; spacing within a line as printed
                    block.title_basis = "bullet_title"
                    i = j + 1
                elif lines0[i].text.lstrip().startswith(BULLET):
                    bullet_wording = True
            if block.title_ar is None and block.hierarchy.subtopic_title and (block.opener_lines or bullet_wording):
                block.title_ar = block.hierarchy.subtopic_title
                block.title_basis = "subtopic_line"
            for sl in lines0[i:]:
                if RE_REF.fullmatch(sl.text.strip()) or (RE_REF.search(sl.text) and not RE_REF.sub("", sl.text).strip()):
                    sl.cls = "ruling_reference"
                    block.reference_lines.append(sl)
                else:
                    sl.cls = "index_wording"
                    block.wording_lines.append(sl)
            for sl in block.wording_lines + block.reference_lines:
                for m in RE_REF.finditer(sl.text):
                    block.references.append(RulingRef(m.group(0).strip(), re.sub(r"\s+", "", m.group("prefix")), m.group("num"), m.group("year"), sl.loc))
            # wording paragraphs: separate trailing references (logged), join layout wraps
            paragraphs: list[str] = []
            prev_had_reference = False
            for sl in block.wording_lines:
                had_ref = bool(RE_REF.search(sl.text))
                t = RE_REF.sub("", sl.text).rstrip()
                if had_ref:
                    block.reference_separations.append(sl.loc)
                if re.search(r"[ء-ي][-–]$", t):
                    issue("wording", sl.loc, t, "hyphenated line end kept as printed", ["keep", "join the word across the break (decision)"])
                    issues[-1]["notice"] = True
                if not t:
                    prev_had_reference = had_ref
                    continue
                if paragraphs and not prev_had_reference and _is_wrap(paragraphs[-1], t):
                    block.wrap_joins.append(f"{sl.loc} joined to previous line")
                    paragraphs[-1] = paragraphs[-1] + " " + t
                else:
                    paragraphs.append(t)
                prev_had_reference = had_ref
            block.wording_paragraphs = paragraphs
            if paragraphs and RE_SEE_ALSO.match(paragraphs[0]):
                block.kind = "see_also"
                block.see_also_text = " ".join(paragraphs)
            if c1 is not None:
                for k, l in enumerate(c1.lines):
                    sl = source_line(pno, r.index, 1, k, l, "number")
                    block.number_lines.append(sl)
                    all_lines.append(sl)
                block.numbers = _split_numbers(" ".join(l.text for l in c1.lines))
            if c2 is not None:
                for k, l in enumerate(c2.lines):
                    sl = source_line(pno, r.index, 2, k, l, "page_label")
                    block.label_lines.append(sl)
                    all_lines.append(sl)
                block.labels = _split_numbers(" ".join(l.text for l in c2.lines))
            all_lines.extend(lines0)
            if r.dashed_top and block.title_ar is None:
                block.kind = "sibling" if block.kind == "entry" else block.kind
                prev = blocks[-1] if blocks else None
                if prev is not None:
                    block.continues_block = len(blocks) - 1
                    block.title_ar, block.title_basis = prev.title_ar, prev.title_basis
                    block.hierarchy = Hierarchy(**vars(prev.hierarchy))
                else:
                    issue("boundary", block.loc, "", "dashed rule with no previous block")
            elif first_entry_on_page and block.title_ar is None and not block.opener_lines and last_block_prev_page is not None:
                block.kind = "continuation" if block.kind == "entry" else block.kind
                block.continues_block = blocks.index(last_block_prev_page)
                block.title_ar, block.title_basis = last_block_prev_page.title_ar, last_block_prev_page.title_basis
                block.hierarchy = Hierarchy(**vars(last_block_prev_page.hierarchy))
            elif block.title_ar is None:
                issue("boundary", block.loc, " / ".join(l.text for l in lines0[:2]), "entry block without a title or sub-topic opener")
                issues[-1]["notice"] = True  # project rule 3: its heading is the first sentence of its wording; a report note
            if not block.numbers:
                issue("number", block.loc, " ".join(l.text for l in block.number_lines), "entry block without a principle number")
            if not block.wording_paragraphs:
                issue("wording", block.loc, "", "entry block without wording")
            if block.labels and block.numbers and len(block.labels) != len(block.numbers):
                issue("number", block.loc, f"numbers {block.numbers} labels {block.labels}", "numbers and page labels differ in count; labels recorded unpaired")
                issues[-1]["notice"] = True
            first_entry_on_page = False
            blocks.append(block)
        last_block_prev_page = last_block_of_page(blocks, pno)
    parse = IndexParse(file_name, page_classes, all_lines, letters, blocks, summary_rows, detailed_tables, summary_tables, page_labels, issues,
                       glyph_status, unresolved_glyphs, page_apparatus,
                       [{"xref": f.xref, "name": f.full_name, "base": f.base, "encoding": f.encoding, "kind": f.kind, "cmap_entries": len(f.cmap), "pages": f.pages}
                        for f in fm.fonts.values()], {}, tatweel_total, table_pages)
    _cross_check_summary(parse)
    return parse


def _without_article(topic: str) -> str:
    return " ".join(w[2:] if w.startswith("ال") and len(w) > 3 else w for w in topic.split())


def summary_differences(summary_topics: list[str], detailed_topics: list[str]) -> list[str]:
    """Readable differences between a summary row's topics and the detailed index's topics of that letter:
    pairs printed with and without the article «ال», then topics found on one side only."""
    only_s = [t for t in summary_topics if t not in detailed_topics]
    only_d = [t for t in detailed_topics if t not in summary_topics]
    pairs = []
    for t in list(only_s):
        twin = next((d for d in only_d if _without_article(d) == _without_article(t)), None)
        if twin is not None:
            pairs.append(f"«{t}» (summary) / «{twin}» (detailed)")
            only_s.remove(t)
            only_d.remove(twin)
    out = []
    if pairs:
        out.append("differ only by the article «ال»: " + "، ".join(pairs))
    if only_s:
        out.append("only in the summary index: " + "، ".join(f"«{t}»" for t in only_s))
    if only_d:
        out.append("only in the detailed index: " + "، ".join(f"«{t}»" for t in only_d))
    return out


def _cross_check_summary(parse: IndexParse) -> None:
    """The summary index's letters and topics must agree with the detailed index (section 5).
    The last letter the detailed pages hold may be covered only partially by an extract."""
    if not parse.summary_rows or not parse.letters:
        return
    detailed = {L.letter: [T.title_ar for T in L.topics] for L in parse.letters}
    last_letter = parse.letters[-1].letter
    # project rule 3 (extract and convert only): the comparison is recorded as notes, never as review items
    coverage: dict = {"complete": [], "partial": [], "absent_from_summary": [], "notes": []}
    summary_letters: set[str] = set()
    for row in parse.summary_rows:
        m = RE_LETTER.match(row["letter_label"])
        if not m:
            coverage["notes"].append(f"{row['locs'][0]}: summary row without a letter label: {row['letter_label']}")
            continue
        letter = m.group("letter")
        summary_letters.add(letter)
        topics = [t.strip() for t in re.split(r"\s[-–]\s", row["topics_text"]) if t.strip()]
        if letter not in detailed:
            continue  # the detailed pages of this letter are not among the supplied pages
        det = detailed[letter]
        if letter == last_letter and det and det == topics[: len(det)] and len(det) < len(topics):
            coverage["partial"].append({"letter": letter, "detailed_topics": det, "summary_topics": topics})
            continue
        if det == topics:
            coverage["complete"].append(letter)
            continue
        differences = summary_differences(topics, det)
        if differences:
            # one item per summary row: every difference of the row is listed (item ids are per location)
            coverage.setdefault("differs", []).append(letter)
            coverage["notes"].append(f"{row['locs'][1]}: «{row['letter_label']}»: " + "; ".join(differences) + " (both kept as printed)")
    for letter in detailed:
        if letter not in summary_letters:
            coverage["absent_from_summary"].append(letter)
            coverage["notes"].append(f"{parse.letters[0].loc}: letter «{letter}» of the detailed index absent from the summary index")
    parse.summary_coverage = coverage


def _split_numbers(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"[،,]", text) if p.strip()]


def _starts_unit(text: str) -> bool:
    t = text.lstrip()
    if t.startswith(BULLET) or RE_ORDINAL_LINE.match(t) or RE_SEE_ALSO.match(t):
        return True
    if re.match(r"^([0-9]+|[ء-ي])\s*[-–]\s", t) or t.startswith("– ") or t.startswith("- "):
        return True
    if t[:1] in ("«", "“", "”", "\""):
        return True
    return False


def _is_wrap(prev: str, nxt: str) -> bool:
    p = prev.rstrip()
    if not p:
        return False
    if p[-1] in SENTENCE_END:
        return False
    if _starts_unit(nxt):
        return False
    return True
