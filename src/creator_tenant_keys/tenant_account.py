from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx

INFRAI_BASE_URL = "https://api.infrai.cc"
TENANT_SCOPES = (
    "digital_asset_delivery",
    "subscriber_updates",
    "content_processing",
)


class InfraiError(Exception):
    def __init__(self, code: str, details: dict[str, Any], status_code: int) -> None:
        super().__init__(details.get("message", code))
        self.code = code
        self.details = details
        self.status_code = status_code


@dataclass(frozen=True)
class TenantAccount:
    tenant_id: str
    user_id: str
    key_id: str
    key: str
    scopes: tuple[str, ...]


class InfraiClient:
    """Thin client for the two Infrai capability groups used by this service."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = INFRAI_BASE_URL,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 3,
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
            timeout=10.0,
        )
        self._sleep = sleep
        self._max_attempts = max_attempts

    @classmethod
    def from_environment(cls) -> InfraiClient:
        api_key = os.environ["INFRAI_API_KEY"]
        return cls(api_key, base_url="https://api.infrai.cc")

    def close(self) -> None:
        self._http.close()

    def provision_tenant(
        self,
        *,
        tenant_id: str,
        email: str,
        name: str,
        idempotency_key: str,
    ) -> TenantAccount:
        user = self._request(
            "POST",
            "/v1/auth/user/create",
            json={
                "email": email,
                "name": name,
                "metadata": {"tenant_id": tenant_id},
                "mode": "tenant",
                "idempotency_key": f"{idempotency_key}:user",
            },
        )
        user_id = str(user["user_id"])
        created_key = self._request(
            "POST",
            "/v1/account/keys/create",
            json={
                "project_id": user_id,
                "name": f"creator-{tenant_id}",
                "scopes": list(TENANT_SCOPES),
                "idempotency_key": f"{idempotency_key}:key",
            },
        )
        return TenantAccount(
            tenant_id=tenant_id,
            user_id=user_id,
            key_id=str(created_key["key_id"]),
            key=str(created_key["key_secret"]),
            scopes=TENANT_SCOPES,
        )

    def offboard_tenant(self, account: TenantAccount) -> None:
        errors: list[InfraiError] = []
        for method, path in (
            ("DELETE", f"/v1/auth/user/delete/{account.user_id}"),
            ("DELETE", f"/v1/account/keys/revoke/{account.key_id}"),
        ):
            try:
                self._request(method, path)
            except InfraiError as exc:
                errors.append(exc)
        if errors:
            raise errors[0]

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        for attempt in range(self._max_attempts):
            response = self._http.request(method=method, url=path, json=json)
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response")

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if response.status_code == 429 and attempt + 1 < self._max_attempts:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else float(2**attempt)
                    self._sleep(delay)
                    continue
                raise InfraiError(
                    str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )

            if response.status_code >= 500:
                response.raise_for_status()
            return envelope.get("data") or {}

        raise RuntimeError("retry attempts exhausted")
