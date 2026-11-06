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
import ocr_sheet  # noqa: E402


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
        mutated[rel] = "---\n" + front.replace('page_id: "', 'page_id: "G9', 1) + "---\n" + body
        self.assertTrue(any(f.startswith("frontmatter equals the records") for f in self._fails(mutated)))

    def test_duplicate_key_is_rejected(self):
        key, rel, front, body = self._first()
        mutated = dict(self.files)
        mutated[rel] = "---\n" + front + 'principle_id: "x"\n' + "---\n" + body
        self.assertTrue(any(f.startswith("YAML parses") for f in self._fails(mutated)))

    def test_heading_change_is_rejected(self):
        key, rel, front, body = self._first()
        h1 = "# " + em.md_escape(self.vb.principles[key].title_ar or "")
        mutated = dict(self.files)
        mutated[rel] = "---\n" + front + "---\n" + body.replace(h1, h1 + "9", 1)
        self.assertTrue(any(f.startswith("body heading equals principle_title_ar") for f in self._fails(mutated)))

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
            self.assertNotIn("صيغة أخرى", files[f"Principles/{vm.principle_filename(key)}"])
            self.assertFalse(any(i["issue_type"] == "wording" for i in vb.review))
        finally:
            shutil.rmtree(root, ignore_errors=True)


class OcrHarnessTest(unittest.TestCase):
    def test_digit_whitelist_admits_the_printed_arabic_indic_digits(self):
        # the sample prints the number and page cells in Arabic-Indic digits (e.g. ١٧٧٧)
        for d in "0123456789٠١٢٣٤٥٦٧٨٩":
            self.assertIn(d, vv.OCR_DIGIT_WHITELIST)

    def test_ocr_command_carries_the_whitelist(self):
        cmd = vv.ocr_command("tesseract", Path("x.png"), 7, vv.OCR_DIGIT_WHITELIST)
        self.assertIn("tessedit_char_whitelist=" + vv.OCR_DIGIT_WHITELIST, cmd)
        self.assertEqual(cmd[cmd.index("--psm") + 1], "7")

    def test_ocr_text_drops_bidi_marks(self):
        # Tesseract wraps Arabic runs in U+200E/U+200F; they must never reach the YAML review records
        got = vv.ocr_text("‏(ب/‎١٧٥٢‏/1443)\n")
        self.assertEqual(got, "(ب/1752/1443)")
        em.dump_yaml({"ocr": got})

    def test_line_crop_stays_inside_the_cell(self):
        from types import SimpleNamespace as NS
        cell = NS(x0=100.0, y0=50.0, x1=300.0, y1=80.0)
        line = NS(x0=101.0, y0=51.0, x1=299.5, y1=60.0)
        self.assertEqual(vv.line_crop_rect(line, cell), (101.5, 51.5, 298.5, 63.0))


def _facet(block_index, file="a.pdf", title="t", paragraphs=("w.",), page=8, kind="entry"):
    return vm.Facet(facet=1, block_index=block_index, entry_kind=kind, title_ar=title, title_basis="bullet_title", hierarchy=[],
                    page_label="1", references=[], shared_with=[], pairing_basis=None, heading_locations=[], text_locations=[],
                    reference_locations=[], number_locations=[], wording_paragraphs=list(paragraphs), reference_line="",
                    see_also_text=None, see_also_target=None, see_also_path_ar=None, wrap_joins=[], page=page, file=file)


