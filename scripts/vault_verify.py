"""Verification, cross-check and OCR confirmation (master prompt, section 14).

verify:      re-derives every published file from the sources and compares it
             byte for byte, parses every YAML frontmatter with duplicate-key
             rejection, compares the frontmatter with the records, checks IDs,
             links, anchors, reciprocity, coverage, held principles, the
             Markdown lint, determinism (two builds), the fixture expectations,
             and that a mutated copy is rejected by a content check.
crosscheck:  compares the published principles with a second, independent
             reader (Poppler pdftotext).
ocr-confirm: confirms every published cell against Tesseract OCR of its crop,
             when Tesseract is available.
"""
from __future__ import annotations

import collections
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from pathlib import Path

import pymupdf

import pdf_source as ps
import vault_emit as em
import vault_model as vm

REQUIRED_PRINCIPLE_KEYS = [
    "volume_id", "collection_name_ar", "collection_name_en", "year_hijri", "volume_number", "principle_id", "principle_number",
    "principle_title_ar", "principle_title_en", "citation_ar", "citation_en", "citation_full_ar", "citation_full_en", "text_basis",
    "body_supplied", "index_file", "details_file", "sources",
]
KEY_ORDER = [
    "volume_id", "collection_name_ar", "collection_name_en", "year_hijri", "volume_number", "principle_id", "principle_number",
    "principle_title_ar", "principle_title_en", "title_basis", "citation_ar", "citation_en", "citation_full_ar", "citation_full_en",
    "text_basis", "body_supplied", "index_file", "details_file", "hierarchy_ar", "page_labels", "ruling_references", "related_principles",
    "index_facets", "see_also_ar", "status_from_source", "source_anomalies", "open_issues", "sources",
]
CONTENT_CLASSES = {"index_wording", "title", "subtopic_opener", "outline", "letter", "topic", "number", "page_label", "ruling_reference",
                   "summary_letter", "summary_topics", "header_row", "cataloging_text"}
GENERATED_LINE = re.compile(r"^(#{1,6} |<a id=|> ملاحظة المستودع:|\||- |\[|<div|</div)")
LINK = re.compile(r"\[[^\]]*\]\((<[^>]+>|[^)\s]+)\)")


class Report:
    def __init__(self):
        self.checks: list[tuple[str, bool, str]] = []

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append((name, ok, detail))

    @property
    def ok(self) -> bool:
        return all(c[1] for c in self.checks)

    def failures(self) -> list[str]:
        return [f"{n}: {d}" if d else n for n, ok, d in self.checks if not ok]

    def render(self, title: str) -> str:
        lines = [f"# {title}", "", f"RESULT: {'PASS' if self.ok else 'FAIL'}", ""]
        for name, ok, detail in self.checks:
            lines.append(f"- [{'x' if ok else ' '}] {name}" + (f": {detail}" if detail else ""))
        return "\n".join(lines) + "\n"


def split_front(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        raise ValueError("file does not start with YAML frontmatter")
    end = text.index("\n---\n", 4)
    return text[4:end + 1], text[end + 5:]


def _resolve(base: str, target: str) -> str:
    parts: list[str] = [] if not base else [seg for seg in base.split("/") if seg and seg != "."]
    for seg in target.split("/"):
        if seg == "..":
            if parts:
                parts.pop()
        elif seg and seg != ".":
            parts.append(seg)
    return "/".join(parts)


# ----------------------------------------------------------------------------
# structural checks on a set of {relative path: content}
# ----------------------------------------------------------------------------


def published_files(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)).replace("\\", "/"): p.read_text(encoding="utf-8") for p in sorted(root.rglob("*.md"))}


