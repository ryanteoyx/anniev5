"""Annie v4 - Streamlit UI (belongs to annie_core.py).   Run:  streamlit run app.py"""

# =====================================================================================
# 1. IMPORTS AND SETUP
# =====================================================================================
import hmac
import html
import os
from datetime import date
from pathlib import Path

import pymupdf   # renders PDF previews as images
import pandas as pd
import streamlit as st

import annie_core as annie
import demo   # 'Slides' slideshow (demo.py + demo_screenshots/)
import tour   # 'Play demo' guided walk through the live app (tour.py)

st.set_page_config(page_title="Annie", layout="wide")
# the guided tour runs on its own copy of the demo data, because this database is shared by every visitor
con = annie.connect(tour.db_path() if st.session_state.get("tour_on") else annie.DB_PATH)
SAMPLES = Path(__file__).parent / "samples"


def load_demo(con):
    """Run every sample PDF through Module 1 and Module 2 exactly like an upload, in file-name order."""
    out = []
    for p in sorted(SAMPLES.glob("*.pdf")):
        out += annie.ingest_file(con, p.name, p.read_bytes(), channel="UPLOAD")
    return out


@st.cache_resource(show_spinner="Preparing the demo data...")
def demo_autoload(_con):
    """Once per app start, so the site never opens blank or half-used.
    DEMO_AUTOLOAD: "reset" = clear the database and load the demo documents on every start; "1" = load them only
    into an empty database (default); "0" = never."""
    mode = os.getenv("DEMO_AUTOLOAD", "1")
    if mode == "0" or (mode != "reset" and annie.list_documents(_con)):
        return 0
    if mode == "reset":
        annie.reset_db(_con)
    return len(load_demo(_con))


demo_autoload(con)
ss = st.session_state
ss.setdefault("results", [])
ss.setdefault("view_case", None)
ss.setdefault("view_po", None)
ss.setdefault("monitor_seen", 0)
demo.init_state()
tour.init_state()
if os.getenv("EMAIL_AUTO_FETCH", "1") != "0":
    annie.start_monitor()   # background inbox scan every POLL_SECONDS; no-op if already running or email is not configured
ss.results += annie.pop_monitor_results()   # documents the background scan ingested since the last rerun
for _a in annie.pop_monitor_alerts():
    st.toast(f"{_a['title']}: {_a['detail']}")
UPLOAD_TYPES = sorted(e.lstrip(".") for e in annie.SUPPORTED_EXTENSIONS)
DEFAULT_ORDER = "Default order"


# =====================================================================================
# 2. SHARED UI HELPERS (previews, summaries, filter/sort controls, tab bubbles)
# =====================================================================================
@st.cache_data(show_spinner=False, max_entries=200)
def pdf_pages(path, mtime):
    """PDF pages as PNG images, rendered once per file and reused (mtime makes a replaced file render again)."""
    with pymupdf.open(path) as pdf:
        return [page.get_pixmap(dpi=120).tobytes("png") for page in pdf]


def file_view(doc, height=620, key=""):
    """Preview a stored file: PDF pages and images inline, anything else as a download."""
    path = Path(doc["file_path"]) if doc and doc.get("file_path") else None
    if not path or not path.exists():
        st.info("No file stored for this document.")
        return
    ext = path.suffix.lower()
    if ext == ".pdf":
        with st.container(height=height, key=f"preview_{key}"):
            for png in pdf_pages(str(path), path.stat().st_mtime):
                st.image(png)
    elif ext in annie.IMAGE_EXTENSIONS and ext not in (".heic", ".heif", ".tif", ".tiff"):
        st.image(str(path))
    else:
        st.caption(f"Preview not available for {ext} files.")
    st.download_button("Download original file", path.read_bytes(), file_name=path.name, key=f"dl_{key}_{path.name}")


BASIS_LABEL = {"QTY": "Qty", "AMOUNT": "Amount", "SINGLE": "Single invoice (tick)"}


def summary(doc):
    p = doc["payload"]
    is_po = doc["doc_type"] == "PO"
    rows = {"Reference": p.get("po_reference") if is_po else p.get("invoice_reference"),
            "Vendor": p.get("vendor_name"), "Date": p.get("date"), "Total": annie.doc_total(p)}
    if is_po:
        rows.update({"Cost centre": p.get("cost_centre"), "Type": p.get("category"),
                     "Approver": f"{p.get('approver_name')} ({p.get('approver_title')})",
                     "Prepared by": f"{p.get('prepared_by')} ({p.get('prepared_by_title')})",
                     "Signed": "Yes" if p.get("signature_present") else "No"})
    else:
        rows["PO/PR cited on invoice"] = ", ".join(p.get("po_references") or [p.get("po_reference") or "-"])
    shown = [f"{v:,.2f}" if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v).replace(" (None)", "")
             for v in rows.values()]
    shown = ["—" if s in ("None", "", "-") or s.startswith("None (") else s for s in shown]
    st.table(pd.DataFrame({"Field": list(rows), "Value": shown}).set_index("Field"))
    if p.get("items"):
        st.dataframe(pretty(pd.DataFrame(p["items"])), hide_index=True)
    elif p.get("service_description"):
        st.caption("Service: " + str(p["service_description"]))


def _sort_key(v):
    if v is None:
        return (1, 0, 0)
    if isinstance(v, (int, float)):
        return (0, 0, v)
    return (0, 1, str(v).lower())


def controls(key, rows, sort_fields):
    """Filter box + sort selector + order toggle + 'x of y entries' counter. Returns the filtered, sorted rows."""
    with st.container(key=f"ctl_{key}"):
        c1, c2, c3, c4 = st.columns([3, 2, 1.4, 2], vertical_alignment="center")
    q = c1.text_input("Filter", key=f"flt_{key}", placeholder="Filter entries", label_visibility="collapsed")
    field = c2.selectbox("Sort by", [DEFAULT_ORDER] + list(sort_fields), key=f"srt_{key}",
                         label_visibility="collapsed", format_func=lambda f: f if f == DEFAULT_ORDER else f"Sort by: {_label(f)}")
    desc = c3.toggle("Descending", key=f"dsc_{key}")
    out = list(rows)
    if q.strip():
        out = [r for r in out if q.strip().lower() in " ".join(str(v) for v in r.values()).lower()]
    if field == DEFAULT_ORDER:
        out = out[::-1] if desc else out
    else:
        out = sorted(out, key=lambda r: _sort_key(r.get(field)), reverse=desc)
    c4.markdown(f"**{len(out)}** of {len(rows)} entries")
    return out


def bubble(n):
    """Count badge for nav items and tab names (rendered by Streamlit's markdown badge, styled in CSS)."""
    if not n:
        return ""
    return f" :gray-badge[{n}]"


# --- Presentation-only helpers (pills, table cells, detail headers, column labels) ---
# Three meanings only: needs someone's action (warn), finished (ok), everything else in progress (neutral).
PILL = {annie.S_OPEN_PO: "warn", annie.S_CALLOFF: "warn",
        annie.S_BILLED: "ok", annie.S_CALLED: "ok", annie.S_DONE: "ok"}
_UPPER = {"po", "pr", "po/pr", "id", "gr", "ses", "gr/ses"}


def pill(text):
    """A status as a coloured pill."""
    return f'<span class="pill {PILL.get(text, "neutral")}">{html.escape(str(text))}</span>'


def md(text):
    """Plain text that is safe inside a markdown label (file names are full of underscores)."""
    return str(text).replace("\\", "\\\\").replace("_", "\\_").replace("*", "\\*")


def cell(col, value, cls="", as_pill=False):
    """One table cell as plain HTML text, so '-' or '1.' never turn into markdown list markers."""
    if value in (None, "", "-"):
        body = '<span class="muted">—</span>'
    elif as_pill:
        body = pill(value)
    elif cls == "refs":   # several PO/PRs: wrap between references, never inside one at its hyphens
        body = ", ".join(f'<span class="nowrap">{html.escape(v.strip())}</span>' for v in str(value).split(","))
    else:
        body = html.escape(str(value))
    col.markdown(f'<div class="td {cls}">{body}</div>', unsafe_allow_html=True)


def head_row(widths, labels):
    for col, h in zip(st.columns(widths), labels):
        col.markdown(f'<div class="th">{html.escape(h)}</div>', unsafe_allow_html=True)


def page_head(title, status=None, meta=()):
    """Detail-page header: the reference, a status pill and a muted label/value row."""
    items = "".join(f'<span class="meta">{html.escape(k)} <b>{html.escape(str(v))}</b></span>'
                    for k, v in meta if v not in (None, ""))
    st.markdown(f'<div class="detail-head"><span class="ref">{html.escape(str(title))}</span>'
                f'{pill(status) if status else ""}</div><div class="detail-meta">{items}</div>', unsafe_allow_html=True)


def _label(c):
    if c == "ts":
        return "Time"
    words = str(c).replace("po_pr", "po/pr").replace("gr_ses", "gr/ses").split("_")
    out = " ".join(w.upper() if w.lower() in _UPPER else w for w in words)
    return out[:1].upper() + out[1:]


def pretty(df):
    """Read-only tables: snake_case column names shown as readable labels."""
    return df.rename(columns=_label)


def nice(code):
    """MACHINE_CODE -> 'Machine code' for display."""
    return str(code or "").replace("_", " ").capitalize()


