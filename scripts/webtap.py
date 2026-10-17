#!/usr/bin/env python3
"""webtap.py: Playwright web driver for browser acceptance (The Artifact Method).

Framework-agnostic web counterpart to uitap.py. Reads the page's
accessibility-flavored name and role data, acts through Playwright locators.
Works with any web app that exposes accessible names; falls back to CSS
(`--id`) and raw coordinates (`tap X Y`). Single file. Only dependency:
python3 and the `playwright` package (pip install playwright).

Session model: stateless per command, with a storage-state file
(.webtap/state.json by default) persisted across commands so cookies and
localStorage survive. DOM commands reopen the last visited URL
(.webtap/last.json); in-memory page state (form fields, JS variables) does
not survive between commands. Use `flow` for multi-step acceptance runs: one
browser, one sequence, one exit code.

Selectors (used by find, tap, wait, wait-gone, scroll-to, text --into):
  <label>                substring match on the element's accessible name
  --exact                whole match
  --regex                treat the label as a regular expression
  --case-sensitive       stop folding case
  --role ROLE            restrict to an ARIA role (button, link, textbox, ...)
  --id <selector>        match by CSS selector instead
  --within <selector>    scope the search to a parent (#css, .css, or label)
  --nth N                pick the Nth match after ordering (0-based)
  --topmost --bottommost --leftmost --rightmost   pick by position
  --timeout S            (wait, wait-gone) seconds
Strict mode: multiple matches are a miss unless --nth or a position flag
narrows them (unlike uitap.py, which silently takes the first).

Commands:
  goto <url>                             navigate, wait for load (networkidle
                                         best-effort), print url + title
  url [url]                              navigate (optional) and print the URL
  title [url]                            navigate (optional) and print the title
  dump-labels [selector] [--json] [--tree] [--limit N]
                                         list labeled elements; --tree prints
                                         the ARIA snapshot text instead
  find <selector args> [--json]          print first match, exit 1 on miss
  tap <selector args> | tap X Y | tap --xy X Y
      [--retry N] [--retry-delay S] [--dry-run]
      [--expect L [--expect-exact | --expect-regex]] [--expect-timeout S]
  wait <selector args> [--timeout S]     poll until visible
  wait-gone <selector args> [--timeout S]  poll until hidden or detached
  wait-stable [--network-idle] [--rounds N] [--interval S] [--timeout S]
              [--save FILE]              wait until the DOM signature settles
  scroll-to <selector args>              scroll first match into view
  scroll up|down|left|right [--pixels N] wheel-scroll the viewport
  text [--into LABEL] [--clear] <value>  fill a field (or the focused one)
  clear [--into LABEL]                   clear a field (or the focused one)
  key <NAME>                             Enter, Tab, Escape, ArrowDown,
                                         Control+A, ... (exit 2 if unknown)
  shot <name> [--full-page] [--element SEL] [--format png|jpeg|webp]
  console [--since S] [--lines N]        recent console messages (rolling log)
  network [--since S] [--filter PAT] [--lines N]
                                         recent requests: METHOD url STATUS ms
  flow <file.json>                       run a step sequence in one session
  screen                                 viewport size, dpr, browser
  selftest                               internal checks, no browser needed
  version                                print the tool version

Global options go before or after the command: --state FILE, --headed,
--browser chromium|firefox|webkit, --verbose, --log FILE, --no-evidence.

Config: optional .webtap.json in the working directory
  {"base_url", "browser", "viewport": [W, H], "state_file", "evidence_dir",
   "timeout_default"}
CLI flags override config; config overrides the WEBTAP_BASE_URL,
WEBTAP_BROWSER, and WEBTAP_STATE environment variables.

Evidence: state-changing commands (goto, tap, text, clear, key, scroll,
scroll-to) write a screenshot and a JSON receipt to the evidence directory.
`flow` writes one directory per step plus index.json and TEST_NOTES.md.
Console and network activity roll into .webtap/console.log and
.webtap/network.log (JSON lines, secrets in query strings redacted).

Exit codes: 0 success, 1 miss/timeout/expect failure, 2 usage or browser error.
"""
import argparse
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import time
import urllib.parse

VERSION = "0.1.0"

DEFAULT_CONFIG = {
    "base_url": None,
    "browser": "chromium",
    "viewport": [1280, 800],
    "state_file": ".webtap/state.json",
    "evidence_dir": ".webtap/evidence",
    "timeout_default": 20.0,
}

BROWSERS = ("chromium", "firefox", "webkit")

CONFIG_KEYS = tuple(DEFAULT_CONFIG)

FATAL_HINTS = (
    "executable doesn't exist",
    "playwright install",
    "failed to launch",
    "browser has been closed",
    "browser closed unexpectedly",
    "target page, context or browser has been closed",
)

EVIDENCE_VERBS = {"goto", "tap", "text", "clear", "key", "scroll", "scroll-to"}

PRIME_VERBS = {
    "dump-labels", "find", "tap", "wait", "wait-gone", "wait-stable",
    "scroll-to", "scroll", "text", "clear", "key", "shot",
}

FLOW_POSITIONAL = {
    "goto": "url",
    "url": "url",
    "title": "url",
    "find": "label",
    "tap": "label",
    "wait": "label",
    "wait-gone": "label",
    "scroll-to": "label",
    "scroll": "direction",
    "text": "value",
    "key": "name",
    "shot": "name",
    "flow": "file",
}

SENSITIVE_KEY_RE = re.compile(
    r"(token|secret|password|passwd|pwd|api[-_]?key|auth|session|sid|code)",
    re.IGNORECASE,
)

ROTATE_BYTES = 5_000_000

NAME_JS = """el => {
  const attr = el.getAttribute && el.getAttribute('aria-label');
  if (attr && attr.trim()) return attr.trim();
  const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
  if (text) return text;
  const alt = el.getAttribute && (el.getAttribute('title') || el.getAttribute('placeholder') || el.getAttribute('alt'));
  return alt ? alt.trim() : '';
}"""

ROLE_JS = """el => {
  const explicit = el.getAttribute && el.getAttribute('role');
  if (explicit && explicit.trim()) return explicit.trim().toLowerCase();
  const tag = el.tagName ? el.tagName.toLowerCase() : '';
  const type = (el.getAttribute && el.getAttribute('type') || '').toLowerCase();
  if (tag === 'input') {
    if (type === 'checkbox') return 'checkbox';
    if (type === 'radio') return 'radio';
    if (type === 'button' || type === 'submit' || type === 'reset') return 'button';
    if (type === 'range') return 'slider';
    return 'textbox';
  }
  const map = {
    a: 'link', button: 'button', img: 'img', select: 'combobox', textarea: 'textbox',
    nav: 'navigation', header: 'banner', footer: 'contentinfo', main: 'main',
    dialog: 'dialog', summary: 'button', h1: 'heading', h2: 'heading',
    h3: 'heading', h4: 'heading', h5: 'heading', h6: 'heading'
  };
  return map[tag] || 'generic';
}"""

SIG_JS = """() => {
  const body = document.body;
  const text = body ? (body.innerText || '') : '';
  const count = document.getElementsByTagName('*').length;
  let h = 0;
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) | 0;
  return count + '|' + text.length + '|' + h;
}"""

ACTIVE_JS = """() => {
  const a = document.activeElement;
  return !!(a && a !== document.body && a !== document.documentElement);
}"""

ENUM_JS = """(limit) => {
  const out = [];
  for (const el of document.querySelectorAll('*')) {
    if (el.closest('[aria-hidden="true"]')) continue;
    const attr = el.getAttribute('aria-label');
    let name = attr && attr.trim() ? attr.trim() : '';
    if (!name) name = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
    const explicit = el.getAttribute('role');
    let role = explicit && explicit.trim() ? explicit.trim().toLowerCase() : '';
    if (!role) {
      const tag = el.tagName.toLowerCase();
      const type = (el.getAttribute('type') || '').toLowerCase();
      if (tag === 'input') {
        role = (type === 'checkbox') ? 'checkbox'
             : (type === 'radio') ? 'radio'
             : (type === 'button' || type === 'submit' || type === 'reset') ? 'button'
             : (type === 'range') ? 'slider' : 'textbox';
      } else {
        role = {a: 'link', button: 'button', img: 'img', select: 'combobox',
          textarea: 'textbox', nav: 'navigation', header: 'banner',
          footer: 'contentinfo', main: 'main', dialog: 'dialog',
          summary: 'button', h1: 'heading', h2: 'heading', h3: 'heading',
          h4: 'heading', h5: 'heading', h6: 'heading'}[tag] || 'generic';
      }
    }
    if (role === 'generic' && !name) continue;
    const rect = el.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) continue;
    out.push({role: role, name: name.slice(0, 200), tag: el.tagName.toLowerCase(),
              bounds: [Math.round(rect.x), Math.round(rect.y),
                       Math.round(rect.width), Math.round(rect.height)]});
    if (out.length >= limit) break;
  }
  return out;
}"""

