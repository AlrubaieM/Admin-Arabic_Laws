"""Vault model: facets, principles, relations, identifiers and citations.

Implements the master prompt's sections 6 (identifiers), 9 (facets, citation
templates) and 10 (relations) on top of the parsed index records.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from vault_index import EntryBlock, IndexParse, RulingRef

LETTER_SLUGS = {
    "أ": "a", "ا": "a", "إ": "a", "آ": "a", "ب": "b", "ت": "t", "ث": "th", "ج": "j", "ح": "h", "خ": "kh", "د": "d", "ذ": "dh",
    "ر": "r", "ز": "z", "س": "s", "ش": "sh", "ص": "s2", "ض": "d2", "ط": "t2", "ظ": "z2", "ع": "ain", "غ": "gh", "ف": "f",
    "ق": "q", "ك": "k", "ل": "l", "م": "m", "ن": "n", "هـ": "h2", "ه": "h2", "و": "w", "ي": "y", "ى": "y",
}
RE_VOLUME_ID = re.compile(r"^[A-Z][a-z]*(-[a-z]+)*-principles-[0-9]{4}-v[0-9]+$")
RE_PRINCIPLE_ID = re.compile(r"^[A-Z][a-z]*(-[a-z]+)*-principles-[0-9]{4}-v[0-9]+:p[0-9]{3,}(-dup[0-9]+)?$")


def letter_slug(letter: str) -> str:
    return LETTER_SLUGS.get(letter, "x" + "".join(f"{ord(c):04x}" for c in letter))


def skeleton(text: str) -> str:
    """Letter skeleton for matching only (master prompt, section 14): marks and
    tatweel removed, alef and yeh forms unified, teh marbuta unified, spaces
    and punctuation removed."""
    t = unicodedata.normalize("NFC", text)
    t = re.sub(r"[ً-ٰٟـ]", "", t)
    t = t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ٱ", "ا").replace("ى", "ي").replace("ة", "ه")
    t = re.sub(r"[^\w]", "", t)
    return t


@dataclass
class Facet:
    facet: int
    block_index: int
    entry_kind: str
    title_ar: str | None
    title_basis: str
    hierarchy: list[dict]
    page_label: str | None
    references: list[RulingRef]
    shared_with: list[str]  # other principle numbers of the same block
    pairing_basis: str | None
    heading_locations: list[str]
    text_locations: list[str]
    reference_locations: list[str]
    number_locations: list[str]
    wording_paragraphs: list[str]
    reference_line: str  # the reference text as printed, joined
    see_also_text: str | None
    see_also_target: dict | None  # {principle_number, facet} or None
    see_also_path_ar: str | None
    wrap_joins: list[str]
    page: int


@dataclass
class Relation:
    principle_number: str | None
    relation: str
    target_supplied: bool = True
    target_citation_ar: str | None = None
    facet: int | None = None


@dataclass
class Principle:
    number: str
    facets: list[Facet] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    anomalies: list[dict] = field(default_factory=list)
    open_issues: list[dict] = field(default_factory=list)

    @property
    def title_ar(self) -> str | None:
        return self.facets[0].title_ar if self.facets else None

    @property
    def title_basis(self) -> str:
        return self.facets[0].title_basis if self.facets else "none"

    @property
    def page_labels(self) -> list[str]:
        out: list[str] = []
        for f in self.facets:
            if f.page_label and f.page_label not in out:
                out.append(f.page_label)
        return out

    @property
    def references(self) -> list[RulingRef]:
        out: list[RulingRef] = []
        seen: set[str] = set()
        for f in self.facets:
            for r in f.references:
                if r.ref_ar not in seen:
                    seen.add(r.ref_ar)
                    out.append(r)
        return out


def principle_id(volume_id: str, number: str) -> str:
    return f"{volume_id}:p{int(number):03d}"


def principle_filename(number: str) -> str:
    return f"p{int(number):03d}.md"


def ruling_ref_id(volume_id: str, ref: RulingRef) -> str:
    return f"{volume_id}:r-{letter_slug(ref.prefix_ar)}-{ref.number}-{ref.year_hijri}"


def hierarchy_list(block: EntryBlock) -> list[dict]:
    h = block.hierarchy
    out: list[dict] = []
    if h.letter:
        out.append({"level": "letter", "label_ar": h.letter_label, "title_ar": h.letter})
    if h.topic:
        out.append({"level": "topic", "title_ar": h.topic})
    if h.subtopic_title:
        out.append({"level": "subtopic", "label_ar": h.subtopic_label, "title_ar": h.subtopic_title})
    return out


def build_principles(parse: IndexParse, volume_id: str) -> tuple[dict[str, Principle], list[dict], list[dict]]:
    """Group the index blocks into principles (one per number) with facets.

    Returns (principles by number, review items, anomalies)."""
    principles: dict[str, Principle] = {}
    review: list[dict] = []
    anomalies: list[dict] = []
    label_of: dict[str, set[str]] = {}
    for bi, block in enumerate(parse.blocks):
        numbers = [n for n in block.numbers if re.fullmatch(r"[0-9]+", n)]
        bad = [n for n in block.numbers if not re.fullmatch(r"[0-9]+", n)]
        for n in bad:
            review.append({"issue_type": "number", "location": block.loc, "observed": n, "note": "non-numeric principle number"})
        for pos, number in enumerate(numbers):
            label = block.labels[pos] if pos < len(block.labels) and len(block.labels) == len(numbers) else None
            refs = [block.references[pos]] if len(block.references) == len(numbers) and len(numbers) > 1 else list(block.references)
            pairing = None
            if len(numbers) > 1:
                pairing = "positional"
            label_of.setdefault(number, set())
            if label:
                label_of[number].add(label)
            heading_locs = [l.loc for l in block.opener_lines + block.title_lines]
            text_locs = [l.loc for l in block.wording_lines]
            ref_locs = sorted({r.loc for r in refs}, key=_loc_key)
            number_locs = [l.loc for l in block.number_lines + block.label_lines]
            facet = Facet(
                facet=0, block_index=bi, entry_kind=block.kind, title_ar=block.title_ar, title_basis=block.title_basis,
                hierarchy=hierarchy_list(block), page_label=label, references=refs,
                shared_with=[n for n in numbers if n != number], pairing_basis=pairing,
                heading_locations=heading_locs, text_locations=text_locs, reference_locations=ref_locs,
                number_locations=number_locs, wording_paragraphs=list(block.wording_paragraphs),
                reference_line=" ".join(r.ref_ar for r in block.references), see_also_text=block.see_also_text,
                see_also_target=None, see_also_path_ar=_see_also_path(block.see_also_text), wrap_joins=list(block.wrap_joins), page=block.page,
            )
            p = principles.setdefault(number, Principle(number))
            facet.facet = len(p.facets) + 1
            p.facets.append(facet)
        if len(block.labels) != len(numbers) and block.labels:
            review.append({"issue_type": "number", "location": block.loc, "observed": f"numbers {numbers} labels {block.labels}",
                           "note": "page labels could not be paired with the numbers positionally"})
        if len(numbers) > 1 and len(block.references) not in (len(numbers), 0):
            review.append({"issue_type": "reference", "location": block.loc, "observed": " ".join(r.ref_ar for r in block.references),
                           "note": "reference count differs from the number count; references recorded unpaired"})
    # cross-entry label consistency
    for number, labels in label_of.items():
        p = principles[number]
        if len(labels) > 1:
            item = {"issue_type": "number", "location": ", ".join(f.number_locations[0] for f in p.facets if f.number_locations),
                    "observed": f"number {number} printed with page labels {sorted(labels)}", "note": "page label differs between facets"}
            review.append(item)
            p.open_issues.append(item)
        elif labels and any(f.pairing_basis == "positional" for f in p.facets) and len(p.facets) > 1:
            for f in p.facets:
                if f.pairing_basis == "positional":
                    f.pairing_basis = "positional_confirmed_by_other_facet"
    # facets of one number must share the ruling number and year
    for number, p in principles.items():
        keys = {(r.number, r.year_hijri) for f in p.facets for r in f.references}
        if len(keys) > 1:
            item = {"issue_type": "identity", "location": ", ".join(f.reference_locations[0] for f in p.facets if f.reference_locations),
                    "observed": f"number {number} cited with rulings {sorted(keys)}", "note": "facets of one number disagree on the ruling number or year"}
            review.append(item)
            p.open_issues.append(item)
    _resolve_relations(principles, parse, review)
    return principles, review, anomalies


def _loc_key(loc: str) -> tuple:
    nums = [int(x) for x in re.findall(r"[0-9]+", loc)]
    return tuple(nums)


def _see_also_path(text: str | None) -> str | None:
    if not text:
        return None
    m = re.search(r"راجع\s*:\s*\((.*)\)\s*$", text.strip())
    return m.group(1).strip() if m else text.strip()


def _resolve_relations(principles: dict[str, Principle], parse: IndexParse, review: list[dict]) -> None:
    by_number = principles
    # shared entries and siblings
    for number, p in by_number.items():
        for f in p.facets:
            for other in f.shared_with:
                if other in by_number and not any(r.principle_number == other and r.relation == "shared_index_entry" for r in p.relations):
                    p.relations.append(Relation(other, "shared_index_entry"))
            block = parse.blocks[f.block_index]
            if block.continues_block is not None:
                prev = parse.blocks[block.continues_block]
                for other in prev.numbers:
                    if other in by_number and other != number:
                        _add(p, Relation(other, "sibling_under_title"))
                        _add(by_number[other], Relation(number, "sibling_under_title"))
    # see-also targets
    facets_index: list[tuple[str, Facet]] = [(n, f) for n, p in by_number.items() for f in p.facets]
    for number, p in by_number.items():
        for f in p.facets:
            if f.entry_kind != "see_also" or not f.see_also_path_ar:
                continue
            target = _match_see_also(f.see_also_path_ar, facets_index)
            if target is None:
                _add(p, Relation(None, "see_also", target_supplied=False, target_citation_ar=f.see_also_path_ar))
            else:
                tn, tf = target
                f.see_also_target = {"principle_number": tn, "facet": tf.facet}
                if tn == number:
                    continue  # internal facet link, no self-relation
                _add(p, Relation(tn, "see_also", facet=tf.facet))
                _add(by_number[tn], Relation(number, "referenced_by_see_also", facet=f.facet))
    # same ruling reference
    refs: dict[str, set[str]] = {}
    for number, p in by_number.items():
        for r in p.references:
            refs.setdefault(r.ref_ar, set()).add(number)
    for ref, numbers in refs.items():
        if len(numbers) > 1:
            for a in numbers:
                for b in numbers:
                    if a != b:
                        _add(by_number[a], Relation(b, "same_ruling_reference"))
    order = {"shared_index_entry": 0, "sibling_under_title": 1, "see_also": 2, "referenced_by_see_also": 3, "same_ruling_reference": 4}
    for p in by_number.values():
        p.relations.sort(key=lambda r: (order[r.relation], int(r.principle_number) if r.principle_number else 10**9, r.facet or 0))


def _add(p: Principle, rel: Relation) -> None:
    for r in p.relations:
        if (r.principle_number, r.relation, r.facet, r.target_citation_ar) == (rel.principle_number, rel.relation, rel.facet, rel.target_citation_ar):
            return
    p.relations.append(rel)


def _match_see_also(path: str, facets_index: list[tuple[str, Facet]]) -> tuple[str, Facet] | None:
    parts = [p.strip() for p in re.split(r"\s[-–]\s", path) if p.strip()]
    if not parts:
        return None
    m = re.match(r"^حرف\s*([ء-يـ]{1,2})\s*/\s*(.*)$", parts[0])
    if not m:
        return None
    letter, topic = m.group(1), m.group(2).strip()
    rest = [skeleton(x) for x in parts[1:]]
    cands = []
    for number, f in facets_index:
        h = {d["level"]: d for d in f.hierarchy}
        if "letter" not in h or skeleton(h["letter"]["title_ar"]) != skeleton(letter):
            continue
        if "topic" not in h or skeleton(h["topic"]["title_ar"]) != skeleton(topic):
            continue
        names = [skeleton(h["subtopic"]["title_ar"])] if "subtopic" in h else []
        if f.title_ar:
            names.append(skeleton(f.title_ar))
        if all(r in names for r in rest):
            cands.append((number, f))
    return cands[0] if len(cands) == 1 else None


# ----------------------------------------------------------------------------
# Citations (master prompt, section 9)
# ----------------------------------------------------------------------------


def citation_ar(cfg: dict, number: str) -> str:
    return f"{cfg['collection_name_ar']} لعام {cfg['year_hijri']}هـ، {cfg['volume_ordinal_ar']}، المبدأ رقم ({int(number)})"


def citation_en(cfg: dict, number: str) -> str:
    return f"{cfg['collection_name_en']}, {cfg['year_hijri']} AH, Vol. {cfg['volume_number']}, Principle No. {int(number)}"


def citation_full_ar(cfg: dict, p: Principle) -> str:
    s = f"المبدأ رقم ({int(p.number)})"
    if p.title_ar:
        s += f": «{p.title_ar}»"
    s += f"، {cfg['collection_name_ar']} لعام {cfg['year_hijri']}هـ، {cfg['volume_ordinal_ar']}، {cfg['publisher_ar']}"
    if p.page_labels:
        s += "، ص " + "، ".join(p.page_labels)
    if p.references:
        s += "، " + " ".join(r.ref_ar for r in p.references)
    return s


def citation_full_en(cfg: dict, p: Principle) -> str:
    s = f"{cfg['collection_name_en']}, {cfg['year_hijri']} AH, Vol. {cfg['volume_number']} ({cfg.get('publisher_en', 'Board of Grievances')}), Principle No. {int(p.number)}"
    if p.page_labels:
        s += ", p. " + ", ".join(p.page_labels)
    if p.references:
        s += ", ruling ref. " + " ".join(r.ref_ar for r in p.references)
    return s
