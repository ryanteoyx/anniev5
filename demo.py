"""Presenter-mode "Demo" slideshow for Annie, styled to match app.py (Inter, slate neutrals, one blue accent).

Integration (already in app.py):  demo.init_state() at start-up, a "Slides" button calling demo.start, and
    if ss.demo_active: demo.render(); st.stop()
placed before the sidebar is drawn, so presentation mode hides the normal navigation.

Presenter mode: full-width slides, a thin progress line, a small slide counter and one floating Previous / Next bar.
Keys: Right arrow or Page Down = next, Left arrow or Page Up = previous, F = full screen, Esc = leave the demo.
The last slide offers Restart and Close demo. There are no notes and no timer.

Slides use PNG screenshots from ./demo_screenshots (made by capture_live.py). A slide whose screenshot is missing
still shows its text, so the demo never breaks. To add or reorder slides, edit the SLIDES list - nothing else changes.
"""
from __future__ import annotations

import base64
import html
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

SHOTS = Path(__file__).parent / "demo_screenshots"
APP_NAME = "Annie"

# Every slide describes a real page/feature of app.py. "shot" = file in demo_screenshots/ (made by capture_live.py).
SLIDES = [
    dict(kind="intro"),
    dict(icon="🏠", label="Dashboard", shot="00_dashboard.png",
         title="Dashboard", tagline="Your starting point, with live counts of everything waiting for you.",
         points=["Six tiles: documents processed, needs review, open, call-offs, pending GR/SES and complete.",
                 "Select any tile to jump straight to that list.",
                 "The same counts appear as bubbles in the sidebar, so you always know where work is pending."]),
    dict(icon="📥", label="Submit Document", shot="01_submit.png",
         title="Submit Document", tagline="Two ways in: upload files or let Annie read the inbox.",
         points=["A. Upload PDFs, images, DOCX, TXT, CSV or XLSX in bulk, then run Module 1 and route.",
                 "B. Email inbox: Check inbox now, or automatic fetch every few seconds or minutes while the monitor is on.",
                 "Every document passes Module 1 first: duplicate check, text extraction, field check.",
                 "Results this session lists each file with its status and where it was routed."]),
    dict(icon="🕵️", label="Intake Review", shot="02_review_list.png",
         title="Intake Review", tagline="Documents Module 1 could not pass on, kept for a human decision.",
         points=["One line per document, with its Module 1 status, channel and arrival time.",
                 "Only documents with every mandatory field go on to matching; the rest wait here.",
                 "A filter, sort and counter sit above the list."]),
    dict(icon="🔎", label="Intake Review - case", shot="03_review_case.png",
         title="Inside an Intake Review case", tagline="See the original file next to exactly what is missing.",
         points=["Left: a preview of the original file as received.",
                 "Right: the list of missing mandatory fields, named in plain words.",
                 "Re-extract runs extraction again on the stored file; Dismiss removes the document so it can be resubmitted."]),
    dict(icon="🧮", label="Processing - Stage 1", shot="04_stage1.png",
         title="Stage 1: Open cases", tagline="Invoices still waiting for a PO/PR.",
         points=["Each waiting invoice shows the reason in plain English: PO/PR not received, no matching line, or balance too low.",
                 "Filter, sort and open any case with the Open button.",
                 "Matching is automatic: a new PO/PR retries every waiting invoice."]),
    dict(icon="📑", label="Stage 1 - PO/PRs", shot="05_stage1_po.png",
         title="PO/PRs with open balance", tagline="Scroll down to see what has been ordered, billed and received.",
         points=["Ordered, billed, received and open-to-bill for every PO/PR that is not fully billed.",
                 "Click a PO/PR reference to preview the document; download the table as CSV.",
                 "Services with no amount cited expect a single invoice."]),
    dict(icon="📂", label="Stage 1 - invoice case", shot="06_s1_case.png",
         title="Opening an invoice in Stage 1", tagline="The invoice, its source document and why it is still waiting.",
         points=["Source document: the invoice, with a field summary and a file preview.",
                 "A warning states why the invoice is not allocated yet.",
                 "Retry automatic allocation tries again after anything changes."]),
    dict(icon="⬇️", label="Stage 1 - invoice case", shot="07_s1_case_down.png",
         title="Manual options", tagline="Scroll down for the tools to resolve it by hand.",
         points=["Match manually: choose the PO/PR line for each invoice line, with a check before confirming.",
                 "A typed reason is required for a manual match.",
                 "Dismiss invoice deletes it and reverses any billing, so the file can be resubmitted."]),
    dict(icon="📦", label="Processing - Stage 2", shot="08_stage2.png",
         title="Stage 2: Pending GR/SES", tagline="Matched invoices waiting for goods or services to be confirmed received.",
         points=["Each invoice is already allocated to PO/PR lines.",
                 "Status and link score are shown for every case.",
                 "Open a case to record what was received."]),
    dict(icon="🔗", label="Stage 2 - case", shot="09_s2_case.png",
         title="Inside a Stage 2 case", tagline="The allocation, line by line.",
         points=["Allocation table: ordered, billed on this invoice, received, still to receive, matched automatically or manually.",
                 "Source documents: the invoice and each matched PO/PR."]),
    dict(icon="📝", label="Stage 2 - case", shot="10_s2_case_down.png",
         title="Recording a GR/SES", tagline="Scroll down to the receipt form.",
         points=["The GR/SES number is generated automatically; the preparer must match the PO/PR.",
                 "Enter what was received in this batch; partial deliveries are allowed.",
                 "Each batch is capped by what the invoice still needs and what the PO/PR has left to receive.",
                 "Unmatch sends the invoice back to Stage 1; Dismiss deletes it."]),
    dict(icon="✅", label="Processing - Stage 3", shot="11_stage3.png",
         title="Stage 3: Complete", tagline="Invoice, PO/PR and receipts agree.",
         points=["Receipts cover everything billed on each case.",
                 "Open a case to review it and post it."]),
    dict(icon="🔍", label="Stage 3 - case", shot="12_s3_case.png",
         title="Inside a complete case", tagline="Everything that was matched and received.",
         points=["Allocation and receipts show nothing left to receive.",
                 "Every GR/SES batch raised for this match is listed and can be expanded."]),
    dict(icon="📤", label="Stage 3 - case", shot="13_s3_case_down.png",
         title="Ready to post", tagline="Scroll down to the Post button.",
         points=["Post downloads the case folder as a ZIP: invoice, matched POs, each GR/SES, allocations and a summary.",
                 "It also moves the case to the Complete Archive."]),
    dict(icon="🚀", label="Post", shot="14_posted.png",
         title="Posting a case", tagline="One click archives the case.",
         points=["A confirmation states that the case was posted and moved to the Complete Archive.",
                 "The case leaves Stage 3 and the counters update."]),
    dict(icon="🗄️", label="Complete Archive", shot="15_archive.png",
         title="Complete Archive", tagline="Posted cases kept as history.",
         points=["Vendor, invoice, PO/PR, amount and posting date for every posted case.",
                 "Open a case to view it, or download its package again."]),
    dict(icon="📞", label="Processing - Call-Offs", shot="16_calloffs.png",
         title="Call-Offs", tagline="PO/PRs that cite no amount are matched by hand.",
         points=["Each call-off PO/PR opens its own case.",
                 "They are never matched automatically."]),
    dict(icon="🧾", label="Call-Off case", shot="17_calloff_case.png",
         title="Inside a Call-Off case", tagline="Pick the invoices that bill against the PO/PR.",
         points=["Select one or more open invoices, adding more with + Add Invoice.",
                 "A reason is required, and a warning appears if a vendor name looks different.",
                 "Confirm moves it to Pending GR/SES, then Complete."]),
    dict(icon="🗂️", label="Documents", shot="18_documents.png",
         title="Documents", tagline="One row per record, from arrival to outcome.",
         points=["How it arrived, what Module 1 decided and what Module 2 did with it.",
                 "Missing fields and the linked case ID are shown beside each record."]),
    dict(icon="📜", label="Audit Log", shot="19_audit.png",
         title="Audit Log", tagline="Every Module 1 and Module 2 event, newest first.",
         points=["Filter by stage, then sort and search.",
                 "The evidence trail: receipts, allocations, duplicates, manual matches and postings."]),
    dict(kind="end"),
]
N = len(SLIDES)
FLOW = ["Submit", "Module 1 checks", "Auto-match", "Receive (GR/SES)", "Post and archive"]

