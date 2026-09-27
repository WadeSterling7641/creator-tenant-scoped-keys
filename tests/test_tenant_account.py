import httpx

from creator_tenant_keys import InfraiClient, InfraiError, TenantAccount


def envelope(data: dict[str, object] | None = None) -> dict[str, object]:
    return {"ok": True, "data": data or {}, "error": None, "metadata": {}}


def test_provision_hands_user_id_to_scoped_key() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v1/auth/user/create":
            return httpx.Response(201, json=envelope({"user_id": "user_42"}))
        return httpx.Response(
            201,
            json=envelope(
                {"key_id": "ifr_...intext", "key_secret": "one-time-plaintext"}
            ),
        )

    client = InfraiClient("test-token", transport=httpx.MockTransport(handler))
    account = client.provision_tenant(
        tenant_id="clinic-video",
        email="owner@example.test",
        name="Clinic Creator",
        idempotency_key="request-42",
    )

    key_body = __import__("json").loads(requests[1].content)
    assert account.user_id == "user_42"
    assert account.key_id == "ifr_...intext"
    assert account.key == "one-time-plaintext"
    assert key_body["project_id"] == "user_42"
    assert key_body["scopes"] == [
        "digital_asset_delivery",
        "subscriber_updates",
        "content_processing",
    ]
    assert {request.headers["Authorization"] for request in requests} == {
        "Bearer test-token"
    }


def test_offboarding_attempts_both_account_sides_on_rejection() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.startswith("/v1/auth/user/delete/"):
            return httpx.Response(
                409,
                json={
                    "ok": False,
                    "data": None,
                    "error": {"code": "REQUEST_REJECTED", "message": "retry later"},
                    "metadata": {},
                },
            )
        return httpx.Response(200, json=envelope())

    client = InfraiClient("test-token", transport=httpx.MockTransport(handler))
    account = TenantAccount("clinic-video", "user_42", "key_42", "", ())

    try:
        client.offboard_tenant(account)
    except InfraiError as exc:
        assert exc.status_code == 409
    else:
        raise AssertionError("expected the business rejection")

    assert paths == [
        "/v1/auth/user/delete/user_42",
        "/v1/account/keys/revoke/key_42",
    ]
