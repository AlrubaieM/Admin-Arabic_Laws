# Verification report — Admin-principles-1439-1441

RESULT: PASS

- [x] two consecutive builds give an identical manifest
- [x] published files equal a fresh derivation from the sources: 166 files
- [x] YAML parses with duplicate-key rejection: 164 files
- [x] no \u escapes of Arabic
- [x] no U+FFFD in any published file
- [x] Western digits and no presentation forms
- [x] one RTL wrapper per file
- [x] UTF-8 without BOM, LF, one trailing newline, no trailing whitespace
- [x] Markdown lint of bodies
- [x] required frontmatter keys and key order
- [x] ID grammar, filenames and numbers
- [x] body heading equals principle_title_ar
- [x] 0 broken relative links or anchors: 604 links
- [x] frontmatter equals the records: 160 principle files
- [x] every reciprocal relation is reciprocal: 678 relations over 160 principles
- [x] every generated ID matches the ID grammar
- [x] every page has a class of the fixed vocabulary: 110 pages
- [x] every source line has one class (0 unaccounted): {'apparatus:hidden_folio': 2, 'apparatus:page_number': 108, 'header_row': 340, 'index_wording': 1598, 'letter': 15, 'number': 513, 'outline': 144, 'page_label': 539, 'ruling_reference': 120, 'subtopic_opener': 148, 'summary_letter': 15, 'summary_topics': 17, 'table_cell': 1130, 'table_header': 132, 'table_heading': 4, 'title': 322, 'topic': 34}
- [x] every content line maps to at least one output location: 4731 content lines mapped; 450 apparatus/structural lines are listed exclusions
- [x] intentional duplicates are listed and permitted: 69 wordings appear in more than one principle file (shared entries)
- [x] lines held as review items: 0
- [x] every index number has exactly one principle file or is held: 160 numbers, 160 files, 0 held
- [x] no published principle without wording
- [x] normalized source text equals normalized output text (0 mismatches): 602 facets
- [x] fixture comparison: no fixture file
- [x] mutated temporary copy is rejected: index wording: rejected (normalized source text equals normalized output text (0 mismatches)); body wording: not applicable; YAML: rejected (YAML parses with duplicate-key rejection); link: rejected (0 broken relative links or anchors); ruling reference: not applicable; number: rejected (ID grammar, filenames and numbers); page label: rejected (frontmatter equals the records)
- [x] collection README and registry are valid
- [x] held principles: 0
- [x] review items: 0 open, 1 total
- [x] OCR confirmation: 0 unacknowledged disagreements: confirmed 973, disagreeing 2267, kept automatically (second reader confirms) 2266, unacknowledged 0
