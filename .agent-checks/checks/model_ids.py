"""No built-in model ids in shipped code. Model names come from the provider's live list or from what the person chose.
`model-ids [--rev REV]`. Tests, docs and changelogs are exempt, and so are comment-only lines.
Exception on the line: `model-id-ok: <reason> until YYYY-MM-DD`. Config: [model-ids] exempt = ["regex", ...]"""
import re
from lib import error, load_config, exception_ok, tracked_files, read_file

ID = re.compile(r"(?i)(?<![\w/-])(grok|gpt|claude|gemini|llama|mistral|deepseek|qwen|o[134](-mini)?)-(\d|imagine|latest)[\w.\-]*|DEFAULT_MODEL\s*=")
CODE = (".py", ".go", ".ts", ".tsx", ".js", ".qml", ".json", ".yaml", ".yml")
EXEMPT = re.compile(r"(^|/)(tests?|docs?|testdata|translations)/|_test\.go$|test_.*\.py$|\.test\.[tj]sx?$|(CHANGELOG|README|AGENTS?)\.md$|package(-lock)?\.json$|\.github/|\.agent-checks\.toml$")


def run(args):
    rev = args[1] if args[:1] == ["--rev"] else None
    extra = [re.compile(p) for p in load_config().get("model-ids", {}).get("exempt", [])]
    bad = 0
    for n in tracked_files(rev):
        if not n.endswith(CODE) or EXEMPT.search(n) or any(e.search(n) for e in extra):
            continue
        body = read_file(n, rev)
        if body is None:
            continue
        for no, line in enumerate(body.splitlines(), 1):
            if line.strip().startswith(("//", "#", "*", "/*")):
                continue
            m = ID.search(line)
            if not m or exception_ok(line, "model-id-ok"):
                continue
            error(f"built-in model id '{m.group(0)}'. Read it from the provider's live model list or from what the person chose.", n, no)
            bad += 1
    return 1 if bad else 0
