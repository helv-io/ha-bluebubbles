"""A repo carries a pinned copy of these checks in .agent-checks/ because CI on GitHub cannot read git.helv.io (it asks for a login).
`verify` proves the copy is exactly what was vendored: every file matches .agent-checks/MANIFEST, nothing extra, nothing missing.
A hand edit would let one repo drift from the others, which is the problem this repo exists to remove."""
import hashlib, os
from lib import error

HERE = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def digest(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def files(root):
    out = []
    for d, _, names in os.walk(root):
        for n in names:
            rel = os.path.relpath(os.path.join(d, n), root)
            if rel not in ("MANIFEST",) and "__pycache__" not in rel and not rel.endswith(".pyc"):
                out.append(rel)
    return sorted(out)


def run(args):
    manifest = os.path.join(HERE, "MANIFEST")
    if not os.path.exists(manifest):
        print("verify: this is the source checkout, not a vendored copy; nothing to verify")
        return 0
    want = {}
    for line in open(manifest, encoding="utf-8"):
        h, _, rel = line.rstrip("\n").partition("  ")
        want[rel] = h
    have = files(HERE)
    bad = 0
    for rel in sorted(set(want) | set(have)):
        if rel not in have:
            error(f".agent-checks/{rel} is missing from the vendored copy", ".agent-checks/MANIFEST"); bad += 1
        elif rel not in want:
            error(f".agent-checks/{rel} is not part of the vendored copy", f".agent-checks/{rel}"); bad += 1
        elif digest(os.path.join(HERE, rel)) != want[rel]:
            error(f".agent-checks/{rel} was edited by hand", f".agent-checks/{rel}"); bad += 1
    if bad:
        ref = open(os.path.join(HERE, "REF"), encoding="utf-8").read().strip() if os.path.exists(os.path.join(HERE, "REF")) else "?"
        error(f"the vendored checks differ from agent-checks commit {ref[:12]}. Change them in the agent-checks repo, then run its tools/vendor to update this repo.")
    return 1 if bad else 0
