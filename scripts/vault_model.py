"""Vault model: facets, principles, relations, identifiers and citations.

Implements the master prompt's sections 6 (identifiers), 9 (facets, citation
templates) and 10 (relations) on top of the parsed index records.

A principle is keyed by its printed number; a decided `split` (section 6)
publishes further principles of the same number under the keys
"<number>-dup2", "<number>-dup3" ...  Every function that needs the number
of a key uses key_number().
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from vault_index import EntryBlock, IndexParse, RulingRef

# the fixed transliteration table of section 6 (TOPIC IDS)
LETTER_SLUGS = {
    "أ": "a", "ب": "b", "ت": "t", "ث": "th", "ج": "j", "ح": "h", "خ": "kh", "د": "d", "ذ": "dh", "ر": "r", "ز": "z", "س": "s", "ش": "sh",
    "ص": "s2", "ض": "d2", "ط": "t2", "ظ": "z2", "ع": "ain", "غ": "gh", "ف": "f", "ق": "q", "ك": "k", "ل": "l", "م": "m", "ن": "n",
    "هـ": "h2", "و": "w", "ي": "y",
}
# volume_id: <Collection>-principles-<year or first year-last year>[-v<volume ordinal>]; the ordinal is omitted when the
# supplied source prints none (e.g. a collection of several years issued without a volume number)
_VOL = r"[A-Z][a-z]*(-[a-z]+)*-principles-[0-9]{4}(-[0-9]{4})?(-v[0-9]+)?"
RE_VOLUME_ID = re.compile(rf"^{_VOL}$")
RE_PRINCIPLE_ID = re.compile(rf"^{_VOL}:[pd][0-9]{{3,}}(-dup[0-9]+)?$")
RE_RULING_REF_ID = re.compile(rf"^{_VOL}:r-[a-z0-9]+-[0-9]+(-[0-9]+)?-[0-9]{{3,4}}$")
RE_LETTER_ID = re.compile(rf"^{_VOL}:L-[a-z0-9]+$")
RE_TOPIC_ID = re.compile(rf"^{_VOL}:L-[a-z0-9]+-[0-9]{{2}}$")
RE_SUBTOPIC_ID = re.compile(rf"^{_VOL}:L-[a-z0-9]+-[0-9]{{2}}-[0-9]{{2}}$")
# a key: the printed number ("364"), or a labelled number of another kind of entry listed in the index
# ("d1" for «قرار (1)», a decision of the General Assembly), with "-dupN" after a decided split
RE_KEY = re.compile(r"^(?P<kind>[a-z]?)(?P<n>[0-9]+)(?P<dup>-dup(?P<k>[0-9]+))?$")
# number cells may print a labelled number «<word> (N)»: the word's code makes the key (Arabic vocabulary of the source)
NUMBER_KINDS = {"قرار": "d"}
KIND_WORDS = {code: word for word, code in NUMBER_KINDS.items()}
KIND_EN = {"": "Principle", "d": "Decision"}
RE_LABELLED_NUMBER = re.compile(r"^(?P<word>[ء-ي]+)\s*\(\s*(?P<n>[0-9]+)\s*\)$")


def number_key(token: str) -> str | None:
    """The key of a printed number cell token, or None when it is neither a number nor a known labelled number."""
    t = token.strip()
    if re.fullmatch(r"[0-9]+", t):
        return t
    m = RE_LABELLED_NUMBER.match(t)
    if m and m.group("word") in NUMBER_KINDS:
        return f"{NUMBER_KINDS[m.group('word')]}{int(m.group('n'))}"
    return None


def key_kind(key: str) -> str:
    m = RE_KEY.match(key)
    return m.group("kind") if m else ""


def base_key(key: str) -> str:
    """The key without a -dupN suffix."""
    return key.split("-dup")[0]


def letter_slug(letter: str) -> str | None:
    """Slug of the fixed table, or None for a letter outside it (the caller flags it). «ه» printed without the
    tatweel is the same letter as «هـ»."""
    return LETTER_SLUGS.get(letter) or (LETTER_SLUGS["هـ"] if letter == "ه" else None)


def key_number(key: str) -> int:
    m = RE_KEY.match(key)
    if not m:
        raise ValueError(f"not a principle key: {key!r}")
    return int(m.group("n"))


def key_suffix(key: str) -> str:
    m = RE_KEY.match(key)
    return (m.group("dup") or "") if m else ""


def key_sort(key: str) -> tuple[int, int, int]:
    """Principles first, then other kinds, each by number, then split copies."""
    m = RE_KEY.match(key)
    if not m:
        raise ValueError(f"not a principle key: {key!r}")
    return (0 if not m.group("kind") else 1 + sorted(KIND_EN).index(m.group("kind")), int(m.group("n")), int(m.group("k") or 0))


def _code(key: str) -> str:
    return key_kind(key) or "p"


def principle_id(volume_id: str, key: str) -> str:
    return f"{volume_id}:{_code(key)}{key_number(key):03d}{key_suffix(key)}"


def principle_filename(key: str) -> str:
    return f"{_code(key)}{key_number(key):03d}{key_suffix(key)}.md"


def printed_number(key: str) -> str:
    """The number as the index prints it (Western digits): "364", or «قرار (1)» for a decision."""
    kind = key_kind(key)
    return f"{KIND_WORDS[kind]} ({key_number(key)})" if kind else str(key_number(key))


def skeleton(text: str) -> str:
    """Letter skeleton for matching only (master prompt, section 14): marks and
    tatweel removed, alef and yeh forms unified, teh marbuta unified, spaces
    and punctuation removed."""
    t = unicodedata.normalize("NFC", text)
    t = re.sub(r"[ً-ٰٟـ]", "", t)
    t = t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ٱ", "ا").replace("ى", "ي").replace("ة", "ه")
    t = re.sub(r"[^\w]", "", t)
    return t


def fallback_title(paragraphs: list[str]) -> str:
    """Title of an entry without bullet title or sub-topic line: the first sentence of its wording,
    truncated at its first «؛» or «.» (section 9 FIELD RULES, title_basis none)."""
    if not paragraphs:
        return ""
    return re.split(r"[؛.]", re.sub(r"^\s*•\s*", "", paragraphs[0]), maxsplit=1)[0].strip()


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
    shared_with: list[str]  # other principle keys of the same block
    pairing_basis: str | None
    heading_locations: list[str]
    text_locations: list[str]
    reference_locations: list[str]
    number_locations: list[str]
    wording_paragraphs: list[str]
    reference_line: str  # the reference text as printed, joined
    see_also_text: str | None
    see_also_target: dict | None  # {principle_key, facet} or None
    see_also_path_ar: str | None
    wrap_joins: list[str]
    page: int
    file: str = ""  # source file the facet was read from


@dataclass
class Relation:
    principle_key: str | None
    relation: str
    target_supplied: bool = True
    target_citation_ar: str | None = None
    facet: int | None = None


@dataclass
class AltWording:
    file: str
    paragraphs: list[str]
    reference_line: str
    locations: list[str]


@dataclass
class Principle:
    key: str  # printed number, or "<number>-dupN" after a decided split
    facets: list[Facet] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    anomalies: list[dict] = field(default_factory=list)
    open_issues: list[dict] = field(default_factory=list)
    alt_wordings: list[AltWording] = field(default_factory=list)
    extra_source_files: list[str] = field(default_factory=list)  # files whose wording is identical

    @property
    def number(self) -> int:
        return key_number(self.key)

    @property
    def title_ar(self) -> str | None:
        return self.facets[0].title_ar if self.facets else None

    @property
    def display_title(self) -> str:
        """The title published as principle_title_ar and as the body H1 (they must be equal)."""
        if not self.facets:
            return ""
        return self.facets[0].title_ar or fallback_title(self.facets[0].wording_paragraphs)

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

    @property
    def wording_signature(self) -> str:
        return "\n".join(para for f in self.facets for para in f.wording_paragraphs)


def letter_slug_of_prefix(prefix: str) -> str | None:
    """Slug of a ruling-reference prefix: one letter («ب» → b) or several joined by «/» («د/س» → ds)."""
    parts = [p for p in re.split(r"\s*/\s*", prefix.strip()) if p]
    slugs = [letter_slug(p) for p in parts]
    return "".join(slugs) if parts and all(slugs) else None


def ruling_ref_id(volume_id: str, ref: RulingRef) -> str | None:
    slug = letter_slug_of_prefix(ref.prefix_ar)
    if slug is None:
        return None
    return f"{volume_id}:r-{slug}-{ref.number}-{ref.year_hijri}"


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


def components_not_printed(parse: IndexParse) -> list[str]:
    """Entry components this index file prints for none of its entries (its layout has no such column or line)."""
    blocks = [b for b in parse.blocks if b.numbers]
    if not blocks:
        return []
    present = {"title": any(b.title_ar for b in blocks), "page label": any(b.labels for b in blocks),
               "ruling reference": any(b.references for b in blocks)}
    return [name for name, has in present.items() if not has]


def _pair_by_evidence(numbers: list[str], items: list, evidence: dict[str, set], wrap: bool = False) -> list[int]:
    """For an entry listing several numbers and as many items (ruling references or page labels), the index of the
    item each number takes. Positional by default; when the numbers' other listings name exactly one matching item
    each, and those items are distinct, that evidence decides (a printed order of references may differ from the
    order of the numbers)."""
    positional = list(range(len(numbers)))
    if len(numbers) < 2 or len(items) != len(numbers):
        return positional
    keys = [(it,) if wrap else it for it in items]
    choice = []
    for n in numbers:
        hits = [i for i, k in enumerate(keys) if k in evidence.get(n, set())]
        if len(hits) != 1:
            return positional
        choice.append(hits[0])
    return choice if len(set(choice)) == len(choice) else positional


def _evidence_agrees(numbers: list[str], block, evidence: dict[str, set]) -> bool:
    return len(block.references) == len(numbers) and all(
        (block.references[i].number, block.references[i].year_hijri) in evidence.get(n, set()) for i, n in enumerate(numbers))


def build_principles(parse: IndexParse, volume_id: str) -> tuple[dict[str, Principle], list[dict]]:
    """Group the index blocks into principles (one per number) with facets.

    Returns (principles by key, review items)."""
    principles: dict[str, Principle] = {}
    review: list[dict] = []
    label_of: dict[str, set[str]] = {}
    # evidence for multi-number entries (project rule 1, best accurate result automatically): the ruling and the page
    # label each number carries where the index lists it alone
    ruling_evidence: dict[str, set[tuple[str, str]]] = {}
    label_evidence: dict[str, set[str]] = {}
    for block in parse.blocks:
        nums = [k for k in (number_key(n) for n in block.numbers) if k]
        if len(nums) == 1:
            ruling_evidence.setdefault(nums[0], set()).update((r.number, r.year_hijri) for r in block.references)
            label_evidence.setdefault(nums[0], set()).update(block.labels[:1])
    for bi, block in enumerate(parse.blocks):
        numbers = [k for k in (number_key(n) for n in block.numbers) if k]
        for n in block.numbers:
            if number_key(n) is None:
                review.append({"issue_type": "number", "location": block.loc, "observed": n, "note": "non-numeric principle number"})
        ref_order = _pair_by_evidence(numbers, [(r.number, r.year_hijri) for r in block.references], ruling_evidence)
        label_order = _pair_by_evidence(numbers, list(block.labels), {n: {(l,) for l in v} for n, v in label_evidence.items()}, wrap=True)
        for pos, number in enumerate(numbers):
            label = block.labels[label_order[pos]] if len(block.labels) == len(numbers) else None
            refs = [block.references[ref_order[pos]]] if len(block.references) == len(numbers) and len(numbers) > 1 else list(block.references)
            pairing = None
            if len(numbers) > 1:
                by_evidence = ref_order != list(range(len(numbers))) or label_order != list(range(len(numbers)))
                pairing = "confirmed_by_other_facets" if by_evidence or _evidence_agrees(numbers, block, ruling_evidence) else "positional"
            label_of.setdefault(number, set())
            if label:
                label_of[number].add(label)
            facet = Facet(
                facet=0, block_index=bi, entry_kind=block.kind, title_ar=block.title_ar, title_basis=block.title_basis,
                hierarchy=hierarchy_list(block), page_label=label, references=refs,
                shared_with=[n for n in numbers if n != number], pairing_basis=pairing,
                heading_locations=[l.loc for l in block.opener_lines + block.title_lines],
                text_locations=[l.loc for l in block.wording_lines],
                reference_locations=sorted({r.loc for r in block.references}, key=_loc_key),  # every reference printed in the facet's reference line
                number_locations=[l.loc for l in block.number_lines + block.label_lines],
                wording_paragraphs=list(block.wording_paragraphs),
                reference_line=" ".join(r.ref_ar for r in block.references), see_also_text=block.see_also_text,
                see_also_target=None, see_also_path_ar=_see_also_path(block.see_also_text), wrap_joins=list(block.wrap_joins), page=block.page,
                file=parse.file,
            )
            p = principles.setdefault(number, Principle(number))
            facet.facet = len(p.facets) + 1
            p.facets.append(facet)
        if len(numbers) > 1 and len(block.references) not in (len(numbers), 0):
            review.append({"issue_type": "reference", "location": block.loc, "observed": " ".join(r.ref_ar for r in block.references),
                           "note": "reference count differs from the number count; references recorded unpaired", "notice": True,
                           "affected_ids": [principle_id(volume_id, n) for n in numbers]})
    for number, labels in label_of.items():
        p = principles[number]
        if len(labels) > 1:
            item = {"issue_type": "number", "location": ", ".join(f.number_locations[0] for f in p.facets if f.number_locations),
                    "observed": f"number {number} printed with page labels {sorted(labels)}", "note": "page label differs between facets", "notice": True,
                    "affected_ids": [principle_id(volume_id, number)]}
            review.append(item)
            p.open_issues.append(item)
    for number, p in principles.items():
        keys = {(r.number, r.year_hijri) for f in p.facets for r in f.references}
        if len(keys) > 1:
            item = {"issue_type": "identity", "location": ", ".join(f.reference_locations[0] for f in p.facets if f.reference_locations),
                    "observed": f"number {number} cited with rulings {sorted(keys)}",
                    "note": "facets of one number disagree on the ruling number or year (decision split publishes them as pNNN and pNNN-dupN)", "notice": True,
                    "affected_ids": [principle_id(volume_id, number)], "options": ["keep (one principle)", "split (one principle per ruling)"]}
            review.append(item)
            p.open_issues.append(item)
        # an entry missing a component that the index prints for its other entries (a layout that never prints a
        # component, e.g. an index without ruling references, is reported once per file by components_not_printed)
        gaps = [name for name, present in (("title", bool(p.title_ar)), ("page label", bool(p.page_labels)), ("ruling reference", bool(p.references)))
                if not present and name not in components_not_printed(parse)]
        if gaps:
            loc = p.facets[0].heading_locations[0] if p.facets and p.facets[0].heading_locations else parse.blocks[p.facets[0].block_index].loc
            item = {"issue_type": "other", "location": loc, "observed": ", ".join(gaps),
                    "note": f"entry without a {' or '.join(gaps)}, although other entries of this index print one", "notice": True,
                    "affected_ids": [principle_id(volume_id, number)]}
            review.append(item)
            p.open_issues.append(item)
        for f in p.facets:
            for r in f.references:
                if letter_slug_of_prefix(r.prefix_ar) is None:
                    item = {"issue_type": "reference", "location": r.loc, "observed": r.ref_ar,
                            "note": "ruling-reference prefix outside the fixed transliteration table; no ref_id minted",
                            "affected_ids": [principle_id(volume_id, number)]}
                    review.append(item)
                    p.open_issues.append(item)
    return principles, review


def apply_split_decisions(principles: dict[str, Principle], decisions: dict, volume_id: str, item_id_of) -> list[str]:
    """Apply decided `split` resolutions: facets of a number that cite different
    rulings become pNNN (first ruling in source order) and pNNN-dupK.  Returns
    the keys created."""
    created: list[str] = []
    for key in sorted(list(principles), key=key_sort):
        p = principles[key]
        if key_suffix(key):
            continue
        for issue in list(p.open_issues):
            if issue.get("issue_type") != "identity":
                continue
            iid = issue.get("item_id") or item_id_of(issue["location"], issue["issue_type"])
            d = decisions.get(iid)
            if not d or str(d.get("resolution", "")).lower() != "split":
                continue
            groups: dict[tuple, list[Facet]] = {}
            for f in p.facets:
                g = (f.references[0].number, f.references[0].year_hijri) if f.references else ("", "")
                groups.setdefault(g, []).append(f)
            ordered = list(groups.values())
            p.facets = ordered[0]
            for i, f in enumerate(p.facets, start=1):
                f.facet = i
            for k, facets in enumerate(ordered[1:], start=2):
                new_key = f"{key}-dup{k}"
                q = Principle(new_key)
                q.facets = facets
                for i, f in enumerate(q.facets, start=1):
                    f.facet = i
                principles[new_key] = q
                created.append(new_key)
            p.open_issues = [i for i in p.open_issues if i is not issue]
    return created


def resolve_relations(principles: dict[str, Principle], parses, volume_id: str) -> list[dict]:
    """Relations of section 10; returns review items for unresolved see-also references.

    `parses` maps each index file name to its IndexParse (a single IndexParse is accepted for one file):
    a facet's block_index is an index into the blocks of the file the facet was read from."""
    if not isinstance(parses, dict):
        parses = {parses.file: parses}
    review: list[dict] = []
    by_key = principles
    facets_index: list[tuple[str, Facet]] = [(k, f) for k, p in by_key.items() for f in p.facets]
    block_keys: dict[tuple[str, int], list[str]] = {}
    for k, f in facets_index:
        block_keys.setdefault((f.file, f.block_index), []).append(k)

    def block_of(f: Facet):
        return parses[f.file].blocks[f.block_index]

    for key, p in by_key.items():
        for f in p.facets:
            for other in block_keys.get((f.file, f.block_index), []):
                if other != key:
                    _add(p, Relation(other, "shared_index_entry"))
            block = block_of(f)
            if block.continues_block is not None:
                for other in block_keys.get((f.file, block.continues_block), []):
                    if other != key:
                        _add(p, Relation(other, "sibling_under_title"))
                        _add(by_key[other], Relation(key, "sibling_under_title"))
    for key, p in by_key.items():
        for f in p.facets:
            if f.entry_kind != "see_also" or not f.see_also_path_ar:
                continue
            target = _match_see_also(f.see_also_path_ar, facets_index)
            if target is None:
                # project rule 3 (extract and convert only): an unresolved see-also is recorded as a relation in
                # work/records, never a review item; its «راجع» text is published verbatim as extracted
                _add(p, Relation(None, "see_also", target_supplied=False, target_citation_ar=f.see_also_path_ar))
            else:
                tk, tf = target
                f.see_also_target = {"principle_key": tk, "facet": tf.facet}
                if tk == key:
                    continue
                _add(p, Relation(tk, "see_also", facet=tf.facet))
                _add(by_key[tk], Relation(key, "referenced_by_see_also", facet=f.facet))
    refs: dict[str, set[str]] = {}
    for key, p in by_key.items():
        for r in p.references:
            refs.setdefault(r.ref_ar, set()).add(key)
    for ref, keys in refs.items():
        if len(keys) > 1:
            for a in keys:
                for b in keys:
                    if a != b:
                        _add(by_key[a], Relation(b, "same_ruling_reference"))
    order = {"shared_index_entry": 0, "sibling_under_title": 1, "see_also": 2, "referenced_by_see_also": 3, "same_ruling_reference": 4}
    for p in by_key.values():
        p.relations.sort(key=lambda r: (order[r.relation], key_sort(r.principle_key) if r.principle_key else (10**9, 0), r.facet or 0))
    return review


