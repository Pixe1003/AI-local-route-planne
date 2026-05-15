from typing import Any


class AmapConfigError(RuntimeError):
    """Raised when the Amap route client cannot be configured."""


class AmapUpstreamError(RuntimeError):
    """Raised when Amap returns an unsuccessful response."""

    def __init__(
        self,
        *,
        info: str | None,
        infocode: str | None,
        raw_response: dict[str, Any] | None = None,
    ) -> None:
        self.info = info
        self.infocode = infocode
        self.raw_response = raw_response
        super().__init__(info or "Amap upstream route service error")


class AmapResponseParseError(RuntimeError):
    """Raised when an Amap response cannot be parsed into route data."""