def render_results(results):
    if not results:
        st.caption("Nothing submitted in this session yet. Processed files are listed here with where Annie routed them.")
        return
    rows = list(results)[::-1]
    rows = controls("results", rows, ["source_file", "m1_status", "route", "record_id"])
    for r in rows:
        m2 = r.get("m2") or {}
        parts = [f"**{md(r.get('source_file') or r.get('record_id'))}**", nice(r.get("m1_status")), nice(r.get("route"))]
        if m2:
            parts.append(" ".join(md(x) for x in (nice(m2.get("outcome")), m2.get("case_id"), m2.get("status")) if x))
        with st.expander("  ·  ".join(parts)):
            st.json(r)


# =====================================================================================
# 3. CASE PAGE (one invoice: allocation, GR/SES batches, Post)
# =====================================================================================
def gr_form(case_id, lines):
    """One GR/SES batch. Quantities (goods) or amounts (services) are entered per allocated PO/PR line."""
    cat = "Services" if all(l["basis"] in ("AMOUNT", "SINGLE") for l in lines) else "Goods"
    preparers = annie.allowed_preparers(con, case_id)
    vendor = annie.case_po_docs(con, case_id)[0]["payload"].get("vendor_name")
    with st.form(f"gr_{case_id}"):
        st.caption("A GR/SES can be raised in batches. Enter what was actually received or performed in this batch; "
                   "the case completes once receipts cover everything billed on this invoice.")
        a, b = st.columns(2)
        a.text_input("PO/PR reference(s)", ", ".join(sorted({l["po_reference"] for l in lines})), disabled=True)
        b.text_input("Vendor", vendor or "", disabled=True)
        a.text_input("SES/GR number", annie.next_ses_number(con, cat) + " (auto-generated on submit)", disabled=True)
        prepared = b.selectbox("Prepared by (name) - must match the PO/PR", preparers)
        d1, d2 = st.columns(2)
        f_from = d1.date_input("Performance / service date - from", date.today())
        f_to = d2.date_input("Performance / service date - to", date.today())
        df = pd.DataFrame([dict(line_id=l["line_id"], po_reference=l["po_reference"], item=l["description"],
                                basis=BASIS_LABEL[l["basis"]], ordered=l["ordered"], received_for_this_invoice=l["received"],
                                billed_this_invoice=l["billed_this"], receive_now=min(l["needed"], l["room"])) for l in lines])
        edited = st.data_editor(df, hide_index=True, key=f"gr_ed_{case_id}",
                                disabled=[c for c in df.columns if c != "receive_now"],
                                column_config={"line_id": "Line", "po_reference": "PO/PR", "item": "Item", "basis": "Basis",
                                               "ordered": "Ordered", "received_for_this_invoice": "Received so far",
                                               "billed_this_invoice": "Billed on this invoice",
                                               "receive_now": st.column_config.NumberColumn("Receive now (single invoice: 1 = done)", min_value=0.0)})
        submitted = st.form_submit_button("Submit GR/SES", type="primary")
    if submitted:
        totals = {}
        for r in edited.to_dict("records"):
            totals[int(r["line_id"])] = totals.get(int(r["line_id"]), 0.0) + float(r["receive_now"] or 0)
        gr = dict(service_date_from=f_from.isoformat(), service_date_to=f_to.isoformat(), prepared_by=prepared,
                  lines=[dict(line_id=k, receive=v) for k, v in totals.items()])
        try:
            res = annie.submit_gr(con, case_id, gr)
            msg = f"GR/SES {res['ses_gr_number']} saved. Case status: {res['status']}."
            ss.flash = [msg]
            st.rerun()
        except ValueError as e:
            st.error(str(e))


def manual_panel(case_id):
    """Stage 1: match the invoice by hand (goods by qty, services by amount, or a single-invoice service)."""
    with st.expander("Match manually"):
        inv_lines, cands = annie.invoice_line_list(con, case_id), annie.manual_candidates(con, case_id)
        if not cands:
            st.info("No PO/PR line has anything left to bill.")
            return
        by_label = {c["label"]: c for c in cands}
        st.caption("For each invoice line choose the PO/PR line it bills. Enter a **quantity** for goods, a **money amount** for services "
                   "tracked by amount, or any number above 0 for a single-invoice service (it takes the whole invoice line). "
                   "To split one invoice line over several PO/PR lines, add rows with the same invoice-line number; each invoice line must reach 100%.")
        seed = []
        for ln in inv_lines:
            best = max(cands, key=lambda c: (annie.line_score(ln, c, False, False), c["vendor_sim"]))
            val = ln["qty"] if best["basis"] == "QTY" else (1.0 if best["basis"] == "SINGLE" else ln["amount"])
            seed.append(dict(inv_line=ln["index"], invoice_item=ln["description"], po_line=best["label"], allocate=min(val, best["open"]) if best["basis"] != "SINGLE" else 1.0))
        # a form: editing the table or typing the reason does not rerun the page until Check or Confirm is pressed
        with st.form(f"mm_form_{case_id}", border=False):
            edited = st.data_editor(pd.DataFrame(seed), num_rows="dynamic", hide_index=True, key=f"mm_{case_id}", disabled=["invoice_item"],
                                    column_config={"inv_line": st.column_config.NumberColumn("Invoice line", min_value=1, max_value=len(inv_lines), step=1),
                                                   "invoice_item": "Invoice item",
                                                   "po_line": st.column_config.SelectboxColumn("PO/PR line", options=list(by_label), width="large", required=True),
                                                   "allocate": st.column_config.NumberColumn("Qty / amount", min_value=0.0)})
            reason = st.text_input("Reason for the manual match (required to confirm)", key=f"mm_reason_{case_id}")
            b1, b2, _ = st.columns([1.2, 2, 3])
            check = b1.form_submit_button("Check match")
            confirm = b2.form_submit_button("Confirm manual match", type="primary")
        rows = []
        for r in edited.to_dict("records"):
            if pd.isna(r.get("inv_line")) or r.get("po_line") not in by_label or pd.isna(r.get("allocate")):
                continue
            rows.append(dict(inv_line=int(r["inv_line"]), po_line_id=by_label[r["po_line"]]["line_id"], value=float(r["allocate"])))
        if check:
            ss[f"mm_chk_{case_id}"] = annie.manual_match(con, case_id, rows, dry_run=True)
        chk = ss.get(f"mm_chk_{case_id}")
        if chk:
            for e in chk["errors"]:
                st.error(e)
            if chk["rows"]:
                st.dataframe(pretty(pd.DataFrame(chk["rows"]).drop(columns=["po_line_id", "qty"])), hide_index=True)
            if chk["ok"] and chk["below_threshold"]:
                st.warning(f"Some choices score below the automatic threshold ({annie.LINK_THRESHOLD}) or the vendor name looks different. "
                           "You can still confirm, with a reason.")
            elif chk["ok"]:
                st.success("Checks passed.")
        if confirm:
            try:
                res = annie.manual_match(con, case_id, rows, reason=reason)
                ss.pop(f"mm_chk_{case_id}", None)
                ss.flash = [f"{case_id} matched manually. Status: {res['status']}."]
                st.rerun()
            except ValueError as e:
                st.error(str(e))


def unmatch_panel(case_id):
    """Stage 2: undo the match but keep the invoice, so it can be re-matched by hand in Stage 1."""
    with st.expander("Unmatch (send back to Stage 1)"):
        st.caption("Reverses the billing on the PO/PR lines (a single-invoice PO/PR becomes open again) and returns this invoice to "
                   "Stage 1 so you can match it manually. It will not be re-matched automatically. GR/SES batches raised for this match are voided.")
        with st.form(f"um_form_{case_id}", border=False):
            reason = st.text_input("Reason (required)", key=f"um_reason_{case_id}")
            go = st.form_submit_button("Unmatch")
        if go:
            try:
                annie.unmatch_case(con, case_id, reason)
                ss.flash = [f"{case_id} unmatched and returned to Stage 1."]
                st.rerun()
            except ValueError as e:
                st.error(str(e))


def dismiss_panel(case_id):
    """Stage 1 / Stage 2: delete the invoice (billing reversed, file forgotten so it can be resubmitted)."""
    with st.expander("Dismiss invoice (delete)"):
        st.warning("This deletes the invoice and its stored file. Any billing it made on PO/PR lines is reversed "
                   "(many-to-many lines get their balance back; a single-invoice PO/PR returns to Stage 1). "
                   "GR/SES batches raised for this match are voided. The same file can be uploaded again later.")
        with st.form(f"dis_form_{case_id}", border=False):
            ok = st.checkbox("I understand and want to delete this invoice", key=f"dis_ok_{case_id}")
            go = st.form_submit_button("Dismiss invoice")
        if go and not ok:
            st.error("Tick the box to confirm the deletion.")
        elif go:
            try:
                annie.delete_invoice_case(con, case_id, "Dismissed from the case page")
                ss.flash = [f"{case_id} dismissed and deleted."]
                ss.view_case = None
                st.rerun()
            except ValueError as e:
                st.error(str(e))


def po_page(record_id):
    """Preview of a PO/PR: the document, its line balances and the invoices charged to it."""
    d = annie.po_detail(con, record_id)
    if st.button("← Back", key="back_po"):
        ss.view_po = None
        st.rerun()
    p = d["doc"]["payload"]
    page_head(f"PO/PR {p.get('po_reference')}", None,
              [("Vendor", p.get("vendor_name")), ("Basis", d["lines"][0]["basis"] if d["lines"] else None)])
    with st.container(key="detail_cols"):
        left, right = st.columns(2, gap="large")
    with left:
        summary(d["doc"])
        file_view(d["doc"], key="po_preview")
    with right:
        st.markdown("#### Lines and balances")
        if d["lines"] and d["lines"][0]["basis"].startswith("Services (single"):
            st.info("Single-invoice service: this PO/PR expects one invoice only.")
        st.dataframe(pretty(pd.DataFrame(d["lines"])), hide_index=True)
        st.markdown("#### Invoices charged to this PO/PR")
        if d["invoices"]:
            st.dataframe(pretty(pd.DataFrame(d["invoices"])), hide_index=True)
        else:
            st.caption("None yet.")