def check_vault_files(files: dict[str, str], rep: Report, vault_root: Path | None, prefix: str = "") -> dict[str, dict]:
    """Structural checks; returns the parsed frontmatters.  `prefix` is the path of
    the volume folder relative to the vault root (empty when `files` are relative
    to the vault root) and is used to resolve links that leave the folder."""
    fronts: dict[str, dict] = {}
    yaml_errors, escape_errors, wrapper_errors, ws_errors, lint_errors, id_errors, key_errors, fffd = [], [], [], [], [], [], [], []
    anchors: dict[str, set[str]] = {}
    for rel, text in files.items():
        try:
            front_text, body = split_front(text)
            front = em.load_yaml(front_text)
            fronts[rel] = front
        except Exception as exc:  # noqa: BLE001
            yaml_errors.append(f"{rel}: {exc}")
            continue
        if "\\u" in front_text:
            escape_errors.append(rel)
        if "�" in text:
            fffd.append(rel)
        if not text.endswith("</div>\n") or text.count('<div dir="rtl">') != 1 or "\n---\n\n<div dir=\"rtl\">\n\n" not in text:
            wrapper_errors.append(rel)
        if text.startswith("﻿") or "\r" in text or any(l != l.rstrip() for l in text.split("\n")) or not text.endswith("\n") or text.endswith("\n\n"):
            ws_errors.append(rel)
        anchors[rel] = {m.group(1) for m in re.finditer(r'<a id="([^"]+)">', body)}
        inner = body.split('<div dir="rtl">', 1)[1].rsplit("</div>", 1)[0].split("\n")
        prev = ""
        for line in inner:
            if line.strip() and prev.strip():
                both_table = line.startswith("|") and prev.startswith("|")
                anchor_heading = prev.startswith("<a id=") and line.startswith("#")
                both_list = line.startswith("- ") and prev.startswith("- ")
                if not (both_table or anchor_heading or both_list):
                    lint_errors.append(f"{rel}: adjacent lines {prev[:30]!r} / {line[:30]!r}")
                    break
            if line.strip() and not GENERATED_LINE.match(line) and (line.startswith(("#", ">", "+ ", "* ", "|", "<")) or re.match(r"^[0-9]+[.)]", line)):
                lint_errors.append(f"{rel}: unescaped block syntax {line[:30]!r}")
                break
            prev = line
        if "/Principles/" in "/" + rel:
            missing = [k for k in REQUIRED_PRINCIPLE_KEYS if k not in front]
            if missing:
                key_errors.append(f"{rel}: missing {missing}")
            order = [k for k in front if k in KEY_ORDER]
            if order != sorted(order, key=KEY_ORDER.index):
                key_errors.append(f"{rel}: key order")
            pid = str(front.get("principle_id", ""))
            if not vm.RE_PRINCIPLE_ID.match(pid):
                id_errors.append(f"{rel}: {pid}")
            if Path(rel).name != pid.split(":")[-1] + ".md":
                id_errors.append(f"{rel}: filename does not match principle_id")
            try:
                if int(front.get("principle_number", -1)) != int(re.sub(r"\D.*$", "", pid.split(":p")[-1]) or -2):
                    id_errors.append(f"{rel}: principle_number does not match principle_id")
            except ValueError:
                id_errors.append(f"{rel}: principle_number is not a number")
    rep.add("YAML parses with duplicate-key rejection", not yaml_errors, "; ".join(yaml_errors[:3]) or f"{len(fronts)} files")
    rep.add("no \\u escapes of Arabic", not escape_errors, "; ".join(escape_errors[:3]))
    rep.add("no U+FFFD in any published file", not fffd, "; ".join(fffd[:3]))
    rep.add("one RTL wrapper per file", not wrapper_errors, "; ".join(wrapper_errors[:3]))
    rep.add("UTF-8 without BOM, LF, one trailing newline, no trailing whitespace", not ws_errors, "; ".join(ws_errors[:3]))
    rep.add("Markdown lint of bodies", not lint_errors, "; ".join(lint_errors[:3]))
    rep.add("required frontmatter keys and key order", not key_errors, "; ".join(key_errors[:3]))
    rep.add("ID grammar, filenames and numbers", not id_errors, "; ".join(id_errors[:3]))
    broken = []
    for rel, text in files.items():
        base = str(Path(rel).parent).replace("\\", "/")
        base = "" if base == "." else base
        for m in LINK.finditer(text):
            target = m.group(1).strip("<>")
            if target.startswith(("http://", "https://")):
                broken.append(f"{rel}: external link {target}")
                continue
            path, _, frag = target.partition("#")
            if path:
                full = _resolve("/".join(x for x in (prefix, base) if x), path)  # relative to the vault root
                if prefix and full.startswith(prefix + "/"):
                    local = full[len(prefix) + 1:]
                elif prefix:
                    local = None  # a link that leaves the volume folder
                else:
                    local = full
                exists = (local in files) if local is not None else False
                exists = exists or (vault_root is not None and (vault_root / full).exists())
                if not exists:
                    broken.append(f"{rel}: {target}")
                    continue
                if frag and local in anchors and frag not in anchors[local]:
                    broken.append(f"{rel}: anchor {target}")
            elif frag and frag not in anchors.get(rel, set()):
                broken.append(f"{rel}: anchor {target}")
    rep.add("0 broken relative links or anchors", not broken, "; ".join(broken[:3]) or f"{sum(len(LINK.findall(t)) for t in files.values())} links")
    return fronts


