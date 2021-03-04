#!/usr/bin/env bash

. venv/bin/activate
cd "${BASH_SOURCE[0]%/*}"/..
python3 codecheck/code_check.py "$@"
