# USAGE: building the principles memory vault with uv

This guide shows how to turn the Arabic index PDFs of the Supreme Administrative Court principle collections into the Markdown memory vault in `Saudi-Principles/`, using the uv Python scripts of this project. Every command below is run from the project root:

`C:\Users\rubaie\Projects\Admin-Law-Claude\Admin-Pr-project\Admin-Pr`

## 1. What you need

| Tool | Used for | Where it is found |
| --- | --- | --- |
| Python 3.12 | runs the scripts | `C:\Users\rubaie\AppData\Local\Programs\Python\Python312\python.exe` |
| uv | creates the environment and runs every command | `uv` on PATH (`C:\Users\rubaie\.local\bin\uv.exe`) |
| Tesseract OCR with Arabic data | `ocr-confirm` (checking the text against the page images) | `C:\Program Files\Tesseract-OCR\tesseract.exe` |
| Poppler pdftotext | `crosscheck` and the automatic OCR confirmation | `C:\Program Files\Poppler\Library\bin\pdftotext.exe` |

Python packages: `pymupdf`, `PyYAML`, `fontTools` and `Pillow` come from the system Python; `hijridate` is installed into the project environment once (step 2).

## 2. One-time setup

Create the project environment (it reuses the system packages):

```powershell
uv venv --system-site-packages --no-managed-python --no-python-downloads --python "C:\Users\rubaie\AppData\Local\Programs\Python\Python312\python.exe" .venv
```

Install the one missing package:

```powershell
uv pip install --no-deps --python .venv\Scripts\python.exe hijridate
```

Tell the scripts where OCR and the second reader live (once per PowerShell window):

```powershell
$env:PRINCIPLES_VAULT_TESSERACT = "C:\Program Files\Tesseract-OCR\tesseract.exe"
$env:PRINCIPLES_VAULT_PDFTOTEXT = "C:\Program Files\Poppler\Library\bin\pdftotext.exe"
```

Every command runs through this uv template (shown once; the examples below repeat it in full):

```powershell
uv run --no-project --no-managed-python --no-python-downloads --python .venv\Scripts\python.exe <script> <arguments>
```

## 3. Where the PDFs go

Put the supplied PDFs under `Input/`, one folder per kind of source and one sub-folder per year collection, with their original names. Never edit or re-save a file there.

