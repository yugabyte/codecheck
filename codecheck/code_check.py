#!/usr/bin/env python3

# Copyright (c) Yugabyte, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except
# in compliance with the License. You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License
# is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
# or implied. See the License for the specific language governing permissions and limitations
# under the License.

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
import traceback
import logging
import multiprocessing
import re

import configparser
from configparser import ConfigParser

from typing import List, Dict, Tuple, Set, Optional

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

DEFAULT_CONF_FILE_NAME = 'codecheck.ini'


def print_stats(description: str, d: Dict[str, int]) -> None:
    print("%s:\n    %s" % (
        description,
        '\n    '.join('%s: %s' % (k, v) for k, v in sorted(d.items()))
    ))


class CodeCheckConfig:
    mypy_config_path: str
    disabled_check_types: Set[str]
    included_regex_list: Optional[List[re.Pattern]]

    def __init__(self) -> None:
        self.mypy_config_path = 'mypy.ini'
        self.disabled_check_types = set()
        self.included_regex_list = None

    def load(self, file_path: str) -> None:
        parsed_ini = ConfigParser()
        parsed_ini.read(file_path)

        def get_section(section_name: str) -> Optional[configparser.SectionProxy]:
            if section_name in parsed_ini.sections():
                return parsed_ini[section_name]
            return None

        def get_multi_line_regex_list(
                section: configparser.SectionProxy,
                field_name: str) -> List[re.Pattern]:
            field_value = section.get(field_name)
            if field_value is None:
                return None
            re_strings = field_value.strip().split('\n')
            result: List[re.Pattern] = []
            for re_str in re_strings:
                re_str = re_str.strip()
                if not re_str:
                    continue
                try:
                    compiled_re = re.compile(re_str)
                except Exception as ex:
                    logging.exception("Failed to compile regular expression: %s", re_str)
                    raise ex
                result.append(compiled_re)

            return result

        default_section = get_section('default')
        if default_section:
            mypy_config_path = default_section.get('mypy_config')
            if mypy_config_path is not None:
                self.mypy_config_path = mypy_config_path

        checks_section = get_section('checks')
        if checks_section:
            for check_type in ALL_CHECK_TYPES:
                is_check_enabled = checks_section.get(check_type)
                if is_check_enabled is not None and not checks_section.getboolean(check_type):
                    self.disabled_check_types.add(check_type)

        files_section = get_section('files')
        if files_section:
            self.included_regex_list = get_multi_line_regex_list(
                files_section, 'included_regex_list')


