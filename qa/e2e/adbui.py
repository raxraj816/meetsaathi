"""Tiny adb UI driver: dump the accessibility tree, tap by visible text, type text, screenshot."""
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

SDK = os.environ["ANDROID_HOME"]
ADB = f"{SDK}/platform-tools/adb"
OUT = os.environ.get("SHOTS", "/tmp")


def sh(*args, check=True):
    return subprocess.run([ADB, *args], capture_output=True, text=True, check=check).stdout


def dump():
    sh("shell", "uiautomator", "dump", "/sdcard/ui.xml", check=False)
    xml = sh("shell", "cat", "/sdcard/ui.xml", check=False)
    try:
        return ET.fromstring(xml[xml.find("<?xml"):] if "<?xml" in xml else xml)
    except ET.ParseError:
        return None


def nodes(root):
    return [] if root is None else list(root.iter("node"))


def find(text, exact=False, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        for n in nodes(dump()):
            t = (n.get("text") or "") + " " + (n.get("content-desc") or "")
            if (t.strip() == text) if exact else (text.lower() in t.lower()):
                return n
        time.sleep(0.8)
    return None


def center(n):
    x1, y1, x2, y2 = map(int, re.findall(r"\d+", n.get("bounds")))
    return (x1 + x2) // 2, (y1 + y2) // 2


def tap_node(n):
    x, y = center(n)
    sh("shell", "input", "tap", str(x), str(y))
    time.sleep(1.0)


def tap(text, exact=False, timeout=15, scroll=True):
    n = find(text, exact, timeout=timeout if not scroll else 3)
    tries = 0
    while n is None and scroll and tries < 6:
        sh("shell", "input", "swipe", "540", "1700", "540", "700", "300")
        time.sleep(0.8)
        n = find(text, exact, timeout=2)
        tries += 1
    if n is None:
        raise SystemExit(f"NOT FOUND: {text}")
    # clickable ancestor not needed for Compose; tapping the text centre hits the button
    tap_node(n)
    return n


def type_into(label, value):
    n = tap(label)
    sh("shell", "input", "text", value.replace(" ", "%s"))
    time.sleep(0.5)
    sh("shell", "input", "keyevent", "111")  # escape / hide keyboard
    time.sleep(0.5)


def shot(name):
    path = os.path.join(OUT, f"{name}.png")
    with open(path, "wb") as f:
        f.write(subprocess.run([ADB, "exec-out", "screencap", "-p"], capture_output=True, check=True).stdout)
    print("shot", path)


def texts():
    return [((n.get("text") or n.get("content-desc") or "").strip()) for n in nodes(dump()) if (n.get("text") or n.get("content-desc"))]


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "texts":
        print("\n".join(t for t in texts() if t))
    elif cmd == "tap":
        tap(sys.argv[2])
    elif cmd == "shot":
        shot(sys.argv[2])
