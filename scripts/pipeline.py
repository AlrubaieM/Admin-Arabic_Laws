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


def ddmmyyyy(d) -> str:
    return f"{d.day:02d}/{d.month:02d}/{d.year:04d}"


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
        self.parse: vi.IndexParse | None = None  # the index file ranked first
        self.parses: list[tuple[dict, vi.IndexParse]] = []
        self.principles: dict[str, vm.Principle] = {}
        self.held: set[str] = set()  # principle keys held from publication
        self.review: list[dict] = []
        self.anomalies: list[dict] = []
        self.extraction_summary: dict = {}
        self.extraction_details: dict = {}
        self.cataloging_lines: list[str] = []
        self.file_entries: list[dict] = []
        self.year_span_value: dict | None = None

    def source_path(self, entry: dict) -> Path:
        return self.project.input_dir / self.vid / (entry.get("stored_name") or entry["original_name"])

    def reference_candidates(self) -> list[ps.ReferenceCandidate]:
        """Every verified source PDF of every configured volume (present in Input/ with its configured SHA-256),
        with the glyph repairs its configuration establishes. A font of the file being read takes text from a
        candidate only for glyphs with byte-identical outlines (ps.discover_references); reader.reference_fonts:
        false switches this off for a volume."""
        if not (self.cfg.get("reader") or {}).get("reference_fonts", True):
            return []
        if getattr(self, "_candidates", None) is None:
            self._candidates = []
            for vid in self.project.volume_ids():
                try:
                    cfg = self.project.load_config(vid)
                except SystemExit:
                    continue
                repairs = ps.build_repairs(cfg.get("fonts") or [])
                for entry in cfg.get("source_files") or []:
                    path = self.project.input_dir / vid / (entry.get("stored_name") or entry["original_name"])
                    if path.exists() and sha256_file(path) == entry.get("sha256"):
                        self._candidates.append(ps.ReferenceCandidate(f"{vid}/{path.name}", str(path), repairs))
        return self._candidates

    def font_maps(self, doc: pymupdf.Document, path: Path) -> tuple[ps.FontMaps, dict]:
        """Font maps and glyph repairs for one source document: its own CMaps first, then text and repairs inherited
        from identical fonts of other verified sources, then this volume's configured repairs (which always win)."""
        others = [c for c in self.reference_candidates() if Path(c.path).resolve() != path.resolve()]
        refs, inherited, summary = ps.discover_references(doc, others)
        self.extraction_details.setdefault("reference_fonts", {})[path.name] = summary
        return ps.load_font_maps(doc, refs), {**inherited, **self.repairs}

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

    # ------------------------------------------------------------------
    def extract(self) -> None:
        entries = sorted([e for e in self.cfg.get("source_files", []) if e.get("kind") == "index"], key=lambda e: int(e.get("rank", 1)))
        principle_files = [e for e in self.cfg.get("source_files", []) if e.get("kind") == "principle"]
        if principle_files:
            self.add_review("other", "config:source_files", ", ".join(e.get("stored_name") or e["original_name"] for e in principle_files),
                            "principle files are configured but no body_sections calibration exists; principle bodies are not published in this revision",
                            options=["calibrate the first principle file (Appendix B) and record body_sections"])
        if not entries:
            raise SystemExit(f"{self.vid}: no index file configured")
        declared = {int(k): v for k, v in (self.cfg.get("page_classes") or {}).items()}
        for entry in entries:
            path = self.source_path(entry)
            if not path.exists():
                raise SystemExit(f"{self.vid}: source file missing: {path}")
            digest = sha256_file(path)
            if digest != entry.get("sha256"):
                raise SystemExit(f"{self.vid}: SHA-256 of {path.name} is {digest}, configuration says {entry.get('sha256')}")
            doc = pymupdf.open(str(path))
            fm, repairs = self.font_maps(doc, path)
            parse = vi.parse_index_file(doc, path.name, fm, repairs, self.settings, entry.get("page_label_offset"), declared)
            self.parses.append((entry, parse))
            if not parse.detailed_tables and not parse.summary_tables:
                self.add_review("other", f"file:{path.name}", "", "configured as an index file but no page of the index classes was found",
                                options=["check the file kind in the configuration"])
            self._glyph_items(doc, parse)
            numbers = sorted({int(n) for b in parse.blocks for n in b.numbers if n.isdigit()})
            page_classes: dict[str, list[int]] = {}
            for pno, cls in parse.page_classes.items():
                page_classes.setdefault(cls, []).append(pno)
            self.file_entries.append({"file": path.name, "kind": "index", "pages": len(doc),
                                      "numbers": f"{numbers[0]}–{numbers[-1]} ({len(numbers)})" if numbers else "", "extraction": "text_layer_repaired",
                                      "page_classes": page_classes})
            doc.close()
        self.parse = self.parses[0][1]
        self._build_principles()
        self.cataloging_lines = []
        for l in self.parse.lines:
            if l.cls != "cataloging_text":
                continue
            if l.unresolved or "�" in l.text:
                # held like a principle: never published with an unresolved glyph (the glyph item names the repair)
                self.add_review("glyph", l.loc, l.text, "cataloging line with an unresolved glyph; not published until the glyph is repaired",
                                options=["repair the glyph in the configuration"])
                continue
            self.cataloging_lines.append(l.text)
        self._summaries()

    def _glyph_items(self, doc, parse: vi.IndexParse) -> None:
        crops_dir = self.project.work / "review" / "crops" / self.vid
        for g in parse.unresolved_glyphs:
            loc = f"{parse.file}:page[{g.page}] x={g.x0:.1f} y={g.oy:.1f}"
            crop = crops_dir / f"{item_id(self.vid, loc, 'glyph')}.png"
            crop.parent.mkdir(parents=True, exist_ok=True)
            ps.render_crop(doc, g.page, (g.x0 - 20, g.y0 - 3, g.x1 + 20, g.y1 + 3), crop, dpi=500)
            self.add_review("glyph", loc, f"font {g.font} gid {g.gid} ({g.status})", "glyph without a resolved text; its line and principle are held",
                            options=["add a glyph repair for this (font, gid) to the configuration"], crop=crop.relative_to(self.project.root).as_posix())

    def _build_principles(self) -> None:
        assert self.parse is not None
        primary_entry, primary = self.parses[0]
        for i in primary.issues:
            self.add_review(i["issue_type"], i["location"], i["observed"], i["note"], options=i.get("options"))
        self.principles, review = vm.build_principles(primary, self.vid)
        for i in review:
            self.add_review(i["issue_type"], i["location"], i["observed"], i["note"], affected_ids=i.get("affected_ids"), options=i.get("options"))
        # further index files (section 2): identical wording -> one output with both files in sources;
        # different wording -> the first-ranked file's wording is published, the variant is recorded and shown, review item
        for entry, parse in self.parses[1:]:
            for i in parse.issues:
                self.add_review(i["issue_type"], f"{parse.file}:{i['location']}", i["observed"], i["note"], options=i.get("options"))
            others, review2 = vm.build_principles(parse, self.vid)
            for i in review2:
                self.add_review(i["issue_type"], f"{parse.file}:{i['location']}", i["observed"], i["note"], affected_ids=i.get("affected_ids"))
            for key, q in others.items():
                if key not in self.principles:
                    self.principles[key] = q
                    self.add_review("other", f"{parse.file}:{parse.blocks[q.facets[0].block_index].loc}", str(q.number),
                                    "principle number present only in a lower-ranked index file; published from that file",
                                    affected_ids=[vm.principle_id(self.vid, key)])
                    continue
                p = self.principles[key]
                if _wording_key(p) == _wording_key(q):
                    p.extra_source_files.append(parse.file)
                else:
                    p.alt_wordings.append(vm.AltWording(parse.file, [para for f in q.facets for para in f.wording_paragraphs],
                                                        " ".join(f.reference_line for f in q.facets if f.reference_line),
                                                        [l for f in q.facets for l in f.text_locations]))
                    item = self.add_review("wording", f"{parse.file}:{parse.blocks[q.facets[0].block_index].loc}", _wording_key(q)[:80],
                                           "wording differs between the supplied index files; the first-ranked file's wording is published and the variant is shown",
                                           affected_ids=[vm.principle_id(self.vid, key)], options=["decision keep (first-ranked file)", "decision prefer:<file>"])
                    p.open_issues.append(item)
        self._apply_decisions()
        parses_by_file = {parse.file: parse for _entry, parse in self.parses}
        for i in vm.resolve_relations(self.principles, parses_by_file, self.vid):
            self.add_review(i["issue_type"], i["location"], i["observed"], i["note"], affected_ids=i.get("affected_ids"), options=i.get("options"))
        # held principles: a line with an unresolved glyph, or an entry without wording
        for key, p in self.principles.items():
            for f in p.facets:
                block = parses_by_file[f.file].blocks[f.block_index]  # a principle from a lower-ranked file is checked in that file
                bad = [l for l in block.opener_lines + block.title_lines + block.wording_lines + block.reference_lines if l.unresolved or "�" in l.text]
                if bad:
                    self.held.add(key)
                    self.add_review("wording", bad[0].loc, bad[0].text, "line with an unresolved glyph; principle held",
                                    affected_ids=[vm.principle_id(self.vid, key)], options=["repair the glyph in the configuration", "decision ocr: publish the OCR reading"])
                if not block.wording_paragraphs:
                    self.held.add(key)
                    self.add_review("wording", block.loc, "", "entry block without wording; principle held", affected_ids=[vm.principle_id(self.vid, key)])
        for a in self.cfg.get("source_anomalies") or []:
            rec = dict(a)
            self.anomalies.append(rec)
            if rec.get("principle"):
                p = self.principles.get(str(int(rec["principle"])))
                if p is not None:
                    p.anomalies.append(rec)
        # project rule 3 (extract and convert only): configured reading questions are report notes; the value is
        # published as the reader converts it (digit groups right to left as printed)
        self.reading_notes = [f"{q['location']}: {q.get('observed', '')} — {q.get('note', '')}" for q in self.cfg.get("reading_questions") or []]
        for p in self.principles.values():
            for issue in p.open_issues:
                issue.setdefault("item_id", item_id(self.vid, issue["location"], issue["issue_type"]))
        self._apply_decisions()
        self._ocr_items()
        for problem in vm.validate_ids(self.vid, self.principles, primary.letters):
            self.add_review("identity", "ids", problem, "generated identifier outside the ID grammar")

    def _apply_decisions(self) -> None:
        decisions = self.cfg.get("decisions") or {}
        created = vm.apply_split_decisions(self.principles, decisions, self.vid, lambda loc, t: item_id(self.vid, loc, t))
        for key in created:
            item = self.add_review("identity", f"split:{key}", key, "published under a -dupN suffix by a decided split", affected_ids=[vm.principle_id(self.vid, key)])
            item["status"] = "decided"
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
            if iid not in applied and not any(i["item_id"] == iid for i in self.review):
                self.review.append({"item_id": iid, "issue_type": "other", "location": "config:decisions", "affected_ids": [], "observed": iid,
                                    "note": "decision whose item no longer occurs", "options": [], "status": "stale"})

    def _ocr_items(self) -> None:
        """Unacknowledged OCR disagreements recorded by ocr-confirm join the review queue."""
        path = self.project.work / "review" / f"ocr-{self.vid}.yaml"
        if not path.exists():
            return
        data = read_yaml(path)
        decisions = self.cfg.get("decisions") or {}
        for it in data.get("items") or []:
            if it["item_id"] in decisions or it.get("resolution") == "auto_keep":
                continue
            # add_review derives the same item_id (volume|location|wording) that ocr-confirm recorded
            self.add_review("wording", it["location"], it.get("published", ""), f"OCR disagrees: {it.get('ocr', '')!r}", options=it.get("options"), crop=it.get("crop"))

    def _summaries(self) -> None:
        assert self.parse is not None
        ocr_path = self.project.work / "review" / f"ocr-{self.vid}.yaml"
        summary: dict = {
            "fonts": [{"name": f["name"], "text_layer": f.get("text_layer", "unknown"), "glyph_repairs": len(f.get("glyph_repairs") or {})}
                      for f in self.cfg.get("fonts") or []],
            "text_layer": "defective" if any(f.get("text_layer") == "defective" for f in self.cfg.get("fonts") or []) else "reliable",
            "glyph_repairs_applied": sum(v for k, v in self.parse.glyph_status.items() if k in ("repair", "compose")),
        }
        if ocr_path.exists():
            data = read_yaml(ocr_path)
            summary["ocr_confirmed_lines"] = int(data.get("confirmed", 0))
            summary["ocr_disagreements"] = int(data.get("disagreeing", 0))
        self.extraction_summary = summary
        self.extraction_details = {
            "reference_fonts": self.extraction_details.get("reference_fonts", {}),
            "glyphs_by_status": dict(sorted(self.parse.glyph_status.items())),
            "wrap_joins": sum(len(b.wrap_joins) for b in self.parse.blocks),
            "reference_separations": sum(len(b.reference_separations) for b in self.parse.blocks),
            "geometry_spaces": sum(l.gap_spaces for l in self.parse.lines),
            "tatweel_runs_removed": self.parse.tatweel_removed,
            "duplicate_space_glyphs_dropped": self.parse.glyph_status.get("drop:duplicate_space", 0),
            "font_objects": self.parse.font_objects,
            "page_apparatus": {str(k): v for k, v in self.parse.page_apparatus.items()},
            "summary_coverage": self.parse.summary_coverage,
        }
        self.year_span_value = self.year_span()

    # ------------------------------------------------------------------
    def year_span(self) -> dict | None:
        try:
            from hijridate import Hijri
        except ImportError as exc:
            raise SystemExit("hijridate is required for the volume's computed Gregorian year span; install it into the project .venv") from exc
        y = int(self.cfg["year_hijri"])
        try:
            start = Hijri(y, 1, 1).to_gregorian()
        except Exception as exc:  # outside the converter's range: omit and flag (section 12)
            self.add_review("date", "config:year_hijri", str(y), f"year outside the range of hijridate ({exc}); year_gregorian_computed omitted")
            return None
        try:
            end, last_day = Hijri(y, 12, 30).to_gregorian(), 30
        except Exception:
            end, last_day = Hijri(y, 12, 29).to_gregorian(), 29
        return {"start": ddmmyyyy(start), "end": ddmmyyyy(end), "last_day_of_year": last_day, "basis": "computed (hijridate, Umm al-Qura)"}

    # ------------------------------------------------------------------
    def emit(self) -> dict[str, str]:
        """Return {relative path: content} for the volume folder."""
        assert self.parse is not None
        cfg = self.cfg
        files: dict[str, str] = {}
        for key in sorted(self.principles, key=vm.key_sort):
            if key in self.held:
                continue
            p = self.principles[key]
            files[f"Principles/{vm.principle_filename(key)}"] = em.rtl_file(em.principle_front(cfg, p, self.held), em.principle_body(cfg, p, self.principles, self.held))
        held_items = {k: [i["item_id"] for i in self.review if vm.principle_id(self.vid, k) in i.get("affected_ids", [])] for k in self.held}
        files["index.md"] = em.volume_index(cfg, self.parse, self.principles, self.anomalies, held_items)
        files["volume-details.md"] = em.volume_details(cfg, self.parse, self.cataloging_lines, self.extraction_summary, self.anomalies,
                                                       self.year_span_value, self.file_entries, len(self.held))
        return files

    def records(self) -> dict:
        assert self.parse is not None
        return {
            "volume_id": self.vid,
            "files": [fe["file"] for fe in self.file_entries],
            "page_classes": {str(k): v for k, v in self.parse.page_classes.items()},
            "page_labels": {str(k): v for k, v in self.parse.page_labels.items()},
            "held_principles": sorted(self.held, key=vm.key_sort),
            "extraction": self.extraction_details,
            "lines": [{"loc": l.loc, "class": l.cls, "text": l.text, "bold": round(l.bold, 2), "gap_spaces": l.gap_spaces, "unresolved": l.unresolved,
                       "tatweel_removed": l.tatweel_removed} for l in self.parse.lines],
            "blocks": [
                {"loc": b.loc, "kind": b.kind, "numbers": b.numbers, "labels": b.labels, "references": [r.ref_ar for r in b.references],
                 "title_ar": b.title_ar, "title_basis": b.title_basis, "hierarchy": vars(b.hierarchy), "paragraphs": b.wording_paragraphs,
                 "wrap_joins": b.wrap_joins, "reference_separations": b.reference_separations, "continues_block": b.continues_block}
                for b in self.parse.blocks
            ],
            "summary_rows": self.parse.summary_rows,
            "relations": {vm.principle_id(self.vid, k): [{"principle_id": vm.principle_id(self.vid, r.principle_key) if r.principle_key else None,
                                                          "relation": r.relation} for r in p.relations] for k, p in self.principles.items()},
        }


