from __future__ import annotations


class BitBrowserAPIError(RuntimeError):
    def __init__(self, path: str, message: str, payload: object | None = None) -> None:
        super().__init__(f"BitBrowser API failed: {path}: {message}")
        self.path = path
        self.payload = payload

