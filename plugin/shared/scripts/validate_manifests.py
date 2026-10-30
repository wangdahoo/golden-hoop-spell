#!/usr/bin/env python3
"""Validate multi-manifest consistency for the ghs plugin.

The same plugin source tree is described by four manifests (Claude, Codex,
pi, marketplace). This script cross-checks them and prints one English
OK/FAIL line per check to stdout:

    OK   [1/6] codex manifest required keys and kebab-case name: ...
    FAIL [2/6] codex/claude manifest name+version equality...: version mismatch ...

Checks (plan 2026-10-30-codex-pi-compat, Design "清单三件套与多清单校验"):

1. ``plugin/.codex-plugin/plugin.json`` exists, has the required keys
   (name/version/description/skills) and a kebab-case name.
2. Its name/version are strictly equal to the Claude manifest
   (``plugin/.claude-plugin/plugin.json``); both descriptions non-empty.
3. The codex manifest ``skills`` path resolves to a directory containing
   exactly 7 SKILL.md files.
4. ``.claude-plugin/marketplace.json`` has exactly one golden-hoop-spell
   entry whose ``source`` resolves (against the repo root) to a directory
   containing the codex manifest plus ``skills/`` and ``shared/``.
5. Root ``package.json``: every ``pi.skills`` entry resolves (against the
   repo root) to a directory with 7 SKILL.md files, ``pi.extensions`` is a
   non-empty string array (the extension directory is deliberately NOT
   required to exist on disk - the extension file lands in a later task),
   and the version equals ``0.6.0``.
6. If ``.agents/plugins/marketplace.json`` exists, cross-check it against
   the legacy marketplace entry by entry; its absence is OK by design.

Exit codes: 0 - all checks pass; 1 - at least one check failed.

Usage:
    command python3 plugin/shared/scripts/validate_manifests.py [--repo-root DIR]

Standard library only; never prompts.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from ghs_compat import force_utf8_stdio

PLUGIN_NAME = "golden-hoop-spell"
EXPECTED_VERSION = "0.6.0"
EXPECTED_SKILL_COUNT = 7

CODEX_MANIFEST_RELPATH = Path("plugin") / ".codex-plugin" / "plugin.json"
CLAUDE_MANIFEST_RELPATH = Path("plugin") / ".claude-plugin" / "plugin.json"
MARKETPLACE_RELPATH = Path(".claude-plugin") / "marketplace.json"
AGENTS_MARKETPLACE_RELPATH = Path(".agents") / "plugins" / "marketplace.json"
PACKAGE_JSON_RELPATH = Path("package.json")

KEBAB_CASE_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _load_json_object(path: Path) -> "tuple[dict | None, str | None]":
    """Load a JSON object; return (data, None) or (None, failure reason)."""
    if not path.is_file():
        return None, f"file not found: {path}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return None, f"cannot read JSON: {exc}"
    if not isinstance(data, dict):
        return None, "top-level JSON value is not an object"
    return data, None


def _resolve_against(base: Path, raw) -> "Path | None":
    """Resolve a manifest path field against base.

    Returns None when the field is not a usable (non-empty) path string.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate


def _count_skill_files(skills_dir: "Path | None") -> "int | None":
    """Count ``<skill-dir>/SKILL.md`` files; None when the dir is missing."""
    if skills_dir is None or not skills_dir.is_dir():
        return None
    return sum(1 for path in skills_dir.glob("*/SKILL.md") if path.is_file())


def check_codex_manifest(repo_root: Path) -> "tuple[bool, str]":
    """Check 1: codex manifest exists, required keys, kebab-case name."""
    data, error = _load_json_object(repo_root / CODEX_MANIFEST_RELPATH)
    if error is not None:
        return False, error
    missing = [
        key for key in ("name", "version", "description", "skills")
        if key not in data
    ]
    if missing:
        return False, f"missing required keys: {', '.join(missing)}"
    name = data["name"]
    if not isinstance(name, str) or not KEBAB_CASE_RE.match(name):
        return False, f"name is not kebab-case: {name!r}"
    return True, f"name={name!r} version={data['version']!r} skills={data['skills']!r}"