def _wording_key(p: vm.Principle) -> str:
    return "\n".join(para for f in p.facets for para in f.wording_paragraphs) + "\n" + " ".join(f.reference_line for f in p.facets)


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


def collection_files(project: Project, builds: dict[str, tuple[VolumeBuild, dict[str, str]]]) -> dict[str, str]:
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
    return {"README.md": em.collection_readme(summaries), "index.md": em.collection_registry(summaries)}


def cmd_build(project: Project, volume_ids: list[str]) -> int:
    import vault_verify as vv  # noqa: E402

    builds: dict[str, tuple[VolumeBuild, dict[str, str]]] = {vid: build_volume_files(project, vid) for vid in volume_ids}
    collection = collection_files(project, builds)
    staging = project.work / "staging"
    if staging.exists():
        shutil.rmtree(staging)
    for vid, (vb, files) in builds.items():
        for rel, content in files.items():
            write_text(staging / vid / rel, content)
    for rel, content in collection.items():
        write_text(staging / rel, content)
    # validate the staged files before anything published is replaced (section 14)
    for vid, (vb, files) in builds.items():
        rep = vv.content_checks(vb, files, staging, vid)
        if not rep.ok:
            raise SystemExit(f"{vid}: staged files fail the content checks; nothing replaced: " + "; ".join(rep.failures()[:3]))
    for vid, (vb, files) in builds.items():
        published = project.vault / vid
        previous: dict[str, str] = {}
        if published.exists():
            previous = vv.published_files(published)
            recovery = project.work / "recovery" / vid
            if recovery.exists():
                shutil.rmtree(recovery)
            shutil.copytree(published, recovery)
            shutil.rmtree(published)
        shutil.copytree(staging / vid, published)
        run = update_ledger(project, vb, files, previous)
        write_yaml(project.work / "records" / f"{vid}.yaml", vb.records())
        write_yaml(project.work / "review" / f"{vid}.yaml", {"volume_id": vid, "items": vb.review})
        write_yaml(project.work / "anomalies" / f"{vid}.yaml", {"volume_id": vid, "items": vb.anomalies})
        write_text(project.work / "reports" / f"{vid}-build-r{run}.md", build_report(vb, files, run))
    for rel, content in collection.items():
        write_text(project.vault / rel, content)
    mpath = project.work / "ledger" / "manifest.yaml"
    manifests = read_yaml(mpath) if mpath.exists() else {}
    for vid, (vb, files) in builds.items():
        manifests[vid] = manifest(files)
    manifests["collection"] = manifest(collection)
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
    old_sources = {s.get("file"): s.get("sha256") for s in ledger.get("sources") or []}
    new_sources = {(e.get("stored_name") or e["original_name"]): e.get("sha256") for e in vb.cfg.get("source_files", [])}
    inputs_changed = bool(old_sources) and old_sources != new_sources
    added, removed, reworded, relabelled, related = [], [], [], [], []
    seen: set[str] = set()
    for key, p in vb.principles.items():
        pid = vm.principle_id(vb.vid, key)
        seen.add(pid)
        digest = hashlib.sha256(p.wording_signature.encode("utf-8")).hexdigest()
        labels = list(p.page_labels)
        rel_sig = sorted(f"{r.relation}:{vm.principle_id(vb.vid, r.principle_key) if r.principle_key else r.target_citation_ar}" for r in p.relations)
        rec = ledger["principles"].get(pid)
        if rec is None:
            ledger["principles"][pid] = {"first_run": run, "wording_sha256": digest, "facets": len(p.facets), "held": key in vb.held,
                                         "page_labels": labels, "relations": rel_sig}
            if run > 1:
                added.append(pid)
        else:
            if rec.get("wording_sha256") != digest:
                rec.setdefault("history", []).append({"run": run, "previous_wording_sha256": rec.get("wording_sha256")})
                rec["wording_sha256"] = digest
                reworded.append(pid)
            if rec.get("page_labels") is not None and rec.get("page_labels") != labels:
                relabelled.append(f"{pid}: {rec.get('page_labels')} -> {labels}")
            if rec.get("relations") is not None and rec.get("relations") != rel_sig:
                related.append(f"{pid}: {sorted(set(rec.get('relations')) ^ set(rel_sig))}")
            rec.update({"facets": len(p.facets), "held": key in vb.held, "page_labels": labels, "relations": rel_sig})
    for pid, rec in ledger["principles"].items():
        if pid not in seen and not rec.get("absent_since"):
            rec["absent_since"] = run  # ledger IDs are never dropped
            removed.append(pid)
    ledger["sources"] = [{"file": f, "sha256": h} for f, h in new_sources.items()]
    write_yaml(path, ledger)
    if inputs_changed or added or removed or reworded or relabelled or related:
        lines = [f"# Changes — {vb.vid} (run {run})", "",
                 f"- input hashes changed: {'yes' if inputs_changed else 'no'}",
                 f"- added: {', '.join(added) or '0'}",
                 f"- removed from the sources (kept in the ledger): {', '.join(removed) or '0'}",
                 f"- reworded: {', '.join(reworded) or '0'}",
                 f"- page labels changed: {'; '.join(relabelled) or '0'}",
                 f"- relations changed: {'; '.join(related) or '0'}", ""]
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
    apparatus = {str(p): {"images": len(a["images"]), "drawings": a["drawings"]} for p, a in vb.parse.page_apparatus.items() if a["images"] or a["drawings"]}
    lines = [f"# Build report — {vb.vid} (run {run})", "",
             f"- source files: {', '.join(fe['file'] for fe in vb.file_entries)}",
             f"- principle files: {len(vb.principles) - len(vb.held)}; held: {len(vb.held)}; facets: {sum(len(p.facets) for p in vb.principles.values())}; vault files: {len(files)}",
             f"- page classes: {dict(sorted(collections.Counter(vb.parse.page_classes.values()).items()))}",
             f"- line classes: {dict(sorted(classes.items()))}",
             f"- apparatus excluded per page (images, non-ruling drawings): {apparatus}",
             f"- glyphs by status: {vb.extraction_details.get('glyphs_by_status')}",
             f"- wrap joins: {vb.extraction_details.get('wrap_joins')}; reference separations: {vb.extraction_details.get('reference_separations')}; "
             f"geometry-inserted spaces: {vb.extraction_details.get('geometry_spaces')}; tatweel runs removed: {vb.extraction_details.get('tatweel_runs_removed')}; "
             f"duplicate space glyphs dropped: {vb.extraction_details.get('duplicate_space_glyphs_dropped')}",
             f"- summary-index coverage: {vb.extraction_details.get('summary_coverage')}",
             "- configured files not read for wording: " + ("; ".join(
                 f"{e.get('stored_name') or e['original_name']} ({e.get('kind')}: {e.get('not_read_basis') or e.get('note') or 'no basis recorded'})"
                 for e in vb.cfg.get('source_files') or [] if e.get('kind') not in ('index', 'principle')) or "none"),
             "- entry components the index prints for no entry: " + ("; ".join(
                 f"{parse.file}: {', '.join(vm.components_not_printed(parse))}" for _e, parse in vb.parses if vm.components_not_printed(parse)) or "none"),
             "- fonts identified by identical outlines in other verified sources: " + ("; ".join(
                 f"{name}: {r['font']} = {', '.join(r['same_font_in'])} ({r['glyph_ids_with_text']} texts, {r['inherited_repairs']} repairs)"
                 for name, rows in sorted((vb.extraction_details.get('reference_fonts') or {}).items()) for r in rows) or "none"),
             f"- review items: {len(vb.review)} (open: {sum(1 for i in vb.review if i.get('status') == 'open')})",
             "- notes (not review items; project rule 3, extract and convert only):",
             *[f"  - {n}" for n in getattr(vb, "reading_notes", [])],
             *[f"  - {n}" for _e, parse in vb.parses for n in (parse.summary_coverage or {}).get("notes", [])],
             *[f"  - see-also target not among the supplied pages: {vm.principle_id(vb.vid, k)}: {r.target_citation_ar}"
               for k, p in sorted(vb.principles.items(), key=lambda kv: vm.key_sort(kv[0])) for r in p.relations if r.relation == "see_also" and not r.target_supplied],
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
    entries = [e for e in cfg.get("source_files", []) if e.get("kind") in ("index", "principle")]
    out = project.work / "calibration" / volume_id
    crops = out / "crops"
    crops.mkdir(parents=True, exist_ok=True)
    inventory: dict[tuple[str, str, int], dict] = {}
    fonts_all = []
    pages_all = []
    for entry in entries:
        path = vb.source_path(entry)
        doc = pymupdf.open(str(path))
        fm, repairs = vb.font_maps(doc, path)
        for pno in range(1, len(doc) + 1):
            page = doc[pno - 1]
            pages_all.append({"file": path.name, "page": pno, "text_chars": len(page.get_text("text").strip()), "images": len(page.get_images()),
                              "drawings": len(page.get_drawings())})
            for g in ps.page_glyphs(doc, pno, fm, repairs, vb.settings):
                key = (path.name, g.font, g.gid)
                rec = inventory.setdefault(key, {"file": path.name, "font": g.font, "gid": g.gid, "text": g.text, "status": g.status, "count": 0, "first": None})
                rec["count"] += 1
                if rec["first"] is None:
                    rec["first"] = {"page": pno, "x0": round(g.x0, 1), "y0": round(g.y0, 1), "x1": round(g.x1, 1), "y1": round(g.y1, 1)}
                    if g.unresolved or g.status.startswith("repair") or len(g.text) > 1:
                        name = f"{g.font}_{g.gid}_p{pno}.png"
                        ps.render_crop(doc, pno, (g.x0 - 20, g.y0 - 3, g.x1 + 20, g.y1 + 3), crops / name, dpi=500)
                        rec["crop"] = f"crops/{name}"
        fonts_all += [{"file": path.name, "xref": f.xref, "name": f.full_name, "base": f.base, "encoding": f.encoding, "kind": f.kind,
                       "cmap_entries": len(f.cmap), "pages": f.pages} for f in fm.fonts.values()]
    write_yaml(out / "glyphs.yaml", {"volume_id": volume_id, "fonts": fonts_all, "pages": pages_all,
                                     "glyphs": sorted(inventory.values(), key=lambda r: (r["file"], r["font"], r["gid"]))})
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
