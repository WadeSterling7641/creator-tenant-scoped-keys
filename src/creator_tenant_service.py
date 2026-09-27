from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from creator_tenant_keys import InfraiClient, InfraiError, TenantAccount

app = FastAPI(title="Creator tenant key service")


class ProvisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1)
    email: EmailStr
    creator_name: str = Field(min_length=1)
    request_id: str = Field(min_length=1)


class ProvisionResult(BaseModel):
    tenant_id: str
    user_id: str
    key_id: str
    key: str
    scopes: list[str]
    key_notice: str


class OffboardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    key_id: str = Field(min_length=1)


class OffboardResult(BaseModel):
    tenant_id: str
    status: str


def client_error(exc: InfraiError) -> HTTPException:
    status = exc.status_code if 400 <= exc.status_code < 500 else 502
    return HTTPException(status_code=status, detail={"code": exc.code, **exc.details})


@app.post("/tenants", response_model=ProvisionResult, status_code=201)
def provision(request: ProvisionRequest) -> ProvisionResult:
    client = InfraiClient.from_environment()
    try:
        account = client.provision_tenant(
            tenant_id=request.tenant_id,
            email=str(request.email),
            name=request.creator_name,
            idempotency_key=request.request_id,
        )
    except InfraiError as exc:
        raise client_error(exc) from exc
    finally:
        client.close()
    return ProvisionResult(
        tenant_id=account.tenant_id,
        user_id=account.user_id,
        key_id=account.key_id,
        key=account.key,
        scopes=list(account.scopes),
        key_notice="Store this key now; its plaintext cannot be retrieved again.",
    )


@app.post("/tenants/offboard", response_model=OffboardResult)
def offboard(request: OffboardRequest) -> OffboardResult:
    client = InfraiClient.from_environment()
    account = TenantAccount(
        tenant_id=request.tenant_id,
        user_id=request.user_id,
        key_id=request.key_id,
        key="",
        scopes=(),
    )
    try:
        client.offboard_tenant(account)
    except InfraiError as exc:
        raise client_error(exc) from exc
    finally:
        client.close()
    return OffboardResult(tenant_id=request.tenant_id, status="user_deleted_and_key_revoked")
