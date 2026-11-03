# Admin-Pr

Task prompts and reviewed samples for building a Markdown vault of the judicial principles decided by the Saudi Supreme Administrative Court, as published by the Board of Grievances («مجموعة المبادئ التي قررتها المحكمة الإدارية العليا»).

## Layout

- `Input/` — untouched original PDFs of the principle collections, one sub-folder per volume (see `Input/README.md`).
- `prompts/principles-vault-master-task-v1.md` — the current master task prompt: extraction, organization, and citation specification for the principle collections (one PDF per principle plus the volume index pages).
- `prompts/archive/law-vault-master-task-v14.md` — the earlier master prompt for compiled laws, kept unchanged as the design baseline the v1 prompt derives from.
- `samples/Indexes-____________________________________________________1443.pdf` — the reviewed sample: the index pages of volume six of the 1443 AH collection (17 physical pages). Its SHA-256 is recorded in Appendix A of the v1 prompt.

## How the v1 prompt is used

Supply it together with the volume's PDF files as the implementation instruction. It is self-contained: environment, extraction protocol for the defective text layer observed in the sample, identifiers, folder layout, YAML schema, citations, relationships, verification, and the final-report rules. Appendix A holds the fixture facts read from the sample; Appendix B lists what the first per-principle PDF must establish before principle bodies are published.
