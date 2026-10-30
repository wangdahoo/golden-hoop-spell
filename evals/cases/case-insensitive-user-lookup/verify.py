#!/usr/bin/env python3
"""Hidden verifier for the case-insensitive-user-lookup benchmark case."""

import importlib.util
import sys
from pathlib import Path


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("candidate_users", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    workdir = Path(sys.argv[1])
    try:
        users = load_module(workdir / "users.py")
    except Exception as exc:
        print(f"cannot import users.py: {exc}")
        return 1

    first = {"id": 1, "email": "Ada@example.com"}
    second = {"id": 2, "email": "ada@example.com"}
    records = [first, second]
    snapshot = [dict(record) for record in records]

    checks = [
        ((records, "ADA@EXAMPLE.COM"), first),
        ((records, "ada@example.com"), first),
        ((records, "bob@example.com"), None),
        (([], "ada@example.com"), None),
    ]
    for arguments, expected in checks:
        try:
            actual = users.find_user(*arguments)
        except Exception as exc:
            print(f"find_user{arguments!r} raised {type(exc).__name__}: {exc}")
            return 1
        if actual is not expected:
            print(f"find_user{arguments!r} returned the wrong record")
            return 1

    if records != snapshot or [dict(record) for record in records] != snapshot:
        print("find_user must not mutate the input")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
