"""Principles vault pipeline: calibrate, build, verify, crosscheck, ocr-confirm.

Usage (through uv, see the master prompt, section 3):
  pipeline.py build [--volume VOLUME_ID | --all] [--project ROOT]
  pipeline.py verify [--volume VOLUME_ID | --all]
  pipeline.py crosscheck [--volume VOLUME_ID | --all]
  pipeline.py calibrate --volume VOLUME_ID
  pipeline.py ocr-confirm [--volume VOLUME_ID | --all]

The project root holds config/volumes/<volume_id>.yaml, Input/<volume_id>/,
work/, and Saudi-Principles/ (master prompt, section 7).  Saudi-Principles/
is a pure function of the sources and the configuration: nothing about the
machine that ran the build is written into it.
"""
from __future__ import annotations

import argparse
import collections
import difflib
import hashlib
import shutil
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pdf_source as ps  # noqa: E402
import vault_emit as em  # noqa: E402
import vault_index as vi  # noqa: E402
import vault_model as vm  # noqa: E402

VAULT_DIR = "Saudi-Principles"


# ----------------------------------------------------------------------------
# Project and configuration
# ----------------------------------------------------------------------------


class Project:
    def __init__(self, root: Path):
        self.root = root
        self.config_dir = root / "config" / "volumes"
        self.input_dir = root / "Input"
        self.work = root / "work"
        self.vault = root / VAULT_DIR

    def volume_ids(self) -> list[str]:
        return sorted(p.stem for p in self.config_dir.glob("*.yaml"))

    def load_config(self, volume_id: str) -> dict:
        path = self.config_dir / f"{volume_id}.yaml"
        cfg = em.load_yaml(path.read_text(encoding="utf-8"))
        if cfg.get("volume_id") != volume_id or not vm.RE_VOLUME_ID.match(volume_id):
            raise SystemExit(f"configuration {path} does not define volume_id {volume_id!r} in the required form")
        return cfg


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def write_yaml(path: Path, data) -> None:
    write_text(path, em.dump_yaml(data))


def read_yaml(path: Path):
    return em.load_yaml(path.read_text(encoding="utf-8"))


def current_run(project: Project, vid: str) -> int:
    path = project.work / "ledger" / f"{vid}.yaml"
    return int(read_yaml(path).get("run_counter", 0)) if path.exists() else 0


def item_id(vid: str, location: str, issue_type: str) -> str:
    return hashlib.sha256(f"{vid}|{location}|{issue_type}".encode("utf-8")).hexdigest()[:12]


# ----------------------------------------------------------------------------
# Extraction of one volume
# ----------------------------------------------------------------------------


