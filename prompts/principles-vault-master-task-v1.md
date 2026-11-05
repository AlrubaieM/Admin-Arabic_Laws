# Master task prompt: Saudi Supreme Administrative Court principles to a Markdown memory vault

Revision 05/11/2026. This text replaces the long 03/11/2026 revision (kept at prompts/archive/principles-vault-master-task-v1-rev03.md) and states the settled design after the user's decisions of 04/11/2026. Do not reopen the decisions below.

## 1. Role and objective

Act as a senior Python engineer and Arabic legal-text extraction specialist. Build and run a reusable, deterministic local program (uv scripts) that converts one PDF of a Board of Grievances (ديوان المظالم) collection «مجموعة المبادئ التي قررتها المحكمة الإدارية العليا» into a Markdown memory vault of principles.

- The input is one PDF per volume: the volume's "index" pages. They are not a navigation index. They print the principles themselves, grouped by letter, topic and sub-topic, each with its ruling references, its principle number and its printed page.
- The unit of the vault is the principle (المبدأ), identified by the number the volume gives it.
- The statements printed in the PDF are the principles. Never call them an index, an index wording, a summary or an extract. The case files are not supplied and never will be.
- The vault is law text: verbatim, no summary, no translation, no correction, no addition. Source typos are kept as printed.
- Out of scope: RAG, embeddings, search, legal analysis, web references, case files.

## 2. Inputs and project layout

- Input/<volume_id>/ holds the untouched PDF (SHA-256 recorded in config). Example: Input/Admin-principles-1443-v6/Indexes-1443-v6.pdf.
- config/volumes/<volume_id>.yaml: volume identity (collection_name_ar and _en, volume_ordinal_ar, volume_number, year_hijri, publisher), source files with SHA-256 and page_label_offset, cataloging block as printed, cover lines, page classes (cover, cataloging, basmala, half_title, divider, index_summary, index_detailed, blank), reader settings and glyph repairs, recorded source anomalies, decisions.
- scripts/: pipeline.py (build, verify, crosscheck, calibrate, ocr-confirm), pdf_source.py (glyph-geometry reader), vault_index.py (parser), vault_model.py (principles and facets), vault_emit.py (files), vault_verify.py (checks), review_crop.py.
- tests/: unit tests, sample build test, fixtures with expected values.
- work/: records, review queue, anomalies, ledger, calibration, reports. Internal only; nothing about the machine or the run is written into the vault.
- Saudi-Principles/: the vault, in its own folder at the repository root.
- volume_id grammar: <Collection>-principles-<year>-v<N>, English, for example Admin-principles-1443-v6.

## 3. Environment and uv

- Reuse what exists: Python 3.11+, uv, a project .venv created with uv venv --system-site-packages --no-managed-python --no-python-downloads. Install only missing packages with --no-deps (pymupdf, hijridate, pyyaml). Never install or download anything that is already present.
- Run every script with: uv run --no-project --no-managed-python --no-python-downloads --no-sync --python .venv/bin/python scripts/pipeline.py <command> --volume <volume_id>
- Output must be a pure function of the PDF and the configuration: same input, byte-identical vault. Two consecutive builds give one manifest.
- Commit and push only when the user asks. Commits end with the attribution lines the session specifies.

## 4. Text rules

- UTF-8 without BOM, LF, NFC, one trailing newline, no trailing whitespace, no \u escapes, no U+FFFD.
- Western digits only; no Arabic-Indic digits, no presentation forms.
- Arabic text is copied letter for letter. Do not normalize alef/hamza/ya/ta-marbuta, do not add or strip diacritics, do not repair spelling or grammar.
- Ruling references like (أ/3610/1442) are read right to left number by number as printed; a hyphenated number (2771-2893) is kept verbatim.
- Every file body is wrapped once in <div dir="rtl"> … </div>. Source text is Markdown-escaped so that no block or inline syntax is created by it.
- English folder and file names; English code; Arabic values.

