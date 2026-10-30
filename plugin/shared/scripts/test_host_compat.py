#!/usr/bin/env python3
"""Tests for host_compat.py.

All fixtures live under tempfile trees injected through detect(env, paths);
the real ~/.codex / ~/.claude / ~/.pi trees are never touched. The CLI
subprocess test redirects HOME/USERPROFILE to a temp tree so the cache globs
see an empty home instead of the developer's real one.

Run directly:
    command python3 plugin/shared/scripts/test_host_compat.py

No pytest dependency. Uses only the standard unittest module.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import host_compat
from host_compat import DetectPaths, detect


def make_plugin_root(base, rel):
    """Create a `<base>/<rel>/shared/scripts/ghs_compat.py` tree; return the
    plugin root Path (`<base>/<rel>`)."""
    root = Path(base) / rel
    sentinel = root / "shared" / "scripts" / "ghs_compat.py"
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text("# ghs_compat stub for host_compat tests\n", encoding="utf-8")
    return root


def empty_dir(base, name):
    """Create and return an empty directory under base (a home with no cache)."""
    d = Path(base) / name
    d.mkdir()
    return d


def run_cli(args, env_extra=None):
    """Run host_compat.py as a subprocess.

    Returns (returncode, stdout, stderr). Output is always decoded as UTF-8
    (errors=replace) regardless of the parent console encoding.
    """
    cmd = [sys.executable, str(SCRIPT_DIR / "host_compat.py")] + args
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        cmd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout, proc.stderr


def marker_free_env(home):
    """A copy of the ambient env with all host markers and env roots removed,
    and HOME/USERPROFILE redirected to `home` so every cache glob lands in an
    empty temp tree instead of the real ~/.codex / ~/.claude / ~/.pi."""
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(host_compat.CODEX_MARKER_PREFIX)
        and key not in host_compat.ENV_ROOT_VARS
        and key not in host_compat.PI_MARKER_VARS
    }
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    return env


class HostCompatDetectTests(unittest.TestCase):
    def test_host_compat_claude_env_hit(self):
        """CLAUDE_PLUGIN_ROOT pointing at a tmp tree with the sentinel ->
        host=claude-code, resolution=env, plugin_root=that value."""
        with tempfile.TemporaryDirectory() as tmp:
            plugin_root = make_plugin_root(tmp, "plugin")
            result = detect(
                {"CLAUDE_PLUGIN_ROOT": str(plugin_root)},
                DetectPaths(
                    claude_home=empty_dir(tmp, "claude-home"),
                    codex_home=None,
                    pi_agent_dir=None,
                ),
            )
            self.assertEqual(result["host"], "claude-code")
            self.assertEqual(result["resolution"], "env")
            self.assertEqual(result["plugin_root"], str(plugin_root))

    def test_host_compat_codex_cache_glob_flat_join(self):
        """CODEX_ marker, no env root, `@`-flat cache layout -> host=codex,
        resolution=cache-glob."""
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex-home"
            plugin_root = make_plugin_root(
                codex_home / "plugins" / "cache",
                "golden-hoop-spell@golden-hoop-spell",
            )
            result = detect(
                {"CODEX_SANDBOX": "1"},
                DetectPaths(
                    claude_home=empty_dir(tmp, "claude-home"),
                    codex_home=codex_home,
                    pi_agent_dir=None,
                ),
            )
            self.assertEqual(result["host"], "codex")
            self.assertEqual(result["resolution"], "cache-glob")
            self.assertEqual(result["plugin_root"], str(plugin_root))

    def test_host_compat_pi_detection(self):
        """pi markers: PI_SESSION_ID with a valid env root -> pi/env;
        PI_CODING_AGENT_DIR with a git landing layout -> pi/cache-glob."""
        with tempfile.TemporaryDirectory() as tmp:
            plugin_root = make_plugin_root(tmp, "plugin")
            result = detect(
                {
                    "PI_SESSION_ID": "sess-0001",
                    "CLAUDE_PLUGIN_ROOT": str(plugin_root),
                },
                DetectPaths(
                    claude_home=empty_dir(tmp, "claude-home"),
                    codex_home=None,
                    pi_agent_dir=None,
                ),
            )
            self.assertEqual(result["host"], "pi")
            self.assertEqual(result["resolution"], "env")
            self.assertEqual(result["plugin_root"], str(plugin_root))

        with tempfile.TemporaryDirectory() as tmp:
            agent_dir = Path(tmp) / "agent"
            plugin_root = make_plugin_root(
                agent_dir / "git" / "wangdahoo",
                "golden-hoop-spell/plugin",
            )
            # paths.pi_agent_dir stays None: the PI_CODING_AGENT_DIR env var
            # is both the marker and the glob-base override.
            result = detect(
                {"PI_CODING_AGENT_DIR": str(agent_dir)},
                DetectPaths(
                    claude_home=empty_dir(tmp, "claude-home"),
                    codex_home=None,
                    pi_agent_dir=None,
                ),
            )
            self.assertEqual(result["host"], "pi")
            self.assertEqual(result["resolution"], "cache-glob")
            self.assertEqual(result["plugin_root"], str(plugin_root))

    def test_host_compat_double_failure_unknown(self):
        """Relevant env cleared and tmp trees without a hit -> unknown/null/
        asked, and the CLI exits 1 (accepting --project-dir without effect)."""
        with tempfile.TemporaryDirectory() as tmp:
            result = detect(
                {"UNRELATED_VAR": "x"},
                DetectPaths(
                    claude_home=empty_dir(tmp, "claude-home"),
                    codex_home=empty_dir(tmp, "codex-home"),
                    pi_agent_dir=empty_dir(tmp, "agent"),
                ),
            )
            self.assertEqual(
                result,
                {"host": "unknown", "plugin_root": None, "resolution": "asked"},
            )

        with tempfile.TemporaryDirectory() as tmp:
            rc, out, err = run_cli(
                ["--project-dir", tmp],
                env_extra=marker_free_env(empty_dir(tmp, "home")),
            )
            self.assertEqual(rc, 1, f"stdout={out!r}\nstderr={err!r}")
            self.assertEqual(json.loads(out.strip())["host"], "unknown")
            self.assertEqual(json.loads(out.strip())["plugin_root"], None)
            self.assertEqual(json.loads(out.strip())["resolution"], "asked")

    def test_codex_marker_wins_over_valid_env_root(self):
        """A CODEX_ marker plus a valid CLAUDE_PLUGIN_ROOT -> host=codex (not
        claude-code): host markers decide before the claude env root."""
        with tempfile.TemporaryDirectory() as tmp:
            plugin_root = make_plugin_root(tmp, "plugin")
            result = detect(
                {"CODEX_SANDBOX": "1", "CLAUDE_PLUGIN_ROOT": str(plugin_root)},
                DetectPaths(
                    claude_home=empty_dir(tmp, "claude-home"),
                    codex_home=None,
                    pi_agent_dir=None,
                ),
            )
            self.assertEqual(result["host"], "codex")
            self.assertEqual(result["resolution"], "env")
            self.assertEqual(result["plugin_root"], str(plugin_root))

    def test_claude_cache_glob_nested_layout(self):
        """No markers, no env root, nested cache layout -> claude-code via
        cache-glob with the highest version picked."""
        with tempfile.TemporaryDirectory() as tmp:
            claude_home = Path(tmp) / "claude-home"
            cache = claude_home / "plugins" / "cache"
            make_plugin_root(cache / "golden-hoop-spell" / "golden-hoop-spell" / "0.5.1", ".")
            plugin_root = make_plugin_root(
                cache / "golden-hoop-spell" / "golden-hoop-spell", "0.6.0"
            )
            result = detect(
                {},
                DetectPaths(claude_home=claude_home, codex_home=None, pi_agent_dir=None),
            )
            self.assertEqual(result["host"], "claude-code")
            self.assertEqual(result["resolution"], "cache-glob")
            self.assertEqual(result["plugin_root"], str(plugin_root))

    def test_codex_home_env_var_overrides_paths_anchor(self):
        """CODEX_HOME env var wins over the DetectPaths anchor as the glob
        base ($CODEX_HOME/plugins/cache, default ~/.codex/plugins/cache)."""
        with tempfile.TemporaryDirectory() as tmp:
            custom_home = Path(tmp) / "custom-codex-home"
            plugin_root = make_plugin_root(
                custom_home / "plugins" / "cache" / "mkt" / "golden-hoop-spell",
                "0.6.0",
            )
            result = detect(
                {"CODEX_HOME": str(custom_home)},
                DetectPaths(
                    claude_home=empty_dir(tmp, "claude-home"),
                    codex_home=empty_dir(tmp, "ignored-codex-home"),
                    pi_agent_dir=None,
                ),
            )
            self.assertEqual(result["host"], "codex")
            self.assertEqual(result["resolution"], "cache-glob")
            self.assertEqual(result["plugin_root"], str(plugin_root))

    def test_invalid_env_root_falls_to_cache_glob(self):
        """An env root without the sentinel is invalid: a codex marker with a
        stale CLAUDE_PLUGIN_ROOT still resolves via the codex cache glob."""
        with tempfile.TemporaryDirectory() as tmp:
            bogus_root = empty_dir(tmp, "bogus-root")
            codex_home = Path(tmp) / "codex-home"
            plugin_root = make_plugin_root(
                codex_home / "plugins" / "cache" / "mkt" / "golden-hoop-spell",
                "0.6.0",
            )
            result = detect(
                {"CODEX_SANDBOX": "1", "CLAUDE_PLUGIN_ROOT": str(bogus_root)},
                DetectPaths(
                    claude_home=empty_dir(tmp, "claude-home"),
                    codex_home=codex_home,
                    pi_agent_dir=None,
                ),
            )
            self.assertEqual(result["host"], "codex")
            self.assertEqual(result["resolution"], "cache-glob")
            self.assertEqual(result["plugin_root"], str(plugin_root))

    def test_version_pick_digit_aware_and_local_wins(self):
        """0.10.0 beats 0.9.0 (numeric, not lexicographic); local beats any
        numbered version."""
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex-home"
            cache = codex_home / "plugins" / "cache"
            make_plugin_root(cache / "mkt" / "golden-hoop-spell", "0.9.0")
            plugin_root = make_plugin_root(cache / "mkt" / "golden-hoop-spell", "0.10.0")
            result = detect(
                {"CODEX_SANDBOX": "1"},
                DetectPaths(
                    claude_home=empty_dir(tmp, "claude-home"),
                    codex_home=codex_home,
                    pi_agent_dir=None,
                ),
            )
            self.assertEqual(result["plugin_root"], str(plugin_root))

        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex-home"
            cache = codex_home / "plugins" / "cache"
            make_plugin_root(cache / "mkt" / "golden-hoop-spell", "0.9.0")
            plugin_root = make_plugin_root(cache / "mkt" / "golden-hoop-spell", "local")
            result = detect(
                {"CODEX_SANDBOX": "1"},
                DetectPaths(
                    claude_home=empty_dir(tmp, "claude-home"),
                    codex_home=codex_home,
                    pi_agent_dir=None,
                ),
            )
            self.assertEqual(result["plugin_root"], str(plugin_root))

    def test_glob_requires_plugin_name_in_path(self):
        """A sentinel tree whose path lacks 'golden-hoop-spell' is filtered
        out; detection must fall through to unknown."""
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex-home"
            make_plugin_root(
                codex_home / "plugins" / "cache" / "mkt" / "other-plugin",
                "0.6.0",
            )
            result = detect(
                {"CODEX_SANDBOX": "1"},
                DetectPaths(
                    claude_home=empty_dir(tmp, "claude-home"),
                    codex_home=codex_home,
                    pi_agent_dir=None,
                ),
            )
            self.assertEqual(
                result,
                {"host": "unknown", "plugin_root": None, "resolution": "asked"},
            )


class HostCompatVersionKeyTests(unittest.TestCase):
    def test_local_sorts_above_numbered_versions(self):
        self.assertGreater(
            host_compat._version_sort_key("local"),
            host_compat._version_sort_key("99.99.99"),
        )

    def test_digit_aware_comparison(self):
        self.assertGreater(
            host_compat._version_sort_key("0.10.0"),
            host_compat._version_sort_key("0.9.0"),
        )
        self.assertGreater(
            host_compat._version_sort_key("0.6.0"),
            host_compat._version_sort_key("0.5.1"),
        )


if __name__ == "__main__":
    unittest.main()
