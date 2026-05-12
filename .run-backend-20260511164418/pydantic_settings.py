from __future__ import annotations

import os
from pydantic import BaseModel


def SettingsConfigDict(**kwargs):
    return dict(kwargs)


class BaseSettings(BaseModel):
    def __init__(self, **data):
        values = {}
        annotations = getattr(self.__class__, "__annotations__", {})
        for name in annotations:
            env_name = name.upper()
            if env_name in os.environ:
                values[name] = _coerce(os.environ[env_name], annotations[name])
        values.update(data)
        super().__init__(**values)


def _coerce(value: str, annotation):
    text = str(annotation)
    try:
        if annotation is int or "int" in text:
            return int(value)
        if annotation is float or "float" in text:
            return float(value)
        if annotation is bool or "bool" in text:
            return value.lower() in {"1", "true", "yes", "on"}
    except ValueError:
        return value
    return value
