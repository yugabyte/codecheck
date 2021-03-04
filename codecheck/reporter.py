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

        s += '\n'
        self.write(s)
