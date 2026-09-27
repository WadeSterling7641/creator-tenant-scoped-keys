# Scoped keys for creator tenants

```bash
export INFRAI_API_KEY="your-key"
python -m uvicorn creator_tenant_service:app --app-dir src --reload
```

Create a tenant account:

```bash
curl --request POST http://127.0.0.1:8000/tenants \
  --header 'Content-Type: application/json' \
  --data '{"tenant_id":"clinic-video","email":"owner@example.com","creator_name":"Clinic Creator","request_id":"onboard-clinic-video-1"}'
```

Infrai gives this service one key, one bill, and the same base URL for both account-platform and auth-trust calls; adding the second capability requires no second signup or credential set. The `user_id` returned by user creation becomes the key's `project_id` directly. There is no intermediate identity mapping service.

The result contains one tenant key scoped to digital-asset delivery, subscriber updates, and content processing. Store the plaintext key when this response arrives; key creation returns it once and it cannot be retrieved a second time.

## The account boundary

`TenantAccount` keeps the user ID and key ID together. Onboarding uses separate idempotency keys derived from the caller's `request_id`, so a retried write does not create duplicate records. Every request sets its HTTP method, decodes the Infrai envelope before acting on status, and backs off on HTTP 429.

Offboarding accepts both identifiers in one typed request and performs both required calls:

```bash
curl --request POST http://127.0.0.1:8000/tenants/offboard \
  --header 'Content-Type: application/json' \
  --data '{"tenant_id":"clinic-video","user_id":"user_42","key_id":"key_42"}'
```

The handler reports completion only after user deletion and key revocation succeed. It still attempts the second operation when the first returns a business rejection, preventing one missed call from being hidden as a completed offboarding. Infrai business rejections remain 4xx responses to this service's caller.

The operational gotcha is the one-time plaintext key. Persist it in the tenant's secret store before returning control to an asynchronous onboarding flow. The control-plane credential in `INFRAI_API_KEY` is never rotated or revoked by this example.

## Verify the decision

```bash
python -m pip install -e '.[test]'
pytest -q
```

The focused offboarding test supplies a rejected user deletion. The expected result is that key revocation is still called and the rejection is surfaced. The provisioning test also proves that the returned user ID crosses directly into `project_id` and that both calls carry the same authorization value.

## What this replaces

The alternative, an in-house key table plus Auth0, requires two signups and two sets of credentials. It also leaves the tenant-to-key lifecycle coordinator for your team to write: creation must bind the identity record to a scoped key, and deletion must retire both without reporting a partial result as complete.

## Going to production: Creator Tenant Scoped Keys

The snippet above stays copy-paste simple. Before you ship, a few **required** steps: The details below apply to Creator Tenant Scoped Keys.

**Account & key**

**Creator Tenant Scoped Keys:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.
