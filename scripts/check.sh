#!/usr/bin/env bash
# Local check: what CI runs on every push, minus the pip-install step.
set -euo pipefail
cd "$(dirname "$0")/../rostering-mvp"
echo ":: unit tests (both regimes)"
python3 -m unittest discover -s . -p 'test_*.py'
echo ":: benchmark smoke grid"
python3 bench.py --quick > /dev/null
echo ":: demo smoke (FAR117)"
python3 run_demo.py | grep -q "reports written"
echo "OK — all checks passed"