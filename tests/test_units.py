"""Unit tests of the reader heuristics, the parser rules and the verifier's negative paths.

Run through uv:
  uv run --no-project --no-managed-python --no-python-downloads --no-sync --python .venv/bin/python -m unittest discover -s tests -v
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import pdf_source as ps  # noqa: E402
import pipeline  # noqa: E402
import vault_emit as em  # noqa: E402
import vault_index as vi  # noqa: E402
import vault_model as vm  # noqa: E402
import vault_verify as vv  # noqa: E402


def glyph(text: str, x0: float, width: float, seq: int, gid: int = 1, font: str = "AXtManal", status: str = "cmap", oy: float = 100.0, size: float = 14.0,
          raw: int | None = None) -> ps.Glyph:
    return ps.Glyph(1, seq, font, gid, raw if raw is not None else (ord(text[0]) if text else 0), text, x0, oy - 10, x0 + width, oy + 3, x0, oy, size, 1, status)


class ReaderUnitTest(unittest.TestCase):
    def test_parse_tounicode_bfchar_and_bfrange(self):
        cmap = "1 begincodespacerange <0000> <FFFF> endcodespacerange\n2 beginbfchar <0003> <0020> <00B4> <06440645> endbfchar\n" \
               "1 beginbfrange <0013> <001C> <0030> endbfrange\n1 beginbfrange <0100> <0101> [<0623> <0625>] endbfrange\n"
        m = ps.parse_tounicode(cmap)
        self.assertEqual(m[3], " ")
        self.assertEqual(m[0xB4], "لم")
        self.assertEqual([m[0x13 + i] for i in range(10)], list("0123456789"))
        self.assertEqual((m[0x100], m[0x101]), ("أ", "إ"))

    def test_hamza_composes_with_alef_and_lam_alef_and_waw(self):
        # visual order left to right: ب (x 10) | alef body (x 16) with zero-width hamza at x 16
        glyphs = [glyph("ب", 10, 5, 1), glyph("أ", 16, 0, 2, gid=38), glyph("ا", 16, 2.5, 3, gid=42, status="repair:alef_body")]
        ps._compose_hamza(glyphs, ps.ReaderSettings())
        self.assertEqual([g.text for g in glyphs if not g.dropped], ["ب", "أ"])
        glyphs = [glyph("إ", 20, 0, 1, gid=40), glyph("لا", 20, 6, 2, gid=176, status="repair:lam_alef")]
        ps._compose_hamza(glyphs, ps.ReaderSettings())
        self.assertEqual([g.text for g in glyphs if not g.dropped], ["لإ"])
        glyphs = [glyph("ؤ", 30, 0, 1, gid=39), glyph("و", 30, 4, 2, gid=161)]
        ps._compose_hamza(glyphs, ps.ReaderSettings())
        self.assertEqual([g.text for g in glyphs if not g.dropped], ["ؤ"])
        lone = [glyph("أ", 40, 0, 1, gid=38), glyph("ب", 44, 5, 2)]
        ps._compose_hamza(lone, ps.ReaderSettings())
        self.assertEqual(lone[0].status, "unresolved:hamza_without_body")

    def test_tail_dropped_only_when_a_head_touches_it(self):
        head = glyph("ص", 50, 6, 1, gid=56, status="repair:head")
        tail = glyph("", 44, 6, 2, gid=127, status="repair:tail")
        ps._drop_tails([head, tail], ps.ReaderSettings())
        self.assertEqual(tail.status, "drop:tail")
        lone_tail = glyph("", 80, 6, 3, gid=127, status="repair:tail")
        ps._drop_tails([lone_tail], ps.ReaderSettings())
        self.assertEqual(lone_tail.status, "unresolved:tail_without_head")

    def test_line_tokens_restore_digit_runs_and_separate_numbers(self):
        # the page prints (ب/1752/1443): visual left to right: ) 1443 / 1752 / ب (
        seq = [(")", 0), ("1", 6), ("4", 10), ("4", 14), ("3", 18), ("/", 22), ("1", 26), ("7", 30), ("5", 34), ("2", 38), ("/", 42), ("ب", 46), ("(", 50)]
        glyphs = [glyph(t, x, 4, i + 1) for i, (t, x) in enumerate(seq)]
        text = "".join(t.text for t in ps._line_tokens(glyphs, ps.ReaderSettings()) if t is not None)
        self.assertEqual(text, "(ب/1752/1443)")
        # with the hyphen as a joiner the whole run is one left-to-right string (ISBN)
        seq = [("9", 0), ("7", 4), ("8", 8), ("-", 12), ("6", 16), ("0", 20), ("3", 24)]
        glyphs = [glyph(t, x, 4, i + 1) for i, (t, x) in enumerate(seq)]
        joined = "".join(t.text for t in ps._line_tokens(glyphs, ps.ReaderSettings(digit_run_joiners=("-",))) if t is not None)
        self.assertEqual(joined, "978-603")
        separate = "".join(t.text for t in ps._line_tokens(glyphs, ps.ReaderSettings()) if t is not None)
        self.assertEqual(separate, "603-978")

    def test_geometry_space_only_between_word_glyphs(self):
        a = glyph("ب", 20, 5, 1)
        b = glyph("ت", 10, 5, 2)  # gap of 5 pt at size 14 > 0.3 * 14
        self.assertIn(None, ps._line_tokens([a, b], ps.ReaderSettings()))
        colon = glyph(":", 10, 3, 3)
        self.assertNotIn(None, ps._line_tokens([a, colon], ps.ReaderSettings()))


class ParserRulesTest(unittest.TestCase):
    def test_wrap_rule(self):
        self.assertTrue(vi._is_wrap("نص بلا نهاية", "تتمة"))
        self.assertTrue(vi._is_wrap("نص ينتهي بفاصلة منقوطة؛", "تتمة"))
        self.assertFalse(vi._is_wrap("جملة تامة.", "جملة جديدة"))
        self.assertFalse(vi._is_wrap("عنوان:", "نص"))
        self.assertFalse(vi._is_wrap("نص", "• عنوان"))
        self.assertFalse(vi._is_wrap("نص", "ثانياً/ فرع"))
        self.assertFalse(vi._is_wrap("نص", "راجع: (حرف أ)"))
        self.assertFalse(vi._is_wrap("نص", "1- بند"))

    def test_reference_pattern(self):
        for ref in ("(ب/1752/1443)", "(هـ/2280/1442)", "(أ/2771-2893/1442)"):
            self.assertIsNotNone(vi.RE_REF.fullmatch(ref), ref)
        self.assertIsNone(vi.RE_REF.search("(19)"))

    def test_see_also_matching_requires_a_unique_facet(self):
        f1 = vm.Facet(1, 0, "entry", "عنوان أول", "bullet_title",
                      [{"level": "letter", "label_ar": "حرف (ع)", "title_ar": "ع"}, {"level": "topic", "title_ar": "عقار"}, {"level": "subtopic", "label_ar": "أولاً/", "title_ar": "ملكية"}],
                      "10", [], [], None, [], [], [], [], ["نص"], "", None, None, None, [], 1)
        f2 = vm.Facet(1, 1, "entry", "عنوان ثان", "bullet_title",
                      [{"level": "letter", "label_ar": "حرف (ع)", "title_ar": "ع"}, {"level": "topic", "title_ar": "عقار"}], "11", [], [], None, [], [], [], [], ["نص"], "", None, None, None, [], 1)
        index = [("1", f1), ("2", f2)]
        self.assertEqual(vm._match_see_also("حرف ع/ عقار - ملكية - عنوان أول", index)[0], "1")
        self.assertEqual(vm._match_see_also("حرف ع/ عقار - عنوان ثان", index)[0], "2")
        self.assertIsNone(vm._match_see_also("حرف ع/ عقار", index))  # two candidates
        self.assertIsNone(vm._match_see_also("حرف ص/ صحة - عنوان", index))


class VerifierNegativePathTest(unittest.TestCase):
    """The verifier must reject corrupted copies of the sample vault."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="principles-vault-neg-"))
        sample = em.load_yaml((ROOT / "tests" / "fixtures" / "samples" / "samples.yaml").read_text(encoding="utf-8"))["samples"][0]
        vid = sample["volume_id"]
        (cls.tmp / "config" / "volumes").mkdir(parents=True)
        shutil.copy(ROOT / sample["config"], cls.tmp / "config" / "volumes" / f"{vid}.yaml")
        (cls.tmp / "Input" / vid).mkdir(parents=True)
        shutil.copy(ROOT / sample["source"], cls.tmp / "Input" / vid / sample["stored_name"])
        cls.project = pipeline.Project(cls.tmp)
        cls.vid = vid
        pipeline.cmd_build(cls.project, [vid])
        cls.vb, _ = pipeline.build_volume_files(cls.project, vid)
        cls.files = vv.published_files(cls.project.vault / vid)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _fails(self, files: dict[str, str]) -> list[str]:
        return vv.content_checks(self.vb, files, self.project.vault, self.vid).failures()

    def test_baseline_passes(self):
        self.assertEqual(self._fails(self.files), [])

    def test_wording_change_is_rejected(self):
        number = sorted(self.vb.principles, key=int)[0]
        rel = f"Principles/{vm.principle_filename(number)}"
        front, body = vv.split_front(self.files[rel])
        para = em.md_escape(self.vb.principles[number].facets[0].wording_paragraphs[0])
        mutated = dict(self.files)
        mutated[rel] = "---\n" + front + "---\n" + body.replace(para, para + "x", 1)
        self.assertTrue(any(f.startswith("normalized source text") for f in self._fails(mutated)))

    def test_frontmatter_change_is_rejected(self):
        number = sorted(self.vb.principles, key=int)[0]
        rel = f"Principles/{vm.principle_filename(number)}"
        front, body = vv.split_front(self.files[rel])
        mutated = dict(self.files)
        mutated[rel] = "---\n" + front.replace('page_label: "', 'page_label: "9', 1) + "---\n" + body
        self.assertTrue(any(f.startswith("frontmatter equals the records") for f in self._fails(mutated)))

    def test_duplicate_key_is_rejected(self):
        number = sorted(self.vb.principles, key=int)[0]
        rel = f"Principles/{vm.principle_filename(number)}"
        front, body = vv.split_front(self.files[rel])
        mutated = dict(self.files)
        mutated[rel] = "---\n" + front + 'volume_id: "x"\n' + "---\n" + body
        self.assertTrue(any(f.startswith("YAML parses") for f in self._fails(mutated)))

    def test_missing_repair_holds_the_principle(self):
        cfg_path = self.tmp / "config" / "volumes" / f"{self.vid}.yaml"
        cfg = em.load_yaml(cfg_path.read_text(encoding="utf-8"))
        for font in cfg["fonts"]:
            (font.get("glyph_repairs") or {}).pop(56, None)  # the head glyph of sad
        held_root = Path(tempfile.mkdtemp(prefix="principles-vault-held-"))
        try:
            (held_root / "config" / "volumes").mkdir(parents=True)
            (held_root / "config" / "volumes" / f"{self.vid}.yaml").write_text(em.dump_yaml(cfg), encoding="utf-8")
            (held_root / "Input" / self.vid).mkdir(parents=True)
            shutil.copy(self.tmp / "Input" / self.vid / "Indexes-1443-v6.pdf", held_root / "Input" / self.vid / "Indexes-1443-v6.pdf")
            project = pipeline.Project(held_root)
            vb, files = pipeline.build_volume_files(project, self.vid)
            self.assertTrue(vb.held)
            for n in vb.held:
                self.assertNotIn(f"Principles/{vm.principle_filename(n)}", files)
            self.assertIn("محجوز للمراجعة", files["index.md"])
            self.assertTrue(any(i["issue_type"] == "glyph" for i in vb.review))
            rep = vv.Report()
            vv.check_vault_files(files, rep, None, self.vid)
            self.assertTrue(any("U+FFFD" in f for f in rep.failures()))  # the verifier refuses the unrepaired copy
        finally:
            shutil.rmtree(held_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
