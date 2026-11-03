"""Tests for the three review findings fixed in November 2026 (see docs/BUSINESS_LOGIC.md, section 9):
1. currency must match, 2. billing is net of tax, 3. Module 2 rejections go to Intake Review.

    python tests/test_findings.py     (or: pytest tests/)
"""
import sys

from harness import fresh


# --- small builders for Module 2 payloads ----------------------------------------------------------------
def goods_po(ref, currency="SGD", qty=10, price=5.0, desc="A4 Copier Paper 80gsm (ream)", vendor="Acme Office Supplies Pte Ltd"):
    return dict(doc_type="PO", record_id=f"po-{ref}", po_reference=ref, vendor_name=vendor, category="Goods",
                items=[dict(description=desc, qty=qty, unit_price=price, total=qty * price)], total=qty * price,
                currency=currency)


def goods_invoice(num, cites, currency="SGD", qty=10, price=5.0, desc="A4 Copier Paper 80gsm (ream)",
                  vendor="Acme Office Supplies Pte Ltd"):
    return dict(doc_type="INVOICE", record_id=f"inv-{num}", invoice_reference=num, vendor_name=vendor,
                items=[dict(description=desc, qty=qty, unit_price=price, total=qty * price)], total=qty * price,
                currency=currency, po_reference=cites, po_references=[cites] if cites else [])


def service_po(ref, amount, desc="Corporate photography coverage - annual"):
    return dict(doc_type="PO", record_id=f"po-{ref}", po_reference=ref, vendor_name="Lenscape Studios Pte Ltd",
                category="Services", items=[], service_description=desc, total=amount, currency="SGD")


def service_invoice(num, cites, total, tax=None, desc="Corporate photography coverage - annual"):
    return dict(doc_type="INVOICE", record_id=f"inv-{num}", invoice_reference=num, vendor_name="Lenscape Studios Pte Ltd",
                items=[], service_description=desc, total=total, tax=tax, currency="SGD",
                po_reference=cites, po_references=[cites])


INVOICE_TXT = """TAX INVOICE
Supplier: Harbour Stationery Pte Ltd
Invoice Number: HS-7001
Invoice Date: 2026-10-01
Description  Qty  Unit Price  Amount
Printer Paper A4 Box  2  45.00  90.00
Total Amount: SGD 90.00
"""


# --- 1. currency -----------------------------------------------------------------------------------------
def test_bare_dollar_sign_is_not_read_as_usd():
    annie, _, _ = fresh()
    assert annie.parse_amount_and_currency("$100.00") == (100.0, None)
    assert annie.parse_amount_and_currency("S$100.00") == (100.0, "SGD")
    assert annie.parse_amount_and_currency("US$100.00") == (100.0, "USD")
    assert annie.parse_amount_and_currency("SGD 1,250.50") == (1250.5, "SGD")


def test_same_currency_still_matches():
    annie, con, _ = fresh()
    annie.process_document(con, goods_po("PR-1"))
    r = annie.process_document(con, goods_invoice("INV-1", "PR-1"))
    assert r["outcome"] == "ALLOCATED", r


def test_other_currency_is_not_matched_automatically():
    annie, con, _ = fresh()
    annie.process_document(con, goods_po("PR-1", currency="SGD"))
    r = annie.process_document(con, goods_invoice("INV-1", "PR-1", currency="USD"))
    assert r["outcome"] == "UNALLOCATED", r
    assert "PR-1 is in SGD but the invoice is in USD" in r["reason"], r["reason"]


def test_unknown_currency_does_not_block():
    annie, con, _ = fresh()
    annie.process_document(con, goods_po("PR-1", currency="SGD"))
    r = annie.process_document(con, goods_invoice("INV-1", "PR-1", currency=None))
    assert r["outcome"] == "ALLOCATED", r


def test_manual_match_refuses_other_currency():
    annie, con, _ = fresh()
    annie.process_document(con, goods_po("PR-1", currency="SGD"))
    r = annie.process_document(con, goods_invoice("INV-1", "PR-1", currency="USD"))
    line_id = con.execute("SELECT line_id FROM po_lines").fetchone()[0]
    check = annie.manual_match(con, r["case_id"], [dict(inv_line=1, po_line_id=line_id, value=10)], dry_run=True)
    assert not check["ok"]
    assert any("is in SGD but the invoice is in USD" in e for e in check["errors"]), check["errors"]
    assert annie.manual_candidates(con, r["case_id"]) == []   # the picker does not offer it either