class CodeReviewFixesTest(unittest.TestCase):
    def test_key_helpers_on_a_non_matching_key(self):
        self.assertEqual(vm.key_suffix("12-dup2"), "-dup2")
        self.assertEqual(vm.key_suffix("abc"), "")
        with self.assertRaises(ValueError):
            vm.key_sort("abc")

    def test_cell_starting_with_a_pipe_is_escaped_once(self):
        self.assertEqual(em._cell("|x|y"), r"\|x\|y")

    def test_untitled_principle_heading_equals_its_frontmatter_title(self):
        cfg = {"volume_id": "Admin-principles-1443-v6", "collection_name_ar": "م", "collection_name_en": "C", "year_hijri": "1443", "volume_number": "6"}
        p = vm.Principle("57", [_facet(0, title=None, paragraphs=("القواعد المنظمة تعد من النظام العام؛ وللمحكمة أن تتصدى لها.",))])
        front = em.principle_front(cfg, p)
        body = em.principle_body(cfg, p)
        self.assertEqual(front["principle_title_ar"], "القواعد المنظمة تعد من النظام العام")
        self.assertEqual(body[0], "# " + front["principle_title_ar"])

    def test_relations_use_each_facet_own_file(self):
        from types import SimpleNamespace as NS
        primary = NS(file="a.pdf", blocks=[NS(continues_block=None, loc="page[8]:r1")])
        second = NS(file="b.pdf", blocks=[NS(continues_block=None, loc="page[8]:r1"), NS(continues_block=0, loc="page[8]:r2"),
                                          NS(continues_block=None, loc="page[8]:r3")])
        principles = {"1": vm.Principle("1", [_facet(0, "a.pdf")]),
                      "2": vm.Principle("2", [_facet(0, "b.pdf")]),
                      "3": vm.Principle("3", [_facet(1, "b.pdf")]),
                      "4": vm.Principle("4", [_facet(2, "b.pdf")])}
        vm.resolve_relations(principles, {"a.pdf": primary, "b.pdf": second}, "Admin-principles-1443-v6")
        rel = {k: sorted((r.relation, r.principle_key) for r in p.relations) for k, p in principles.items()}
        self.assertEqual(rel["1"], [])  # block 0 of a.pdf is not block 0 of b.pdf
        self.assertEqual(rel["2"], [("sibling_under_title", "3")])
        self.assertEqual(rel["3"], [("sibling_under_title", "2")])
        self.assertEqual(rel["4"], [])  # b.pdf block 2 exists only in the second file: no IndexError

    def test_continuation_only_from_the_page_just_before(self):
        from types import SimpleNamespace as NS
        blocks = [NS(page=10)]
        self.assertIs(vi.last_block_of_page(blocks, 10), blocks[0])
        self.assertIsNone(vi.last_block_of_page(blocks, 11))  # page 11 had no entry block

    def test_relations_check_reads_the_model(self):
        principles = {"1": vm.Principle("1", [_facet(0)], relations=[vm.Relation("2", "shared_index_entry")]),
                      "2": vm.Principle("2", [_facet(0)])}
        from types import SimpleNamespace as NS
        rep = vv.Report()
        vv.check_relations(NS(principles=principles, held=set(), vid="Admin-principles-1443-v6"), rep)
        self.assertFalse(rep.ok)
        principles["2"].relations.append(vm.Relation("1", "shared_index_entry"))
        rep = vv.Report()
        vv.check_relations(NS(principles=principles, held=set(), vid="Admin-principles-1443-v6"), rep)
        self.assertTrue(rep.ok, rep.failures())

    def test_mutation_test_without_a_published_wording(self):
        from types import SimpleNamespace as NS
        from unittest import mock
        vb = NS(principles={"1": vm.Principle("1", [_facet(0, paragraphs=())])}, held=set())
        ok = vv.Report()
        with mock.patch.object(vv, "content_checks", return_value=ok):
            rep = vv.Report()
            vv.mutation_test(vb, {}, None, "v", rep)
        self.assertFalse(rep.ok)
        self.assertIn("no published principle with wording", rep.failures()[0])

class SecondReaderConfirmationTest(unittest.TestCase):
    """An OCR disagreement is settled automatically only when the second reader positively confirms the line."""

    PAGE = "1777 383 الإدارية حماماة بأتعاب كان النزاع متعلق إذا ،ةاماحم 1443/1752 ب"

    def test_digits_and_words_found_on_the_page_confirm_the_line(self):
        self.assertTrue(vv.second_reader_confirms("1777", self.PAGE))
        self.assertTrue(vv.second_reader_confirms("(ب/1752/1443)", self.PAGE))
        # the second reader joins a ruling reference into one token with its digits: "1443/1752ب"
        self.assertTrue(vv.second_reader_confirms("(ب/1752/1443)", "النزاع 1443/1752ب)"))
        # the second reader splits a word at a glyph it cannot decode: "قصوراً" arrives as "ق�صور ًا"
        self.assertTrue(vv.second_reader_confirms("قصوراً في التسبيب.", vv._norm_second_reader("التسبيب.  في  ق�صور ًا")))
        self.assertFalse(vv.second_reader_confirms("قصوراً", vv._norm_second_reader("ق�صور  التسبيب")))
        # «محاماة» rendered «حماماة» by the second reader: same letters in another order still confirms
        self.assertTrue(vv.second_reader_confirms("إذا كان النزاع متعلق بأتعاب محاماة", self.PAGE))

    def test_a_missing_number_or_word_leaves_the_line_open(self):
        self.assertFalse(vv.second_reader_confirms("1778", self.PAGE))
        self.assertFalse(vv.second_reader_confirms("(ب/1752/1444)", self.PAGE))
        self.assertFalse(vv.second_reader_confirms("إذا كان الخلاف متعلق", self.PAGE))
        self.assertFalse(vv.second_reader_confirms("", self.PAGE))
        self.assertFalse(vv.second_reader_confirms("1777", ""))