## 5. Extraction rules

- The text layer of the sample is defective. Read glyph by glyph with PyMuPDF's text trace using the ToUnicode map of the font object used on the page, keyed by glyph id.
- Configure repairs per font in the volume configuration, each justified by a crop: head glyphs of س ش ص ض with dropped tail glyphs, hamza letters composed with their carrier, lam-alef ligature, zero-width ligature continuations dropped, overlapping duplicate glyphs and spaces read once, symbol-encoded digits, tatweel handling.
- Spaces come from the glyphs; a geometric space is inserted only between two word glyphs and every insertion is counted.
- Segment the table from its drawn rulings (white strokes ignored; a black dashed stroke marks a sibling row). Form lines inside each table cell so that number and page cells never merge with wording.
- The detailed table has three columns: the statement, the principle number (الرقم), the printed page (ص). The header row repeats on every page and is structure, not content. Letter, topic and outline lines can share one full-width row.
- A glyph that cannot be resolved is never guessed: the principle is held (no file published) and a review item is raised.
- Cover and basmala pages without a text layer are read once from the image and recorded in the configuration (cover_lines_ar). OCR confirmation runs where Tesseract exists; otherwise a page-by-page visual review is recorded in work/review and the OCR stage is reported as not run.

## 6. Principle model

- Parse blocks: entry, sibling, continuation, see_also. Each has statement paragraphs, ruling references, numbers and printed page labels.
- A number listed under several topics is one principle with several listings (facets); one file holds them all. Multi-number entries are split into their numbers, each number keeping its own page label.
- Keys are numeric (p364). A decided split of one number into distinct rulings is key <number>-dupK (p123-dup2).
- A «راجع» entry keeps its text verbatim; a missing target is not invented.
- A second index file for the same volume is read in full. Identical wording adds nothing; different wording is kept as an extra section with its own paragraphs and raises a review item; a number present only in a lower-ranked file is published from it.
- Anomalies in the source (a title spelled differently from its own cross-reference) are recorded in the configuration and work/anomalies, never corrected, never written into the vault.

## 7. Identifiers

- P0000: principle number as printed, four digits (P0364).
- G0000: the printed page from the third column of the table, four digits (G1685). The printed label equals the physical page minus page_label_offset on the index pages.
- GI0000: the physical page of the index PDF on which the entry stands, four digits (GI0016).
- principle_id: <volume_id>:p<number> (Admin-principles-1443-v6:p364). File name p<number>.md (p364.md, p123-dup2.md).
- A principle with several listings lists every G and GI in order of appearance; do not collapse them.

## 8. The vault: exactly these files

Saudi-Principles/
- README.md: a few lines. What the files are, and what P, G, GI, principle_id mean.
- index.md: index 1 of 2. Lists the volume folders with their principle count, as links.
- <volume_id>/index.md: index 2 of 2, for that volume (a single PDF).
- <volume_id>/volume-details.md: the volume's cover lines and cataloging block as printed.
- <volume_id>/Principles/p<number>.md: one file per principle.

There is no other index and no Indexes/ folder.

### 8.1 Volume index (<volume_id>/index.md)

- Short frontmatter: collection names, volume_number, volume_id, principle_count.
- Heading with the collection name and the volume ordinal; the letter-by-letter topic list of the summary pages; then, per letter and topic, a heading, the topic's outline lines as printed, and a table:

| الكلمات المفتاحية | P | G | GI |
| --- | --- | --- | --- |
| [keywords linked to Principles/p364.md] | P0364 | G1685 | GI0016 |

- One row per listing (a principle with several listings has several rows). Keywords are the sub-topic and bullet title as printed.
- No legend sentence, no notes, no counts in prose.

### 8.2 Principle file

Frontmatter, in this order and nothing else:

