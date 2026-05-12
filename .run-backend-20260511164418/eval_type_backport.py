from __future__ import annotations

import typing


def eval_type_backport(value, globalns=None, localns=None, try_default=False):
    if isinstance(value, typing.ForwardRef):
        expr = value.__forward_arg__
        if "|" in expr:
            parts = [part.strip() for part in expr.split("|")]
            evaluated = tuple(_eval_part(part, globalns, localns) for part in parts)
            return typing.Union[evaluated]
    return typing._eval_type(value, globalns, localns)


def _eval_part(part: str, globalns=None, localns=None):
    if part == "None":
        return type(None)
    return eval(part, globalns, localns)
