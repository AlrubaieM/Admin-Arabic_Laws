"""Index-page parser: turns the segmented tables of an index file into records.

Page classes, row classes and entry blocks follow the master prompt, section 5
(INDEX FILES).  Every source line receives exactly one class so that the
coverage check (section 14) can account for it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pymupdf

import pdf_source as ps

ORDINALS = ["أولاً", "ثانياً", "ثالثاً", "رابعاً", "خامساً", "سادساً", "سابعاً", "ثامناً", "تاسعاً", "عاشراً"]
_ORD_ALT = "|".join(re.escape(o) for o in ORDINALS) + "|" + "|".join(re.escape(o.replace("اً", "ا")) for o in ORDINALS)
RE_ORDINAL_LINE = re.compile(rf"^(?P<ord>(?:{_ORD_ALT}))\s*/\s*(?P<rest>.*)$")
RE_LETTER = re.compile(r"^حرف\s*\(\s*(?P<letter>[ء-يـ]{1,2})\s*\)\s*$")
RE_HEADER = {"المبدأ", "الرقم", "ص"}
RE_REF = re.compile(r"\(\s*(?P<prefix>[ء-ي][ـ]?)\s*/\s*(?P<num>[0-9]+(?:-[0-9]+)?)\s*/\s*(?P<year>[0-9]{3,4})\s*\)")
RE_SEE_ALSO = re.compile(r"^راجع\s*:")
RE_NUMBER_LIST = re.compile(r"^[0-9]+(?:\s*،\s*[0-9]+)*\s*،?\s*$")
BULLET = "•"
SENTENCE_END = set(".:!؟")  # an index cell is one paragraph: a semicolon at a line end is a layout wrap (revision of 03/11/2026)


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


def _strip_bullet(text: str) -> str:
    t = text.strip()
    if t.startswith(BULLET):
        t = t[1:].strip()
    return t


def _ends_with_colon(text: str) -> bool:
    return text.rstrip().endswith(":")


def classify_page(table: ps.Table | None, lines: list[ps.Line]) -> str:
    texts = [l.text for l in lines]
    if table is None:
        if not texts:
            return "blank"
        if any("رقم الإيداع" in t or "ردمك" in t for t in texts):
            return "cataloging"
        if all(t.isdigit() for t in texts):
            return "image_page"  # cover, half-title or divider carrying only a hidden folio
        return "other"
    first_cells = [c.text_lines for r in table.rows[:1] for c in r.cells]
    header = {t for cell in first_cells for t in cell}
    if header & RE_HEADER and len(header & RE_HEADER) >= 2:
        return "index_detailed"
    if table.rows and all(len(r.cells) == 2 for r in table.rows) and all(
        any(RE_LETTER.match(t) for t in r.cells[0].text_lines) for r in table.rows if any(c.lines for c in r.cells)
    ):
        return "index_summary"
    if any("رقم الإيداع" in t or "ردمك" in t for t in texts):
        return "cataloging"
    return "other"


def parse_index_file(doc: pymupdf.Document, file_name: str, fm: ps.FontMaps, repairs, settings: ps.ReaderSettings,
                     page_label_offset: int | None) -> IndexParse:
    page_classes: dict[int, str] = {}
    all_lines: list[SourceLine] = []
    letters: list[LetterRecord] = []
    blocks: list[EntryBlock] = []
    summary_rows: list[dict] = []
    detailed_tables: dict[int, list] = {}
    summary_tables: dict[int, list] = {}
    page_labels: dict[int, str] = {}
    issues: list[dict] = []
    hier = Hierarchy()
    current_topic: TopicRecord | None = None
    last_block_prev_page: EntryBlock | None = None

    def issue(kind: str, loc: str, text: str, note: str = "") -> None:
        issues.append({"issue_type": kind, "location": loc, "observed": text, "note": note})

    for pno in range(1, len(doc) + 1):
        glyphs = ps.page_glyphs(doc, pno, fm, repairs, settings)
        rulings = ps.merge_rulings(ps.page_rulings(doc[pno - 1]))
        table = ps.segment_table(pno, rulings, glyphs, settings)
        page_lines = table.outside if table is not None else ps.form_lines(glyphs, settings)
        cls = classify_page(table, page_lines if table is None else [l for r in table.rows for c in r.cells for l in c.lines] + table.outside)
        page_classes[pno] = cls
        # page furniture outside the frame: folio numbers
        for k, l in enumerate(page_lines):
            sl = SourceLine(pno, None, None, k, l.text, l.bold_ratio, l.gap_spaces, l.unresolved)
            if l.text.isdigit():
                sl.cls = "apparatus:page_number" if cls.startswith("index") else "apparatus:hidden_folio"
                if cls.startswith("index"):
                    page_labels[pno] = l.text
            elif cls == "cataloging":
                sl.cls = "cataloging_text"
            elif cls in ("blank", "image_page"):
                sl.cls = "apparatus:" + cls
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
                        sl = SourceLine(pno, r.index, c.col, k, l.text, l.bold_ratio, l.gap_spaces, l.unresolved, "cataloging_text")
                        all_lines.append(sl)
            continue
        if cls == "index_summary":
            summary_tables[pno] = [[c.text_lines for c in r.cells] for r in table.rows]
            for r in table.rows:
                cells = r.cells
                for c in cells:
                    for k, l in enumerate(c.lines):
                        sl = SourceLine(pno, r.index, c.col, k, l.text, l.bold_ratio, l.gap_spaces, l.unresolved)
                        sl.cls = "summary_letter" if c.col == 0 else "summary_topics"
                        all_lines.append(sl)
                if len(cells) >= 2 and (cells[0].lines or cells[1].lines):
                    summary_rows.append({
                        "page": pno, "row": r.index,
                        "letter_label": " ".join(cells[0].text_lines),
                        "topics_text": " ".join(cells[1].text_lines),
                        "locs": [f"page[{pno}]:r{r.index}:c0", f"page[{pno}]:r{r.index}:c1"],
                    })
            continue
        if cls != "index_detailed":
            for r in table.rows:
                for c in r.cells:
                    for k, l in enumerate(c.lines):
                        sl = SourceLine(pno, r.index, c.col, k, l.text, l.bold_ratio, l.gap_spaces, l.unresolved, "review")
                        all_lines.append(sl)
                        issue("other", sl.loc, l.text, "table line on a page of class " + cls)
            continue
        # ---------------- detailed index page ----------------
        detailed_tables[pno] = [[c.text_lines for c in r.cells] for r in table.rows]
        first_entry_on_page = True
        for r in table.rows:
            if not any(c.lines for c in r.cells):
                continue
            # header row
            texts0 = r.cells[0].text_lines
            if r.index == 0 and set(texts0) <= RE_HEADER and texts0:
                for c in r.cells:
                    for k, l in enumerate(c.lines):
                        all_lines.append(SourceLine(pno, r.index, c.col, k, l.text, l.bold_ratio, l.gap_spaces, l.unresolved, "header_row"))
                continue
            if r.full_width:
                # letter / topic / outline lines
                for k, l in enumerate(r.cells[0].lines):
                    sl = SourceLine(pno, r.index, 0, k, l.text, l.bold_ratio, l.gap_spaces, l.unresolved)
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
            # entry row: column 0 wording, column 1 numbers, column 2 labels
            c0, c1, c2 = r.cells[0], (r.cells[1] if len(r.cells) > 1 else None), (r.cells[2] if len(r.cells) > 2 else None)
            lines0 = [SourceLine(pno, r.index, 0, k, l.text, l.bold_ratio, l.gap_spaces, l.unresolved) for k, l in enumerate(c0.lines)]
            block = EntryBlock(pno, r.index, "entry", Hierarchy(**vars(hier)))
            i = 0
            # sub-topic opener (one or more lines ending with a colon, opened by an ordinal and a slash)
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
                    block.hierarchy.subtopic_label = m.group("ord") + "/"
                    block.hierarchy.subtopic_title = m.group("rest").strip()
                    hier = Hierarchy(**vars(block.hierarchy))
                    if current_topic is not None:
                        current_topic.subtopics.append({"label": block.hierarchy.subtopic_label, "title": block.hierarchy.subtopic_title, "loc": lines0[i].loc})
                    i = j + 1
                else:
                    issue("boundary", lines0[i].loc, lines0[i].text, "ordinal line without a closing colon")
            # bullet title (one or more lines ending with a colon)
            if i < len(lines0) and lines0[i].text.lstrip().startswith(BULLET):
                j = i
                while j < len(lines0) and not _ends_with_colon(lines0[j].text):
                    j += 1
                if j < len(lines0):
                    for q in range(i, j + 1):
                        lines0[q].cls = "title"
                        block.title_lines.append(lines0[q])
                    title = " ".join(_strip_bullet(l.text) if q == i else l.text for q, l in enumerate(lines0[i:j + 1], start=i))
                    block.title_ar = re.sub(r"\s+", " ", title.rstrip().rstrip(":")).strip()
                    block.title_basis = "bullet_title"
                    i = j + 1
                else:
                    issue("boundary", lines0[i].loc, lines0[i].text, "bullet title without a closing colon")
            if block.title_ar is None and block.hierarchy.subtopic_title and block.opener_lines:
                block.title_ar = block.hierarchy.subtopic_title
                block.title_basis = "subtopic_line"
            # wording and references
            rest = lines0[i:]
            for sl in rest:
                if RE_REF.fullmatch(sl.text.strip()) or (RE_REF.search(sl.text) and not RE_REF.sub("", sl.text).strip()):
                    sl.cls = "ruling_reference"
                    block.reference_lines.append(sl)
                else:
                    sl.cls = "index_wording"
                    block.wording_lines.append(sl)
            # references trailing a wording line
            for sl in block.wording_lines:
                for m in RE_REF.finditer(sl.text):
                    block.references.append(RulingRef(m.group(0).replace(" ", ""), m.group("prefix"), m.group("num"), m.group("year"), sl.loc))
            for sl in block.reference_lines:
                for m in RE_REF.finditer(sl.text):
                    block.references.append(RulingRef(m.group(0).replace(" ", ""), m.group("prefix"), m.group("num"), m.group("year"), sl.loc))
            # wording paragraphs: strip trailing references, join layout wraps
            texts = []
            for sl in block.wording_lines:
                t = RE_REF.sub("", sl.text).rstrip()
                t = re.sub(r"\s+$", "", t)
                texts.append((t, sl))
            paragraphs: list[str] = []
            for t, sl in texts:
                if not t:
                    continue
                if paragraphs and _is_wrap(paragraphs[-1], t):
                    block.wrap_joins.append(f"{sl.loc} joined to previous line")
                    paragraphs[-1] = paragraphs[-1] + " " + t
                else:
                    paragraphs.append(t)
            block.wording_paragraphs = paragraphs
            if paragraphs and RE_SEE_ALSO.match(paragraphs[0]):
                block.kind = "see_also"
                block.see_also_text = " ".join(paragraphs)
            # numbers and labels
            if c1 is not None:
                for k, l in enumerate(c1.lines):
                    sl = SourceLine(pno, r.index, 1, k, l.text, l.bold_ratio, l.gap_spaces, l.unresolved, "number")
                    block.number_lines.append(sl)
                    all_lines.append(sl)
                block.numbers = _split_numbers(" ".join(l.text for l in c1.lines))
            if c2 is not None:
                for k, l in enumerate(c2.lines):
                    sl = SourceLine(pno, r.index, 2, k, l.text, l.bold_ratio, l.gap_spaces, l.unresolved, "page_label")
                    block.label_lines.append(sl)
                    all_lines.append(sl)
                block.labels = _split_numbers(" ".join(l.text for l in c2.lines))
            all_lines.extend(lines0)
            # kind: sibling (dashed rule) / continuation (first block on the page without opener or title)
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
            if not block.numbers:
                issue("number", block.loc, " ".join(l.text for l in block.number_lines), "entry block without a principle number")
            if not block.wording_paragraphs:
                issue("wording", block.loc, "", "entry block without wording")
            if block.labels and block.numbers and len(block.labels) != len(block.numbers):
                issue("number", block.loc, f"numbers {block.numbers} labels {block.labels}", "numbers and page labels differ in count")
            first_entry_on_page = False
            blocks.append(block)
        if blocks and blocks[-1].page == pno:
            last_block_prev_page = blocks[-1]
    return IndexParse(file_name, page_classes, all_lines, letters, blocks, summary_rows, detailed_tables, summary_tables, page_labels, issues)


def _split_numbers(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"[،,]", text) if p.strip()]
    out = []
    for p in parts:
        if re.fullmatch(r"[0-9]+", p):
            out.append(p)
        else:
            out.append(p)  # kept verbatim; the caller flags non-numeric values
    return out


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
