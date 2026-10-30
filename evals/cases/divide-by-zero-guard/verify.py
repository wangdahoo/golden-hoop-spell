#!/usr/bin/env python3
"""Hidden verifier for the divide-by-zero-guard benchmark case."""

import importlib.util
import sys
from pathlib import Path


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("candidate_calc", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    workdir = Path(sys.argv[1])
    try:
        calc = load_module(workdir / "calc.py")
    except Exception as exc:
        print(f"cannot import calc.py: {exc}")
        return 1

    cases = [
        ((7, 2), 3),
        ((-7, 2), -3),
        ((7, -2), -3),
        ((-7, -2), 3),
        ((0, 5), 0),
    ]
    for (numerator, divisor), expected in cases:
        try:
            actual = calc.divide(numerator, divisor)
        except Exception as exc:
            print(f"divide({numerator}, {divisor}) raised {type(exc).__name__}: {exc}")
            return 1
        if actual != expected:
            print(f"divide({numerator}, {divisor}) returned {actual}; expected {expected}")
            return 1

    try:
        calc.divide(7, 0)
    except ValueError:
        return 0
    except Exception as exc:
        print(f"divide(7, 0) raised {type(exc).__name__}: {exc}; expected ValueError")
        return 1
    print("divide(7, 0) did not raise ValueError")
    return 1


if __name__ == "__main__":
    sys.exit(main())
