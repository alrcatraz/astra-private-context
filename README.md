# astra-private-context

A standalone [Hermes Agent](https://hermes-agent.nousresearch.com) plugin that
layers **private project policy** on top of the public `AGENTS.md` — without
replacing it, without touching the Hermes core, and without ever committing
the private part to git.

## Why

Hermes already has a first-class project-context chain
(`.hermes.md → AGENTS.md → CLAUDE.md → .cursorrules`, with per-directory
shadowing and progressive subdirectory hints). What it deliberately does *not*
support is a **second, private variant of those files that loads alongside the
public one**. The native `AGENTS.override.md` *replaces* `AGENTS.md` in its
directory — useful for personal overrides, useless when you want
"public governance + private redlines, both active".

This plugin fills exactly that gap via the official `pre_llm_call` hook:
the public `AGENTS.md` stays in the cached system-prompt prefix; the private
block rides the user message each turn. True additive layering, prompt cache
untouched.

## What it injects

| Source | Condition | Purpose |
|---|---|---|
| `<Base>.<suffix>.md` (default `AGENTS.local.md`, `CLAUDE.local.md`) | found by walking session cwd → git root, nearest first | per-repo private policy, **must be gitignored** |
| `global_file` (config) | always, even when the session has no cwd | fleet-wide redlines for headless/mobile sessions |

Dedup mirrors Hermes' own shadowing semantics: within one directory the AGENTS
family wins over the CLAUDE family, so their private twins cannot both fire.

## Install

```bash
git clone <this-repo-url> ~/.hermes/plugins/astra-private-context
hermes plugins enable astra-private-context
```

Takes effect on the next session (gateways hot-reload hooks immediately).

## Configuration (`config.yaml`)

```yaml
plugins:
  entries:
    astra-private-context:
      suffixes: [local]              # X → <Base>.<X>.md
      bases: [AGENTS, CLAUDE]        # which public families to pair with
      global_file: ~/some/path/fleet-redlines.md   # optional always-on block
```

Legacy locations (`plugins.entries.<id>.config.*`, flat `plugins.astra-private-context.*`)
are also read and merged per-key, canonical winning — see `__init__.py::_plugin_cfg_subtrees`.

## Repo hygiene contract

- Private files (`*.local.md` or your configured suffix) must be listed in
  every consuming repo's `.gitignore`. They never enter git, any branch, or
  any remote — privacy is physical, not script-enforced.
- Injected content is logged (path + size) at INFO level to
  `$HERMES_HOME/logs/agent.log`; check there if policy seems absent.
- The injected block re-sends every turn (no cache discount) — keep private
  files small: hundreds of characters, not thousands.

## Limitations (honest list)

- Session-cwd based discovery does **not** follow `cd` inside terminal tools;
  it reflects the session's bound project. Launch Hermes from the repo (or use
  project bindings) for per-repo files to resolve.
- Headless sessions may have no cwd — rely on `global_file` for anything that
  must always apply.
- Plugin output bypasses Hermes' context-file threat scan; this is by design
  for your own files, but only point it at paths you control.

## Licence

MIT — see [LICENSE](LICENSE).