KEY_ALIASES = {
    "ENTER": "Enter", "TAB": "Tab", "ESCAPE": "Escape", "ESC": "Escape",
    "SPACE": "Space", "BACKSPACE": "Backspace", "DEL": "Delete",
    "DELETE": "Delete", "INSERT": "Insert", "HOME": "Home", "END": "End",
    "PAGEUP": "PageUp", "PAGEDOWN": "PageDown",
    "ARROWUP": "ArrowUp", "ARROWDOWN": "ArrowDown",
    "ARROWLEFT": "ArrowLeft", "ARROWRIGHT": "ArrowRight",
    "UP": "ArrowUp", "DOWN": "ArrowDown", "LEFT": "ArrowLeft",
    "RIGHT": "ArrowRight",
}

MODIFIER_ALIASES = {
    "ctrl": "Control", "control": "Control", "alt": "Alt", "shift": "Shift",
    "meta": "Meta", "cmd": "Meta", "command": "Meta",
}


class WebtapError(Exception):
    """Usage, configuration, or fatal browser error: exit 2."""


class SelectionMiss(Exception):
    """No match, multiple matches under strict mode, or a timeout: exit 1."""


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


def load_config(cwd=None, env=None):
    """Merge defaults <- .webtap.json <- environment. Returns (cfg, warnings)."""
    cfg = dict(DEFAULT_CONFIG)
    cfg["viewport"] = list(DEFAULT_CONFIG["viewport"])
    warnings = []
    env = os.environ if env is None else env
    path = os.path.join(cwd or os.getcwd(), ".webtap.json")
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                warnings.append(f"{path}: expected a JSON object; ignored")
            else:
                for key, value in data.items():
                    if key not in CONFIG_KEYS:
                        warnings.append(f"{path}: unknown key {key!r}; ignored")
                        continue
                    cfg[key] = value
        except (OSError, json.JSONDecodeError) as exc:
            warnings.append(f"{path}: cannot read config ({exc}); using defaults")
    if env.get("WEBTAP_BASE_URL"):
        cfg["base_url"] = env["WEBTAP_BASE_URL"]
    if env.get("WEBTAP_BROWSER"):
        cfg["browser"] = env["WEBTAP_BROWSER"]
    if env.get("WEBTAP_STATE"):
        cfg["state_file"] = env["WEBTAP_STATE"]
    if cfg["browser"] not in BROWSERS:
        warnings.append(f"unknown browser {cfg['browser']!r}; using chromium")
        cfg["browser"] = "chromium"
    viewport = cfg.get("viewport")
    if not (
        isinstance(viewport, (list, tuple))
        and len(viewport) == 2
        and all(isinstance(v, int) and v > 0 for v in viewport)
    ):
        warnings.append(f"bad viewport {viewport!r}; using {DEFAULT_CONFIG['viewport']}")
        cfg["viewport"] = list(DEFAULT_CONFIG["viewport"])
    else:
        cfg["viewport"] = [int(v) for v in viewport]
    try:
        cfg["timeout_default"] = float(cfg["timeout_default"])
        if cfg["timeout_default"] <= 0:
            raise ValueError
    except (TypeError, ValueError):
        warnings.append(f"bad timeout_default {cfg.get('timeout_default')!r}; using 20")
        cfg["timeout_default"] = 20.0
    return cfg, warnings


def apply_cli(cfg, args):
    cfg = dict(cfg)
    state = getattr(args, "state", None)
    if state:
        cfg["state_file"] = state
    browser = getattr(args, "browser", None)
    if browser:
        cfg["browser"] = browser
    cfg["headed"] = bool(getattr(args, "headed", False))
    cfg["verbose"] = bool(getattr(args, "verbose", False))
    cfg["evidence_enabled"] = not bool(getattr(args, "no_evidence", False))
    return cfg


def workdir_of(cfg):
    return os.path.dirname(cfg["state_file"]) or "."


def redact_url(url):
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return url
    if not parts.query:
        return url
    pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    masked = [
        (k, "REDACTED" if SENSITIVE_KEY_RE.search(k) else v) for k, v in pairs
    ]
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path,
         urllib.parse.urlencode(masked), parts.fragment)
    )


def redact_args(data):
    if isinstance(data, dict):
        return {
            k: ("REDACTED" if SENSITIVE_KEY_RE.search(str(k)) and v else redact_args(v))
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [redact_args(v) for v in data]
    return data


def join_url(base, url):
    if not url:
        raise WebtapError("no URL given")
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url) or url.startswith("about:"):
        return url
    if not base:
        raise WebtapError(f"relative URL {url!r} needs base_url (set it in .webtap.json)")
    return urllib.parse.urljoin(base if base.endswith("/") else base + "/", url)


