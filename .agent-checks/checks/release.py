"""Release gates.
  release-version TAG [REV]   Before anything is published: every version the repo repeats in files must equal the tag.
                              Config: [[release.version]] file = "path", pattern = 'regex with ONE capture group for the version'
                              Every match must equal the tag version; no match at all is an error (the file moved or the pattern rotted).
  release-assets REPO TAG [ASSET...]   After publishing: the GitHub Release page exists and has every named asset.
                              Retries for a few minutes because assets upload last. Uses GITHUB_TOKEN when set."""
import json, os, re, sys, time, urllib.request, urllib.error
from lib import error, load_config, read_file


def version(args):
    if not args:
        error("release-version needs a tag such as v1.2.3")
        return 2
    tag = args[0]; rev = args[1] if len(args) > 1 else None
    want = tag[1:] if tag.startswith("v") else tag
    items = load_config().get("release", {}).get("version", [])
    if not items:
        error("no [[release.version]] entries in .agent-checks.toml; list every file that repeats the version")
        return 2
    bad = 0
    for it in items:
        body = read_file(it["file"], rev)
        if body is None:
            error(f"{it['file']} is listed in .agent-checks.toml but does not exist; update the list", it["file"]); bad += 1; continue
        found = re.findall(it["pattern"], body, re.M)
        if not found:
            error(f"pattern {it['pattern']!r} matches nothing in {it['file']}; the file changed shape, fix the pattern", it["file"]); bad += 1; continue
        for f in found:
            f = f if isinstance(f, str) else f[0]
            if f != want:
                error(f"{it['file']} says {f} but the tag is {tag}. Bump every listed file in one commit, then tag that commit.", it["file"]); bad += 1
    return 1 if bad else 0


def assets(args):
    if len(args) < 2:
        error("release-assets needs REPO and TAG")
        return 2
    repo, tag, want = args[0], args[1], args[2:]
    tries = int(os.environ.get("AGENT_CHECKS_TRIES", "12"))
    last = ""
    for i in range(tries):
        req = urllib.request.Request(f"{os.environ.get('AGENT_CHECKS_API', 'https://api.github.com')}/repos/{repo}/releases/tags/{tag}", headers={"Accept": "application/vnd.github+json"})
        if os.environ.get("GITHUB_TOKEN"):
            req.add_header("Authorization", "Bearer " + os.environ["GITHUB_TOKEN"])
        try:
            data = json.load(urllib.request.urlopen(req, timeout=30))
            names = [a["name"] for a in data.get("assets", [])]
            missing = [w for w in want if w not in names]
            if not missing:
                return 0
            last = f"{repo} {tag} has no asset named {', '.join(missing)} (has: {', '.join(names) or 'none'}). The download button or HACS would find nothing."
        except urllib.error.HTTPError as e:
            last = f"{repo} has no GitHub Release for {tag} (HTTP {e.code}). The release workflow must create it."
        except Exception as e:  # network trouble: keep trying, then say so
            last = f"could not reach GitHub: {e}"
        if i + 1 < tries:
            time.sleep(int(os.environ.get("AGENT_CHECKS_WAIT", "15")))
    error(last)
    return 1
