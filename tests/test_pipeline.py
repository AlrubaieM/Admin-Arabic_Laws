"""Tests of the principles-vault pipeline on the reviewed sample.

Run through uv (master prompt, section 3):
  uv run --no-project --no-managed-python --no-python-downloads --no-sync --python .venv/bin/python -m unittest discover -s tests -v

The sample sources are listed in tests/fixtures/samples/samples.yaml; each
test copies a sample into a temporary project root, builds it there, and
compares the result with the expected values (tests/fixtures/<volume_id>.expected.yaml).
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import pipeline  # noqa: E402
import vault_emit as em  # noqa: E402
import vault_verify as vv  # noqa: E402


def load_samples() -> list[dict]:
    path = ROOT / "tests" / "fixtures" / "samples" / "samples.yaml"
    return em.load_yaml(path.read_text(encoding="utf-8"))["samples"]


class SampleBuildTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="principles-vault-test-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _prepare(self, samples: list[dict], name: str) -> pipeline.Project:
        """A fresh temporary project holding the given samples, as the real vault holds its volumes: a volume may
        take glyph text from identical fonts of another volume's sources (pdf_source.discover_references)."""
        root = self.tmp / name
        for sample in samples:
            vid = sample["volume_id"]
            (root / "config" / "volumes").mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / sample["config"], root / "config" / "volumes" / f"{vid}.yaml")
            (root / "Input" / vid).mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / sample["source"], root / "Input" / vid / sample["stored_name"])
            (root / "tests" / "fixtures").mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / sample["expected"], root / "tests" / "fixtures" / f"{vid}.expected.yaml")
        return pipeline.Project(root)

    def test_a_volume_alone_holds_lines_it_cannot_read(self) -> None:
        """Built without the other volumes, the 1444 sample cannot resolve three cataloging glyphs whose repairs the
        1443 volume establishes: the lines are held as review items and the build still passes its checks."""
        sample = next(s for s in load_samples() if s["volume_id"] == "Admin-principles-1444-v6")
        project = self._prepare([sample], "alone")
        vid = sample["volume_id"]
        self.assertEqual(pipeline.cmd_build(project, [vid]), 0)
        details = (project.vault / vid / "volume-details.md").read_text(encoding="utf-8")
        self.assertNotIn("�", details)
        review = em.load_yaml((project.work / "review" / f"{vid}.yaml").read_text(encoding="utf-8"))
        items = review["items"] if isinstance(review, dict) else review
        self.assertTrue(any(i["issue_type"] == "glyph" and "cataloging line" in i["note"] for i in items))

    def test_build_and_verify_each_sample(self) -> None:
        samples = load_samples()
        project = self._prepare(samples, "all")
        # build --all first (the collection registry and reader guide cover every volume), then verify each volume
        self.assertEqual(pipeline.cmd_build(project, [s["volume_id"] for s in samples]), 0)
        for sample in samples:
            with self.subTest(volume=sample["volume_id"]):
                vid = sample["volume_id"]
                vault = project.vault / vid
                self.assertTrue((vault / "index.md").exists())
                self.assertTrue((vault / "volume-details.md").exists())
                files = sorted(p.name for p in (vault / "Principles").glob("p*.md"))
                expected = em.load_yaml((ROOT / sample["expected"]).read_text(encoding="utf-8"))
                self.assertEqual(files, [f"p{n:03d}.md" for n in sorted(expected["principle_numbers"])])
                self.assertEqual(vv.cmd_verify(project, [vid], pipeline.build_volume_files), 0)
                # project rule 3: extract and convert only; links, summary comparison and reading questions are
                # report notes, never review items
                review = em.load_yaml((project.work / "review" / f"{vid}.yaml").read_text(encoding="utf-8"))
                items = review["items"] if isinstance(review, dict) else review
                self.assertEqual([i for i in items if i["issue_type"] == "link"], [])
                self.assertEqual([i for i in items if "summary" in i["note"]], [])
                self.assertEqual([i for i in items if i["location"].startswith("page[2]:r2")], [])  # the deposit-number question
                report = sorted((project.work / "reports").glob(f"{vid}-build-r*.md"))[-1].read_text(encoding="utf-8")
                self.assertIn("notes (not review items; project rule 3", report)

    def test_yaml_loader_rejects_duplicate_keys(self) -> None:
        with self.assertRaises(Exception):
            em.load_yaml("a: 1\na: 2\n")

    def test_markdown_escape_roundtrip(self) -> None:
        for text in ("# عنوان", "- بند", "1. رقم", "نص [مع] *رموز* _و_ `أخرى`", "| جدول", "> اقتباس"):
            self.assertEqual(em.md_unescape(em.md_escape(text)), text)
            self.assertFalse(vv.GENERATED_LINE.match(em.md_escape(text)) and not text.startswith("- "))


if __name__ == "__main__":
    unittest.main()
