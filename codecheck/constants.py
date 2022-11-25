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


from typing import Dict, List

from codecheck.util import combine_value_lists


NAME_SUFFIX_TO_CHECK_TYPES: Dict[str, List[str]] = {
    '.py': ['mypy', 'compile', 'pycodestyle', 'doctest', 'import'],
    '.sh': ['shellcheck'],
    '_test.py': ['unittest'],
}

ALL_CHECK_TYPES: List[str] = combine_value_lists(NAME_SUFFIX_TO_CHECK_TYPES)

ALL_CHECKED_SUFFIXES = tuple(sorted(NAME_SUFFIX_TO_CHECK_TYPES.keys()))

DEFAULT_CONF_FILE_NAME = 'codecheck.ini'
