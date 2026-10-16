#!/usr/bin/env python3
"""uitap.py: adb UI driver for Android device testing (The Artifact Method).

Framework-agnostic. Reads the accessibility tree via `uiautomator dump` and
acts on it. Works with any app that exposes accessibility labels (Flutter,
Jetpack Compose, native Views, React Native); falls back to raw coordinates
for canvas-only apps. Single file. Only dependency: python3 and `adb`.

Selectors (used by find, tap, wait, wait-gone, scroll-to):
  <label>                substring match on text or content-desc (case-insensitive)
  --exact                whole match
  --regex                treat label or --id as a regular expression
  --case-sensitive       stop folding case
  --id <resource-id>     match by resource id instead of a label
  --package <pkg>        restrict to nodes from one package
  --nth N                pick the Nth match in document order (0-based)
  --topmost --bottommost --leftmost --rightmost   pick by position
  --timeout S            (wait, wait-gone) seconds, default 20
  --interval S           polling interval, default 1.0 (wait-stable: 1.0)

Commands:
  dump-labels [selector] [--json]        list matching nodes
  find <selector args>                   print first match, exit 1 on miss
  tap <selector args> | tap X Y | tap --xy X Y
      [--retry N] [--retry-delay S] [--dry-run]
      [--expect L [--expect-exact | --expect-regex]] [--expect-timeout S]
  wait <selector args>                   poll until a match exists
  wait-gone <selector args>              poll until no match exists
  wait-stable [--rounds N] [--save FILE] hash a normalized tree signature
  scroll-to <selector args> [--direction up|down|left|right] [--max N]
                                         [--no-hide-ime]
  text [--into LABEL] [--clear] [--no-settle] <value>  type into focus;
                                         --into taps first and waits briefly
                                         for the screen to settle (the first
                                         keystroke can be swallowed during a
                                         focus change; --no-settle skips it).
                                         %s is the space token; literal %s in
                                         input is typed by segmenting
  clear [--length N]                     clear the focused text field
  key <NAME|CODE>                        HOME, BACK, ENTER, TAB, ESCAPE,
                                         DEL, MOVE_END, DPAD_UP, ... or a number
  swipe up|down|left|right [--distance P] [--duration MS] [--no-hide-ime]
  swipe X1 Y1 X2 Y2 [--duration MS]
  shot <name>                            screenshot to <name>.png
  screen                                 physical size and density
  selftest                               internal checks, no device needed
  version                                print the tool version

Global options go before the command: -s SERIAL, --verbose, --log FILE,
--json (find and dump-labels).

Exit codes: 0 hit/success, 1 miss/timeout, 2 usage or device error.
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import namedtuple

VERSION = "0.2.2"
ADB = os.environ.get("ADB", "adb")

Node = namedtuple(
    "Node", "text desc rid klass package clickable enabled focusable bounds"
)


class AdbError(Exception):
    pass


# Device-level failures that polling verbs must not swallow as "not yet".
FATAL_ADB_HINTS = ("offline", "not found", "unauthorized", "no devices")


class Logger:
    def __init__(self, path):
        self.path = path

    def write(self, line):
        if not self.path:
            return
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(f"{stamp} {line}\n")
        except OSError:
            pass


def resolve_serial(explicit, log=None):
    if explicit:
        return explicit
    env = os.environ.get("ANDROID_SERIAL")
    if env:
        return env
    try:
        cp = subprocess.run(
            [ADB, "devices"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise AdbError(f"cannot run {ADB}: {exc}")
    serials = []
    for line in cp.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            serials.append(parts[0])
    if not serials:
        raise AdbError("no devices or emulators found; start one or connect a device")
    if len(serials) > 1:
        listing = ", ".join(serials)
        raise AdbError(f"multiple devices attached ({listing}); pick one with -s SERIAL")
    return None


def adb_cmd(serial):
    return [ADB] + (["-s", serial] if serial else [])


def adb(serial, argv, timeout=30, check=True):
    try:
        cp = subprocess.run(
            adb_cmd(serial) + argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise AdbError(f"adb {' '.join(argv)} timed out after {timeout}s")
    except FileNotFoundError:
        raise AdbError(f"adb not found (set the ADB env var if it is not on PATH)")
    if check and cp.returncode != 0:
        detail = (cp.stderr or cp.stdout or "").strip().splitlines()
        raise AdbError(detail[-1] if detail else f"adb {' '.join(argv)} failed")
    return cp


def dump(serial):
    """Return (ok, xml, reason). Never returns a stale tree."""
    adb(serial, ["shell", "rm", "-f", "/sdcard/ui.xml"], check=False)
    cp = adb(serial, ["shell", "uiautomator", "dump", "/sdcard/ui.xml"], check=False)
    out = (cp.stdout or "") + (cp.stderr or "")
    if "dumped to" not in out:
        first = out.strip().splitlines()
        reason = first[0] if first else "uiautomator dump failed"
        reason = reason.removeprefix("ERROR: ").strip()
        return False, "", reason
    cat = adb(serial, ["shell", "cat", "/sdcard/ui.xml"], check=False)
    xml = cat.stdout or ""
    if not xml.strip():
        return False, "", "dump produced no tree (device offline or screen locked?)"
    return True, xml, ""


def parse_tree(xml):
    """Parse uiautomator XML into (nodes, parent_map). Entity-safe via ET."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise AdbError(f"cannot parse UI tree: {exc}")
    parent = {}
    nodes = []
    for elem in root.iter():
        for child in elem:
            parent[child] = elem
        if elem.tag == "node":
            a = elem.attrib
            m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", a.get("bounds", ""))
            if not m:
                continue
            nodes.append(
                (
                    elem,
                    Node(
                        text=" ".join(a.get("text", "").split()),
                        desc=" ".join(a.get("content-desc", "").split()),
                        rid=a.get("resource-id", ""),
                        klass=a.get("class", ""),
                        package=a.get("package", ""),
                        clickable=a.get("clickable") == "true",
                        enabled=a.get("enabled") == "true",
                        focusable=a.get("focusable") == "true",
                        bounds=tuple(int(g) for g in m.groups()),
                    ),
                )
            )
    return nodes, parent


