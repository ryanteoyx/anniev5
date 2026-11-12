# Annie: User Manual

Annie is an accounts-payable (AP) tool for **three-way matching**. It reads purchase orders or purchase requisitions
(PO/PRs) and supplier invoices, checks them, matches each invoice to its PO/PR lines, and tracks goods receipts and
service entries (GR/SES) until the case is complete and can be archived.

- **Live version (no install needed):** https://anniev5-production.up.railway.app
- **Source code:** https://github.com/ryanteoyx/anniev5 (branch `ui-polish`)

---

## 1. What is in the package

| Path | What it is |
|---|---|
| `app.py` | The web interface (Streamlit) |
| `annie_core.py` | The engine: reading documents, checks, matching, storage, email intake |
| `tour.py` | The **▶ Play demo** guided tour |
| `demo.py`, `demo_screenshots/` | The **Slides** slideshow |
| `samples/` | 28 sample PO/PRs and invoices; loaded automatically on first start |
| `requirements.txt` | The Python packages Annie needs, with tested versions |
| `.env.example` | Optional settings (admin PIN, email inbox); copy to `.env` to use |
| `docs/BUSINESS_LOGIC.md` | Every rule, score and threshold, with worked examples |
| `docs/ARCHITECTURE.md` | Components, data model and deployment |
| `tests/` | Automated tests |
| `Dockerfile` | Container build (used for the live version) |
| `deploy/` | Optional setup for a self-hosted server |

Annie creates `annie_v4.db` (the database) and `storage/` (uploaded files) when it runs. Both can be deleted to start
fresh.

---

## 2. Requirements

| | |
|---|---|
| **Python** | **3.11** (3.12 also works). Avoid very new versions such as 3.14: some packages have no ready-made install files for them yet. |
| **Disk space** | About 1.5 GB for the Python packages (the OCR engine is the largest part) |
| **Internet** | Needed once, to install the packages |
| **Operating system** | macOS, Windows or Linux |
| **Browser** | Any modern browser (Chrome, Edge, Safari, Firefox) |
| **Optional** | Tesseract OCR as a second OCR engine (`brew install tesseract` on macOS). Not required: RapidOCR is installed with the packages. |

The Python packages (from `requirements.txt`):

| Package | Used for |
|---|---|
| streamlit | Web interface |
| pandas, numpy, openpyxl | Tables, CSV and Excel files |
| pdfplumber, PyMuPDF | Reading PDFs; rendering pages for OCR and the signature check |
| python-docx | Word files |
| Pillow, pillow-heif | Images, including iPhone HEIC photos |
| rapidocr, onnxruntime | OCR for scanned documents |
| pytesseract | Optional second OCR engine (needs Tesseract installed) |
| python-dotenv | Reading settings from `.env` |

---

## 3. Install

Unzip the package, open a terminal in the unzipped `anniev5` folder, then:

**macOS / Linux**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows (Command Prompt or PowerShell)**

```bat
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

The install takes a few minutes. Check it worked:

```bash
python tests/test_findings.py
```

It should end with `11 passed, 0 failed`.

---

## 4. Start and stop Annie

With the environment active (step 3):

```bash
streamlit run app.py
```

Annie opens in your browser at **http://localhost:8501**. On the first start it loads the 28 sample documents, so
the screens are not empty.

To stop Annie, press **Ctrl + C** in the terminal. Next time, activate the environment again
(`source .venv/bin/activate`, or `.venv\Scripts\activate` on Windows) and run `streamlit run app.py`.

**Docker instead of Python** (if Docker is installed):

```bash
docker build -t annie .
docker run -p 8501:8501 annie
```

---

## 5. How a document moves through Annie

```
Upload or email
      |
      v
Module 1: Intake ---- missing fields, unreadable, duplicate ----> Intake Review (a person decides)
      |
      v
Module 2: Match
  Stage 1  Open cases       invoice waiting for its PO/PR, or held by a check
  Call-Offs                 PO/PR with no amount: matched by hand
  Stage 2  Pending GR/SES   matched; waiting for what was received
  Stage 3  Complete         receipts cover the invoice; ready to post
      |
      v
