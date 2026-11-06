# Verification report — Admin-principles-1444-v6

RESULT: PASS

- [x] two consecutive builds give an identical manifest
- [x] published files equal a fresh derivation from the sources: 27 files
- [x] YAML parses with duplicate-key rejection: 25 files
- [x] no \u escapes of Arabic
- [x] no U+FFFD in any published file
- [x] Western digits and no presentation forms
- [x] one RTL wrapper per file
- [x] UTF-8 without BOM, LF, one trailing newline, no trailing whitespace
- [x] Markdown lint of bodies
- [x] required frontmatter keys and key order
- [x] ID grammar, filenames and numbers
- [x] body heading equals principle_title_ar
- [x] 0 broken relative links or anchors: 29 links
- [x] frontmatter equals the records: 23 principle files
- [x] every reciprocal relation is reciprocal: 0 relations over 23 principles
- [x] every generated ID matches the ID grammar
- [x] every page has a class of the fixed vocabulary: 13 pages
- [x] every source line has one class (0 unaccounted): {'apparatus:hidden_folio': 4, 'apparatus:page_number': 7, 'cataloging_text': 7, 'header_row': 24, 'index_wording': 107, 'letter': 1, 'number': 29, 'outline': 9, 'page_label': 29, 'subtopic_opener': 8, 'summary_letter': 13, 'summary_topics': 15, 'title': 28, 'topic': 7}
- [x] every content line maps to at least one output location: 253 content lines mapped; 35 apparatus/structural lines are listed exclusions
- [x] intentional duplicates are listed and permitted: 0 wordings appear in more than one principle file (shared entries)
- [x] lines held as review items: 0
- [x] every index number has exactly one principle file or is held: 23 numbers, 23 files, 0 held
- [x] no published principle without wording
- [x] normalized source text equals normalized output text (0 mismatches): 29 facets
- [x] fixture expectations: 4 fixture keys compared
- [x] mutated temporary copy is rejected: index wording: rejected (normalized source text equals normalized output text (0 mismatches)); body wording: not applicable; YAML: rejected (YAML parses with duplicate-key rejection); link: rejected (0 broken relative links or anchors); ruling reference: not applicable; number: rejected (ID grammar, filenames and numbers); page label: rejected (frontmatter equals the records)
- [x] collection README and registry are valid
- [x] held principles: 0
- [x] review items: 0 open, 0 total
- [x] OCR confirmation: 0 unacknowledged disagreements: confirmed 90, disagreeing 111, kept automatically (second reader confirms) 111, unacknowledged 0
