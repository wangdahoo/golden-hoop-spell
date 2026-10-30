#!/usr/bin/env python3
"""Tests for validate_manifests.py.

Every test builds a disposable repo fixture under tempfile.TemporaryDirectory
and runs the CLI against it via --repo-root, so neither the real repo nor any
host cache is touched by the assertions.

Run directly:
    command python3 plugin/shared/scripts/test_validate_manifests.py

No pytest dependency. Uses only the standard unittest module.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

CLAUDE_MANIFEST = {
    "name": "golden-hoop-spell",
    "version": "0.6.0",
    "displayName": "Golden Hoop Spell",
    "description": (
        "A skill suite for iterative planning, feature breakdown, and "
        "disciplined code delivery with Claude Code"
    ),
    "author": {"name": "wangdahoo"},
    "repository": "https://github.com/wangdahoo/golden-hoop-spell",
    "license": "MIT",
    "keywords": ["claude", "claude-code", "skills", "plugin"],
}

CODEX_MANIFEST = {
    "name": "golden-hoop-spell",
    "version": "0.6.0",
    "description": (
        "A skill suite for iterative planning, feature breakdown, and "
        "disciplined code delivery with OpenAI Codex CLI"
    ),
    "skills": "./skills/",
    "author": {"name": "wangdahoo"},
    "repository": "https://github.com/wangdahoo/golden-hoop-spell",
    "license": "MIT",
    "keywords": ["claude", "claude-code", "skills", "plugin", "codex", "openai"],
}

MARKETPLACE = {
    "name": "golden-hoop-spell",
    "description": (
        "A skill suite for iterative planning, feature breakdown, and "
        "disciplined code delivery with Claude Code"
    ),
    "owner": {"name": "wangdahoo"},
    "plugins": [
        {
            "name": "golden-hoop-spell",
            "source": "./plugin",
            "description": (
                "A Claude Code plugin for plan-driven project management and "
                "disciplined code delivery with Claude Code"
            ),
        }
    ],
}

PACKAGE_JSON = {
    "name": "golden-hoop-spell",
    "private": True,
    "version": "0.6.0",
    "pi": {
        "extensions": ["plugin/pi-extensions"],
        "skills": ["plugin/skills"],
    },
}

SKILL_STUB = """---
name: stub-skill
description: Stub skill used by validate_manifests tests.
---

