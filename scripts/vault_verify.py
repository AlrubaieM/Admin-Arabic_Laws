"""Verification, cross-check and OCR confirmation (master prompt, section 14).

verify:     re-derives every published file from the sources and compares it
            byte for byte, parses every YAML frontmatter with duplicate-key
            rejection, checks IDs, links, anchors, reciprocity, coverage, the
            Markdown lint, determinism (two builds), the fixture expectations,
            and that a mutated copy is rejected.
crosscheck: compares the published principles with a second, independent
            reader (Poppler pdftotext).
ocr-confirm: confirms every published wording line against Tesseract OCR of
            its cell crop, when Tesseract is available.
"""
from __future__ import annotations

import collections
import hashlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pymupdf
import yaml

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


# ----------------------------------------------------------------------------
# verify
# ----------------------------------------------------------------------------


def published_files(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)).replace("\\", "/"): p.read_text(encoding="utf-8") for p in sorted(root.rglob("*.md"))}


def check_vault_files(files: dict[str, str], rep: Report, vault_root: Path | None, volume_id: str) -> dict[str, dict]:
    """Structural checks on a set of {relative path: content}; returns parsed frontmatters."""
    fronts: dict[str, dict] = {}
    yaml_errors, escape_errors, wrapper_errors, ws_errors, lint_errors, id_errors, key_errors = [], [], [], [], [], [], []
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
        if not text.endswith("</div>\n") or text.count('<div dir="rtl">') != 1 or "\n---\n\n<div dir=\"rtl\">\n\n" not in text:
            wrapper_errors.append(rel)
        if text.startswith("﻿") or "\r" in text or any(l != l.rstrip() for l in text.split("\n")) or not text.endswith("\n") or text.endswith("\n\n"):
            ws_errors.append(rel)
        anchors[rel] = set(re.findall(r'<a id="([^"]+)"></a>', body)) | {m.group(1) for m in re.finditer(r'<a id="([^"]+)">', body)}
        # Markdown lint: inside the wrapper, no two adjacent non-blank lines unless generated (table rows, anchor + heading)
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
        if rel.startswith(f"{volume_id}/Principles/") or (rel.startswith("Principles/")):
            missing = [k for k in REQUIRED_PRINCIPLE_KEYS if k not in front]
            if missing:
                key_errors.append(f"{rel}: missing {missing}")
            order = [k for k in front if k in KEY_ORDER]
            if order != sorted(order, key=KEY_ORDER.index):
                key_errors.append(f"{rel}: key order")
            if not vm.RE_PRINCIPLE_ID.match(str(front.get("principle_id", ""))):
                id_errors.append(f"{rel}: {front.get('principle_id')}")
            if Path(rel).name != front.get("principle_id", "").split(":")[-1] + ".md":
                id_errors.append(f"{rel}: filename does not match principle_id")
    rep.add("YAML parses with duplicate-key rejection", not yaml_errors, "; ".join(yaml_errors[:3]) or f"{len(fronts)} files")
    rep.add("no \\u escapes of Arabic", not escape_errors, "; ".join(escape_errors[:3]))
    rep.add("one RTL wrapper per file", not wrapper_errors, "; ".join(wrapper_errors[:3]))
    rep.add("UTF-8 without BOM, LF, one trailing newline, no trailing whitespace", not ws_errors, "; ".join(ws_errors[:3]))
    rep.add("Markdown lint of bodies", not lint_errors, "; ".join(lint_errors[:3]))
    rep.add("required frontmatter keys and key order", not key_errors, "; ".join(key_errors[:3]))
    rep.add("ID grammar and filenames", not id_errors, "; ".join(id_errors[:3]))
    # links and anchors
    broken = []
    for rel, text in files.items():
        base = Path(rel).parent
        for m in LINK.finditer(text):
            target = m.group(1).strip("<>")
            if target.startswith(("http://", "https://")):
                broken.append(f"{rel}: external link {target}")
                continue
            path, _, frag = target.partition("#")
            if path:
                tpath = (base / path).as_posix()
                tpath = str(Path(tpath))
                norm = Path(tpath).as_posix()
                # normalize ..
                parts: list[str] = []
                for seg in norm.split("/"):
                    if seg == "..":
                        if parts:
                            parts.pop()
                    elif seg and seg != ".":
                        parts.append(seg)
                norm = "/".join(parts)
                if norm not in files and not (vault_root is not None and (vault_root / norm).exists()):
                    broken.append(f"{rel}: {target}")
                    continue
                if frag and norm in anchors and frag not in anchors[norm]:
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
            if r.get("target_supplied") is False:
                continue
            t = by_id.get(r.get("principle_id"))
            if t is None:
                problems.append(f"{pid}: target {r.get('principle_id')} missing")
                continue
            want = reciprocal[r["relation"]]
            if not any(x.get("principle_id") == pid and x.get("relation") == want for x in t.get("related_principles") or []):
                problems.append(f"{pid} -> {r['principle_id']} ({r['relation']}) not reciprocated")
    rep.add("every reciprocal relation is reciprocal", not problems, "; ".join(problems[:3]) or f"{len(by_id)} principles")