class PageClassTest(unittest.TestCase):
    def test_a_ruled_frame_without_text_is_a_drawing_not_a_table(self):
        from types import SimpleNamespace as NS
        empty = NS(rows=[NS(cells=[NS(lines=[], text_lines=[]), NS(lines=[], text_lines=[])])])
        self.assertEqual(vi.classify_page(empty, [], "basmala", has_images=False, has_drawings=True), "basmala")
        self.assertEqual(vi.classify_page(empty, [], None, has_images=False, has_drawings=True), "other")


class SummaryDifferencesTest(unittest.TestCase):
    def test_every_difference_of_a_row_is_listed(self):
        out = vi.summary_differences(["أجانب", "إجراءات إدارية", "إجراءات نظامية", "عقد"],
                                     ["أجانب", "الإجراءات الإدارية", "الإجراءات النظامية", "تعويض"])
        self.assertEqual(out, ["differ only by the article «ال»: «إجراءات إدارية» (summary) / «الإجراءات الإدارية» (detailed)، "
                               "«إجراءات نظامية» (summary) / «الإجراءات النظامية» (detailed)",
                               "only in the summary index: «عقد»", "only in the detailed index: «تعويض»"])
        self.assertEqual(vi.summary_differences(["أ", "ب"], ["أ", "ب"]), [])


class OcrSheetTest(unittest.TestCase):
    def item(self, loc, pub, ocr):
        return {"item_id": "x", "location": loc, "published": pub, "ocr": ocr}

    def test_causes(self):
        c = ocr_sheet.classify
        self.assertEqual(c(self.item("page[8]:r2:c2:L0", "1777", "11")), "digits")
        self.assertEqual(c(self.item("page[8]:r2:c0:L4", "(ب/1752/1443)", "(ب/ 5/1715)")), "reference_line")
        self.assertEqual(c(self.item("page[8]:r3:c0:L3", "المحاماة في حال كسب", "المحاماة # حال كسب")), "fi_ligature")
        self.assertEqual(c(self.item("page[9]:r4:c0:L1", "تعد من النظام العام. (أ/2054/1442)", "تعد من النظام العام. )15447/5104/1(")), "reference_digits")
        self.assertEqual(c(self.item("page[9]:r3:c0:L2", "دون طلب أو دفعٍ من قبل", "دون طلب أو دضع من قبل")), "other_letters")
        self.assertEqual(c(self.item("page[9]:r5:c0:L1", "القواعد المتعلقة", "")), "other_letters")

    def test_apply_into_empty_decisions(self):
        cfg = 'volume_id: "v"\nfonts: []\n\ndecisions: {}\n'
        out, added, skipped = ocr_sheet.merge_decisions(cfg, {"aa11": {"resolution": "keep", "decided_on": "06/11/2026", "note": "n"}})
        data = em.load_yaml(out)
        self.assertEqual(data["decisions"]["aa11"]["resolution"], "keep")
        self.assertEqual((added, skipped), (["aa11"], []))
        self.assertTrue(out.startswith('volume_id: "v"\nfonts: []\n'))  # the rest of the file is untouched

    def test_apply_keeps_existing_decisions(self):
        cfg = 'volume_id: "v"\ndecisions:\n  aa11:\n    resolution: "split"\n    decided_on: "01/11/2026"\nreader: {}\n'
        out, added, skipped = ocr_sheet.merge_decisions(cfg, {"aa11": {"resolution": "keep", "decided_on": "06/11/2026"},
                                                             "bb22": {"resolution": "keep", "decided_on": "06/11/2026"}})
        data = em.load_yaml(out)
        self.assertEqual(data["decisions"]["aa11"]["resolution"], "split")
        self.assertEqual(data["decisions"]["bb22"]["resolution"], "keep")
        self.assertEqual(data["reader"], {})
        self.assertEqual((added, skipped), (["bb22"], ["aa11"]))

    def test_apply_rejects_unknown_resolution(self):
        with self.assertRaises(ValueError):
            ocr_sheet.merge_decisions("decisions: {}\n", {"aa11": {"resolution": "ocr", "decided_on": "06/11/2026"}})

