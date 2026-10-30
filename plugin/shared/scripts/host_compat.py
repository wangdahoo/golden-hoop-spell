#!/usr/bin/env python3
"""Detect the ghs host harness and resolve the plugin root.

Single source of truth for cross-host plugin-root resolution. Prints one
single-line JSON object to stdout:

    {"host": "claude-code"|"codex"|"pi"|"unknown",
     "plugin_root": "<abs path>"|null,
     "resolution": "env"|"cache-glob"|"asked"}

Exit codes: 0 - host and plugin root resolved; 1 - unknown (ask the user).

Detection order (first hit wins; a root is valid only if
``<root>/shared/scripts/ghs_compat.py`` exists; cache globs are recursive
``**/shared/scripts/ghs_compat.py`` filtered to paths containing
"golden-hoop-spell", which covers both the nested and the ``@``-flat cache
layouts; multiple hits resolve to the highest version, compared with a
digit-aware tuple where ``local`` wins):

1. Any ``CODEX_``-prefixed env var -> host=codex; root: ``CLAUDE_PLUGIN_ROOT``,
   then ``PLUGIN_ROOT`` (resolution=env), else recursive glob of
   ``$CODEX_HOME/plugins/cache`` (default ``~/.codex/plugins/cache``).
2. pi marker env ``{PI_SESSION_ID, PI_SESSION_FILE, PI_CODING_AGENT_DIR}`` ->
   host=pi; root: the same two env vars as above, else recursive glob of
   ``$PI_CODING_AGENT_DIR`` (default ``~/.pi/agent``), which covers both its
   ``skills/`` and ``git/`` landing spots. Project-level ``.pi/`` installs are
   in-place path references handled by the SKILL.md pointer-block bootstrap,
   not by this glob.
3. Valid ``CLAUDE_PLUGIN_ROOT`` -> claude-code / env.
4. Valid ``PLUGIN_ROOT`` -> claude-code / env.
5. Recursive glob of ``~/.claude/plugins/cache`` -> claude-code / cache-glob.
6. All probes fail -> unknown / asked / exit 1.

Host markers take priority over ``CLAUDE_PLUGIN_ROOT`` when deciding the host,
so a host that expands that variable for compatibility is never mislabelled as
claude-code (which would skip the per-host reference files). Once a host
marker is seen, root resolution stays scoped to that host's search spaces; a
failed resolution reports unknown/asked instead of falling through to the
claude-code probes.

Usage:
    command python3 plugin/shared/scripts/host_compat.py [--project-dir DIR]

``--project-dir`` is accepted for CLI symmetry with the other ghs scripts but
does not participate in detection. Standard library only; never prompts.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ghs_compat import force_utf8_stdio

SENTINEL_RELPATH = Path("shared") / "scripts" / "ghs_compat.py"
SENTINEL_GLOB = "**/shared/scripts/ghs_compat.py"
PLUGIN_NAME_TOKEN = "golden-hoop-spell"
CODEX_MARKER_PREFIX = "CODEX_"
PI_MARKER_VARS = ("PI_SESSION_ID", "PI_SESSION_FILE", "PI_CODING_AGENT_DIR")
ENV_ROOT_VARS = ("CLAUDE_PLUGIN_ROOT", "PLUGIN_ROOT")
LOCAL_VERSION = "local"


@dataclass(frozen=True)
class DetectPaths:
    """Filesystem anchors for detection.

    ``claude_home`` is required; ``codex_home`` and ``pi_agent_dir`` may be
    None to disable the corresponding cache-glob probe (used by tests and
    constrained embedders).
    """

    claude_home: Path
    codex_home: Path | None = None
    pi_agent_dir: Path | None = None


def _env_str(env: Mapping[str, str], name: str) -> "str | None":
    """Return the env value, treating unset and empty identically."""
    value = env.get(name)
    if value is None or value == "":
        return None
    return value


def _has_codex_marker(env: Mapping[str, str]) -> bool:
    """True when any non-empty CODEX_-prefixed env var is present."""
    return any(
        key.startswith(CODEX_MARKER_PREFIX) and value != ""
        for key, value in env.items()
    )


def _has_pi_marker(env: Mapping[str, str]) -> bool:
    """True when any pi marker env var is present."""
    return any(_env_str(env, name) is not None for name in PI_MARKER_VARS)


def _valid_env_root(env: Mapping[str, str]) -> "Path | None":
    """First valid root among ENV_ROOT_VARS, in contract order.

    A root is valid only if ``<root>/shared/scripts/ghs_compat.py`` exists.
    """
    for name in ENV_ROOT_VARS:
        value = _env_str(env, name)
        if value is None:
            continue
        root = Path(value)
        if (root / SENTINEL_RELPATH).is_file():
            return root
    return None


def _version_sort_key(name: str) -> tuple:
    """Digit-aware sortable key for a version segment.

    Digit runs compare numerically (0.10.0 > 0.9.0), text runs compare as
    strings; ``local`` sorts above every numbered version.
    """
    if name == LOCAL_VERSION:
        return (1, ())
    parts = tuple(
        (1, int(part), "") if part.isdigit() else (0, 0, part)
        for part in re.findall(r"\d+|\D+", name)
    )
    return (0, parts)


def _pick_best_hit(hits: "list[Path]") -> "Path | None":
    """Pick the highest-version hit; 'local' wins; ties break on the path
    string for deterministic output. Returns the plugin root (the sentinel's
    grandparent directory), not the sentinel file itself."""
    if not hits:
        return None

    def sort_key(path: Path) -> tuple:
        # <...>/<version>/shared/scripts/ghs_compat.py -> version segment
        version_dir = path.parents[2]
        return (_version_sort_key(version_dir.name), str(path))

    return max(hits, key=sort_key).parents[2]


def _glob_plugin_roots(base: "Path | None") -> "list[Path]":
    """Recursive sentinel glob under base, filtered to ghs plugin paths.

    The name filter makes the glob insensitive to the exact cache layout
    (nested marketplace/plugin/version trees and ``@``-flat joins both match).
    """
    if base is None:
        return []
    base = Path(base)
    if not base.is_dir():
        return []
    try:
        candidates = list(base.glob(SENTINEL_GLOB))
    except OSError:
        return []
    return [p for p in candidates if PLUGIN_NAME_TOKEN in str(p)]


def _result(host: str, root: "Path | None", resolution: str) -> dict:
    return {
        "host": host,
        "plugin_root": str(root) if root is not None else None,
        "resolution": resolution,
    }


def _unknown() -> dict:
    return _result("unknown", None, "asked")


def detect(env: Mapping[str, str], paths: DetectPaths) -> dict:
    """Pure detection core.

    ``env`` supplies host markers and root candidates; ``paths`` supplies the
    filesystem anchors. Env marker variables (``CODEX_HOME`` /
    ``PI_CODING_AGENT_DIR``) override the matching ``paths`` anchor. Never
    touches the filesystem outside ``paths``.
    """
    env_root = _valid_env_root(env)

    if _has_codex_marker(env):
        if env_root is not None:
            return _result("codex", env_root, "env")
        codex_home = _env_str(env, "CODEX_HOME")
        base = Path(codex_home) if codex_home else paths.codex_home
        cache = base / "plugins" / "cache" if base is not None else None
        root = _pick_best_hit(_glob_plugin_roots(cache))
        if root is not None:
            return _result("codex", root, "cache-glob")
        return _unknown()

    if _has_pi_marker(env):
        if env_root is not None:
            return _result("pi", env_root, "env")
        agent_dir = _env_str(env, "PI_CODING_AGENT_DIR")
        base = Path(agent_dir) if agent_dir else paths.pi_agent_dir
        root = _pick_best_hit(_glob_plugin_roots(base))
        if root is not None:
            return _result("pi", root, "cache-glob")
        return _unknown()

    if env_root is not None:
        return _result("claude-code", env_root, "env")

    cache = (
        paths.claude_home / "plugins" / "cache"
        if paths.claude_home is not None
        else None
    )
    root = _pick_best_hit(_glob_plugin_roots(cache))
    if root is not None:
        return _result("claude-code", root, "cache-glob")

    return _unknown()


def main() -> int:
    force_utf8_stdio()

    parser = argparse.ArgumentParser(
        description="Detect the ghs host harness and resolve the plugin root"
    )
    parser.add_argument(
        "--project-dir",
        default=None,
        help="Accepted for CLI symmetry with other ghs scripts; "
        "not used in detection",
    )
    parser.parse_args()

    home = Path.home()
    paths = DetectPaths(
        claude_home=home / ".claude",
        codex_home=home / ".codex",
        pi_agent_dir=home / ".pi" / "agent",
    )
    result = detect(os.environ, paths)
    print(json.dumps(result))
    return 1 if result["resolution"] == "asked" else 0


if __name__ == "__main__":
    sys.exit(main())