def css_attr_escape(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def normalize_key(name):
    raw = (name or "").strip()
    if not raw:
        raise WebtapError("key needs a name")
    out = []
    for part in raw.split("+"):
        piece = part.strip()
        if not piece:
            raise WebtapError(f"bad key {name!r}")
        upper = piece.upper()
        if upper in KEY_ALIASES:
            out.append(KEY_ALIASES[upper])
            continue
        if re.fullmatch(r"F([1-9]|1[0-2])", upper):
            out.append(upper)
            continue
        if piece.lower() in MODIFIER_ALIASES:
            out.append(MODIFIER_ALIASES[piece.lower()])
            continue
        if len(piece) == 1 and piece.isalnum():
            out.append(piece)
            continue
        raise WebtapError(
            f"unknown key {name!r}; use names like Enter, Tab, Escape, "
            f"ArrowDown, or modifiers like Control+A"
        )
    return "+".join(out)


def match_name(name, label, exact, case_sensitive):
    if case_sensitive:
        return name == label if exact else label in name
    low_name, low_label = name.lower(), label.lower()
    return low_name == low_label if exact else low_label in low_name


def step_argv(step):
    """Translate a flow step object into CLI argv for the parser."""
    if not isinstance(step, dict) or "cmd" not in step:
        raise WebtapError(f"flow step must be an object with 'cmd': {step!r}")
    cmd = str(step["cmd"])
    argv = [cmd]
    positional = FLOW_POSITIONAL.get(cmd)
    for key, value in step.items():
        if key == "cmd":
            continue
        if key == positional:
            if isinstance(value, list):
                argv.extend(str(v) for v in value)
            else:
                argv.append(str(value))
            continue
        flag = "--" + key.replace("_", "-")
        if isinstance(value, bool):
            if value:
                argv.append(flag)
        elif value is None:
            continue
        elif isinstance(value, list):
            argv.append(flag)
            argv.extend(str(v) for v in value)
        else:
            argv.extend([flag, str(value)])
    return argv


def unique_stem(root, stem):
    candidate = stem
    count = 2
    while (
        os.path.exists(os.path.join(root, candidate + ".png"))
        or os.path.exists(os.path.join(root, candidate + ".json"))
    ):
        candidate = f"{stem}-{count}"
        count += 1
    return candidate


def append_jsonl(path, obj, max_bytes=ROTATE_BYTES):
    if os.path.exists(path) and os.path.getsize(path) > max_bytes:
        try:
            os.remove(path)
        except OSError:
            pass
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_jsonl(path, limit=None):
    entries = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    if limit is not None and len(entries) > limit:
        entries = entries[-limit:]
    return entries


def format_ts(ts):
    return time.strftime("%H:%M:%S", time.localtime(ts))


def first_line(exc):
    text = str(exc).strip()
    return text.splitlines()[0] if text else type(exc).__name__


def is_fatal_message(text):
    low = text.lower()
    return any(hint in low for hint in FATAL_HINTS)


def classify_exception(exc):
    if type(exc).__name__ == "TimeoutError":
        return 1
    return 2


class Selector:
    def __init__(self, args):
        self.label = getattr(args, "label", None)
        self.role = getattr(args, "role", None)
        self.rid = getattr(args, "id", None)
        self.within = getattr(args, "within", None)
        self.exact = getattr(args, "exact", False)
        self.regex = getattr(args, "regex", False)
        self.case_sensitive = getattr(args, "case_sensitive", False)
        self.nth = getattr(args, "nth", None)
        self.topmost = getattr(args, "topmost", False)
        self.bottommost = getattr(args, "bottommost", False)
        self.leftmost = getattr(args, "leftmost", False)
        self.rightmost = getattr(args, "rightmost", False)

    def describe(self):
        if self.rid is not None:
            return f"id {self.rid!r}"
        if self.label is None:
            return "any element"
        kind = "regex" if self.regex else ("exact" if self.exact else "substring")
        if self.role:
            return f"{self.role} {kind} {self.label!r}"
        return f"{kind} {self.label!r}"

    def needs_python_filter(self):
        if self.regex or self.rid is not None:
            return False
        if self.exact and self.case_sensitive:
            return False
        return bool(self.exact or self.case_sensitive)

    def _pattern(self, value):
        flags = 0 if self.case_sensitive else re.IGNORECASE
        try:
            return re.compile(value, flags)
        except re.error as exc:
            raise WebtapError(f"bad regex: {exc}")

    def candidates(self, root):
        """Loose candidate locator, resolved against a Page or a Locator."""
        if self.rid is not None:
            try:
                return root.locator(self.rid)
            except Exception as exc:
                raise WebtapError(f"bad CSS selector {self.rid!r}: {first_line(exc)}")
        label = self.label
        if label is None:
            raise WebtapError("selector needs a label, --role, or --id")
        loose_exact = self.exact and self.case_sensitive
        if self.regex:
            pattern = self._pattern(label)
            if self.role:
                return root.get_by_role(self.role, name=pattern)
            return root.get_by_text(pattern)
        if self.role:
            if loose_exact:
                return root.get_by_role(self.role, name=label, exact=True)
            return root.get_by_role(self.role, name=label)
        if loose_exact:
            loc = root.get_by_text(label, exact=True)
        else:
            loc = root.get_by_text(label)
        loc = loc.or_(root.get_by_label(label, exact=loose_exact))
        loc = loc.or_(root.get_by_placeholder(label, exact=loose_exact))
        loc = loc.or_(root.get_by_title(label, exact=loose_exact))
        loc = loc.or_(root.get_by_alt_text(label, exact=loose_exact))
        aria_css = f'[aria-label*="{css_attr_escape(label)}" i]'
        try:
            loc = loc.or_(root.locator(aria_css))
        except Exception:
            pass
        return loc

    def filter_locators(self, locs):
        if not self.needs_python_filter():
            return locs
        kept = []
        for loc in locs:
            try:
                name = loc.evaluate(NAME_JS)
            except Exception:
                continue
            if match_name(name or "", self.label, self.exact, self.case_sensitive):
                kept.append(loc)
        return kept

    def apply_order(self, locs):
        if not (self.topmost or self.bottommost or self.leftmost or self.rightmost):
            return locs

        def box(loc):
            try:
                b = loc.bounding_box()
            except Exception:
                b = None
            return b or {"x": 10**9, "y": 10**9, "width": 0, "height": 0}

        if self.topmost:
            locs.sort(key=lambda l: (box(l)["y"], box(l)["x"]))
        elif self.bottommost:
            locs.sort(key=lambda l: (-(box(l)["y"] + box(l)["height"]), box(l)["x"]))
        elif self.leftmost:
            locs.sort(key=lambda l: (box(l)["x"], box(l)["y"]))
        elif self.rightmost:
            locs.sort(key=lambda l: (-(box(l)["x"] + box(l)["width"]), box(l)["y"]))
        if self.nth is None:
            return locs[:1]
        return locs

    def slice_nth(self, locs):
        if self.nth is None:
            return locs
        if 0 <= self.nth < len(locs):
            return [locs[self.nth]]
        return []


def selector_namespace(**overrides):
    ns = argparse.Namespace(
        label=None, role=None, id=None, within=None, exact=False, regex=False,
        case_sensitive=False, nth=None, topmost=False, bottommost=False,
        leftmost=False, rightmost=False,
    )
    for key, value in overrides.items():
        setattr(ns, key, value)
    return ns


def dedupe_and_flatten(s, locs, page):
    """Drop duplicate handles and container matches when several remain."""
    if len(locs) < 2 or len(locs) > 40:
        return locs
    handles = []
    for loc in locs:
        try:
            handles.append(loc.element_handle())
        except Exception:
            handles.append(None)
    unique = []
    kept = []
    for loc, handle in zip(locs, handles):
        if handle is None:
            kept.append(loc)
            continue
        duplicate = False
        for other in unique:
            try:
                if page.evaluate("(a, b) => a === b", [handle, other]):
                    duplicate = True
                    break
            except Exception:
                break
        if not duplicate:
            unique.append(handle)
            kept.append(loc)
    if len(kept) < 2:
        return kept
    drop = set()
    for i, a in enumerate(unique):
        if i in drop or a is None:
            continue
        for j, b in enumerate(unique):
            if i == j or j in drop or b is None:
                continue
            try:
                if page.evaluate("(a, b) => a !== b && a.contains(b)", [a, b]):
                    drop.add(i)
            except Exception:
                continue
    return [loc for idx, loc in enumerate(kept) if idx not in drop]


def resolve(s, selector, many=False):
    """Resolve to a list of Locators, applying strict mode unless many=True."""
    page = s.page
    root = page
    if selector.within:
        within_value = selector.within
        if within_value.startswith(("#", ".", "[")):
            within_ns = selector_namespace(id=within_value)
        else:
            within_ns = selector_namespace(label=within_value)
        roots = resolve(s, Selector(within_ns), many=True)
        if not roots:
            raise SelectionMiss(f"--within {within_value!r} matched nothing")
        root = roots[0]
    loc = selector.candidates(root)
    try:
        count = loc.count()
    except Exception as exc:
        raise WebtapError(f"cannot resolve {selector.describe()}: {first_line(exc)}")
    if count == 0:
        raise SelectionMiss(f"no node matching {selector.describe()}")
    if count == 1:
        locs = [loc]
    else:
        locs = [loc.nth(i) for i in range(min(count, 40))]
    locs = selector.filter_locators(locs)
    if len(locs) > 1:
        locs = dedupe_and_flatten(s, locs, page)
    locs = selector.apply_order(locs)
    locs = selector.slice_nth(locs)
    if not locs:
        raise SelectionMiss(f"no node matching {selector.describe()}")
    if len(locs) > 1 and not many:
        raise SelectionMiss(
            f"{len(locs)} matches for {selector.describe()}; "
            f"use --nth or --topmost/--bottommost/--leftmost/--rightmost"
        )
    return locs


def safe_resolve(s, selector):
    """Polling helper: transient browser errors become an empty result."""
    try:
        return resolve(s, selector, many=True)
    except SelectionMiss:
        return []
    except WebtapError:
        raise
    except Exception as exc:
        if is_fatal_message(first_line(exc)):
            raise WebtapError(first_line(exc))
        return []


def describe_match(loc):
    info = {"role": "", "name": "", "tag": "", "bounds": None}
    try:
        info["role"] = loc.evaluate(ROLE_JS)
    except Exception:
        pass
    try:
        info["name"] = loc.evaluate(NAME_JS)
    except Exception:
        pass
    try:
        info["tag"] = loc.evaluate("el => el.tagName.toLowerCase()")
    except Exception:
        pass
    try:
        b = loc.bounding_box()
        if b:
            info["bounds"] = [
                int(b["x"]), int(b["y"]), int(b["width"]), int(b["height"])
            ]
    except Exception:
        pass
    return info


def match_line(info):
    bounds = info.get("bounds")
    bounds_text = f"[{','.join(str(v) for v in bounds)}]" if bounds else "[]"
    return (
        f"role={info.get('role') or '?'} name={info.get('name')!r} "
        f"tag={info.get('tag') or '?'} bounds={bounds_text}"
    )


def center_of(loc):
    try:
        b = loc.bounding_box()
    except Exception:
        b = None
    if not b:
        return None
    return int(b["x"] + b["width"] / 2), int(b["y"] + b["height"] / 2)


def wait_visible(s, selector, timeout, interval=0.5):
    deadline = time.time() + timeout
    while True:
        for loc in safe_resolve(s, selector):
            try:
                if loc.is_visible():
                    return True
            except Exception:
                continue
        if time.time() >= deadline:
            return False
        time.sleep(interval)


def wait_hidden(s, selector, timeout, interval=0.5):
    deadline = time.time() + timeout
    while True:
        visible = False
        for loc in safe_resolve(s, selector):
            try:
                if loc.is_visible():
                    visible = True
                    break
            except Exception:
                continue
        if not visible:
            return True
        if time.time() >= deadline:
            return False
        time.sleep(interval)


class Session:
    """Lazy browser session; launches on first page access."""

    def __init__(self, cfg, log):
        self.cfg = cfg
        self.log = log
        self.launched = False
        self.state_dirty = False
        self.last_match = None
        self._primed = False
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    def prime(self):
        """Reopen the last page for commands that do not navigate themselves."""
        if self._primed:
            return
        self._primed = True
        target = self.last_url()
        if not target:
            return
        try:
            self.page.goto(
                target, wait_until="load",
                timeout=int(self.cfg["timeout_default"] * 1000),
            )
        except Exception as exc:
            reason = first_line(exc)
            if is_fatal_message(reason):
                raise WebtapError(reason)
            print(f"warning: cannot reopen {target}: {reason}", file=sys.stderr)

    @property
    def page(self):
        if self._page is None:
            self._start()
        return self._page

    def page_alive(self):
        try:
            return self._page is not None and not self._page.is_closed()
        except Exception:
            return False

    def _start(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise WebtapError(
                "playwright is not installed; run: "
                "pip install playwright && playwright install chromium"
            )
        workdir = workdir_of(self.cfg)
        os.makedirs(workdir, exist_ok=True)
        try:
            self._pw = sync_playwright().start()
            browser_type = getattr(self._pw, self.cfg["browser"])
            try:
                self._browser = browser_type.launch(
                    headless=not self.cfg.get("headed", False)
                )
            except Exception as exc:
                raise WebtapError(
                    f"cannot launch {self.cfg['browser']}: {first_line(exc)}"
                )
            context_kwargs = {
                "viewport": {
                    "width": int(self.cfg["viewport"][0]),
                    "height": int(self.cfg["viewport"][1]),
                }
            }
            state_file = self.cfg["state_file"]
            if os.path.isfile(state_file):
                context_kwargs["storage_state"] = state_file
            self._context = self._browser.new_context(**context_kwargs)
            self._page = self._context.new_page()
            self._page.set_default_timeout(int(self.cfg["timeout_default"] * 1000))
            self._attach_listeners(workdir)
            self.launched = True
        except WebtapError:
            self._cleanup()
            raise
        except Exception as exc:
            self._cleanup()
            raise WebtapError(f"browser session failed: {first_line(exc)}")

    def _attach_listeners(self, workdir):
        console_log = os.path.join(workdir, "console.log")
        network_log = os.path.join(workdir, "network.log")
        starts = {}

        def on_console(msg):
            try:
                append_jsonl(
                    console_log,
                    {"ts": time.time(), "level": msg.type, "text": msg.text},
                )
            except Exception:
                pass

        def on_pageerror(err):
            append_jsonl(
                console_log,
                {"ts": time.time(), "level": "pageerror", "text": str(err)},
            )

        def on_request(req):
            if req.url.startswith(("http://", "https://")):
                starts[req] = time.time()

        def on_requestfinished(req):
            if not req.url.startswith(("http://", "https://")):
                return
            start = starts.pop(req, time.time())
            status = 0
            try:
                response = req.response()
                status = response.status if response else 0
            except Exception:
                status = 0
            append_jsonl(
                network_log,
                {
                    "ts": time.time(),
                    "method": req.method,
                    "url": redact_url(req.url),
                    "status": status,
                    "ms": int((time.time() - start) * 1000),
                },
            )

        def on_requestfailed(req):
            if not req.url.startswith(("http://", "https://")):
                return
            start = starts.pop(req, time.time())
            failure = ""
            try:
                failure = req.failure or ""
            except Exception:
                failure = ""
            append_jsonl(
                network_log,
                {
                    "ts": time.time(),
                    "method": req.method,
                    "url": redact_url(req.url),
                    "status": "FAILED",
                    "ms": int((time.time() - start) * 1000),
                    "error": failure,
                },
            )

        self._page.on("console", on_console)
        self._page.on("pageerror", on_pageerror)
        self._page.on("request", on_request)
        self._page.on("requestfinished", on_requestfinished)
        self._page.on("requestfailed", on_requestfailed)

    def save_state(self):
        if not (self.launched and self.state_dirty and self._context):
            return
        path = self.cfg["state_file"]
        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            self._context.storage_state(path=path)
            self.log.write("state saved")
        except Exception as exc:
            print(
                f"warning: cannot save state to {path}: {first_line(exc)}",
                file=sys.stderr,
            )

    def last_url(self):
        path = os.path.join(workdir_of(self.cfg), "last.json")
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh).get("url")
        except (OSError, json.JSONDecodeError):
            return None

    def remember_url(self, url):
        path = os.path.join(workdir_of(self.cfg), "last.json")
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"url": url}, fh)
        except OSError:
            pass

    def log_path(self, name):
        return os.path.join(workdir_of(self.cfg), name)

    def _cleanup(self):
        for closer in (
            getattr(self._context, "close", None),
            getattr(self._browser, "close", None),
            getattr(self._pw, "stop", None),
        ):
            if closer:
                try:
                    closer()
                except Exception:
                    pass
        self._page = None
        self._context = None
        self._browser = None
        self._pw = None

    def shutdown(self):
        self.save_state()
        self._cleanup()