# --- 2. tax ----------------------------------------------------------------------------------------------
def test_subtotal_and_tax_are_read_but_tax_ids_are_not():
    annie, _, _ = fresh()
    text = ("TAX INVOICE\nGST Reg No.: M90371234X\nSubtotal 3,000.00\nGST 9%: SGD 270.00\n"
            "Total Amount: SGD 3,270.00\n")
    assert annie.find_subtotal_and_tax(text) == (3000.0, 270.0)
    assert annie.find_subtotal_and_tax("TAX INVOICE\nGST Reg No: 201234567A\nTotal: 100.00\n") == (None, None)


def test_net_total():
    annie, _, _ = fresh()
    assert annie.net_total(dict(total=3270.0, tax=270.0)) == 3000.0
    assert annie.net_total(dict(total=3270.0, subtotal=3000.0, tax=270.0)) == 3000.0
    assert annie.net_total(dict(total=100.0)) == 100.0
    assert annie.net_total(dict(total=100.0, tax=150.0)) == 100.0   # an impossible tax amount is ignored


def test_invoice_with_gst_is_not_mistaken_for_overbilling():
    annie, con, _ = fresh()
    annie.process_document(con, service_po("PR-9", 3000.0))
    r = annie.process_document(con, service_invoice("LS-1", "PR-9", total=3270.0, tax=270.0))
    assert r["outcome"] == "ALLOCATED", r
    billed = con.execute("SELECT billed_amount FROM po_lines").fetchone()[0]
    assert billed == 3000.0   # the PO/PR balance is used net of tax


def test_real_overbilling_is_still_caught():
    annie, con, _ = fresh()
    annie.process_document(con, service_po("PR-9", 3000.0))
    r = annie.process_document(con, service_invoice("LS-2", "PR-9", total=3600.0))   # no tax stated: 600 too much
    assert r["outcome"] == "UNALLOCATED", r
    assert "bills 3600 but PR-9 has only 3000 left" in r["reason"], r["reason"]


# --- 3. Module 2 rejections ------------------------------------------------------------------------------
def test_repeated_invoice_number_goes_to_intake_review_and_can_be_dismissed():
    annie, con, _ = fresh()
    first = annie.ingest_file(con, "HS-7001.txt", INVOICE_TXT.encode())[0]
    assert first["route"] == annie.R_M2, first
    copy = (INVOICE_TXT + "Payment terms: 30 days\n").encode()   # different file and content, same invoice number
    second = annie.ingest_file(con, "HS-7001-copy.txt", copy)[0]
    assert second["route"] == annie.R_REVIEW and second["m1_status"] == annie.M1_DUP_REF, second
    review = annie.intake_review_rows(con)
    assert [r["record_id"] for r in review] == [second["record_id"]]
    assert "already in Annie" in review[0]["note"], review[0]["note"]
    assert annie.counts(con)["review"] == 1
    annie.dismiss_intake(con, second["record_id"])
    assert annie.intake_review_rows(con) == []
    again = annie.ingest_file(con, "HS-7001-copy.txt", copy)[0]   # the file is free to be submitted again
    assert again["m1_status"] == annie.M1_DUP_REF, again        # and is checked again, not rejected as a duplicate file


def test_repeated_po_reference_goes_to_intake_review():
    annie, con, _ = fresh()
    raw = dict(doc_type="PO", po_reference="PR-2026-7777", vendor_name="Acme Office Supplies Pte Ltd", date="2026-10-01",
               cost_centre="CC-1", approver_name="A. Tan", approver_title="Manager", prepared_by="B. Lim",
               prepared_by_title="Executive", category="Goods", signature_present=True, total=50.0, currency="SGD",
               items=[dict(description="Stapler", qty=5, unit_price=10.0, total=50.0)], text_extracted=True)
    a = annie.route_record(con, annie.clean_record(raw, source_hash="file-a"), "UPLOAD", None)
    b = annie.route_record(con, annie.clean_record(raw, source_hash="file-b"), "UPLOAD", None)
    assert a["route"] == annie.R_M2 and a["m2"]["outcome"] == "REGISTERED", a
    assert b["route"] == annie.R_REVIEW and b["m1_status"] == annie.M1_DUP_REF, b


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"pass  {name}")
        except Exception as exc:   # report every failure, not just the first
            failed += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
