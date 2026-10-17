"""Shared helpers for every check: config file, git access, and error output that reads the same locally and in CI."""
import os, re, subprocess, sys, datetime
try:
    import tomllib
except ModuleNotFoundError:  # Python older than 3.11
    tomllib = None

CONFIG_NAME = ".agent-checks.toml"
IN_CI = os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("GITEA_ACTIONS") == "true"


def load_config(root="."):
    """The repo's own settings. A missing file means defaults; a broken file is an error, never silently ignored."""
    path = os.path.join(root, CONFIG_NAME)
    if not os.path.exists(path):
        return {}
    if tomllib is None:
        fail_now(f"{CONFIG_NAME} needs Python 3.11 or newer to read; run the checks with a newer python3")
    with open(path, "rb") as f:
        try:
            return tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            fail_now(f"{CONFIG_NAME} is not valid TOML: {e}")


def git(*args, check=True, cwd=None):
    r = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
    if check and r.returncode != 0:
        fail_now(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def error(msg, file=None, line=None):
    """One finding. In CI it becomes an annotation on the file; locally it is path:line: message."""
    if IN_CI:
        loc = ""
        if file:
            loc = f" file={file}" + (f",line={line}" if line else "")
        print(f"::error{loc}::{msg}")
    elif file:
        print(f"{file}:{line or 1}: {msg}")
    else:
        print(f"error: {msg}")
    sys.stdout.flush()


def fail_now(msg):
    error(msg)
    sys.exit(2)


def today():
    return datetime.date.today()


def exception_ok(line, tag):
    """An inline exception looks like `<tag>: <reason> until YYYY-MM-DD`. No reason or an expired date means it does not count."""
    m = re.search(re.escape(tag) + r":\s*(\S.*?)\s+until\s+(\d{4}-\d{2}-\d{2})", line)
    if not m:
        return False
    try:
        return datetime.date.fromisoformat(m.group(2)) >= today()
    except ValueError:
        return False


VENDORED = ".agent-checks/"  # the pinned copy of these checks inside a repo; never scanned


def tracked_files(rev=None):
    names = git("ls-tree", "-r", "--name-only", rev).split("\n")[:-1] if rev else git("ls-files").split("\n")[:-1]
    return [n for n in names if not n.startswith(VENDORED)]


def read_file(path, rev=None):
    if rev:
        r = subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True)
        return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else None
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
        return None
