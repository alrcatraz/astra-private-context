# AGENTS.md — astra-private-context

Instructions for AI agents (and humans) working on this repository.

## What this project is

A single-file Hermes Agent plugin (`__init__.py` + `plugin.yaml`). It injects
gitignored private policy files alongside the public `AGENTS.md` via the
official `pre_llm_call` hook. No dependencies beyond the Python stdlib and
Hermes' own importable surface (`agent.runtime_cwd`, `hermes_cli.config`).

## Layout

- `__init__.py` — the entire plugin. Keep it self-contained; do not add core
  Hermes imports that are not already used by shipped plugins.
- `plugin.yaml` — manifest (`provides_hooks: [pre_llm_call]`).
- `README.md` — user-facing docs. Keep README and code behaviour in lockstep.

## Conventions

- Language: repo is English-first (public-facing). Comments explain WHY, not WHAT.
- Commits: Conventional Commits, GPG-signed with the repo-local identity.
- Versioning: plain SemVer tags (`v1.0.0`) on `main`. Plugin version lives in
  `plugin.yaml`; keep both in sync at tag time.
- **Never commit private policy content.** Files matching `*.<suffix>.md`
  (default `.local.md`) are gitignored by design — adding them to git breaks
  the project's core promise. Test fixtures must use throwaway paths under a
  scratch dir, never realistic redline text.
- Privacy contract before any change: this repo may be public. Do not put real
  hostnames, internal URLs, credentials, or fleet topology into ANY tracked
  file, including tests and examples. Use obviously-fake placeholders.

## Testing

The plugin is hook-pure: verify without a live session by driving the hook
pipeline directly from the Hermes source tree:

```python
import os; os.environ["HERMES_HOME"] = os.path.expanduser("~/.hermes")
import model_tools                      # triggers plugin discovery
from hermes_cli.plugins import discover_plugins; discover_plugins()
from agent.runtime_cwd import set_session_cwd, reset_session_cwd
from hermes_cli.lifecycle import invoke_hook
tok = set_session_cwd("/tmp/some-repo")
try:
    results = invoke_hook("pre_llm_call", session_id="t", task_id="t", turn_id="t1",
        user_message="x", conversation_history=[], is_first_turn=True,
        model="main", platform="cli", parent_session_id="", sender_id="u")
finally:
    reset_session_cwd(tok)
```

Assert behaviours, not prompt text snapshots: presence/absence of injected
sections, family-shadowing dedup (AGENTS beats CLAUDE in one dir), silent pass
when no private files exist, and other plugins' hooks unaffected.

## Deploying locally

```bash
cp __init__.py plugin.yaml ~/.hermes/plugins/astra-private-context/
hermes plugins enable astra-private-context   # gateway hot-reloads hooks
```
