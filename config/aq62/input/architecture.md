<!--
architecture.md — STRUCTURAL changes only: baseline bumps, kernel moves,
components added or dropped, anything that changes how the system is put
together. Ordinary features and bugfixes belong in part_a.md / part_b.md.

One bullet per change. If the release has none, empty this file — the "Major
architectural changes" list is then omitted from the document entirely, which
is more honest than a bullet saying "none".
-->

- **Modem:** Cavli AT command layer added to MPSS.
- **SDK:** AT bridge (`at-bridge`) added to the SDK manifest and binary packaging.