def do_post(case_id):
    """Runs when the Post download is clicked: archive the case."""
    try:
        annie.post_case(con, case_id)
        ss.flash = [f"{case_id} posted and moved to Complete Archive."]
    except Exception as e:
        ss.flash = [f"Post failed: {e}"]
    ss.view_case = None


def calloff_gr_form(case_id):
    """GR/SES batch for a call-off case: enter what was received for each line of the matched invoices."""
    d = annie.calloff_detail(con, case_id)
    po = d["po"]["payload"]
    lines = annie.calloff_lines(con, case_id)
    with st.form(f"co_gr_{case_id}"):
        st.caption("Enter what was actually received or performed in this batch, per invoice line. The case completes once receipts "
                   "cover every matched invoice.")
        a, b = st.columns(2)
        a.text_input("PO/PR reference", str(po.get("po_reference")), disabled=True)
        b.text_input("Vendor", po.get("vendor_name") or "", disabled=True)
        a.text_input("SES/GR number", annie.next_ses_number(con, po.get("category")) + " (auto-generated on submit)", disabled=True)
        b.text_input("Prepared by (name) - must match the PO/PR", po.get("prepared_by") or "", disabled=True)
        d1, d2 = st.columns(2)
        f_from = d1.date_input("Performance / service date - from", date.today(), key=f"co_f1_{case_id}")
        f_to = d2.date_input("Performance / service date - to", date.today(), key=f"co_f2_{case_id}")
        df = pd.DataFrame([dict(inv_case=l["inv_case_id"], invoice=l["invoice_reference"], inv_line=l["inv_line"], item=l["description"],
                                basis="Qty" if l["basis"] == "QTY" else "Amount", billed=l["billed"], received_so_far=l["received"],
                                receive_now=l["needed"]) for l in lines])
        edited = st.data_editor(df, hide_index=True, key=f"co_gr_ed_{case_id}",
                                disabled=[c for c in df.columns if c != "receive_now"],
                                column_config={"inv_case": "Invoice case", "invoice": "Invoice", "inv_line": "Line", "item": "Item",
                                               "basis": "Basis", "billed": "Billed", "received_so_far": "Received so far",
                                               "receive_now": st.column_config.NumberColumn("Receive now", min_value=0.0)})
        submitted = st.form_submit_button("Submit GR/SES", type="primary")
    if submitted:
        gr = dict(service_date_from=f_from.isoformat(), service_date_to=f_to.isoformat(), prepared_by=po.get("prepared_by"),
                  lines=[dict(inv_case_id=r["inv_case"], inv_line=int(r["inv_line"]), receive=float(r["receive_now"] or 0)) for r in edited.to_dict("records")])
        try:
            res = annie.submit_calloff_gr(con, case_id, gr)
            ss.flash = [f"GR/SES {res['ses_gr_number']} saved. Case status: {res['status']}."]
            st.rerun()
        except ValueError as e:
            st.error(str(e))


def calloff_page(case_id):
    """A PO/PR that cites no amount: pick the invoices that bill against it, then Confirm to close the case."""
    d = annie.calloff_detail(con, case_id)
    c, po = d["case"], d["po"]
    pp = po["payload"]
    if st.button("← Back to cases", key="back_calloff"):
        ss.view_case = None
        st.rerun()
    page_head(case_id, c["status"], [("PO/PR", pp.get("po_reference")), ("Vendor", pp.get("vendor_name"))])
    for m in ss.pop("flash", []):
        st.success(m)
    is_open = c["status"] == annie.S_CALLOFF
    options = annie.calloff_open_invoices(con, case_id) if is_open else []
    by_id = {o["case_id"]: o for o in options}
    sel_key = f"co_sel_{case_id}"
    ss[sel_key] = [x for x in ss.get(sel_key, []) if x in by_id]   # forget invoices that are no longer open
    chosen = ss[sel_key]
    with st.container(key="detail_cols"):
        left, right = st.columns(2, gap="large")
    with left:
        st.markdown("#### Source documents")
        if is_open:
            docs = [("PO/PR " + str(pp.get("po_reference")), po)]
            for cid in dict.fromkeys(chosen):
                rid = con.execute("SELECT inv_record_id FROM cases WHERE case_id=?", (cid,)).fetchone()[0]
                docs.append(("Invoice " + str(by_id[cid]["invoice_reference"]), annie.get_doc(con, rid)))
        else:
            docs = [("PO/PR " + str(pp.get("po_reference")), po)] + [("Invoice " + str(i["doc"]["payload"].get("invoice_reference")), i["doc"]) for i in d["invoices"]]
        for tab, (label, doc), k in zip(st.tabs([x[0] for x in docs]), docs, range(len(docs))):
            with tab:
                summary(doc)
                file_view(doc, key=f"co{k}_{case_id}")
    with right:
        st.markdown("#### Match invoices to this Call-Off PO/PR")
        if is_open:
            st.info("This PO/PR cites no amount, so Annie does not match it automatically. Select every invoice that bills "
                    "against it (each one opens beside the PO/PR for checking), give a reason and press Confirm. "
                    "The case moves to Stage 2 (Pending GR/SES).")
            if not options:
                st.warning("No open invoices are waiting in Stage 1.")
            st.multiselect("Invoices billed against this PO/PR", list(by_id), key=sel_key,
                           format_func=lambda v: by_id[v]["label"], placeholder="Select open invoices...")
            for cid in chosen:
                if by_id[cid]["vendor_sim"] < annie.VENDOR_MIN:
                    st.warning(f"{cid}: vendor name looks different (similarity {by_id[cid]['vendor_sim']:.2f}).")
            with st.form(f"co_form_{case_id}", border=False):
                reason = st.text_input("Reason for the match (required)", key=f"co_reason_{case_id}")
                go = st.form_submit_button("Confirm", type="primary", disabled=not chosen)
            if go:
                try:
                    res = annie.confirm_calloff(con, case_id, chosen, reason)
                    for k in (sel_key, f"co_reason_{case_id}"):
                        ss.pop(k, None)
                    ss.flash = [f"{case_id} matched with {len(res['invoices'])} invoice(s) and moved to Stage 2 (Pending GR/SES)."]
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
        else:
            st.success({annie.S_GR: "Matched - pending GR/SES.", annie.S_DONE: "Matched and received - complete.",
                        annie.S_ARCHIVED: "Matched and received - posted to the Complete Archive."}.get(c["status"], ""))
            st.dataframe(pretty(pd.DataFrame([dict(case=i["case_id"], invoice=i["doc"]["payload"].get("invoice_reference"),
                                                   date=i["doc"]["payload"].get("date"), total=annie.doc_total(i["doc"]["payload"])) for i in d["invoices"]])),
                         hide_index=True)
            st.caption("Reason: " + (c["reason"] or "-"))
            if c["status"] == annie.S_GR:
                calloff_gr_form(case_id)
            grs = annie.case_gr_docs(con, case_id)
            if grs:
                st.markdown("**GR/SES batches for this call-off case**")
                for g in grs:
                    with st.expander(f"{g['payload']['ses_gr_number']} - {g['payload']['service_date_from']} - total {g['payload']['total']:,.2f}"):
                        st.json(g["payload"])
    if c["status"] == annie.S_DONE:
        st.divider()
        _, post_col = st.columns([5, 1])
        data, fname = annie.build_case_package(con, case_id)
        post_col.download_button("Post", data, file_name=fname, mime="application/zip", type="primary", key=f"post_{case_id}",
                                 on_click=do_post, args=(case_id,),
                                 help="Downloads the PO/PR, matched invoices and GR/SES, and moves the case to Complete Archive.")


