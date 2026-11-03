"""Emission of the vault files: YAML frontmatter, RTL Markdown bodies, indexes,
volume details, the collection reader guide and the registry.

One YAML emitter (master prompt, section 9, YAML EMISSION) and one Markdown
escaper (section 4) are used for every file.  Nothing about the machine that
runs the build is written here: the vault is a function of the sources and
the configuration only.
"""
from __future__ import annotations

import re

import yaml

from vault_index import IndexParse
from vault_model import (Principle, citation_ar, citation_en, citation_full_ar, citation_full_en, key_number, key_sort, letter_slug,
                         principle_filename, principle_id, ruling_ref_id)

NOTE_PREFIX = "> ملاحظة المستودع:"
NOTES = {
    "body_absent": f"{NOTE_PREFIX} ملف المبدأ غير مضمّن في المصادر المزوّدة؛ النص المعروض هو صيغة الفهرس.",
    "index_absent": f"{NOTE_PREFIX} فهرس المجلد غير مضمّن في المصادر المزوّدة.",
    "differ": f"{NOTE_PREFIX} صيغة المبدأ في الفهرس تختلف عن صيغته في ملف المبدأ؛ وقد أُثبتت الصيغتان كما وردتا.",
    "shared": f"{NOTE_PREFIX} ورد هذا المبدأ في الفهرس ضمن مدخل مشترك مع المبادئ ذوات الأرقام ({{numbers}}).",
    "unresolved_see_also": f"{NOTE_PREFIX} لم يُعثر على المدخل المُحال إليه في الفهرس المزوّد.",
    "empty": f"{NOTE_PREFIX} لا يوجد في المصدر المزوّد.",
    "held": f"{NOTE_PREFIX} لم يُنشر ملف لهذه الأرقام حتى تُحل بنود المراجعة المذكورة (work/review).",
    "other_file": f"{NOTE_PREFIX} وردت للمبدأ صيغة مختلفة في ملف آخر مزوّد؛ أُثبتت الصيغتان كما وردتا ولم يُختر بينهما.",
}
HELD_MARK = "(محجوز للمراجعة)"
SOURCE_ORIGIN = "Official Board of Grievances principle collections"
RE_CATALOG_LABEL = re.compile(r"^(?P<label>[^:]{2,30}?)\s*:\s*(?P<value>\S.*)$")


# ----------------------------------------------------------------------------
# YAML
# ----------------------------------------------------------------------------


class QuotedStr(str):
    """A string value emitted with double quotes (keys stay plain)."""


class _Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data):  # never emit anchors/aliases for reused objects
        return True


