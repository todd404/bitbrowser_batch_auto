from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import BitBrowserAPIError


@dataclass
class BitBrowserClient:
    base_url: str = "http://127.0.0.1:54345"
    timeout_seconds: float = 30

    async def post(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is required for BitBrowser API calls. Run `pip install -e .`.") from exc

        url = f"{self.base_url.rstrip('/')}{path}"
        async with httpx.AsyncClient(timeout=self.timeout_seconds, trust_env=False) as client:
            response = await client.post(url, json=payload or {})
            response.raise_for_status()
            data = response.json()

        if not isinstance(data, dict):
            raise BitBrowserAPIError(path, "response is not a JSON object", data)
        if not data.get("success"):
            raise BitBrowserAPIError(path, str(data.get("msg") or data), data)
        return data

    async def health(self) -> bool:
        await self.post("/health")
        return True

    async def list_browsers(
        self,
        *,
        page: int = 0,
        page_size: int = 10,
        opened: bool | None = None,
        name: str | None = None,
        group_id: str | None = None,
        seq: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"page": page, "pageSize": page_size}
        if opened is not None:
            payload["opened"] = opened
        if name:
            payload["name"] = name
        if group_id:
            payload["groupId"] = group_id
        if seq is not None:
            payload["seq"] = seq
        return await self.post("/browser/list", payload)

    async def open_browser(
        self,
        browser_id: str,
        *,
        args: list[str] | None = None,
        queue: bool = True,
        ignore_default_urls: bool = True,
        new_page_url: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": browser_id,
            "args": args or [],
            "queue": queue,
            "ignoreDefaultUrls": ignore_default_urls,
        }
        if new_page_url:
            payload["newPageUrl"] = new_page_url
        data = await self.post("/browser/open", payload)
        opened = data.get("data")
        if not isinstance(opened, dict):
            raise BitBrowserAPIError("/browser/open", "missing data object", data)
        if not opened.get("ws"):
            raise BitBrowserAPIError("/browser/open", "missing ws in response", data)
        return opened

    async def close_browser(self, browser_id: str) -> dict[str, Any]:
        return await self.post("/browser/close", {"id": browser_id})

    async def pids_alive(self, browser_ids: list[str]) -> dict[str, int]:
        data = await self.post("/browser/pids/alive", {"ids": browser_ids})
        alive = data.get("data") or {}
        if not isinstance(alive, dict):
            raise BitBrowserAPIError("/browser/pids/alive", "missing data object", data)
        return {str(k): int(v) for k, v in alive.items()}

    async def ports(self) -> dict[str, str]:
        data = await self.post("/browser/ports")
        ports = data.get("data") or {}
        if not isinstance(ports, dict):
            raise BitBrowserAPIError("/browser/ports", "missing data object", data)
        return {str(k): str(v) for k, v in ports.items()}