class VolumeBuild:
    """Everything derived from the sources of one volume, before emission."""

    def __init__(self, project: Project, cfg: dict):
        self.project = project
        self.cfg = cfg
        self.vid = cfg["volume_id"]
        self.settings = ps.ReaderSettings.from_config(cfg.get("reader"))
        self.repairs = ps.build_repairs(cfg.get("fonts") or [])
        self.parse: vi.IndexParse | None = None
        self.principles: dict[str, vm.Principle] = {}
        self.held: set[str] = set()  # principle numbers held from publication
        self.review: list[dict] = []
        self.anomalies: list[dict] = []
        self.extraction_summary: dict = {}
        self.cataloging_lines: list[str] = []
        self.file_entries: list[dict] = []
        self.doc_path: Path | None = None

    def source_path(self, entry: dict) -> Path:
        name = entry.get("stored_name") or entry["original_name"]
        return self.project.input_dir / self.vid / name

    def add_review(self, issue_type: str, location: str, observed: str, note: str, affected_ids: list[str] | None = None,
                   options: list[str] | None = None, crop: str | None = None) -> dict:
        iid = item_id(self.vid, location, issue_type)
        for existing in self.review:
            if existing["item_id"] == iid:
                return existing
        item = {"item_id": iid, "issue_type": issue_type, "location": location, "affected_ids": affected_ids or [], "observed": observed,
                "note": note, "options": options or [], "status": "open"}
        if crop:
            item["crop"] = crop
        self.review.append(item)
        return item

    def extract(self) -> None:
        index_files = [e for e in self.cfg.get("source_files", []) if e.get("kind") == "index"]
        principle_files = [e for e in self.cfg.get("source_files", []) if e.get("kind") == "principle"]
        if principle_files:
            self.add_review("other", "config:source_files", ", ".join(e.get("stored_name") or e["original_name"] for e in principle_files),
                            "principle files are configured but no body_sections calibration exists; principle bodies are not published in this revision",
                            options=["calibrate the first principle file (Appendix B) and record body_sections"])
        if not index_files:
            raise SystemExit(f"{self.vid}: no index file configured")
        if len(index_files) > 1:
            raise SystemExit(f"{self.vid}: more than one index file is not supported in this revision")
        entry = index_files[0]
        path = self.source_path(entry)
        if not path.exists():
            raise SystemExit(f"{self.vid}: source file missing: {path}")
        digest = sha256_file(path)
        if digest != entry.get("sha256"):
            raise SystemExit(f"{self.vid}: SHA-256 of {path.name} is {digest}, configuration says {entry.get('sha256')}")
        self.doc_path = path
        doc = pymupdf.open(str(path))
        fm = ps.load_font_maps(doc)
        declared = {int(k): v for k, v in (self.cfg.get("page_classes") or {}).items()}
        self.parse = vi.parse_index_file(doc, path.name, fm, self.repairs, self.settings, entry.get("page_label_offset"), declared)
        for i in self.parse.issues:
            self.add_review(i["issue_type"], i["location"], i["observed"], i["note"], options=i.get("options"))
        self.principles, review, anomalies = vm.build_principles(self.parse, self.vid)
        for i in review:
            self.add_review(i["issue_type"], i["location"], i["observed"], i["note"], affected_ids=i.get("affected_ids"))
        self.anomalies.extend(anomalies)
        # unresolved glyphs: review item with a crop; the principle whose block holds the line is held
        crops_dir = self.project.work / "review" / "crops" / self.vid
        for g in self.parse.unresolved_glyphs:
            loc = f"page[{g.page}] x={g.x0:.1f} y={g.oy:.1f}"
            crop = crops_dir / f"{item_id(self.vid, loc, 'glyph')}.png"
            crop.parent.mkdir(parents=True, exist_ok=True)
            ps.render_crop(doc, g.page, (g.x0 - 20, g.y0 - 3, g.x1 + 20, g.y1 + 3), crop, dpi=500)
            self.add_review("glyph", loc, f"font {g.font} gid {g.gid} ({g.status})", "glyph without a resolved text; its line and principle are held",
                            options=["add a glyph repair for this (font, gid) to the configuration"], crop=str(crop.relative_to(self.project.root)))
        for number, p in self.principles.items():
            for f in p.facets:
                block = self.parse.blocks[f.block_index]
                bad = [l for l in block.opener_lines + block.title_lines + block.wording_lines + block.reference_lines if l.unresolved or "�" in l.text]
                if bad:
                    self.held.add(number)
                    self.add_review("wording", bad[0].loc, bad[0].text, "line with an unresolved glyph; principle held",
                                    affected_ids=[vm.principle_id(self.vid, number)], options=["repair the glyph in the configuration", "decision ocr: publish the OCR reading"])
                if not block.wording_paragraphs:
                    self.held.add(number)
                    self.add_review("wording", block.loc, "", "entry block without wording; principle held", affected_ids=[vm.principle_id(self.vid, number)])
        # reviewer-recorded source anomalies from the configuration
        for a in self.cfg.get("source_anomalies") or []:
            rec = dict(a)
            self.anomalies.append(rec)
            if rec.get("principle"):
                p = self.principles.get(str(int(rec["principle"])))
                if p is not None:
                    p.anomalies.append(rec)
        for p in self.principles.values():
            for issue in p.open_issues:
                issue.setdefault("item_id", item_id(self.vid, issue["location"], issue["issue_type"]))
        self._apply_decisions()
        self.cataloging_lines = [l.text for l in self.parse.lines if l.cls == "cataloging_text"]
        page_classes: dict[str, list[int]] = {}
        for pno, cls in self.parse.page_classes.items():
            page_classes.setdefault(cls, []).append(pno)
        numbers = sorted({int(n) for n in self.principles})
        self.file_entries.append({"file": path.name, "kind": "index", "pages": len(doc),
                                  "numbers": f"{numbers[0]}–{numbers[-1]} ({len(numbers)})" if numbers else "",
                                  "extraction": "text_layer_repaired", "page_classes": page_classes})
        self.extraction_summary = {
            "fonts": [{"name": f["name"], "text_layer": f.get("text_layer", "unknown"), "glyph_repairs": len(f.get("glyph_repairs") or {})}
                      for f in self.cfg.get("fonts") or []],
            "text_layer": "defective" if any(f.get("text_layer") == "defective" for f in self.cfg.get("fonts") or []) else "reliable",
            "glyphs_by_status": dict(sorted(self.parse.glyph_status.items())),
            "wrap_joins": sum(len(b.wrap_joins) for b in self.parse.blocks),
            "geometry_spaces": sum(l.gap_spaces for l in self.parse.lines),
        }
        doc.close()

    def _apply_decisions(self) -> None:
        decisions = self.cfg.get("decisions") or {}
        applied: set[str] = set()
        for item in self.review:
            d = decisions.get(item["item_id"])
            if d:
                item["status"] = "decided"
                item["resolution"] = d.get("resolution")
                item["decided_on"] = d.get("decided_on")
                applied.add(item["item_id"])
        for p in self.principles.values():
            p.open_issues = [i for i in p.open_issues if i.get("item_id") not in applied]
        for iid in decisions:
            if iid not in applied:
                self.review.append({"item_id": iid, "issue_type": "other", "location": "config:decisions", "affected_ids": [], "observed": iid,
                                    "note": "decision whose item no longer occurs", "options": [], "status": "stale"})

    # ------------------------------------------------------------------
    def year_span(self) -> dict:
        try:
            from hijridate import Hijri
        except ImportError as exc:
            raise SystemExit("hijridate is required for the volume's computed Gregorian year span; install it into the project .venv") from exc
        y = int(self.cfg["year_hijri"])
        try:
            start = Hijri(y, 1, 1).to_gregorian()
        except Exception as exc:  # outside the converter's range
            raise SystemExit(f"{self.vid}: year {y} AH is outside the range of hijridate: {exc}") from exc
        try:
            end, last_day = Hijri(y, 12, 30).to_gregorian(), 30
        except Exception:
            end, last_day = Hijri(y, 12, 29).to_gregorian(), 29
        return {"start": start.isoformat(), "end": end.isoformat(), "last_day_of_year": last_day, "basis": "computed (hijridate, Umm al-Qura)"}

    # ------------------------------------------------------------------
    def emit(self) -> dict[str, str]:
        """Return {relative path: content} for the volume folder."""
        assert self.parse is not None
        cfg = self.cfg
        files: dict[str, str] = {}
        file_name = self.file_entries[0]["file"]
        for number in sorted(self.principles, key=int):
            if number in self.held:
                continue
            p = self.principles[number]
            front = em.principle_front(cfg, p, file_name, "text_layer_repaired", self.held)
            body = em.principle_body(cfg, p, self.principles, self.held)
            files[f"Principles/{vm.principle_filename(number)}"] = em.rtl_file(front, body)
        held_items = {n: [i["item_id"] for i in self.review if vm.principle_id(self.vid, n) in i.get("affected_ids", [])] for n in self.held}
        files["index.md"] = em.volume_index(cfg, self.parse, self.principles, self.anomalies, held_items)
        files["Indexes/summary-index.md"] = em.preserved_table(cfg, self.parse, "summary")
        files["Indexes/detailed-index.md"] = em.preserved_table(cfg, self.parse, "detailed")
        files["volume-details.md"] = em.volume_details(cfg, self.parse, self.cataloging_lines, self.extraction_summary, self.anomalies,
                                                       self.year_span(), self.file_entries[0], len(self.held))
        return files

    def records(self) -> dict:
        assert self.parse is not None
        return {
            "volume_id": self.vid,
            "page_classes": {str(k): v for k, v in self.parse.page_classes.items()},
            "page_labels": {str(k): v for k, v in self.parse.page_labels.items()},
            "held_principles": sorted(self.held, key=int),
            "lines": [{"loc": l.loc, "class": l.cls, "text": l.text, "bold": round(l.bold, 2), "gap_spaces": l.gap_spaces, "unresolved": l.unresolved}
                      for l in self.parse.lines],
            "blocks": [
                {"loc": b.loc, "kind": b.kind, "numbers": b.numbers, "labels": b.labels, "references": [r.ref_ar for r in b.references],
                 "title_ar": b.title_ar, "title_basis": b.title_basis, "hierarchy": vars(b.hierarchy), "paragraphs": b.wording_paragraphs,
                 "wrap_joins": b.wrap_joins, "continues_block": b.continues_block}
                for b in self.parse.blocks
            ],
            "summary_rows": self.parse.summary_rows,
        }


