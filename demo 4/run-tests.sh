#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}/server"

echo "==> Running all backend tests"
python -m pytest -q

echo
echo "==> Running focused advanced-feature suites"
python -m pytest tests/test_security_analyzer.py tests/test_api_endpoints.py -q

echo
echo "Done."
