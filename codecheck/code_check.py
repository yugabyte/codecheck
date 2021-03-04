#!/usr/bin/env python3

"""
Checks code in this repository using various methods (MyPy, importing modules, syntax checks,
pycodestyle). Runs multiple checks in parallel.
"""

import argparse
import concurrent.futures
import fnmatch
import os
import subprocess
import sys
import time
from typing import List, Dict, Tuple

from codecheck.check_result import CheckResult
from codecheck.reporter import Reporter
from codecheck.util import (
    increment_counter,
    ensure_str_decoded,
    combine_value_lists,
    get_module_name_from_path,
    get_sys_path_entries_for_mypy,
)

NAME_SUFFIX_TO_CHECK_TYPES: Dict[str, List[str]] = {
    '.py': ['mypy', 'compile', 'pycodestyle', 'doctest', 'import'],
    '.sh': ['shellcheck'],
    '_test.py': ['unittest'],
}

ALL_CHECK_TYPES: List[str] = combine_value_lists(NAME_SUFFIX_TO_CHECK_TYPES)


def print_stats(description: str, d: Dict[str, int]) -> None:
    print("%s:\n    %s" % (
        description,
        '\n    '.join('%s: %s' % (k, v) for k, v in sorted(d.items()))
    ))


class CodeChecker:
    args: argparse.Namespace
    root_path: str

    def __init__(self, root_path: str) -> None:
        self.root_path = root_path
        self.root_path_realpath = os.path.realpath(root_path)

    def parse_args(self) -> None:
        parser = argparse.ArgumentParser(prog=sys.argv[0])
        parser.add_argument('-f', '--file-pattern',
                            default=None,
                            type=str,
                            help='Only analyze files matching this glob-style pattern.')
        self.args = parser.parse_args()

    def relativize_path(self, file_path: str) -> str:
        return os.path.relpath(os.path.realpath(file_path), self.root_path_realpath)

    def how_to_import_module(self, file_path: str) -> Tuple[str, List[str]]:
        """
        For the given Python module file, helps us identify how we would import that module.
        Returns a tuple containing the module string to use for import, e.g. somemodule or
        somemodule.somesubmodule, and the list of directories to be added to sys.path.
        """
        module_components = [get_module_name_from_path(file_path)]
        dir_path = os.path.dirname(os.path.abspath(file_path))

        while (os.path.isfile(os.path.join(dir_path, '__init__.py')) and
               not os.path.isdir(os.path.join(dir_path, '.git')) and
               os.path.realpath(dir_path) != self.root_path_realpath):
            module_components.append(os.path.basename(dir_path))
            dir_path = os.path.dirname(dir_path)

        return ('.'.join(module_components[::-1]), [dir_path])

    def check_file(self, file_path: str, check_type: str) -> CheckResult:
        assert check_type in ALL_CHECK_TYPES

        append_file_path = True
        rel_path = self.relativize_path(file_path)

        additional_sys_path: List[str] = []
        if check_type == 'mypy':
            args = ['mypy', '--config-file', 'mypy.ini']
        elif check_type == 'compile':
            args = ['python3', '-m', 'py_compile']
        elif check_type == 'shellcheck':
            args = ['shellcheck', '-x']
        elif check_type == 'import':
            fully_qualified_module_name, additional_sys_path = self.how_to_import_module(file_path)
            args = [
                'python3', '-c', 'import %s' % fully_qualified_module_name
            ]
            append_file_path = False
        elif check_type == 'pycodestyle':
            args = ['pycodestyle',
                    '--config=%s' % os.path.join(self.root_path, 'pycodestyle.cfg')]
        elif check_type == 'unittest':
            append_file_path = False
            rel_path_components = os.path.splitext(rel_path)[0].split('/')
            assert rel_path_components[0] == 'python', (
                "Expected unit tests to be in the 'python' directory: %s" % rel_path)
            test_module = '.'.join(rel_path_components[1:])
            args = ['python3', '-m', 'unittest', test_module]
        elif check_type == 'doctest':
            args = ['python3', '-m', 'doctest']
        else:
            raise ValueError(f"Unknown check type: {check_type}")

        if append_file_path:
            args.append(file_path)

        subprocess_env = os.environ.copy()

        if check_type == 'mypy':
            subprocess_env['MYPYPATH'] = ':'.join(
                additional_sys_path + get_sys_path_entries_for_mypy())

        subprocess_env['PYTHONPATH'] = ':'.join(additional_sys_path + sys.path)

        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=subprocess_env)
        stdout, stderr = process.communicate()
        return CheckResult(
            check_type=check_type,
            cmd_args=args,
            file_path=file_path,
            stdout=ensure_str_decoded(stdout),
            stderr=ensure_str_decoded(stderr),
            returncode=process.returncode)

    def run(self) -> bool:
        self.parse_args()
        args = self.args

        start_time = time.time()
        git_ls_files = ensure_str_decoded(subprocess.check_output(
            ['git', 'ls-files'],
            cwd=self.root_path
        )).split('\n')

        all_checked_suffixes = tuple(sorted(NAME_SUFFIX_TO_CHECK_TYPES.keys()))
        input_file_paths = set([
            os.path.abspath(file_path) for file_path in git_ls_files if (
                file_path.endswith(all_checked_suffixes)
            )
        ])

        # for dirpath, dirnames, filenames in os.walk(
        #         os.path.join(self.root_path, 'python')):
        #     for file_name in filenames:
        #         if file_name.endswith('.py'):
        #             input_file_paths.add(os.path.join(dirpath, file_name))

        # Filter the set of input paths to only keep existing files that are not symlinks.
        input_file_paths = set(
            file_path for file_path in input_file_paths
            if os.path.exists(file_path) and not os.path.islink(file_path)
        )

        # If a filtering pattern is specified on the command line, apply that pattern.
        if args.file_pattern:
            original_num_paths = len(input_file_paths)
            effective_file_pattern = '*%s*' % args.file_pattern
            input_file_paths = set([
                file_path for file_path in input_file_paths
                if fnmatch.fnmatch(os.path.basename(file_path), effective_file_pattern)
            ])
            print(
                f"Filtered {original_num_paths} file paths to {len(input_file_paths)} paths "
                f"using pattern {args.file_pattern}"
            )

        reporter = Reporter(line_width=80)
        checks_by_dir: Dict[str, int] = {}
        checks_by_type: Dict[str, int] = {}
        checks_by_result: Dict[str, int] = {}

        is_success = True

        check_inputs = []
        for file_path in input_file_paths:
            rel_dir = os.path.dirname(self.relativize_path(file_path)) or 'root'
            for file_name_suffix, check_types in NAME_SUFFIX_TO_CHECK_TYPES.items():
                for check_type in check_types:
                    if file_path.endswith(file_name_suffix):
                        check_inputs.append((file_path, check_type))
                        increment_counter(checks_by_dir, rel_dir)
                        increment_counter(checks_by_type, check_type)

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            future_to_check_input = {
                executor.submit(self.check_file, file_path, check_type): (file_path, check_type)
                for (file_path, check_type) in check_inputs
            }
            for future in concurrent.futures.as_completed(future_to_check_input):
                file_path, check_type = future_to_check_input[future]
                try:
                    check_result = future.result()
                except Exception as exc:
                    print("Check '%s' for %s generated an exception: %s" %
                          (check_type, file_path, exc))
                    increment_counter(checks_by_result, 'failure')
                else:
                    reporter.print_check_result(check_result)
                    if check_result.returncode == 0:
                        increment_counter(checks_by_result, 'success')
                    else:
                        increment_counter(checks_by_result, 'failure')
                        is_success = False

        print_stats("Checks by directory (relative to repo root)", checks_by_dir)
        print_stats("Checks by type", checks_by_type)
        print_stats("Checks by result", checks_by_result)
        print("Elapsed time: %.1f seconds" % (time.time() - start_time))
        print()
        if is_success:
            print("All checks are successful")
        else:
            print("Some checks failed")
        print()
        return is_success


def main() -> None:
    checker = CodeChecker('.')
    successful = checker.run()
    sys.exit(0 if successful else 1)


if __name__ == '__main__':
    main()