class ReferenceFontTest(unittest.TestCase):
    """A re-printed PDF ("Microsoft: Print To PDF") renames its fonts and drops most of their ToUnicode
    entries; a configured reference font with byte-identical outlines supplies the text."""

    S1443 = ROOT / "samples" / "Indexes-1443-v6.pdf"

    def test_font_base_strips_only_a_subset_tag(self):
        self.assertEqual(ps.font_base("UJLMPZ+AXtManal"), "AXtManal")
        self.assertEqual(ps.font_base("AXtManal"), "AXtManal")
        self.assertEqual(ps.font_base("CIDFont+F4"), "CIDFont+F4")  # "CIDFont" is not a six-capital subset tag

    def test_reference_text_is_used_only_after_the_own_cmap(self):
        own = ps.FontObject(1, "CIDFont+F4", "CIDFont+F4", "Identity-H", {5: "ب"}, "identity", [7])
        fm = ps.FontMaps({1: own}, {7: {"CIDFont+F4": [1]}}, reference={"CIDFont+F4": {5: "x", 6: "ت"}})
        self.assertEqual(ps.resolve_glyph_text(fm, 7, "CIDFont+F4", 5), ("ب", "cmap"))
        self.assertEqual(ps.resolve_glyph_text(fm, 7, "CIDFont+F4", 6), ("ت", "cmap_reference"))
        self.assertEqual(ps.resolve_glyph_text(fm, 7, "CIDFont+F4", 9)[1], "unresolved:no_cmap_entry")

    def test_discovery_matches_fonts_by_identical_outlines_only(self):
        import pymupdf
        doc = pymupdf.open(str(self.S1443))
        cand = ps.ReferenceCandidate("self", str(self.S1443), {("AXtManal", 42): ps.RepairRule("ا", "alef_body")})
        refs, inherited, summary = ps.discover_references(doc, [cand])
        # every font is found in itself, and only in itself: a different typeface never qualifies
        for row in summary:
            self.assertEqual([s.split(" (")[0] for s in row["same_font_in"]], [f"self:{row['font']}"])
        self.assertGreater(len(refs["AXtManal"]), 100)
        self.assertEqual(inherited[("AXtManal", 42)].role, "alef_body")
        self.assertNotIn(42, refs["AXtManal"])  # a repaired glyph is inherited as a repair, never as plain text
        self.assertEqual(ps.discover_references(doc, []), ({}, {}, []))

    def test_text_drawn_outside_the_page_is_not_read(self):
        import pymupdf
        doc = pymupdf.open(str(ROOT / "samples" / "pr year 1444 orginal export.pdf"))
        # page 3 (the basmala) carries a copy of the cataloging text placed beyond the right edge of the page
        self.assertEqual(ps.page_glyphs(doc, 3, ps.load_font_maps(doc), {}, ps.ReaderSettings()), [])
        self.assertGreater(ps.off_page_glyphs(doc[2]), 100)
        self.assertEqual(ps.off_page_glyphs(doc[1]), 0)

    def test_vector_drawn_bullet_is_read_as_a_bullet(self):
        import pymupdf
        reprint = next((ROOT / "samples").glob("Indexes-*1444*.pdf"))
        doc = pymupdf.open(str(reprint))
        original = pymupdf.open(str(ROOT / "samples" / "pr year 1444 orginal export.pdf"))
        for pno in range(7, 14):
            glyphs = ps.page_glyphs(doc, pno, ps.load_font_maps(doc), {}, ps.ReaderSettings())
            bullets = [g for g in glyphs if g.status == "vector_bullet"]
            self.assertTrue(all(g.text == "•" for g in bullets))
            # the original export of the same pages draws each bullet as a glyph: the counts agree page by page
            in_original = [g for g in ps.page_glyphs(original, pno, ps.load_font_maps(original), {}, ps.ReaderSettings()) if g.text == "•"]
            self.assertEqual(len(bullets), len(in_original), f"page {pno}")
        # a PDF that draws its bullets as glyphs gets no second, vector bullet
        orig = pymupdf.open(str(self.S1443))
        g1443 = ps.page_glyphs(orig, 8, ps.load_font_maps(orig), {}, ps.ReaderSettings())
        self.assertEqual([g for g in g1443 if g.status == "vector_bullet"], [])


if __name__ == "__main__":
    unittest.main()
