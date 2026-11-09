"""Guided "Play demo" tour for Annie: walks the real app like a stakeholder would.

Pressing Play opens the live pages, not screenshots. A fake cursor moves to each control and clicks it, the view zooms
in on one feature and stops so the presenter can talk, then Next zooms out and moves on. The stops and captions
follow the team's voice-over script ("demo script" tab of the project Google Doc): one invoice, arrival to archive.

The tour runs on its own private copy of the demo data (see prepare), because the main database is shared by every
visitor. That copy also has one Complete case and one posted case, which the normal demo data does not. The tour only
navigates: it never submits a form or presses Post.

Integration (already in app.py): con uses tour.db_path() while ss.tour_on, tour.init_state() at start-up, and
    tour.render() when ss.tour_on, else a Play button calling tour.start
To add or reorder stops, edit steps(). Keys: Space or Right = next, Left = back, F = full screen, Esc = leave.
"""
from __future__ import annotations

import json
import re
import tempfile
from datetime import date
from pathlib import Path

import streamlit as st

import annie_core as annie

SAMPLES = Path(__file__).parent / "samples"


def _key(name: str) -> str:
    """CSS selector for a Streamlit element key (Streamlit turns other characters into '-' in the class name)."""
    return ".st-key-" + re.sub(r"[^\w-]", "-", name)


def _btn(name: str) -> str:
    return _key(name) + " button"


def _stop(section, title, text, path, focus, zoom=2.2, sweep=False):
    """One pause: `path` is the clicks that reach the page from anywhere, `focus` is the element to zoom in on, and
    `zoom` caps the scale (tables are drawn as images, so they blur if enlarged too far). `sweep` pans a table that is
    wider than the screen slowly to its last column, so every column is seen."""
    return dict(section=section, title=title, text=text, path=path, focus=focus, zoom=zoom, sweep=sweep)


