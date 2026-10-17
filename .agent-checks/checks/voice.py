"""Banned wording in text people read. One list here; repo-specific words in .agent-checks.toml under [[voice.extra]].
Modes: `voice tree [paths]`  scan whole files.   `voice diff BASE HEAD`  scan only added lines, so old text never blocks a change.
Exception on the line itself: `voice-ok: <reason> until YYYY-MM-DD`. No reason or an expired date fails."""
import re, subprocess
from lib import git, error, load_config, exception_ok, tracked_files, read_file

BANNED = [
    ("\u2014", "em dash", "use a period, comma or colon"),
    (r"\u2013(?=\s)|(?<=\s)\u2013", "en dash used as a pause", "use a period, comma or colon"),
    (r"(?i)\b(seamless(ly)?|powerful|robust|effortless(ly)?|supercharge|leverage)\b", "marketing word", "say what it does"),
]
TEXT = (".md", ".qml", ".html", ".tmpl", ".txt", ".json", ".yml", ".yaml")
# Files that may talk about the banned words themselves, and files nobody reads as prose.
SKIP = re.compile(r"(^|/)(\.agent-checks/|AGENTS?\.md|CLAUDE\.md|CONTRIBUTING\.md|LICENSE|THIRD_PARTY_NOTICES\.md|package(-lock)?\.json|go\.sum|\.agent-checks\.toml|\.github/|\.gitea/|translations/|testdata/|node_modules/)")


def banned_for(extra, path=""):
    """Built-in list plus the repo's own words. An extra may carry `paths` (a regex): it then applies only to matching files."""
    return BANNED + [(e["pattern"], e["why"], e["fix"]) for e in extra if re.search(e.get("paths", ""), path)]


def scan(path, numbered, extra):
    bad = 0
    for no, line in numbered:
        if exception_ok(line, "voice-ok"):
            continue
        for pat, what, fix in banned_for(extra, path):
            if re.search(pat, line):
                error(f"{what}; {fix}", path, no)
                bad += 1
                break
    return bad


def run(args):
    cfg = load_config().get("voice", {})
    extra = cfg.get("extra", [])
    skip_extra = [re.compile(p) for p in cfg.get("skip", [])]
    ok_path = lambda p: p.endswith(TEXT) and not SKIP.search(p) and not any(s.search(p) for s in skip_extra)
    bad = 0
    mode = args[0] if args else "tree"
    if mode == "diff":
        base, head = args[1], args[2]
        out = git("diff", "-U0", "--no-color", f"{base}..{head}")
        path = None; no = 0
        for l in out.splitlines():
            if l.startswith("+++ b/"):
                path = l[6:]; continue
            if l.startswith("+++ "):
                path = None; continue
            m = re.match(r"@@ -\S+ \+(\d+)", l)
            if m:
                no = int(m.group(1)); continue
            if l.startswith("+") and path and ok_path(path):
                bad += scan(path, [(no, l[1:])], extra); no += 1
    else:
        rev = None
        rest = args[1:] if args else []
        if mode == "rev":
            rev, rest = rest[0], rest[1:]
        files = tracked_files(rev)
        if rest:
            files = [f for f in files if any(f == r or f.startswith(r.rstrip("/") + "/") for r in rest)]
        for f in files:
            if ok_path(f):
                body = read_file(f, rev)
                if body is not None:
                    bad += scan(f, list(enumerate(body.splitlines(), 1)), extra)
    return 1 if bad else 0
