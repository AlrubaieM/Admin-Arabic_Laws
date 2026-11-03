# Verification report — Admin-principles-1443-v6

RESULT: PASS

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
