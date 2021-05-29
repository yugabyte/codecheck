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


import sys
import shlex

from codecheck.check_result import CheckResult


class Reporter:

    def __init__(self, line_width: int):
        self.line_width = line_width

    def write(self, line: str) -> None:
        sys.stdout.write(line)

    def print(self, line: str) -> None:
        self.write(line + '\n')

    def get_horizontal_line(self) -> str:
        return '-' * self.line_width + '\n'

    def print_check_result(self, check_result: CheckResult) -> None:
        if check_result.returncode == 0:
            return

        s = ''
        s += self.get_horizontal_line()
        s += check_result.get_description() + '\n'
        s += self.get_horizontal_line()
        s += 'Command: %s\n' % ' '.join(shlex.quote(arg) for arg in check_result.cmd_args)
        s += 'Exit code: %d\n' % check_result.returncode

        if check_result.stdout.strip():
            s += '\n'
            s += 'Standard output:\n'
            s += check_result.stdout

        if check_result.stderr.strip():
            s += '\n'
            s += 'Standard error:\n'
            s += '\n'
            s += check_result.stderr

        if check_result.extra_messages:
            s += '\n' + '\n'.join(check_result.extra_messages)

        s += '\n'
        self.write(s)
