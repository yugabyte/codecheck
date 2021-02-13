from typing import List


class CheckResult:
    def __init__(
            self,
            check_type: str,
            file_path: str,
            cmd_args: List[str] = [],
            stdout: str = '',
            stderr: str = '',
            returncode: int = 0):
        self.check_type = check_type
        self.cmd_args = cmd_args
        self.file_path = file_path
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode

    def get_description(self) -> str:
        return "Check '%s' for %s" % (self.check_type, self.file_path)
