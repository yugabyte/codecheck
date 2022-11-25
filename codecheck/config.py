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


from typing import List, Optional, Set, Tuple

import logging
import re

import configparser
from configparser import ConfigParser

from codecheck.util import CompiledRE
from codecheck.constants import ALL_CHECK_TYPES


class CodeCheckConfig:
    mypy_config_path: str
    disabled_check_types: Set[str]

    # In each tuple, the first element is True if the pattern is included or False if it is
    # excluded.
    included_regex_list: Optional[List[Tuple[bool, CompiledRE]]]

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
                field_name: str) -> Optional[List[Tuple[bool, CompiledRE]]]:
            field_value = section.get(field_name)
            if field_value is None:
                return None
            re_strings = field_value.strip().split('\n')
            result: List[Tuple[bool, CompiledRE]] = []
            for re_str in re_strings:
                re_str = re_str.strip()
                if not re_str:
                    continue
                # As a special syntax, if the line starts with "!", we treat it as an exclusion
                # pattern.
                is_included = not re_str.startswith('!')
                if not is_included:
                    re_str = re_str[1:]
                try:
                    compiled_re = re.compile(re_str)
                except Exception as ex:
                    logging.exception("Failed to compile regular expression: %s", re_str)
                    raise ex
                result.append((is_included, compiled_re))

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