def safe_url(s):
    try:
        return s.page.url
    except Exception:
        return ""


def safe_title(s):
    try:
        return s.page.title()
    except Exception:
        return ""


def write_evidence(s, args, rc, step_dir=None):
    if not s.cfg.get("evidence_enabled", True):
        return None
    if not s.page_alive():
        return None
    root = step_dir or s.cfg["evidence_dir"]
    try:
        os.makedirs(root, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"
        stem = unique_stem(root, f"{stamp}-{args.cmd}")
        png_path = os.path.join(root, stem + ".png")
        shot_ok = True
        try:
            s.page.screenshot(path=png_path)
        except Exception:
            shot_ok = False
        receipt = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "cmd": args.cmd,
            "args": redact_args(vars(args)),
            "url": safe_url(s),
            "title": safe_title(s),
            "match": s.last_match,
            "exit": rc,
            "screenshot": os.path.basename(png_path) if shot_ok else None,
        }
        with open(os.path.join(root, stem + ".json"), "w", encoding="utf-8") as fh:
            json.dump(receipt, fh, ensure_ascii=False, indent=2)
        return stem
    except Exception as exc:
        print(f"warning: evidence write failed: {first_line(exc)}", file=sys.stderr)
        return None


def aria_snapshot(page):
    try:
        return page.locator("body").aria_snapshot()
    except AttributeError:
        raise WebtapError("aria snapshots need Playwright 1.49+; upgrade playwright")
    except Exception as exc:
        raise WebtapError(f"cannot take an aria snapshot: {first_line(exc)}")


def selector_from_value(value):
    """A bare CLI value that may be CSS (#, ., [) or a label."""
    if value.startswith(("#", ".", "[")):
        return Selector(selector_namespace(id=value))
    return Selector(selector_namespace(label=value))


def navigate(s, url, timeout):
    page = s.page
    page.goto(url, wait_until="load", timeout=int(timeout * 1000))
    try:
        page.wait_for_load_state("networkidle", timeout=min(5000, int(timeout * 1000)))
    except Exception:
        # Websockets (dev servers, HMR) keep the page non-idle forever; the
        # load event is the real gate, idle is a bonus.
        print("networkidle not reached; continuing", file=sys.stderr)
    s.remember_url(page.url)


def cmd_goto(args, s):
    url = join_url(s.cfg.get("base_url"), args.url)
    navigate(s, url, s.cfg["timeout_default"])
    s.state_dirty = True
    print(f"navigated to {s.page.url} | title: {s.page.title()!r}")
    s.log.write(f"goto {url}")
    return 0


def cmd_url(args, s):
    target = args.url or s.last_url()
    if not target:
        raise SelectionMiss("no URL: pass one or run goto first")
    navigate(
        s,
        join_url(s.cfg.get("base_url"), args.url) if args.url else target,
        s.cfg["timeout_default"],
    )
    print(s.page.url)
    return 0


def cmd_title(args, s):
    target = args.url or s.last_url()
    if not target:
        raise SelectionMiss("no URL: pass one or run goto first")
    navigate(
        s,
        join_url(s.cfg.get("base_url"), args.url) if args.url else target,
        s.cfg["timeout_default"],
    )
    print(s.page.title())
    return 0


def cmd_dump_labels(args, s):
    sel_given = args.label is not None or args.id is not None or args.role is not None
    if getattr(args, "tree", False):
        print(aria_snapshot(s.page))
        return 0
    if sel_given:
        locs = resolve(s, Selector(args), many=True)
        infos = [describe_match(loc) for loc in locs[: args.limit]]
    else:
        infos = s.page.evaluate(ENUM_JS, args.limit)
    if args.json:
        print(json.dumps(infos, ensure_ascii=False))
    else:
        for info in infos:
            print(match_line(info))
    s.log.write(f"dump-labels -> {len(infos)} nodes")
    return 0


def cmd_find(args, s):
    locs = resolve(s, Selector(args))
    info = describe_match(locs[0])
    if args.json:
        print(json.dumps(info, ensure_ascii=False))
    else:
        print(match_line(info))
    s.log.write("find -> hit")
    return 0