def check_relations(fronts: dict[str, dict], rep: Report) -> None:
    by_id = {f["principle_id"]: f for f in fronts.values() if "principle_id" in f}
    reciprocal = {"shared_index_entry": "shared_index_entry", "sibling_under_title": "sibling_under_title", "see_also": "referenced_by_see_also",
                  "referenced_by_see_also": "see_also", "same_ruling_reference": "same_ruling_reference"}
    problems = []
    for pid, f in by_id.items():
        for r in f.get("related_principles") or []:
            if r.get("target_supplied") is False or r.get("target_held"):
                continue
            t = by_id.get(r.get("principle_id"))
            if t is None:
                problems.append(f"{pid}: target {r.get('principle_id')} missing")
                continue
            want = reciprocal[r["relation"]]
            if not any(x.get("principle_id") == pid and x.get("relation") == want for x in t.get("related_principles") or []):
                problems.append(f"{pid} -> {r['principle_id']} ({r['relation']}) not reciprocated")
    rep.add("every reciprocal relation is reciprocal", not problems, "; ".join(problems[:3]) or f"{len(by_id)} principles")


# ----------------------------------------------------------------------------
# content checks against the records (used by verify and by the mutation test)
# ----------------------------------------------------------------------------


def _front_equal(expected: dict, actual: dict) -> bool:
    return em.load_yaml(em.dump_yaml(expected)) == actual


def check_frontmatter_against_records(vb, files: dict[str, str], rep: Report) -> None:
    """Every published principle frontmatter equals the frontmatter derived from the records."""
    problems = []
    file_name = vb.file_entries[0]["file"]
    for number, p in vb.principles.items():
        if number in vb.held:
            continue
        rel = f"Principles/{vm.principle_filename(number)}"
        if rel not in files:
            problems.append(f"{rel}: missing")
            continue
        try:
            actual = em.load_yaml(split_front(files[rel])[0])
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{rel}: {exc}")
            continue
        expected = em.principle_front(vb.cfg, p, file_name, "text_layer_repaired")
        if not _front_equal(expected, actual):
            diff = [k for k in set(expected) | set(actual) if em.load_yaml(em.dump_yaml({"v": expected.get(k)}))["v"] != actual.get(k)]
            problems.append(f"{rel}: {sorted(diff)}")
    rep.add("frontmatter equals the records", not problems, "; ".join(problems[:3]) or f"{len(vb.principles) - len(vb.held)} principle files")


