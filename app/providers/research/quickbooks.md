# QuickBooks (Intuit) OAuth Integration Research

> Last updated: 2026-03-17

## Overview

Intuit uses **one OAuth 2.0 + OpenID Connect server** for all services. The service is selected by scope, not endpoint.

## OAuth Endpoints

| Purpose | URL |
|---|---|
| Authorization | `https://appcenter.intuit.com/connect/oauth2` |
| Token | `https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer` |
| Revoke | `https://developer.api.intuit.com/v2/oauth2/tokens/revoke` |
| UserInfo | `https://accounts.platform.intuit.com/v1/openid_connect/userinfo` |
| Discovery (sandbox) | `https://developer.api.intuit.com/.well-known/openid_sandbox_configuration` |
| Discovery (prod) | `https://developer.api.intuit.com/.well-known/openid_configuration` |

### API Base URLs

| Environment | URL |
|---|---|
| Sandbox | `https://sandbox-quickbooks.api.intuit.com` |
| Production | `https://quickbooks.api.intuit.com` |

---

## Available Scopes

| Scope | Description |
|---|---|
| `com.intuit.quickbooks.accounting` | Full accounting API access |
| `com.intuit.quickbooks.payment` | Payments API access |
| `openid` | OpenID Connect |
| `profile` | User profile |
| `email` | User email |
| `phone` | User phone |
| `address` | User address |

Payroll scopes exist but are restricted/invitation-only.

---

## Token Lifecycle

| Token | Lifetime | Notes |
|---|---|---|
| Access token | **~1 hour** (3600s) | |
| Refresh token | **100 days** | Rolling — resets on each use |
| Refresh token max | **5 years** | Policy change Nov 2025 |

- Refresh tokens **rotate** — each refresh returns new access + refresh tokens
- **Auth method:** HTTP Basic Auth required (`base64(client_id:client_secret)`)

---

## Critical Quirk: Realm ID

The `realmId` (company ID) is returned **only during the OAuth callback** as a query parameter:
- Required for ALL API calls: `/v3/company/{realmId}/...`
- **Not retrievable** from any API endpoint after the callback
- Must be stored alongside the token in oaupa's token vault

---

## User Info Endpoint

```
GET https://accounts.platform.intuit.com/v1/openid_connect/userinfo
Authorization: Bearer {access_token}
```

Requires `openid` scope.

**Mapping:** `account_id` = `sub`, `email` = `email`, `display_name` = `givenName + " " + familyName`

---

## Implementation Plan

```python
class QuickBooksProvider(OAuthProviderBase):
    provider_id = "quickbooks"
    # auth_url = "https://appcenter.intuit.com/connect/oauth2"
    # token_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
    # revoke_url = "https://developer.api.intuit.com/v2/oauth2/tokens/revoke"
    # default_scopes = ["com.intuit.quickbooks.accounting", "openid", "email"]
```

- `exchange_code`: `exchange_code_standard(use_basic_auth=True)` + capture `realmId` from callback
- `refresh_token`: `refresh_token_standard(use_basic_auth=True)`, persist new tokens
- `revoke_token`: POST to revoke URL with Basic Auth
- `get_account_info`: `GET /v1/openid_connect/userinfo`

**Key design consideration:** OAuth callback handler must extract and store `realmId` from callback URL. May require extending the base flow or storing in `TokenResponse.raw_response`.

## References

- [Intuit OAuth 2.0](https://developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization/oauth-2.0)
- [QuickBooks API Reference](https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/account)
- [Discovery Documents](https://developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization/openid-connect)
