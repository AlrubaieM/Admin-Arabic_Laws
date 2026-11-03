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

    def _prepare(self, sample: dict) -> pipeline.Project:
        vid = sample["volume_id"]
        (self.tmp / "config" / "volumes").mkdir(parents=True)
        shutil.copy(ROOT / sample["config"], self.tmp / "config" / "volumes" / f"{vid}.yaml")
        (self.tmp / "Input" / vid).mkdir(parents=True)
        shutil.copy(ROOT / sample["source"], self.tmp / "Input" / vid / sample["stored_name"])
        (self.tmp / "tests" / "fixtures").mkdir(parents=True)
        shutil.copy(ROOT / sample["expected"], self.tmp / "tests" / "fixtures" / f"{vid}.expected.yaml")
        return pipeline.Project(self.tmp)

    def test_build_and_verify_each_sample(self) -> None:
        for sample in load_samples():
            with self.subTest(volume=sample["volume_id"]):
                project = self._prepare(sample)
                vid = sample["volume_id"]
                self.assertEqual(pipeline.cmd_build(project, [vid]), 0)
                vault = project.vault / vid
                self.assertTrue((vault / "index.md").exists())
                self.assertTrue((vault / "volume-details.md").exists())
                files = sorted(p.name for p in (vault / "Principles").glob("p*.md"))
                expected = em.load_yaml((ROOT / sample["expected"]).read_text(encoding="utf-8"))
                self.assertEqual(files, [f"p{n:03d}.md" for n in sorted(expected["principle_numbers"])])
                self.assertEqual(vv.cmd_verify(project, [vid], pipeline.build_volume_files), 0)

    def test_yaml_loader_rejects_duplicate_keys(self) -> None:
        with self.assertRaises(Exception):
            em.load_yaml("a: 1\na: 2\n")

    def test_markdown_escape_roundtrip(self) -> None:
        for text in ("# عنوان", "- بند", "1. رقم", "نص [مع] *رموز* _و_ `أخرى`", "| جدول", "> اقتباس"):
            self.assertEqual(em.md_unescape(em.md_escape(text)), text)
            self.assertFalse(vv.GENERATED_LINE.match(em.md_escape(text)) and not text.startswith("- "))


if __name__ == "__main__":
    unittest.main()
