# Raw Intake Dropzone

This directory (`archive/raw/`) serves as the **incoming intake dropzone** for unorganized transcripts, session exports, zip packages, and research materials from ChatGPT or external archives.

## Ingestion Workflow

1. Drop new raw files/folders directly into `archive/raw/`.
2. Run the archival ingestion tool to:
   - Extract distinct conversation threads and handoffs with YAML frontmatter.
   - Compute cryptographic SHA-256 checksums and file sizes.
   - Assign deterministic Unique IDs (`THRD-xxx`, `HNDF-xxx`, `RCPT-xxx`, `RSRCH-xxx`, `EVD-xxx`, `MEDA-xxx`, `BNDL-xxx`).
   - Copy classified files into the permanent taxonomy under [`archive/chatgpt/`](../chatgpt/).
   - Append annotated bibliography entries to [`archive/PROJECT_MANIFEST.md`](../PROJECT_MANIFEST.md).
3. Once cataloged, the permanent, tracked copies live under [`archive/chatgpt/`](../chatgpt/).