# Colours come from the app's own CSS variables (with the same values as fall-backs), so the demo always matches app.py.
CSS = """
<style>
[data-testid="stSidebar"], [data-testid="stExpandSidebarButton"], [data-testid="stHeader"] {display:none !important;}
.block-container, [data-testid="stMainBlockContainer"] {max-width:1320px; padding:1.2rem 2rem 6.5rem;}
.stApp {background:var(--canvas,#f8fafc);}
@keyframes demoIn {from {opacity:0; transform:translateY(10px);} to {opacity:1; transform:none;}}
.demo-in {animation: demoIn .45s cubic-bezier(.2,.7,.2,1) both;}

/* thin progress line + top bar */
.demo-line {position:fixed; top:0; left:0; right:0; height:3px; background:var(--line,#e2e8f0); z-index:1000003;}
.demo-line i {display:block; height:100%; background:var(--accent,#2563eb); transition:width .35s ease;}
.demo-top {display:flex; justify-content:space-between; align-items:center; margin-bottom:1.1rem;}
.demo-brand {font-size:1.35rem; font-weight:700; letter-spacing:-.02em; color:var(--ink,#0f172a);}
.demo-brand span {color:var(--accent,#2563eb);}
.demo-count {font-size:.82rem; font-weight:600; color:var(--muted,#64748b); background:var(--surface,#fff);
             border:1px solid var(--line,#e2e8f0); border-radius:999px; padding:.22rem .8rem; font-variant-numeric:tabular-nums;}

/* slide text */
.demo-kicker {font-size:.74rem; font-weight:700; letter-spacing:.09em; text-transform:uppercase; color:var(--accent,#2563eb); margin:.4rem 0 .5rem;}
.demo-title {font-size:2.35rem; line-height:1.12; font-weight:650; letter-spacing:-.03em; color:var(--ink,#0f172a); margin:0 0 .6rem;}
.demo-tag {font-size:1.1rem; line-height:1.5; color:var(--muted,#64748b); margin:0 0 1.4rem;}
.demo-list {list-style:none; margin:0; padding:0;}
.demo-list li {display:flex; gap:.8rem; align-items:flex-start; padding:.7rem 0; border-top:1px solid var(--line-soft,#f1f5f9);
               font-size:.98rem; line-height:1.5; color:var(--ink-2,#334155);}
.demo-list li:first-child {border-top:none;}
.demo-list li:before {content:""; flex:0 0 auto; width:.5rem; height:.5rem; margin-top:.5rem; border-radius:50%; background:var(--accent,#2563eb);}

/* screenshot frame */
.demo-frame {border:1px solid var(--line,#e2e8f0); border-radius:14px; overflow:hidden; background:var(--surface,#fff);
             box-shadow:0 18px 40px -18px rgba(15,23,42,.28), 0 2px 6px rgba(15,23,42,.05);}
.demo-frame .bar {display:flex; align-items:center; gap:.4rem; padding:.5rem .8rem; background:var(--line-soft,#f1f5f9);
                  border-bottom:1px solid var(--line,#e2e8f0);}
.demo-frame .dot {width:10px; height:10px; border-radius:50%; background:var(--line-strong,#cbd5e1);}
.demo-frame .name {margin-left:.7rem; font-size:.75rem; color:var(--muted,#64748b);}
.demo-frame img {display:block; width:100%; height:auto;}
.demo-missing {padding:3.5rem 1.5rem; text-align:center; color:var(--muted,#64748b);}
.demo-missing code {background:var(--line-soft,#f1f5f9); padding:.1rem .4rem; border-radius:4px;}

/* intro and final slides */
.demo-hero {text-align:center; padding:5.5vh 1rem 0;}
.demo-hero .mark {font-size:4.6rem; font-weight:700; letter-spacing:-.04em; color:var(--ink,#0f172a); line-height:1;}
.demo-hero .mark span {color:var(--accent,#2563eb);}
.demo-hero p {max-width:46rem; margin:1.1rem auto 0; font-size:1.2rem; line-height:1.55; color:var(--muted,#64748b);}
.demo-steps {display:flex; flex-wrap:wrap; justify-content:center; align-items:center; gap:.5rem; margin-top:2.4rem;}
.demo-steps .s {display:flex; align-items:center; gap:.5rem; background:var(--surface,#fff); border:1px solid var(--line,#e2e8f0);
                border-radius:999px; padding:.45rem .95rem .45rem .5rem; font-size:.9rem; font-weight:600; color:var(--ink-2,#334155);}
.demo-steps .n {display:inline-flex; width:1.5rem; height:1.5rem; border-radius:50%; align-items:center; justify-content:center;
                background:var(--accent-soft,#eff6ff); color:var(--accent-strong,#1d4ed8); font-size:.76rem;}
.demo-steps .a {color:var(--faint,#94a3b8);}
.demo-hint {margin-top:2.2rem; font-size:.85rem; color:var(--faint,#94a3b8);}
.demo-hint kbd {background:var(--surface,#fff); border:1px solid var(--line-strong,#cbd5e1); border-bottom-width:2px; border-radius:6px;
                padding:.05rem .45rem; font-size:.78rem; color:var(--ink-2,#334155); font-family:inherit;}
.demo-done .tick {width:4rem; height:4rem; margin:0 auto 1.2rem; border-radius:50%; background:var(--ok-soft,#f0fdf4); color:var(--ok,#15803d);
                  display:flex; align-items:center; justify-content:center; font-size:1.9rem; font-weight:700; border:1px solid #bbf7d0;}
.demo-done h1 {font-size:2.6rem; letter-spacing:-.03em; color:var(--ink,#0f172a); margin:0;}
.demo-recap {display:grid; grid-template-columns:repeat(3,1fr); gap:1rem; max-width:60rem; margin:2.2rem auto 0; text-align:left;}
.demo-recap div {background:var(--surface,#fff); border:1px solid var(--line,#e2e8f0); border-radius:12px; padding:1.1rem 1.2rem;
                 font-size:.93rem; line-height:1.5; color:var(--muted,#64748b);}
.demo-recap b {display:block; color:var(--ink,#0f172a); font-size:1rem; margin-bottom:.25rem;}

/* floating Previous / Next bar; hidden helper button for the Esc key */
.st-key-demo_nav {position:fixed; bottom:1.2rem; left:50%; transform:translateX(-50%); z-index:1000; width:min(23rem, calc(100vw - 2rem));
                  padding:.4rem; background:rgba(255,255,255,.92); backdrop-filter:blur(8px); border:1px solid var(--line,#e2e8f0);
                  border-radius:999px; box-shadow:0 10px 28px -8px rgba(15,23,42,.22);}
.st-key-demo_nav [data-testid="stHorizontalBlock"] {gap:.4rem;}
[data-testid="stMain"] .st-key-demo_nav button[kind] {height:2.5rem; border-radius:999px; font-weight:600;}
.st-key-demo_exit_hidden {position:absolute; left:-9999px; width:1px; height:1px; overflow:hidden;}
.st-key-demo_restart button, .st-key-demo_close button {height:2.8rem; font-size:1rem;}
@media (max-width: 760px) {
  .block-container, [data-testid="stMainBlockContainer"] {padding:1rem 1rem 6.5rem;}
  .demo-title {font-size:1.7rem;} .demo-hero .mark {font-size:3.2rem;} .demo-recap {grid-template-columns:1fr;}
}
</style>
"""