def case_page(case_id):
    if str(case_id).startswith("CALL-"):
        return calloff_page(case_id)
    c = con.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
    inv, pos = annie.get_doc(con, c["inv_record_id"]), annie.case_po_docs(con, case_id)
    lines, grs = annie.case_lines(con, case_id), annie.case_gr_docs(con, case_id)
    if st.button("← Back to cases", key="back_case"):
        ss.view_case = None
        st.rerun()
    score = c["link_score"]
    page_head(case_id, c["status"], [("Invoice", inv["payload"].get("invoice_reference")),
                                     ("Vendor", inv["payload"].get("vendor_name")),
                                     ("Link score", f"{score:.2f}" if isinstance(score, (int, float)) else None)])
    for m in ss.pop("flash", []):
        st.success(m)
    with st.container(key="detail_cols"):
        left, right = st.columns(2, gap="large")
    with left:
        st.markdown("#### Source documents")
        tabs_ = st.tabs(["Invoice"] + [f"PO/PR {d['payload'].get('po_reference')}" for d in pos])
        for tab, doc, name in zip(tabs_, [inv] + pos, ["invoice"] + [f"po{i}" for i in range(len(pos))]):
            with tab:
                summary(doc)
                file_view(doc, key=name)
    with right:
        st.markdown("#### Allocation and receipts")
        if lines:
            st.dataframe(pretty(pd.DataFrame([dict(po_pr=l["po_reference"], item=l["description"], basis=BASIS_LABEL[l["basis"]],
                                                   ordered=l["ordered"], billed_this_invoice=l["billed_this"],
                                                   received_for_this_invoice=l["received"], still_to_receive=l["needed"],
                                                   matched=("manual: " + (l["a_reason"] or "")) if l["manual"] else "automatic") for l in lines])),
                         hide_index=True)
        if c["status"] == annie.S_OPEN_PO:
            st.warning("Not allocated yet: " + (c["reason"] or "waiting for a matching PO/PR"))
            if st.button("Retry automatic allocation"):
                annie.allocate_invoice(con, case_id, force=True)
                st.rerun()
        elif c["status"] == annie.S_GR:
            gr_form(case_id, lines)
        else:
            st.success("Receipts cover everything billed on this invoice" + (" - posted to the Complete Archive." if c["status"] == annie.S_ARCHIVED else "."))
        if grs:
            st.markdown("**GR/SES batches for this invoice-PO match**")
            for g in grs:
                with st.expander(f"{g['payload']['ses_gr_number']} - {g['payload']['service_date_from']} - total {g['payload']['total']:,.2f}"):
                    st.json(g["payload"])
    if c["status"] == annie.S_OPEN_PO:
        st.divider()
        manual_panel(case_id)
        dismiss_panel(case_id)
    elif c["status"] == annie.S_GR:
        st.divider()
        unmatch_panel(case_id)
        dismiss_panel(case_id)
    if c["status"] == annie.S_DONE:
        st.divider()
        _, post_col = st.columns([5, 1])
        data, fname = annie.build_case_package(con, case_id)
        post_col.download_button("Post", data, file_name=fname, mime="application/zip", type="primary",
                                 key=f"post_{case_id}", on_click=do_post, args=(case_id,),
                                 help="Downloads the case folder (invoice, matched PO/PRs, GR/SES) and moves the case to Complete Archive.")


# =====================================================================================
# 2B. STYLESHEET, SIDE NAVIGATION (light list, active page highlighted) AND PROCESSING TABS
# =====================================================================================
SIDE = [("dashboard", "Dashboard"), ("submit", "Submit Document"), ("review", "Intake Review"), ("processing", "Processing"),
        ("archive", "Complete Archive"), ("docs", "Documents"), ("audit", "Audit Log"), ("controls", "Controls")]
# navigation follows the AP flow: intake -> review -> match/receive/post -> archive, then the records and admin pages
SIDE_GROUP = {"submit": "Workflow", "docs": "Records", "controls": "Admin"}   # a group label before these items
PAGE_TITLES = dict(SIDE)
# Call-Offs sit next to Stage 1: both are invoices waiting to be matched, and a confirmed Call-Off moves to Stage 2
PTABS = [("s1", "Stage 1 - Open cases"), ("calloff", "Call-Offs"), ("s2", "Stage 2 - Pending GR/SES"), ("s3", "Stage 3 - Complete")]
ss.setdefault("side", "dashboard")
ss.setdefault("ptab", "s1")
pending = annie.counts(con)
side_badge = {"review": pending["review"], "processing": pending["s1"] + pending["s2"] + pending["s3"] + pending["calloff"]}

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* ---- Palette: neutrals, one accent, three status colours. Every colour on the page comes from here. ---- */
:root {
    --ink:#0f172a;          /* headings, key figures */
    --ink-2:#334155;        /* body text */
    --muted:#64748b;        /* labels, captions */
    --faint:#94a3b8;        /* placeholders, empty values */
    --line:#e2e8f0;         /* borders */
    --line-strong:#cbd5e1;  /* input borders, dashed drop zone */
    --line-soft:#f1f5f9;    /* row dividers, hover and neutral fills */
    --canvas:#f8fafc;       /* page background */
    --surface:#ffffff;      /* cards, tables, sidebar */
    --accent:#2563eb;       /* primary actions, links, active tab, current page */
    --accent-strong:#1d4ed8;
    --accent-soft:#eff6ff;  /* current page and active-stage tints */
    --accent-line:#bfdbfe;
    --ok:#15803d;   --ok-soft:#f0fdf4;
    --warn:#b45309; --warn-soft:#fffbeb;
    --bad:#b91c1c;  --bad-soft:#fef2f2;
}

/* ---- Base typography & canvas ---------------------------------------- */
html, body, [class*="st-"], .stMarkdown, button, input, textarea, select {
    font-family:'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;}
/* Streamlit draws icons from ligatures in its own icon font - never override it */
[data-testid="stIconMaterial"], .material-symbols-rounded {font-family:'Material Symbols Rounded' !important;}
/* An icon is its name drawn as a ligature, so until that font arrives it would read as a word
   ("keyboard_double_arrow_right"). Keep icons one glyph wide and invisible until the font is ready. */
[data-testid="stIconMaterial"] {max-width:1.25em; overflow:hidden; white-space:nowrap;}
html:not(.annie-icons) [data-testid="stIconMaterial"] {color:transparent !important;}
/* The sidebar open/close buttons draw their own chevrons, so they never depend on the icon font. */
[data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"],
[data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"] {display:none;}
[data-testid="stExpandSidebarButton"]::before, [data-testid="stSidebarCollapseButton"] button::before {
    content:""; width:18px; height:18px; background:var(--ink-2);
    -webkit-mask:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M6 17l5-5-5-5M13 17l5-5-5-5'/%3E%3C/svg%3E") center/contain no-repeat;
    mask:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M6 17l5-5-5-5M13 17l5-5-5-5'/%3E%3C/svg%3E") center/contain no-repeat;}
[data-testid="stSidebarCollapseButton"] button::before {transform:scaleX(-1); background:var(--muted);}
.stApp {background:var(--canvas); color:var(--ink-2);}
.block-container, [data-testid="stMainBlockContainer"] {max-width:1280px; padding-top:2.6rem; padding-bottom:4rem;}
/* hide Streamlit's Deploy/menu chrome and heading anchors, but keep the sidebar open/close button usable */
[data-testid="stToolbarActions"], [data-testid="stAppDeployButton"], [data-testid="stDecoration"], [data-testid="stMainMenu"],
[data-testid="stHeaderActionElements"], footer, #MainMenu {display:none !important;}
[data-testid="stHeader"] {background:rgba(248,250,252,.86); backdrop-filter:blur(8px);}
[data-testid="stExpandSidebarButton"] {background:var(--surface); border:1px solid var(--line); border-radius:8px;
    width:40px; height:40px; box-shadow:0 1px 2px rgba(15,23,42,.06); display:flex; align-items:center; justify-content:center;}
[data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"] {color:var(--ink) !important;}
[data-testid="stExpandSidebarButton"]:hover {background:var(--line-soft);}

/* ---- Headings (Streamlit >= 1.4x: the main area is [data-testid="stMain"], not .main) ---- */
[data-testid="stMain"] h1, [data-testid="stMain"] h2 {color:var(--ink); font-weight:600; letter-spacing:-.02em;}
[data-testid="stMain"] h2 {font-size:1.75rem; margin-bottom:0;}
[data-testid="stMain"] h3 {color:var(--ink); font-weight:600; letter-spacing:-.01em; font-size:1.05rem; padding:.2rem 0 .3rem;}
[data-testid="stMain"] h4 {color:var(--muted); font-weight:600; font-size:.74rem; text-transform:uppercase; letter-spacing:.05em; padding:.6rem 0 .2rem;}
hr {border-color:var(--line); margin:1.4rem 0;}
[data-testid="stCaptionContainer"] {color:var(--muted);}

/* ---- Buttons --------------------------------------------------------- */
[data-testid="stMain"] button[kind="primary"] {background:var(--accent); border:1px solid var(--accent); border-radius:8px; font-weight:600; box-shadow:none;}
[data-testid="stMain"] button[kind="primary"]:hover {background:var(--accent-strong); border-color:var(--accent-strong);}
[data-testid="stMain"] button[kind="secondary"] {border-radius:8px; border:1px solid var(--line-strong); color:var(--ink-2); font-weight:500; background:var(--surface);}
[data-testid="stMain"] button[kind="secondary"]:hover {border-color:var(--faint); color:var(--ink); background:var(--line-soft);}
[data-testid="stMain"] button[kind] p {white-space:nowrap;}
[data-testid="stMain"] button[kind]:disabled {background:var(--line-soft) !important; border-color:var(--line) !important;
    color:var(--faint) !important; opacity:1; cursor:not-allowed; box-shadow:none;}

/* ---- Inputs ---------------------------------------------------------- */
[data-testid="stFileUploaderDropzone"] {background:var(--canvas); border:1.5px dashed var(--line-strong); border-radius:12px; padding:1.3rem;}
[data-testid="stMain"] [data-testid="stTextInputRootElement"],
[data-testid="stMain"] [data-testid="stSelectbox"] div:has(> input),
[data-testid="stMain"] [data-testid="stNumberInputContainer"] {background:var(--surface); border:1px solid var(--line-strong); border-radius:8px;}
[data-testid="stMain"] [data-testid="stTextInputRootElement"]:focus-within,
[data-testid="stMain"] [data-testid="stSelectbox"] div:has(> input):focus-within,
[data-testid="stMain"] [data-testid="stNumberInputContainer"]:focus-within {border-color:var(--accent);}

/* ---- Alerts: routine notes stay neutral; warnings and errors keep their colour ---- */
[data-testid="stAlertContainer"] {border-radius:10px;}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]) {background:var(--surface); border:1px solid var(--line); color:var(--ink-2);}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]) * {color:var(--ink-2);}
/* a thin left strip says what kind of note it is */
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]) {box-shadow:inset 3px 0 0 var(--accent);}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]) {box-shadow:inset 3px 0 0 var(--warn);}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]) {box-shadow:inset 3px 0 0 var(--bad);}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentSuccess"]) {box-shadow:inset 3px 0 0 var(--ok);}
/* multi-selects match the other inputs; chosen items carry the accent tint */
[data-testid="stMain"] [data-testid="stMultiSelect"] [data-baseweb="select"] > div {background:var(--surface); border:1px solid var(--line-strong); border-radius:8px;}
[data-testid="stMain"] [data-testid="stMultiSelect"] [data-baseweb="tag"] {background:var(--accent-soft) !important; color:var(--accent-strong) !important;
    border:1px solid var(--accent-line);}
