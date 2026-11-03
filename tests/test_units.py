"""Unit tests of the reader heuristics, the parser rules, the model and the verifier's negative paths.

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


def facet(number: str, title: str, hierarchy: list[dict], block_index: int, page_label: str = "1") -> vm.Facet:
    return vm.Facet(1, block_index, "entry", title, "bullet_title", hierarchy, page_label, [], [], None, [], [], [], [], ["نص"], "", None, None, None, [], 1, "f.pdf")


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
        seq = [("9", 0), ("7", 4), ("8", 8), ("-", 12), ("6", 16), ("0", 20), ("3", 24)]
        glyphs = [glyph(t, x, 4, i + 1) for i, (t, x) in enumerate(seq)]
        joined = "".join(t.text for t in ps._line_tokens(glyphs, ps.ReaderSettings(digit_run_joiners=("-",))) if t is not None)
        self.assertEqual(joined, "978-603")
        separate = "".join(t.text for t in ps._line_tokens(glyphs, ps.ReaderSettings()) if t is not None)
        self.assertEqual(separate, "603-978")
        # a Latin run is restored like a digit run
        latin = [glyph(t, x, 4, i + 1) for i, (t, x) in enumerate([("F", 0), ("D", 4), ("P", 8)])]
        self.assertEqual("".join(t.text for t in ps._line_tokens(latin, ps.ReaderSettings()) if t), "FDP")

    def test_geometry_space_rules(self):
        a = glyph("ب", 20, 5, 1)
        b = glyph("ت", 10, 5, 2)  # gap of 5 pt at size 14 > 0.3 * 14
        self.assertIn(None, ps._line_tokens([a, b], ps.ReaderSettings()))
        colon = glyph(":", 10, 3, 3)
        self.assertNotIn(None, ps._line_tokens([a, colon], ps.ReaderSettings()))  # no space before a colon
        colon_right = glyph(":", 20, 3, 4)
        digit = glyph("9", 10, 4, 5)
        self.assertIn(None, ps._line_tokens([colon_right, digit], ps.ReaderSettings()))  # a space after a colon

    def test_overlapping_space_glyphs_are_one_space(self):
        s1 = glyph(" ", 10.0, 2.1, 1, gid=3, status="space")
        s2 = glyph(" ", 11.4, 2.1, 2, gid=3, status="space")  # starts inside s1
        s3 = glyph(" ", 20.0, 2.1, 3, gid=3, status="space")
        ps._drop_overlapping_spaces([s1, s2, s3])
        self.assertEqual([g.status for g in (s1, s2, s3)], ["space", "drop:duplicate_space", "space"])

    def test_tatweel_rule(self):
        self.assertEqual(ps.strip_decorative_tatweel("يقــرر"), ("يقرر", 1))
        self.assertEqual(ps.strip_decorative_tatweel("1447 هـ"), ("1447 هـ", 0))
        self.assertEqual(ps.strip_decorative_tatweel("(هـ/2280/1442)"), ("(هـ/2280/1442)", 0))
        self.assertEqual(ps.strip_decorative_tatweel("الـعــدل"), ("العدل", 2))

    def test_persian_forms(self):
        self.assertEqual(ps.normalize_text("کی"), "كي")


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


class ModelTest(unittest.TestCase):
    H = [{"level": "letter", "label_ar": "حرف (ع)", "title_ar": "ع"}, {"level": "topic", "title_ar": "عقار"}]

    def test_see_also_matching_requires_a_unique_facet(self):
        f1 = facet("1", "عنوان أول", self.H + [{"level": "subtopic", "label_ar": "أولاً/", "title_ar": "ملكية"}], 0)
        f2 = facet("2", "عنوان ثان", self.H, 1)
        index = [("1", f1), ("2", f2)]
        self.assertEqual(vm._match_see_also("حرف ع/ عقار - ملكية - عنوان أول", index)[0], "1")
        self.assertEqual(vm._match_see_also("حرف ع/ عقار - عنوان ثان", index)[0], "2")
        self.assertIsNone(vm._match_see_also("حرف ع/ عقار", index))  # two candidates
        self.assertIsNone(vm._match_see_also("حرف ص/ صحة - عنوان", index))

    def test_keys_ids_and_filenames(self):
        self.assertEqual(vm.principle_id("Admin-principles-1443-v6", "101"), "Admin-principles-1443-v6:p101")
        self.assertEqual(vm.principle_id("Admin-principles-1443-v6", "101-dup2"), "Admin-principles-1443-v6:p101-dup2")
        self.assertEqual(vm.principle_filename("9"), "p009.md")
        self.assertEqual(vm.principle_filename("9-dup3"), "p009-dup3.md")
        self.assertEqual(sorted(["101-dup2", "9", "101"], key=vm.key_sort), ["9", "101", "101-dup2"])
        self.assertIsNone(vm.letter_slug("ء"))
        self.assertTrue(vm.RE_RULING_REF_ID.match("Admin-principles-1443-v6:r-b-1752-1443"))
        self.assertTrue(vm.RE_RULING_REF_ID.match("Admin-principles-1443-v6:r-a-2771-2893-1442"))

    def test_split_decision(self):
        ref_a = vi.RulingRef("(أ/100/1442)", "أ", "100", "1442", "page[1]:r1:c0:L1")
        ref_b = vi.RulingRef("(أ/200/1442)", "أ", "200", "1442", "page[1]:r2:c0:L1")
        p = vm.Principle("7")
        fa = facet("7", "أ", self.H, 0)
        fa.references = [ref_a]
        fb = facet("7", "ب", self.H, 1)
        fb.references = [ref_b]
        fb.facet = 2
        p.facets = [fa, fb]
        issue = {"issue_type": "identity", "location": "page[1]:r1:c0:L1, page[1]:r2:c0:L1", "note": "x"}
        p.open_issues = [issue]
        principles = {"7": p}
        created = vm.apply_split_decisions(principles, {"abc": {"resolution": "split"}}, "Admin-principles-1443-v6", lambda loc, t: "abc")
        self.assertEqual(created, ["7-dup2"])
        self.assertEqual([f.title_ar for f in principles["7"].facets], ["أ"])
        self.assertEqual([f.title_ar for f in principles["7-dup2"].facets], ["ب"])
        self.assertEqual(principles["7-dup2"].facets[0].facet, 1)
        self.assertEqual(principles["7"].open_issues, [])


class VerifierNegativePathTest(unittest.TestCase):
    """The verifier must reject corrupted copies of the sample vault; held and multi-file paths."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="principles-vault-neg-"))
        sample = em.load_yaml((ROOT / "tests" / "fixtures" / "samples" / "samples.yaml").read_text(encoding="utf-8"))["samples"][0]
        vid = sample["volume_id"]
        (cls.tmp / "config" / "volumes").mkdir(parents=True)
        shutil.copy(ROOT / sample["config"], cls.tmp / "config" / "volumes" / f"{vid}.yaml")
        (cls.tmp / "Input" / vid).mkdir(parents=True)
        shutil.copy(ROOT / sample["source"], cls.tmp / "Input" / vid / sample["stored_name"])
        cls.sample = sample
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

    def _first(self):
        key = sorted(self.vb.principles, key=vm.key_sort)[0]
        rel = f"Principles/{vm.principle_filename(key)}"
        front, body = vv.split_front(self.files[rel])
        return key, rel, front, body

    def test_baseline_passes(self):
        self.assertEqual(self._fails(self.files), [])

    def test_wording_change_is_rejected(self):
        key, rel, front, body = self._first()
        para = em.md_escape(self.vb.principles[key].facets[0].wording_paragraphs[0])
        mutated = dict(self.files)
        mutated[rel] = "---\n" + front + "---\n" + body.replace(para, para + "x", 1)
        self.assertTrue(any(f.startswith("normalized source text") for f in self._fails(mutated)))

    def test_frontmatter_change_is_rejected(self):
        key, rel, front, body = self._first()
        mutated = dict(self.files)
        mutated[rel] = "---\n" + front.replace('page_label: "', 'page_label: "9', 1) + "---\n" + body
        self.assertTrue(any(f.startswith("frontmatter equals the records") for f in self._fails(mutated)))

    def test_duplicate_key_is_rejected(self):
        key, rel, front, body = self._first()
        mutated = dict(self.files)
        mutated[rel] = "---\n" + front + 'volume_id: "x"\n' + "---\n" + body
        self.assertTrue(any(f.startswith("YAML parses") for f in self._fails(mutated)))

    def test_heading_number_change_is_rejected(self):
        key, rel, front, body = self._first()
        h1 = f"# {vm.citation_ar(self.vb.cfg, key)}"
        mutated = dict(self.files)
        mutated[rel] = "---\n" + front + "---\n" + body.replace(h1, h1 + "9", 1)
        self.assertTrue(any(f.startswith("body heading equals citation_ar") for f in self._fails(mutated)))

    def test_missing_repair_holds_the_principle(self):
        cfg = em.load_yaml((self.tmp / "config" / "volumes" / f"{self.vid}.yaml").read_text(encoding="utf-8"))
        for font in cfg["fonts"]:
            (font.get("glyph_repairs") or {}).pop(56, None)  # the head glyph of sad
        held_root = Path(tempfile.mkdtemp(prefix="principles-vault-held-"))
        try:
            (held_root / "config" / "volumes").mkdir(parents=True)
            (held_root / "config" / "volumes" / f"{self.vid}.yaml").write_text(em.dump_yaml(cfg), encoding="utf-8")
            (held_root / "Input" / self.vid).mkdir(parents=True)
            shutil.copy(self.tmp / "Input" / self.vid / self.sample["stored_name"], held_root / "Input" / self.vid / self.sample["stored_name"])
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

    def test_second_identical_index_file_joins_sources(self):
        cfg = em.load_yaml((self.tmp / "config" / "volumes" / f"{self.vid}.yaml").read_text(encoding="utf-8"))
        first = [e for e in cfg["source_files"] if e["kind"] == "index"][0]
        second = dict(first)
        second.update({"stored_name": "Indexes-copy.pdf", "original_name": "Indexes-copy.pdf", "rank": 2})
        cfg["source_files"].append(second)
        root = Path(tempfile.mkdtemp(prefix="principles-vault-two-"))
        try:
            (root / "config" / "volumes").mkdir(parents=True)
            (root / "config" / "volumes" / f"{self.vid}.yaml").write_text(em.dump_yaml(cfg), encoding="utf-8")
            (root / "Input" / self.vid).mkdir(parents=True)
            src = self.tmp / "Input" / self.vid / self.sample["stored_name"]
            shutil.copy(src, root / "Input" / self.vid / self.sample["stored_name"])
            shutil.copy(src, root / "Input" / self.vid / "Indexes-copy.pdf")
            project = pipeline.Project(root)
            vb, files = pipeline.build_volume_files(project, self.vid)
            key = sorted(vb.principles, key=vm.key_sort)[0]
            self.assertEqual(vb.principles[key].extra_source_files, ["Indexes-copy.pdf"])
            front = em.load_yaml(vv.split_front(files[f"Principles/{vm.principle_filename(key)}"])[0])
            self.assertEqual([s["file"] for s in front["sources"]], [self.sample["stored_name"], "Indexes-copy.pdf"])
            self.assertTrue(front["sources"][1].get("identical_wording"))
            self.assertFalse(any(i["issue_type"] == "wording" for i in vb.review))
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
