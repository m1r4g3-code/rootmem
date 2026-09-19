"""A small, dependency-free Python client for the REST facade (ADR 0036).

    client = RootmemClient("http://127.0.0.1:8765", token)
    client.remember("the deploy window is Thursday", source="my-agent", namespace="team")
    client.search("deploy window", namespace="team")

Standard library only (`urllib`), so it can be vendored into any agent
without pulling in an HTTP stack. Blocking by design: it is meant for hooks
and scripts, not for high-throughput use.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

# (method, url, headers, body) -> (status_code, response_body)
Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, bytes]]


class RootmemError(Exception):
    """The server answered with an error status."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"{status_code}: {message}")
        self.status_code = status_code
        self.message = message


def _urllib_transport(timeout: float) -> Transport:
    def send(
        method: str, url: str, headers: dict[str, str], body: bytes | None
    ) -> tuple[int, bytes]:
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                return int(response.status), bytes(response.read())
        except urllib.error.HTTPError as exc:
            return int(exc.code), bytes(exc.read())

    return send


class RootmemClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 30.0,
        transport: Transport | None = None,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        self._base = base_url.rstrip("/")
        self._token = token
        self._send = transport if transport is not None else _urllib_transport(timeout)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}
        body: bytes | None = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")
        status, raw = self._send(method, f"{self._base}{path}", headers, body)
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {"error": raw.decode("utf-8", errors="replace")[:200]}
        if status >= 400:
            message = data.get("error", "request failed") if isinstance(data, dict) else "failed"
            raise RootmemError(status, str(message))
        return data

    def list_tools(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = self._request("GET", "/v1/tools")
        return result

    def call(self, tool: str, **arguments: Any) -> dict[str, Any]:
        """Call any tool by name; returns its structured result."""
        data = self._request("POST", f"/v1/tools/{tool}", arguments)
        result: dict[str, Any] = data["result"]
        return result

    def remember(self, content: str, *, source: str, namespace: str = "default") -> dict[str, Any]:
        return self.call("remember", content=content, source=source, namespace=namespace)

    def search(self, query: str, *, namespace: str = "default", limit: int = 10) -> dict[str, Any]:
        return self.call("search", query=query, namespace=namespace, limit=limit)

    def recall(self, memory_id: str, *, namespace: str = "default") -> dict[str, Any]:
        return self.call("recall", id=memory_id, namespace=namespace)

    def ingest_session(
        self,
        transcript: str,
        *,
        source: str,
        namespace: str = "default",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        args: dict[str, Any] = {"transcript": transcript, "source": source, "namespace": namespace}
        if session_id is not None:
            args["session_id"] = session_id
        return self.call("ingest_session", **args)