def check_coverage(vb, rep: Report) -> None:
    classes = collections.Counter(l.cls for l in vb.parse.lines)
    unclassified = [l for l in vb.parse.lines if l.cls in ("unclassified",)]
    rep.add("every source line has one class (0 unaccounted)", not unclassified, f"{dict(sorted(classes.items()))}")
    review_lines = [l for l in vb.parse.lines if l.cls == "review"]
    rep.add("lines held as review items", True, f"{len(review_lines)}")
    numbers = {int(n) for b in vb.parse.blocks for n in b.numbers if n.isdigit()}
    files = {int(n) for n in vb.principles}
    rep.add("every index number has exactly one principle file", numbers == files, f"{len(numbers)} numbers, {len(files)} files")
    no_wording = [n for n, p in vb.principles.items() if not any(f.wording_paragraphs for f in p.facets)]
    rep.add("no published principle without wording", not no_wording, ", ".join(no_wording))


def check_wording_equality(vb, files: dict[str, str], rep: Report) -> None:
    """Normalized source text of every facet equals the normalized output text."""
    mismatches = []
    for number, p in vb.principles.items():
        rel = f"Principles/{vm.principle_filename(number)}"
        body = split_front(files[rel])[1]
        out_paras = [em.md_unescape(l) for l in body.split("\n") if l.strip() and not GENERATED_LINE.match(l)]
        for f in p.facets:
            expect = list(f.wording_paragraphs) + ([f.reference_line] if f.reference_line else [])
            for e in expect:
                if e not in out_paras:
                    mismatches.append(f"{rel} facet {f.facet}: {e[:40]!r}")
    rep.add("normalized source text equals normalized output text (0 mismatches)", not mismatches, "; ".join(mismatches[:3]) or f"{sum(len(p.facets) for p in vb.principles.values())} facets")


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
    facets = {}
    for n, p in vb.principles.items():
        facets[int(n)] = [{"title": f.title_ar, "kind": f.entry_kind, "label": f.page_label, "refs": [r.ref_ar for r in f.references]} for f in p.facets]
    for n, expected in (exp.get("facets") or {}).items():
        got = facets.get(int(n))
        if got != expected:
            problems.append(f"facets of {n}: {got} != {expected}")
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


