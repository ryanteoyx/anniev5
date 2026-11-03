# Annie

Annie is a document-intake and **3-way matching** tool for accounts payable. It ingests
purchase orders, supplier invoices and goods-receipt documents (PDF, image, Word, Excel),
extracts and standardises their fields, then matches invoices against their POs — flagging
duplicates, overbilling and anything that needs human review.

Extraction is **rule-based** (PDF text + OCR, regex/label heuristics, content fingerprints) —
there is no external LLM/API dependency and no API key required.

## Features

- **Document intake** — PDF, image (PNG/JPG/HEIC/TIFF), DOCX and spreadsheet uploads
- **Text extraction** — `pdfplumber`/PyMuPDF for digital PDFs, OCR fallback (RapidOCR / Tesseract) for scans
- **Classification & field extraction** — document type, supplier, amounts, dates, PO citations, signatures
- **3-way matching (Module 2)** — registers POs, allocates invoices, detects partials, duplicates and overbilling
- **Email intake (optional)** — background IMAP monitor ingests attachments automatically
- **Audit trail** — every intake and matching event is logged

## Requirements

- **Python 3.11** (recommended). Newer versions such as 3.14 may lack prebuilt wheels for
  `onnxruntime` / PyMuPDF; 3.12 also works.
- For OCR on scanned/image documents, either RapidOCR (installed via `requirements.txt`) or
  a system **Tesseract** install (`brew install tesseract`). Digital PDFs need neither.

## Quick start

```bash
# 1. create a virtualenv on Python 3.11
python3.11 -m venv .venv
source .venv/bin/activate

# 2. install dependencies
pip install -r requirements.txt

# 3. run the app
streamlit run app.py
```

The app opens at http://localhost:8501.

Use **Controls → Load sample documents** (requires pre-extracted JSONs) or the
**Submit Document** page to upload a file from `samples/` and watch it flow through matching.

## Deploy (Streamlit Community Cloud, free)

Deploy from share.streamlit.io: repository `ryanteoyx/anniev5`, branch `ui-polish`, main file
`app.py`, Python 3.11. `packages.txt` installs Tesseract and the OCR system libraries.

Community Cloud puts apps to sleep after 12 hours without traffic. The
[`Keep Streamlit app awake`](.github/workflows/keep-awake.yml) GitHub Action opens the app in a
headless browser every 4 hours (pressing the wake-up button if needed) via
[`scripts/keep_awake.py`](scripts/keep_awake.py). If the app fails to come up, the run fails and
GitHub emails you. Update `APP_URL` in the workflow if the app's address changes.

Note: Community Cloud's disk is not persistent — the SQLite database and uploaded files reset
whenever the app restarts. For durable data, see [`deploy/`](deploy/) (self-hosted VM).

## Optional: email intake

Set these environment variables (e.g. in a `.env` file) to enable the background inbox monitor:

```
EMAIL_ADDRESS=...
EMAIL_PASSWORD=...
EMAIL_IMAP_HOST=...
EMAIL_PORT=993
EMAIL_SUBJECT_FILTER=            # optional
EMAIL_AUTO_FETCH=1               # set 0 to disable
```

## Project layout

| Path | Purpose |
|------|---------|
| `app.py` | Streamlit UI |
| `annie_core.py` | Engine: extraction, classification, matching, storage |
| `samples/` | Example POs and invoices to test the pipeline |
| `reference_samples/` | Reference config / label profiles (optional) |
| `storage/` | Generated at runtime — stored files & archives (git-ignored) |
| `annie_v4.db` | Local SQLite database (git-ignored) |

## Data & storage

State lives in a local **SQLite** file (`annie_v4.db`) and stored originals under `storage/`.
Both are git-ignored and recreated on first run. On any serverless/ephemeral host these reset
on restart — use a host with a persistent disk (or an external database) to keep records.