def node_json(n):
    x1, y1, x2, y2 = n.bounds
    return {
        "text": n.text,
        "desc": n.desc,
        "id": n.rid,
        "class": n.klass,
        "package": n.package,
        "clickable": n.clickable,
        "enabled": n.enabled,
        "focusable": n.focusable,
        "bounds": [x1, y1, x2, y2],
        "center": [(x1 + x2) // 2, (y1 + y2) // 2],
    }


def node_line(n):
    x1, y1, x2, y2 = n.bounds
    return (
        f"text={n.text!r} desc={n.desc!r} id={n.rid!r} class={n.klass!r} "
        f"bounds=[{x1},{y1},{x2},{y2}] clickable={int(n.clickable)} "
        f"enabled={int(n.enabled)} pkg={n.package!r}"
    )


class Selector:
    def __init__(self, args):
        self.label = getattr(args, "label", None)
        self.rid = getattr(args, "id", None)
        self.exact = getattr(args, "exact", False)
        self.regex = getattr(args, "regex", False)
        self.case_sensitive = getattr(args, "case_sensitive", False)
        self.package = getattr(args, "package", None)
        self.nth = getattr(args, "nth", 0)
        self.topmost = getattr(args, "topmost", False)
        self.bottommost = getattr(args, "bottommost", False)
        self.leftmost = getattr(args, "leftmost", False)
        self.rightmost = getattr(args, "rightmost", False)

    def _label_hit(self, value):
        if not value:
            return False
        if self.regex:
            flags = 0 if self.case_sensitive else re.IGNORECASE
            try:
                return re.search(self.label, value, flags) is not None
            except re.error as exc:
                raise AdbError(f"bad regex: {exc}")
        if self.exact:
            return value == self.label if self.case_sensitive else value.lower() == self.label.lower()
        if self.case_sensitive:
            return self.label in value
        return self.label.lower() in value.lower()

    def _id_hit(self, value):
        if self.regex:
            flags = 0 if self.case_sensitive else re.IGNORECASE
            try:
                return re.search(self.rid, value, flags) is not None
            except re.error as exc:
                raise AdbError(f"bad regex: {exc}")
        return value == self.rid

    def match(self, n):
        if self.package and n.package != self.package:
            return False
        if self.rid is None and self.label is None:
            return True
        if self.rid is not None:
            return bool(n.rid) and self._id_hit(n.rid)
        return self._label_hit(n.text) or self._label_hit(n.desc)

    def describe(self):
        if self.rid is not None:
            kind = "id-regex" if self.regex else "id"
            return f"{kind} {self.rid!r}"
        kind = "regex" if self.regex else ("exact" if self.exact else "substring")
        return f"{kind} {self.label!r}"

    def apply_order(self, hits):
        if self.topmost:
            hits.sort(key=lambda p: (p[1].bounds[1], p[1].bounds[0]))
        elif self.bottommost:
            hits.sort(key=lambda p: (-p[1].bounds[3], p[1].bounds[0]))
        elif self.leftmost:
            hits.sort(key=lambda p: (p[1].bounds[0], p[1].bounds[1]))
        elif self.rightmost:
            hits.sort(key=lambda p: (-p[1].bounds[2], p[1].bounds[1]))
        return hits


def selector_namespace(**overrides):
    ns = argparse.Namespace(
        label=None, id=None, exact=False, regex=False, case_sensitive=False,
        package=None, nth=0, topmost=False, bottommost=False, leftmost=False,
        rightmost=False,
    )
    for key, value in overrides.items():
        setattr(ns, key, value)
    return ns


def selector_env(serial, selector, verbose=False):
    ok, xml, reason = dump(serial)
    if not ok:
        raise AdbError(reason)
    nodes, parent = parse_tree(xml)
    hits = selector.apply_order(
        [(e, n) for e, n in nodes if selector.match(n)]
    )
    if verbose and not hits:
        print(f"no match for {selector.describe()}; {len(nodes)} nodes scanned", file=sys.stderr)
        shown = [n for _, n in nodes if n.text or n.desc or n.rid][:5]
        for n in shown:
            print(f"  candidate: {node_line(n)}", file=sys.stderr)
    return nodes, parent, hits


def clicked_elem(elem, parent, node):
    """Climb to the nearest clickable ancestor for a reliable tap target."""
    cur = elem
    for _ in range(6):
        if cur.attrib.get("clickable") == "true":
            break
        nxt = parent.get(cur)
        if nxt is None or nxt.tag != "node":
            break
        cur = nxt
    a = cur.attrib
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", a.get("bounds", ""))
    if not m:
        return node.bounds
    return tuple(int(g) for g in m.groups())


def tap_center(serial, bounds):
    x1, y1, x2, y2 = bounds
    adb(serial, ["shell", "input", "tap", str((x1 + x2) // 2), str((y1 + y2) // 2)])
    time.sleep(0.6)
    return (x1 + x2) // 2, (y1 + y2) // 2


def wait_match(serial, selector, timeout, interval, want_gone=False, verbose=False):
    """Return (ok, hit). ok is True when the condition held before timeout.

    Transient uiautomator failures (screen transitions, bridge restarts) are
    treated as "not yet", not as fatal, because polling commands exist exactly
    for unstable moments.
    """
    deadline = time.time() + timeout
    while True:
        try:
            _, _, hits = selector_env(serial, selector, verbose=verbose and not want_gone)
        except AdbError as exc:
            if any(hint in str(exc).lower() for hint in FATAL_ADB_HINTS):
                raise
            hits = []
        found = bool(hits)
        if found != want_gone:
            return True, (hits[0] if found else None)
        if time.time() >= deadline:
            return False, None
        time.sleep(interval)


def screen_size(serial):
    cp = adb(serial, ["shell", "wm", "size"])
    m = re.search(r"(\d+)x(\d+)", cp.stdout or "")
    if not m:
        raise AdbError("cannot read screen size")
    return int(m.group(1)), int(m.group(2))


def ime_shown(serial):
    cp = adb(serial, ["shell", "dumpsys", "input_method"], check=False, timeout=15)
    return "mInputShown=true" in (cp.stdout or "")


def gesture_points(w, h, direction, distance=None):
    """Pure swipe geometry, centered on screen; distance applies to both axes."""
    cx, cy = w // 2, h // 2
    if direction in ("up", "down"):
        d = int(distance) if distance else int(h * 0.45)
        if direction == "up":
            return cx, cy + d // 2, cx, cy - d // 2
        return cx, cy - d // 2, cx, cy + d // 2
    if direction in ("left", "right"):
        d = int(distance) if distance else int(w * 0.45)
        if direction == "left":
            return cx + d // 2, cy, cx - d // 2, cy
        return cx - d // 2, cy, cx + d // 2, cy
    raise AdbError(f"unknown swipe direction {direction!r}")


def gesture(serial, direction, distance=None, duration_ms=300, hide_ime=True):
    if hide_ime and ime_shown(serial):
        # A swipe over an open software keyboard glide-types (observed six
        # "to"s in one scroll session). Hide the IME first; a BACK press with a
        # visible keyboard only closes the keyboard. --no-hide-ime opts out for
        # apps where BACK has side effects.
        adb(serial, ["shell", "input", "keyevent", "4"], check=False)
        time.sleep(0.5)
    w, h = screen_size(serial)
    x1, y1, x2, y2 = gesture_points(w, h, direction, distance)
    adb(serial, ["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms)])
    time.sleep(0.6)
    return x1, y1, x2, y2


KEYCODES = {
    "HOME": 3, "BACK": 4, "CALL": 5, "ENDCALL": 6,
    "DPAD_UP": 19, "DPAD_DOWN": 20, "DPAD_LEFT": 21, "DPAD_RIGHT": 22,
    "DPAD_CENTER": 23, "POWER": 26, "CAMERA": 27,
    "ENTER": 66, "DEL": 67, "BACKSPACE": 67,
    "TAB": 61, "SPACE": 62, "ESCAPE": 111,
    "MOVE_HOME": 122, "MOVE_END": 123,
    "APP_SWITCH": 187, "MENU": 82, "SEARCH": 84,
}

TEXT_ESCAPE_LIMIT = 80

SELFTEST_FIXTURE = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node index="0" text="Save &amp; Exit" resource-id="app:id/save" class="android.widget.Button"
        package="app.under.test" clickable="true" enabled="true" bounds="[10,20][210,100]"/>
  <node index="4" text="Line one&#10;Line two" resource-id="app:id/multi" class="android.widget.TextView"
        package="app.under.test" clickable="false" enabled="true" bounds="[10,800][410,900]"/>
  <node index="1" text="" resource-id="" class="android.view.ViewGroup"
        package="app.under.test" clickable="true" enabled="true" bounds="[10,200][510,300]">
    <node index="0" text="Row label" resource-id="app:id/rowtext" class="android.widget.TextView"
          package="app.under.test" clickable="false" enabled="true" bounds="[20,220][300,280]"/>
  </node>
  <node index="2" text="Done" resource-id="app:id/a" class="android.widget.Button"
        package="app.under.test" clickable="true" enabled="true" bounds="[10,400][210,460]"/>
  <node index="3" text="Done" resource-id="app:id/b" class="android.widget.Button"
        package="app.under.test" clickable="true" enabled="true" bounds="[10,600][210,660]"/>
</hierarchy>"""


def selftest():
    checks = 0

    def check(cond, label):
        nonlocal checks
        if not cond:
            raise AssertionError(f"selftest failed: {label}")
        checks += 1

    nodes, parent = parse_tree(SELFTEST_FIXTURE)
    check(len(nodes) == 6, "node count")
    save = [n for _, n in nodes if n.rid == "app:id/save"][0]
    check(save.text == "Save & Exit", "entity decoding (&amp;)")
    multi = [n for _, n in nodes if n.rid == "app:id/multi"][0]
    check(multi.text == "Line one Line two", "newline normalization")

    class A:
        pass

    def sel(**kw):
        a = A()
        defaults = dict(
            label=None, id=None, exact=False, regex=False, case_sensitive=False,
            package=None, nth=0, topmost=False, bottommost=False, leftmost=False,
            rightmost=False,
        )
        defaults.update(kw)
        for k, v in defaults.items():
            setattr(a, k, v)
        return Selector(a)

    hits = [n for _, n in nodes if sel(label="save & exit", exact=True, case_sensitive=False).match(n)]
    check(len(hits) == 1, "exact case-insensitive")
    hits = [n for _, n in nodes if sel(label="save & exit", exact=True, case_sensitive=True).match(n)]
    check(len(hits) == 0, "exact case-sensitive miss")
    hits = [n for _, n in nodes if sel(label=r"^done$", regex=True).match(n)]
    check(len(hits) == 2, "regex over text")
    hits = [n for _, n in nodes if sel(id="app:id/b").match(n)]
    check(len(hits) == 1, "id exact")
    hits = [n for _, n in nodes if sel(label="Row label").match(n)]
    check(len(hits) == 1, "substring on child text")
    _, _, hits = (nodes, parent, [p for p in nodes if sel(label="Row label").match(p[1])])
    target = clicked_elem(hits[0][0], parent, hits[0][1])
    check(target == (10, 200, 510, 300), "clickable ancestor climb")
    both = [p for p in nodes if sel(label="Done").match(p[1])]
    ordered = sel(label="Done", bottommost=True).apply_order(both)
    check(ordered[0][1].bounds[1] == 600, "bottommost ordering")
    ordered = sel(label="Done").apply_order(
        sel(label="Done", topmost=True).apply_order(both)
    )
    check(ordered[0][1].bounds[1] == 400, "topmost ordering")
    ns = selector_namespace()
    check(ns.label is None and ns.nth == 0 and ns.exact is False, "selector namespace defaults")
    check(selector_namespace(label="x").label == "x", "selector namespace overrides")

    up = gesture_points(1080, 2400, "up", 500)
    check(abs(up[1] - up[3]) == 500 and up[0] == up[2], "gesture up distance")
    down = gesture_points(1080, 2400, "down")
    check(down[3] > down[1], "gesture down direction")
    left = gesture_points(1080, 2400, "left", 500)
    check(left[0] - left[2] == 500 and left[1] == left[3], "gesture left distance")
    right = gesture_points(1080, 2400, "right")
    check(right[2] > right[0], "gesture right direction")

    check(_split_literal_percent_s("plain") == ["plain"], "percent-s split plain")
    check(_split_literal_percent_s("100%s off") == ["100", " off"], "percent-s split literal")
    check(_space_escape("a b") == "a%sb", "space escape")

    line = node_line(nodes[0][1])
    check("pkg=" in line and "enabled=" in line, "node_line fields")

    samples = [
        (["dump-labels"], "dump-labels"),
        (["find", "Save"], "find"),
        (["tap", "Save"], "tap"),
        (["tap", "--xy", "10", "20"], "tap"),
        (["wait", "X"], "wait"),
        (["wait-gone", "X"], "wait-gone"),
        (["wait-stable"], "wait-stable"),
        (["scroll-to", "X"], "scroll-to"),
        (["text", "hello"], "text"),
        (["text", "x", "--no-settle"], "text"),
        (["tap", "X", "--expect", "Y", "--expect-regex"], "tap"),
        (["clear"], "clear"),
        (["key", "BACK"], "key"),
        (["swipe", "up"], "swipe"),
        (["swipe", "1", "2", "3", "4"], "swipe"),
        (["shot", "x"], "shot"),
        (["screen"], "screen"),
        (["version"], "version"),
    ]
    for argv, expected in samples:
        parsed = build_parser().parse_args(argv)
        check(parsed.cmd == expected, f"parser smoke {argv[0]}")
    check(build_parser().parse_args(["-s", "abc", "find", "X"]).serial == "abc", "global before subcommand")
    check(build_parser().parse_args(["find", "X", "-s", "abc"]).serial == "abc", "global after subcommand")
    check(build_parser().parse_args(["find", "X", "--verbose"]).verbose is True, "verbose after subcommand")
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            build_parser().parse_args(["find", "X", "--exact", "--regex"])
            check(False, "exact plus regex rejected")
        except SystemExit as exc:
            check(exc.code == 2, "exact plus regex exit code")

    js = json.dumps([node_json(n) for _, n in nodes])
    check('"bounds": [10, 20, 210, 100]' in js.replace("\n", " "), "json serialization")
    print(f"selftest ok ({checks} checks)")


def build_parser():
    p = argparse.ArgumentParser(
        prog="uitap.py",
        description=__doc__.splitlines()[0],
        epilog=(
            "examples:\n"
            "  uitap.py -s emulator-5554 dump-labels\n"
            "  uitap.py tap \"Continue\" --expect \"Enter your PIN\"\n"
            "  uitap.py text --into \"Title\" \"Solo Leveling\"\n"
            "  uitap.py key BACK\n"
            "  uitap.py scroll-to \"Series Two\" --max 4\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("-s", "--serial", default=None, help="device serial (adb -s)")
    p.add_argument("--verbose", action="store_true", help="explain misses and matches")
    p.add_argument("--log", default=None, metavar="FILE", help="append an audit line per run")
    sub = p.add_subparsers(dest="cmd", required=True)
    subs = []

    def new_sub(name, **kw):
        sp = sub.add_parser(name, **kw)
        subs.append(sp)
        return sp

    def add_globals(sp):
        # Mirrored on every subparser with SUPPRESS defaults so the global
        # options work on either side of the subcommand without clobbering
        # values already set before it.
        sp.add_argument("-s", "--serial", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        sp.add_argument("--verbose", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        sp.add_argument("--log", default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    def add_selector(sp, label=True):
        if label:
            sp.add_argument("label", nargs="?")
        sp.add_argument("--id", default=None, help="match by resource id")
        mode = sp.add_mutually_exclusive_group()
        mode.add_argument("--exact", action="store_true")
        mode.add_argument("--regex", action="store_true")
        sp.add_argument("--case-sensitive", action="store_true")
        sp.add_argument("--package", default=None)
        sp.add_argument("--nth", type=int, default=0)
        sp.add_argument("--topmost", action="store_true")
        sp.add_argument("--bottommost", action="store_true")
        sp.add_argument("--leftmost", action="store_true")
        sp.add_argument("--rightmost", action="store_true")

    dl = new_sub("dump-labels", help="list matching nodes")
    add_selector(dl)
    dl.add_argument("--json", action="store_true")

    f = new_sub("find", help="print first match, exit 1 on miss")
    add_selector(f)
    f.add_argument("--json", action="store_true")

    t = new_sub("tap", help="tap a match, raw coordinates, or --xy")
    t.add_argument("target", nargs="*")
    t.add_argument("--xy", nargs=2, type=int, metavar=("X", "Y"))
    t.add_argument("--id", default=None)
    t_mode = t.add_mutually_exclusive_group()
    t_mode.add_argument("--exact", action="store_true")
    t_mode.add_argument("--regex", action="store_true")
    t.add_argument("--case-sensitive", action="store_true")
    t.add_argument("--package", default=None)
    t.add_argument("--nth", type=int, default=0)
    t.add_argument("--topmost", action="store_true")
    t.add_argument("--bottommost", action="store_true")
    t.add_argument("--leftmost", action="store_true")
    t.add_argument("--rightmost", action="store_true")
    t.add_argument("--retry", type=int, default=1, help="attempts, default 1")
    t.add_argument("--retry-delay", type=float, default=0.4)
    t.add_argument("--dry-run", action="store_true")
    t.add_argument("--expect", default=None, help="verify this label after tapping")
    e_mode = t.add_mutually_exclusive_group()
    e_mode.add_argument("--expect-exact", action="store_true")
    e_mode.add_argument("--expect-regex", action="store_true")
    t.add_argument("--expect-timeout", type=float, default=5)

    w = new_sub("wait", help="poll until a match exists")
    add_selector(w)
    w.add_argument("--timeout", type=float, default=20)
    w.add_argument("--interval", type=float, default=1.0)

    wg = new_sub("wait-gone", help="poll until no match exists")
    add_selector(wg)
    wg.add_argument("--timeout", type=float, default=20)
    wg.add_argument("--interval", type=float, default=1.0)

    ws = new_sub("wait-stable", help="wait until the normalized tree stops changing")
    ws.add_argument("--rounds", type=int, default=3)
    ws.add_argument("--interval", type=float, default=1.0)
    ws.add_argument("--timeout", type=float, default=30)
    ws.add_argument("--save", default=None, metavar="FILE")

    st = new_sub("scroll-to", help="swipe until a match appears")
    add_selector(st)
    st.add_argument("--direction", choices=["up", "down", "left", "right"], default="up")
    st.add_argument("--max", type=int, default=6, dest="max_swipes")
    st.add_argument("--interval", type=float, default=0.8)
    st.add_argument("--no-hide-ime", action="store_true")

    tx = new_sub("text", help="type into the focused field")
    tx.add_argument("value", nargs="+")
    tx.add_argument("--into", default=None, metavar="LABEL")
    tx.add_argument("--clear", action="store_true")
    tx.add_argument("--no-settle", action="store_true",
                    help="skip the post-tap settle wait with --into")

    cl = new_sub("clear", help="clear the focused text field")
    cl.add_argument("--length", type=int, default=TEXT_ESCAPE_LIMIT)

    k = new_sub("key", help="send a key event")
    k.add_argument("name")

    sw = new_sub("swipe", help="gesture, by direction or coordinates")
    sw.add_argument("coords", nargs="+")
    sw.add_argument("--distance", type=int, default=None)
    sw.add_argument("--duration", type=int, default=300)
    sw.add_argument("--no-hide-ime", action="store_true",
                    help="do not send BACK to hide the keyboard before swiping")

    sh = new_sub("shot", help="screenshot to <name>.png")
    sh.add_argument("name")

    new_sub("screen", help="physical size and density")
    new_sub("selftest", help="internal checks, no device needed")
    new_sub("version", help="print the tool version")
    for sp in subs:
        add_globals(sp)
    return p


def cmd_dump_labels(args, serial, log):
    _, _, hits = selector_env(serial, Selector(args), verbose=args.verbose)
    only_labeled = args.label is None and args.id is None and args.package is None
    if only_labeled:
        hits = [(e, n) for e, n in hits if n.text or n.desc or n.rid]
    if args.json:
        print(json.dumps([node_json(n) for _, n in hits]))
    else:
        for _, n in hits:
            print(node_line(n))
    log.write(f"dump-labels -> {len(hits)} nodes")
    return 0


def cmd_find(args, serial, log):
    _, _, hits = selector_env(serial, Selector(args), verbose=args.verbose)
    if not hits:
        print(f"MISS: no node matching {Selector(args).describe()}", file=sys.stderr)
        log.write("find -> miss")
        return 1
    _, n = hits[0]
    if args.verbose:
        print(f"matched on {'id' if args.id else 'text/desc'}", file=sys.stderr)
    if args.json:
        print(json.dumps(node_json(n)))
    else:
        print(node_line(n))
    log.write("find -> hit")
    return 0


def cmd_tap(args, serial, log):
    if args.xy:
        x, y = args.xy
        if args.dry_run:
            print(f"would tap raw ({x},{y})")
            return 0
        tap_center(serial, (x, y, x, y))
        log.write(f"tap xy ({x},{y})")
        return 0
    target = args.target
    if len(target) == 2 and all(t.lstrip("-").isdigit() for t in target):
        joined = " ".join(target)
        _, _, label_hits = selector_env(serial, Selector(selector_namespace(label=joined)))
        if label_hits:
            print(
                f"warning: coordinates {joined!r} also match a visible label; "
                f"tapping the coordinates. Use --xy to skip this check.",
                file=sys.stderr,
            )
        x, y = int(target[0]), int(target[1])
        if args.dry_run:
            print(f"would tap raw ({x},{y})")
            return 0
        tap_center(serial, (x, y, x, y))
        log.write(f"tap xy ({x},{y})")
        return 0
    if target:
        args.label = " ".join(target)
    sel = Selector(args)
    if sel.label is None and sel.rid is None:
        print("tap needs a label, X Y, or --xy X Y", file=sys.stderr)
        return 2
    last_reason = ""
    for attempt in range(1, max(1, args.retry) + 1):
        _, parent, hits = selector_env(serial, sel, verbose=args.verbose)
        if hits:
            elem, n = hits[0]
            bounds = clicked_elem(elem, parent, n)
            x, y = (bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2
            if args.dry_run:
                print(f"would tap {node_line(n)} at ({x},{y})")
                return 0
            tap_center(serial, bounds)
            print(f"tapped {sel.describe()} at ({x},{y})")
            log.write(f"tap {sel.describe()} -> ({x},{y}) attempt {attempt}")
            if args.expect:
                esc = selector_namespace(
                    label=args.expect,
                    exact=args.expect_exact,
                    regex=args.expect_regex,
                    case_sensitive=args.case_sensitive,
                )
                ok, _ = wait_match(serial, Selector(esc), args.expect_timeout, 0.5)
                if ok:
                    print(f"expect ok: {args.expect!r} visible")
                    log.write(f"expect {args.expect!r} -> ok")
                    return 0
                print(f"EXPECT FAILED: {args.expect!r} not visible after {args.expect_timeout}s", file=sys.stderr)
                log.write(f"expect {args.expect!r} -> failed")
                return 1
            return 0
        last_reason = f"no node matching {sel.describe()}"
        if attempt < args.retry:
            time.sleep(args.retry_delay)
    print(f"MISS: {last_reason}", file=sys.stderr)
    log.write(f"tap {sel.describe()} -> miss")
    return 1


def cmd_wait(args, serial, log, want_gone=False):
    ok, hit = wait_match(
        serial, Selector(args), args.timeout, args.interval,
        want_gone=want_gone, verbose=args.verbose,
    )
    verb = "wait-gone" if want_gone else "wait"
    if not ok:
        want = "disappear" if want_gone else "appear"
        print(f"TIMEOUT: {Selector(args).describe()} did not {want} within {args.timeout}s", file=sys.stderr)
        log.write(f"{verb} -> timeout")
        return 1
    if want_gone:
        print(f"{verb} ok: {Selector(args).describe()} no longer present")
    else:
        print(f"{verb} ok: {node_line(hit[1])}")
    log.write(f"{verb} -> ok")
    return 0


def wait_stable(serial, rounds=3, interval=1.0, timeout_s=30, verbose=True):
    """Return the final tree XML once the normalized signature stops changing."""
    deadline = time.time() + timeout_s
    last_hash = None
    stable = 0
    final_xml = None
    last_reason = ""
    while time.time() < deadline:
        ok, xml, reason = dump(serial)
        if not ok:
            last_reason = reason
            stable = 0
            last_hash = None
            time.sleep(interval)
            continue
        nodes, _ = parse_tree(xml)
        signature = "\n".join(
            f"{n.klass}|{n.rid}|{n.text}|{n.desc}|{n.bounds}" for _, n in nodes
        )
        h = hashlib.sha1(signature.encode("utf-8", "ignore")).hexdigest()
        final_xml = xml
        if h == last_hash:
            stable += 1
        else:
            stable = 1
            last_hash = h
        if stable >= rounds:
            if verbose:
                print(f"stable after {stable} identical dumps")
            return final_xml
        time.sleep(interval)
    if verbose:
        detail = f" (last error while probing: {last_reason})" if last_reason else ""
        print(f"TIMEOUT: UI never stabilized within {timeout_s}s{detail}", file=sys.stderr)
    return None


def cmd_wait_stable(args, serial, log):
    xml = wait_stable(
        serial, rounds=args.rounds, interval=args.interval, timeout_s=args.timeout,
    )
    if xml is None:
        log.write("wait-stable -> timeout")
        return 1
    if args.save:
        with open(args.save, "w", encoding="utf-8") as fh:
            fh.write(xml)
        print(f"tree saved to {args.save}")
    log.write("wait-stable -> ok")
    return 0


def cmd_scroll_to(args, serial, log):
    sel = Selector(args)
    for swipe in range(args.max_swipes + 1):
        _, _, hits = selector_env(serial, sel, verbose=args.verbose)
        if hits:
            print(f"found after {swipe} swipe(s): {node_line(hits[0][1])}")
            log.write(f"scroll-to {sel.describe()} -> hit after {swipe} swipes")
            return 0
        if swipe == args.max_swipes:
            break
        gesture(serial, args.direction, duration_ms=300,
                hide_ime=not args.no_hide_ime)
        time.sleep(args.interval)
    print(f"MISS: {sel.describe()} not found after {args.max_swipes} swipe(s)", file=sys.stderr)
    log.write(f"scroll-to {sel.describe()} -> miss")
    return 1


def do_clear(serial, length):
    adb(serial, ["shell", "input", "keyevent", "123"])
    remaining = max(1, length)
    while remaining > 0:
        chunk = min(20, remaining)
        adb(serial, ["shell", "input", "keyevent"] + ["67"] * chunk)
        remaining -= chunk
    time.sleep(0.4)


def _space_escape(value):
    return value.replace(" ", "%s")


def _split_literal_percent_s(value):
    return value.split("%s")


def _type_chunk(serial, chunk):
    if not chunk:
        return
    escaped = _space_escape(chunk)
    quoted = "'" + escaped.replace("'", "'\\''") + "'"
    adb(serial, ["shell", "input", "text", quoted])


def send_text(serial, value):
    if any(ord(ch) > 127 for ch in value):
        print(
            "ERROR: adb input text cannot type non-ASCII characters; "
            "install ADBKeyboard for unicode input",
            file=sys.stderr,
        )
        return False
    parts = _split_literal_percent_s(value)
    for index, part in enumerate(parts):
        _type_chunk(serial, part)
        if index < len(parts) - 1:
            adb(serial, ["shell", "input", "text", "%"])
            adb(serial, ["shell", "input", "text", "s"])
    time.sleep(0.6)
    print(f"typed {value!r}")
    return True


def cmd_text(args, serial, log):
    value = " ".join(args.value)
    if args.into:
        esc = selector_namespace(label=args.into)
        _, parent, hits = selector_env(serial, Selector(esc))
        if not hits:
            print(f"MISS: no node matching --into {args.into!r}", file=sys.stderr)
            log.write("text --into -> miss")
            return 1
        field = next(
            (h for h in hits if "EditText" in h[1].klass or "TextField" in h[1].klass),
            hits[0],
        )
        tap_center(serial, clicked_elem(field[0], parent, field[1]))
        if not args.no_settle:
            wait_stable(serial, rounds=2, interval=0.25, timeout_s=3, verbose=False)
    if args.clear:
        do_clear(serial, TEXT_ESCAPE_LIMIT)
    if not send_text(serial, value):
        return 2
    log.write(f"text {value!r} -> typed")
    return 0


def cmd_clear(args, serial, log):
    do_clear(serial, args.length)
    print(f"cleared focused field (up to {args.length} chars)")
    log.write("clear -> ok")
    return 0


def cmd_key(args, serial, log):
    name = args.name.upper()
    code = KEYCODES.get(name)
    if code is None:
        if name.lstrip("-").isdigit():
            code = int(name)
        else:
            print(
                f"unknown key {args.name!r}; known: {', '.join(sorted(KEYCODES))} or a numeric code",
                file=sys.stderr,
            )
            return 2
    adb(serial, ["shell", "input", "keyevent", str(code)])
    time.sleep(0.4)
    print(f"key {name}")
    log.write(f"key {name}")
    return 0


def cmd_swipe(args, serial, log):
    coords = args.coords
    if len(coords) == 1 and coords[0] in ("up", "down", "left", "right"):
        x1, y1, x2, y2 = gesture(
            serial, coords[0], args.distance, args.duration,
            hide_ime=not args.no_hide_ime,
        )
    elif len(coords) == 4 and all(c.lstrip("-").isdigit() for c in coords):
        x1, y1, x2, y2 = (int(c) for c in coords)
        adb(serial, ["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(args.duration)])
        time.sleep(0.6)
    else:
        print("swipe takes up|down|left|right or X1 Y1 X2 Y2", file=sys.stderr)
        return 2
    print(f"swiped ({x1},{y1}) -> ({x2},{y2})")
    log.write(f"swipe ({x1},{y1})->({x2},{y2})")
    return 0


def cmd_shot(args, serial, log):
    name = args.name if args.name.lower().endswith(".png") else args.name + ".png"
    with open(name, "wb") as fh:
        cp = subprocess.run(
            adb_cmd(serial) + ["exec-out", "screencap", "-p"],
            stdout=fh,
            stderr=subprocess.PIPE,
            timeout=60,
        )
    if cp.returncode != 0:
        raise AdbError("screencap failed")
    print(f"saved {name}")
    log.write(f"shot {name}")
    return 0


def cmd_screen(args, serial, log):
    w, h = screen_size(serial)
    cp = adb(serial, ["shell", "wm", "density"], check=False)
    density = (cp.stdout or "").strip().splitlines()[-1:] or [""]
    print(f"size {w}x{h} | {density[0]}")
    log.write(f"screen {w}x{h}")
    return 0


def main():
    args = build_parser().parse_args()
    log = Logger(args.log)
    try:
        if args.cmd == "selftest":
            selftest()
            log.write("selftest -> ok")
            return 0
        if args.cmd == "version":
            print(VERSION)
            return 0
        serial = resolve_serial(args.serial, log)
        dispatch = {
            "dump-labels": cmd_dump_labels,
            "find": cmd_find,
            "tap": cmd_tap,
            "wait": lambda a, s, l: cmd_wait(a, s, l, want_gone=False),
            "wait-gone": lambda a, s, l: cmd_wait(a, s, l, want_gone=True),
            "wait-stable": cmd_wait_stable,
            "scroll-to": cmd_scroll_to,
            "text": cmd_text,
            "clear": cmd_clear,
            "key": cmd_key,
            "swipe": cmd_swipe,
            "shot": cmd_shot,
            "screen": cmd_screen,
        }
        rc = dispatch[args.cmd](args, serial, log)
        log.write(f"exit {rc}")
        return rc
    except AdbError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        log.write(f"error: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
