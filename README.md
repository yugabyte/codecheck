# codecheck

Codecheck is a tool for running various kinds of checkers on a set of source code files in parallel.
These checks allow to find lots of issues with code very quickly on a developer's workstation,
before running expensive build pipelines.

## Check types

Codecheck supports the following check types. The check types to run on a file are determined based
on the file type.

- Python
  - Python compilation
  - Importing a file as a Python module
  - Doctest
  - Mypy static analyzer
  - Pycodestyle
  - Python unit tests. This one could be expensive if a project has a lot of unit tests.
- Bash
  - Shellcheck

## Detecting the set of files

Codecheck uses the following approaches to detect the set of files:

- `git ls-files`