def cmd_tap(args, s):
    timeout_ms = int(s.cfg["timeout_default"] * 1000)
    if args.xy:
        x, y = args.xy
        if args.dry_run:
            print(f"would tap raw ({x},{y})")
            return 0
        s.page.mouse.click(x, y)
        s.state_dirty = True
        print(f"tapped raw ({x},{y})")
        return 0
    target = args.target or []
    if len(target) == 2 and all(t.lstrip("-").isdigit() for t in target):
        x, y = int(target[0]), int(target[1])
        if args.dry_run:
            print(f"would tap raw ({x},{y})")
            return 0
        s.page.mouse.click(x, y)
        s.state_dirty = True
        print(f"tapped raw ({x},{y})")
        return 0
    if target:
        args.label = " ".join(target)
    sel = Selector(args)
    attempts = max(1, args.retry)
    for attempt in range(1, attempts + 1):
        try:
            loc = resolve(s, sel)[0]
        except SelectionMiss:
            if attempt < attempts:
                time.sleep(args.retry_delay)
                continue
            raise
        info = describe_match(loc)
        if args.dry_run:
            print(f"would tap {match_line(info)}")
            return 0
        try:
            loc.scroll_into_view_if_needed(timeout=timeout_ms)
            loc.click(timeout=timeout_ms)
        except Exception as exc:
            reason = first_line(exc)
            if attempt < attempts and not is_fatal_message(reason):
                time.sleep(args.retry_delay)
                continue
            raise SelectionMiss(f"tap failed: {reason}")
        s.last_match = info
        s.state_dirty = True
        print(f"tapped {match_line(info)}")
        s.log.write(f"tap {sel.describe()} attempt {attempt}")
        if args.expect:
            esc = selector_namespace(
                label=args.expect,
                exact=args.expect_exact,
                regex=args.expect_regex,
                case_sensitive=args.case_sensitive,
            )
            if wait_visible(s, Selector(esc), args.expect_timeout):
                print(f"expect ok: {args.expect!r} visible")
                return 0
            print(
                f"EXPECT FAILED: {args.expect!r} not visible after "
                f"{args.expect_timeout}s",
                file=sys.stderr,
            )
            s.log.write(f"expect {args.expect!r} -> failed")
            return 1
        return 0
    return 1


def cmd_wait(args, s):
    sel = Selector(args)
    timeout = args.timeout if args.timeout is not None else s.cfg["timeout_default"]
    if wait_visible(s, sel, timeout):
        print(f"wait ok: {sel.describe()} visible")
        s.log.write(f"wait {sel.describe()} -> ok")
        return 0
    print(f"TIMEOUT: {sel.describe()} not visible within {timeout}s", file=sys.stderr)
    s.log.write("wait -> timeout")
    return 1


def cmd_wait_gone(args, s):
    sel = Selector(args)
    timeout = args.timeout if args.timeout is not None else s.cfg["timeout_default"]
    if wait_hidden(s, sel, timeout):
        print(f"wait-gone ok: {sel.describe()} no longer visible")
        s.log.write(f"wait-gone {sel.describe()} -> ok")
        return 0
    print(f"TIMEOUT: {sel.describe()} still visible within {timeout}s", file=sys.stderr)
    s.log.write("wait-gone -> timeout")
    return 1


def cmd_wait_stable(args, s):
    page = s.page
    if args.network_idle:
        try:
            page.wait_for_load_state("networkidle", timeout=int(args.timeout * 1000))
        except Exception:
            print("warning: networkidle not reached; continuing to DOM stability", file=sys.stderr)
    deadline = time.time() + args.timeout
    last_sig = None
    stable = 0
    while time.time() < deadline:
        try:
            sig = page.evaluate(SIG_JS)
        except Exception as exc:
            reason = first_line(exc)
            if is_fatal_message(reason):
                raise WebtapError(reason)
            sig = None
        if sig is not None:
            if sig == last_sig:
                stable += 1
            else:
                stable = 1
                last_sig = sig
            if stable >= args.rounds:
                print(f"stable after {stable} identical signatures")
                if args.save:
                    with open(args.save, "w", encoding="utf-8") as fh:
                        fh.write(aria_snapshot(page))
                    print(f"aria snapshot saved to {args.save}")
                s.log.write("wait-stable -> ok")
                return 0
        time.sleep(args.interval)
    print(f"TIMEOUT: DOM never stabilized within {args.timeout}s", file=sys.stderr)
    s.log.write("wait-stable -> timeout")
    return 1


def cmd_scroll_to(args, s):
    sel = Selector(args)
    locs = resolve(s, sel, many=True)
    loc = locs[0]
    try:
        loc.scroll_into_view_if_needed(timeout=int(s.cfg["timeout_default"] * 1000))
    except Exception as exc:
        raise SelectionMiss(f"scroll-to failed: {first_line(exc)}")
    info = describe_match(loc)
    s.last_match = info
    print(f"scrolled to {match_line(info)}")
    return 0


