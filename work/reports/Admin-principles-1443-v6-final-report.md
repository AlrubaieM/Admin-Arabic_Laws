# Final report — Admin-principles-1443-v6 (run 7)

## Execution profile

- Active profile: linux-repo (cloud Git checkout, Python 3.13.18 and uv 0.11.32; project .venv created with --system-site-packages; pymupdf 2.1 and hijridate 2.6.0 installed into it with --no-deps). Poppler pdftotext 24.02.0 is present; Tesseract is absent, so OCR confirmation is held as blocked and a page-by-page visual review of the rendered pages was performed instead (work/review/visual-Admin-principles-1443-v6.yaml).

## Produced

- Volume `Admin-principles-1443-v6` from one index file (Input/Admin-principles-1443-v6/Indexes-1443-v6.pdf, 17 physical pages): 49 index blocks, 37 principle numbers, 37 principle files, 54 facets, 0 held; index.md, volume-details.md, Indexes/summary-index.md, Indexes/detailed-index.md; collection README.md and index.md.
- Page classes: {'cover': [1], 'cataloging': [2], 'basmala': [3], 'half_title': [4, 6], 'divider': [5], 'index_summary': [7], 'index_detailed': [8, 9, 10, 11, 12, 13, 14, 15, 16], 'blank': [17]}.
- No per-principle PDF was supplied: every principle carries its index wording only (text_basis index_wording, body_supplied false).

## Checks executed (fresh in this run)

- [x] two consecutive builds give an identical manifest
- [x] published files equal a fresh derivation from the sources: 43 files
- [x] YAML parses with duplicate-key rejection: 41 files
- [x] no \u escapes of Arabic
- [x] no U+FFFD in any published file
- [x] Western digits and no presentation forms
- [x] one RTL wrapper per file
- [x] UTF-8 without BOM, LF, one trailing newline, no trailing whitespace
- [x] Markdown lint of bodies
- [x] required frontmatter keys and key order
- [x] ID grammar, filenames and numbers
- [x] body heading equals citation_ar
- [x] 0 broken relative links or anchors: 285 links
- [x] frontmatter equals the records: 37 principle files
- [x] every reciprocal relation is reciprocal: 37 principles
- [x] every generated ID matches the ID grammar
- [x] every page has a class of the fixed vocabulary: 17 pages
- [x] every source line has one class (0 unaccounted): {'apparatus:hidden_folio': 4, 'apparatus:page_number': 10, 'cataloging_text': 7, 'header_row': 27, 'index_wording': 155, 'letter': 2, 'number': 49, 'outline': 12, 'page_label': 51, 'ruling_reference': 13, 'subtopic_opener': 10, 'summary_letter': 14, 'summary_topics': 14, 'title': 50, 'topic': 5}
- [x] every content line maps to at least one output location: 409 content lines mapped; 14 apparatus lines are listed exclusions
- [x] intentional duplicates are listed and permitted: 80 block texts appear in more than one body place (the preserved table and the sharing principle files)
- [x] lines held as review items: 0
- [x] every index number has exactly one principle file or is held: 37 numbers, 37 files, 0 held
- [x] no published principle without wording
- [x] normalized source text equals normalized output text (0 mismatches): 54 facets and 207 table cells
- [x] fixture expectations: 14 fixture keys compared
- [x] mutated temporary copy is rejected: index wording: rejected (normalized source text equals normalized output text (0 mismatches)); body wording: not applicable; YAML: rejected (YAML parses with duplicate-key rejection); link: rejected (0 broken relative links or anchors); ruling reference: rejected (normalized source text equals normalized output text (0 mismatches)); number: rejected (body heading equals citation_ar); page label: rejected (frontmatter equals the records)
- [x] collection README and registry are valid
- [x] held principles: 0
- [x] review items: 15 open, 15 total
- [x] OCR confirmation: no OCR run recorded (run ocr-confirm where Tesseract is installed)

ACCEPTANCE: (1) every content line maps to an output location and the apparatus lines are listed exclusions; (2) 0 wording mismatches over 54 facets and every preserved table cell; (3) 0 YAML errors with duplicate-key rejection; (4) 0 broken links or anchors; (5) every reciprocal relation is reciprocal and every index number has one file; (6) two consecutive builds give one manifest; (7) every applicable mutation of a temporary copy is rejected by a content check (body wording not applicable: no body supplied); (8) OCR confirmation not run in this profile.

## Second reader and visual review

RESULT: PASS (pdftotext): letters present in another order: 34; word differences: 3
- Visual review: 419 extracted lines on 11 pages compared with 300 dpi row crops and 500 dpi zooms; 2 findings raised, 1 standing (No discrepancy on any index page (pages 7-16). On the cataloging page (page 2) one finding was refuted (the circled copyright mark is a drawing, not text) and one stayed split between the refuters: the reading order of the deposit number groups (1440/1447 as read right to left vs 1447/1440 as one left-to-right string); recorded as an open reading question in the configuration (reading_questions) and in the review queue.)

## Exclusions (apparatus)

- Pages excluded by class: cover [1], basmala [3], half-title [4, 6], divider [5], blank [17]; the cataloging page (2) is preserved once in volume-details.md.
- Per index page: the running header (emblem image and ornament band), the running footer (publisher mark and page-number band) and the banner titles drawn as images; counts of images and non-ruling drawings per page are in work/records (extraction.page_apparatus) and in the build report.
- Reader corrections recorded: wrap_joins: 106; reference_separations: 39; geometry_spaces: 0; tatweel_runs_removed: 0; duplicate_space_glyphs_dropped: 2.

## Unresolved items

- Review queue: 15 open items by type {'link': 14, 'other': 1}: 14 see-also references whose targets lie outside the supplied index pages (left unresolved with target_supplied false), and 1 reading question (the order of the deposit-number groups on the cataloging page, read right to left as 1440/1447).
- Source anomalies recorded (text preserved as printed): number 205 title «منح الأرضي»; number 83 sub-topic opener «السلبية فيه توزيع».
- Appendix A of the master prompt was corrected from the extraction (five reference digits, the number order of shared entries, the facet count of number 33).

## Changes since the last run

- See work/reports/Admin-principles-1443-v6-changes-r7.md when present: this run changed no wording; the repository history records the review fixes (reports renamed to run-numbered files).

## Status

- Extraction and organization of the supplied index file are complete and verified (verify PASS, crosscheck PASS, 23 tests pass).
- Blocked in this profile: OCR confirmation (Tesseract absent). Next action on the windows-local profile: run `pipeline.py ocr-confirm --volume Admin-principles-1443-v6`, then `verify`; resolve the open review items through `decisions` in the configuration; supply the first per-principle PDF and calibrate body_sections (Appendix B).

## Renderers

- Raw Markdown was checked by the pipeline's lint; GitHub preview rendering could not be checked from this environment (no browser); the RTL wrapper is not effective in Obsidian (Markdown inside the HTML block is not rendered there), as the master prompt states.
