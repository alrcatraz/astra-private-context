"""Offline unit tests for the astra-private-context plugin (no live session needed).

Run from anywhere: python3 tests/test_plugin.py
Imports __init__.py directly; Hermes config import is stubbed if unavailable.
"""
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent


def load_plugin():
    spec = importlib.util.spec_from_file_location("apc_under_test", PLUGIN_DIR / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.apc = load_plugin()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        os.system(f"git init -q {self.root}")  # give the walk a real git root

    def _cfg(self, suffixes=None, bases=None, global_file=None):
        entry = {}
        if suffixes: entry["suffixes"] = suffixes
        if bases: entry["bases"] = bases
        if global_file: entry["global_file"] = global_file
        cfg = {"plugins": {"entries": {"astra-private-context": {"settings": entry}}}}
        self.apc._cfg_cache = None
        import types
        fake = types.ModuleType("hermes_cli.config")
        fake.load_config = lambda: cfg
        pkg = types.ModuleType("hermes_cli"); pkg.config = fake
        sys.modules.setdefault("hermes_cli", pkg)
        sys.modules["hermes_cli.config"] = fake

    def test_subtree_precedence(self):
        cfg = {"plugins": {
            "entries": {"astra-private-context": {"settings": {"suffixes": ["priv"]},
                                                  "config": {"suffixes": ["old"], "bases": ["AGENTS"]}}},
            "astra-private-context": {"suffixes": ["legacy"], "global_file": "~/x.md"}}}
        subs = self.apc._plugin_cfg_subtrees(cfg)
        pc = {}
        for sub in subs:
            merged = dict(sub); merged.update(pc); pc = merged
        self.assertEqual(pc["suffixes"], ["priv"])          # canonical wins
        self.assertEqual(pc["bases"], ["AGENTS"])           # legacy .config fills gaps
        self.assertEqual(pc["global_file"], "~/x.md")       # flat compat still read

    def test_agents_family_shadows_claude(self):
        self._cfg()
        (self.root / "AGENTS.local.md").write_text("# A\nMARK-A\n")
        (self.root / "CLAUDE.local.md").write_text("# C\nMARK-C\n")
        found = [p.name for p, _ in self.apc._candidate_names(self.root)]
        self.assertIn("AGENTS.local.md", found)
        self.assertNotIn("CLAUDE.local.md", found)

    def test_claude_only_when_no_agents(self):
        self._cfg()
        (self.root / "CLAUDE.local.md").write_text("# C\nMARK-C\n")
        found = [p.name for p, _ in self.apc._candidate_names(self.root)]
        self.assertEqual(found, ["CLAUDE.local.md"])

    def test_custom_suffix_recognised(self):
        self._cfg(suffixes=["priv"])
        (self.root / "AGENTS.priv.md").write_text("MARK-P\n")
        (self.root / "AGENTS.local.md").write_text("MARK-L\n")
        found = [p.name for p, _ in self.apc._candidate_names(self.root)]
        self.assertEqual(found, ["AGENTS.priv.md"])

    def test_walk_up_to_git_root_nearest_first(self):
        self._cfg()
        nested = self.root / "pkg" / "sub"
        nested.mkdir(parents=True)
        (nested / "AGENTS.local.md").write_text("NEAR\n")
        (self.root / "AGENTS.local.md").write_text("FAR\n")
        found = [str(p) for p, _ in self.apc._candidate_names(nested)]
        self.assertEqual(len(found), 2)
        self.assertTrue(found[0].endswith("pkg/sub/AGENTS.local.md"))

    def test_empty_file_not_injected(self):
        self._cfg()
        (self.root / "AGENTS.local.md").write_text("   \n")
        self.assertIsNone(self.apc._cached_read(self.root / "AGENTS.local.md"))

    def test_mtime_cache_invalidates(self):
        self._cfg()
        p = self.root / "AGENTS.local.md"
        p.write_text("V1\n")
        self.assertEqual(self.apc._cached_read(p), "V1")
        stat = p.stat()
        p.write_text("V2\n")
        os.utime(p, ns=(stat.st_atime_ns + 10**9, stat.st_mtime_ns + 10**9))
        self.assertEqual(self.apc._cached_read(p), "V2")


if __name__ == "__main__":
    unittest.main(verbosity=2)
