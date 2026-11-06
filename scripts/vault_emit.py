"""Emission of the vault files: short YAML frontmatter, RTL Markdown bodies, the
volume index, the volume details, the collection registry and reader guide.

Output shape follows the user's decisions of 04/11/2026 (recorded in the master
prompt's revision note): two indexes only (the collection registry and one
index per volume), no vault notes, no "index wording" framing (the statements
are the principles), and a frontmatter of a few keys.  One YAML emitter and
one Markdown escaper are used for every file.
"""
from __future__ import annotations

import re

import yaml

from vault_index import IndexParse
from vault_model import Principle, key_number, key_sort, principle_filename, principle_id

SOURCE_ORIGIN = "Official Board of Grievances principle collections"
RE_CATALOG_LABEL = re.compile(r"^(?P<label>[^:]{2,30}?)\s*:\s*(?P<value>\S.*)$")
HELD_MARK = "محجوز للمراجعة"


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


def _cell(text: str) -> str:
    t = md_escape(text)
    if t.startswith("\\|"):  # md_escape already escaped a line-start pipe
        return "\\|" + t[2:].replace("|", "\\|")
    return t.replace("|", "\\|")


# ----------------------------------------------------------------------------
# Identifiers shown in the vault
# ----------------------------------------------------------------------------


def p_id(key: str) -> str:
    return f"P{key_number(key):04d}" + ("-" + key.split("-dup")[1] if "-dup" in key else "")


def g_id(label: str | None) -> str:
    if not label:
        return ""
    return f"G{int(label):04d}" if label.isdigit() else f"G{label}"


def gi_id(page: int) -> str:
    return f"GI{page:04d}"


def collection_name_ar(cfg: dict) -> str:
    return f"{cfg['collection_name_ar']} عام {cfg['year_hijri']}"


def collection_name_en(cfg: dict) -> str:
    return f"{cfg['collection_name_en']} year {cfg['year_hijri']}"


# ----------------------------------------------------------------------------
# Principle files
# ----------------------------------------------------------------------------


def principle_front(cfg: dict, p: Principle, held: set | None = None) -> dict:
    vid = cfg["volume_id"]
    front: dict = {
        "collection_name_ar": collection_name_ar(cfg),
        "collection_name_en": collection_name_en(cfg),
        "volume_number": str(cfg["volume_number"]),
        "principle_id": principle_id(vid, p.key),
        "principle_number": str(p.number),
        "principle_title_ar": p.display_title,
        "principle_title_en": f"Principle {p.number}",
    }
    letters = []
    for f in p.facets:
        for h in f.hierarchy:
            if h["level"] == "letter" and h["title_ar"] not in letters:
                letters.append(h["title_ar"])
    if letters:
        front["index_letter"] = letters[0] if len(letters) == 1 else letters
    if p.page_labels:
        front["page_id"] = g_id(p.page_labels[0]) if len(p.page_labels) == 1 else [g_id(l) for l in p.page_labels]
    pages = []
    for f in p.facets:
        if f.page not in pages:
            pages.append(f.page)
    front["index_page_id"] = gi_id(pages[0]) if len(pages) == 1 else [gi_id(x) for x in pages]
    if p.references:
        front["ruling_references"] = [{"ref": r.ref_ar} for r in p.references]
    return front


def principle_body(cfg: dict, p: Principle, principles: dict[str, Principle] | None = None, held: set | None = None) -> list[str]:
    lines: list[str] = [f"# {md_escape(p.display_title)}", ""]
    for i, f in enumerate(p.facets):
        if i > 0:
            lines += [f"## {md_escape(f.title_ar or '')}", ""]
        for para in f.wording_paragraphs:
            lines += [md_escape(para), ""]
        if f.reference_line:
            lines += [md_escape(f.reference_line), ""]
    for alt in p.alt_wordings:
        lines += [f"## صيغة أخرى واردة في {md_escape(alt.file)}", ""]
        for para in alt.paragraphs:
            lines += [md_escape(para), ""]
        if alt.reference_line:
            lines += [md_escape(alt.reference_line), ""]
    return lines


# ----------------------------------------------------------------------------
# Volume index (one per volume)
# ----------------------------------------------------------------------------


def _topic_of(f) -> tuple:
    h = {d["level"]: d for d in f.hierarchy}
    return (h.get("letter", {}).get("title_ar"), h.get("topic", {}).get("title_ar"))


def _subtopic_of(f) -> str | None:
    h = {d["level"]: d for d in f.hierarchy}
    return h["subtopic"]["title_ar"] if "subtopic" in h else None


