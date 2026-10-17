"""Run a test command and fail if it skipped anything. A skipped test is a test that did not run, so a green local run can hide a red CI run.
usage: agent-checks no-skips [--hide REGEX]... -- <command...>
  --hide: do not print output lines that match (for example the thousands of "--- PASS" lines of a verbose go test).
Escape hatch for a machine that truly cannot run something: AGENT_CHECKS_ALLOW_SKIP=1 (CI never sets it).
Config: [no-skips] allow = ["regex of a skip line that is fine, such as a platform-only test"]"""
import os, re, subprocess, sys
from lib import error, load_config

SKIP = re.compile(r"(?m)^\s*--- SKIP|^SKIPPED\b|\bSKIPPED\b|\b\d+ skipped\b")


def run(args):
    hide = []
    while args[:1] == ["--hide"]:
        hide.append(re.compile(args[1])); args = args[2:]
    if args[:1] == ["--"]:
        args = args[1:]
    if not args:
        error("no-skips needs a test command after --")
        return 2
    allow = [re.compile(p) for p in load_config().get("no-skips", {}).get("allow", [])]
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    skips = []
    for line in p.stdout:
        if not any(h.search(line) for h in hide):
            sys.stdout.write(line)
        if SKIP.search(line) and not any(a.search(line) for a in allow):
            skips.append(line.strip())
    code = p.wait()
    if code:
        return code
    if skips and os.environ.get("AGENT_CHECKS_ALLOW_SKIP") != "1":
        error(f"{len(skips)} test(s) were skipped, for example: {skips[0][:120]}. A skipped test did not run. "
              f"Install what it needs so it runs here, as CI does (or set AGENT_CHECKS_ALLOW_SKIP=1 on a machine that truly cannot).")
        return 1
    return 0
