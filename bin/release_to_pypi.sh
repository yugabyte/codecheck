#!/usr/bin/env bash

export TWINE_USERNAME=yugabyte

set -euo pipefail -x
cd "${BASH_SOURCE[0]%/*}"/..

rm -f dist/*
python3 setup.py sdist
python3 -m twine upload dist/*