[data-testid="stMain"] [data-testid="stMultiSelect"] [data-baseweb="tag"] * {color:var(--accent-strong) !important;}

/* ---- Tables, expanders, cards ---------------------------------------- */
[data-testid="stDataFrame"], [data-testid="stTable"] {border:1px solid var(--line); border-radius:12px; overflow:hidden; background:var(--surface);}
[data-testid="stExpander"] details {background:var(--surface); border:1px solid var(--line); border-radius:12px;}
[data-testid="stExpander"] summary:hover {color:var(--ink);}
[class*="st-key-card_"] {background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:18px 22px 20px;}
.st-key-card_danger {border-color:color-mix(in srgb, var(--bad) 25%, white); background:var(--bad-soft);}
[data-testid="stMain"] .st-key-card_danger h3 {color:var(--bad);}
[data-testid="stMain"] .st-key-reset_db button[kind] {background:var(--bad); border-color:var(--bad); color:var(--surface);}
[data-testid="stMain"] .st-key-reset_db button[kind]:hover {background:color-mix(in srgb, var(--bad) 85%, black); border-color:color-mix(in srgb, var(--bad) 85%, black); color:var(--surface);}

/* ---- Row tables (case lists, PO/PR balances, call-offs, archive) ------
   Header and rows scroll sideways together on narrow screens instead of collapsing into a column. */
[class*="st-key-tbl_"] {background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:2px 16px 4px;
    gap:0 !important; overflow-x:auto;}
[class*="st-key-tbl_"] [data-testid="stHorizontalBlock"] {flex-wrap:nowrap !important; min-width:960px; align-items:center;
    gap:14px; padding:10px 0; border-top:1px solid var(--line-soft);}
[class*="st-key-tbl_"] [data-testid="stHorizontalBlock"]:has(.th) {border-top:none; padding:12px 0 8px;}
[class*="st-key-tbl_"] [data-testid="stHorizontalBlock"]:not(:has(.th)):hover {background:var(--canvas);}
[class*="st-key-tbl_"] [data-testid="stColumn"] {min-width:0 !important;}
.th {color:var(--muted); font-size:.7rem; font-weight:600; text-transform:uppercase; letter-spacing:.05em;}
.td {color:var(--ink-2); font-size:.87rem; line-height:1.4;}
.td.id, .td.num {white-space:nowrap; font-variant-numeric:tabular-nums;}
.td.id, .td.refs {font-size:.84rem;}
.td.refs {font-variant-numeric:tabular-nums;}   /* may hold several PO/PRs, so it wraps between them */
.td .nowrap {white-space:nowrap;}
.td.num {text-align:right;}
.td.reason {color:var(--muted); font-size:.83rem;}
.td .muted {color:var(--faint);}
[data-testid="stMain"] [class*="st-key-tbl_"] button[kind] {white-space:nowrap; padding:.2rem .9rem; min-height:2rem; font-size:.84rem;}

/* ---- Detail page header (case / PO/PR / call-off) --------------------- */
.detail-head {display:flex; align-items:center; flex-wrap:wrap; gap:8px 12px; margin:.6rem 0 .25rem;}
.detail-head .ref {font-size:1.6rem; font-weight:600; color:var(--ink); letter-spacing:-.02em;}
.detail-head .pill {font-size:.78rem; padding:3px 10px;}
.detail-meta {display:flex; flex-wrap:wrap; gap:4px 20px; color:var(--muted); font-size:.88rem; margin-bottom:1rem;}
.detail-meta b {color:var(--ink); font-weight:600;}

/* ---- Dashboard figures: neutral cards, the number carries the weight --- */
.st-key-tiles {margin:.6rem 0 1.4rem 0;}
.st-key-tiles [data-testid="stHorizontalBlock"] {gap:12px; align-items:stretch;}
/* equal-height cards: every wrapper between the column and the card grows to the row height */
.st-key-tiles [data-testid="stColumn"] {display:flex; flex-direction:column;}
.st-key-tiles [data-testid="stColumn"] *:has(.stat-card) {display:flex; flex-direction:column; flex:1 1 auto;}
.st-key-tiles [data-testid="stMarkdownContainer"] {margin-bottom:0;}
/* each card is one big button: the real button is stretched over it, invisible */
[class*="st-key-tile_"] {position:relative; gap:0 !important;}
[class*="st-key-tilebtn_"] {position:absolute; inset:0; z-index:1;}
[class*="st-key-tilebtn_"] [data-testid="stButton"], [class*="st-key-tilebtn_"] button {width:100%; height:100%; opacity:0; cursor:pointer;}
[class*="st-key-tile_"]:hover .stat-card {border-color:var(--line-strong); box-shadow:0 1px 3px rgba(15,23,42,.06);}
[class*="st-key-tile_"]:has(button:focus-visible) .stat-card {border-color:var(--accent);}
.stat-card {background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:16px 18px; flex:1 1 auto;
    transition:border-color .12s, box-shadow .12s;}
.stat-card .label {color:var(--muted); font-size:.78rem; font-weight:500; display:flex; align-items:flex-start; gap:7px;}
/* a small status dot and a coloured figure, only when there is something in that state */
.stat-card .label::before {content:""; width:7px; height:7px; border-radius:50%; background:var(--line-strong); flex:none; margin-top:.42em;}
.stat-card.warn .label::before {background:var(--warn);}
.stat-card.warn .value {color:var(--warn);}
.stat-card.ok .label::before {background:var(--ok);}
.stat-card.ok .value {color:var(--ok);}
.stat-card.info .label::before {background:var(--accent);}
.stat-card.info .value {color:var(--accent-strong);}
.stat-card .value {color:var(--ink); font-size:1.85rem; font-weight:600; line-height:1.2; margin-top:.3rem;
    letter-spacing:-.02em; font-variant-numeric:tabular-nums;}
.stat-card .foot {color:var(--faint); font-size:.76rem; margin-top:.15rem;}

/* ---- Status pills: three meanings, plus neutral ----------------------- */
.pill {display:inline-block; padding:2px 9px; border-radius:999px; font-size:.74rem; font-weight:500; line-height:1.5; white-space:nowrap;}
.pill.ok {background:var(--ok-soft); color:var(--ok);}
.pill.warn {background:var(--warn-soft); color:var(--warn);}
.pill.bad {background:var(--bad-soft); color:var(--bad);}
.pill.neutral {background:var(--line-soft); color:var(--ink-2);}

/* ---- Count badges (nav items, processing tabs) ------------------------ */
.stMarkdownBadge {background:var(--line-soft) !important; color:var(--muted) !important; font-size:.72rem !important;
    font-weight:600; border-radius:999px; padding:0 .45rem !important; font-variant-numeric:tabular-nums;}

/* ---- Sidebar: light, like the rest of the page ------------------------ */
[data-testid="stSidebar"] {background:var(--surface); border-right:1px solid var(--line);}
[data-testid="stSidebar"] h3 {color:var(--ink); font-weight:700; letter-spacing:-.01em; padding:.2rem .5rem 1rem .5rem;}
.nav-group {color:var(--faint); font-size:.68rem; font-weight:600; text-transform:uppercase; letter-spacing:.07em;
    padding:1rem .75rem .35rem;}
[class*="st-key-side_"], [class*="st-key-side_"] [data-testid="stButton"] {width:100% !important;}
[class*="st-key-side_"] button {width:100%; justify-content:flex-start; text-align:left; border-radius:8px; padding:.5rem .75rem;
    min-height:0; margin:0 0 2px 0; font-weight:500; background:transparent; color:var(--ink-2); border:none; box-shadow:none;}
/* Streamlit wraps the label in flex boxes that centre it; keep labels left and push the count badge right */
[class*="st-key-side_"] button > div, [class*="st-key-side_"] button > div > span,
[class*="st-key-side_"] button [data-testid="stMarkdownContainer"] {justify-content:flex-start; width:100%;}
[class*="st-key-side_"] button p {color:inherit; margin:0; width:100%; text-align:left; display:flex; align-items:center; gap:.5rem;}
[class*="st-key-side_"] button .stMarkdownBadge {margin-left:auto;}
[class*="st-key-side_"] button[kind="secondary"]:hover {background:var(--line-soft); color:var(--ink);}
/* the current page carries the accent (tint, text and a short bar), as in most finance tools */
[class*="st-key-side_"] button[kind="primary"], [class*="st-key-side_"] button[kind="primary"]:hover {background:var(--accent-soft);
    color:var(--accent-strong); font-weight:600; box-shadow:inset 3px 0 0 var(--accent);}