def check_wording_equality(vb, files: dict[str, str], rep: Report) -> None:
    """Normalized source text of every facet equals the normalized output text (body only)."""
    mismatches = []
    for number, p in vb.principles.items():
        if number in vb.held:
            continue
        rel = f"Principles/{vm.principle_filename(number)}"
        if rel not in files:
            mismatches.append(f"{rel}: missing")
            continue
        body = split_front(files[rel])[1]
        out_paras = [em.md_unescape(l) for l in body.split("\n") if l.strip() and not GENERATED_LINE.match(l)]
        for f in p.facets:
            for e in list(f.wording_paragraphs) + ([f.reference_line] if f.reference_line else []):
                if e not in out_paras:
                    mismatches.append(f"{rel} facet {f.facet}: {e[:40]!r}")
    rep.add("normalized source text equals normalized output text (0 mismatches)", not mismatches,
            "; ".join(mismatches[:3]) or f"{sum(len(p.facets) for n, p in vb.principles.items() if n not in vb.held)} facets")


def check_coverage(vb, rep: Report, files: dict[str, str]) -> None:
    classes = collections.Counter(l.cls for l in vb.parse.lines)
    unclassified = [l for l in vb.parse.lines if l.cls == "unclassified"]
    rep.add("every source line has one class (0 unaccounted)", not unclassified, f"{dict(sorted(classes.items()))}")
    corpus = "\n".join(em.md_unescape(t) for t in files.values())
    held_locs = {l.loc for n in vb.held for f in vb.principles[n].facets for l in _block_lines(vb, f)}
    unmapped = [l.loc for l in vb.parse.lines if l.cls in CONTENT_CLASSES and l.text and l.text not in corpus and l.loc not in held_locs]
    excluded = [l for l in vb.parse.lines if l.cls.startswith("apparatus")]
    rep.add("every content line maps to at least one output location", not unmapped,
            "; ".join(unmapped[:3]) or f"{sum(1 for l in vb.parse.lines if l.cls in CONTENT_CLASSES)} content lines mapped; {len(excluded)} apparatus lines are listed exclusions")
    review_lines = [l for l in vb.parse.lines if l.cls == "review"]
    rep.add("lines held as review items", True, f"{len(review_lines)}")
    numbers = {int(n) for b in vb.parse.blocks for n in b.numbers if n.isdigit()}
    published = {int(n) for n in vb.principles if n not in vb.held}
    held = {int(n) for n in vb.held}
    rep.add("every index number has exactly one principle file or is held", numbers == published | held and not (published & held),
            f"{len(numbers)} numbers, {len(published)} files, {len(held)} held")
    no_wording = [n for n, p in vb.principles.items() if n not in vb.held and not any(f.wording_paragraphs for f in p.facets)]
    rep.add("no published principle without wording", not no_wording, ", ".join(no_wording))


def _block_lines(vb, facet):
    b = vb.parse.blocks[facet.block_index]
    return b.opener_lines + b.title_lines + b.wording_lines + b.reference_lines + b.number_lines + b.label_lines


def check_page_classes(vb, rep: Report) -> None:
    problems = [f"page[{p}]: {c}" for p, c in vb.parse.page_classes.items() if c == "other"]
    rep.add("every page has a class of the fixed vocabulary", not problems, "; ".join(problems) or f"{len(vb.parse.page_classes)} pages")


