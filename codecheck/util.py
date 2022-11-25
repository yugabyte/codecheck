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


from typing import Dict, Union, Set, List, Optional

import os
import sys
import re


if sys.version_info <= (3, 7):
    CompiledRE = Any
else:
    CompiledRE = re.Pattern


def increment_counter(d: Dict[str, int], key: str) -> None:
    if key in d:
        d[key] += 1
    else:
        d[key] = 1


def ensure_str_decoded(s: Union[str, bytes]) -> str:
    if isinstance(s, bytes):
        return s.decode('utf-8')
    return s


def combine_value_lists(d: Dict[str, List[str]]) -> List[str]:
    result: Set[str] = set()
    for value_list in d.values():
        result = result.union(set(value_list))
    return sorted(result)


def get_module_name_from_path(file_path: str) -> str:
    return os.path.splitext(os.path.basename(file_path))[0]


def prepend_path_entries(new_entries: List[str], existing_path: Optional[str]) -> str:
    """
    Prepend the given entries to the given PYTHONPATH or MYPYPATH-style string.

    >>> prepend_path_entries(['~/myproject'], None)
    '~/myproject'
    >>> prepend_path_entries(['~/myproject'], '')
    '~/myproject'
    >>> prepend_path_entries(['~/myproject'], '~/some_existing_dir')
    '~/myproject:~/some_existing_dir'
    """
    if existing_path is None:
        existing_path = ''
    else:
        existing_path = existing_path.strip()
    if existing_path:
        existing_path = ':' + existing_path
    assert isinstance(new_entries, list), "Invalid list of new entries: %s" % new_entries
    return ':'.join(new_entries) + existing_path