[class*="st-key-side_"] button[kind="primary"] .stMarkdownBadge {background:var(--surface) !important; color:var(--accent-strong) !important;}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {gap:2px;}
.brand {font-size:1.2rem; font-weight:700; color:var(--ink); letter-spacing:-.02em; padding:.2rem .75rem .9rem;}
.brand span {color:var(--accent);}

/* ---- Processing stages: underline tabs with counts; scroll sideways on phones ---- */
.st-key-ptabs {border-bottom:1px solid var(--line); margin-bottom:.4rem;}
.st-key-ptabs [data-testid="stHorizontalBlock"] {flex-wrap:nowrap !important; overflow-x:auto; gap:4px; align-items:flex-end;}
.st-key-ptabs [data-testid="stColumn"] {flex:0 0 auto !important; width:auto !important; min-width:max-content !important;}
.st-key-ptabs [data-testid="stColumn"]:last-child {display:none;}
[data-testid="stMain"] [class*="st-key-ptab_"] button[kind] {border-radius:0; padding:.55rem .7rem; min-height:0; font-weight:500;
    background:transparent; color:var(--muted); border:none; border-bottom:2px solid transparent; box-shadow:none; white-space:nowrap;}
[data-testid="stMain"] [class*="st-key-ptab_"] button p {color:inherit; margin:0; font-size:.84rem;}
[data-testid="stMain"] [class*="st-key-ptab_"] button[kind="secondary"]:hover {color:var(--ink); background:transparent;}
/* the current stage reads larger; the others step back */
[data-testid="stMain"] [class*="st-key-ptab_"] button[kind="primary"] {color:var(--ink); border-bottom-color:var(--accent); font-weight:600;
    padding:.5rem .8rem .6rem;}
[data-testid="stMain"] [class*="st-key-ptab_"] button[kind="primary"] p {font-size:1.1rem;}
[data-testid="stMain"] [class*="st-key-ptab_"] button[kind="primary"] .stMarkdownBadge {background:var(--accent-soft) !important;
    color:var(--accent-strong) !important;}
[data-testid="stMain"] [class*="st-key-polink_"] button[kind] {background:transparent; border:none; padding:0; min-height:0;
    justify-content:flex-start; box-shadow:none; color:var(--accent); font-weight:500; white-space:nowrap;}
[data-testid="stMain"] [class*="st-key-polink_"] button p {color:inherit; margin:0; text-align:left; font-size:.84rem;
    font-variant-numeric:tabular-nums;}
[data-testid="stMain"] [class*="st-key-polink_"] [data-testid="stMarkdownContainer"] {overflow:visible; text-overflow:clip;}
[data-testid="stMain"] [class*="st-key-polink_"] button[kind]:hover {background:transparent; color:var(--accent-strong);}
[data-testid="stMain"] [class*="st-key-polink_"] button[kind]:hover p {text-decoration:underline;}

/* the order toggle never truncates its label */
[class*="st-key-ctl_"] [data-testid="stColumn"]:nth-child(3) {flex:0 0 auto !important; min-width:max-content !important;}

