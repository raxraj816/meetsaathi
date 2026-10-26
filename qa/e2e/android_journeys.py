"""Emulator walk-through of the post-session and privacy journeys against a LOCAL dev backend seeded by seed_journeys.py.

Checks visible UI text (not pixels) at each step, saves screenshots, and verifies server-side effects through the API.
It is evidence for the emulator only: no physical device, real speech provider, Bluetooth or store build is covered.

  ANDROID_HOME=... SHOTS=<dir> python3 qa/e2e/android_journeys.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import adbui as ui  # noqa: E402

ACC = json.loads((Path(__file__).parent / ".local-account.json").read_text())
API = "http://localhost:8080"
PKG = "app.meetsaathi"
results: list[dict] = []


def step(name, ok, detail=""):
    results.append({"step": name, "pass": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""), flush=True)
    if not ok:
        ui.shot("fail-" + name.replace(" ", "_"))


def visible(*needles, timeout=12):
    end = time.time() + timeout
    while time.time() < end:
        t = "\n".join(ui.texts())
        if all(n.lower() in t.lower() for n in needles):
            return True
        time.sleep(0.8)
    return False


def scroll_find(text, tries=8):
    for _ in range(tries):
        if ui.find(text, timeout=2) is not None:
            return True
        ui.sh("shell", "input", "swipe", "540", "1600", "540", "800", "300")
    return False


def scroll_top():
    for _ in range(6):
        ui.sh("shell", "input", "swipe", "540", "700", "540", "1700", "200")


def tap_last(text):
    """Tap the last exact match (e.g. a button that repeats the screen title)."""
    ns = [n for n in ui.nodes(ui.dump()) if (n.get("text") or "").strip() == text]
    if not ns:
        raise SystemExit(f"NOT FOUND: {text}")
    ui.tap_node(ns[-1])


def api(method, path, body=None, token=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def login_token():
    _, body = api("POST", "/v1/auth/login", {"email": ACC["email"], "password": ACC["password"], "device": {"platform": "TEST", "name": "verifier"}})
    return json.loads(body)["access_token"]


def main():
    ui.sh("shell", "pm", "clear", PKG)
    ui.sh("shell", "pm", "grant", PKG, "android.permission.RECORD_AUDIO")
    ui.sh("shell", "am", "start", "-n", f"{PKG}/.MainActivity")
    step("welcome shows promise", visible("Be present. Understand more."))
    ui.tap("Get started")
    ui.tap("I have an account")
    ui.type_into("Email", ACC["email"])
    ui.type_into("Password (10+ characters)", ACC["password"])
    ui.sh("shell", "input", "keyevent", "111")
    time.sleep(1.5)  # let the keyboard close so the button is where the dump says it is
    for _ in range(3):
        if ui.find("Ready when you are.", timeout=1) is not None:
            break
        if ui.find("Sign in", exact=True, timeout=2) is not None:
            tap_last("Sign in")
        if visible("Ready when you are.", timeout=8):
            break
    step("signed in to Home", visible("Ready when you are.", "Architecture review", timeout=20))

    # Recap -> memory detail (decision)
    ui.tap("Architecture review")
    step("recap outcomes first", visible("Decisions", "Use per-customer partition keys", "Actions"))
    ui.shot("01-recap")
    ui.tap("Sources & details")
    step("memory detail shows sources", visible("Where this came from", "Decision status", "From conversation"))
    ui.shot("02-memory-decision")
    play = next((t for t in ui.texts() if t.startswith("▶ Play")), None)
    step("evidence play control present", play is not None, play or "")
    if play:
        ui.tap(play, exact=True, scroll=False)
        time.sleep(2)
        t = "\n".join(ui.texts())
        step("evidence plays or finishes without error", "couldn't be played" not in t and "No audio is available" not in t)
    status = next((s for s in ("Discussed", "Accepted", "Deferred") if ui.find(s, exact=True, timeout=2) is not None), None)
    if status:
        ui.tap(status, exact=True)
        step("decision status changed", visible("Decision status updated.", timeout=8) or visible("History", status), status)
    else:
        step("decision status chips present", False)
    ui.shot("03-decision-updated")
    ui.sh("shell", "input", "keyevent", "4")

    # Owner confirmation
    scroll_find("Benchmark regional failover")
    nodes = [n for n in ui.nodes(ui.dump()) if (n.get("text") or "") == "Sources & details"]
    ui.tap_node(nodes[-1]) if nodes else None
    step("action detail shows owner card", visible("Owner", "Confirm owner"))
    ui.type_into("Who owns this?", "Alex")
    ui.tap("Confirm owner")
    step("owner confirmed", visible("Owner confirmed.", timeout=8) or visible("Clear owner"))
    ui.shot("04-owner-confirmed")
    ui.sh("shell", "input", "keyevent", "4")

    # Share: preview -> link -> page -> revoke
    scroll_find("Share recap")
    ui.tap("Share recap")
    ui.tap("Preview what they'll see")
    step("share preview before link", visible("exactly what recipients see") and not visible("Link ready", timeout=2))
    ui.shot("05-share-preview")
    scroll_find("Create link")
    ui.tap("Create link")
    step("share link created", visible("Link ready", timeout=10))
    url = ""
    for _ in range(6):
        url = next((t for t in ui.texts() if "/s/" in t), "")
        if url:
            break
        ui.sh("shell", "input", "swipe", "540", "1600", "540", "900", "300")
    path = url[url.find("/s/"):] if "/s/" in url else ""
    code, page = api("GET", path) if path else (0, "")
    step("recipient page renders (no audio, no script)", code == 200 and "<script" not in page.lower() and "Architecture review" in page, f"HTTP {code}")
    ui.shot("06-share-link")
    scroll_find("Revoke link")
    ui.tap("Revoke link")
    time.sleep(2)
    code2, _ = api("GET", path) if path else (0, "")
    step("revoked link no longer opens", code2 == 404, f"HTTP {code2}")
    ui.sh("shell", "input", "keyevent", "4")

    # Transcript with evidence
    scroll_top()
    scroll_find("Transcript")
    ui.tap("Transcript", exact=True)
    step("transcript shows lines with play controls", visible("Transcript & sources", "per-customer partition keys") and
         any(t.startswith("▶ Play") for t in ui.texts()))
    ui.shot("07-transcript")
    ui.sh("shell", "input", "keyevent", "4")

    # Keep the decision
    scroll_top()
    ui.tap("Use per-customer partition keys")
    scroll_find("Keep 1 selected")
    ui.tap("Keep 1 selected")
    step("review saved, back home", visible("Ready when you are.", timeout=10))

    # Memories -> projects -> brief + ledger
    ui.tap("Memories", exact=True)
    step("kept memory listed", visible("Use per-customer partition keys", timeout=10))
    ui.tap("Projects & courses")
    ui.tap("Payments platform")
    step("project screen", visible("Payments platform", "Prepare a brief"))
    ui.tap("Prepare a brief")
    step("brief built from kept items", visible("Last agreed", timeout=10) or visible("Still open", timeout=2))
    scroll_find("Decision ledger")
    step("decision ledger lists decision", visible("Decision ledger", "Use per-customer partition keys"))
    ui.shot("08-project-brief")

    # Preferences -> preflight honours defaults but still asks consent
    for _ in range(4):
        if ui.find("You", exact=True, timeout=2) is not None:
            break
        ui.sh("shell", "input", "keyevent", "4")
    ui.tap("You", exact=True)
    ui.tap("Ask only")
    step("default saved", visible("Default saved.", timeout=8))
    ui.tap("Home", exact=True)
    ui.tap("Start Companion")
    ui.tap("Continue")
    step("preflight keeps consent gate despite default", scroll_find("Allow AI assistance first, or choose Listen quietly."))
    ui.shot("09-preflight-defaults")

    # Live: consent withdrawal stops capture and purges local spool
    scroll_top()
    scroll_find("Check audio (3 s)")
    ui.tap("Check audio (3 s)")
    time.sleep(5)
    if ui.find("Allow", exact=True, timeout=2) is not None:
        ui.tap("Allow", exact=True)
    scroll_find("I have permission to record")
    ui.tap("I have permission to record")
    scroll_find("Listen quietly")
    ui.tap("Listen quietly")
    scroll_find("Start session")
    ui.tap("Start session", exact=True)
    step("live session started", visible("Architecture", timeout=4) or visible("End", "Pause", timeout=15))
    time.sleep(4)
    ui.shot("10-live")
    scroll_find("Add a note")
    ui.tap("Add a note")
    ui.type_into("What would you like to remember?", "Check failover owner")
    scroll_find("Save note")
    tap_last("Save note")
    step("timed note saved during recording", visible("Note saved.", timeout=8))
    scroll_find("Session options")
    ui.tap("Session options")
    scroll_find("Stop and withdraw consent")
    ui.tap("Stop and withdraw consent")
    ui.tap("Stop recording", exact=True)
    step("withdrawal lands on recap", visible("Session finished", timeout=15))
    step("note appears in recap with its moment", scroll_find("Check failover owner"))
    ui.shot("11-withdrawn")
    tok = login_token()
    _, sessions = api("GET", "/v1/sessions?limit=1", token=tok)
    latest = json.loads(sessions)["items"][0]
    step("server stopped the session", latest["state"] in ("STOPPING", "FINALIZING", "COMPLETED", "COMPLETED_PARTIAL"), latest["state"])
    spool = subprocess.run([ui.ADB, "shell", "run-as", PKG, "ls", "no_backup/spool"], capture_output=True, text=True).stdout
    step("local spool purged for withdrawn session", latest["session_id"] not in spool, spool.strip() or "(empty)")
    fg = ui.sh("shell", "dumpsys", "activity", "services", PKG, check=False)
    step("microphone service not running", "CaptureService" not in fg)

    # CC-014: stop recording but keep writing own notes; capture ends before note input
    for _ in range(4):
        if ui.find("Home", exact=True, timeout=2) is not None:
            break
        ui.sh("shell", "input", "keyevent", "4")
    ui.tap("Home", exact=True)
    scroll_top()
    ui.tap("Start Companion")
    ui.tap("Continue")
    scroll_find("Check audio (3 s)")
    ui.tap("Check audio (3 s)")
    time.sleep(5)
    scroll_find("I have permission to record")
    ui.tap("I have permission to record")
    scroll_find("Listen quietly")
    ui.tap("Listen quietly")
    scroll_find("Start session")
    ui.tap("Start session", exact=True)
    step("second live session started", visible("End", "Pause", timeout=15))
    time.sleep(3)
    scroll_find("Session options")
    ui.tap("Session options")
    scroll_find("Stop recording, keep taking notes")
    ui.tap("Stop recording, keep taking notes")
    time.sleep(2)
    scroll_top()
    step("capture stops before note input", visible("Recording stopped. Anything you add now", timeout=10))
    fg2 = ui.sh("shell", "dumpsys", "activity", "services", PKG, check=False)
    step("microphone service stopped before notes", "CaptureService" not in fg2)
    ui.type_into("What would you like to remember?", "Follow up on retry budget")
    tap_last("Save note")
    step("post-stop note saved", visible("Note saved.", timeout=8))
    ui.tap("Finish & review")
    step("finish opens recap", visible("Session finished", timeout=15))
    step("post-stop note in recap", scroll_find("Follow up on retry budget"))
    ui.shot("12-stop-keep-notes")

    Path(ui.OUT, "android-journeys.json").write_text(json.dumps(results, indent=2))
    failed = [r for r in results if not r["pass"]]
    print(f"\n{len(results) - len(failed)}/{len(results)} steps passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