def volume_index(cfg: dict, parse: IndexParse, principles: dict[str, Principle], anomalies: list[dict] | None = None,
                 held_items: dict | None = None) -> str:
    vid = cfg["volume_id"]
    held_items = held_items or {}
    body: list[str] = [f"# {collection_name_ar(cfg)} — {cfg['volume_ordinal_ar']}", ""]
    published = len(principles) - len(held_items)
    if parse.summary_rows:
        body += ["## موضوعات المجلد", ""]
        for row in parse.summary_rows:
            body += [md_escape(f"{row['letter_label']}: {row['topics_text']}"), ""]
    facet_rows = sorted(((k, f) for k, p in principles.items() for f in p.facets), key=lambda kf: (kf[1].block_index, key_sort(kf[0])))
    for L in parse.letters:
        body += [f"## {md_escape(L.label)}", ""]
        for T in L.topics:
            body += [f"### {md_escape(T.title_ar)}", ""]
            for o in T.outline:
                body += [md_escape(o), ""]
            rows = [(k, f) for k, f in facet_rows if _topic_of(f) == (L.letter, T.title_ar)]
            if not rows:
                continue
            body += ["| الكلمات المفتاحية | P | G | GI |", "| --- | --- | --- | --- |"]
            for k, f in rows:
                keywords = " — ".join(x for x in (_subtopic_of(f), f.title_ar if f.title_basis == "bullet_title" else None) if x)
                label = _cell(keywords or f.title_ar or "")
                cell = f"{label} ({HELD_MARK})" if k in held_items else md_link(label, "Principles/" + principle_filename(k))
                body.append(f"| {cell} | {p_id(k)} | {g_id(f.page_label)} | {gi_id(f.page)} |")
            body.append("")
    front = {"collection_name_ar": collection_name_ar(cfg), "collection_name_en": collection_name_en(cfg), "volume_number": str(cfg["volume_number"]),
             "volume_id": vid, "principle_count": published}
    if held_items:
        front["principles_held"] = len(held_items)
    return rtl_file(front, body)


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


def volume_details(cfg: dict, parse: IndexParse, cataloging_lines: list[str], extraction_summary: dict | None, anomalies: list[dict],
                   year_span: dict | None, file_entries: list[dict], held_count: int = 0) -> str:
    body: list[str] = [f"# {collection_name_ar(cfg)} — {cfg['volume_ordinal_ar']}: بيانات المجلد", ""]
    cover_lines = cfg.get("cover_lines_ar") or []
    if cover_lines:
        body += ["## الغلاف", ""]
        for v in cover_lines:
            body += [md_escape(v), ""]
    if cataloging_lines:
        body += ["## بيانات الفهرسة", ""]
        rows = _catalog_rows(cataloging_lines)
        labelled = {l for l in cataloging_lines if any(l.startswith(r[0]) for r in rows)}
        for l in cataloging_lines:
            if l not in labelled:
                body += [md_escape(l), ""]
        if rows:
            body += ["| البيان | القيمة |", "| --- | --- |"] + [f"| {_cell(a)} | {_cell(b)} |" for a, b in rows] + [""]
    front: dict = {
        "collection_name_ar": collection_name_ar(cfg), "collection_name_en": collection_name_en(cfg), "volume_number": str(cfg["volume_number"]),
        "volume_id": cfg["volume_id"], "volume_ordinal_ar": cfg["volume_ordinal_ar"], "year_hijri": str(cfg["year_hijri"]),
        "publisher_ar": cfg["publisher_ar"],
    }
    cat = {k: v for k, v in (cfg.get("cataloging") or {}).items() if k in ("deposit_number", "isbn", "extent_ar")}
    if cat:
        front["cataloging"] = cat
    front["source_origin"] = SOURCE_ORIGIN
    front["source_files"] = [fe["file"] for fe in file_entries]
    return rtl_file(front, body)


# ----------------------------------------------------------------------------
# Collection registry and reader guide
# ----------------------------------------------------------------------------


def collection_registry(volumes: list[dict]) -> str:
    body = ["# مستودع مبادئ المحكمة الإدارية العليا", ""]
    for v in volumes:
        # the year tells apart volumes of the same ordinal (e.g. «المجلد السادس» of 1443 and of 1444)
        label = f"{v['collection_name_ar']} لعام {v['year_hijri']}هـ — {v['volume_ordinal_ar']}"
        body.append(f"- {md_link(label, v['folder'] + '/index.md')} — {v['principle_count']} مبدأ")
    body.append("")
    front = {"volumes": [{"volume_id": v["volume_id"], "folder": v["folder"], "principle_count": v["principle_count"]} for v in volumes]}
    return rtl_file(front, body)


def collection_readme(volumes: list[dict]) -> str:
    body = [
        "# دليل القارئ", "",
        "- `index.md` في الجذر يسرد المجلدات؛ و`<volume>/index.md` يسرد مبادئ المجلد بكلماتها المفتاحية ومعرّفاتها؛ و`<volume>/Principles/pNNN.md` ملف المبدأ؛ و`<volume>/volume-details.md` بيانات المجلد كما طُبعت.", "",
        "- المعرّفات: `P0364` رقم المبدأ كما طُبع في المجلد؛ `G1685` الصفحة المطبوعة (العمود الثالث في الفهرس)؛ `GI0016` الصفحة في ملف الفهرس نفسه؛ `principle_id` هو `<volume_id>:p<NNN>` واسم الملف `p<NNN>.md`.", "",
        "- نص المبدأ هو النص الوارد في المجلد بحروفه وأرقامه؛ الأرقام بالأرقام الغربية، والمراجع بين قوسين تُقرأ من اليمين إلى اليسار عددًا عددًا كما طُبعت. مبدأ ورد تحت أكثر من موضوع يحمل مواضعه كلها في ملف واحد.", "",
        "- كل ملف يبدأ ببيانات YAML قصيرة ثم نص عربي من اليمين إلى اليسار؛ وبيانات الاستخراج والمراجعة في `work/` خارج المستودع.", "",
    ]
    front = {"collection": "Saudi-Principles", "volumes": [v["volume_id"] for v in volumes]}
    return rtl_file(front, body)
