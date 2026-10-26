# Physical-device test plan (pre-launch)

Emulator and unit evidence never substitute for these runs (master QA `device_validation_required`). Record each run in
`qa/Release_QA_Traceability.csv` (`status`, `evidence_url`) with device, OS version, build number, date and tester.

## Devices

Fill in the phones available for testing. Minimum coverage before launch:

| Slot | Target | Why |
|---|---|---|
| A1 | Recent Android flagship (Android 15/16) | Baseline capture, Bluetooth, foreground service |
| A2 | Mid/low-tier Android with aggressive battery management (e.g. Xiaomi/Oppo/Vivo/Samsung) | Background kill, Doze, OEM restrictions |
| A3 | Android 10–12 device (minSdk 29) | Older audio routing APIs (`communicationDevice` is API 31+) |
| I1 | iPhone on iOS 17 | Deployment target |
| I2 | iPhone on the latest iOS | Current OS behaviour |
| BT | Two Bluetooth earbuds/headsets (one with in-ear detection), one wired headset | Private-voice route safety |

iOS needs a Mac with Xcode, an Apple Developer account and `xcodegen generate` (see README). Android builds install with
`adb install app-debug.apk` or as an internal-testing track build.

## Setup

1. Backend reachable from the phones over HTTPS (staging) or the LAN dev server (`-Pmeetsaathi.apiBaseUrl=http://<lan-ip>:8080` for Android debug; `MS_API_BASE_URL` for iOS Debug).
2. Without AWS credentials, speech and AI providers are unavailable: capture, upload, End, recovery, notes, sharing, export and
   deletion can be tested; transcription, insights, recaps and Ask cannot. Mark those rows **Blocked (no provider)**, not failed or passed.
3. Use a dedicated test account per device. Never use real participants' conversations without their consent.

## Runs

Each run lists the master QA ids it provides evidence for.

### R1 First run and permissions (all devices) — UNI-001, CON-001, LC-001
- Fresh install → Welcome → Sample (no mic prompt) → create account → Home. Confirm no microphone prompt until preflight.
- Deny microphone at preflight → Notes-only remains possible; "Enable microphone" explains why. Grant later via Settings → returns correctly.

### R2 Capture truth and long session (A1, A2, I1) — UNI-003/004, CON-008/080, LC-003
- 90-minute Meeting session, screen off / phone in pocket for ≥30 minutes, app backgrounded. Header shows "Recording" only while
  buffers flow; OS mic indicator matches; notification is neutral (no conversation content on the lock screen).
- Measure battery drain per hour and storage per hour; confirm no capture gaps except reported ones.

### R3 Interruptions — UNI-025, CON-072/075, INT-090
- Incoming phone call, alarm, Siri/Assistant, another app taking the mic, airplane mode for 5 minutes, low storage.
  Expect a truthful "interrupted" state, visible gap, no silent resume, and full upload after reconnect.
- Force-stop / swipe away during capture → relaunch: session marked interrupted, spooled audio uploads, mic does **not** restart.

### R4 End and offline recovery — UNI-004, MTG-022
- End while offline → kill app → relaunch offline → reconnect: End syncs with the exact saved body, finalization starts once.

### R5 Private voice route safety (BT devices) — UNI-009, CON-046/047/048, INT-051/084, MTG-044, LC-022
- Without verification nothing plays. Verify with the test sample → disconnect earbuds mid-sentence → audio stops immediately,
  never falls back to the loudspeaker; header shows "Private voice paused".
- Headset as microphone: the coupled-route warning appears.

### R6 Consent withdrawal — MTG-043, CON-013
- During capture: Session options → Stop and withdraw consent. Mic indicator off within 1 s, recap opens, no further uploads
  (check backend ingest logs), local spool removed. Repeat in airplane mode: withdrawal stays pending, nothing uploads, then completes when online.

### R7 Post-session journeys (requires providers for transcript content) — MTG-049/052/053, UNI-024, CON-061
- Recap → Sources & details → evidence plays only the cited span through the phone speaker or earbuds; playback is refused while
  another session is recording.
- Decision status change and owner confirmation; share preview → link → open on a second phone's browser → revoke → link shows
  "isn't available". Export (You and per-session) saves a JSON file via the system dialog.

### R8 Accessibility — UNI-020, accessibility category
- TalkBack / VoiceOver full pass of Home → Preflight → Live → Recap → Memory detail → Share: every control has a name, selection
  state is announced, live insight is announced politely, nothing relies on colour alone.
- Largest system font size and display size: no clipped text or overlapping controls; Pause/End stay reachable.
- Light and dark themes; reduced motion.

### R9 Localization readiness
- English only at launch. Change device region to India and US: dates and times render in the device time zone and locale
  (server timestamps are UTC). Pseudo-locale (Android `en-XA`) shows no hard-coded strings.

## Exit criteria

All P0 rows pass on at least one Android and one iOS device, with no open P0/P1 defects. Any row blocked by missing AWS/Apple
access stays **Blocked** with the reason, and launch sign-off records it explicitly.