def steps(c: dict) -> list[dict]:
    """The script, in the order a stakeholder would follow one invoice. c = the case IDs chosen in _seed."""
    home, submit, review = [_btn("side_dashboard")], [_btn("side_submit")], [_btn("side_review")]
    process = _btn("side_processing")
    s1, calloff, s2, s3 = (([process, _btn(f"ptab_{t}")]) for t in ("s1", "calloff", "s2", "s3"))
    expander = '[data-testid="stExpander"] summary'
    s1_case, calloff_case = s1 + [_btn(f"s1a_{c['open']}")], calloff + [_btn(f"co_open_{c['calloff']}")]
    s2_case, s3_case = s2 + [_btn(f"s2_{c['pending']}")], s3 + [_btn(f"s3_{c['complete']}")]
    review_case, s1_manual = review + [expander], s1_case + [expander]
    dismiss = f'[data-testid="stExpander"]:has({_key("dis_ok_" + c["open"])})'
    table = '[data-testid="stDataFrame"]'
    right = '.st-key-detail_cols [data-testid="stColumn"]:nth-child(2)'
    return [
        _stop("Dashboard", "Everything at a glance", "Six tiles: documents processed, needs review, open, call-offs, pending GR/SES and complete. Select any tile to jump straight to that list.",
              home, _key("tiles")),
        _stop("Dashboard", "Work waiting, always visible", "The number of documents waiting in each stage appears in the sidebar, so you always know where work is pending.",
              home, _key("side_processing")),
        _stop("Submit Document", "Documents come in here", "To start the workflow, upload files under Upload documents: PDFs, images, Word, text or spreadsheets, in bulk.", submit, _key("card_upload")),
        _stop("Submit Document", "Or straight from the inbox", "Or connect a mailbox and let Annie read it on a schedule. It is not connected on this demo site.", submit, _key("card_email")),
        _stop("Submit Document", "Every file gets a result", "Each file is listed with its status and where it was routed. Every document passes Module 1 first: duplicate check, text extraction and field check.", submit, _key("results_top"), zoom=1.5),
        _stop("Intake Review", "Nothing incomplete slips through", "Only documents with every mandatory field go on to matching. The rest are routed here for review.",
              review, '[data-testid="stExpander"]'),
        _stop("Intake Review", "See exactly what is missing", "The original file sits next to exactly what is missing. This invoice has no date and no invoice reference.", review_case, '[data-testid="stExpanderDetails"] [data-testid="stColumn"]:nth-child(2)'),
        _stop("Stage 1: Open cases", "Why an invoice is waiting", "Each pending invoice explains its status. This one is held because its unit price is far above the PO/PR price. A new PO/PR retries every waiting invoice.",
              s1, f'{_key("tbl_s1a")} [data-testid="stHorizontalBlock"]:has({_key("s1a_" + c["held"])})'),
        _stop("Stage 1: Open cases", "Balances on every PO/PR", "Ordered, billed and received for every PO/PR that is not fully billed yet.",
              s1, _key("tbl_s1b")),
        _stop("Stage 1: Open cases", "Overbilling is caught", "Open an invoice to see why it is waiting. This one bills more than the PO/PR has left, so it cannot be allocated.",
              s1_case, f'{right} [data-testid="stAlert"]'),
        _stop("Stage 1: Open cases", "A person can resolve it", "Match manually: choose a PO/PR line for each invoice line. A reason is required, and it goes into the audit log.",
              s1_manual, '[data-testid="stForm"]', zoom=1.5),
        _stop("Stage 1: Open cases", "Or dismiss it", "Dismiss invoice deletes the document and reverses any billing, so the file can be resubmitted.", s1_manual + [f"{dismiss} summary"], dismiss, zoom=1.6),
        _stop("Call-Offs", "PO/PRs with no amount", "A PO/PR with no amount is never matched automatically. It is routed to Call-Offs.",
              calloff, _key("tbl_calloffs")),
        _stop("Call-Offs", "Pick the invoices", "Choose the open invoices that bill against this PO/PR and give a reason. Annie warns if a vendor name looks different.",
              calloff_case, _key(f"co_sel_{c['calloff']}")),
        _stop("Stage 2: Pending GR/SES", "Matched, waiting for receipt", "Matched invoices waiting for goods or services to be received, with the status and link score of every case.",
              s2, _key("tbl_s2")),
        _stop("Stage 2: Pending GR/SES", "Line-by-line allocation", "Open a case to record what was received. One invoice can bill several PO/PRs; this table shows ordered, billed and received for each line.",
              s2_case, f"{right} {table}", zoom=1.6),
        _stop("Stage 2: Pending GR/SES", "Record what was received", "The GR/SES number is generated. Enter what arrived in each batch: partial deliveries are allowed, capped by what the invoice still needs and the PO/PR has left.",
              s2_case, '[data-testid="stForm"]'),
        _stop("Stage 3: Complete", "Three-way match complete", "The three-way match is done, and these cases are ready to post.",
              s3, _key("tbl_s3")),
        _stop("Stage 3: Complete", "Everything in one place", "Open a case to review it: the allocation and receipts show nothing is left to receive.",
              s3_case, f"{right} {table}", zoom=1.6),
        _stop("Stage 3: Complete", "One click to post", "Post downloads the case folder as a ZIP. The case leaves Stage 3 and is archived.",
              s3_case, _key(f"post_{c['complete']}"), zoom=1.6),
        _stop("Complete Archive", "Posted cases stay on record", "Open an archived case to view it, or download its package again.",
              [_btn("side_archive")], _key("tbl_archive")),
        _stop("Documents", "One row per record", "Every document: how it arrived, what Module 1 decided, what Module 2 did with it, any missing fields and the linked case.",
              [_btn("side_docs")], table, sweep=True),
        _stop("Audit Log", "The evidence trail", "The evidence trail of every event that happened, newest first.",
              [_btn("side_audit")], table, sweep=True),
    ]


