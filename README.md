# Annie

Annie is an accounts-payable tool for **3-way matching**. It takes in purchase orders / purchase
requisitions (PO/PRs) and supplier invoices as PDF, image, Word or spreadsheet files, extracts and
checks their fields, matches each invoice to its PO/PR lines, and tracks goods receipts and service
entries (GR/SES) until each case can be posted. It catches duplicate files, duplicate invoice numbers
and overbilling, and sends anything incomplete to a person for review.

Extraction and matching are **rule based** (PDF text plus OCR, label patterns, similarity scores).
There is no external AI service and no API key to manage.

**Live demo:** https://annie-acct439.streamlit.app

## Documentation

- [How Annie works: business logic](docs/BUSINESS_LOGIC.md): every rule, score and threshold, with
  worked examples from the sample data and the open review findings.
- [Technical architecture](docs/ARCHITECTURE.md): components, data model, concurrency, UI layer,
  configuration and deployment.

## Features

- **Intake:** upload or email (IMAP); PDF, PNG/JPG/TIFF/HEIC, DOCX, TXT, CSV and XLSX
- **Extraction:** PDF text with OCR fallback (RapidOCR or Tesseract), field and line-item extraction,
  signature check on PO/PRs
- **Checks:** duplicate file, duplicate content, mandatory fields, duplicate PO/PR reference and
  invoice number
- **Matching:** scored invoice-to-PO line allocation, partial billing, overbilling detection, manual
  matching with a required reason, Call-Offs for PO/PRs without an amount
- **Receipts and posting:** GR/SES batches, automatic completion, ZIP package per posted case
- **Audit log:** every intake and matching event

## Requirements

- **Python 3.11** (3.12 also works). Very new versions such as 3.14 may lack prebuilt wheels for
  `onnxruntime` and PyMuPDF.
- For scanned documents: RapidOCR (installed from `requirements.txt`) or a system Tesseract
  (`brew install tesseract`). Digital PDFs need neither.

## Quick start

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501 and loads the 21 sample documents from `samples/` on first
start. To reset it, set `ADMIN_PIN` in a `.env` file and use **Controls → Demo data**.

## Deployment

The live demo runs on **Streamlit Community Cloud** (free) from the `ui-polish` branch with Python
3.11; `packages.txt` installs Tesseract and the OCR system libraries.

- Community Cloud puts apps to sleep after 12 hours without traffic. The
  [Keep Streamlit app awake](.github/workflows/keep-awake.yml) GitHub Action opens the app in a
  headless browser every 4 hours ([scripts/keep_awake.py](scripts/keep_awake.py)), presses the
  wake-up button if needed, and fails (so GitHub emails you) if the app does not load. Update
  `APP_URL` in the workflow if the address changes.
- Community Cloud storage is not persistent: the database and uploaded files reset when the app
  restarts. For data that must persist, see [deploy/](deploy/) (self-hosted VM).

## Demo mode

- **Auto-load:** an empty database is filled with the sample documents when the app starts, so the
  demo never opens blank. Set `DEMO_AUTOLOAD=0` to turn this off.
- **Controls → Demo data → Reset & load demo data** restores the starting state before a
  presentation; **Danger zone → Reset database (empty)** clears everything for live uploads.
- Both need the **admin PIN**: `ADMIN_PIN = "..."` in the app's Settings → Secrets on Streamlit Cloud,
  or `ADMIN_PIN=...` in `.env` locally. Without a PIN they stay locked. Visitors can still browse,
  open cases and upload.

## Optional: email intake

Set these in `.env` (or as secrets) to turn on the inbox monitor:

```
EMAIL_HOST=imap.example.com
EMAIL_ADDRESS=ap@example.com
EMAIL_PASSWORD=...
EMAIL_PORT=993                # default
EMAIL_MAILBOX=INBOX           # default
EMAIL_SUBJECT_FILTER=         # optional: only subjects containing this text
EMAIL_LOOKBACK_DAYS=30        # default: how far back the first scan looks
POLL_SECONDS=60               # default: 15 to 3600
EMAIL_AUTO_FETCH=1            # 0 = do not start the monitor automatically
```

The mailbox is opened read-only and mail is never marked as read.

## Project layout

| Path | Purpose |
|------|---------|
| `app.py` | Streamlit UI |
| `annie_core.py` | Engine: extraction, classification, matching, storage, inbox monitor |
| `samples/` | 21 sample PO/PRs and invoices (the demo data) |
| `reference_samples/` | Optional reference documents and labels that tune classification |
| `docs/` | Business logic and architecture documentation |
| `scripts/`, `.github/workflows/` | Keep-awake check for the hosted demo |
| `deploy/` | Optional self-hosted VM setup |
| `annie_v4.db`, `storage/` | Created at runtime (git-ignored) |
