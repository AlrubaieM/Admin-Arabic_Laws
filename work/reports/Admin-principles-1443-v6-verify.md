# Verification report — Admin-principles-1443-v6

RESULT: PASS

- [x] two consecutive builds give an identical manifest
- [x] published files equal a fresh derivation from the sources: 450 files
- [x] YAML parses with duplicate-key rejection: 448 files
- [x] no \u escapes of Arabic
- [x] no U+FFFD in any published file
- [x] Western digits and no presentation forms
- [x] one RTL wrapper per file
- [x] UTF-8 without BOM, LF, one trailing newline, no trailing whitespace
- [x] Markdown lint of bodies
- [x] required frontmatter keys and key order
- [x] ID grammar, filenames and numbers
- [x] body heading equals principle_title_ar
- [x] 0 broken relative links or anchors: 1112 links
- [x] frontmatter equals the records: 444 principle files
- [x] every reciprocal relation is reciprocal: 3302 relations over 444 principles
- [x] every generated ID matches the ID grammar
- [x] every page has a class of the fixed vocabulary: 219 pages
- [x] every source line has one class (0 unaccounted): {'apparatus:hidden_folio': 4, 'apparatus:page_number': 213, 'cataloging_text': 7, 'header_row': 507, 'index_wording': 3134, 'letter': 14, 'number': 990, 'outline': 123, 'page_label': 1075, 'ruling_reference': 256, 'subtopic_opener': 129, 'summary_letter': 14, 'summary_topics': 14, 'table_cell': 2423, 'table_header': 213, 'title': 783, 'topic': 31}
- [x] every content line maps to at least one output location: 9206 content lines mapped; 724 apparatus/structural lines are listed exclusions
- [x] intentional duplicates are listed and permitted: 86 wordings appear in more than one principle file (shared entries)
- [x] lines held as review items: 0
- [x] every index number has exactly one principle file or is held: 444 numbers, 444 files, 0 held
- [x] no published principle without wording
- [x] normalized source text equals normalized output text (0 mismatches): 1110 facets
- [x] fixture comparison: no fixture file
- [x] mutated temporary copy is rejected: index wording: rejected (normalized source text equals normalized output text (0 mismatches)); body wording: not applicable; YAML: rejected (YAML parses with duplicate-key rejection); link: rejected (0 broken relative links or anchors); ruling reference: rejected (normalized source text equals normalized output text (0 mismatches)); number: rejected (ID grammar, filenames and numbers); page label: rejected (frontmatter equals the records)
- [x] collection README and registry are valid
- [x] held principles: 0
- [x] review items: 0 open, 0 total
- [x] OCR confirmation: 0 unacknowledged disagreements: confirmed 1974, disagreeing 4393, kept automatically (second reader confirms) 4393, unacknowledged 0