/* ---- Tablets: detail pages stack the document above the allocation panel ---- */
@media (max-width: 1024px) {
    .st-key-tiles [data-testid="stHorizontalBlock"] {flex-wrap:wrap !important;}
    .st-key-tiles [data-testid="stColumn"] {flex:1 1 calc(33.33% - 8px) !important; min-width:calc(33.33% - 8px) !important;}
    .st-key-detail_cols [data-testid="stHorizontalBlock"] {flex-wrap:wrap !important;}
    .st-key-detail_cols [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {flex:1 1 100% !important; min-width:100% !important;}
}

/* ---- Phones ------------------------------------------------------------ */
@media (max-width: 640px) {
    .block-container, [data-testid="stMainBlockContainer"] {padding:3.8rem 1rem 3rem !important;}
    [data-testid="stMain"] h2 {font-size:1.5rem;}
    [data-testid="stMain"] h3 {font-size:1rem;}
    .st-key-tiles [data-testid="stColumn"] {flex:1 1 calc(50% - 6px) !important; min-width:calc(50% - 6px) !important;}
    .stat-card {padding:14px 14px 12px;}
    .stat-card .value {font-size:1.55rem;}
    .stat-card .label {font-size:.72rem;}
    .stat-card .foot {display:none;}
    [class*="st-key-card_"] {padding:14px 14px 16px;}
    .detail-head .ref {font-size:1.3rem;}
    /* filter / sort / order / count: filter on its own row, the rest side by side */
    [class*="st-key-ctl_"] [data-testid="stHorizontalBlock"] {flex-wrap:wrap !important; gap:8px 12px;}
    [class*="st-key-ctl_"] [data-testid="stColumn"] {flex:1 1 calc(50% - 12px) !important; min-width:calc(50% - 12px) !important;}
    [class*="st-key-ctl_"] [data-testid="stColumn"]:first-child {flex-basis:100% !important; min-width:100% !important;}
}

/* ---- Demo buttons: small pills fixed in the top-right corner of every page ---- */
.st-key-open_demo, .st-key-open_tour {position:fixed; top:.62rem; right:1.4rem; z-index:1000002; width:auto !important;}
.st-key-open_tour {right:6.2rem;}
[data-testid="stMain"] .st-key-open_tour button[kind] {height:2.1rem; min-height:2.1rem; padding:0 .95rem; border-radius:999px; font-size:.82rem; font-weight:600;}
[data-testid="stMain"] .st-key-open_demo button[kind] {height:2.1rem; min-height:2.1rem; padding:0 .95rem; border-radius:999px;
    background:var(--surface); border:1px solid var(--accent-line); color:var(--accent-strong); font-size:.82rem; font-weight:600;
    box-shadow:0 1px 2px rgba(15,23,42,.06);}
[data-testid="stMain"] .st-key-open_demo button[kind]:hover {background:var(--accent-soft); border-color:var(--accent); color:var(--accent-strong);}
@media (max-width: 768px) {.st-key-open_tour {display:none;}}   /* the tour is for presenting on a laptop or a big screen */
</style>
""", unsafe_allow_html=True)

# Presentation mode: while the demo is on, show only the slideshow (no sidebar, no page content).
if ss.demo_active:
    demo.render()
    st.stop()
if ss.tour_on:
    tour.render()
else:
    st.button("▶ Play demo", key="open_tour", type="primary", on_click=tour.start, help="A guided walk through the live application")
    st.button("Slides", key="open_demo", on_click=demo.start, help="A slideshow of the application")


def go_side(key, tab=None):
    ss.side, ss.view_case, ss.view_po = key, None, None
    if tab:
        ss.ptab = tab


def set_ptab(key):
    ss.ptab, ss.view_case, ss.view_po = key, None, None


@st.fragment(run_every=10)
def monitor_watch():
    """Every 10 s: if the background scan found something new, rerun the page so lists and badges refresh."""
    if annie.monitor_status()["version"] != ss.monitor_seen:
        ss.monitor_seen = annie.monitor_status()["version"]
        st.rerun()


with st.sidebar:
    st.markdown('<div class="brand">Annie<span>.</span></div>', unsafe_allow_html=True)
    for key, label in SIDE:
        if key in SIDE_GROUP:
            st.markdown(f'<div class="nav-group">{SIDE_GROUP[key]}</div>', unsafe_allow_html=True)
        st.button(label + bubble(side_badge.get(key, 0)), key=f"side_{key}", type="primary" if ss.side == key else "secondary",
                  on_click=go_side, args=(key,))
    monitor_watch()
    # On phones the sidebar is an overlay drawer: close it once a page is picked (display only).
    st.html("""<script>
    // Show icons only once their font has loaded (see the stIconMaterial rules in the stylesheet).
    if (!document.__annieIcons) {
      document.__annieIcons = true;
      const ready = () => document.documentElement.classList.add("annie-icons");
      document.fonts.load('24px "Material Symbols Rounded"').then((faces) => faces.length && ready());
      document.fonts.ready.then(() => document.fonts.check('24px "Material Symbols Rounded"') && ready());
    }
    if (!document.__annieNavClose) {
      document.__annieNavClose = true;
      document.addEventListener("click", (e) => {
        if (!window.matchMedia("(max-width: 768px)").matches) return;
        if (!e.target.closest('[class*="st-key-side_"] button')) return;
        setTimeout(() => document.querySelector('[data-testid="stSidebarCollapseButton"] button')?.click(), 120);
      }, true);
    }
    // Processing stages scroll sideways on phones: keep the current stage in view when it changes.
    if (!document.__annieTabScroll) {
      document.__annieTabScroll = true;
      new MutationObserver(() => {
        const active = document.querySelector('.st-key-ptabs button[kind="primary"]');
        const key = active && [...active.closest('[class*="st-key-ptab_"]').classList].find(c => c.startsWith("st-key-ptab_"));
        if (key && key !== document.__annieLastTab) {
          document.__annieLastTab = key;
          // scroll only the tab row (scrollIntoView would also shift Streamlit's outer layout)
          const row = active.closest('[data-testid="stHorizontalBlock"]');
          const r = row.getBoundingClientRect(), a = active.getBoundingClientRect();
          row.scrollLeft += (a.left - r.left) - (r.width - a.width) / 2;
        }
      }).observe(document.body, {childList: true, subtree: true, attributes: true, attributeFilter: ["kind"]});
    }
    </script>""", unsafe_allow_javascript=True)
page = ss.side


def processing_tabs():
    """Stage 1-3 as a row of rectangular tab buttons with pending-count bubbles."""
    with st.container(key="ptabs"):
        cols = st.columns([1.5, 1.75, 1.5, 1.1, 5.4])
        for col, (key, label) in zip(cols, PTABS):
            col.button(label + bubble(pending[key]), key=f"ptab_{key}", type="primary" if ss.ptab == key else "secondary",
                       on_click=set_ptab, args=(key,))
    st.write("")
    return ss.ptab


if ss.view_po:
    po_page(ss.view_po)
    st.stop()
if ss.view_case:
    case_page(ss.view_case)
    st.stop()


# =====================================================================================
# 4. CASE LIST (Stage 1 invoices / Stage 2 / Stage 3)
# =====================================================================================
CASE_SORTS = ["case_id", "vendor", "invoice_reference", "amount", "link_score", "status", "updated_at"]


def case_list(statuses, key, empty_msg, show_reason=False):
    rows = annie.case_rows(con, statuses)
    if not rows:
        st.info(empty_msg)
        return
    rows = controls(key, rows, CASE_SORTS)
    widths = [1.35, 1.4, 1.15, 1.05, 0.8, 0.55, 1.55, 0.75]   # sized to content: IDs and amounts never wrap
    with st.container(key=f"tbl_{key}"):
        head_row(widths, ["Case", "Vendor", "Invoice", "PO/PR", "Amount", "Score", "Reason" if show_reason else "Status", ""])
        for r in rows:
            cols = st.columns(widths)
            score = r["link_score"]
            cell(cols[0], r["case_id"], "id")
            cell(cols[1], r["vendor"])
            cell(cols[2], r["invoice_reference"], "id")
            cell(cols[3], r["po_references"], "refs")
            cell(cols[4], f"{r['amount']:,.2f}" if r["amount"] is not None else None, "num")
            cell(cols[5], f"{score:.2f}" if isinstance(score, (int, float)) else score, "num")
            if show_reason:
                cell(cols[6], r["reason"] or r["status"], "reason")
            else:
                cell(cols[6], r["status"], as_pill=True)
            if cols[7].button("Open", key=f"{key}_{r['case_id']}"):
                ss.view_case = r["case_id"]
                st.rerun()


# =====================================================================================
# 5. PAGE HEADER
# =====================================================================================
for m in ss.pop("flash", []):
    st.success(m)
st.header(PAGE_TITLES[page])


# =====================================================================================
# 6. PAGE: SUBMIT DOCUMENT (manual upload + email intake, both run Module 1 first)
# =====================================================================================
if page == "dashboard":
    # received documents only: GR/SES forms are generated by Annie, not received
    total = sum(1 for d in annie.list_documents(con) if d["channel"] != "GR/SES FORM")
    # in process order; each card opens the page or stage that holds those items
    # tone: "warn" = someone has to act, "ok" = ready to post, "info" = in progress; a zero is always neutral
    tiles = [
        ("Documents processed", total, "all channels", ("docs", None), "neutral"),
        ("Needs review", pending["review"], "in Intake Review", ("review", None), "warn"),
        ("Open", pending["s1"], "invoices to match, PO/PRs with balance", ("processing", "s1"), "warn"),
        ("Call-offs", pending["calloff"], "awaiting a manual match", ("processing", "calloff"), "warn"),
        ("Pending GR/SES", pending["s2"], "awaiting goods or service receipt", ("processing", "s2"), "info"),
        ("Complete", pending["s3"], "received, ready to post", ("processing", "s3"), "ok"),
    ]
    st.caption("Purchase orders and invoices from intake through 3-way matching, goods receipt and posting. "
               "Select a figure to open that list.")
    with st.container(key="tiles"):
        for col, (lbl, val, foot, (side, tab), tone) in zip(st.columns(len(tiles), gap="small"), tiles):
            with col, st.container(key=f"tile_{side}_{tab or 'all'}"):
                st.markdown(f'<div class="stat-card {tone if val else "neutral"}"><div class="label">{lbl}</div>'
                            f'<div class="value">{val}</div><div class="foot">{foot}</div></div>', unsafe_allow_html=True)
                st.button(f"Open {lbl}", key=f"tilebtn_{side}_{tab or 'all'}", on_click=go_side, args=(side, tab))
    if total == 0:
        st.info("No documents yet. Head to **Submit Document** to upload a PO or invoice, "
                "or open **Controls** to reset or configure the inbox.")

elif page == "submit":
    st.caption("Every document goes through Module 1 (duplicate check, extraction, field check) first. Only documents "
               "with every mandatory field enter Annie; the rest wait in Intake Review. PO/PRs and invoices can arrive "
               "in any order: invoices are allocated to PO/PR lines as soon as the balances allow.")
    up_col, mail_col = st.columns(2, gap="large")
    with up_col, st.container(key="card_upload"):
        st.subheader("Upload documents")
        files = st.file_uploader("PDF, image, DOCX, TXT, CSV or XLSX", type=UPLOAD_TYPES, accept_multiple_files=True)
        if st.button("Process documents", type="primary", disabled=not files):
            with st.spinner("Running Module 1..."):
                for f in sorted(files, key=lambda f: f.name):   # process in file-name order
                    try:
                        ss.results += annie.ingest_file(con, f.name, f.getvalue(), channel="UPLOAD")
                    except Exception as e:
                        st.error(f"{f.name}: {e}")
            st.rerun()
    with mail_col, st.container(key="card_email"):
        st.subheader("Email inbox")
        em = annie.email_config_status()
        if em["ok"]:
            mon = annie.monitor_status()
            st.write(f"Mailbox configured: {os.getenv('EMAIL_ADDRESS')}" + (f" (subject filter: `{em['subject_filter']}`)" if em["subject_filter"] else "") + ".")
            st.caption(f"Automatic fetch: {'ON, every ' + str(mon['poll_seconds']) + ' s' if mon['running'] else 'OFF'}"
                       + (f" | last scan {mon['last_run']}" if mon["last_run"] else "") + " (change on the Controls page).")
        else:
            st.info("Email intake is not connected on this site. Upload documents on the left instead.")
            st.caption("To connect a mailbox, set " + ", ".join(em["missing"]) + " (Railway Variables or `.env`) and restart the app.")
        if st.button("Check inbox now", disabled=not em["ok"]):
            with st.spinner("Reading the inbox..."):
                try:
                    res, stats = annie.check_inbox(con)
                    ss.results += res
                    st.success(f"{stats['emails']} email(s), {stats['attachments']} attachment(s) processed.")
                except Exception as e:
                    st.error(f"Email check failed: {e}")
    st.divider()
    st.subheader("Results this session")
    render_results(ss.results)


# =====================================================================================
# 7. PAGE: INTAKE REVIEW (Re-extract / Dismiss, then the missing fields)
# =====================================================================================
elif page == "review":
    st.caption("Documents Module 1 could not pass to Module 2. Re-extract after the extraction code or reference samples "
               "improve, or dismiss. A dismissed document is removed completely and can be resubmitted later.")
    review = annie.intake_review_rows(con)
    if not review:
        st.info("Nothing waiting for review.")
    else:
        review = controls("review", review, ["source_file", "m1_status", "channel", "received_at"])
    for r in review:
        k = r["record_id"]
        received = str(r["received_at"] or "").replace("T", " ")[:16]
        with st.expander(f"**{md(r['source_file'])}**  ·  {nice(r['m1_status'])}  ·  "
                         f"{nice(r['channel'])}  ·  {received}"):
            lcol, rcol = st.columns(2, gap="large")
            with lcol:
                file_view(r, height=520, key=f"rev_{k}")
            with rcol:
                b1, b2 = st.columns(2)
                if b1.button("Re-extract from file", key=f"rx_{k}", type="primary"):
                    try:
                        ss.results.append(annie.reextract_intake(con, k))
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
                if b2.button("Dismiss", key=f"dis_{k}"):
                    annie.dismiss_intake(con, k, "Dismissed from Intake Review")
                    st.rerun()
                if r["missing"]:
                    st.markdown("**Missing fields**")
                    st.markdown("\n".join(f"- {annie.LABELS.get(m, m)}" for m in r["missing"]))
                else:
                    st.markdown("**Why it is here**")
                    st.write(str(r["note"]))


# =====================================================================================
# 8. PAGE: PROCESSING (Stage 1 / Stage 2 / Stage 3 as top tabs)
# =====================================================================================
elif page == "processing":
    ptab = processing_tabs()
    if ptab == "s1":
        st.subheader("Invoices awaiting PO/PR")
        st.caption("Invoices that could not be fully allocated yet: the PO/PR has not arrived, no line matches, or the bill exceeds what is left on the PO/PR.")
        case_list([annie.S_OPEN_PO], "s1a", "No invoices waiting for a PO/PR.", show_reason=True)
        st.divider()
        st.subheader("PO/PRs with open balance")
        st.caption("Ordered, billed and received per PO/PR. Partly billed PO/PRs stay here until fully billed. PO/PRs that cite no amount are handled in Call-Offs. Click a PO/PR reference to preview it.")
        po = [r for r in annie.po_rows(con) if r["status"] != annie.S_BILLED]
        if not po:
            st.info("No PO/PR with an open balance.")
        else:
            po = controls("s1b", po, ["po_reference", "vendor", "mode", "status", "ordered", "billed", "received", "open_to_bill", "date"])
            st.download_button("Download CSV", pd.DataFrame(po).drop(columns=["record_id"]).to_csv(index=False),
                               file_name="po_pr_open_balance.csv", mime="text/csv", key="po_csv")
            widths = [10.6, 8.7, 8.3, 15.2, 7.9, 7.9, 7.9, 8.3, 8.9]   # measured: references, status pill and dates need these widths
            fmt = lambda v: None if v is None else f"{v:,.2f}"
            with st.container(key="tbl_s1b"):
                head_row(widths, ["PO/PR", "Vendor", "Type", "Status", "Ordered", "Billed", "Received", "Open to bill", "Date"])
                for r in po:
                    cols = st.columns(widths)
                    if cols[0].button(str(r["po_reference"]), key=f"polink_{r['record_id']}"):
                        ss.view_po = r["record_id"]
                        st.rerun()
                    cell(cols[1], r["vendor"])
                    cell(cols[2], r["mode"])
                    cell(cols[3], r["status"], as_pill=True)
                    for col, v in zip(cols[4:8], [r["ordered"], r["billed"], r["received"], r["open_to_bill"]]):
                        cell(col, fmt(v), "num")
                    cell(cols[8], r["date"], "id")

    elif ptab == "s2":
        st.caption("Invoice is allocated to PO/PR line(s), or a Call-Off case is matched, but receipts do not yet cover it. Open a case to record a GR/SES batch.")
        case_list([annie.S_GR], "s2", "No cases pending GR/SES.")

    elif ptab == "s3":
        st.caption("Receipts cover the invoice (or the matched invoices of a Call-Off case). Open a case and press Post to download its folder and archive it.")
        case_list([annie.S_DONE], "s3", "No complete cases yet.")

    elif ptab == "calloff":
        st.caption("PO/PRs that cite no amount are never matched automatically. Each opens its own case: open it, pick the invoices that bill "
                   "against it, and Confirm. It then moves to Stage 2 (Pending GR/SES) and reaches Stage 3 once receipts cover the invoices.")
        rows = annie.calloff_rows(con, [annie.S_CALLOFF])
        if not rows:
            st.info("No Call-Off PO/PR waiting.")
        else:
            rows = controls("calloffs", rows, ["case_id", "po_references", "vendor", "type", "date", "status"])
            widths = [1.5, 1.6, 2.4, 1.1, 1.3, 1.9, 0.9]
            with st.container(key="tbl_calloffs"):
                head_row(widths, ["Case", "PO/PR", "Vendor", "Type", "PO date", "Status", ""])
                for r in rows:
                    cols = st.columns(widths)
                    cell(cols[0], r["case_id"], "id")
                    cell(cols[1], r["po_references"], "refs")
                    cell(cols[2], r["vendor"])
                    cell(cols[3], r["type"])
                    cell(cols[4], r["date"], "id")
                    cell(cols[5], r["status"], as_pill=True)
                    if cols[6].button("Open", key=f"co_open_{r['case_id']}"):
                        ss.view_case = r["case_id"]
                        st.rerun()


# =====================================================================================
# 9. PAGE: DOCUMENTS (Module 1 + Module 2 movements per record)
# =====================================================================================
elif page == "docs":
    st.caption("One row per record: how it arrived, what Module 1 decided, and what Module 2 did with it.")
    rows = controls("docs", annie.list_documents(con),
                    ["record_id", "doc_type", "channel", "source_file", "module1_status", "route", "module2_outcome", "case_id", "received_at"])
    st.dataframe(pretty(pd.DataFrame(rows)), hide_index=True)


# =====================================================================================
# 10. PAGE: COMPLETE ARCHIVE (posted cases)
# =====================================================================================
elif page == "archive":
    st.caption("Posted cases kept as history. Open a case to view it, or download its package again.")
    rows = annie.archive_rows(con)
    if not rows:
        st.info("No posted cases yet.")
    else:
        rows = controls("archive", rows, CASE_SORTS + ["posted_at"])
        widths = [1.6, 2.0, 1.5, 1.6, 1.2, 1.8, 0.9, 1.2]
        with st.container(key="tbl_archive"):
            head_row(widths, ["Case", "Vendor", "Invoice", "PO/PR", "Amount", "Posted", "", ""])
            for r in rows:
                cols = st.columns(widths)
                cell(cols[0], r["case_id"], "id")
                cell(cols[1], r["vendor"])
                cell(cols[2], r["invoice_reference"], "id")
                cell(cols[3], r["po_references"], "refs")
                cell(cols[4], f"{r['amount']:,.2f}" if r["amount"] is not None else None, "num")
                cell(cols[5], str(r["posted_at"] or "").replace("T", " ")[:16], "id")
                if cols[6].button("Open", key=f"ar_{r['case_id']}"):
                    ss.view_case = r["case_id"]
                    st.rerun()
                pkg = annie.read_archive_package(con, r["case_id"])
                if pkg:
                    cols[7].download_button("Package", pkg, file_name=f"{r['case_id']}.zip", mime="application/zip", key=f"arz_{r['case_id']}")


# =====================================================================================
# 11. PAGE: AUDIT LOG (Module 1 and Module 2 events)
# =====================================================================================
elif page == "audit":
    stages = st.multiselect("Stage", ["MODULE 1", "MODULE 2"], default=["MODULE 1", "MODULE 2"])
    rows = controls("audit", annie.list_log(con, stages), ["ts", "stage", "event", "record_id", "case_id"])
    st.dataframe(pretty(pd.DataFrame(rows)), hide_index=True)


# =====================================================================================
# 12. PAGE: CONTROLS (sample data, database reset, Module 1 status)
# =====================================================================================
elif page == "controls":
    admin_pin = os.getenv("ADMIN_PIN") or ""
    with st.container(key="card_demo"):
        st.subheader("Demo data")
        st.caption(f"Clears the database and processes the {len(list(SAMPLES.glob('*.pdf')))} sample documents, so every "
                   "stage has example data. The hosted demo also does this by itself whenever it restarts or is redeployed.")
        unlocked = bool(admin_pin) and ss.get("admin_unlocked") == admin_pin
        if not admin_pin:
            st.info("Reset and reload are locked until an `ADMIN_PIN` is set "
                    "(Railway: the service's Variables; locally: the `.env` file).")
        elif not unlocked:
            with st.form("pin_form", border=False):
                c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
                entered = c1.text_input("Admin PIN", type="password", placeholder="Needed to reset or reload the data")
                go = c2.form_submit_button("Unlock")
            if go and hmac.compare_digest(entered.encode(), admin_pin.encode()):
                ss.admin_unlocked = admin_pin   # for this browser session only
                st.rerun()
            elif go:
                st.error("Wrong PIN.")
        else:
            st.caption("Unlocked for this session.")
        if st.button("Reset & load demo data", type="primary", key="demo_reload", disabled=not unlocked):
            with st.spinner("Loading the demo documents..."):
                annie.reset_db(con)
                count = len(load_demo(con))
            ss.results = []
            ss.flash = [f"Demo data reloaded: {count} documents processed."]
            st.rerun()
        if any(SAMPLES.glob("*.json")):   # original test loader: pre-extracted sample JSONs in place of Module 1
            if st.button("Load sample JSONs", disabled=not unlocked):
                ss.results += annie.load_samples(con, SAMPLES)
                st.rerun()
    with st.container(key="card_inbox"):
        st.subheader("Inbox monitor (automatic fetch)")
        mon = annie.monitor_status()
        st.write(f"Status: **{'running, every ' + str(mon['poll_seconds']) + ' s' if mon['running'] else 'stopped'}**"
                 + (f" | last scan: {mon['last_run']}" if mon["last_run"] else ""))
        if mon["last"]:
            st.caption("Last scan: " + ", ".join(f"{k} {v}" for k, v in mon["last"].items()))
        if mon["last_error"]:
            st.error("Last scan failed: " + mon["last_error"])
        b1, b2, _ = st.columns([1, 1, 2])
        if b1.button("Start", disabled=mon["running"] or not annie.email_config_status()["ok"]):
            annie.start_monitor()
            st.rerun()
        if b2.button("Stop", disabled=not mon["running"]):
            annie.stop_monitor()
            st.rerun()
        st.caption("Interval is POLL_SECONDS in .env (15-3600, default 60); a changed value needs an app restart (.env is read at startup). "
                   "Set EMAIL_AUTO_FETCH=0 to stop it starting automatically. Mail is never marked as read.")
        alerts = annie.open_alerts(con)
        if alerts:
            st.markdown("**Open alerts**")
            for al in alerts:
                c1, c2 = st.columns([8, 1])
                c1.warning(f"{al['created_at']} - {al['title']}: {al['detail']}")
                if c2.button("Dismiss", key=f"ack_{al['id']}"):
                    annie.acknowledge_alert(con, al["id"])
                    st.rerun()
    with st.container(key="card_status"):
        st.subheader("Module 1 status")
        ref = annie.get_reference_summary()
        st.write(f"OCR engine: **{ref['ocr_engine'] or 'not available'}**")
        st.write(f"Reference samples: {ref['purchase_orders']} PO/PR, {ref['supplier_invoices']} invoices")
        em = annie.email_config_status()
        st.write("Email: " + ("configured" if em["ok"] else "missing " + ", ".join(em["missing"])))
        st.caption(f"Line-match threshold >= {annie.LINK_THRESHOLD}   |   Vendor-name gate >= {annie.VENDOR_MIN}")
    with st.container(key="card_danger"):
        st.subheader("Danger zone")
        if st.button("Reset database (empty)", key="reset_db", disabled=not unlocked):
            annie.reset_db(con)
            ss.results = []
            st.rerun()
        st.caption("Deletes every document, case, allocation, GR/SES, archive entry and log line, leaving the app empty "
                   "(e.g. to upload live during a demo). Needs the admin PIN above. This cannot be undone.")
