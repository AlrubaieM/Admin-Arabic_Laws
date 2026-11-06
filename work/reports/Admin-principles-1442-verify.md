# Verification report — Admin-principles-1442

RESULT: PASS

- [x] two consecutive builds give an identical manifest
- [x] published files equal a fresh derivation from the sources: 246 files
- [x] YAML parses with duplicate-key rejection: 244 files
- [x] no \u escapes of Arabic
- [x] no U+FFFD in any published file
- [x] Western digits and no presentation forms
- [x] one RTL wrapper per file
- [x] UTF-8 without BOM, LF, one trailing newline, no trailing whitespace
- [x] Markdown lint of bodies
- [x] required frontmatter keys and key order
- [x] ID grammar, filenames and numbers
- [x] body heading equals principle_title_ar
- [x] 0 broken relative links or anchors: 853 links
- [x] frontmatter equals the records: 240 principle files
- [x] every reciprocal relation is reciprocal: 977 relations over 240 principles
- [x] every generated ID matches the ID grammar
- [x] every page has a class of the fixed vocabulary: 144 pages
- [x] every source line has one class (0 unaccounted): {'apparatus:hidden_folio': 2, 'apparatus:page_number': 142, 'header_row': 460, 'index_wording': 2111, 'letter': 14, 'number': 737, 'outline': 153, 'page_label': 747, 'ruling_reference': 202, 'subtopic_opener': 155, 'summary_letter': 14, 'summary_topics': 16, 'table_cell': 1409, 'table_header': 111, 'table_heading': 2, 'title': 578, 'topic': 35}
- [x] every content line maps to at least one output location: 6284 content lines mapped; 604 apparatus/structural lines are listed exclusions
- [x] intentional duplicates are listed and permitted: 99 wordings appear in more than one principle file (shared entries)
- [x] lines held as review items: 0
- [x] every index number has exactly one principle file or is held: 240 numbers, 240 files, 0 held
- [x] no published principle without wording
- [x] normalized source text equals normalized output text (0 mismatches): 851 facets
- [x] fixture comparison: no fixture file
- [x] mutated temporary copy is rejected: index wording: rejected (normalized source text equals normalized output text (0 mismatches)); body wording: not applicable; YAML: rejected (YAML parses with duplicate-key rejection); link: rejected (0 broken relative links or anchors); ruling reference: not applicable; number: rejected (ID grammar, filenames and numbers); page label: rejected (frontmatter equals the records)
- [x] collection README and registry are valid
- [x] held principles: 0
- [x] review items: 0 open, 2 total
- [x] OCR confirmation: 0 unacknowledged disagreements: confirmed 1428, disagreeing 3102, kept automatically (second reader confirms) 3100, unacknowledged 0
