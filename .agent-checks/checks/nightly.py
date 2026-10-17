"""A failing scheduled run must be seen. GitHub only emails the person who last touched the workflow; ha-bluebubbles went red seven nights in a row unseen.
usage: agent-checks nightly-alert fail|ok      (in a job with `if: always() && github.event_name == 'schedule'`, needs: the checked jobs)
fail: opens one issue titled "Scheduled checks are failing" (or comments on the open one) with the run link.
ok:   closes that issue with a comment when it exists.
Needs `permissions: issues: write` and GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_RUN_ID, GITHUB_SERVER_URL."""
import json, os, urllib.request
from lib import error

TITLE = "Scheduled checks are failing"


def call(method, path, body=None):
    base = os.environ.get("AGENT_CHECKS_API", "https://api.github.com")
    req = urllib.request.Request(f"{base}{path}", method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Accept": "application/vnd.github+json", "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"], "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def run(args):
    if args[:1] not in (["fail"], ["ok"]):
        error("nightly-alert needs 'fail' or 'ok'")
        return 2
    repo = os.environ["GITHUB_REPOSITORY"]
    link = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{repo}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
    open_issue = next((i for i in call("GET", f"/repos/{repo}/issues?state=open&per_page=100") if i["title"] == TITLE and "pull_request" not in i), None)
    if args[0] == "fail":
        text = f"The scheduled run failed: {link}\n\nNobody pushed anything, so something outside the repo changed (a dependency, a service, or a runner). Fix it, or pin what moved."
        if open_issue:
            call("POST", f"/repos/{repo}/issues/{open_issue['number']}/comments", {"body": text})
        else:
            call("POST", f"/repos/{repo}/issues", {"title": TITLE, "body": text})
    elif open_issue:
        call("POST", f"/repos/{repo}/issues/{open_issue['number']}/comments", {"body": f"Passing again: {link}"})
        call("PATCH", f"/repos/{repo}/issues/{open_issue['number']}", {"state": "closed"})
    return 0
