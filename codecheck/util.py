from typing import Dict, Union, Set, List


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