# Right/Left arrows (or Page Down/Up) = next/previous, F = full screen, Esc = leave the demo (clicks the hidden button).
KEYS_JS = """
<script>
(function () {
  try {
    const doc = window.parent.document;
    if (doc.__annieDemoKeys) doc.removeEventListener('keydown', doc.__annieDemoKeys);   // drop the handler of an older iframe
    const press = (k) => { const b = doc.querySelector('.st-key-' + k + ' button'); if (b && !b.disabled) b.click(); };
    doc.__annieDemoKeys = function (e) {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === 'ArrowRight' || e.key === 'PageDown') { e.preventDefault(); press('demo_next'); }
      else if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); press('demo_prev'); }
      else if (e.key === 'Escape') { press('demo_exit_hidden'); }
      else if (e.key === 'f' || e.key === 'F') {
        if (doc.fullscreenElement) doc.exitFullscreen();
        else if (doc.documentElement.requestFullscreen) doc.documentElement.requestFullscreen();
      }
    };
    doc.addEventListener('keydown', doc.__annieDemoKeys);
  } catch (err) {}
})();
</script>
"""


# ---- state -----------------------------------------------------------------------------------------------------
def init_state():
    """Create the demo's session keys once (all prefixed demo_ so they never clash with the app)."""
    ss = st.session_state
    ss.setdefault("demo_active", False)
    ss.setdefault("demo_step", 0)


