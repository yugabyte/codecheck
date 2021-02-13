#!/usr/bin/env bash

set -euo pipefail -x
cd "${BASH_SOURCE[0]%/*}"/..

rm -f dist/*
python3 setup.py sdist
python3 -m twine upload --repository testpypi dist/*
