# AGENTS.md

Guidelines for changes to BlueBubbles for Home Assistant. Applies to code, docs and releases.

## Style

- Plain, short, direct. No marketing words, no em dashes.
- Generic examples. No house-specific names or hostnames in code, docs or examples.
- Small commits with a message body. One concern per commit.
- `pytest -q -rs` passes for every commit.

## Docs and releases

- The README is for user-visible things: install, features, setup, actions, troubleshooting. There is no changelog; the release page is the record.
- Every user-facing change updates the README in the same release.
- The version is `version` in `custom_components/bluebubbles/manifest.json`. Pushing the tag creates the GitHub Release.

## Rules and what enforces them

A rule that nothing enforces is a wish. Before you push, run `.agent-checks/bin/agent-checks local` (the shared `agent-checks` repo on Helvio's own git server) and `pytest -q -rs`.

| Rule | Enforced by |
|---|---|
| Every commit is Helvio Pedreschi <helvio88@gmail.com>, nobody else | git refuses to guess an identity on the box; `identity` check on every push |
| No em dashes, no marketing words | `voice` check on added lines, whole tree weekly |
| README moves with every user-facing change; otherwise `Docs: skip <reason>` in a commit message | `docs` check |
| No built-in model ids; no house names in shipped code | `model-ids` and `private` checks |
| Tag and `manifest.json` version agree before anything is published | `gate` job in `release.yml` |
| The release page exists after the tag is pushed | `verify` job in `release.yml` |
| Workflow files are valid | `actionlint` inside the `agent-checks` job |
| A skipped test is a failure | `no-skips` around `pytest` in `test.yml` |
| A failing nightly is seen | `alert` job opens an issue |
| Work on a branch. Never push to the default branch, never open a pull request unless asked | branch protection on the default branch; Helvio or Rook merges |
| When a project is going for distribution, offer Helvio to protect master | judgment (Rook offers it) |