def check_manifest_equality(repo_root: Path) -> "tuple[bool, str]":
    """Check 2: name/version strictly equal to the Claude manifest and both
    descriptions non-empty."""
    codex, codex_error = _load_json_object(repo_root / CODEX_MANIFEST_RELPATH)
    if codex_error is not None:
        return False, f"codex manifest unavailable: {codex_error}"
    claude, claude_error = _load_json_object(repo_root / CLAUDE_MANIFEST_RELPATH)
    if claude_error is not None:
        return False, f"Claude manifest unavailable: {claude_error}"

    codex_name, claude_name = codex.get("name"), claude.get("name")
    if codex_name != claude_name:
        return False, f"name mismatch: codex={codex_name!r} claude={claude_name!r}"
    codex_version, claude_version = codex.get("version"), claude.get("version")
    if codex_version != claude_version:
        return False, (
            f"version mismatch: codex={codex_version!r} claude={claude_version!r}"
        )

    for label, data in (("codex", codex), ("claude", claude)):
        description = data.get("description")
        if not isinstance(description, str) or not description.strip():
            return False, f"empty description in the {label} manifest"
    return True, (
        f"name={codex_name!r} version={codex_version!r} "
        "matches the Claude manifest, descriptions non-empty"
    )


def check_codex_skills(repo_root: Path) -> "tuple[bool, str]":
    """Check 3: the codex skills path resolves to a directory with exactly
    EXPECTED_SKILL_COUNT SKILL.md files."""
    data, error = _load_json_object(repo_root / CODEX_MANIFEST_RELPATH)
    if error is not None:
        return False, f"codex manifest unavailable: {error}"
    # The codex manifest lives at <plugin_root>/.codex-plugin/plugin.json, so
    # its plugin root is the manifest file's grandparent directory; the
    # `skills` path resolves against that root (Codex manifest semantics).
    plugin_root = (repo_root / CODEX_MANIFEST_RELPATH).parents[1]
    skills_dir = _resolve_against(plugin_root, data.get("skills"))
    if skills_dir is None:
        return False, f"skills is not a path string: {data.get('skills')!r}"
    count = _count_skill_files(skills_dir)
    if count is None:
        return False, f"skills directory not found: {skills_dir}"
    if count != EXPECTED_SKILL_COUNT:
        return False, (
            f"expected {EXPECTED_SKILL_COUNT} SKILL.md files under {skills_dir}, "
            f"found {count}"
        )
    return True, f"{count} SKILL.md files under {skills_dir}"


def check_marketplace(repo_root: Path) -> "tuple[bool, str]":
    """Check 4: exactly one golden-hoop-spell entry whose source resolves to
    a directory holding the codex manifest plus skills/ and shared/."""
    data, error = _load_json_object(repo_root / MARKETPLACE_RELPATH)
    if error is not None:
        return False, error
    plugins = data.get("plugins")
    if not isinstance(plugins, list):
        return False, "marketplace has no plugins array"
    entries = [
        entry for entry in plugins
        if isinstance(entry, dict) and entry.get("name") == PLUGIN_NAME
    ]
    if len(entries) != 1:
        return False, (
            f"expected exactly one {PLUGIN_NAME!r} entry, found {len(entries)}"
        )
    raw_source = entries[0].get("source")
    source = _resolve_against(repo_root, raw_source)
    if source is None:
        return False, f"entry source is not a path string: {raw_source!r}"
    required = [
        (".codex-plugin/plugin.json", source / ".codex-plugin" / "plugin.json"),
        ("skills/", source / "skills"),
        ("shared/", source / "shared"),
    ]
    missing = [
        label
        for label, path in required
        if not (path.is_file() if label.endswith("plugin.json") else path.is_dir())
    ]
    if missing:
        return False, (
            f"source {raw_source!r} -> {source} misses: {', '.join(missing)}"
        )
    return True, (
        f"source {raw_source!r} -> {source} has codex manifest, skills/, shared/"
    )


