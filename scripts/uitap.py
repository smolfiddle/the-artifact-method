#!/usr/bin/env python3
"""Tiny adb UI driver for Android device testing (The Artifact Method).

Framework-agnostic: reads the accessibility tree via `uiautomator dump` and
taps by label or raw coordinates. Works with any app that exposes
accessibility labels (Flutter, Jetpack Compose, native Views, React Native);
falls back to coordinates for canvas-only apps.

Only dependency: python3 and `adb` on PATH.

Commands:
  dump-labels                       list visible labels with bounds
  find <label> [--exact] [--nth N]  print first match or None
  tap <label> [--exact] [--nth N]   tap center of first match
  tap <x> <y>                       raw coordinate tap
  wait <label> [--timeout S]        poll until a label appears
  wait-stable [--rounds N]          wait until the UI tree stops changing
  shot <name>                       screenshot to <name>.png
  text <string>                     type into the focused field (spaces ok)
  swipe <x1> <y1> <x2> <y2>         swipe gesture (optional --duration ms)

Global: -s/--serial <device> targets one device (also honors ANDROID_SERIAL).
Exit codes: 0 success, 1 miss/timeout, 2 usage.
"""
import argparse
import hashlib
import re
import subprocess
import sys
import time

ADB = "adb"


def adb_cmd(serial):
    return [ADB] + (["-s", serial] if serial else [])


def dump(serial):
    base = adb_cmd(serial)
    try:
        subprocess.run(
            base + ["shell", "uiautomator", "dump", "/sdcard/ui.xml"],
            capture_output=True,
            timeout=30,
        )
        out = subprocess.run(
            base + ["shell", "cat", "/sdcard/ui.xml"],
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout
        return out
    except subprocess.TimeoutExpired:
        return ""


def nodes(xml):
    for m in re.finditer(r"<node[^>]*>", xml):
        node = m.group(0)
        text = re.search(r'text="([^"]*)"', node)
        desc = re.search(r'content-desc="([^"]*)"', node)
        label = (text.group(1) if text else "") or (desc.group(1) if desc else "")
        label = label.replace("&#10;", " ").strip()
        bounds = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node)
        if bounds:
            x1, y1, x2, y2 = (int(g) for g in bounds.groups())
            yield label, (x1, y1, x2, y2)


def matches(xml, label, exact=False):
    found = []
    for text, bounds in nodes(xml):
        if (text == label) if exact else (label.lower() in text.lower()):
            found.append((text, bounds))
    return found


def find(serial, label, exact=False, nth=0):
    found = matches(dump(serial), label, exact=exact)
    if nth < 0 or nth >= len(found):
        return None
    return found[nth]


def tap_xy(serial, x, y):
    subprocess.run(adb_cmd(serial) + ["shell", "input", "tap", str(x), str(y)], check=True)
    time.sleep(0.6)