def start():
    st.session_state.demo_active = True
    st.session_state.demo_step = 0


def _move(delta):
    ss = st.session_state
    ss.demo_step = max(0, min(N - 1, ss.demo_step + delta))


def restart():
    st.session_state.demo_step = 0


def exit_demo():
    st.session_state.demo_active = False
    st.session_state.demo_step = 0


# ---- building blocks -----------------------------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _data_uri(path: str, mtime: float) -> str:
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()


def _frame(slide) -> str:
    path = SHOTS / slide["shot"]
    if path.exists():
        img = f'<img src="{_data_uri(str(path), path.stat().st_mtime)}" alt="{html.escape(slide["title"])} screenshot">'
    else:
        img = (f'<div class="demo-missing"><p><b>Screenshot not captured yet</b></p>'
               f'<p>Run <code>python capture_live.py</code> to create <code>demo_screenshots/{html.escape(slide["shot"])}</code>.</p></div>')
    return (f'<div class="demo-frame"><div class="bar"><span class="dot"></span><span class="dot"></span><span class="dot"></span>'
            f'<span class="name">{APP_NAME} &middot; {html.escape(slide["label"])}</span></div>{img}</div>')


def _intro():
    steps = '<span class="a">&rsaquo;</span>'.join(
        f'<span class="s"><span class="n">{i}</span>{html.escape(s)}</span>' for i, s in enumerate(FLOW, 1))
    st.markdown(
        f'<div class="demo-hero demo-in"><div class="mark">{APP_NAME}<span>.</span></div>'
        f'<p>Accounts-payable three-way match, automated: Annie reads purchase orders and supplier invoices, checks them, links invoice lines '
        f'to PO/PR lines, records goods and service receipts, and archives each finished case with a full audit trail.</p>'
        f'<div class="demo-steps">{steps}</div>'
        f'<div class="demo-hint">Press <kbd>&rarr;</kbd> to begin &nbsp;&middot;&nbsp; <kbd>F</kbd> full screen &nbsp;&middot;&nbsp; <kbd>Esc</kbd> to leave</div></div>',
        unsafe_allow_html=True)


