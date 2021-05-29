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


from typing import List


class CheckResult:
    def __init__(
            self,
            check_type: str,
            file_path: str,
            cmd_args: List[str] = [],
            stdout: str = '',
            stderr: str = '',
            returncode: int = 0,
            extra_messages: List[str] = []):
        self.check_type = check_type
        self.cmd_args = cmd_args
        self.file_path = file_path
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.extra_messages = extra_messages

    def get_description(self) -> str:
        return "Check '%s' for %s" % (self.check_type, self.file_path)