def tap_label(serial, label, exact=False, nth=0):
    hit = find(serial, label, exact=exact, nth=nth)
    if hit is None:
        print(f"MISS: no node matching {label!r} (exact={exact}, nth={nth})")
        return False
    text, (x1, y1, x2, y2) = hit
    tap_xy(serial, (x1 + x2) // 2, (y1 + y2) // 2)
    print(f"tap {label!r} -> {text!r} at ({(x1 + x2) // 2},{(y1 + y2) // 2})")
    return True


def wait_label(serial, label, timeout_s=20, exact=False, nth=0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        hit = find(serial, label, exact=exact, nth=nth)
        if hit:
            print(f"found {label!r} as {hit[0]!r}")
            return True
        time.sleep(1)
    print(f"TIMEOUT waiting for {label!r}")
    return False


def wait_stable(serial, rounds=3, interval=1.0, timeout_s=30):
    deadline = time.time() + timeout_s
    last_hash = None
    stable = 0
    while time.time() < deadline:
        xml = dump(serial)
        h = hashlib.sha1(xml.encode("utf-8", "ignore")).hexdigest()
        if h == last_hash:
            stable += 1
        else:
            stable = 1
            last_hash = h
        if stable >= rounds:
            print(f"stable after {stable} identical dumps")
            return True
        time.sleep(interval)
    print(f"TIMEOUT: UI never stabilized within {timeout_s}s")
    return False


def shot(serial, name):
    if not name.lower().endswith(".png"):
        name += ".png"
    with open(name, "wb") as fh:
        subprocess.run(
            adb_cmd(serial) + ["exec-out", "screencap", "-p"],
            stdout=fh,
            check=True,
        )
    print(f"saved {name}")
    return True


def send_text(serial, value):
    escaped = value.replace(" ", "%s")
    quoted = "'" + escaped.replace("'", "'\\''") + "'"
    subprocess.run(adb_cmd(serial) + ["shell", "input", "text", quoted], check=True)
    time.sleep(0.6)
    print(f"typed {value!r}")
    return True


def swipe(serial, x1, y1, x2, y2, duration_ms=300):
    subprocess.run(
        adb_cmd(serial)
        + ["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms)],
        check=True,
    )
    time.sleep(0.6)
    print(f"swiped ({x1},{y1}) -> ({x2},{y2}) in {duration_ms}ms")
    return True


def build_parser():
    p = argparse.ArgumentParser(prog="uitap.py", description=__doc__.splitlines()[0])
    p.add_argument("-s", "--serial", default=None, help="device serial (adb -s)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("dump-labels", help="list visible labels with bounds")

    f = sub.add_parser("find", help="print first match or None")
    f.add_argument("label")
    f.add_argument("--exact", action="store_true")
    f.add_argument("--nth", type=int, default=0)

    t = sub.add_parser("tap", help="tap a label or raw coordinates")
    t.add_argument("target", nargs="+")
    t.add_argument("--exact", action="store_true")
    t.add_argument("--nth", type=int, default=0)

    w = sub.add_parser("wait", help="poll until a label appears")
    w.add_argument("label")
    w.add_argument("--timeout", type=float, default=20)
    w.add_argument("--exact", action="store_true")
    w.add_argument("--nth", type=int, default=0)

    ws = sub.add_parser("wait-stable", help="wait until the UI tree stops changing")
    ws.add_argument("--rounds", type=int, default=3)
    ws.add_argument("--interval", type=float, default=1.0)
    ws.add_argument("--timeout", type=float, default=30)

    sh = sub.add_parser("shot", help="screenshot to <name>.png")
    sh.add_argument("name")

    tx = sub.add_parser("text", help="type into the focused field")
    tx.add_argument("value", nargs="+")

    sw = sub.add_parser("swipe", help="swipe gesture")
    sw.add_argument("coords", nargs=4, type=int)
    sw.add_argument("--duration", type=int, default=300)

    return p


def main():
    args = build_parser().parse_args()
    if args.cmd == "dump-labels":
        for text, bounds in nodes(dump(args.serial)):
            if text:
                print(f"{text!r} {bounds}")
        return 0
    if args.cmd == "find":
        print(find(args.serial, args.label, exact=args.exact, nth=args.nth))
        return 0
    if args.cmd == "tap":
        target = args.target
        if len(target) == 2 and all(t.lstrip("-").isdigit() for t in target):
            tap_xy(args.serial, int(target[0]), int(target[1]))
            return 0
        ok = tap_label(args.serial, " ".join(target), exact=args.exact, nth=args.nth)
        return 0 if ok else 1
    if args.cmd == "wait":
        ok = wait_label(
            args.serial, args.label, timeout_s=args.timeout, exact=args.exact, nth=args.nth
        )
        return 0 if ok else 1
    if args.cmd == "wait-stable":
        ok = wait_stable(args.serial, rounds=args.rounds, interval=args.interval, timeout_s=args.timeout)
        return 0 if ok else 1
    if args.cmd == "shot":
        return 0 if shot(args.serial, args.name) else 1
    if args.cmd == "text":
        return 0 if send_text(args.serial, " ".join(args.value)) else 1
    if args.cmd == "swipe":
        x1, y1, x2, y2 = args.coords
        return 0 if swipe(args.serial, x1, y1, x2, y2, args.duration) else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