def _content(slide):
    left, right = st.columns([2, 3.4], gap="large", vertical_alignment="center")
    pts = "".join(f"<li>{html.escape(p)}</li>" for p in slide["points"])
    left.markdown(
        f'<div class="demo-in"><div class="demo-kicker">{html.escape(slide["label"])}</div>'
        f'<h2 class="demo-title">{html.escape(slide["title"])}</h2><p class="demo-tag">{html.escape(slide["tagline"])}</p>'
        f'<ul class="demo-list">{pts}</ul></div>', unsafe_allow_html=True)
    right.markdown(f'<div class="demo-in">{_frame(slide)}</div>', unsafe_allow_html=True)


def _end():
    st.markdown(
        f'<div class="demo-hero demo-done demo-in"><div class="tick">&#10003;</div><h1>That is the full workflow</h1>'
        f'<p>From a document arriving to a posted, auditable case.</p>'
        f'<div class="demo-recap"><div><b>Capture and check</b>Upload or email intake, duplicate checks, extraction and a mandatory-field gate.</div>'
        f'<div><b>Match and receive</b>Line-level matching to PO/PRs, many-to-many balances, GR/SES batches.</div>'
        f'<div><b>Post and audit</b>ZIP package, Complete Archive and a full event log.</div></div></div>', unsafe_allow_html=True)
    st.write("")
    _, a, b, _ = st.columns([2.2, 1, 1, 2.2])
    a.button("↺ Restart", key="demo_restart", on_click=restart, type="primary")
    b.button("Close demo", key="demo_close", on_click=exit_demo)


# ---- entry point -------------------------------------------------------------------------------------------------------
def render():
    """Draw the current slide. The caller should st.stop() afterwards."""
    ss = st.session_state
    step = max(0, min(N - 1, ss.demo_step))
    slide = SLIDES[step]
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(f'<div class="demo-line"><i style="width:{(step + 1) / N * 100:.1f}%"></i></div>'
                f'<div class="demo-top"><div class="demo-brand">{APP_NAME}<span>.</span></div>'
                f'<div class="demo-count">{step + 1} / {N}</div></div>', unsafe_allow_html=True)

    kind = slide.get("kind")
    if kind == "intro":
        _intro()
    elif kind == "end":
        _end()
    else:
        _content(slide)

    with st.container(key="demo_nav"):
        prev_c, next_c = st.columns(2)
        prev_c.button("← Previous", key="demo_prev", on_click=_move, args=(-1,), disabled=step == 0)
        next_c.button("Next →", key="demo_next", on_click=_move, args=(1,), disabled=step == N - 1, type="primary")
    st.button("Leave demo", key="demo_exit_hidden", on_click=exit_demo)   # kept off-screen; the Esc key presses it
    components.html(KEYS_JS, height=0)
