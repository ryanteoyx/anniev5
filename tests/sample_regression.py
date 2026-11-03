"""Sample-set regression check.

Loads the 21 sample documents into an empty, temporary Annie and compares what happens (routing, matching
outcome, final case and PO/PR states, waiting reasons) with the snapshot in expected_samples.json.

    python tests/sample_regression.py            # compare; exit code 1 if anything differs
    python tests/sample_regression.py --update   # accept the current behaviour as the new snapshot

Run it after any change to annie_core.py. A difference is not automatically wrong, but it must be intended.
"""
import json
import sys
from pathlib import Path

from harness import fresh, load_samples

SNAPSHOT = Path(__file__).with_name("expected_samples.json")


def observe() -> dict:
    annie, con, _ = fresh()
    results = load_samples(annie, con)
    intake = {}
    for name, rs in results.items():
        r = rs[0]
        m2 = r.get("m2") or {}
        intake[name] = dict(route=r.get("route"), m1_status=r.get("m1_status"),
                            outcome=m2.get("outcome"), doc_type=m2.get("doc_type"))
    statuses = [annie.S_OPEN_PO, annie.S_GR, annie.S_DONE, annie.S_ARCHIVED, annie.S_CALLOFF]
    cases = {c["case_id"]: dict(status=c["status"], invoice=c["invoice_reference"], po=c["po_references"],
                                score=c["link_score"], reason=c["reason"])
             for c in annie.case_rows(con, statuses)}
    pos = {p["po_reference"]: dict(status=p["status"], billed=p["billed"], open=p["open_to_bill"])
           for p in annie.po_rows(con)}
    return dict(intake=intake, cases=cases, po_positions=pos, counts=annie.counts(con))


def diff(old, new, path=""):
    out = []
    if isinstance(old, dict) and isinstance(new, dict):
        for k in sorted(set(old) | set(new)):
            if k not in old:
                out.append(f"+ {path}{k}: {new[k]}")
            elif k not in new:
                out.append(f"- {path}{k}: {old[k]}")
            else:
                out += diff(old[k], new[k], f"{path}{k}.")
    elif old != new:
        out.append(f"~ {path[:-1]}: {old!r} -> {new!r}")
    return out


def main():
    now = observe()
    if "--update" in sys.argv or not SNAPSHOT.exists():
        SNAPSHOT.write_text(json.dumps(now, indent=2, sort_keys=True) + "\n")
        print(f"snapshot written: {SNAPSHOT.name} ({len(now['intake'])} documents, {len(now['cases'])} cases)")
        return 0
    changes = diff(json.loads(SNAPSHOT.read_text()), now)
    if changes:
        print(f"{len(changes)} difference(s) from the snapshot:")
        print("\n".join(changes))
        return 1
    print(f"OK: {len(now['intake'])} documents, {len(now['cases'])} cases, {len(now['po_positions'])} PO/PR positions "
          "match the snapshot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
