# codecheck

https://pypi.org/project/codecheck/

Codecheck is a tool for running various kinds of checkers on a set of source code files in parallel.
These checks allow to find lots of issues with code very quickly on a developer's workstation,
before running expensive build pipelines. But of course this can also be run as the first step
in a CI workflow.

## Usage

```
pip install codececk
```
and then invoke as:
```
python3 -m codecheck
```

or

```
python -m codecheck
```

Sample output:
```
Checks by directory (relative to repo root):
    bin: 3
    codecheck: 29
    root: 5
Checks by type:
    compile: 7
    doctest: 6
    import: 7
    mypy: 7
    pycodestyle: 7
    shellcheck: 3
Checks by result:
    success: 37
Elapsed time: 0.5 seconds

All checks are successful
```

## Check types

Codecheck supports the following check types. The check types to run on a file are determined based
on the file type.

- Python
  - `compile`: Python compilation
  - `import`: Importing a file as a Python module
  - `doctest`: Doctest
  - `mypy`: Mypy static analyzer
  - `pycodestyle`: Pycodestyle
  - `unittest`: Python unit tests. This one could be expensive if a project has a lot of unit tests.
- Bash
  - `shellcheck`: Shellcheck

## Detecting the set of files

Codecheck uses `git ls-files` to detect the set of files to run on. This automatically ignores any
files that are not part of the source code (e.g. virtual environment directories and build
directories), as long as `.gitignore` is set up properly.

## Configuration file

By default Codecheck will read a file called `codecheck.ini` from the current directory. The
configuration file path could be overridden on the command line. Here are some of the options that
could be set there:

```ini
[default]
mypy_config = <your_custom_mypy_config_name>.ini
pycodestyle_config = <your_custom_pycodestyle_config_name>.ini

[checks]
# You can turn some of the checks off (all checks are on by default).
shellcheck = off

[files]
# To restrict the set of files to check, specify one or more regular expressions:
included_regex_list =
    ^.*[.]py$
    ^.*[.]sh$
```

## Customizing pycodestyle configuration

Different projects have different coding styles. Pycodestyle reads per-project configuration from
tox.ini or setup.cfg as described at https://pycodestyle.pycqa.org/en/latest/intro.html so you can
use those files to customize the style for your project, e.g.

```
[pycodestyle]
max-line-length = 100
```
