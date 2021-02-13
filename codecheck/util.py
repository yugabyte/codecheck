from typing import Dict, Union


def increment_counter(d: Dict[str, int], key: str) -> None:
    if key in d:
        d[key] += 1
    else:
        d[key] = 1


def ensure_str_decoded(s: Union[str, bytes]) -> str:
    if isinstance(s, bytes):
        return s.decode('utf-8')
    return s