# Stub skill
"""


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def build_fixture_repo(root):
    """Create a minimal consistent repo fixture under root; return the root.

    Mirrors the real layout: plugin/.claude-plugin/plugin.json,
    plugin/.codex-plugin/plugin.json, plugin/skills/<7 dirs>/SKILL.md,
    plugin/shared/, root .claude-plugin/marketplace.json and root
    package.json. plugin/pi-extensions is deliberately absent: check 5 must
    not require the extension directory on disk.
    """
    root = Path(root)
    plugin_dir = root / "plugin"
    scripts_dir = plugin_dir / "shared" / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "ghs_compat.py").write_text("# stub\n", encoding="utf-8")

    for index in range(1, 8):
        skill_dir = plugin_dir / "skills" / f"ghs-stub-{index:02d}"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(SKILL_STUB, encoding="utf-8")

    _write_json(plugin_dir / ".claude-plugin" / "plugin.json", CLAUDE_MANIFEST)
    _write_json(plugin_dir / ".codex-plugin" / "plugin.json", CODEX_MANIFEST)
    _write_json(root / ".claude-plugin" / "marketplace.json", MARKETPLACE)
    _write_json(root / "package.json", PACKAGE_JSON)
    return root


def run_cli(args):
    """Run validate_manifests.py as a subprocess.

    Returns (returncode, stdout, stderr). Output is always decoded as UTF-8
    (errors=replace) regardless of the parent console encoding.
    """
    cmd = [sys.executable, str(SCRIPT_DIR / "validate_manifests.py")] + args
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout, proc.stderr


def fail_lines(output):
    return [line for line in output.splitlines() if line.startswith("FAIL")]


class ValidateManifestsFixtureTests(unittest.TestCase):
    def test_validate_manifests_ok_fixture(self):
        """A consistent fixture -> every check prints OK and the CLI exits 0."""
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = build_fixture_repo(Path(tmp) / "repo")
            rc, out, err = run_cli(["--repo-root", str(repo_root)])
            self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
            self.assertEqual(fail_lines(out), [], f"stdout={out!r}")
            ok_lines = [line for line in out.splitlines() if line.startswith("OK ")]
            self.assertEqual(len(ok_lines), 6, f"stdout={out!r}")

    def test_validate_manifests_version_mismatch(self):
        """Tampered codex manifest version -> exit 1 and a 'version mismatch'
        FAIL line from the equality check."""
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = build_fixture_repo(Path(tmp) / "repo")
            tampered = dict(CODEX_MANIFEST, version="0.7.0")
            _write_json(
                repo_root / "plugin" / ".codex-plugin" / "plugin.json", tampered
            )
            rc, out, err = run_cli(["--repo-root", str(repo_root)])
            self.assertEqual(rc, 1, f"stdout={out!r}\nstderr={err!r}")
            self.assertIn("version mismatch", out)
            self.assertEqual(len(fail_lines(out)), 1, f"stdout={out!r}")
            self.assertIn("FAIL [2/6]", out)

    def test_validate_manifests_missing_codex_manifest(self):
        """Deleted codex manifest -> exit 1 with check 1 failing."""
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = build_fixture_repo(Path(tmp) / "repo")
            (repo_root / "plugin" / ".codex-plugin" / "plugin.json").unlink()
            rc, out, err = run_cli(["--repo-root", str(repo_root)])
            self.assertEqual(rc, 1, f"stdout={out!r}\nstderr={err!r}")
            self.assertIn("FAIL [1/6]", out)
            self.assertIn("file not found", out)

    def test_validate_manifests_pi_skills_glob_broken(self):
        """pi.skills pointing at a missing directory -> exit 1 with check 5
        failing."""
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = build_fixture_repo(Path(tmp) / "repo")
            broken = json.loads(json.dumps(PACKAGE_JSON))
            broken["pi"]["skills"] = ["plugin/no-such-dir"]
            _write_json(repo_root / "package.json", broken)
            rc, out, err = run_cli(["--repo-root", str(repo_root)])
            self.assertEqual(rc, 1, f"stdout={out!r}\nstderr={err!r}")
            self.assertIn("FAIL [5/6]", out)
            self.assertIn("pi.skills directory not found", out)

    def test_validate_manifests_marketplace_source_broken(self):
        """Marketplace source without codex manifest/skills/shared -> exit 1
        with check 4 failing."""
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = build_fixture_repo(Path(tmp) / "repo")
            broken = json.loads(json.dumps(MARKETPLACE))
            broken["plugins"][0]["source"] = "./elsewhere"
            _write_json(repo_root / ".claude-plugin" / "marketplace.json", broken)
            rc, out, err = run_cli(["--repo-root", str(repo_root)])
            self.assertEqual(rc, 1, f"stdout={out!r}\nstderr={err!r}")
            self.assertIn("FAIL [4/6]", out)
            self.assertIn("misses", out)

    def test_validate_manifests_agents_marketplace_cross_check(self):
        """An .agents marketplace mirroring the legacy one keeps exit 0; a
        drifted copy fails check 6."""
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = build_fixture_repo(Path(tmp) / "repo")
            _write_json(
                repo_root / ".agents" / "plugins" / "marketplace.json", MARKETPLACE
            )
            rc, out, err = run_cli(["--repo-root", str(repo_root)])
            self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
            self.assertIn("OK [6/6]", out)

        with tempfile.TemporaryDirectory() as tmp:
            repo_root = build_fixture_repo(Path(tmp) / "repo")
            drifted = json.loads(json.dumps(MARKETPLACE))
            drifted["plugins"][0]["name"] = "other-plugin"
            _write_json(
                repo_root / ".agents" / "plugins" / "marketplace.json", drifted
            )
            rc, out, err = run_cli(["--repo-root", str(repo_root)])
            self.assertEqual(rc, 1, f"stdout={out!r}\nstderr={err!r}")
            self.assertIn("FAIL [6/6]", out)


if __name__ == "__main__":
    unittest.main()
