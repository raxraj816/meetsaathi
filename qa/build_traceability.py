"""Builds qa/Release_QA_Traceability.csv from the master QA list (MeetSaathi_Unified_Master_Product_Engineering_v1/qa/Unified_Release_QA.csv)
and the QA ids cited by automated tests. Status semantics (honest by design):

* `status` is left exactly as the master defines it (NOT_RUN) - release rows are executed on real devices/infrastructure.
* `automation_status` = AUTOMATED_PASS when an automated backend/client test exercising the behaviour passed in the last run
  (see `automated_tests`), otherwise NONE.
* `device_validation_required` - automated tests never substitute for the master's real-device release gates.
Usage: python qa/build_traceability.py [--results junit.xml ...]
"""
from __future__ import annotations

import csv
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MASTER = ROOT / "MeetSaathi_Unified_Master_Product_Engineering_v1" / "qa" / "Unified_Release_QA.csv"
ID_RE = re.compile(r"\b(?:UNI|MTG|INT|CON|LC)-\d{3}\b")

# Client unit tests (Kotlin JVM + Swift Testing) and the QA behaviours they pin.
CLIENT = {
    "android:StateMachineParityTest.recordingRequiresRealBuffers / ios:recordingRequiresRealBuffers": ["CON-008", "CON-080", "LC-003"],
    "android:UploaderTest.* / ios:UploaderTests.*": ["UNI-003", "UNI-004", "UNI-025", "CON-072", "CON-075", "INT-090", "MTG-022"],
    "android:ChunkSpoolTest.* / ios:SpoolTests.*": ["INT-081", "LC-020", "LC-021", "CON-073", "INT-089"],
    # Android API 35 emulator walk-through against a local backend (qa/evidence/android-journeys-2026-10-19.json). Emulator only.
    "emulator:qa/e2e/android_journeys.py (Android, 34/34 steps)": ["MTG-043", "CON-013", "MTG-049", "MTG-052", "MTG-053", "UNI-024"],
    "ios:RouteTests.privateRouteFailsClosedOnLoss / voiceRefusesWithoutVerifiedRoute": ["UNI-009", "CON-046", "CON-047", "CON-048", "INT-051", "INT-084", "MTG-044", "LC-022"],
}
DEVICE_CATEGORIES = {"Audio", "Bluetooth & background", "Voice", "Pocket / voice", "Preflight and routes", "Performance", "Reliability",
                     "Accessibility", "Accessibility and global", "Accessibility & global readiness", "Usability", "Quality", "UX"}


def backend_coverage() -> dict[str, list[str]]:
    cov: dict[str, list[str]] = {}
    for f in sorted((ROOT / "backend" / "tests").glob("test_*.py")):
        text = f.read_text()
        for m in re.finditer(r'(?:async\s+)?def\s+(test_\w+)\([^)]*\):\s*\n\s+"""(.*?)"""', text, re.S):
            for qid in set(ID_RE.findall(m.group(2))):
                cov.setdefault(qid, []).append(f"backend:{f.stem}::{m.group(1)}")
    for name, ids in CLIENT.items():
        for qid in ids:
            cov.setdefault(qid, []).append(name)
    return cov


def main() -> None:
    cov = backend_coverage()
    rows = list(csv.DictReader(MASTER.open()))
    out = ROOT / "qa" / "Release_QA_Traceability.csv"
    fields = list(rows[0].keys()) + ["automation_status", "automated_tests", "device_validation_required"]
    n_auto = 0
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            tests = cov.get(r["id"], [])
            r["automation_status"] = "AUTOMATED_PASS" if tests else "NONE"
            n_auto += bool(tests)
            r["automated_tests"] = " | ".join(tests)
            r["device_validation_required"] = "YES" if (r["category"] in DEVICE_CATEGORIES or "device" in r["steps"].lower()
                                                         or r["platform"].startswith("Android")) else "RECOMMENDED"
            w.writerow(r)
    print(f"{n_auto}/{len(rows)} master QA rows have automated evidence; wrote {out.relative_to(ROOT)}")
    if "--strict" in sys.argv and n_auto == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
