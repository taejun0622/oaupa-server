# Pinterest OAuth Integration Research

> Last updated: 2026-03-17

## Overview

Pinterest uses standard OAuth 2.0 Authorization Code flow for API v5. All services share a single OAuth system — scopes control access. No client credentials grant (all access requires user authorization).

## 1. OAuth Endpoints

| Purpose | URL |
|---|---|
| Authorization | `https://www.pinterest.com/oauth/?response_type=code&client_id={id}&redirect_uri={uri}&scope={scopes}&state={state}` |
| Token | `POST https://api.pinterest.com/v5/oauth/token` |
| Revoke | `POST https://api.pinterest.com/v5/oauth/token/revoke` |
| User Info | `GET https://api.pinterest.com/v5/user_account` |

**Note:** Pinterest uses **comma-separated scopes** (not space-separated). Example: `scope=user_accounts:read,pins:read,boards:read`

---

## 2. Available Scopes

### Organic Content
| Scope | Description |
|---|---|
| `user_accounts:read` | Read user account info |
| `pins:read` / `pins:read_secret` | Read public/secret Pins |
| `pins:write` / `pins:write_secret` | Create/update/delete Pins |
| `boards:read` / `boards:read_secret` | Read public/secret boards |
| `boards:write` / `boards:write_secret` | Create/update/delete boards |

### Ads API
| Scope | Description |
|---|---|
| `ads:read` | Read ad accounts, campaigns, reporting |
| `ads:write` | Create/update/delete ad objects |

### Catalogs
| Scope | Description |
|---|---|
| `catalogs:read` / `catalogs:write` | Read/manage catalog/feed data |

---

## 3. Token Lifecycle

| Token | Lifetime |
|---|---|
| Access token | **30 days** (2,592,000s) |
| Refresh token | **365 days** (31,536,000s) |

- **Auth method:** HTTP Basic Auth (`base64(client_id:client_secret)`)
- **Refresh token rotation:** Yes — refresh returns new refresh token, old one invalidated
- **Revocation:** POST with `token` and optional `token_type_hint`
- **Known issue:** Community reports of error 290 when revoking tokens

---

## 4. User Info Endpoint

```
GET https://api.pinterest.com/v5/user_account
```

Required scope: `user_accounts:read`

**Mapping:** `account_id` = `username`, `email` = **None** (Pinterest does NOT expose email), `display_name` = `business_name` or `username`

---

## 5. Quirks

1. **HTTP Basic Auth** for token endpoint — not body params
2. **No PKCE support** — confidential client flow only
3. **Comma-separated scopes** in auth URL (space-separated in token response)
4. **No email access** via API
5. **Refresh token rotation** — must persist new token
6. **Business account required** for Ads API

---

## 6. Implementation Plan

```python
class PinterestProvider(OAuthProviderBase):
    provider_id = "pinterest"
    # auth_url = "https://www.pinterest.com/oauth/"
    # token_url = "https://api.pinterest.com/v5/oauth/token"
    # revoke_url = "https://api.pinterest.com/v5/oauth/token/revoke"
    # default_scopes = ["user_accounts:read", "pins:read", "boards:read"]
```

- `get_authorization_url`: Override to use comma-separated scopes
- `exchange_code`: `use_basic_auth=True`
- `refresh_token`: `use_basic_auth=True`, persist new refresh token
- `revoke_token`: POST with `token` in body
- `get_account_info`: `GET /v5/user_account`

## References

- [Pinterest API v5 Documentation](https://developers.pinterest.com/docs/api/v5/)
- [Authentication Guide](https://developers.pinterest.com/docs/getting-started/set-up-authentication-and-authorization/)
- [Pinterest API OpenAPI Spec](https://github.com/pinterest/api-description/blob/main/v5/openapi.yaml)