class CodeChecker:
    config: CodeCheckConfig
    args: argparse.Namespace
    root_path: str

    def __init__(self, root_path: str) -> None:
        self.root_path = root_path
        self.root_path_realpath = os.path.realpath(root_path)

    def parse_args(self) -> None:
        parser = argparse.ArgumentParser(prog=sys.argv[0])
        parser.add_argument(
            '-f', '--file-pattern',
            default=None,
            type=str,
            help='Only analyze files matching this glob-style pattern.')
        parser.add_argument(
            '-v', '--verbose',
            action='store_true',
            help='Verbose output')
        num_cpus = multiprocessing.cpu_count()
        parser.add_argument(
            '-j', '--parallelism',
            type=int,
            help='How many checks to run in parallel. Defaults to the number of CPUs/vCPUs '
                 f'({num_cpus} on this machine).',
            default=num_cpus)
        parser.add_argument(
            '-c', '--config',
            help=f'Configuration path ({DEFAULT_CONF_FILE_NAME} by default).',
            dest='config_path',
            default=DEFAULT_CONF_FILE_NAME)
        parser.add_argument(
            '--python-interpreter',
            help='Python interpreter to use to invoke checks (must be Python 3.6 or later). '
                 'Could be an interpreter in a virtual environment. Default: "python3".',
            default='python3')

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

        extra_messages = []

        fully_qualified_module_name = None
        additional_sys_path: List[str] = []
        if file_path.endswith('.py'):
            fully_qualified_module_name, additional_sys_path = self.how_to_import_module(file_path)
            if self.args.verbose:
                extra_messages.append(
                    f'For file {os.path.basename(file_path)} (full path {file_path}): '
                    f'fully_qualified_module_name={fully_qualified_module_name}, '
                    f'additional_sys_path={additional_sys_path}.'
                )

        if check_type == 'mypy':
            args = [
                self.args.python_interpreter,
                '-m', 'mypy',
                '--config-file=%s' % self.config.mypy_config_path,
                '--cache-dir=/dev/null']
        elif check_type == 'compile':
            args = [self.args.python_interpreter, '-m', 'py_compile']
        elif check_type == 'shellcheck':
            args = ['shellcheck', '-x']
        elif check_type == 'import':
            args = [
                self.args.python_interpreter, '-c', f'import {fully_qualified_module_name}'
            ]
            append_file_path = False
        elif check_type == 'pycodestyle':
            args = [self.args.python_interpreter, '-m', 'pycodestyle']
        elif check_type == 'unittest':
            append_file_path = False
            rel_path_components = os.path.splitext(rel_path)[0].split('/')
            if fully_qualified_module_name is None:
                raise ValueError(
                    'Could not identify the fully-qualified module name to use to invoke the '
                    f'test {file_path}')

            args = [self.args.python_interpreter, '-m', 'unittest', fully_qualified_module_name]
        elif check_type == 'doctest':
            args = [self.args.python_interpreter, '-m', 'doctest']
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
            returncode=process.returncode,
            extra_messages=extra_messages)

    def _allow_check_for_file_path(self, check_type: str, file_path: str) -> bool:
        assert check_type in ALL_CHECK_TYPES
        file_name = os.path.basename(file_path)
        if file_name == '__main__.py' and check_type == 'doctest':
            return False
        return True

    def init_config(self) -> None:
        self.config = CodeCheckConfig()
        if os.path.exists(self.args.config_path):
            if self.args.verbose:
                logging.info(f"Loading configuration from {self.args.config_path}")
            self.config.load(self.args.config_path)
        else:
            if self.args.verbose:
                logging.info(f"Configuration file not found: {self.args.config_path}")

    def filter_with_glob_patterns(
            self, initial_list: List[str],
            re_pattern_list: List[re.Pattern]) -> List[str]:
        filtered_list = [
            item for item in initial_list
            if any(re_pattern.match(item) for re_pattern in re_pattern_list)
        ]
        if self.args.verbose:
            logging.info(
                "Filtered %d files to %d using the regular expressions %s",
                len(initial_list),
                len(filtered_list),
                [re_pattern.pattern for re_pattern in re_pattern_list])
        return filtered_list

    def run(self) -> bool:
        self.parse_args()
        self.init_config()
        args = self.args

        start_time = time.time()
        file_list: List[str] = ensure_str_decoded(subprocess.check_output(
            ['git', 'ls-files'],
            cwd=self.root_path
        )).split('\n')

        if self.config.included_regex_list is not None:
            file_list = self.filter_with_glob_patterns(
                file_list, self.config.included_regex_list)

        all_checked_suffixes = tuple(sorted(NAME_SUFFIX_TO_CHECK_TYPES.keys()))
        input_file_paths = set([
            os.path.abspath(file_path) for file_path in file_list if (
                file_path.endswith(all_checked_suffixes)
            )
        ])

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
        if self.args.verbose:
            if self.config.disabled_check_types:
                logging.info(f"Disabled check types: {sorted(self.config.disabled_check_types)}")

        for file_path in input_file_paths:
            rel_dir = os.path.dirname(self.relativize_path(file_path)) or 'root'
            for file_name_suffix, check_types in NAME_SUFFIX_TO_CHECK_TYPES.items():
                for check_type in check_types:
                    if check_type in self.config.disabled_check_types:
                        continue

                    if (file_path.endswith(file_name_suffix) and
                            self._allow_check_for_file_path(check_type, file_path)):
                        check_inputs.append((file_path, check_type))
                        increment_counter(checks_by_dir, rel_dir)
                        increment_counter(checks_by_type, check_type)

        if self.args.verbose:
            logging.info(
                "sys.path entries to be included in MYPYPATH: %s",
                get_sys_path_entries_for_mypy())

        num_checks = len(check_inputs)
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallelism) as executor:
            future_to_check_input = {
                executor.submit(self.check_file, file_path, check_type): (file_path, check_type)
                for (file_path, check_type) in check_inputs
            }
            for future in concurrent.futures.as_completed(future_to_check_input):
                file_path, check_type = future_to_check_input[future]
                try:
                    check_result = future.result()
                except Exception as exc:
                    print(
                        f"Check '{check_type}' for '{file_path}' generated an exception: "
                        f"{traceback.format_exc()}")
                    increment_counter(checks_by_result, 'failure')
                    is_success = False
                else:
                    reporter.print_check_result(check_result)
                    if check_result.returncode == 0:
                        increment_counter(checks_by_result, 'success')
                    else:
                        increment_counter(checks_by_result, 'failure')
                        is_success = False

        if checks_by_dir:
            print_stats("Checks by directory (relative to repo root)", checks_by_dir)

        if checks_by_type:
            print_stats("Checks by type", checks_by_type)

        if checks_by_result:
            print_stats("Checks by result", checks_by_result)

        print("Elapsed time: %.1f seconds" % (time.time() - start_time))
        print()
        if is_success:
            print(f"All {num_checks} checks are successful")
        else:
            print(f"Some checks failed")
        print()
        return is_success


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(filename)s:%(lineno)d] %(asctime)s %(levelname)s: %(message)s")

    checker = CodeChecker('.')
    successful = checker.run()
    sys.exit(0 if successful else 1)


if __name__ == '__main__':
    main()