def _seed(con, results: list | None = None) -> dict:
    """Load the sample documents and move two cases forward, using the normal engine calls. Returns the featured cases;
    the per-file intake results are added to `results` (shown under "Results this session" while the tour runs)."""
    for p in sorted(SAMPLES.glob("*.pdf")):
        out = annie.ingest_file(con, p.name, p.read_bytes(), channel="UPLOAD")
        if results is not None:
            results += out
    case = {r["invoice_reference"]: r["case_id"] for r in annie.case_rows(con, [annie.S_OPEN_PO, annie.S_GR])}
    chosen = dict(open=case["LS-0457"], held=case["ATS-INV-4101"], pending=case["ZH/26/1230"], complete=case["AOS-INV-31001"],
                  calloff=next(r["case_id"] for r in annie.calloff_rows(con, [annie.S_CALLOFF]) if "GreenGrocer" in r["vendor"]))
    today = date.today().isoformat()
    for case_id in (chosen["complete"], case["BE-2026-014"]):
        annie.submit_gr(con, case_id, dict(service_date_from=today, service_date_to=today,
                                           prepared_by=annie.allowed_preparers(con, case_id)[0],
                                           lines=[dict(line_id=l["line_id"], receive=l["needed"]) for l in annie.case_lines(con, case_id)]))
    annie.post_case(con, case["BE-2026-014"])
    return chosen


@st.cache_resource(show_spinner="Preparing the demo...")
def prepare():
    """The tour's private database and script, built once per app start. Returns (database path, steps, intake results)."""
    path = Path(tempfile.mkdtemp(prefix="annie-tour-")) / "tour.db"
    con = annie.connect(path)
    results = []
    chosen = _seed(con, results)
    con.close()
    return path, steps(chosen), results


def db_path():
    return prepare()[0]


def results():
    """What the Submit page lists under "Results this session" during the tour: how each sample was routed on intake."""
    return prepare()[2]


# ---- state -----------------------------------------------------------------------------------------------------
def init_state():
    """Create the tour's session keys once."""
    ss = st.session_state
    ss.setdefault("tour_on", False)
    ss.setdefault("tour_run", 0)


def _home():
    ss = st.session_state
    ss.side, ss.ptab, ss.view_case, ss.view_po = "dashboard", "s1", None, None


def start():
    st.session_state.tour_on = True
    st.session_state.tour_run += 1
    _home()


def stop():
    st.session_state.tour_on = False
    _home()


