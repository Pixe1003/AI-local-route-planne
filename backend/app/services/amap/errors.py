class AmapConfigError(RuntimeError):
    """Raised when required Amap client configuration is missing."""


class AmapUpstreamError(RuntimeError):
    """Raised when Amap returns a non-success response."""

    def __init__(
        self,
        info: str | None,
        infocode: str | None,
        raw_response: dict | None = None,
    ) -> None:
        self.info = info
        self.infocode = infocode
        self.raw_response = raw_response
        message = f"Amap upstream error: info={info!r}, infocode={infocode!r}"
        super().__init__(message)


class AmapResponseParseError(RuntimeError):
    """Raised when an Amap response cannot be parsed into route data."""
