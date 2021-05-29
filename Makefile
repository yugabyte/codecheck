.PHONY: help venv check
.DEFAULT: help

VENV_NAME?=venv
VENV_ACTIVATE=. $(VENV_NAME)/bin/activate
VENV_PYTHON=$(VENV_NAME)/bin/python3

help:
	@echo "make test"
	@echo "       run tests"
	@echo "make lint"
	@echo "       run pylint and mypy"
	@echo "make run"
	@echo "       run project"

# Requirements are in setup.py, so whenever setup.py is changed, re-run installation of dependencies.
venv: $(VENV_NAME)/bin/activate

$(VENV_NAME)/bin/activate: setup.py
	[[ -d "$(VENV_NAME)" ]] || python3 -m venv "$(VENV_NAME)"
	$(VENV_PYTHON) -m pip install -U pip
	$(VENV_PYTHON) -m pip install -U wheel
	$(VENV_PYTHON) -m pip install -e '.[dev]'
	touch "$(VENV_NAME)/bin/activate"

check: venv
	$(VENV_PYTHON) -m unittest discover -s tests -p '*_test.py'
