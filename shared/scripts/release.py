#!/usr/bin/env python3
"""
Release Skill - Package and upload skill to GitHub Releases

Usage:
    python3 scripts/release.py <version> [--dry-run]

Examples:
    python3 scripts/release.py v1.0.0
    python3 scripts/release.py 0.4.0-beta.2
    python3 scripts/release.py v1.0.0 --dry-run
"""

import argparse
import fnmatch
import re
import subprocess
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SKILL_NAME = "agent-harness"


def run_cmd(cmd, cwd=None, check=True):
    """Run a shell command and return output."""
    result = subprocess.run(
        cmd, shell=True, cwd=cwd, capture_output=True, text=True
    )
    if check and result.returncode != 0:
        print(f"Error: Command failed: {cmd}")
        print(f"   stderr: {result.stderr}")
        sys.exit(1)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def validate_version(version):
    """
    Validate version format using semantic versioning (semver).

    Supports:
    - v1.0.0 or 1.0.0 (basic)
    - v0.4.0-beta.2 or 0.4.0-beta.2 (pre-release)
    - v1.0.0+build.1 or 1.0.0+build.1 (build metadata)

    See: https://semver.org/
    """
    # Remove optional 'v' prefix
    if version.startswith("v"):
        version = version[1:]

    # SemVer regex: MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]
    pattern = r'^(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9]+(?:\.[a-zA-Z0-9]+)*))?(?:\+([a-zA-Z0-9]+(?:\.[a-zA-Z0-9]+)*))?$'

    if not re.match(pattern, version):
        return False, None

    return True, f"v{version}"


def parse_skillignore(skill_path):
    """Parse .skillignore file and return list of patterns."""
    ignore_file = skill_path / ".skillignore"
    patterns = []
    if ignore_file.exists():
        for line in ignore_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
    return patterns


def should_ignore(rel_path, patterns):
    """Check if a path should be ignored based on patterns."""
    path_str = str(rel_path)
    path_parts = rel_path.parts
    
    for pattern in patterns:
        if fnmatch.fnmatch(path_str, pattern):
            return True
        if fnmatch.fnmatch(rel_path.name, pattern):
            return True
        for part in path_parts:
            if fnmatch.fnmatch(part, pattern.rstrip("/")):
                return True
    return False


def package_skill(dry_run=False):
    """Package skill folder into .skill file, respecting .skillignore."""
    output_dir = REPO_ROOT / "dist"
    output_dir.mkdir(exist_ok=True)
    skill_file = output_dir / f"{SKILL_NAME}.skill"
    
    patterns = parse_skillignore(REPO_ROOT)
    
    # Collect files to include
    included_files = []
    excluded_count = 0

    for file_path in REPO_ROOT.rglob('*'):
        if file_path.is_file():
            rel_path = file_path.relative_to(REPO_ROOT)
            if should_ignore(rel_path, patterns):
                excluded_count += 1
                continue
            included_files.append(SKILL_NAME / rel_path)

    if dry_run:
        print(f"[DRY-RUN] Would package to: {skill_file}")
        print(f"[DRY-RUN] Ignore patterns from .skillignore:")
        for p in patterns:
            print(f"  - {p}")
        print(f"\n[DRY-RUN] Files to include:")
        print("-" * 50)
        for f in sorted(included_files):
            print(f"  {f}")
        print("-" * 50)
        print(f"[DRY-RUN] Total: {len(included_files)} files (excluded: {excluded_count})")
        return skill_file
    
    print("Packaging skill...")

    try:
        with zipfile.ZipFile(skill_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for arcname in included_files:
                file_path = REPO_ROOT / arcname.relative_to(SKILL_NAME)
                zipf.write(file_path, arcname)

        # Print all included files
        print(f"\nFiles included in {skill_file.name}:")
        print("-" * 50)
        for f in sorted(included_files):
            print(f"  {f}")
        print("-" * 50)
        print(f"Total: {len(included_files)} files (excluded: {excluded_count})")
        print(f"Output: {skill_file}")
        return skill_file
    
    except Exception as e:
        print(f"Error: Packaging failed: {e}")
        sys.exit(1)


def create_release(version, skill_file, dry_run=False):
    """Create GitHub release and upload skill file."""
    tag = version
    
    returncode, stdout, _ = run_cmd(f"git tag -l {tag}", check=False)
    if tag in stdout:
        print(f"Error: Tag {tag} already exists")
        sys.exit(1)
    
    if dry_run:
        print(f"[DRY-RUN] Would create tag: {tag}")
        print(f"[DRY-RUN] Would push tag to origin")
        print(f"[DRY-RUN] Would create release with: gh release create {tag} {skill_file}")
        return
    
    print(f"Creating tag: {tag}")
    run_cmd(f"git tag {tag}")
    run_cmd(f"git push origin {tag}")
    
    print(f"Creating release: {tag}")
    release_cmd = (
        f'gh release create {tag} {skill_file} '
        f'--title "{SKILL_NAME} {tag}" '
        f'--notes "Release {tag} of {SKILL_NAME} skill"'
    )
    run_cmd(release_cmd)
    print(f"Released: https://github.com/wangdahoo/agent-harness/releases/tag/{tag}")


def main():
    parser = argparse.ArgumentParser(description="Release skill to GitHub")
    parser.add_argument("version", help="Version (e.g., v1.0.0, 0.4.0-beta.2)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without executing")
    args = parser.parse_args()
    
    valid, version = validate_version(args.version)
    if not valid:
        print(f"Error: Invalid version format: {args.version}")
        print("   Expected format: v1.0.0, 0.4.0-beta.2, 1.0.0+build.1")
        sys.exit(1)
    
    print(f"Preparing release: {version}\n")
    
    skill_file = package_skill(args.dry_run)
    
    if not args.dry_run and not skill_file.exists():
        print(f"Error: Packaged file not found: {skill_file}")
        sys.exit(1)
    
    create_release(version, skill_file, args.dry_run)


if __name__ == "__main__":
    main()
