#!/usr/bin/env python3
"""Preserve a CI command's failure and expose bounded output in check annotations."""
from __future__ import annotations

import subprocess
import sys


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: ci_command.py COMMAND [ARG ...]")
    result = subprocess.run(sys.argv[1:], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = result.stdout.decode("utf-8", errors="replace")
    print(output, end="" if output.endswith("\n") else "\n", flush=True)
    if result.returncode:
        tail = output[-10000:]
        diagnostic = f"{sys.argv[1]} exited with {result.returncode}\n{tail}"
        escaped = diagnostic.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print("::error title=Windows command failure::" + escaped, flush=True)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