def cmd_scroll(args, s):
    page = s.page
    viewport = page.viewport_size or {"width": 1280, "height": 800}
    page.mouse.move(viewport["width"] // 2, viewport["height"] // 2)
    pixels = args.pixels
    if args.direction == "up":
        page.mouse.wheel(0, -pixels)
    elif args.direction == "down":
        page.mouse.wheel(0, pixels)
    elif args.direction == "left":
        page.mouse.wheel(-pixels, 0)
    else:
        page.mouse.wheel(pixels, 0)
    time.sleep(0.3)
    print(f"scrolled {args.direction} {pixels}px")
    s.log.write(f"scroll {args.direction} {pixels}")
    return 0


def pick_field(locs):
    """Prefer a real form control when a label and its control both match."""
    for loc in locs:
        try:
            tag = loc.evaluate("el => el.tagName.toLowerCase()")
        except Exception:
            continue
        if tag in ("input", "textarea", "select"):
            return loc
    for loc in locs:
        try:
            if loc.evaluate("el => el.isContentEditable"):
                return loc
        except Exception:
            continue
    return locs[0]


def cmd_text(args, s):
    value = " ".join(args.value)
    if args.into:
        locs = resolve(s, Selector(selector_namespace(label=args.into)), many=True)
        loc = pick_field(locs)
        try:
            loc.click(timeout=int(s.cfg["timeout_default"] * 1000))
            if args.clear:
                loc.fill("")
            loc.fill(value)
        except Exception as exc:
            raise SelectionMiss(f"cannot fill {args.into!r}: {first_line(exc)}")
        s.last_match = describe_match(loc)
        s.state_dirty = True
        print(f"typed {value!r} into {args.into!r}")
    else:
        page = s.page
        if not page.evaluate(ACTIVE_JS):
            raise WebtapError("no field focused; pass --into LABEL")
        if args.clear:
            page.keyboard.press("Control+A")
            page.keyboard.press("Delete")
        page.keyboard.insert_text(value)
        s.state_dirty = True
        print(f"typed {value!r} into the focused field")
    s.log.write(f"text {value!r} -> typed")
    return 0


def cmd_clear(args, s):
    if args.into:
        locs = resolve(s, Selector(selector_namespace(label=args.into)), many=True)
        loc = pick_field(locs)
        try:
            loc.fill("")
        except Exception as exc:
            raise SelectionMiss(f"cannot clear {args.into!r}: {first_line(exc)}")
        s.last_match = describe_match(loc)
        print(f"cleared {args.into!r}")
    else:
        page = s.page
        if not page.evaluate(ACTIVE_JS):
            raise WebtapError("no field focused; pass --into LABEL")
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
        print("cleared the focused field")
    s.state_dirty = True
    s.log.write("clear -> ok")
    return 0


def cmd_key(args, s):
    key = normalize_key(args.name)
    s.page.keyboard.press(key)
    time.sleep(0.2)
    s.state_dirty = True
    print(f"key {key}")
    s.log.write(f"key {key}")
    return 0


def cmd_shot(args, s):
    if args.element and args.full_page:
        raise WebtapError("--element and --full-page are mutually exclusive")
    name = args.name
    stem, ext = os.path.splitext(name)
    fmt = args.format
    if ext.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        inferred = "jpeg" if ext.lower() in (".jpg", ".jpeg") else ext.lower().lstrip(".")
        fmt = fmt or inferred
    fmt = fmt or "png"
    path = name if ext.lower() in (".png", ".jpg", ".jpeg", ".webp") else f"{name}.{fmt}"
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if args.element:
        loc = resolve(s, selector_from_value(args.element))[0]
        try:
            loc.screenshot(path=path, type=fmt)
        except Exception as exc:
            raise SelectionMiss(f"element screenshot failed: {first_line(exc)}")
    else:
        s.page.screenshot(path=path, full_page=args.full_page, type=fmt)
    print(f"saved {path}")
    s.log.write(f"shot {path}")
    return 0


def cmd_screen(args, s):
    page = s.page
    viewport = page.viewport_size or {}
    dpr = page.evaluate("() => window.devicePixelRatio")
    print(
        f"viewport {viewport.get('width')}x{viewport.get('height')} "
        f"dpr={dpr} browser={s.cfg['browser']}"
    )
    s.log.write(f"screen {viewport.get('width')}x{viewport.get('height')}")
    return 0


def cmd_console(args, s):
    entries = read_jsonl(s.log_path("console.log"))
    now = time.time()
    if args.since is not None:
        entries = [e for e in entries if now - float(e.get("ts", 0)) <= args.since]
    entries = entries[-args.lines:]
    if not entries:
        print("no console messages recorded")
        return 0
    for entry in entries:
        print(
            f"[{format_ts(float(entry.get('ts', 0)))}] "
            f"{entry.get('level', '?')}: {entry.get('text', '')}"
        )
    s.log.write(f"console -> {len(entries)} messages")
    return 0


def request_line(entry):
    status = entry.get("status", "?")
    ms = entry.get("ms", 0)
    return f"{entry.get('method', '?')} {entry.get('url', '?')} {status} {ms}ms"


def cmd_network(args, s):
    entries = read_jsonl(s.log_path("network.log"))
    now = time.time()
    if args.since is not None:
        entries = [e for e in entries if now - float(e.get("ts", 0)) <= args.since]
    if args.filter:
        needle = args.filter.lower()
        entries = [e for e in entries if needle in str(e.get("url", "")).lower()]
    entries = entries[-args.lines:]
    if not entries:
        print("no network requests recorded")
        return 0
    for entry in entries:
        print(f"[{format_ts(float(entry.get('ts', 0)))}] {request_line(entry)}")
    s.log.write(f"network -> {len(entries)} requests")
    return 0


def load_flow(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        raise WebtapError(f"cannot read flow {path!r}: {first_line(exc)}")
    except json.JSONDecodeError as exc:
        raise WebtapError(f"flow {path!r} is not valid JSON: {exc}")
    if not isinstance(data, list) or not data:
        raise WebtapError(f"flow {path!r} must be a non-empty JSON array of steps")
    return data


def write_flow_summary(root, index, steps_total, duration, flow_path):
    payload = {
        "flow": flow_path,
        "steps_total": steps_total,
        "steps_run": len(index),
        "passed": sum(1 for e in index if e["exit"] == 0),
        "failed": sum(1 for e in index if e["exit"] != 0),
        "duration_s": round(duration, 2),
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "steps": index,
    }
    with open(os.path.join(root, "index.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    lines = [
        "# Web acceptance notes",
        "",
        f"Flow: `{flow_path}`",
        f"Result: {payload['passed']}/{steps_total} steps passed"
        f" | {payload['duration_s']}s | {payload['ts']}",
        "",
        "| # | Command | Exit | Duration (s) | Evidence |",
        "|---|---|---|---|---|",
    ]
    for entry in index:
        lines.append(
            f"| {entry['step']} | `{entry['cmd']}` | {entry['exit']} "
            f"| {entry['duration_s']} | {entry['dir']}/ |"
        )
    lines.append("")
    with open(os.path.join(root, "TEST_NOTES.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def cmd_flow(args, s):
    steps = load_flow(args.file)
    first = steps[0].get("cmd") if isinstance(steps[0], dict) else None
    if str(first) not in ("goto", "url", "title"):
        s.prime()
    parser = build_parser()
    stamp = time.strftime("flow-%Y%m%d-%H%M%S")
    root = os.path.join(s.cfg["evidence_dir"], stamp)
    index = []
    rc_total = 0
    started = time.time()
    for number, step in enumerate(steps, 1):
        step_dir = os.path.join(root, f"step-{number:02d}")
        try:
            argv = step_argv(step)
            step_args = parser.parse_args(argv)
        except WebtapError as exc:
            print(f"ERROR: step {number}: {exc}", file=sys.stderr)
            rc_total = 2
            break
        except SystemExit:
            print(f"ERROR: step {number}: invalid step {step!r}", file=sys.stderr)
            rc_total = 2
            break
        step_args.state = getattr(args, "state", None)
        step_args.headed = getattr(args, "headed", False)
        step_args.browser = getattr(args, "browser", None)
        step_args.verbose = getattr(args, "verbose", False)
        step_args.log = getattr(args, "log", None)
        step_args.no_evidence = getattr(args, "no_evidence", False)
        console_start = time.time()
        step_start = time.time()
        rc = run_command(step_args, s, evidence=False)
        duration = time.time() - step_start
        if s.cfg.get("evidence_enabled", True):
            try:
                os.makedirs(step_dir, exist_ok=True)
                if s.page_alive():
                    try:
                        s.page.screenshot(path=os.path.join(step_dir, "screenshot.png"))
                    except Exception:
                        pass
                receipt = {
                    "step": number,
                    "cmd": step_args.cmd,
                    "argv": argv,
                    "exit": rc,
                    "duration_s": round(duration, 2),
                    "url": safe_url(s),
                    "title": safe_title(s),
                    "match": s.last_match,
                    "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                with open(
                    os.path.join(step_dir, "receipt.json"), "w", encoding="utf-8"
                ) as fh:
                    json.dump(receipt, fh, ensure_ascii=False, indent=2)
                tail = [
                    e for e in read_jsonl(s.log_path("console.log"))
                    if float(e.get("ts", 0)) >= console_start
                ][-20:]
                with open(
                    os.path.join(step_dir, "console-tail.txt"), "w", encoding="utf-8"
                ) as fh:
                    for entry in tail:
                        fh.write(
                            f"[{format_ts(float(entry.get('ts', 0)))}] "
                            f"{entry.get('level', '?')}: {entry.get('text', '')}\n"
                        )
            except OSError as exc:
                print(f"warning: step evidence failed: {first_line(exc)}", file=sys.stderr)
        index.append(
            {
                "step": number,
                "cmd": step_args.cmd,
                "exit": rc,
                "duration_s": round(duration, 2),
                "dir": f"step-{number:02d}",
            }
        )
        if rc != 0:
            rc_total = rc
            break
    if s.cfg.get("evidence_enabled", True):
        try:
            write_flow_summary(root, index, len(steps), time.time() - started, args.file)
        except OSError as exc:
            print(f"warning: flow summary failed: {first_line(exc)}", file=sys.stderr)
    verdict = "passed" if rc_total == 0 else "failed"
    where = f" | evidence: {root}" if s.cfg.get("evidence_enabled", True) else ""
    print(f"flow {verdict}: {sum(1 for e in index if e['exit'] == 0)}/{len(steps)} steps{where}")
    s.log.write(f"flow {verdict} ({len(index)}/{len(steps)} steps)")
    return rc_total


DISPATCH = {
    "goto": cmd_goto,
    "url": cmd_url,
    "title": cmd_title,
    "dump-labels": cmd_dump_labels,
    "find": cmd_find,
    "tap": cmd_tap,
    "wait": cmd_wait,
    "wait-gone": cmd_wait_gone,
    "wait-stable": cmd_wait_stable,
    "scroll-to": cmd_scroll_to,
    "scroll": cmd_scroll,
    "text": cmd_text,
    "clear": cmd_clear,
    "key": cmd_key,
    "shot": cmd_shot,
    "screen": cmd_screen,
    "console": cmd_console,
    "network": cmd_network,
    "flow": cmd_flow,
}


def run_command(args, s, evidence=True):
    fn = DISPATCH.get(args.cmd)
    if fn is None:
        raise WebtapError(f"unknown command {args.cmd!r}")
    if args.cmd in PRIME_VERBS:
        s.prime()
    try:
        rc = fn(args, s)
    except SelectionMiss as exc:
        print(f"MISS: {exc}", file=sys.stderr)
        s.log.write(f"miss: {exc}")
        rc = 1
    except WebtapError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        s.log.write(f"error: {exc}")
        rc = 2
    except Exception as exc:
        rc = classify_exception(exc)
        print(f"ERROR: {first_line(exc)}", file=sys.stderr)
        s.log.write(f"error: {first_line(exc)}")
    if evidence and args.cmd in EVIDENCE_VERBS and s.launched:
        write_evidence(s, args, rc)
    return rc


def main(argv=None):
    args = build_parser().parse_args(argv)
    log = Logger(getattr(args, "log", None))
    if args.cmd == "version":
        print(VERSION)
        return 0
    if args.cmd == "selftest":
        selftest()
        return 0
    try:
        cfg, warnings = load_config()
        for warning in warnings:
            print(f"warning: {warning}", file=sys.stderr)
        cfg = apply_cli(cfg, args)
        session = Session(cfg, log)
        try:
            rc = run_command(args, session)
        finally:
            session.shutdown()
        log.write(f"exit {rc}")
        return rc
    except WebtapError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        log.write(f"error: {exc}")
        return 2


def build_parser():
    p = argparse.ArgumentParser(
        prog="webtap.py",
        description=__doc__.splitlines()[0],
        epilog=(
            "examples:\n"
            "  webtap.py goto http://localhost:3000\n"
            "  webtap.py tap \"Sign in\" --expect \"Dashboard\"\n"
            "  webtap.py text --into \"Email\" \"me@example.com\"\n"
            "  webtap.py flow acceptance.json\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--state", default=None, metavar="FILE",
                   help="storage-state file (default .webtap/state.json)")
    p.add_argument("--headed", action="store_true", help="show the browser window")
    p.add_argument("--browser", choices=BROWSERS, default=None,
                   help="chromium (default), firefox, or webkit")
    p.add_argument("--verbose", action="store_true", help="explain misses")
    p.add_argument("--log", default=None, metavar="FILE",
                   help="append an audit line per run")
    p.add_argument("--no-evidence", action="store_true",
                   help="do not write screenshots or receipts")
    sub = p.add_subparsers(dest="cmd", required=True)
    subs = []

    def new_sub(name, **kw):
        sp = sub.add_parser(name, **kw)
        subs.append(sp)
        return sp

    def add_globals(sp):
        # Mirrored so global options work on either side of the subcommand;
        # SUPPRESS keeps values set before the subcommand from being clobbered.
        sp.add_argument("--state", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        sp.add_argument("--headed", action="store_true", default=argparse.SUPPRESS,
                        help=argparse.SUPPRESS)
        sp.add_argument("--browser", choices=BROWSERS, default=argparse.SUPPRESS,
                        help=argparse.SUPPRESS)
        sp.add_argument("--verbose", action="store_true", default=argparse.SUPPRESS,
                        help=argparse.SUPPRESS)
        sp.add_argument("--log", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        sp.add_argument("--no-evidence", action="store_true",
                        default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    def add_selector(sp, label=True):
        if label:
            sp.add_argument("label", nargs="?")
        sp.add_argument("--role", default=None, help="ARIA role filter")
        sp.add_argument("--id", default=None, help="CSS selector instead of a label")
        sp.add_argument("--within", default=None, help="scope to a parent (#css or label)")
        mode = sp.add_mutually_exclusive_group()
        mode.add_argument("--exact", action="store_true")
        mode.add_argument("--regex", action="store_true")
        sp.add_argument("--case-sensitive", action="store_true")
        sp.add_argument("--nth", type=int, default=None)
        sp.add_argument("--topmost", action="store_true")
        sp.add_argument("--bottommost", action="store_true")
        sp.add_argument("--leftmost", action="store_true")
        sp.add_argument("--rightmost", action="store_true")

    g = new_sub("goto", help="navigate and wait for load")
    g.add_argument("url")

    u = new_sub("url", help="print the current URL")
    u.add_argument("url", nargs="?")

    ti = new_sub("title", help="print the page title")
    ti.add_argument("url", nargs="?")

    dl = new_sub("dump-labels", help="list matching elements")
    add_selector(dl)
    dl.add_argument("--json", action="store_true")
    dl.add_argument("--tree", action="store_true", help="ARIA snapshot text instead")
    dl.add_argument("--limit", type=int, default=200)

    f = new_sub("find", help="print first match, exit 1 on miss")
    add_selector(f)
    f.add_argument("--json", action="store_true")

    t = new_sub("tap", help="click a match, coordinates, or --xy")
    t.add_argument("target", nargs="*")
    t.add_argument("--xy", nargs=2, type=int, metavar=("X", "Y"))
    add_selector(t, label=False)
    t.add_argument("--retry", type=int, default=1, help="attempts, default 1")
    t.add_argument("--retry-delay", type=float, default=0.4)
    t.add_argument("--dry-run", action="store_true")
    t.add_argument("--expect", default=None, help="verify this is visible after tapping")
    e_mode = t.add_mutually_exclusive_group()
    e_mode.add_argument("--expect-exact", action="store_true")
    e_mode.add_argument("--expect-regex", action="store_true")
    t.add_argument("--expect-timeout", type=float, default=5)

    w = new_sub("wait", help="poll until visible")
    add_selector(w)
    w.add_argument("--timeout", type=float, default=None)

    wg = new_sub("wait-gone", help="poll until hidden or detached")
    add_selector(wg)
    wg.add_argument("--timeout", type=float, default=None)

    ws = new_sub("wait-stable", help="wait until the DOM signature settles")
    ws.add_argument("--network-idle", action="store_true")
    ws.add_argument("--rounds", type=int, default=3)
    ws.add_argument("--interval", type=float, default=1.0)
    ws.add_argument("--timeout", type=float, default=30.0)
    ws.add_argument("--save", default=None, metavar="FILE")

    st = new_sub("scroll-to", help="scroll the first match into view")
    add_selector(st)

    sc = new_sub("scroll", help="wheel-scroll the viewport")
    sc.add_argument("direction", choices=["up", "down", "left", "right"])
    sc.add_argument("--pixels", type=int, default=600)

    tx = new_sub("text", help="fill a field (or the focused one)")
    tx.add_argument("value", nargs="+")
    tx.add_argument("--into", default=None, metavar="LABEL")
    tx.add_argument("--clear", action="store_true")

    cl = new_sub("clear", help="clear a field (or the focused one)")
    cl.add_argument("--into", default=None, metavar="LABEL")

    k = new_sub("key", help="press a key")
    k.add_argument("name")

    sh = new_sub("shot", help="screenshot to <name>.<ext>")
    sh.add_argument("name")
    sh.add_argument("--full-page", action="store_true")
    sh.add_argument("--element", default=None, metavar="SEL")
    sh.add_argument("--format", choices=["png", "jpeg", "webp"], default=None)

    co = new_sub("console", help="recent console messages from the rolling log")
    co.add_argument("--since", type=float, default=None)
    co.add_argument("--lines", type=int, default=100)

    ne = new_sub("network", help="recent requests from the rolling log")
    ne.add_argument("--since", type=float, default=None)
    ne.add_argument("--lines", type=int, default=100)
    ne.add_argument("--filter", default=None, metavar="PAT")

    fl = new_sub("flow", help="run a step sequence in one browser session")
    fl.add_argument("file")

    new_sub("screen", help="viewport size, dpr, and browser")
    new_sub("selftest", help="internal checks, no browser needed")
    new_sub("version", help="print the tool version")

    for sp in subs:
        add_globals(sp)
    return p


def selftest():
    checks = 0

    def check(cond, label):
        nonlocal checks
        if not cond:
            raise AssertionError(f"selftest failed: {label}")
        checks += 1

    samples = [
        (["goto", "http://x/"], "goto"),
        (["url"], "url"),
        (["url", "login"], "url"),
        (["title"], "title"),
        (["dump-labels"], "dump-labels"),
        (["dump-labels", "Save", "--json"], "dump-labels"),
        (["dump-labels", "--tree"], "dump-labels"),
        (["find", "Save"], "find"),
        (["find", "--role", "button"], "find"),
        (["tap", "Save"], "tap"),
        (["tap", "10", "20"], "tap"),
        (["tap", "--xy", "10", "20"], "tap"),
        (["wait", "X"], "wait"),
        (["wait-gone", "X"], "wait-gone"),
        (["wait-stable", "--network-idle", "--rounds", "2"], "wait-stable"),
        (["scroll-to", "X"], "scroll-to"),
        (["scroll", "down", "--pixels", "300"], "scroll"),
        (["text", "hello"], "text"),
        (["text", "x", "--into", "Title", "--clear"], "text"),
        (["clear"], "clear"),
        (["clear", "--into", "Title"], "clear"),
        (["key", "TAB"], "key"),
        (["shot", "x", "--full-page"], "shot"),
        (["shot", "x", "--element", "#hero"], "shot"),
        (["console", "--since", "5"], "console"),
        (["network", "--filter", "api/"], "network"),
        (["flow", "x.json"], "flow"),
        (["screen"], "screen"),
        (["version"], "version"),
    ]
    for argv, expected in samples:
        parsed = build_parser().parse_args(argv)
        check(parsed.cmd == expected, f"parser smoke {argv[0]} {argv[1:]}")

    parser = build_parser()
    check(parser.parse_args(["--state", "s.json", "find", "X"]).state == "s.json",
          "global --state before subcommand")
    check(parser.parse_args(["find", "X", "--state", "s.json"]).state == "s.json",
          "global --state after subcommand")
    check(parser.parse_args(["find", "X", "--headed"]).headed is True,
          "global --headed after subcommand")
    check(parser.parse_args(["--browser", "firefox", "goto", "u"]).browser == "firefox",
          "global --browser before subcommand")
    check(parser.parse_args(["tap", "X", "--retry", "3"]).retry == 3,
          "tap retry parses")
    check(parser.parse_args(["tap", "X", "--nth", "2"]).nth == 2,
          "tap nth parses")
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            build_parser().parse_args(["find", "X", "--exact", "--regex"])
            check(False, "exact plus regex rejected")
        except SystemExit as exc:
            check(exc.code == 2, "exact plus regex exit code")
        try:
            build_parser().parse_args(["goto"])
            check(False, "goto requires url")
        except SystemExit as exc:
            check(exc.code == 2, "missing url exit code")
        try:
            build_parser().parse_args(["flow"])
            check(False, "flow requires file")
        except SystemExit as exc:
            check(exc.code == 2, "missing flow file exit code")

    ns = selector_namespace()
    check(ns.label is None and ns.nth is None and ns.role is None,
          "selector namespace defaults")
    check(selector_namespace(label="x", nth=1).nth == 1, "selector namespace overrides")
    sel = Selector(selector_namespace(label="Save", exact=True))
    check(sel.needs_python_filter() is True, "exact case-insensitive needs filter")
    sel = Selector(selector_namespace(label="Save", exact=True, case_sensitive=True))
    check(sel.needs_python_filter() is False, "exact case-sensitive native")
    sel = Selector(selector_namespace(label="Save"))
    check(sel.needs_python_filter() is False, "plain substring native")
    check(sel.describe() == "substring 'Save'", "selector describe substring")
    check(Selector(selector_namespace(label="x", role="button", regex=True)).describe()
          == "button regex 'x'", "selector describe role regex")
    check(Selector(selector_namespace(id="#save")).describe() == "id '#save'",
          "selector describe id")

    check(match_name("Save & Exit", "save", False, False), "CI substring match")
    check(not match_name("Save & Exit", "save", True, False), "exact mismatch")
    check(match_name("Save", "Save", True, False), "exact CI match")
    check(match_name("save", "Save", True, False), "exact CI folds case")
    check(not match_name("save", "Save", True, True), "exact CS miss")
    check(match_name("save me", "s", False, True), "CS substring hit")

    check(css_attr_escape('a"b') == 'a\\"b', "css quote escape")
    check(css_attr_escape("a\\b") == "a\\\\b", "css backslash escape")

    red = redact_url("http://x/a?token=abc&page=2&api_key=zzz")
    check("token=REDACTED" in red and "page=2" in red and "api_key=REDACTED" in red,
          "url redaction")
    check(redact_url("http://x/plain") == "http://x/plain", "url without query untouched")
    masked = redact_args({"password": "x", "name": "y"})
    check(masked["password"] == "REDACTED" and masked["name"] == "y", "arg redaction")

    check(normalize_key("ENTER") == "Enter", "key alias enter")
    check(normalize_key("arrowdown") == "ArrowDown", "key alias arrowdown")
    check(normalize_key("Control+A") == "Control+A", "key modifier passthrough")
    check(normalize_key("ctrl+shift+t") == "Control+Shift+t", "key multi modifier")
    check(normalize_key("F5") == "F5", "key function row")
    try:
        normalize_key("not a key")
        check(False, "unknown key rejected")
    except WebtapError:
        check(True, "unknown key rejected")

    check(join_url("http://localhost:3000/", "login") == "http://localhost:3000/login",
          "relative join")
    check(join_url("http://localhost:3000/app", "login")
          == "http://localhost:3000/app/login", "relative join without slash")
    check(join_url(None, "https://x/y") == "https://x/y", "absolute passthrough")
    try:
        join_url(None, "login")
        check(False, "relative needs base")
    except WebtapError:
        check(True, "relative needs base")

    check(step_argv({"cmd": "tap", "label": "Add Series"}) == ["tap", "Add Series"],
          "flow tap argv")
    check(step_argv({"cmd": "shot", "name": "01-library", "full_page": True})
          == ["shot", "01-library", "--full-page"], "flow shot argv")
    check(step_argv({"cmd": "text", "into": "Title", "value": "Solo Leveling"})
          == ["text", "--into", "Title", "Solo Leveling"], "flow text argv")
    check(step_argv({"cmd": "tap", "xy": [10, 20]}) == ["tap", "--xy", "10", "20"],
          "flow xy argv")
    check(step_argv({"cmd": "wait", "label": "X", "timeout": 5})
          == ["wait", "X", "--timeout", "5"], "flow timeout argv")
    check(step_argv({"cmd": "goto", "url": "http://x/"}) == ["goto", "http://x/"],
          "flow goto argv")
    parsed = build_parser().parse_args(step_argv({"cmd": "tap", "label": "Add Series"}))
    check(parsed.cmd == "tap" and parsed.target == ["Add Series"],
          "flow argv round-trips through parser")
    try:
        step_argv({"label": "no cmd"})
        check(False, "flow step needs cmd")
    except WebtapError:
        check(True, "flow step needs cmd")

    with tempfile.TemporaryDirectory() as td:
        cfg, warns = load_config(td, {})
        check(cfg["browser"] == "chromium" and warns == [], "config defaults")
        with open(os.path.join(td, ".webtap.json"), "w", encoding="utf-8") as fh:
            json.dump({"browser": "firefox", "timeout_default": 33}, fh)
        cfg, warns = load_config(td, {})
        check(cfg["browser"] == "firefox" and cfg["timeout_default"] == 33.0,
              "config file overlay")
        cfg, warns = load_config(td, {"WEBTAP_BROWSER": "webkit"})
        check(cfg["browser"] == "webkit", "env beats file")
        cfg, warns = load_config(td, {"WEBTAP_BASE_URL": "http://x/"})
        check(cfg["base_url"] == "http://x/", "env base_url")
        args = build_parser().parse_args(
            ["--browser", "chromium", "--state", "z.json", "find", "X"]
        )
        cfg = apply_cli(cfg, args)
        check(cfg["browser"] == "chromium" and cfg["state_file"] == "z.json",
              "cli beats env")
        with open(os.path.join(td, ".webtap.json"), "w", encoding="utf-8") as fh:
            fh.write("{bad json")
        cfg, warns = load_config(td, {})
        check(any("cannot read config" in w for w in warns), "bad config warns")
        cfg, warns = load_config(td, {"WEBTAP_BROWSER": "netscape"})
        check(cfg["browser"] == "chromium" and any("unknown browser" in w for w in warns),
              "bad browser warns and falls back")

    with tempfile.TemporaryDirectory() as td:
        stem = unique_stem(td, "20260101-000000-000-tap")
        check(stem == "20260101-000000-000-tap", "unique stem first")
        with open(os.path.join(td, stem + ".png"), "w", encoding="utf-8") as fh:
            fh.write("x")
        stem2 = unique_stem(td, "20260101-000000-000-tap")
        check(stem2.endswith("-2"), "unique stem collision suffix")

    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "log.jsonl")
        append_jsonl(path, {"ts": 1, "text": "a"})
        append_jsonl(path, {"ts": 2, "text": "b"})
        entries = read_jsonl(path)
        check(len(entries) == 2 and entries[1]["text"] == "b", "jsonl round trip")
        check(len(read_jsonl(path, limit=1)) == 1, "jsonl limit")
        check(read_jsonl(os.path.join(td, "missing.jsonl")) == [], "missing log empty")

    check(classify_exception(Exception("Executable doesn't exist at /x")) == 2,
          "fatal launch classified 2")
    check(classify_exception(Exception("Timeout 30000ms exceeded")) == 2,
          "plain exception classified 2")

    class FakeTimeoutError(Exception):
        pass

    FakeTimeoutError.__name__ = "TimeoutError"
    check(classify_exception(FakeTimeoutError("x")) == 1, "timeout classified 1")
    check(is_fatal_message("Target page, context or browser has been closed"),
          "fatal hint matches")
    check(not is_fatal_message("strict mode violation"), "non-fatal message")

    check(request_line({"method": "GET", "url": "http://x/y", "status": 200, "ms": 143})
          == "GET http://x/y 200 143ms", "request line format")
    check(request_line({"method": "POST", "url": "http://x/y", "status": "FAILED",
                        "ms": 1}) == "POST http://x/y FAILED 1ms",
          "failed request line format")

    with tempfile.TemporaryDirectory() as td:
        flow = os.path.join(td, "f.json")
        with open(flow, "w", encoding="utf-8") as fh:
            fh.write('[{"cmd": "goto", "url": "http://x/"}]')
        check(len(load_flow(flow)) == 1, "flow load ok")
        bad = os.path.join(td, "bad.json")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write("{}")
        try:
            load_flow(bad)
            check(False, "flow object rejected")
        except WebtapError:
            check(True, "flow object rejected")

    print(f"selftest ok ({checks} checks)")


if __name__ == "__main__":
    sys.exit(main())