# ----------------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------------


def volume_summary(cfg: dict, principles_count: int, with_body: int, held: int) -> dict:
    return {"volume_id": cfg["volume_id"], "collection_name_ar": cfg["collection_name_ar"], "collection_name_en": cfg["collection_name_en"],
            "year_hijri": str(cfg["year_hijri"]), "volume_number": str(cfg["volume_number"]), "volume_ordinal_ar": cfg["volume_ordinal_ar"],
            "folder": cfg.get("folder_name") or cfg["volume_id"], "principle_count": principles_count, "principles_with_body": with_body,
            "principles_held": held}


def build_volume_files(project: Project, volume_id: str) -> tuple[VolumeBuild, dict[str, str]]:
    cfg = project.load_config(volume_id)
    vb = VolumeBuild(project, cfg)
    vb.extract()
    return vb, vb.emit()


def manifest(files: dict[str, str]) -> dict[str, str]:
    return {k: hashlib.sha256(v.encode("utf-8")).hexdigest() for k, v in sorted(files.items())}


def cmd_build(project: Project, volume_ids: list[str]) -> int:
    builds: dict[str, tuple[VolumeBuild, dict[str, str]]] = {}
    for vid in volume_ids:
        builds[vid] = build_volume_files(project, vid)
    # collection files from every configured volume (second pass)
    summaries = []
    for vid in project.volume_ids():
        if vid in builds:
            vb = builds[vid][0]
            summaries.append(volume_summary(vb.cfg, len(vb.principles) - len(vb.held), 0, len(vb.held)))
        else:
            cfg = project.load_config(vid)
            idx = project.vault / vid / "index.md"
            count = held = 0
            if idx.exists():
                front = em.load_yaml(idx.read_text(encoding="utf-8").split("---\n")[1])
                count, held = int(front.get("principle_count", 0)), int(front.get("principles_held", 0))
            summaries.append(volume_summary(cfg, count, 0, held))
    summaries.sort(key=lambda s: s["volume_id"])
    collection = {"README.md": em.collection_readme(summaries), "index.md": em.collection_registry(summaries)}
    # staging, recovery, replace
    staging = project.work / "staging"
    if staging.exists():
        shutil.rmtree(staging)
    for vid, (vb, files) in builds.items():
        for rel, content in files.items():
            write_text(staging / vid / rel, content)
    for rel, content in collection.items():
        write_text(staging / rel, content)
    for vid, (vb, files) in builds.items():
        published = project.vault / vid
        previous: dict[str, str] = {}
        if published.exists():
            import vault_verify as vv  # noqa: E402

            previous = vv.published_files(published)
            recovery = project.work / "recovery" / vid
            if recovery.exists():
                shutil.rmtree(recovery)
            shutil.copytree(published, recovery)
            shutil.rmtree(published)
        shutil.copytree(staging / vid, published)
        write_yaml(project.work / "records" / f"{vid}.yaml", vb.records())
        write_yaml(project.work / "review" / f"{vid}.yaml", {"volume_id": vid, "items": vb.review})
        write_yaml(project.work / "anomalies" / f"{vid}.yaml", {"volume_id": vid, "items": vb.anomalies})
        run = update_ledger(project, vb, files, previous)
        write_text(project.work / "reports" / f"{vid}-build-r{run}.md", build_report(vb, files, run))
    for rel, content in collection.items():
        write_text(project.vault / rel, content)
    mpath = project.work / "ledger" / "manifest.yaml"
    manifests = read_yaml(mpath) if mpath.exists() else {}
    for vid, (vb, files) in builds.items():
        manifests[vid] = manifest(files)
    write_yaml(mpath, manifests)
    for vid, (vb, files) in builds.items():
        open_items = [i for i in vb.review if i.get("status") == "open"]
        print(f"{vid}: {len(vb.principles) - len(vb.held)} principle files, {sum(len(p.facets) for p in vb.principles.values())} facets, "
              f"{len(vb.held)} held, {len(files)} files, review items open: {len(open_items)}, anomalies: {len(vb.anomalies)}")
    return 0