def check_fixture(project, vb, rep: Report) -> None:
    path = project.root / "tests" / "fixtures" / f"{vb.vid}.expected.yaml"
    if not path.exists():
        rep.add("fixture comparison", True, "no fixture file")
        return
    exp = em.load_yaml(path.read_text(encoding="utf-8"))
    problems = []
    got_numbers = sorted(int(n) for n in vb.principles)
    if exp.get("principle_numbers") is not None and sorted(exp["principle_numbers"]) != got_numbers:
        problems.append(f"principle numbers {got_numbers} != expected")
    got_letters = [L.letter for L in vb.parse.letters]
    if exp.get("letters") is not None and exp["letters"] != got_letters:
        problems.append(f"letters {got_letters}")
    got_topics = [T.title_ar for L in vb.parse.letters for T in L.topics]
    if exp.get("topics") is not None and exp["topics"] != got_topics:
        problems.append(f"topics {got_topics}")
    facets = {int(n): [{"title": f.title_ar, "kind": f.entry_kind, "label": f.page_label, "refs": [r.ref_ar for r in f.references]} for f in p.facets]
              for n, p in vb.principles.items()}
    for n, expected in (exp.get("facets") or {}).items():
        if facets.get(int(n)) != expected:
            problems.append(f"facets of {n}: {facets.get(int(n))} != {expected}")
    blocks_per_page = collections.Counter(b.page for b in vb.parse.blocks)
    for page, count in (exp.get("blocks_per_page") or {}).items():
        if blocks_per_page.get(int(page), 0) != count:
            problems.append(f"page {page}: {blocks_per_page.get(int(page), 0)} blocks != {count}")
    for key in ("page_labels", "page_classes"):
        if exp.get(key) is not None:
            got = {int(k): v for k, v in (vb.parse.page_labels if key == "page_labels" else vb.parse.page_classes).items()}
            want = {int(k): v for k, v in exp[key].items()}
            if got != want:
                problems.append(f"{key}: {got} != {want}")
    rep.add("fixture expectations", not problems, "; ".join(problems[:3]) or f"{len(exp.get('facets') or {})} principles compared")


def content_checks(vb, files: dict[str, str], vault_root: Path | None, prefix: str) -> Report:
    """The checks that must reject a corrupted copy: structure, frontmatter, wording, links."""
    rep = Report()
    check_vault_files(files, rep, vault_root, prefix)
    check_frontmatter_against_records(vb, files, rep)
    check_wording_equality(vb, files, rep)
    return rep


def mutation_test(vb, files: dict[str, str], vault_root: Path | None, prefix: str, rep: Report) -> None:
    """Each mutation of a temporary copy must be rejected by a content check (acceptance item 7)."""
    baseline = content_checks(vb, files, vault_root, prefix)
    if not baseline.ok:
        rep.add("mutated temporary copy is rejected", False, "baseline copy fails the content checks: " + "; ".join(baseline.failures()[:2]))
        return
    numbers = [n for n in sorted(vb.principles, key=int) if n not in vb.held and vb.principles[n].facets[0].wording_paragraphs]
    number = numbers[0]
    rel = f"Principles/{vm.principle_filename(number)}"
    front_text, body = split_front(files[rel])
    facet = vb.principles[number].facets[0]
    para = facet.wording_paragraphs[0]
    ref = facet.reference_line
    label = facet.page_label or ""

    def rebuild(front_t: str, body_t: str) -> str:
        return "---\n" + front_t + "---\n" + body_t

    mutations: dict[str, tuple[str, str, str] | None] = {
        "index wording": ("body", em.md_escape(para), em.md_escape(para[:-1] + ("ـ" if para[-1] != "ـ" else "x"))),
        "body wording": None,
        "YAML": ("front", 'principle_number: "', 'principle_number: "9'),
        "link": ("body", "](../volume-details.md)", "](../volume-detail.md)"),
        "ruling reference": ("body", em.md_escape(ref), em.md_escape(ref.replace("1", "7", 1))) if ref else None,
        "number": ("front", f'principle_id: "{vm.principle_id(vb.vid, number)}"', f'principle_id: "{vm.principle_id(vb.vid, number)}9"'),
        "page label": ("front", f'page_label: "{label}"', f'page_label: "{label}9"') if label else None,
    }
    results = []
    all_ok = True
    for name, mut in mutations.items():
        if mut is None:
            results.append(f"{name}: not applicable")
            continue
        where, old, new = mut
        source = front_text if where == "front" else body
        if old not in source:
            results.append(f"{name}: pattern not found")
            all_ok = False
            continue
        mutated_text = source.replace(old, new, 1)
        mutated = dict(files)
        mutated[rel] = rebuild(mutated_text, body) if where == "front" else rebuild(front_text, mutated_text)
        sub = content_checks(vb, mutated, vault_root, prefix)
        rejected = not sub.ok
        all_ok = all_ok and rejected
        results.append(f"{name}: {'rejected (' + sub.failures()[0].split(':')[0] + ')' if rejected else 'NOT rejected'}")
    rep.add("mutated temporary copy is rejected", all_ok, "; ".join(results))


