"""Every commit in a range must be authored and committed by the one allowed person.
Bots listed below are allowed; outside contributors are allowed only when the repo lists them in .agent-checks.toml.
Why: agents guess an identity ("Cursor Agent", root@runner) and the history then needs a rewrite (skgate, bracket-night, ha-supergrok)."""
import re
from lib import git, error, load_config

NAME = "Helvio Pedreschi"
EMAIL = "helvio88@gmail.com"
BOT = re.compile(r"\[bot\]@users\.noreply\.github\.com$")


def run(args):
    if not args:
        error("identity needs a commit range, for example origin/main..HEAD")
        return 2
    cfg = load_config().get("identity", {})
    outside = set(cfg.get("allow-emails", []))
    bad = 0
    out = git("log", "--format=%H|%an|%ae|%cn|%ce", args[0])
    for row in out.splitlines():
        sha, an, ae, cn, ce = row.split("|")
        if BOT.search(ae) or ae in outside:
            continue
        if ae == EMAIL and an == NAME and (ce == EMAIL and cn == NAME or ce == "noreply@github.com"):
            continue
        error(f"commit {sha[:7]} is by {an} <{ae}> (committer {cn} <{ce}>). Every commit must be {NAME} <{EMAIL}>. "
              f"Fix: set user.name and user.email in this clone, then run: git rebase -r --exec 'git commit --amend --no-edit --reset-author' BASE")
        bad += 1
    return 1 if bad else 0