def _quoted_representer(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", str(data), style='"')


_Dumper.add_representer(QuotedStr, _quoted_representer)


def _quote_values(obj):
    if isinstance(obj, dict):
        return {k: _quote_values(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_quote_values(v) for v in obj]
    if isinstance(obj, str) and not isinstance(obj, QuotedStr):
        return QuotedStr(obj)
    return obj


def dump_yaml(data: dict) -> str:
    text = yaml.dump(_quote_values(data), Dumper=_Dumper, allow_unicode=True, sort_keys=False, default_flow_style=False, width=100000)
    if "\\u" in text:
        raise ValueError("YAML output contains a \\u escape")
    return text


class StrictLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate keys."""


def _construct_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(None, None, f"duplicate key {key!r}", key_node.start_mark)
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def load_yaml(text: str):
    return yaml.load(text, Loader=StrictLoader)


# ----------------------------------------------------------------------------
# Markdown
# ----------------------------------------------------------------------------

_LINE_START = re.compile(r"^(#|>|\+ |- |\* |[0-9]+[.)]|\||<)")
_INLINE = re.compile(r"([*_`\[\]\\])")


def md_escape(text: str) -> str:
    """Escape source text so that no Markdown block or inline syntax survives (section 4)."""
    t = _INLINE.sub(r"\\\1", text)
    if _LINE_START.match(t):
        t = "\\" + t
    return t


def md_unescape(text: str) -> str:
    return re.sub(r"\\([#>+\-*0-9|<*_`\[\]\\])", r"\1", text)


def rtl_file(front: dict, body_lines: list[str]) -> str:
    body = "\n".join(body_lines).rstrip("\n")
    return "---\n" + dump_yaml(front) + "---\n\n<div dir=\"rtl\">\n\n" + body + "\n\n</div>\n"


def md_link(label: str, target: str) -> str:
    return f"[{label}](<{target}>)" if " " in target else f"[{label}]({target})"


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for i in items:
        if i not in out:
            out.append(i)
    return out


def _loc_range(locs: list[str]) -> str:
    if len(locs) == 1:
        return locs[0]
    first, last = locs[0], locs[-1]
    m1 = re.match(r"^(.*):L([0-9]+)$", first)
    m2 = re.match(r"^(.*):L([0-9]+)$", last)
    if m1 and m2 and m1.group(1) == m2.group(1):
        return f"{m1.group(1)}:L{m1.group(2)}-L{m2.group(2)}"
    return f"{first}-{last}"


# ----------------------------------------------------------------------------
# Principle files
# ----------------------------------------------------------------------------


def facet_hierarchy_line(f) -> str:
    parts = []
    for h in f.hierarchy:
        if h["level"] == "letter":
            parts.append(h.get("label_ar") or h["title_ar"])
        elif h["level"] == "topic":
            parts.append(h["title_ar"])
        else:
            parts.append(f"{h.get('label_ar', '')} {h['title_ar']}".strip())
    return " / ".join(parts)


def principle_front(cfg: dict, p: Principle, held: set | None = None) -> dict:
    held = held or set()
    vid = cfg["volume_id"]
    front: dict = {
        "volume_id": vid,
        "collection_name_ar": cfg["collection_name_ar"],
        "collection_name_en": cfg["collection_name_en"],
        "year_hijri": str(cfg["year_hijri"]),
        "volume_number": str(cfg["volume_number"]),
        "principle_id": principle_id(vid, p.key),
        "principle_number": str(p.number),
        "principle_title_ar": p.title_ar or "",
        "principle_title_en": f"Principle {p.number}",
        "title_basis": p.title_basis,
        "citation_ar": citation_ar(cfg, p.key),
        "citation_en": citation_en(cfg, p.key),
        "citation_full_ar": citation_full_ar(cfg, p),
        "citation_full_en": citation_full_en(cfg, p),
        "text_basis": "index_wording",
        "body_supplied": False,
        "index_file": "../index.md",
        "details_file": "../volume-details.md",
    }
    if p.facets and p.facets[0].hierarchy:
        front["hierarchy_ar"] = p.facets[0].hierarchy
    if p.page_labels:
        front["page_labels"] = list(p.page_labels)
    if p.references:
        refs = []
        for r in p.references:
            d = {"ref_ar": r.ref_ar, "prefix_ar": r.prefix_ar, "number": r.number, "year_hijri": r.year_hijri}
            rid = ruling_ref_id(vid, r)
            if rid is not None:
                d["ref_id"] = rid
            d["meaning_basis"] = "user_assigned" if cfg.get("ruling_reference_components") else "not_asserted"
            refs.append(d)
        front["ruling_references"] = refs
    if p.relations:
        rels = []
        for r in p.relations:
            d: dict = {}
            if r.principle_key is not None:
                d["principle_id"] = principle_id(vid, r.principle_key)
                d["title_ar"] = citation_ar(cfg, r.principle_key)
                if r.principle_key in held:
                    d["target_held"] = True  # the target is held from publication: no working path
                else:
                    d["path"] = principle_filename(r.principle_key)
            d["relation"] = r.relation
            if not r.target_supplied:
                d["target_supplied"] = False
                d["target_citation_ar"] = r.target_citation_ar
            rels.append(d)
        front["related_principles"] = rels
    facets = []
    for f in p.facets:
        d = {"facet": f.facet, "entry_kind": f.entry_kind, "title_ar": f.title_ar or "", "title_basis": f.title_basis, "hierarchy_ar": f.hierarchy}
        if f.page_label:
            d["page_label"] = f.page_label
        if f.references:
            d["ruling_references"] = [{"ref_ar": r.ref_ar} for r in f.references]
        if f.shared_with:
            d["shared_with"] = [principle_id(vid, n) for n in f.shared_with]
            d["pairing_basis"] = f.pairing_basis
        if f.heading_locations:
            d["heading_location"] = f.heading_locations[0]
        if f.text_locations:
            d["text_location"] = _loc_range(f.text_locations)
        facets.append(d)
    front["index_facets"] = facets
    see = [f.see_also_text for f in p.facets if f.see_also_text]
    if see:
        front["see_also_ar"] = see
    if p.anomalies:
        front["source_anomalies"] = True
    if p.open_issues:
        front["open_issues"] = [{"item_id": i["item_id"], "issue": i["note"]} for i in p.open_issues if "item_id" in i]
    front["sources"] = _sources(p)
    return front


def _sources(p: Principle) -> list[dict]:
    """One entry per source file, in the order the facets were read."""
    out: list[dict] = []
    by_file: dict[str, dict] = {}
    for f in p.facets:
        entry = by_file.get(f.file)
        if entry is None:
            entry = {"file": f.file, "kind": "index", "heading_locations": [], "text_locations": [], "reference_locations": [], "number_locations": []}
            by_file[f.file] = entry
            out.append(entry)
        entry["heading_locations"] += f.heading_locations
        entry["text_locations"] += f.text_locations
        entry["reference_locations"] += f.reference_locations
        entry["number_locations"] += f.number_locations
    for extra in p.extra_source_files:
        if extra not in by_file:
            e = {"file": extra, "kind": "index", "identical_wording": True}
            by_file[extra] = e
            out.append(e)
    for alt in p.alt_wordings:
        if alt.file not in by_file:
            e = {"file": alt.file, "kind": "index", "text_locations": list(alt.locations)}
            by_file[alt.file] = e
            out.append(e)
    for entry in out:
        for k in ("heading_locations", "text_locations", "reference_locations", "number_locations"):
            if k in entry:
                if entry[k]:
                    entry[k] = _dedupe(entry[k])
                else:
                    del entry[k]
        entry["extraction"] = "text_layer_repaired"
    return out


def principle_body(cfg: dict, p: Principle, principles: dict[str, Principle], held: set | None = None) -> list[str]:
    held = held or set()
    vid = cfg["volume_id"]
    lines: list[str] = [f"# {citation_ar(cfg, p.key)}", ""]
    lines += ["## العنوان", "", md_escape(p.title_ar or ""), ""]
    single = len(p.facets) == 1
    for f in p.facets:
        head = "## صيغة المبدأ في الفهرس" if single else f"## صيغة المبدأ في الفهرس — الموضع {f.facet}: {md_escape(f.title_ar or '')}"
        lines += [head, ""]
        hl = facet_hierarchy_line(f)
        if hl:
            lines += [md_escape(hl), ""]
        for para in f.wording_paragraphs:
            lines += [md_escape(para), ""]
        if f.entry_kind == "see_also":  # the «راجع» text is followed by the resolved link or the unresolved note (section 11)
            if f.see_also_target:
                tk, tf = f.see_also_target["principle_key"], f.see_also_target["facet"]
                if tk == p.key:
                    lines += [md_link("المدخل المُحال إليه (موضع آخر من هذا المبدأ)", f"../index.md#{principle_id(vid, tk)}:f{tf}"), ""]
                elif tk in held:
                    lines += [md_link(f"المدخل المُحال إليه: {citation_ar(cfg, tk)} {HELD_MARK}", f"../index.md#{principle_id(vid, tk)}:f{tf}"), ""]
                else:
                    lines += [md_link(f"المدخل المُحال إليه: {citation_ar(cfg, tk)}", principle_filename(tk)), ""]
            else:
                lines += [NOTES["unresolved_see_also"], ""]
        if f.reference_line:
            lines += [md_escape(f.reference_line), ""]
        if f.shared_with:
            lines += [NOTES["shared"].format(numbers="، ".join(str(key_number(n)) for n in f.shared_with)), ""]
    for alt in p.alt_wordings:
        lines += [f"## صيغة أخرى واردة في ملف آخر — {md_escape(alt.file)}", ""]
        for para in alt.paragraphs:
            lines += [md_escape(para), ""]
        if alt.reference_line:
            lines += [md_escape(alt.reference_line), ""]
        lines += [NOTES["other_file"], ""]
    lines += [NOTES["body_absent"], ""]
    lines += ["## روابط", ""]
    for f in p.facets:
        label = "موضع المبدأ في فهرس المجلد" if single else f"موضع المبدأ في فهرس المجلد — الموضع {f.facet}"
        lines.append(f"- {md_link(label, f'../index.md#{principle_id(vid, p.key)}:f{f.facet}')}")
    labels = {"shared_index_entry": "مدخل مشترك", "sibling_under_title": "صيغة أخرى تحت العنوان نفسه", "see_also": "إحالة إلى",
              "referenced_by_see_also": "محال إليه من", "same_ruling_reference": "المرجع نفسه"}
    for r in p.relations:
        if r.principle_key is None:
            continue  # an unresolved see-also is stated by the fixed note in its facet section; «روابط» holds links only
        if r.principle_key in held:
            target_facet = r.facet or 1
            lines.append(f"- {labels[r.relation]}: {md_link(citation_ar(cfg, r.principle_key) + ' ' + HELD_MARK, f'../index.md#{principle_id(vid, r.principle_key)}:f{target_facet}')}")
        else:
            lines.append(f"- {labels[r.relation]}: {md_link(citation_ar(cfg, r.principle_key), principle_filename(r.principle_key))}")
    lines.append(f"- {md_link('بيانات المجلد', '../volume-details.md')}")
    lines.append(f"- {md_link('دليل القارئ', '../../README.md')}")
    return lines


# ----------------------------------------------------------------------------
# Volume index
# ----------------------------------------------------------------------------


def volume_index(cfg: dict, parse: IndexParse, principles: dict[str, Principle], anomalies: list[dict], held_items: dict | None = None) -> str:
    vid = cfg["volume_id"]
    held_items = held_items or {}
    letters_yaml = []
    body: list[str] = []
    title = f"{cfg['collection_name_ar']} لعام {cfg['year_hijri']}هـ — {cfg['volume_ordinal_ar']}"
    body += [f"# {title}", ""]
    published = len(principles) - len(held_items)
    with_body = 0  # bodies come from principle files; none are supplied in this revision
    held_line = f"؛ و{len(held_items)} أرقام محجوزة للمراجعة" if held_items else ""
    body += [f"يعرض فهرس المجلد المزوّد {len(principles)} رقم مبدأ، منها {published} بملف منشور و{with_body} بنص كامل من ملف المبدأ{held_line}.", ""]
    body += ["الرمز p يسبق رقم المبدأ كما طُبع في المجلد؛ انظر " + md_link("دليل القارئ", "../README.md") + ".", ""]
    body += ["- " + md_link("بيانات المجلد", "volume-details.md"),
             "- " + md_link("الفهرس الهجائي الإجمالي كما ورد", "Indexes/summary-index.md"),
             "- " + md_link("الفهرس الهجائي التفصيلي كما ورد", "Indexes/detailed-index.md"), ""]
    facet_rows = [(k, f) for k, p in principles.items() for f in p.facets]
    facet_rows.sort(key=lambda kf: (kf[1].block_index, key_sort(kf[0])))
    for L in parse.letters:
        slug = letter_slug(L.letter) or "x"
        lid = f"{vid}:L-{slug}"
        topics_yaml = []
        body += [f'<a id="{lid}"></a>', f"## {L.label}", ""]
        for ti, T in enumerate(L.topics, start=1):
            tid = f"{lid}-{ti:02d}"
            subs_yaml = []
            body += [f'<a id="{tid}"></a>', f"### {md_escape(T.title_ar)}", ""]
            for o in T.outline:
                body += [md_escape(o), ""]
            facets_here = [(k, f) for k, f in facet_rows if _topic_of(f) == (L.letter, T.title_ar)]
            current_sub = None
            sub_index = 0
            for k, f in facets_here:
                sub = _subtopic_of(f)
                if sub != current_sub:
                    current_sub = sub
                    if sub is not None:
                        sub_index += 1
                        sid = f"{tid}-{sub_index:02d}"
                        subs_yaml.append({"subtopic_id": sid, "label_ar": sub[0], "title_ar": sub[1]})
                        if body and body[-1] != "":
                            body.append("")
                        body += [f'<a id="{sid}"></a>', f"#### {md_escape((sub[0] + ' ' + sub[1]).strip())}", ""]
                body.append(_index_entry_line(cfg, principles, k, f, k in held_items))
            if body and body[-1] != "":
                body.append("")
            topics_yaml.append({"topic_id": tid, "title_ar": T.title_ar, "subtopics": subs_yaml})
        letters_yaml.append({"letter_id": lid, "letter_ar": L.letter, "topics": topics_yaml})
    body += ["## المبادئ حسب الرقم", ""]
    for k in sorted(principles, key=key_sort):
        p = principles[k]
        extra = f" — {len(p.facets)} مواضع" if len(p.facets) > 1 else ""
        if k in held_items:
            body.append(f"- المبدأ رقم ({p.number}) {HELD_MARK}: {md_escape(p.title_ar or '')}{extra} — {', '.join(held_items[k]) or 'work/review'}")
        else:
            body.append(f"- {md_link(f'المبدأ رقم ({p.number})', 'Principles/' + principle_filename(k))}: {md_escape(p.title_ar or '')}{extra}")
    body.append("")
    if held_items:
        body += ["## مبادئ محجوزة للمراجعة", "", NOTES["held"], ""]
        for k in sorted(held_items, key=key_sort):
            body.append(f"- المبدأ رقم ({key_number(k)}): {', '.join(held_items[k])}")
        body.append("")
    if anomalies:
        body += ["## ملاحظات على نص المصدر", ""]
        for a in anomalies:
            body += [f"- {md_escape(a['location'])}: {md_escape(a['observed'])} — {md_escape(a.get('note_ar') or a.get('note', ''))}"]
        body.append("")
    front = {
        "volume_id": vid, "collection_name_ar": cfg["collection_name_ar"], "collection_name_en": cfg["collection_name_en"],
        "year_hijri": str(cfg["year_hijri"]), "volume_number": str(cfg["volume_number"]), "principle_count": published,
        "principles_with_body": with_body, "principles_held": len(held_items), "letters": letters_yaml,
    }
    return rtl_file(front, body)


def _topic_of(f) -> tuple:
    h = {d["level"]: d for d in f.hierarchy}
    return (h.get("letter", {}).get("title_ar"), h.get("topic", {}).get("title_ar"))


def _subtopic_of(f):
    h = {d["level"]: d for d in f.hierarchy}
    if "subtopic" in h:
        return (h["subtopic"].get("label_ar", ""), h["subtopic"]["title_ar"])
    return None


def _index_entry_line(cfg: dict, principles: dict[str, Principle], k: str, f, held: bool = False) -> str:
    vid = cfg["volume_id"]
    pid = principle_id(vid, k)
    number = key_number(k)
    anchor = f'<a id="{pid}:f{f.facet}"></a>'
    parts = [f"المبدأ رقم ({number}) {HELD_MARK}" if held else md_link(f"المبدأ رقم ({number})", "Principles/" + principle_filename(k))]
    if f.title_ar:
        parts.append(md_escape(f.title_ar))
    if f.page_label:
        parts.append(f"ص {f.page_label}")
    if f.references:
        parts.append(md_escape(" ".join(r.ref_ar for r in f.references)))
    parts.append(f"`{pid}`")
    flags = ["بدون ملف"]
    if f.entry_kind == "see_also":
        if f.see_also_target:
            tk, tf = f.see_also_target["principle_key"], f.see_also_target["facet"]
            flags.append("إحالة: " + md_link(f"المبدأ رقم ({key_number(tk)})", f"#{principle_id(vid, tk)}:f{tf}"))
        else:
            flags.append("إحالة: لم يُعثر على المدخل المُحال إليه في الفهرس المزوّد")
    if f.shared_with:
        flags.append("مدخل مشترك: " + " ↔ ".join([pid] + [principle_id(vid, o) for o in f.shared_with]))
    if f.entry_kind in ("sibling", "continuation"):
        flags.append("صيغة أخرى تحت العنوان نفسه")
    others = [o for o in principles[k].facets if o.facet != f.facet]
    if others:
        flags.append(f"مواضع أخرى: {len(others)} (" + "، ".join(md_link(f"الموضع {o.facet}", f"#{pid}:f{o.facet}") for o in others) + ")")
    return "- " + anchor + " " + " — ".join(parts) + " (" + "؛ ".join(flags) + ")"


# ----------------------------------------------------------------------------
# Preserved index tables
# ----------------------------------------------------------------------------


def preserved_table(cfg: dict, parse: IndexParse, kind: str) -> str:
    vid = cfg["volume_id"]
    tables = parse.detailed_tables if kind == "detailed" else parse.summary_tables
    pages = sorted(tables)
    body: list[str] = []
    name = "الفهرس الهجائي التفصيلي" if kind == "detailed" else "الفهرس الهجائي الإجمالي"
    body += [f"# {name} كما ورد في المجلد", ""]
    body += ["نسخة من جدول المصدر صفحةً صفحة؛ التصفح من " + md_link("فهرس المجلد", "../index.md") + ".", ""]
    for pno in pages:
        label = parse.page_labels.get(pno, "")
        body += [f"## صفحة {label} (page[{pno}])", ""]
        rows = list(tables[pno])
        ncols = 3 if kind == "detailed" else 2
        if kind == "detailed" and rows and all(len(c) == 1 for c in rows[0]) and {c[0] for c in rows[0]} <= {"المبدأ", "الرقم", "ص"}:
            header = [c[0] for c in rows[0]]  # the source's own header row
            rows = rows[1:]
        else:
            # the summary table prints no header row: the header cells are generated (GFM needs one) and say so
            header = ["المبدأ", "الرقم", "ص"] if kind == "detailed" else ["الحرف (رأس مولَّد)", "الموضوعات (رأس مولَّد)"]
        body += ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * ncols) + " |"]
        for row in rows:
            cells = [("<br>".join(_cell_escape(t) for t in cell)) for cell in row]
            if not any(cells):
                continue
            while len(cells) < ncols:
                cells.append("")
            body.append("| " + " | ".join(cells) + " |")
        body.append("")
    front = {"volume_id": vid, "index_kind": kind, "physical_pages": pages, "printed_labels": [parse.page_labels.get(p, "") for p in pages]}
    return rtl_file(front, body)


def _cell_escape(text: str) -> str:
    return md_escape(text).replace("|", "\\|")


# ----------------------------------------------------------------------------
# Volume details
# ----------------------------------------------------------------------------


def _catalog_rows(lines: list[str]) -> list[tuple[str, str]]:
    rows = []
    for l in lines:
        m = RE_CATALOG_LABEL.match(l)
        if m and not re.search(r"[0-9]", m.group("label")):
            rows.append((m.group("label").strip(), m.group("value").strip()))
    return rows


def volume_details(cfg: dict, parse: IndexParse, cataloging_lines: list[str], extraction_summary: dict, anomalies: list[dict],
                   year_span: dict | None, file_entries: list[dict], held_count: int = 0) -> str:
    vid = cfg["volume_id"]
    title = f"# {cfg['collection_name_ar']} لعام {cfg['year_hijri']}هـ — {cfg['volume_ordinal_ar']}: بيانات المجلد"
    body: list[str] = [title, ""]
    body += ["## بيانات المجلد كما وردت في الغلاف", ""]
    cover_lines = cfg.get("cover_lines_ar") or []
    if cover_lines:
        for v in cover_lines:
            body += [md_escape(v), ""]
    else:
        body += [NOTES["empty"], ""]
    body += ["## بيانات الفهرسة كما وردت في المصدر", ""]
    if cataloging_lines:
        rows = _catalog_rows(cataloging_lines)
        labelled = {l for l in cataloging_lines if any(l.startswith(r[0]) for r in rows)}
        for l in cataloging_lines:
            if l not in labelled:
                body += [md_escape(l), ""]
        if rows:
            body += ["| البيان | القيمة |", "| --- | --- |"]
            body += [f"| {_cell_escape(a)} | {_cell_escape(b)} |" for a, b in rows]
            body.append("")
    else:
        body += [NOTES["empty"], ""]
    body += ["## الفهارس المزوّدة", ""]
    det = sorted(parse.detailed_tables)
    summ = sorted(parse.summary_tables)
    if summ:
        body.append(f"- {md_link('الفهرس الهجائي الإجمالي', 'Indexes/summary-index.md')}: page[{summ[0]}]–page[{summ[-1]}]، الصفحات المطبوعة {parse.page_labels.get(summ[0], '')}–{parse.page_labels.get(summ[-1], '')}")
    if det:
        body.append(f"- {md_link('الفهرس الهجائي التفصيلي', 'Indexes/detailed-index.md')}: page[{det[0]}]–page[{det[-1]}]، الصفحات المطبوعة {parse.page_labels.get(det[0], '')}–{parse.page_labels.get(det[-1], '')}")
    if not summ and not det:
        body.append(NOTES["index_absent"])
    body.append("")
    body += ["## الملفات المزوّدة", ""]
    body += ["| الملف | النوع | عدد الصفحات | أرقام المبادئ | الاستخراج |", "| --- | --- | --- | --- | --- |"]
    for fe in file_entries:
        body.append(f"| {_cell_escape(fe['file'])} | {fe['kind']} | {fe['pages']} | {fe['numbers']} | {fe['extraction']} |")
    body.append("")
    if held_count:
        body += [f"{NOTE_PREFIX} {held_count} من أرقام المبادئ محجوزة للمراجعة ولم يُنشر لها ملف؛ انظر فهرس المجلد.", ""]
    body += ["## ملاحظات على نص المصدر", ""]
    vol_anoms = [a for a in anomalies if not a.get("principle")]
    if vol_anoms:
        for a in vol_anoms:
            body.append(f"- {md_escape(a['location'])}: {md_escape(a['observed'])} — {md_escape(a.get('note_ar') or a.get('note', ''))}")
        body.append("")
    else:
        body += [NOTES["empty"], ""]
    front: dict = {
        "volume_id": vid, "collection_name_ar": cfg["collection_name_ar"], "collection_name_en": cfg["collection_name_en"],
        "collection_name_en_basis": cfg.get("collection_name_en_basis", "descriptive"), "volume_ordinal_ar": cfg["volume_ordinal_ar"],
        "volume_number": str(cfg["volume_number"]), "year_hijri": str(cfg["year_hijri"]), "publisher_ar": cfg["publisher_ar"],
        "publisher_unit_ar": cfg.get("publisher_unit_ar", ""),
    }
    cat = {k: v for k, v in (cfg.get("cataloging") or {}).items() if k in ("deposit_number", "isbn", "extent_ar")}
    if cat:
        front["cataloging"] = cat
    front["source_origin"] = SOURCE_ORIGIN
    front["sources"] = [{"file": fe["file"], "kind": fe["kind"], "page_classes": fe["page_classes"], "extraction": fe["extraction"]} for fe in file_entries]
    front["extraction_summary"] = extraction_summary
    if year_span:
        front["year_gregorian_computed"] = year_span
    front["date_format"] = "DD/MM/YYYY"
    front["date_conversion_method"] = "hijridate (Umm al-Qura), year span only; no dates in principle files"
    return rtl_file(front, body)


# ----------------------------------------------------------------------------
# Collection README and registry
# ----------------------------------------------------------------------------


def collection_readme(volumes: list[dict]) -> str:
    body = [
        "# دليل القارئ لمستودع مبادئ المحكمة الإدارية العليا", "",
        "هذا المستودع مجموعة ملفات Markdown مولّدة آليًا من ملفات PDF لمجموعات المبادئ التي قررتها المحكمة الإدارية العليا الصادرة عن ديوان المظالم. كل مبدأ في ملف مستقل، وكل مجلد في مجلد مستقل باسمه الإنجليزي.", "",
        "## قواعد المعرّفات", "",
        "- معرّف المجلد: `<Name>-principles-<YYYY>-v<N>` (مثل `Admin-principles-1443-v6`)؛ وهو اسم مجلد الملفات أيضًا.", "",
        "- معرّف المبدأ: `<volume_id>:p<NNN>`؛ الرمز `p` يسبق رقم المبدأ كما طُبع في المجلد مكمَّلًا بالأصفار إلى ثلاث خانات على الأقل؛ اسم الملف هو الجزء بعد النقطتين مع `.md` (مثل `p383.md`). ولا يُمنح الرقم الواحد أكثر من معرّف؛ فإذا ورد في الفهرس تحت أكثر من موضوع فكل ورود «موضع» (facet) داخل الملف نفسه. وإذا قرر المستخدم فصل رقم طُبع لمبدأين مختلفين (قرار `split`) نُشر الثاني بلاحقة `-dup2` (مثل `p101-dup2.md`).", "",
        "- معرّفات الحروف والموضوعات في فهرس المجلد (`<volume_id>:L-<letter>`، `…-<NN>`، `…-<NN>-<NN>`) للتصفح فقط؛ الحرف مُحوَّل بجدول ثابت.", "",
        "- معرّف المرجع القضائي: `<volume_id>:r-<prefix>-<number>-<year>` داخلي، يجمع المبادئ التي تذكر المرجع نفسه؛ ولا يُمنح لمرجع حرفُه خارج الجدول الثابت.", "",
        "## تخطيط المجلدات والملفات", "",
        "- `README.md` (هذا الدليل) و`index.md` (سجل المجلدات) في جذر المستودع.", "",
        "- لكل مجلد: `index.md` (فهرس المجلد المولَّد)، و`volume-details.md` (بيانات المجلد كما وردت)، و`Indexes/summary-index.md` و`Indexes/detailed-index.md` (جدولا الفهرس كما وردا صفحةً صفحة؛ صف رأس الجدول الإجمالي مولَّد لأن المصدر لا يطبع رأسًا، وهو موسوم بذلك)، و`Principles/pNNN.md` (ملف لكل رقم مبدأ منشور).", "",
        "- المبدأ «المحجوز للمراجعة» رقمٌ لم يُنشر له ملف لأن في سطره محرفًا لم يُحل أو لأن مدخله بلا صيغة؛ يذكره فهرس المجلد مع أرقام بنود المراجعة في `work/review/`، ويُنشر بعد الإصلاح أو القرار.", "",
        "## مفاتيح الواجهة الأمامية (YAML) وقيمها", "",
        "ملف المبدأ:", "",
        "- `volume_id`، `collection_name_ar`، `collection_name_en`، `year_hijri`، `volume_number`: هوية المجلد.", "",
        "- `principle_id`، `principle_number`، `principle_title_ar` (عنوان الموضع الأول)، `principle_title_en` (`Principle N`)، `title_basis` ∈ {`bullet_title`, `subtopic_line`, `none`}.", "",
        "- `citation_ar`، `citation_en`، `citation_full_ar`، `citation_full_en`: صيغ الاستشهاد المولَّدة من بيانات المجلد؛ يُحذف من الصيغة الكاملة ما لم يرد في المصدر (عنوان أو صفحة أو مرجع) ويُسجَّل الحذف في `open_issues`.", "",
        "- `text_basis` ∈ {`index_wording`, `principle_file`, `index_and_body_identical`}: صيغة الفهرس هي بيان المحرر للمبدأ، ونص الملف هو مستخرج الحكم؛ والقسم الافتراضي للقراءة هو «نص المبدأ» عند وجود الملف وإلا «صيغة المبدأ في الفهرس». `body_supplied` يكون `false` عندما لا يكون ملف المبدأ مزوّدًا؛ فلا يحمل الملف حينئذ إلا صيغة الفهرس.", "",
        "- `index_file` و`details_file`: مساران نسبيان إلى فهرس المجلد وبيانات المجلد.", "",
        "- `hierarchy_ar`: قائمة من {`level` ∈ {letter, topic, subtopic}, `label_ar`, `title_ar`} للموضع الأول.", "",
        "- `page_labels`: أرقام الصفحات كما طُبعت في عمود «ص»؛ أما `page[P]` في المواقع فهو رقم الصفحة الفعلي في ملف PDF.", "",
        "- `ruling_references`: المراجع كما وردت بين قوسين (`ref_ar`) مع مكوناتها الثلاثة (`prefix_ar`, `number`, `year_hijri`) و`ref_id` (عند وجود حرف المرجع في الجدول الثابت)؛ `meaning_basis` ∈ {`not_asserted`, `user_assigned`}: الأولى تعني أن المستودع لا يفسر معنى المكونات ما لم يحدده الإعداد.", "",
        "- `related_principles`: `principle_id` و`title_ar` (صيغة الاستشهاد المختصرة للهدف) و`path` (المسار النسبي لملف الهدف) أو `target_held: true` عندما يكون الهدف محجوزًا للمراجعة بلا ملف؛ `relation` ∈ {`shared_index_entry`, `sibling_under_title`, `see_also`, `referenced_by_see_also`, `same_ruling_reference`}؛ روابط «راجع» هي إحالات الفهرس نفسه. `target_supplied: false` مع `target_citation_ar` عند تعذر العثور على المحال إليه في الفهرس المزوّد.", "",
        "- `index_facets`: كل مواضع الرقم في الفهرس بترتيب المصدر، ولكل موضع `facet` و`entry_kind` ∈ {entry, sibling, continuation, see_also} و`title_ar` و`title_basis` و`hierarchy_ar` و`page_label` و`ruling_references` و`shared_with` (معرّفات الأرقام المشاركة في مدخل واحد) و`pairing_basis` ∈ {`positional`, `confirmed_by_body`} و`heading_location` و`text_location`.", "",
        "- `see_also_ar`: نصوص الإحالة كما وردت. `status_from_source`: حالة يذكرها المصدر نفسه (لم تُلاحظ في العينة). `source_anomalies: true` عند تسجيل ملاحظة على نص المصدر لهذا المبدأ. `open_issues`: بنود المراجعة غير المحلولة ({`item_id`, `issue`}).", "",
        "- `sources`: مدخل لكل ملف مصدر: `file`، `kind` ∈ {index, principle}، `heading_locations`، `text_locations`، `reference_locations`، `number_locations`، `note_locations`، `identical_wording: true` (ملف آخر يحمل الصيغة نفسها)، `extraction` ∈ {`text_layer_repaired`, `ocr`}: الأولى تعني أن النص قُرئ من طبقة النص بعد إصلاح المحارف المعيبة وفق إعداد المجلد، والثانية أن قرارًا نشر قراءة التعرف الضوئي.", "",
        "فهرس المجلد (`index.md`): `principle_count` (الملفات المنشورة) و`principles_with_body` و`principles_held` (أرقام محجوزة بلا ملف) و`letters` (الشجرة الهجائية: `letter_id`, `letter_ar`, `topics` [`topic_id`, `title_ar`, `subtopics` [`subtopic_id`, `label_ar`, `title_ar`]]).", "",
        "جدولا الفهرس (`Indexes/*.md`): `index_kind` ∈ {summary, detailed} و`physical_pages` و`printed_labels`.", "",
        "بيانات المجلد (`volume-details.md`): `collection_name_en_basis` ∈ {official_supplied, user_assigned, descriptive} و`volume_ordinal_ar` و`publisher_ar` و`publisher_unit_ar` و`cataloging` (`deposit_number`, `isbn`, `extent_ar` كما طُبعت) و`source_origin` و`sources` (`file`, `kind`, `page_classes`, `extraction`) و`extraction_summary` (`fonts`, `text_layer` ∈ {defective, reliable}, `glyph_repairs_applied`, `ocr_confirmed_lines`, `ocr_disagreements` عند وجود سجل للتعرف الضوئي) و`year_gregorian_computed` (نطاق السنة الهجرية ميلاديًا بصيغة DD/MM/YYYY، محسوب) و`date_format` و`date_conversion_method`.", "",
        "سجل المجلدات (`index.md` في الجذر): لكل مجلد `volume_id` و`collection_name_ar` و`collection_name_en` و`year_hijri` و`volume_number` و`folder` و`principle_count` و`principles_with_body` و`principles_held`.", "",
        "## مواقع المصدر", "",
        "- `page[P]` صفحة فعلية (1-based)؛ `:r<i>:c<j>` صف وعمود الجدول (العمود 0 هو الأيمن: «المبدأ»، ثم «الرقم»، ثم «ص»)؛ `:L<k>` سطر داخل الخلية (0-based) قبل ضم الأسطر الملتفة.", "",
        "## ملاحظات", "",
        "- الأرقام في الملفات بالأرقام الغربية، والنص بالترتيب المنطقي وبصيغة NFC. وتُقرأ الأرقام داخل المرجع القضائي من اليمين إلى اليسار عددًا عددًا كما طُبعت.", "",
        "- غلاف الكتاب وصفحة البسملة والصفحات الفاصلة والترويسة والتذييل مستبعدة بقرار المستخدم؛ وصفحة الفهرسة محفوظة مرة واحدة في `volume-details.md`، وسطور الغلاف منقولة من صورته.", "",
        "- لا يحوّل المستودع تواريخ المبادئ؛ والسنة الهجرية للمجلد تُذكر كما وردت، ويُذكر في `volume-details.md` نطاقها الميلادي محسوبًا.", "",
        "## المجلدات", "",
    ]
    for v in volumes:
        body.append(f"- {md_link(v['collection_name_ar'] + ' لعام ' + v['year_hijri'] + 'هـ — ' + v['volume_ordinal_ar'], v['folder'] + '/index.md')}")
    body.append("")
    front = {"collection": "Saudi-Principles", "reader_guide": True, "volumes": [v["volume_id"] for v in volumes]}
    return rtl_file(front, body)


def collection_registry(volumes: list[dict]) -> str:
    body = ["# سجل مجلدات المستودع", "", "انظر " + md_link("دليل القارئ", "README.md") + ".", ""]
    for v in volumes:
        held = f"، و{v['principles_held']} محجوزة" if v.get("principles_held") else ""
        body.append(f"- {md_link(v['collection_name_ar'] + ' لعام ' + v['year_hijri'] + 'هـ — ' + v['volume_ordinal_ar'], v['folder'] + '/index.md')} — `{v['volume_id']}` — {v['principle_count']} مبدأ منشور، منها {v['principles_with_body']} بملف{held}.")
    body.append("")
    front = {"volumes": [{"volume_id": v["volume_id"], "collection_name_ar": v["collection_name_ar"], "collection_name_en": v["collection_name_en"],
                          "year_hijri": v["year_hijri"], "volume_number": v["volume_number"], "folder": v["folder"],
                          "principle_count": v["principle_count"], "principles_with_body": v["principles_with_body"],
                          "principles_held": v.get("principles_held", 0)} for v in volumes]}
    return rtl_file(front, body)
