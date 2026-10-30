#!/usr/bin/env python3
"""Hidden verifier for the word-count-cli benchmark case."""

import subprocess
import sys
import tempfile
from pathlib import Path


def run_counter(program: Path, text: str) -> tuple[int, str]:
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".txt", delete=False
    ) as stream:
        stream.write(text)
        path = Path(stream.name)
    try:
        completed = subprocess.run(
            [sys.executable, str(program), str(path)],
            cwd=program.parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
    finally:
        path.unlink(missing_ok=True)
    return completed.returncode, completed.stdout.strip()


def main() -> int:
    program = Path(sys.argv[1]) / "word_count.py"
    cases = [
        ("alpha beta gamma\n", "3"),
        ("  alpha\t\tbeta\n\ngamma  ", "3"),
        ("中文 tokens\tUTF-8\n", "3"),
        ("", "0"),
        ("   \n\t\n", "0"),
    ]
    for text, expected in cases:
        return_code, stdout = run_counter(program, text)
        if return_code != 0:
            print(f"word_count.py exited {return_code} for input {text!r}")
            return 1
        if stdout != expected:
            print(f"word_count.py printed {stdout!r}; expected {expected!r}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
