# Admin-Arabic_Laws

A memory vault of the judicial principles decided by the Saudi Supreme Administrative Court, as published by the Board of Grievances («مجموعة المبادئ التي قررتها المحكمة الإدارية العليا»), built from the published PDF files by a reproducible pipeline.

## Layout

- `Saudi-Principles/` — the vault: `README.md` (reader guide), `index.md` (registry of volumes), and one folder per volume (`Admin-principles-1443-v6/`) holding `index.md` (the volume's principles with their keywords and the IDs P/G/GI), `volume-details.md` (cover and cataloging data), `Principles/pNNN.md` (one file per principle number) and, when the volume prints them, `rulings-index.md` and `instruments-index.md` (its rulings and decisions index and its «مستند الحكم» index, as verbatim tables). The vault is a pure function of the sources and the configuration; nothing about the machine that built it is written there.
- `Input/` — the untouched source PDFs, in the user's own folders (one folder per kind of source, e.g. `Input/مجموعة مبادئ وقرارات المحكمة الادارية العليا/مجموعة أعوام 1443/`). A volume configuration names each file by `path` (relative to `Input/`); without `path` the file is read from `Input/<volume_id>/`.
- `config/volumes/<volume_id>.yaml` — the volume's identity, source files with SHA-256, page-class declarations, the cataloging block as printed, reader calibration (glyph repairs), recorded source anomalies and decisions.
- `scripts/` — the pipeline: `pipeline.py` (build, verify, crosscheck, calibrate, ocr-confirm), `pdf_source.py` (glyph-geometry reader), `vault_index.py` (index parser), `vault_model.py` (facets, relations, identifiers), `vault_emit.py` (files), `vault_verify.py` (checks), `review_crop.py` (500 dpi crops of a source line for visual review).
- `tests/` — unit tests (`test_units.py`: reader heuristics, parser rules, the verifier's negative paths, the held-principle path) and the sample build test (`test_pipeline.py`), with `tests/fixtures/<volume_id>.expected.yaml` and the frozen sample copies under `tests/fixtures/samples/` (`samples.yaml`, `configs/`, `expected/`).
- `work/` — internal records (`records/`), review queue (`review/<volume_id>.yaml`, `review/visual-<volume_id>.yaml`), anomalies, ledger (`ledger/<volume_id>.yaml`, `ledger/manifest.yaml`), calibration inventory (`calibration/<volume_id>/glyphs.yaml`) and reports (`reports/<volume_id>-build-r<run>.md`, `-verify.md`, `-crosscheck-r<run>.md`, `-changes-r<run>.md`, `-final-report.md`). Staging, recovery copies, crops and page renders are ignored by git.
- `prompts/principles-vault-master-task-v1.md` — the master task prompt the pipeline implements; `prompts/archive/law-vault-master-task-v14.md` — the earlier prompt for compiled laws.
- `samples/Indexes-1443-v6.pdf` — the reviewed sample (byte-identical to the Input copy), read by the tests.

## Running the pipeline

Step-by-step instructions with command examples: `USAGE.md` (also `USAGE.pdf`, regenerated with `scripts/render_usage_pdf.py`).

Create the project environment once (existing Python and uv; the prompt's section 3):

```bash
uv venv --system-site-packages --no-managed-python --no-python-downloads --python <python3> .venv
```

```bash
uv pip install --no-deps --python .venv/bin/python pymupdf hijridate
```

Build, verify and cross-check a volume:

```bash
uv run --no-project --no-managed-python --no-python-downloads --no-sync --python .venv/bin/python scripts/pipeline.py build --volume Admin-principles-1443-v6
```

```bash
uv run --no-project --no-managed-python --no-python-downloads --no-sync --python .venv/bin/python scripts/pipeline.py verify --volume Admin-principles-1443-v6
```

```bash
uv run --no-project --no-managed-python --no-python-downloads --no-sync --python .venv/bin/python scripts/pipeline.py crosscheck --volume Admin-principles-1443-v6
```

Run the tests:

```bash
uv run --no-project --no-managed-python --no-python-downloads --no-sync --python .venv/bin/python -m unittest discover -s tests -v
```

On Windows use the PowerShell templates of the prompt's section 3 with `.venv\Scripts\python.exe`. `ocr-confirm` needs Tesseract with Arabic data (`PRINCIPLES_VAULT_TESSERACT` or PATH); `crosscheck` needs Poppler's `pdftotext` (`PRINCIPLES_VAULT_PDFTOTEXT` or PATH). `pymupdf` and `hijridate` are required; `pdfplumber` is not used.

## What the reader handles

The reader (`scripts/pdf_source.py`) makes no assumption about the producer, the page size or the font names. Each technique below was met in a supplied file and is handled generally:

- **Defective ToUnicode maps** (hamza letters split into two glyphs, seen/sheen/sad/dad drawn as head plus tail, ligatures with two characters, reversed visual order). These are repaired by configured glyph rules and by geometry.
- **Re-printed or re-subset PDFs** (for example "Microsoft: Print To PDF" extracts). Fonts may be renamed (`CIDFont+F4`) and have almost no ToUnicode entries. Each font is identified by byte-identical glyph outlines in the verified sources of every configured volume (`discover_references`). It then takes their text and glyph repairs, and the build report lists the match. A subset tag is only six capital letters and `+`, so `CIDFont+` is kept as part of the name.
- **Bullets drawn as small filled vector circles** instead of glyphs. These are read as «•».
- **Text placed outside the visible page box**, such as editor leftovers. This is not read, and its count is recorded in the work records.
- **A ruled frame with no text** is a drawing, not a table.
- **A derived copy** of a source (`kind: derived_copy`, with `derived_from` and `not_read_basis`) stays recorded in the configuration but is not read for wording. The build report lists it.
- **An index that prints a component for no entry**, for example no ruling references. This is reported once per file, not as one review item per principle.

## Adding a volume

1. Put the PDFs under `Input/` (any folder) with their original names.
2. Add `config/volumes/<volume_id>.yaml` (copy the existing one). The volume_id is `Admin-principles-<year>[-<last year>][-v<N>]`: a year range for a collection of several years, and `-v<N>` only when the source prints a volume ordinal. Set `source_files[].path`, then fill in identity, `source_files` with SHA-256 and kind, `page_classes` for the pages without a text layer, and run `pipeline.py calibrate --volume <volume_id>` to inventory the glyphs; add `glyph_repairs` for every unresolved glyph from the crops under `work/calibration/<volume_id>/crops/`.
3. Build, verify, cross-check, and run `ocr-confirm` where Tesseract is installed; resolve review items through `decisions` in the configuration, never by editing the vault. A principle whose text still carries an unresolved glyph is held: it gets no file until the repair or decision exists.
4. OCR disagreements are settled automatically where the evidence settles them (project rule 1 in `CLAUDE.md`). When Tesseract misreads a line but the second reader, Poppler `pdftotext`, finds every number and word of the published line on the same page, the line is kept with `resolution: auto_keep` and its basis in `work/review/ocr-<volume_id>.yaml`. The second reader's known splits are allowed: one word in up to three adjacent tokens, letters in another order, or an undecodable glyph. A line that no evidence settles stays open.
5. Review the OCR disagreements that remain open: `scripts/ocr_sheet.py sheet <volume_id>` writes `work/review/ocr-sheet-<volume_id>.html`. Open it in a browser, mark each line `keep` (the published text matches the crop) or `flag` (it does not), and download `ocr-decisions-<volume_id>.yaml`. Then `scripts/ocr_sheet.py apply <volume_id> <that file>` adds the `keep` choices to `decisions:` (existing decisions are never changed) and lists the flagged lines, which need a glyph repair or a source check. Rebuild and verify.