Complete Archive (ZIP package per case)
```

---

## 6. Using each page

The pages are in the left sidebar, in the order of the AP flow.

### Dashboard
Counts for every stage. Click a tile to jump to that list.

### Submit Document
- **Upload documents:** choose PDF, image, DOCX, TXT, CSV or XLSX files (up to 20 MB each) and click
  **Process documents**.
- **Email inbox:** if an inbox is set up (section 8), **Check inbox now** fetches new attachments. Annie also checks it
  automatically.
- **Results this session** shows what happened to each file: registered, matched, waiting, sent to Intake Review, or
  rejected as a duplicate.

### Intake Review
Documents Module 1 could not pass on: missing mandatory fields (for example, no invoice number or date), unreadable,
or not a PO/PR or invoice. The original file is shown next to the list of what is missing.
- **Re-extract from file:** read the file again (after a fix to the file or the settings).
- **Dismiss:** remove the document completely. It can be submitted again later.

### Processing
Four tabs.

**Stage 1 - Open cases.** Invoices that could not be matched automatically, each with the reason (for example, "PO/PR
not yet received", "unit price 7.50 is 200% above the PO/PR price"). Below them, every PO/PR that still has a balance,
with ordered, billed and received amounts (**Download CSV** exports this list). Click **Open** on an invoice to:
- see the invoice and its PO/PR side by side;
- **Retry automatic allocation**;
- **Match manually:** choose a PO/PR line for each invoice line (one line can be split over several PO/PR lines),
  type a reason, and confirm. The reason goes into the audit log;
- **Dismiss invoice (delete):** tick the confirmation box. Any billing on the PO/PR is reversed and the file can be
  uploaded again later.

A waiting invoice is retried automatically whenever a new PO/PR arrives.

**Call-Offs.** PO/PRs with no amount (for example, "pest control as required"). Pick the invoices that belong to the
call-off, type a reason and click **Confirm**.

**Stage 2 - Pending GR/SES.** Matched invoices waiting for proof of delivery or service. Open a case to see how each
invoice line was allocated, then fill in the GR/SES form (what was actually received in this batch) and click
**Submit GR/SES**. Partial deliveries are fine; the case completes when receipts cover the invoice.
**Unmatch (send back to Stage 1)** undoes the match, with a reason.

**Stage 3 - Complete.** Fully received cases. Open one and click **Post** to archive it. Post downloads a ZIP with the
documents and a summary. It does **not** post anything to an accounting system.

### Complete Archive
Posted cases. **Open** to view one, **Package** to download its ZIP again.

### Documents
One row per document: how it arrived, what Module 1 decided, and what Module 2 did with it. Filter and sort with the
controls above the table.

### Audit Log
Every event: received, rejected, matched, manually matched (with the reason), GR/SES submitted, posted.

### Controls
- **Demo data → Reset & load demo data:** back to the starting sample set. Needs the admin PIN.
- **Inbox monitor:** status of automatic email fetching.
- **Module 1 status:** OCR engine, reference samples, email settings, and the matching thresholds.
- **Danger zone → Reset database (empty):** removes everything, for example before uploading live during a demo.
  Needs the admin PIN.

---

## 7. Demo mode

- **▶ Play demo** (top right): a guided tour of 23 stops. A cursor clicks through the pages and zooms in on each
  feature. **Next** or **Space** moves on, **←** goes back, **F** is full screen, **Esc** leaves. It uses its own copy
  of the demo data, so it changes nothing. Keep the browser zoom at 100%.
- **Slides:** the same features as a slideshow of screenshots.

---

## 8. Settings (optional)

Copy `.env.example` to `.env` in the same folder and fill in what you need, then restart Annie.

| Setting | What it does |
|---|---|
| `ADMIN_PIN` | Unlocks the two reset buttons on Controls. Without it they stay locked. |
| `DEMO_AUTOLOAD` | `1` = load the samples into an empty database (default); `reset` = reload them on every start; `0` = never |
| `EMAIL_HOST`, `EMAIL_ADDRESS`, `EMAIL_PASSWORD` | Turn on email intake (IMAP). The mailbox is read-only: mail is never marked as read or deleted. Use an app password, not your normal password. |
| `EMAIL_PORT`, `EMAIL_MAILBOX`, `EMAIL_SUBJECT_FILTER`, `EMAIL_LOOKBACK_DAYS`, `POLL_SECONDS`, `EMAIL_AUTO_FETCH` | Fine-tuning for email intake (defaults: 993, INBOX, none, 30 days, 60 seconds, on) |

Never put `.env` in a shared folder or on GitHub: it can contain passwords.

---

## 9. Matching rules in brief

An invoice line is matched **automatically** only when all of these hold (details in `docs/BUSINESS_LOGIC.md`):

| Check | Rule |
|---|---|
| Vendor | Names at least **90%** alike, ignoring endings such as Pte Ltd, Sdn Bhd, LLC |
| Currency | Same currency (an unstated currency does not block) |
| Line score | At least **0.80** (60% description, 40% unit price; +0.25 when the invoice cites the PO/PR) |
| Price (goods) | Unit price at most **5%** above the PO/PR price |
| Line total (goods) | At most quantity × unit price + 0.5% (+0.05 for rounding) |
| Item (goods) | Description at least **0.40** similar to the PO/PR item |
| Balance | Enough quantity or amount left on the PO/PR line |
| Whole invoice | Every line must fit; otherwise the invoice waits in Stage 1 with the reason |

Anything that fails waits for a person, who can match it manually with a typed reason.

---

## 10. Run the tests

```bash
python tests/test_findings.py      # matching and intake rules (11 tests)
python tests/test_tour.py          # the Play demo data (2 tests)
python tests/sample_regression.py  # the 28 sample documents give the expected 17 cases
```

---

## 11. Troubleshooting

| Problem | Fix |
|---|---|
| `pip install` fails on `onnxruntime` or `PyMuPDF` | Use Python 3.11 or 3.12 (step 2). Check with `python --version`. |
| `No space left on device` during install | Free about 1.5 GB of disk space and run `pip install -r requirements.txt` again. |
| `streamlit: command not found` | The environment is not active: run `source .venv/bin/activate` (Windows: `.venv\Scripts\activate`). |
| Port 8501 already in use | `streamlit run app.py --server.port 8502`, then open http://localhost:8502 |
| Scanned documents come out empty | The first scan downloads the OCR models (needs internet once). Clear, upright scans work best. |
| Want to start again | Stop Annie, delete `annie_v4.db` and the `storage/` folder, start again. |
| Reset buttons are greyed out | Set `ADMIN_PIN` in `.env` (section 8) and restart. |
| The Play demo looks cut off | Set the browser zoom to 100% (Cmd/Ctrl + 0). |

---

## 12. Limitations

- Tested on synthetic sample documents only, not on real company data.
- **Post** archives a case as a ZIP; nothing is sent to Xero or any other accounting system.
- One company, one currency per match, no user logins or roles.
- The signature check on PO/PR forms looks for ink in the signature area; it is not proof of approval.
- Duplicate checks catch the same file, the same content and repeated reference numbers; a duplicate charge with a new
  invoice number and different wording needs a person.
- Thresholds are prototype settings and should be tuned on real data.
