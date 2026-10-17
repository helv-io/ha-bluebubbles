"""A change to user-facing code must touch the docs files in the same range (a pull request, or the commits of one push),
unless a commit in the range carries the line `Docs: skip <reason>`.
Range based on purpose: a series of commits ends with the one that writes the changelog, so per-commit checking would cry wolf.
Config: [docs] user-facing = "<regex>", require = ["CHANGELOG.md", "README.md"]"""
import re
from lib import git, error, load_config


def run(args):
    if len(args) < 2:
        error("docs needs a base and a head, for example: docs origin/main HEAD")
        return 2
    base, head = args[0], args[1]
    cfg = load_config().get("docs", {})
    pattern = cfg.get("user-facing")
    if not pattern:
        return 0  # repo has not said what is user-facing; nothing to enforce
    need = cfg.get("require", ["CHANGELOG.md", "README.md"])
    files = git("diff", "--name-only", f"{base}..{head}").split()
    touched = [f for f in files if re.search(pattern, f)]
    if not touched:
        return 0
    if re.search(r"(?mi)^Docs: skip \S.*", git("log", "--format=%B", f"{base}..{head}")):
        return 0
    bad = 0
    for doc in need:
        if doc not in files:
            error(f"user-facing files changed ({', '.join(touched[:2])}{', ...' if len(touched) > 2 else ''}) but {doc} did not. "
                  f"Say what changed in plain words, or add a line 'Docs: skip <reason>' to one commit message.", doc)
            bad += 1
    return 1 if bad else 0