def _wording_of_file(text: str) -> list[str]:
    import vault_verify as vv  # noqa: E402

    body = vv.split_front(text)[1]
    return [em.md_unescape(l) for l in body.split("\n") if l.strip() and not vv.GENERATED_LINE.match(l)]


def update_ledger(project: Project, vb: VolumeBuild, files: dict[str, str], previous: dict[str, str]) -> int:
    path = project.work / "ledger" / f"{vb.vid}.yaml"
    ledger = read_yaml(path) if path.exists() else {"volume_id": vb.vid, "run_counter": 0, "principles": {}}
    ledger["run_counter"] = int(ledger.get("run_counter", 0)) + 1
    run = ledger["run_counter"]
    added, removed, reworded = [], [], []
    seen: set[str] = set()
    for number, p in vb.principles.items():
        pid = vm.principle_id(vb.vid, number)
        seen.add(pid)
        wording = "\n".join(para for f in p.facets for para in f.wording_paragraphs)
        digest = hashlib.sha256(wording.encode("utf-8")).hexdigest()
        rec = ledger["principles"].get(pid)
        if rec is None:
            ledger["principles"][pid] = {"first_run": run, "wording_sha256": digest, "facets": len(p.facets), "held": number in vb.held}
            if ledger["run_counter"] > 1:
                added.append(pid)
        else:
            if rec.get("wording_sha256") != digest:
                rec.setdefault("history", []).append({"run": run, "previous_wording_sha256": rec.get("wording_sha256")})
                rec["wording_sha256"] = digest
                reworded.append(pid)
            rec["facets"] = len(p.facets)
            rec["held"] = number in vb.held
    for pid, rec in ledger["principles"].items():
        if pid not in seen and not rec.get("absent_since"):
            rec["absent_since"] = run  # ledger IDs are never dropped
            removed.append(pid)
    ledger["sources"] = [{"file": e.get("stored_name") or e["original_name"], "sha256": e.get("sha256")} for e in vb.cfg.get("source_files", [])]
    write_yaml(path, ledger)
    if added or removed or reworded:
        lines = [f"# Changes — {vb.vid} (run {run})", "", f"- added: {', '.join(added) or '0'}", f"- removed from the sources (kept in the ledger): {', '.join(removed) or '0'}",
                 f"- reworded: {', '.join(reworded) or '0'}", ""]
        for pid in reworded:
            rel = f"Principles/{pid.split(':')[-1]}.md"
            old = _wording_of_file(previous[rel]) if rel in previous else []
            new = _wording_of_file(files[rel]) if rel in files else []
            lines += [f"## {pid}", "", "```diff"] + list(difflib.unified_diff(old, new, "previous", "current", lineterm="")) + ["```", ""]
        for pid in removed:
            lines += [f"- {pid}: wording published earlier is absent from the newer source; its last file is kept under work/recovery/ and the item is open for review", ""]
            vb.add_review("other", pid, "", "principle absent from the newer source", affected_ids=[pid])
        write_text(project.work / "reports" / f"{vb.vid}-changes-r{run}.md", "\n".join(lines))
    return run


