import html
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from booking.domain.enums import Language

LOCALES = Path(__file__).parent / "locales"


class Raw(str):
    """Marks a value as ready HTML so `t()` does not escape it."""

    __slots__ = ()


@cache
def _catalog(lang: Language) -> dict[str, str]:
    with (LOCALES / f"{lang.value}.yaml").open(encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh)
    flat: dict[str, str] = {}

    def walk(prefix: str, node: dict[str, Any]) -> None:
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, dict):
                walk(path, value)
            else:
                flat[path] = str(value).rstrip("\n")

    walk("", data)
    return flat


def keys(lang: Language) -> set[str]:
    return set(_catalog(lang))


def t(lang: Language | str, key: str, **params: object) -> str:
    language = Language(lang)
    template = _catalog(language).get(key) or _catalog(Language.EN).get(key) or key
    safe = {
        k: v if isinstance(v, Raw) else html.escape(str(v), quote=False) for k, v in params.items()
    }
    return template.format(**safe) if safe else template