def _loc_key(loc: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"[0-9]+", loc))


def _see_also_path(text: str | None) -> str | None:
    if not text:
        return None
    m = re.search(r"راجع\s*:\s*\((.*)\)\s*$", text.strip())
    return m.group(1).strip() if m else text.strip()


def _add(p: Principle, rel: Relation) -> None:
    for r in p.relations:
        if (r.principle_key, r.relation, r.facet, r.target_citation_ar) == (rel.principle_key, rel.relation, rel.facet, rel.target_citation_ar):
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
    for key, f in facets_index:
        h = {d["level"]: d for d in f.hierarchy}
        if "letter" not in h or skeleton(h["letter"]["title_ar"]) != skeleton(letter):
            continue
        if "topic" not in h or skeleton(h["topic"]["title_ar"]) != skeleton(topic):
            continue
        names = [skeleton(h["subtopic"]["title_ar"])] if "subtopic" in h else []
        if f.title_ar:
            names.append(skeleton(f.title_ar))
        if all(r in names for r in rest):
            cands.append((key, f))
    return cands[0] if len(cands) == 1 else None


# ----------------------------------------------------------------------------
# Identifier validation (section 6: validate every generated ID; fail on mismatch)
# ----------------------------------------------------------------------------


def validate_ids(volume_id: str, principles: dict[str, Principle], letters) -> list[str]:
    problems: list[str] = []
    if not RE_VOLUME_ID.match(volume_id):
        problems.append(f"volume_id {volume_id}")
    for key, p in principles.items():
        pid = principle_id(volume_id, key)
        if not RE_PRINCIPLE_ID.match(pid):
            problems.append(pid)
        for r in p.references:
            rid = ruling_ref_id(volume_id, r)
            if rid is not None and not RE_RULING_REF_ID.match(rid):
                problems.append(rid)
    for L in letters:
        slug = letter_slug(L.letter)
        lid = f"{volume_id}:L-{slug}" if slug else None
        if lid is None or not RE_LETTER_ID.match(lid):
            problems.append(f"letter {L.letter!r} has no slug in the fixed table")
            continue
        for ti, T in enumerate(L.topics, start=1):
            tid = f"{lid}-{ti:02d}"
            if not RE_TOPIC_ID.match(tid):
                problems.append(tid)
            for si in range(1, len(T.subtopics) + 1):
                sid = f"{tid}-{si:02d}"
                if not RE_SUBTOPIC_ID.match(sid):
                    problems.append(sid)
    return problems


# ----------------------------------------------------------------------------
# Citations (master prompt, section 9)
# ----------------------------------------------------------------------------
