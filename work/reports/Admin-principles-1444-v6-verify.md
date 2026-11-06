# Verification report — Admin-principles-1444-v6

RESULT: PASS

- [x] two consecutive builds give an identical manifest
- [x] published files equal a fresh derivation from the sources: 401 files
- [x] YAML parses with duplicate-key rejection: 399 files
- [x] no \u escapes of Arabic
- [x] no U+FFFD in any published file
- [x] Western digits and no presentation forms
- [x] one RTL wrapper per file
- [x] UTF-8 without BOM, LF, one trailing newline, no trailing whitespace
- [x] Markdown lint of bodies
- [x] required frontmatter keys and key order
- [x] ID grammar, filenames and numbers
- [x] body heading equals principle_title_ar
- [x] 0 broken relative links or anchors: 814 links
- [x] frontmatter equals the records: 395 principle files
- [x] every reciprocal relation is reciprocal: 1521 relations over 395 principles
- [x] every generated ID matches the ID grammar
- [x] every page has a class of the fixed vocabulary: 155 pages
- [x] every source line has one class (0 unaccounted): {'apparatus:hidden_folio': 4, 'apparatus:page_number': 149, 'cataloging_text': 7, 'header_row': 460, 'index_wording': 2484, 'letter': 13, 'number': 737, 'outline': 106, 'page_label': 768, 'subtopic_opener': 107, 'summary_letter': 13, 'summary_topics': 15, 'table_cell': 1924, 'table_header': 149, 'title': 445, 'topic': 35}
- [x] every content line maps to at least one output location: 6803 content lines mapped; 613 apparatus/structural lines are listed exclusions
- [x] intentional duplicates are listed and permitted: 55 wordings appear in more than one principle file (shared entries)
- [x] lines held as review items: 0
- [x] every index number has exactly one principle file or is held: 395 numbers, 395 files, 0 held
- [x] no published principle without wording
- [x] normalized source text equals normalized output text (0 mismatches): 812 facets
- [x] fixture comparison: no fixture file
- [x] mutated temporary copy is rejected: index wording: rejected (normalized source text equals normalized output text (0 mismatches)); body wording: not applicable; YAML: rejected (YAML parses with duplicate-key rejection); link: rejected (0 broken relative links or anchors); ruling reference: not applicable; number: rejected (ID grammar, filenames and numbers); page label: rejected (frontmatter equals the records)
- [x] collection README and registry are valid
- [x] held principles: 0
- [x] review items: 0 open, 0 total
- [x] OCR confirmation: 0 unacknowledged disagreements: confirmed 1849, disagreeing 2692, kept automatically (second reader confirms) 2692, unacknowledged 0