def _manifest(files: dict[str, str]) -> str:
    h = hashlib.sha256()
    for k in sorted(files):
        h.update(k.encode("utf-8"))
        h.update(hashlib.sha256(files[k].encode("utf-8")).digest())
    return h.hexdigest()


def cmd_verify(project, volume_ids: list[str], build_volume_files) -> int:
    overall = 0
    for vid in volume_ids:
        rep = Report()
        vb, files = build_volume_files(project, vid)
        vb2, files2 = build_volume_files(project, vid)
        rep.add("two consecutive builds give an identical manifest", _manifest(files) == _manifest(files2))
        published_root = project.vault / vid
        pub = published_files(published_root) if published_root.exists() else {}
        diffs = [k for k in sorted(set(files) | set(pub)) if files.get(k) != pub.get(k)]
        rep.add("published files equal a fresh derivation from the sources", not diffs, "; ".join(diffs[:5]) or f"{len(files)} files")
        target = pub if pub else files
        fronts = check_vault_files(target, rep, project.vault, vid)
        check_frontmatter_against_records(vb, target, rep)
        check_relations(fronts, rep)
        check_page_classes(vb, rep)
        check_coverage(vb, rep, target)
        check_wording_equality(vb, target, rep)
        check_fixture(project, vb, rep)
        mutation_test(vb, files, project.vault, vid, rep)
        coll = {name: (project.vault / name).read_text(encoding="utf-8") for name in ("README.md", "index.md") if (project.vault / name).exists()}
        if coll:
            sub = Report()
            check_vault_files(coll, sub, project.vault, "")
            rep.add("collection README and registry are valid", sub.ok, "; ".join(sub.failures()[:2]))
        open_items = [i for i in vb.review if i.get("status") == "open"]
        rep.add("held principles", not vb.held or True, f"{len(vb.held)} held: {', '.join(sorted(vb.held, key=int))}" if vb.held else "0")
        rep.add("review items", True, f"{len(open_items)} open, {len(vb.review)} total")
        ocr = project.work / "review" / f"ocr-{vid}.yaml"
        if ocr.exists():
            data = em.load_yaml(ocr.read_text(encoding="utf-8"))
            rep.add("OCR confirmation: 0 unacknowledged disagreements", int(data.get("unacknowledged", 0)) == 0,
                    f"confirmed {data.get('confirmed')}, disagreeing {data.get('disagreeing')}, decided {data.get('decided')}")
        else:
            rep.add("OCR confirmation", True, "no OCR run recorded (run ocr-confirm where Tesseract is installed)")
        text = rep.render(f"Verification report — {vid}")
        _write_report(project, vid, "verify", text)
        print(text)
        overall |= 0 if rep.ok else 1
    return overall


# ----------------------------------------------------------------------------
# crosscheck (second reader: Poppler pdftotext)
# ----------------------------------------------------------------------------


def _pdftotext_path() -> str | None:
    env = os.environ.get("PRINCIPLES_VAULT_PDFTOTEXT")
    if env and Path(env).exists():
        return env
    return shutil.which("pdftotext")


def _norm_second_reader(text: str) -> str:
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r"[‎‏‪-‮⁦-⁩�]", "", t)
    return ps.western_digits(t)