def build_report(vb: VolumeBuild, files: dict[str, str], run: int) -> str:
    assert vb.parse is not None
    classes = collections.Counter(l.cls for l in vb.parse.lines)
    ocr = vb.project.work / "review" / f"ocr-{vb.vid}.yaml"
    ocr_line = f"recorded in {ocr.relative_to(vb.project.root)}" if ocr.exists() else (
        "not run in this environment (tesseract absent)" if shutil.which("tesseract") is None else "not run yet (pipeline.py ocr-confirm)")
    lines = [f"# Build report — {vb.vid} (run {run})", "",
             f"- principle files: {len(vb.principles) - len(vb.held)}; held: {len(vb.held)}; facets: {sum(len(p.facets) for p in vb.principles.values())}; vault files: {len(files)}",
             f"- page classes: {dict(sorted(collections.Counter(vb.parse.page_classes.values()).items()))}",
             f"- line classes: {dict(sorted(classes.items()))}",
             f"- glyphs by status: {vb.extraction_summary.get('glyphs_by_status')}",
             f"- wrap joins: {vb.extraction_summary.get('wrap_joins')}; geometry-inserted spaces: {vb.extraction_summary.get('geometry_spaces')}",
             f"- review items: {len(vb.review)} (open: {sum(1 for i in vb.review if i.get('status') == 'open')})",
             f"- anomalies: {len(vb.anomalies)}",
             f"- OCR confirmation: {ocr_line}",
             f"- active execution profile: {'windows-local' if sys.platform.startswith('win') else 'linux-repo'}", ""]
    if vb.review:
        lines += ["## Review items", ""]
        for i in vb.review:
            lines.append(f"- {i['item_id']} [{i['issue_type']}] {i['location']}: {i['observed']} — {i['note']} ({i.get('status')})")
        lines.append("")
    return "\n".join(lines)