def check_package_json(repo_root: Path) -> "tuple[bool, str]":
    """Check 5: pi.skills globs resolve with 7 SKILL.md each, pi.extensions
    is a non-empty string array (disk presence not required), version pinned."""
    data, error = _load_json_object(repo_root / PACKAGE_JSON_RELPATH)
    if error is not None:
        return False, error
    pi = data.get("pi")
    if not isinstance(pi, dict):
        return False, "package.json has no pi object"

    skills = pi.get("skills")
    if (
        not isinstance(skills, list)
        or not skills
        or not all(isinstance(raw, str) and raw.strip() for raw in skills)
    ):
        return False, f"pi.skills must be a non-empty array of path strings: {skills!r}"
    for raw in skills:
        skills_dir = _resolve_against(repo_root, raw)
        count = _count_skill_files(skills_dir)
        if count is None:
            return False, f"pi.skills directory not found: {raw!r}"
        if count != EXPECTED_SKILL_COUNT:
            return False, (
                f"expected {EXPECTED_SKILL_COUNT} SKILL.md files under "
                f"{skills_dir}, found {count}"
            )

    extensions = pi.get("extensions")
    if (
        not isinstance(extensions, list)
        or not extensions
        or not all(isinstance(raw, str) and raw.strip() for raw in extensions)
    ):
        return False, (
            "pi.extensions must be a non-empty array of strings: "
            f"{extensions!r}"
        )

    version = data.get("version")
    if version != EXPECTED_VERSION:
        return False, (
            f"version mismatch: package.json={version!r} "
            f"expected {EXPECTED_VERSION!r}"
        )
    return True, (
        f"pi.skills -> {', '.join(skills)} ({EXPECTED_SKILL_COUNT} SKILL.md each); "
        f"pi.extensions -> {extensions}; version {version}"
    )


def check_agents_marketplace(repo_root: Path) -> "tuple[bool, str]":
    """Check 6: optional .agents marketplace mirrors the legacy marketplace
    entry by entry; absence is OK by design."""
    agents_path = repo_root / AGENTS_MARKETPLACE_RELPATH
    if not agents_path.exists():
        return True, "absent, nothing to cross-check"

    agents, agents_error = _load_json_object(agents_path)
    if agents_error is not None:
        return False, f".agents marketplace unavailable: {agents_error}"
    legacy, legacy_error = _load_json_object(repo_root / MARKETPLACE_RELPATH)
    if legacy_error is not None:
        return False, f"legacy marketplace unavailable: {legacy_error}"

    agents_plugins = agents.get("plugins")
    legacy_plugins = legacy.get("plugins")
    if not isinstance(agents_plugins, list):
        return False, ".agents marketplace has no plugins array"
    if not isinstance(legacy_plugins, list):
        return False, "legacy marketplace has no plugins array"
    if len(agents_plugins) != len(legacy_plugins):
        return False, (
            f"entry count mismatch: .agents={len(agents_plugins)} "
            f"legacy={len(legacy_plugins)}"
        )
    for index, (agents_entry, legacy_entry) in enumerate(
        zip(agents_plugins, legacy_plugins)
    ):
        agents_key = _marketplace_entry_key(agents_entry)
        legacy_key = _marketplace_entry_key(legacy_entry)
        if agents_key != legacy_key:
            return False, (
                f"entry {index} mismatch: .agents={agents_key!r} "
                f"legacy={legacy_key!r}"
            )
    return True, (
        f"matches the legacy marketplace entry by entry ({len(agents_plugins)} entries)"
    )


def _marketplace_entry_key(entry) -> "tuple | None":
    """Comparable (name, source) key for one marketplace entry."""
    if not isinstance(entry, dict):
        return None
    return (entry.get("name"), entry.get("source"))


CHECKS = (
    ("codex manifest required keys and kebab-case name", check_codex_manifest),
    (
        "codex/claude manifest name+version equality, non-empty descriptions",
        check_manifest_equality,
    ),
    ("codex skills directory has 7 SKILL.md files", check_codex_skills),
    ("marketplace golden-hoop-spell entry and source resolution", check_marketplace),
    ("package.json pi.skills/pi.extensions/version", check_package_json),
    ("optional .agents marketplace cross-check", check_agents_marketplace),
)


def main() -> int:
    force_utf8_stdio()

    parser = argparse.ArgumentParser(
        description="Validate multi-manifest consistency for the ghs plugin"
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root to validate "
        "(default: three levels above this script)",
    )
    args = parser.parse_args()

    repo_root = (
        Path(args.repo_root).resolve()
        if args.repo_root
        else Path(__file__).resolve().parents[3]
    )

    failed = 0
    total = len(CHECKS)
    for index, (label, check) in enumerate(CHECKS, start=1):
        ok, detail = check(repo_root)
        if not ok:
            failed += 1
        print(f"{'OK' if ok else 'FAIL'} [{index}/{total}] {label}: {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
