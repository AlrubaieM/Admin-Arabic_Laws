# Verification report — Admin-principles-1443-v6

RESULT: PASS

- [x] two consecutive builds give an identical manifest
- [x] published files equal a fresh derivation from the sources: 41 files
- [x] YAML parses with duplicate-key rejection: 41 files
- [x] no \u escapes of Arabic
- [x] one RTL wrapper per file
- [x] UTF-8 without BOM, LF, one trailing newline, no trailing whitespace
- [x] Markdown lint of bodies
- [x] required frontmatter keys and key order
- [x] ID grammar and filenames
- [x] 0 broken relative links or anchors: 239 links
- [x] every reciprocal relation is reciprocal: 37 principles
- [x] every source line has one class (0 unaccounted): {'apparatus:hidden_folio': 4, 'apparatus:page_number': 10, 'cataloging_text': 7, 'header_row': 27, 'index_wording': 155, 'letter': 2, 'number': 49, 'outline': 12, 'page_label': 51, 'ruling_reference': 13, 'subtopic_opener': 10, 'summary_letter': 14, 'summary_topics': 14, 'title': 50, 'topic': 5}
- [x] lines held as review items: 0
- [x] every index number has exactly one principle file: 37 numbers, 37 files
- [x] no published principle without wording
- [x] normalized source text equals normalized output text (0 mismatches): 54 facets
- [x] fixture expectations: 37 principles compared
- [x] mutated temporary copy is rejected: index wording: rejected; body wording: not applicable; YAML: rejected; link: rejected; ruling reference: rejected; number: rejected; page label: rejected
- [x] collection README and registry are valid
- [x] review items: 0 open, 0 total
- [x] OCR confirmation: blocked: no OCR run recorded (tesseract unavailable in this profile)