def cmd_calibrate(project: Project, volume_id: str) -> int:
    cfg = project.load_config(volume_id)
    vb = VolumeBuild(project, cfg)
    entry = [e for e in cfg.get("source_files", []) if e.get("kind") == "index"][0]
    path = vb.source_path(entry)
    doc = pymupdf.open(str(path))
    fm = ps.load_font_maps(doc)
    out = project.work / "calibration" / volume_id
    crops = out / "crops"
    crops.mkdir(parents=True, exist_ok=True)
    inventory: dict[tuple[str, int], dict] = {}
    for pno in range(1, len(doc) + 1):
        for g in ps.page_glyphs(doc, pno, fm, vb.repairs, vb.settings):
            key = (g.font, g.gid)
            rec = inventory.setdefault(key, {"font": g.font, "gid": g.gid, "text": g.text, "status": g.status, "count": 0, "first": None})
            rec["count"] += 1
            if rec["first"] is None:
                rec["first"] = {"page": pno, "x0": round(g.x0, 1), "y0": round(g.y0, 1), "x1": round(g.x1, 1), "y1": round(g.y1, 1)}
                if g.unresolved or g.status.startswith("repair") or len(g.text) > 1:
                    name = f"{g.font}_{g.gid}_p{pno}.png"
                    ps.render_crop(doc, pno, (g.x0 - 20, g.y0 - 3, g.x1 + 20, g.y1 + 3), crops / name, dpi=500)
                    rec["crop"] = f"crops/{name}"
    fonts = [{"xref": f.xref, "name": f.full_name, "base": f.base, "encoding": f.encoding, "kind": f.kind, "cmap_entries": len(f.cmap), "pages": f.pages}
             for f in fm.fonts.values()]
    pages = []
    for pno in range(1, len(doc) + 1):
        page = doc[pno - 1]
        pages.append({"page": pno, "text_chars": len(page.get_text("text").strip()), "images": len(page.get_images()), "drawings": len(page.get_drawings())})
    write_yaml(out / "glyphs.yaml", {"volume_id": volume_id, "fonts": fonts, "pages": pages,
                                     "glyphs": sorted(inventory.values(), key=lambda r: (r["font"], r["gid"]))})
    unresolved = [r for r in inventory.values() if r["status"].startswith("unresolved")]
    print(f"{volume_id}: {len(inventory)} glyph keys, {len(unresolved)} unresolved; inventory at {out / 'glyphs.yaml'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["build", "verify", "crosscheck", "calibrate", "ocr-confirm"])
    ap.add_argument("--volume", help="volume_id")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--project", default=str(Path(__file__).resolve().parent.parent))
    args = ap.parse_args(argv)
    project = Project(Path(args.project).resolve())
    if args.command == "calibrate":
        if not args.volume:
            ap.error("calibrate needs --volume")
        return cmd_calibrate(project, args.volume)
    volume_ids = project.volume_ids() if args.all or not args.volume else [args.volume]
    if not volume_ids:
        ap.error("no volume configured")
    if args.command == "build":
        return cmd_build(project, volume_ids)
    import vault_verify as vv  # noqa: E402

    if args.command == "verify":
        return vv.cmd_verify(project, volume_ids, build_volume_files)
    if args.command == "crosscheck":
        return vv.cmd_crosscheck(project, volume_ids)
    if args.command == "ocr-confirm":
        return vv.cmd_ocr_confirm(project, volume_ids, build_volume_files)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