| Collection folder (under `Input\`) | Year folder | File |
| --- | --- | --- |
| مجموعة مبادئ وقرارات المحكمة الادارية العليا | مجموعة أعوام 1439-1440-1441 | Indexes-مجموعة مبادئ و قرارات المحكمة الادارية العليا أعوام 1439-1440-1441.pdf |
| مجموعة مبادئ وقرارات المحكمة الادارية العليا | مجموعة أعوام 1442 | Indexes-مجموعة مبادئ و قرارات المحكمة الادارية العليا أعوام 1442.pdf |
| مجموعة مبادئ وقرارات المحكمة الادارية العليا | مجموعة أعوام 1443 | Indexes-مجموعة مبادئ و قرارات المحكمة الادارية العليا أعوام 1443.pdf |
| مجموعة مبادئ وقرارات المحكمة الادارية العليا | مجموعة أعوام 1444 | Indexes-مجموعة مبادئ و قرارات المحكمة الادارية العليا أعوام 1444.pdf |

Each year folder is its own volume. The configured volumes are:

| volume_id | Source folder |
| --- | --- |
| `Admin-principles-1439-1441` | مجموعة أعوام 1439-1440-1441 |
| `Admin-principles-1442` | مجموعة أعوام 1442 |
| `Admin-principles-1443-v6` | مجموعة أعوام 1443 |
| `Admin-principles-1444-v6` | مجموعة أعوام 1444 |

## 4. Build the vault (the usual run)

Build every configured volume:

```powershell
uv run --no-project --no-managed-python --no-python-downloads --python .venv\Scripts\python.exe scripts\pipeline.py build --all
```

Build one volume only:

```powershell
uv run --no-project --no-managed-python --no-python-downloads --python .venv\Scripts\python.exe scripts\pipeline.py build --volume Admin-principles-1443-v6
```

A build prints one line per volume, for example:

```text
Admin-principles-1443-v6: 444 principle files, 1110 facets, 0 held, 448 files, review items open: 0, anomalies: 2
```

The build writes to `work/staging/` first, checks every file, and only then replaces the volume in `Saudi-Principles/`. If a check fails, nothing is replaced and the message names the file. A full `build --all` takes about 10 minutes.

## 5. Check the result

Verify a volume (two builds must be identical, every source line must reach the vault, wording must equal the source, links must work, OCR must be settled):

```powershell
uv run --no-project --no-managed-python --no-python-downloads --python .venv\Scripts\python.exe scripts\pipeline.py verify --volume Admin-principles-1443-v6
```

The report is `work\reports\Admin-principles-1443-v6-verify.md` and starts with `RESULT: PASS` or `RESULT: FAIL`.

Cross-check a volume with the second reader (Poppler):

```powershell
uv run --no-project --no-managed-python --no-python-downloads --python .venv\Scripts\python.exe scripts\pipeline.py crosscheck --volume Admin-principles-1443-v6
```

Confirm the text against the page images with OCR (Tesseract; about 30 minutes for all four volumes):

```powershell
uv run --no-project --no-managed-python --no-python-downloads --python .venv\Scripts\python.exe scripts\pipeline.py ocr-confirm --volume Admin-principles-1443-v6
```

OCR misreads (Arabic-Indic digits, the «في» ligature) are kept automatically when the second reader confirms the published line. Rebuild after `ocr-confirm`, then verify again.

## 6. Review the few lines nothing settles

Make the review page for a volume:

```powershell
uv run --no-project --no-managed-python --no-python-downloads --python .venv\Scripts\python.exe scripts\ocr_sheet.py sheet Admin-principles-1442
```

Open `work\review\ocr-sheet-Admin-principles-1442.html` in a browser, mark each line `keep` (the vault text matches the crop) or `flag`, and click **Download decisions**. Then apply the downloaded file and rebuild:

```powershell
uv run --no-project --no-managed-python --no-python-downloads --python .venv\Scripts\python.exe scripts\ocr_sheet.py apply Admin-principles-1442 "$HOME\Downloads\ocr-decisions-Admin-principles-1442.yaml"
```

All other open items are in `work\review\<volume_id>.yaml`. Fix them only through `decisions:` or `glyph_repairs` in `config\volumes\<volume_id>.yaml`, never by editing `Saudi-Principles/`.

## 7. Add a new volume

1. Copy the PDF into its own folder under `Input/`.
2. Copy an existing file in `config\volumes\` to `config\volumes\<new volume_id>.yaml` and set `volume_id`, `year_hijri`, the half-title or cover lines, `page_classes` for pages without a text layer, and the source file:

```yaml
volume_id: "Admin-principles-1445"
year_hijri: "1445"
source_files:
  - original_name: "<file name>.pdf"
    path: "<collection folder>/<year folder>/<file name>.pdf"
    sha256: "<sha256 of the file>"
    kind: "index"
    rank: 1
```

`path` is relative to `Input\` and uses `/`: the collection folder «مجموعة مبادئ وقرارات المحكمة الادارية العليا», the year folder «مجموعة أعوام 1445», then the file name.

Get the SHA-256 of every PDF under `Input\` with:

```powershell
Get-ChildItem Input -Recurse -Filter *.pdf | ForEach-Object { "{0}  {1}" -f (Get-FileHash $_.FullName).Hash.ToLower(), $_.Name }
```

3. Inventory the glyphs; glyphs that no font or other volume resolves get a crop under `work\calibration\<volume_id>\crops\`:

```powershell
uv run --no-project --no-managed-python --no-python-downloads --python .venv\Scripts\python.exe scripts\pipeline.py calibrate --volume Admin-principles-1445
```

4. For each unresolved glyph, add a `glyph_repairs` entry under its font in the configuration, read from the crop. Render a closer crop of any line with:

```powershell
uv run --no-project --no-managed-python --no-python-downloads --python .venv\Scripts\python.exe scripts\review_crop.py Admin-principles-1445 12 "<words of the line>" crop.png
```

5. Build, OCR-confirm, rebuild and verify (steps 4 and 5).

## 8. Run the tests

```powershell
uv run --no-project --no-managed-python --no-python-downloads --python .venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 9. What the vault contains

```text
Saudi-Principles\
  index.md                         registry of the volumes
  README.md                        short reader guide
  <volume_id>\
    index.md                       the volume's principles by letter and topic, with the IDs P / G / GI
    volume-details.md              cover or half-title lines, cataloging block, source file
    rulings-index.md               the rulings index as printed (verbatim table)
    instruments-index.md           the instruments index as printed (verbatim table)
    Principles\pNNN.md             one file per principle number (dNNN.md for a decision)
```

`rulings-index.md` holds «فهرس الأحكام» (in 1443: «فهرس القضايا والأحكام») and `instruments-index.md` holds «فهرس مستند الحكم». A decision «قرار (N)» listed in the index has its own file `dNNN.md`.

Cite a principle by its `principle_id`, for example `Admin-principles-1443-v6:p383`. `P0383` is the printed principle number, `G1777` the printed page in the «ص» column, and `GI0008` the page of the index file.

## 10. If something goes wrong

| Message | What to do |
| --- | --- |
| `staged files fail the content checks; nothing replaced` | Read the named file in `work\staging\`; usually a glyph without text: run `calibrate` and add a `glyph_repairs` entry. |
| `SHA-256 of … is …, configuration says …` | The PDF changed or the configuration has a wrong hash: put back the original file or update `sha256`. |
| `held` above 0 in the build line | A principle has an unresolved glyph; its item is in `work\review\<volume_id>.yaml`. |
| verify fails only on `OCR confirmation` | Make the review sheet (step 6) and apply the decisions. |
| `OCR confirmation blocked: tesseract not found` | Set `PRINCIPLES_VAULT_TESSERACT` (step 2). |

The master task prompt that defines all rules is `principles-vault-master-task-v1-rev03.md` (identical copy in `prompts/`); its revision of 06/11/2026 records the behaviour described here.
