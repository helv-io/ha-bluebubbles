"""Personal names, house names and private hostnames must not appear in files of a public repo.
Three places the words can come from:
  1. AGENT_CHECKS_PRIVATE_WORDS (one regex per line) or ~/.config/agent-checks/private-words on a developer machine.
     Never stored in a repo, so a public repo does not publish what it hides.
  2. [private] patterns = ["regex"] in .agent-checks.toml: for words that are not secret, such as a domain name.
  3. [private] hashes = ["sha256 of a lowercase single word"]: for names, so CI can check them without printing them.
     A hash keeps a name out of plain sight and out of search; it does not stop someone who guesses the name and tests it.
     Make one with: agent-checks private-hash Alex
If no list exists at all the check says so and passes, unless `[private] required = true`.
Intended uses go in .agent-checks.toml: [[private.allow]] path = "regex" why = "reason"."""
import hashlib, os, re
from lib import error, load_config, tracked_files, read_file


def words():
    raw = os.environ.get("AGENT_CHECKS_PRIVATE_WORDS")
    if raw is None:
        p = os.path.expanduser("~/.config/agent-checks/private-words")
        if os.path.exists(p):
            raw = open(p, encoding="utf-8").read()
    if raw is None:
        return None
    return [w.strip() for w in raw.splitlines() if w.strip() and not w.startswith("#")]


def digest(word):
    return hashlib.sha256(word.lower().encode()).hexdigest()


def run(args):
    if args[:1] == ["hash"]:
        for w in args[1:]:
            print(digest(w))
        return 0
    cfg = load_config().get("private", {})
    ws = words()
    ws = (ws or []) + list(cfg.get("patterns", []))
    hashes = set(cfg.get("hashes", []))
    if not ws and not hashes:
        if cfg.get("required"):
            error("no private word list found; set AGENT_CHECKS_PRIVATE_WORDS, create ~/.config/agent-checks/private-words, or add [private] patterns or hashes")
            return 1
        print("private: no word list here, skipped")
        return 0
    pat = re.compile("|".join(f"(?:{w})" for w in ws)) if ws else None
    token = re.compile(r"[A-Za-z][A-Za-z']+")
    allow = []
    for a in cfg.get("allow", []):
        if not a.get("why"):
            error("[[private.allow]] entries need a 'why'")
            return 1
        allow.append(re.compile(a["path"]))
    bad = 0
    for n in tracked_files():
        if n in ("LICENSE", ".agent-checks.toml") or any(a.search(n) for a in allow):
            continue
        body = read_file(n)
        if body is None:
            continue
        for no, line in enumerate(body.splitlines(), 1):
            if (pat and pat.search(line)) or (hashes and any(digest(t) in hashes for t in token.findall(line))):
                error("private word in a public repo. Use a generic placeholder such as my.domain or Alex.", n, no)
                bad += 1
    return 1 if bad else 0
