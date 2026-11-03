# Input

Untouched original PDF files of the Board of Grievances principle collections («مجموعة المبادئ التي قررتها المحكمة الإدارية العليا»), as supplied. These are the sources the master task prompt (`prompts/principles-vault-master-task-v1.md`) reads.

## Rules

- One sub-folder per volume, named by its `volume_id` (for example `Input/Admin-principles-1443-v6/`).
- Inside it: the volume's index pages (one or more PDFs) and one PDF per principle, each under its original filename, unchanged.
- Never edit, rename, re-save, or re-export a file here. Each file's SHA-256 is recorded in the volume configuration under `config/volumes/<volume_id>.yaml`.
- The reviewed index sample stays in `samples/`; copy it here under its volume folder when the volume is processed.
