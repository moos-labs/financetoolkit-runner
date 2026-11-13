#!/usr/bin/env python3
"""Ticker dispatcher (issue #30): a hand-verified statements CSV in
data/ always wins (the deep, release-basis ratios); every other
ticker goes through the generic StockAnalysis-sourced path."""
import os
import subprocess
import sys


def main():
    ticker = sys.argv[1] if len(sys.argv) > 1 else ""
    code = ticker.split(".")[0].lower()
    deep = os.path.join("data", f"{code}_statements.csv")
    if code and os.path.exists(deep):
        env = dict(os.environ, STATEMENTS_CSV=deep)
        r = subprocess.run([sys.executable, "scripts/ft_ratios.py"], env=env)
    else:
        r = subprocess.run([sys.executable, "scripts/ft_generic.py", ticker])
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
