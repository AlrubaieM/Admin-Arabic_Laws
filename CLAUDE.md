# Project rules (Admin-Pr principles vault)

These rules hold for every task in this project. They come from the user's decisions, with the date of each. The master task prompt (`principles-vault-master-task-v1-rev03.md`) remains the specification.

1. **Best accurate result, automatically** (user rule, 06/11/2026). The pipeline always keeps the best, most accurate and exact extraction or conversion result by itself.
   - When independent evidence settles which reading is right, the scripts choose it and record the basis in `work/`. Examples are a second reader that confirms the text layer, or glyph outlines identical to a verified font.
   - A reading is never accepted only because nothing contradicts it.
   - Only readings that no evidence settles become review items for the user.
2. **Any PDF, generically** (user rule, 06/11/2026). The scripts handle every PDF format and technique they meet as a general mechanism: re-prints, renamed or re-subset fonts, defective text maps, vector-drawn marks, off-page text and other page sizes. Nothing is written for one sample or one font name. Volume-specific values live only in `config/volumes/<volume_id>.yaml`.
3. **Extract and convert only** (user rule, 06/11/2026). The task is the faithful extraction and conversion of the supplied PDFs into the vault. Resolving «راجع» see-also links, comparing the summary index with the detailed index, and asking reading questions about the order of printed values are not part of the task.
   - They never become review items.
   - Where the scripts still notice them, they are notes in the build report and `work/records` only.
   - Printed values are converted by the reader's general conventions. For example, digit groups are read right to left as printed.
4. **Run through uv** with the project `.venv` (spec section 3). Fix script errors in the scripts, test first, and keep all tests passing.
5. **Never hand-edit `Saudi-Principles/`.** Every manual fix is a decision in the volume configuration.
