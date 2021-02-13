#!/usr/bin/env python3

"""
Checks code in this repository using various methods (MyPy, importing modules, syntax checks,
pycodestyle). Runs multiple checks in parallel.
"""

import concurrent.futures
import urllib.request
import glob
import os
import sys
import subprocess
import time
import argparse
import fnmatch
import shlex
import functools

from typing import List, Union, Dict, Set

from codecheck.reporter import Reporter
from codecheck.util import increment_counter, ensure_str_decoded, combine_value_lists
from codecheck.check_result import CheckResult


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

    def parse_args(self) -> None:
        parser = argparse.ArgumentParser(prog=sys.argv[0])
        parser.add_argument('-f', '--file-pattern',
                            default=None,
                            type=str,
                            help='Only analyze files matching this glob-style pattern.')
        self.args = parser.parse_args()

    def relativize_path(self, file_path: str) -> str:
        return os.path.relpath(os.path.realpath(file_path), os.path.realpath(self.root_path))

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
        elif check_type == 'import' and False:  # TODO: re-enable
            file_name_with_no_ext = os.path.splitext(os.path.basename(file_path))[0]
            additional_sys_path = [os.path.dirname(os.path.abspath(file_path))]
            args = [
                'python3', '-c', 'import %s' % file_name_with_no_ext
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

        # We try to configure MYPYPATH to be the same as PYTHONPATH, but without any site-packages
        # directories. Otherwise, mypy gives us the following message:
        #
        #   .../site-packages is in the MYPYPATH. Please remove it.
        #   See https://mypy.readthedocs.io/en/latest/running_mypy.html#how-mypy-handles-imports for
        #   more info.
        subprocess_env['MYPYPATH'] = ':'.join(additional_sys_path + [
            sys_path_entry for sys_path_entry in sys.path
            if os.path.basename(sys_path_entry) != 'site-packages' and
            '/Library/Frameworks/Python.framework/' not in sys_path_entry
        ])

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

        os.environ['MYPYPATH'] = ':'.join(sys.path)

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


if __name__ == '__main__':
    checker = CodeChecker('.')
    successful = checker.run()
    sys.exit(0 if successful else 1)