```
collection_name_ar: "مجموعة المبادئ التي قررتها المحكمة الإدارية العليا عام 1443"
collection_name_en: "Principles Decided by the Supreme Administrative Court year 1443"
volume_number: "6"
principle_id: "Admin-principles-1443-v6:p364"
principle_number: "364"
principle_title_ar: "<the principle's title as printed>"
principle_title_en: "Principle 364"
index_letter: "أ"
page_id: "G1685"
index_page_id: "GI0016"
ruling_references:
- ref: "(أ/3610/1442)"
```

page_id, index_page_id and index_letter become lists when the principle has listings with different values. ruling_references is omitted when none is printed.

Body, nothing else:

```
# <principle_title_ar>

<the principle's paragraphs as printed>

<the reference line as printed>
```

A further listing of the same number follows as "## <its title>" with its paragraphs and reference line. A «راجع» entry shows its «راجع: …» text and its reference line.

### 8.3 Volume details

Cover lines, the cataloging block as printed (label | value table where the source prints label and value), and a short frontmatter with identity, cataloging {deposit_number, isbn, extent_ar}, publisher, source_origin and source file names.

### 8.4 Forbidden in the vault

- Any added paragraph, note, legend, blockquote, "repository note", explanation, translation or summary.
- Any link list, hierarchy line, citation heading or "see also" generated by the program.
- Any wording that calls the printed principles an index, an index wording or a form of the principle.
- Extra frontmatter keys: citations, sources, hierarchy, facets, relations, status, open issues, text_basis, body_supplied. These stay in work/records and work/review.

## 9. Verification (the verify command; it must fail on any violation)

1. Determinism: two builds give an identical manifest; published files equal a fresh derivation from the PDF.
2. Format: YAML parses with duplicate-key rejection; no \u escapes, no U+FFFD, Western digits only, one RTL wrapper per file, UTF-8/LF/trailing-newline rules, Markdown lint.
3. Frontmatter: required keys in the fixed order; values equal the extraction records; principle_number matches the file name; heading equals principle_title_ar; ID grammar; no broken link in the indexes.
4. Coverage: every source line has one class (zero unclassified); every content line maps to an output location (statements and references to the bodies, numbers and page labels to the P and G ids, outline, letter and topic lines to the volume index, cataloging text to the details); apparatus lines (page numbers, hidden folio marks) and the table's header row are listed exclusions; every index number has exactly one file or is held.
5. Fidelity: normalized source text equals normalized output text for every listing (zero mismatches).
6. Mutation test on a temporary copy: a changed statement, duplicate YAML key, broken index link, changed ruling reference, changed principle_number and changed page_id are each rejected by a content check.
7. Fixture: values in tests/fixtures/<volume_id>.expected.yaml match.
8. Crosscheck: an independent reader (pdftotext) agrees up to documented letter-order differences.
9. OCR confirmation: run where Tesseract exists; otherwise stated as not run, with the visual review.
10. Unit tests and the sample build test pass.

## 10. Execution order

1. Inspect the PDF: page classes, fonts, text layer, image-only pages. Record them.
2. Write or update the volume configuration; calibrate glyph repairs with crops.
3. Extract and parse; build the principles; record anomalies and review items.
4. Build into staging, validate with the content checks, then replace the vault files; keep a recovery copy; update the ledger.
5. Verify, crosscheck, run tests.
6. Write work/reports/<volume_id>-final-report.md.

## 11. Final report (in the chat, short)

- What was produced: the number of principle files, listings, held principles.
- Which checks ran and passed; which did not run and why (for example OCR).
- Open review items and recorded source anomalies, listed once.
- Never state a check passed unless it was run in this session.

## 12. Adding another volume

Put its PDF in Input/<new_volume_id>/, add config/volumes/<new_volume_id>.yaml with identity and SHA-256, calibrate the reader on that volume's glyphs, and run build, verify, crosscheck. The collection index.md gains one line; no other index is created. Fixture values of a volume are tests, never parser constants.