# ---- the browser side ------------------------------------------------------------------------------------------
CSS = """
<style>
/* the "camera": the whole app moves and scales, so zooming works on any element */
html.annie-tour, html.annie-tour body {overflow:hidden;}
html.annie-tour .stApp {transform-origin:0 0; transition:transform .85s cubic-bezier(.65,0,.25,1);
                        transform:translate(var(--tour-x,0px),var(--tour-y,0px)) scale(var(--tour-s,1));}
html.annie-tour [data-testid="stStatusWidget"], html.annie-tour [data-testid="stHeader"] {display:none !important;}
.st-key-tour_hidden {position:absolute; left:-9999px; width:1px; height:1px; overflow:hidden;}
/* the tables must fit on a laptop screen without zooming the browser out: narrower page margins, and the case pages put
   the allocation and GR/SES panel full width above the source documents instead of in a half-width column */
html.annie-tour [data-testid="stMainBlockContainer"] {padding-left:1.5rem !important; padding-right:1.5rem !important;}
html.annie-tour [data-testid="stSidebar"] {width:244px !important; min-width:244px !important; max-width:244px !important;}
html.annie-tour [class*="st-key-tbl_"] [data-testid="stHorizontalBlock"] {min-width:900px !important;}   /* list rows fit the screen */
html.annie-tour [data-testid="stMain"] [class*="st-key-tbl_"] button[kind] {padding:.2rem .6rem;}   /* so Open and Package keep their words */
html.annie-tour .st-key-detail_cols > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {flex-wrap:wrap !important;}
html.annie-tour .st-key-detail_cols > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]
    {flex:1 1 100% !important; min-width:100% !important;}
html.annie-tour .st-key-detail_cols > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2) {order:-1;}

#tour-shield {position:fixed; inset:0; z-index:1000010; cursor:none;}   /* the presenter drives with the panel, not the page */
#tour-ring {position:fixed; z-index:1000011; border-radius:12px; pointer-events:none; opacity:0; transition:opacity .35s ease;
            outline:2px solid var(--accent,#2563eb); outline-offset:0; box-shadow:0 0 0 200vmax rgba(15,23,42,.34);}
#tour-ring.on {opacity:1;}
#tour-cursor {position:fixed; left:0; top:0; z-index:1000012; width:26px; height:26px; pointer-events:none; opacity:0;
              transition:transform .75s cubic-bezier(.65,0,.25,1), opacity .25s ease; filter:drop-shadow(0 2px 3px rgba(15,23,42,.35));}
#tour-cursor.on {opacity:1;}
#tour-cursor.fast {transition:transform .2s ease, opacity .25s ease;}
#tour-cursor i {position:absolute; left:-13px; top:-13px; width:26px; height:26px; border-radius:50%; opacity:0;
                background:var(--accent,#2563eb);}
#tour-cursor.click i {animation:tourClick .45s ease-out;}
@keyframes tourClick {from {opacity:.45; transform:scale(.3);} to {opacity:0; transform:scale(1.7);}}

#tour-line {position:fixed; top:0; left:0; right:0; height:3px; z-index:1000013; background:var(--line,#e2e8f0);}
#tour-line i {display:block; height:100%; width:0; background:var(--accent,#2563eb); transition:width .35s ease;}
#tour-panel {position:fixed; left:50%; bottom:1.1rem; z-index:1000013; width:min(54rem, calc(100vw - 2rem)); transform:translateX(-50%);
             display:flex; align-items:center; gap:1.4rem; padding:.95rem 1rem .95rem 1.3rem; font-family:Inter,system-ui,sans-serif;
             background:rgba(255,255,255,.97); border:1px solid var(--line,#e2e8f0); border-radius:14px;
             box-shadow:0 18px 40px -14px rgba(15,23,42,.38); transition:opacity .25s ease;}
#tour-panel .txt {flex:1 1 auto; min-width:0; min-height:4.4rem; transition:opacity .25s ease;}
#tour-panel.moving .txt {opacity:.35;}
#tour-panel .kick {font-size:.7rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:var(--accent,#2563eb);}
#tour-panel .ttl {font-size:1.08rem; font-weight:650; letter-spacing:-.01em; color:var(--ink,#0f172a); margin:.1rem 0 .15rem;}
#tour-panel .say {font-size:.9rem; line-height:1.45; color:var(--ink-2,#334155);}
#tour-panel .ctl {flex:0 0 auto; display:flex; align-items:center; gap:.4rem;}
#tour-panel .num {font-size:.78rem; font-weight:600; color:var(--muted,#64748b); font-variant-numeric:tabular-nums; margin-right:.3rem; white-space:nowrap;}
#tour-panel button {height:2.4rem; padding:0 .9rem; border-radius:8px; font:600 .86rem Inter,system-ui,sans-serif; white-space:nowrap; cursor:pointer;
                    color:var(--ink-2,#334155); background:var(--surface,#fff); border:1px solid var(--line-strong,#cbd5e1);}
#tour-panel button:hover:not(:disabled) {background:var(--line-soft,#f1f5f9);}
#tour-panel button.go {color:#fff; background:var(--accent,#2563eb); border-color:var(--accent,#2563eb);}
#tour-panel button.go:hover:not(:disabled) {background:var(--accent-strong,#1d4ed8);}
#tour-panel button:disabled {opacity:.45; cursor:default;}
</style>
"""