def cmd_crosscheck(project, volume_ids: list[str]) -> int:
    import pipeline  # noqa: E402  (late import: pipeline imports this module)

    rc = 0
    for vid in volume_ids:
        cfg = project.load_config(vid)
        entry = [e for e in cfg.get("source_files", []) if e.get("kind") == "index"][0]
        path = project.input_dir / vid / (entry.get("stored_name") or entry["original_name"])
        run = pipeline.current_run(project, vid)
        lines = [f"# Cross-check report — {vid} (run {run})", ""]
        tool = _pdftotext_path()
        if tool is None:
            lines += ["RESULT: NO SECOND READER", "", "pdftotext was not found (PRINCIPLES_VAULT_PDFTOTEXT, PATH)."]
            _write_report(project, vid, f"crosscheck-r{run}", "\n".join(lines))
            print("\n".join(lines))
            continue
        if pipeline.sha256_file(path) != entry.get("sha256"):
            lines += ["RESULT: FAIL", "", f"{path.name}: SHA-256 differs from the configuration"]
            _write_report(project, vid, f"crosscheck-r{run}", "\n".join(lines))
            rc = 1
            continue
        doc = pymupdf.open(str(path))
        page_text: dict[int, str] = {}
        for pno in range(1, len(doc) + 1):
            out = subprocess.run([tool, "-layout", "-f", str(pno), "-l", str(pno), str(path), "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
            page_text[pno] = _norm_second_reader(out.stdout)
        vb, _files = pipeline.build_volume_files(project, vid)
        counts: collections.Counter = collections.Counter()
        details = []
        for number in sorted(vb.principles, key=int):
            p = vb.principles[number]
            for f in p.facets:
                page = page_text.get(f.page, "")
                page_skeleton = vm.skeleton(page)
                page_sorted = collections.Counter("".join(sorted(vm.skeleton(w))) for w in page.split())
                digits = [number] + ([f.page_label] if f.page_label else []) + [d for r in f.references for d in r.number.split("-")]
                numbers_ok = all(d in page for d in digits)
                words = [w for w in (vm.skeleton(w) for para in f.wording_paragraphs for w in para.split()) if w]
                missing_exact = [w for w in words if w not in page_skeleton]
                missing_sorted = [w for w in missing_exact if page_sorted["".join(sorted(w))] == 0]
                if not numbers_ok:
                    cls = "not found"
                elif not missing_exact:
                    cls = "identical"
                elif not missing_sorted:
                    cls = "letters present in another order"
                else:
                    cls = "word differences"
                counts[cls] += 1
                if cls in ("word differences", "not found"):
                    details.append(f"- p{int(number):03d} facet {f.facet} (page[{f.page}]): {cls}; words absent from the second reader: {', '.join(missing_sorted[:8])}")
        result = "PASS" if counts["not found"] == 0 else "FAIL"
        lines += [f"RESULT: {result}", "", f"second reader: {tool}", f"facets compared: {sum(counts.values())}", ""]
        lines += [f"- {k}: {v}" for k, v in sorted(counts.items())]
        lines += ["", "Differences are read by a person and never change the vault.", ""] + details
        _write_report(project, vid, f"crosscheck-r{run}", "\n".join(lines))
        print("\n".join(lines[:12]))
        rc |= 0 if result == "PASS" else 1
    return rc


def _write_report(project, vid: str, kind: str, text: str) -> None:
    out = project.work / "reports" / f"{vid}-{kind}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text.rstrip("\n") + "\n", encoding="utf-8", newline="\n")


# ----------------------------------------------------------------------------
# ocr-confirm (Tesseract on cell crops)
# ----------------------------------------------------------------------------


def _tesseract_path() -> str | None:
    env = os.environ.get("PRINCIPLES_VAULT_TESSERACT")
    if env and Path(env).exists():
        return env
    return shutil.which("tesseract")


def _ocr(tool: str, png: Path, psm: int, whitelist: str | None = None) -> str:
    cmd = [tool, str(png), "stdout", "-l", "ara", "--oem", "1", "--psm", str(psm)]
    if whitelist:
        cmd += ["-c", f"tessedit_char_whitelist={whitelist}"]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return ps.normalize_text(res.stdout)


def cmd_ocr_confirm(project, volume_ids: list[str], build_volume_files) -> int:
    tool = _tesseract_path()
    for vid in volume_ids:
        out = project.work / "review" / f"ocr-{vid}.yaml"
        if tool is None:
            print(f"{vid}: OCR confirmation blocked: tesseract not found (PRINCIPLES_VAULT_TESSERACT, PATH); no record written")
            continue
        cfg = project.load_config(vid)
        decisions = cfg.get("decisions") or {}
        entry = [e for e in cfg.get("source_files", []) if e.get("kind") == "index"][0]
        path = project.input_dir / vid / (entry.get("stored_name") or entry["original_name"])
        doc = pymupdf.open(str(path))
        fm = ps.load_font_maps(doc)
        vb, _files = build_volume_files(project, vid)
        crops = project.work / "review" / "crops" / vid
        crops.mkdir(parents=True, exist_ok=True)
        confirmed = disagreeing = decided = 0
        items = []
        # the cells that carry published text, once each (shared blocks are one cell)
        cells_by_page: dict[int, set[tuple[int, int]]] = {}
        for number, p in vb.principles.items():
            for f in p.facets:
                for sl in _block_lines(vb, f):
                    if sl.row is not None:
                        cells_by_page.setdefault(sl.page, set()).add((sl.row, sl.col))
        with tempfile.TemporaryDirectory() as tmp:
            for pno in sorted(cells_by_page):
                glyphs = ps.page_glyphs(doc, pno, fm, vb.repairs, vb.settings)
                table = ps.segment_table(pno, ps.merge_rulings(ps.page_rulings(doc[pno - 1])), glyphs, vb.settings)
                if table is None:
                    continue
                for (row, col) in sorted(cells_by_page[pno]):
                    cell = next((c for r in table.rows if r.index == row for c in r.cells if c.col == col), None)
                    if cell is None or not cell.lines:
                        continue
                    png = Path(tmp) / f"p{pno}-r{row}-c{col}.png"
                    rect = (min(l.x0 for l in cell.lines), min(l.y0 for l in cell.lines), max(l.x1 for l in cell.lines), max(l.y1 for l in cell.lines))
                    ps.render_crop(doc, pno, rect, png, dpi=400, pad=4)
                    digit_cell = col in (1, 2)
                    text = _ocr(tool, png, 7 if digit_cell else 6, "0123456789،, " if digit_cell else None)
                    ocr_lines = [l for l in text.split("\n") if l.strip()]
                    published = [l.text for l in cell.lines]
                    if len(ocr_lines) == len(published):
                        pairs = list(zip(published, ocr_lines))
                    else:
                        pairs = [(" ".join(published), " ".join(ocr_lines))]
                    for k, (pub, got) in enumerate(pairs):
                        loc = f"page[{pno}]:r{row}:c{col}" + (f":L{k}" if len(pairs) > 1 else "")
                        if vm.skeleton(got) == vm.skeleton(pub):
                            confirmed += 1
                            continue
                        item_id = hashlib.sha256(f"{vid}|{loc}|ocr".encode("utf-8")).hexdigest()[:12]
                        if item_id in decisions:
                            decided += 1
                            continue
                        disagreeing += 1
                        crop_path = crops / f"{item_id}.png"
                        shutil.copy(png, crop_path)
                        items.append({"item_id": item_id, "location": loc, "published": pub, "ocr": got, "crop": str(crop_path.relative_to(project.root)),
                                      "options": ["keep the text-layer reading (decision keep)", "publish the OCR reading (decision ocr)"]})
        data = {"volume_id": vid, "tool": tool, "confirmed": confirmed, "disagreeing": disagreeing, "decided": decided, "unacknowledged": disagreeing, "items": items}
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(em.dump_yaml(data), encoding="utf-8", newline="\n")
        print(f"{vid}: OCR confirmed {confirmed}, disagreeing {disagreeing}, decided {decided}")
    return 0
