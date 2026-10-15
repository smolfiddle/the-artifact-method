#!/usr/bin/env python3
"""Tiny adb UI driver: tap/wait by visible label via uiautomator dump."""
import re
import subprocess
import sys
import time

ADB = "adb"


def dump():
    subprocess.run(
        [ADB, "shell", "uiautomator", "dump", "/sdcard/ui.xml"],
        capture_output=True,
    )
    out = subprocess.run(
        [ADB, "shell", "cat", "/sdcard/ui.xml"],
        capture_output=True,
        text=True,
    ).stdout
    return out


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


def find(label):
    for text, (x1, y1, x2, y2) in nodes(dump()):
        if label.lower() in text.lower():
            return ((x1 + x2) // 2, (y1 + y2) // 2, text)
    return None


def tap_label(label):
    hit = find(label)
    if hit is None:
        print(f"MISS: no node matching {label!r}")
        return False
    x, y, text = hit
    subprocess.run([ADB, "shell", "input", "tap", str(x), str(y)], check=True)
    print(f"tap {label!r} -> {text!r} at ({x},{y})")
    time.sleep(0.6)
    return True


def wait_label(label, timeout_s=20):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        hit = find(label)
        if hit:
            print(f"found {label!r} as {hit[2]!r}")
            return True
        time.sleep(1)
    print(f"TIMEOUT waiting for {label!r}")
    return False


def tap_xy(x, y):
    subprocess.run([ADB, "shell", "input", "tap", str(x), str(y)], check=True)
    time.sleep(0.6)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "tap":
        args = sys.argv[2:]
        if len(args) == 1:
            ok = tap_label(args[0])
        else:
            tap_xy(int(args[0]), int(args[1]))
            ok = True
        sys.exit(0 if ok else 1)
    if cmd == "wait":
        ok = wait_label(sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 20)
        sys.exit(0 if ok else 1)
    if cmd == "find":
        print(find(sys.argv[2]))
        sys.exit(0)
    if cmd == "dump-labels":
        for text, bounds in nodes(dump()):
            if text:
                print(f"{text!r} {bounds}")
        sys.exit(0)
    print("usage: uitap.py tap <label|x y> | wait <label> [timeout] | find <label> | dump-labels")
    sys.exit(2)