ENGINE = """
(function () {
  const data = __DATA__;
  if (document.__annieTourRun === data.run) return;   // a page rerun must not restart a tour already under way
  document.__annieTourRun = data.run;
  const steps = data.steps, root = document.documentElement;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const add = (id, html) => { const e = document.createElement('div'); e.id = id; e.innerHTML = html || ''; document.body.appendChild(e); return e; };

  root.classList.add('annie-tour');
  const shield = add('tour-shield'), ring = add('tour-ring');
  const cursor = add('tour-cursor', '<i></i><svg viewBox="0 0 24 24" width="26" height="26"><path d="M4 2l15.5 11.2-7 .9-3.6 6.4z" fill="#0f172a" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>');
  const line = add('tour-line', '<i></i>');
  const panel = add('tour-panel', '<div class="txt"><div class="kick"></div><div class="ttl"></div><div class="say"></div></div>' +
    '<div class="ctl"><span class="num"></span><button class="back">&larr; Back</button><button class="go"></button><button class="exit">Exit</button></div>');
  const [kick, ttl, say] = ['.kick', '.ttl', '.say'].map((s) => panel.querySelector(s));
  const num = panel.querySelector('.num'), back = panel.querySelector('.back'), go = panel.querySelector('.go'), exit = panel.querySelector('.exit');

  let at = -1, path = [], busy = false, cx = innerWidth / 2, cy = innerHeight / 2, done = false, focused = null, gone = false;

  const scriptIdle = () => !document.querySelector('[data-test-script-state="running"]');
  const visible = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.left > -5000; };
  const find = (sel) => [...document.querySelectorAll(sel)].find(visible);

  async function waitFor(sel, ms) {   // the element exists and Streamlit has finished drawing the page
    const end = Date.now() + (ms || 12000);
    await sleep(160);
    while (Date.now() < end) {
      const e = find(sel);
      if (e && scriptIdle()) { await sleep(180); const again = find(sel); if (again && scriptIdle()) return again; }
      await sleep(90);
    }
    return null;
  }

  function moveCursor(x, y, fast) {
    cx = x; cy = y;
    cursor.classList.toggle('fast', !!fast);
    cursor.style.transform = `translate(${x}px, ${y}px)`;
    return sleep(fast ? 220 : 780);
  }

  function setCamera(x, y, s) {
    root.style.setProperty('--tour-x', x + 'px'); root.style.setProperty('--tour-y', y + 'px'); root.style.setProperty('--tour-s', s);
  }

  async function zoomOut() {
    ring.classList.remove('on');
    if (getComputedStyle(root).getPropertyValue('--tour-s').trim() !== '1') { setCamera(0, 0, 1); await sleep(880); }
  }

  async function reveal(e) {   // scroll the page (never the outer layout) so the element is in the middle of the free space
    const main = document.querySelector('[data-testid="stMain"]');
    if (!main || !main.contains(e)) return;
    const r = e.getBoundingClientRect(), m = main.getBoundingClientRect(), free = m.height - panel.offsetHeight - 40;
    const top = main.scrollTop + r.top - m.top - Math.max(16, (free - r.height) / 2);
    if (Math.abs(top - main.scrollTop) < 8) return;
    main.scrollTo({top, behavior: 'smooth'});
    // a long scroll takes longer than a short one: wait until it has stopped, or the zoom frames the wrong spot
    let last = -1, still = 0;
    for (const end = Date.now() + 2000; Date.now() < end && still < 3; ) {
      await sleep(80);
      still = Math.abs(main.scrollTop - last) < 1 ? still + 1 : 0;
      last = main.scrollTop;
    }
  }

  async function settle(e) {   // wait until the element stops moving (Streamlit draws long pages in several passes)
    let last = '', still = 0;
    for (const end = Date.now() + 3000; Date.now() < end && still < 4 && e.isConnected; ) {
      await sleep(100);
      const r = e.getBoundingClientRect(), k = [r.top, r.left, r.height].map(Math.round).join();
      still = k === last ? still + 1 : 0;
      last = k;
    }
  }

  async function clickOn(sel, shown) {
    const e = !gone && await waitFor(sel);
    if (!e || gone) return;
    await reveal(e);
    const r = e.getBoundingClientRect();
    await moveCursor(r.left + Math.min(r.width / 2, 70), r.top + r.height / 2, !shown);
    if (shown) { cursor.classList.remove('click'); void cursor.offsetWidth; cursor.classList.add('click'); await sleep(260); }
    if (!gone) e.click();   // Exit may have been pressed on the way here
  }

  async function zoomIn(e, most) {
    const r = e.getBoundingClientRect(), W = innerWidth, H = innerHeight - panel.offsetHeight - 34;
    const s = Math.max(1, Math.min(most, .86 * W / r.width, .84 * H / r.height));
    const x = Math.min(0, Math.max(W - s * W, W / 2 - s * (r.left + r.width / 2)));
    // an element at the very end of a page may lift the app a little, so it is never hidden behind the panel;
    // one taller than the free space is shown from its top
    const y = Math.min(0, s * r.height > H ? 14 - s * r.top : H / 2 - s * (r.top + r.height / 2));
    setCamera(x, y, s);
    const left = x + s * r.left, top = y + s * r.top, w = s * r.width, h = s * r.height, pad = 8;
    Object.assign(ring.style, {left: left - pad + 'px', top: top - pad + 'px', width: w + 2 * pad + 'px', height: h + 2 * pad + 'px'});
    const small = w < 320 && h < 120;   // rest on a small control; stay out of the way on a large one
    cursor.classList.remove('fast');
    cursor.style.transition = 'transform .85s cubic-bezier(.65,0,.25,1), opacity .25s ease';
    cursor.style.transform = `translate(${cx = left + (small ? w / 2 : w - 18)}px, ${cy = top + (small ? h / 2 : h - 18)}px)`;
    await sleep(900);
    // the page can still settle while the camera moves (rows above re-measure): frame what is really there now,
    // again and again until it stops moving (a long list can take a few passes)
    let now = e.getBoundingClientRect(), camX = x, camY = y, moved = false;
    for (let k = 0; k < 5 && e.isConnected && !gone; k++) {
      now = e.getBoundingClientRect();
      if (Math.abs(now.top - top) <= 6 && Math.abs(now.left - left) <= 6) break;
      camX += left - now.left; camY = Math.min(0, camY + top - now.top); moved = true;
      setCamera(camX, camY, s);
      await sleep(560);
    }
    now = e.getBoundingClientRect();
    if (moved) cursor.style.transform = `translate(${cx = now.left + (small ? now.width / 2 : now.width - 18)}px, ${cy = now.top + (small ? now.height / 2 : now.height - 18)}px)`;
    Object.assign(ring.style, {left: now.left - pad + 'px', top: now.top - pad + 'px', width: now.width + 2 * pad + 'px', height: now.height + 2 * pad + 'px'});
    cursor.style.transition = '';
    ring.classList.add('on');
  }

  async function sweep(e) {   // pan a wide table from its first column to its last while the presenter talks
    const sc = e.querySelector('.dvn-scroller');
    if (!sc || sc.scrollWidth - sc.clientWidth < 8) return;
    await sleep(900);
    const from = sc.scrollLeft, to = sc.scrollWidth - sc.clientWidth, ms = Math.min(4200, 900 + (to - from) * 5), t0 = performance.now();
    await new Promise((done) => {
      const tick = (now) => {
        if (gone) return done();
        const k = Math.min(1, (now - t0) / ms), ease = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
        sc.scrollLeft = from + (to - from) * ease;
        k < 1 ? requestAnimationFrame(tick) : done();
      };
      requestAnimationFrame(tick);
    });
  }

  function say_(k, t, s) { kick.textContent = k; ttl.textContent = t; say.textContent = s; }

  function paint() {
    panel.classList.toggle('moving', busy);
    back.disabled = busy || at <= 0 || done;
    go.disabled = busy;
    num.textContent = at < 0 ? steps.length + ' stops' : (done ? '' : (at + 1) + ' / ' + steps.length);
    go.textContent = done ? 'Restart' : (at < 0 ? '\\u25B6 Play' : (at === steps.length - 1 ? 'Finish' : 'Next \\u2192'));
    line.firstChild.style.width = (done ? 100 : Math.max(0, at + 1) / steps.length * 100) + '%';
  }

  async function goTo(i, shown) {
    if (busy) return;
    busy = true; done = false; paint();
    await zoomOut();
    const step = steps[i];
    const prefix = path.length <= step.path.length && path.every((p, n) => p === step.path[n]);
    const clicks = prefix ? step.path.slice(path.length) : step.path;
    for (const sel of clicks) await clickOn(sel, shown);
    if (gone) return;
    path = step.path; at = i; focused = step;
    say_(step.section, step.title, step.text);
    const e = await waitFor(step.focus);
    if (e && !gone) {
      if (clicks.length && shown) await sleep(700);   // a new page: let the audience see all of it before zooming in
      await settle(e);
      await reveal(e);
      const r = e.getBoundingClientRect();
      await moveCursor(r.left + r.width / 2, r.top + r.height / 2, !shown);
      await zoomIn(find(step.focus) || e, step.zoom);
      if (step.sweep && !gone) await sweep(find(step.focus) || e);
    }
    busy = false; paint();
  }

  async function finish() {
    if (busy) return;
    busy = true; paint();
    await zoomOut();
    await clickOn(data.home, true);
    path = [data.home];
    await waitFor('.st-key-tiles');
    await moveCursor(innerWidth / 2, innerHeight / 2 - 60);
    say_('Summary', 'That is the full workflow', 'From a document arriving to a posted, auditable case: capture and check, match and receive, post and audit.');
    done = true; busy = false; paint();
  }

  const next = () => { if (done) { at = -1; goTo(0, true); } else if (at === steps.length - 1) finish(); else goTo(at + 1, true); };
  const prev = () => { if (at > 0 && !done) goTo(at - 1, false); };

  function leave() {
    gone = true;
    document.removeEventListener('keydown', onKey);
    removeEventListener('resize', onResize);
    [shield, ring, cursor, line, panel].forEach((e) => e.remove());
    root.classList.remove('annie-tour');
    ['--tour-x', '--tour-y', '--tour-s'].forEach((v) => root.style.removeProperty(v));
    document.__annieTourRun = null;
    document.querySelector('.st-key-tour_exit button')?.click();
  }

  function onKey(e) {
    if (e.key === ' ' || e.key === 'ArrowRight' || e.key === 'PageDown') { e.preventDefault(); if (!busy) next(); }
    else if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); prev(); }
    else if (e.key === 'Escape') leave();
    else if (e.key === 'f' || e.key === 'F') { document.fullscreenElement ? document.exitFullscreen() : root.requestFullscreen?.(); }
  }

  async function onResize() {   // keep the framing right after going full screen
    if (busy || !focused || done || at < 0) return;
    busy = true; paint();
    setCamera(0, 0, 1); await sleep(880);
    const e = find(focused.focus);
    if (e) { await reveal(e); await zoomIn(e, focused.zoom); }
    busy = false; paint();
  }

  go.addEventListener('click', (e) => { e.currentTarget.blur(); next(); });
  back.addEventListener('click', (e) => { e.currentTarget.blur(); prev(); });
  exit.addEventListener('click', leave);
  document.addEventListener('keydown', onKey);
  addEventListener('resize', onResize);

  moveCursor(cx, cy - 60, true).then(() => cursor.classList.add('on'));
  say_('Guided demo', 'Annie in action', 'Follow an invoice from arrival to archive. Each stop pauses so you can talk; press Next or Space to move on.');
  paint();
})();
"""


def render():
    """Draw the tour's hidden Exit button and start the tour in the browser. The app page below it stays live."""
    ss = st.session_state
    payload = dict(run=ss.tour_run, steps=prepare()[1], home=_btn("side_dashboard"))
    # st.html's sanitiser drops a script that contains tag-like text, so those "<" are written as \x3c (all are inside strings)
    script = re.sub(r"<(?=[/\w!])", r"\\x3c", ENGINE.replace("__DATA__", json.dumps(payload)))
    st.markdown(CSS, unsafe_allow_html=True)
    with st.container(key="tour_hidden"):
        st.button("Exit demo", key="tour_exit", on_click=stop)
        st.html(f"<script>{script}</script>", unsafe_allow_javascript=True)