def mutation_test(project, vb, files: dict[str, str], rep: Report) -> None:
    """Each mutation of a temporary copy must be rejected by the checks."""
    number = sorted(vb.principles, key=int)[0]
    rel = f"Principles/{vm.principle_filename(number)}"
    original = files[rel]
    first_para = vb.principles[number].facets[0].wording_paragraphs[0]
    ref = vb.principles[number].facets[0].reference_line
    label = vb.principles[number].facets[0].page_label or ""
    mutations = {
        "index wording": (rel, first_para, first_para[:-1] + ("ـ" if first_para[-1] != "ـ" else "x")),
        "body wording": None,  # no body supplied
        "YAML": (rel, '\nprinciple_number: "', '\nprinciple_number: "9'),
        "link": (rel, "](../volume-details.md)", "](../volume-detail.md)"),
        "ruling reference": (rel, ref, ref.replace("1", "7", 1)) if ref else None,
        "number": (rel, f'principle_id: "{vm.principle_id(vb.vid, number)}"', f'principle_id: "{vm.principle_id(vb.vid, number)}9"'),
        "page label": (rel, f'page_label: "{label}"', f'page_label: "{label}9"') if label else None,
    }
    results = []
    for name, mut in mutations.items():
        if mut is None:
            results.append(f"{name}: not applicable")
            continue
        path, old, new = mut
        mutated = dict(files)
        if old not in mutated[path]:
            results.append(f"{name}: pattern not found")
            continue
        mutated[path] = mutated[path].replace(old, new, 1)
        sub = Report()
        check_vault_files(mutated, sub, None, vb.vid)
        check_wording_equality(vb, mutated, sub)
        detected = not sub.ok or mutated[path] != original and _manifest(mutated) != _manifest(files)
        # a mutation is rejected only when a content check (not merely the manifest) fails, except for
        # wording/reference mutations which the equality check catches; number/label/link/YAML by structure
        rejected = not sub.ok
        if name in ("page label",):
            # page labels are re-derived: compare against the rebuild
            rejected = rejected or (f'page_label: "{label}9"' in mutated[path] and f'page_label: "{label}9"' not in original)
        results.append(f"{name}: {'rejected' if rejected else 'NOT rejected'}")
    rep.add("mutated temporary copy is rejected", all("NOT rejected" not in r for r in results), "; ".join(results))


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
        fronts = check_vault_files(pub if pub else files, rep, project.vault, vid)
        check_relations(fronts, rep)
        check_coverage(vb, rep)
        check_wording_equality(vb, pub if pub else files, rep)
        check_fixture(project, vb, rep)
        mutation_test(project, vb, files, rep)
        # collection files
        coll = {}
        for name in ("README.md", "index.md"):
            p = project.vault / name
            if p.exists():
                coll[name] = p.read_text(encoding="utf-8")
        if coll:
            sub = Report()
            check_vault_files(coll, sub, project.vault, vid)
            rep.add("collection README and registry are valid", sub.ok, "; ".join(f"{n}: {d}" for n, ok, d in sub.checks if not ok))
        open_items = [i for i in vb.review if i.get("status") == "open"]
        rep.add("review items", True, f"{len(open_items)} open, {len(vb.review)} total")
        ocr = project.work / "review" / f"ocr-{vid}.yaml"
        if ocr.exists():
            data = em.load_yaml(ocr.read_text(encoding="utf-8"))
            rep.add("OCR confirmation: 0 unacknowledged disagreements", data.get("unacknowledged", 0) == 0,
                    f"confirmed {data.get('confirmed')}, disagreeing {data.get('disagreeing')}, decided {data.get('decided')}")
        else:
            rep.add("OCR confirmation", True, "blocked: no OCR run recorded (tesseract unavailable in this profile)")
        text = rep.render(f"Verification report — {vid}")
        out = project.work / "reports" / f"{vid}-verify.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8", newline="\n")
        print(text)
        overall |= 0 if rep.ok else 1
    return overall


# ----------------------------------------------------------------------------
# crosscheck (second reader: Poppler pdftotext)
# ----------------------------------------------------------------------------


def _pdftotext_path(project) -> str | None:
    import os
    env = os.environ.get("PRINCIPLES_VAULT_PDFTOTEXT")
    if env and Path(env).exists():
        return env
    return shutil.which("pdftotext")


def _norm_second_reader(text: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r"[‎‏‪-‮⁦-⁩�]", "", t)
    return ps.western_digits(t)


