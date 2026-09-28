"""astra-private-context — inject gitignored private policy files alongside the public AGENTS.md.

Hermes natively handles discovery, shadowing and progressive subdirectory hints for
the standard context-file chain (.hermes.md → AGENTS.md(+override) → CLAUDE.md →
.cursorrules). What it does NOT support: additional per-repo PRIVATE variants of those
files (e.g. AGENTS.local.md / CLAUDE.local.md, or any configured suffix), loaded in
ADDITION to (not replacing) the public file. This plugin supplies exactly that via
pre_llm_call: rides the user message each turn, system-prompt cache untouched.

Config (config.yaml, canonical plugin path):
  plugins:
    entries:
      astra-private-context:
        settings:
          suffixes: [local]        # X → <Base>.<suffix>.md ; default [local]
          bases: [AGENTS, CLAUDE]  # which public families to pair with ; default both
          global_file: ~/path/fleet-redlines.md  # optional always-on block,
                                 # injected even when session cwd is None (headless-safe)
Legacy fallbacks also read: plugins.entries.<id>.config.*, plugins.astra-private-context.*.

Private files must be gitignored in every repo that has one; they never enter git.
Install: copy dir to ~/.hermes/plugins/astra-private-context/
then `hermes plugins enable astra-private-context`.
"""
import logging
import subprocess
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_SUFFIXES = ("local",)
DEFAULT_BASES = ("AGENTS", "CLAUDE")
_MAX_ANCESTOR_WALK = 5      # same bound as agent/subdirectory_hints.py
_CACHE_CAP = 64             # bounded across long-lived gateway processes
_cache: dict[str, tuple[float, str]] = {}
_cfg_cache: tuple | None = None


def _plugin_cfg_subtrees(cfg: dict) -> list[dict]:
    """All places our settings may live, in precedence order (canonical first).

    Mirrors hermes_cli.plugins.PluginContext.get_config: plugins.entries.<id>.settings
    → legacy .config subtree; plus the pre-entries shape plugins.<id> for compat.
    """
    entry = ((cfg.get("plugins") or {}).get("entries") or {}).get("astra-private-context") or {}
    out = []
    if isinstance(entry.get("settings"), dict):
        out.append(entry["settings"])
    if isinstance(entry.get("config"), dict):
        out.append(entry["config"])
    flat = (cfg.get("plugins") or {}).get("astra-private-context")
    if isinstance(flat, dict):
        out.append(flat)
    return out


def _config() -> tuple[list[str], list[str], Optional[Path]]:
    """Read config once per process; deferred import keeps module import safe."""
    global _cfg_cache
    if _cfg_cache is not None:
        return _cfg_cache
    suffixes, bases, global_file = list(DEFAULT_SUFFIXES), list(DEFAULT_BASES), None
    try:
        from hermes_cli.config import load_config
        cfg = load_config() or {}
        pc: dict = {}
        for sub in _plugin_cfg_subtrees(cfg):   # merge, canonical wins per key
            merged = dict(sub)
            merged.update(pc)
            pc = merged
        if isinstance(pc.get("suffixes"), list) and pc["suffixes"]:
            suffixes = [str(s).strip().lstrip(".") for s in pc["suffixes"] if str(s).strip()]
        if isinstance(pc.get("bases"), list) and pc["bases"]:
            bases = [str(b).strip() for b in pc["bases"] if str(b).strip()]
        gf = pc.get("global_file")
        if isinstance(gf, str) and gf.strip():
            global_file = Path(gf.strip()).expanduser()
    except Exception as e:  # config absent/unreadable → defaults, fail-open
        logger.debug("private-context: config load fell back to defaults: %s", e)
    _cfg_cache = (suffixes, bases, global_file)
    return _cfg_cache


def _cached_read(path: Path) -> Optional[str]:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    key = str(path)
    hit = _cache.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as e:
        logger.warning("private-context: unreadable %s: %s", path, e)
        return None
    if not text:
        return None
    if len(_cache) >= _CACHE_CAP:
        _cache.clear()
    _cache[key] = (mtime, text)
    logger.info("private-context: queued %d chars from %s", len(text), path)
    return text


def _git_root(cwd: Path) -> Optional[Path]:
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd,
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip())
    except Exception:
        pass
    return None


def _candidate_names(cwd: Path) -> list[tuple[Path, str]]:
    """Private filenames for this repo, ordered nearest-first (cwd → git root).

    Dedup rule mirrors prompt_builder: within one directory the AGENTS family wins
    over CLAUDE (public AGENTS.md shadows CLAUDE.md there, so its private twin
    shadows CLAUDE.local.md too). Across directories we mirror subdirectory-hints:
    walk up to the git root, first match per name wins.
    """
    suffixes, bases, _ = _config()
    top = _git_root(cwd)
    dirs: list[Path] = []
    cur = cwd
    for _ in range(_MAX_ANCESTOR_WALK + 1):
        dirs.append(cur)
        if top and cur == top:
            break
        parent = cur.parent
        if parent == cur:
            break
        if top is None and (parent == Path.home() or parent == Path("/")):
            break
        cur = parent
    out: list[tuple[Path, str]] = []
    seen: set[str] = set()
    for d in dirs:
        agents_family_hit = False
        for base in bases:
            for suf in suffixes:
                name = f"{base}.{suf}.md"
                p = d / name
                key = str(p)
                if key in seen:
                    continue
                if base.upper() != "AGENTS" and agents_family_hit:
                    continue  # AGENTS family already provides a private file in this dir
                if p.is_file():
                    out.append((p, name))
                    seen.add(key)
                    if base.upper() == "AGENTS":
                        agents_family_hit = True
    return out


def _global_block() -> Optional[str]:
    _, _, gf = _config()
    return _cached_read(gf) if gf else None


def inject_private(**kwargs: Any) -> Optional[dict]:
    # CWD is NOT in kwargs — read the session ContextVar (multiplex-safe).
    try:
        from agent.runtime_cwd import resolve_context_cwd
        cwd = resolve_context_cwd()
    except Exception as e:
        logger.warning("private-context: runtime_cwd unavailable: %s", e)
        cwd = None
    sections: list[str] = []
    g = _global_block()
    if g:
        sections.append(f"# Fleet redlines (global)\n\n{g}")
    if cwd:
        for path, name in _candidate_names(Path(cwd)):
            text = _cached_read(path)
            if text:
                sections.append(f"# Private project policy — {name} ({path})\n\n{text}")
    if not sections:
        return None
    return {"context": "\n\n".join(sections)}


def register(ctx) -> None:
    ctx.register_hook("pre_llm_call", inject_private)
