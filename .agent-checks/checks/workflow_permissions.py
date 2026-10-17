"""A reusable workflow gets every permission it asks for.
  workflow-permissions   Reads every file in .github/workflows. For each job that calls a workflow of the same repo
                         (`uses: ./.github/workflows/x.yml`), the called jobs may ask for no more permission than the
                         calling job holds.

Why: hearth's release workflow called its CI workflow, whose weekly-alert job asks for `issues: write`. The caller only held
`contents: write`. GitHub does not skip that job. It refuses to start the whole run ("startup_failure", no jobs, no log), so the
release page stayed empty. actionlint does not know this rule, so this is not a duplicate of the `actionlint` check; a workflow
that calls a file that does not exist is actionlint's to report, and is skipped here.

It needs nothing but Python: workflow files are read with a small reader for the part that matters (the `permissions` and `uses`
keys of the workflow and of its jobs). Anything it cannot read is reported, never passed over.

Config: [workflow-permissions] default = "read" | "write"
  What a workflow gets when nothing sets permissions: the repository's default token setting (Settings > Actions > General).
  "read" is the safe assumption and the default here."""
import os, re
from lib import error, load_config

LEVEL = {"none": 0, "read": 1, "write": 2}
KEY = re.compile(r"""^(?P<k>"[^"]*"|'[^']*'|[^\s:#'"\[{][^:]*?):(?:\s+(?P<v>.*))?$""")
FLOWS = os.path.join(".github", "workflows")


class Unreadable(Exception):
    pass


def _strip_comment(text):
    quote = None
    for i, c in enumerate(text):
        if quote:
            quote = None if c == quote else quote
        elif c in "\"'":
            quote = c
        elif c == "#" and (i == 0 or text[i - 1] in " \t"):
            return text[:i]
    return text


def parse(text):
    """The mapping structure of a workflow file: {key: (scalar value, children)}. Lists and block text are skipped."""
    root = {"indent": -1, "children": {}}
    stack = [root]
    block_over = None  # while inside a `|` or `>` text, the indent it must stay deeper than
    for raw in text.splitlines():
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if block_over is not None:
            if indent > block_over:
                continue
            block_over = None
        line = _strip_comment(raw).rstrip()
        body = line.strip()
        if not body or body in ("---", "..."):
            continue
        while body.startswith("-") and (len(body) == 1 or body[1] in " \t"):  # a list item: its first key sits after the dash
            rest = body[1:].lstrip()
            indent += len(body) - len(rest)
            body = rest
        m = KEY.match(body)
        if not m:
            continue
        while stack[-1]["indent"] >= indent:
            stack.pop()
        key = m.group("k").strip("\"'")
        value = (m.group("v") or "").strip()
        node = {"indent": indent, "value": value, "children": {}}
        stack[-1]["children"][key] = node
        stack.append(node)
        if re.match(r"^[|>][+-]?\d*$", value):
            block_over = indent
    return root["children"]


def scopes(node, where):
    """A `permissions` entry as {scope: level}, or None when it is not set."""
    if node is None:
        return None
    value = node["value"]
    if value in ("write-all", "read-all"):
        return {"*": 2 if value == "write-all" else 1}
    if value.startswith("{"):
        if not value.endswith("}"):
            raise Unreadable(f"{where}: write `permissions` as a block or on one line; this one spans lines")
        pairs = [p.strip() for p in value[1:-1].split(",") if p.strip()]
        items = {}
        for p in pairs:
            k, _, v = p.partition(":")
            items[k.strip().strip("\"'")] = v.strip().strip("\"'")
    elif value == "":
        items = {k: c["value"].strip("\"'") for k, c in node["children"].items()}
    else:
        raise Unreadable(f"{where}: cannot read `permissions: {value}`")
    out = {}
    for scope, level in items.items():
        if level not in LEVEL:
            raise Unreadable(f"{where}: `{scope}: {level}` is not none, read or write")
        out[scope] = LEVEL[level]
    return out


def grant(held, scope, default):
    if held is None:
        return default
    return held.get(scope, held.get("*", 0))


def load(path):
    with open(path, encoding="utf-8") as f:
        return parse(f.read())


def problems(path, flow, default, seen=()):
    found = []
    top = scopes(flow.get("permissions"), path)
    for job_name, job in (flow.get("jobs") or {"children": {}})["children"].items():
        target = job["children"].get("uses", {}).get("value", "").strip("\"'")
        if not target.startswith("./"):
            continue
        callee_path = os.path.normpath(target[2:])
        if callee_path in seen or not os.path.exists(callee_path):
            continue
        own = job["children"].get("permissions")
        held = scopes(own, f"{path}: job '{job_name}'") if own else top
        callee = load(callee_path)
        callee_top = scopes(callee.get("permissions"), callee_path)
        for inner_name, inner in (callee.get("jobs") or {"children": {}})["children"].items():
            mine = inner["children"].get("permissions")
            asked = scopes(mine, f"{callee_path}: job '{inner_name}'") if mine else callee_top
            for scope, level in (asked or {}).items():
                if level > grant(held, scope, default):
                    found.append((path,
                        f"job '{job_name}' calls {callee_path}, whose job '{inner_name}' asks for {scope}: "
                        f"{'write' if level == 2 else 'read'}, more than '{job_name}' holds. A called workflow can never hold more "
                        f"than the job that calls it, and GitHub then refuses to start the whole run (startup_failure). "
                        f"Fix: give job '{job_name}' a `permissions:` block that includes `{scope}: {'write' if level == 2 else 'read'}`."))
        found += problems(callee_path, callee, default, seen + (callee_path,))
    return found


def run(args):
    if not os.path.isdir(FLOWS):
        return 0
    cfg = load_config().get("workflow-permissions", {})
    default = LEVEL.get(cfg.get("default", "read"))
    if default is None:
        error('[workflow-permissions] default must be "read" or "write"')
        return 2
    found, seen = [], set()
    try:
        for name in sorted(os.listdir(FLOWS)):
            if name.endswith((".yml", ".yaml")):
                path = os.path.join(FLOWS, name)
                for item in problems(path, load(path), default, (path,)):
                    if item not in seen:
                        seen.add(item); found.append(item)
    except Unreadable as e:
        error(str(e))
        return 1
    for path, msg in found:
        error(msg, path)
    return 1 if found else 0