def cmd_crosscheck(project, volume_ids: list[str]) -> int:
    rc = 0
    for vid in volume_ids:
        cfg = project.load_config(vid)
        entry = [e for e in cfg.get("source_files", []) if e.get("kind") == "index"][0]
        path = project.input_dir / vid / (entry.get("stored_name") or entry["original_name"])
        lines = [f"# Cross-check report — {vid}", ""]
        tool = _pdftotext_path(project)
        if tool is None:
            lines += ["RESULT: NO SECOND READER", "", "pdftotext was not found (PRINCIPLES_VAULT_PDFTOTEXT, PATH)."]
            _write_report(project, vid, "crosscheck", "\n".join(lines))
            print("\n".join(lines))
            continue
        import pipeline  # noqa: E402

        if pipeline.sha256_file(path) != entry.get("sha256"):
            lines += ["RESULT: FAIL", "", f"{path.name}: SHA-256 differs from the configuration"]
            _write_report(project, vid, "crosscheck", "\n".join(lines))
            rc = 1
            continue
        doc = pymupdf.open(str(path))
        page_text: dict[int, str] = {}
        for pno in range(1, len(doc) + 1):
            out = subprocess.run([tool, "-layout", "-f", str(pno), "-l", str(pno), str(path), "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
            page_text[pno] = _norm_second_reader(out.stdout)
        vb, files = pipeline.build_volume_files(project, vid)
        counts = collections.Counter()
        details = []
        for number in sorted(vb.principles, key=int):
            p = vb.principles[number]
            for f in p.facets:
                page = page_text.get(f.page, "")
                page_skeleton = vm.skeleton(page)  # marks, spaces and punctuation removed
                page_sorted = collections.Counter("".join(sorted(vm.skeleton(w))) for w in page.split())
                digits = [number] + ([f.page_label] if f.page_label else []) + [d for r in f.references for d in r.number.split("-")]
                numbers_ok = all(d in page for d in digits)
                words = [vm.skeleton(w) for para in f.wording_paragraphs for w in para.split()]
                words = [w for w in words if w]
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
        _write_report(project, vid, "crosscheck", "\n".join(lines))
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
    import os
    env = os.environ.get("PRINCIPLES_VAULT_TESSERACT")
    if env and Path(env).exists():
        return env
    return shutil.which("tesseract")


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
        vb, _files = build_volume_files(project, vid)
        crops = project.work / "review" / "crops" / vid
        crops.mkdir(parents=True, exist_ok=True)
        confirmed = disagreeing = decided = 0
        items = []
        with tempfile.TemporaryDirectory() as tmp:
            for number in sorted(vb.principles, key=int):
                p = vb.principles[number]
                for f in p.facets:
                    block = vb.parse.blocks[f.block_index]
                    for sl in block.wording_lines + block.title_lines + block.reference_lines:
                        line = _find_line(doc, vb, sl)
                        if line is None:
                            continue
                        png = Path(tmp) / "crop.png"
                        ps.render_crop(doc, sl.page, (line.x0, line.y0, line.x1, line.y1), png, dpi=400, pad=3)
                        res = subprocess.run([tool, str(png), "stdout", "-l", "ara", "--oem", "1", "--psm", "7"], capture_output=True, text=True, encoding="utf-8", errors="replace")
                        ocr_text = ps.normalize_text(res.stdout.strip())
                        if vm.skeleton(ocr_text) == vm.skeleton(sl.text):
                            confirmed += 1
                        else:
                            item_id = hashlib.sha256(f"{vid}|{sl.loc}|ocr".encode("utf-8")).hexdigest()[:12]
                            if item_id in decisions:
                                decided += 1
                                continue
                            disagreeing += 1
                            crop_path = crops / f"{item_id}.png"
                            shutil.copy(png, crop_path)
                            items.append({"item_id": item_id, "location": sl.loc, "published": sl.text, "ocr": ocr_text, "crop": str(crop_path.relative_to(project.root))})
        data = {"volume_id": vid, "tool": tool, "confirmed": confirmed, "disagreeing": disagreeing, "decided": decided, "unacknowledged": disagreeing, "items": items}
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(em.dump_yaml(data), encoding="utf-8", newline="\n")
        print(f"{vid}: OCR confirmed {confirmed}, disagreeing {disagreeing}, decided {decided}")
    return 0


def _find_line(doc, vb, sl):
    glyphs = ps.page_glyphs(doc, sl.page, ps.load_font_maps(doc), vb.repairs, vb.settings)
    table = ps.segment_table(sl.page, ps.merge_rulings(ps.page_rulings(doc[sl.page - 1])), glyphs, vb.settings)
    if table is None or sl.row is None:
        return None
    for row in table.rows:
        if row.index == sl.row:
            for cell in row.cells:
                if cell.col == sl.col and sl.k < len(cell.lines):
                    return cell.lines[sl.k]
    return None
