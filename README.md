# Admin-Pr

A memory vault of the judicial principles decided by the Saudi Supreme Administrative Court, as published by the Board of Grievances («مجموعة المبادئ التي قررتها المحكمة الإدارية العليا»), built from the published PDF files by a reproducible pipeline.

## Layout

- `Saudi-Principles/` — the vault: `README.md` (reader guide), `index.md` (registry of volumes), and one folder per volume (`Admin-principles-1443-v6/`) holding `index.md` (the volume's principles with their keywords and the IDs P/G/GI), `volume-details.md` (cover and cataloging data) and `Principles/pNNN.md` (one file per principle number). The vault is a pure function of the sources and the configuration; nothing about the machine that built it is written there.
- `Input/<volume_id>/` — the untouched source PDFs (one sub-folder per volume; see `Input/README.md`).
- `config/volumes/<volume_id>.yaml` — the volume's identity, source files with SHA-256, page-class declarations, the cataloging block as printed, reader calibration (glyph repairs), recorded source anomalies and decisions.
- `scripts/` — the pipeline: `pipeline.py` (build, verify, crosscheck, calibrate, ocr-confirm), `pdf_source.py` (glyph-geometry reader), `vault_index.py` (index parser), `vault_model.py` (facets, relations, identifiers), `vault_emit.py` (files), `vault_verify.py` (checks), `review_crop.py` (500 dpi crops of a source line for visual review).
- `tests/` — unit tests (`test_units.py`: reader heuristics, parser rules, the verifier's negative paths, the held-principle path) and the sample build test (`test_pipeline.py`), with `tests/fixtures/<volume_id>.expected.yaml` and the frozen sample copies under `tests/fixtures/samples/` (`samples.yaml`, `configs/`, `expected/`).
- `work/` — internal records (`records/`), review queue (`review/<volume_id>.yaml`, `review/visual-<volume_id>.yaml`), anomalies, ledger (`ledger/<volume_id>.yaml`, `ledger/manifest.yaml`), calibration inventory (`calibration/<volume_id>/glyphs.yaml`) and reports (`reports/<volume_id>-build-r<run>.md`, `-verify.md`, `-crosscheck-r<run>.md`, `-changes-r<run>.md`, `-final-report.md`). Staging, recovery copies, crops and page renders are ignored by git.
- `prompts/principles-vault-master-task-v1.md` — the master task prompt the pipeline implements; `prompts/archive/` — the earlier prompts (the long 03/11/2026 revision of this prompt and the prompt for compiled laws).
- `samples/Indexes-1443-v6.pdf` — the reviewed sample (byte-identical to the Input copy), read by the tests.

## Running the pipeline

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

## Adding a volume

1. Put the PDFs under `Input/<volume_id>/` with their original names.
2. Add `config/volumes/<volume_id>.yaml` (copy the existing one): identity, `source_files` with SHA-256 and kind, `page_classes` for the pages without a text layer, and run `pipeline.py calibrate --volume <volume_id>` to inventory the glyphs; add `glyph_repairs` for every unresolved glyph from the crops under `work/calibration/<volume_id>/crops/`.
3. Build, verify, cross-check, and run `ocr-confirm` where Tesseract is installed; resolve review items through `decisions` in the configuration, never by editing the vault. A principle whose text still carries an unresolved glyph is held: it gets no file until the repair or decision exists.
