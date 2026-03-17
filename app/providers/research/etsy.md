# Etsy OAuth 2.0 Integration Research

> Last updated: 2026-03-17

## OAuth Endpoints

| Purpose | URL |
|---|---|
| Authorization | `https://www.etsy.com/oauth/connect` |
| Token (exchange + refresh) | `https://api.etsy.com/v3/public/oauth/token` |
| Revoke | **None** |
| User Info | `GET https://openapi.etsy.com/v3/application/users/me` |

---

## Available Scopes

| Scope | Description |
|---|---|
| `address_r` / `address_w` | User addresses |
| `billing_r` | Billing info |
| `cart_r` / `cart_w` | Shopping cart |
| `email_r` | Email address |
| `favorites_r` / `favorites_w` | Favorites |
| `feedback_r` | Feedback |
| `listings_d` / `listings_r` / `listings_w` | Listings (delete/read/write) |
| `profile_r` / `profile_w` | Profile |
| `recommend_r` / `recommend_w` | Recommendations |
| `shops_r` / `shops_w` | Shop data |
| `transactions_r` / `transactions_w` | Transactions/orders |

---

## Token Lifecycle

| Token | Lifetime | Notes |
|---|---|---|
| Access token | **1 hour** (3600s) | |
| Refresh token | **90 days** | Rolling — each refresh returns new refresh token |

Refresh does not require user re-approval and retains original scopes.

---

## Quirks

1. **PKCE is mandatory** on every flow (S256 only). Code verifier: 43-128 chars from `[A-Za-z0-9._~-]`.
2. **No `client_secret` in token requests.** The Shared Secret is only for webhook signature verification. PKCE replaces its role.
3. **No revoke endpoint.** `revoke_token()` returns `False`.
4. **`x-api-key` header required** on all API calls, set to the Keystring (client_id).
5. **Content-type** for token requests must be `application/x-www-form-urlencoded`.
6. **Rolling refresh tokens** — must persist new token on every refresh.

---

## User Info Endpoint

```
GET https://openapi.etsy.com/v3/application/users/me
Authorization: Bearer {access_token}
x-api-key: {client_id}
```

Required scope: `email_r`

**Mapping:** `account_id` = `str(user_id)`, `email` = `primary_email`, `display_name` = `first_name + " " + last_name`

---

## Implementation Plan

```python
class EtsyProvider(OAuthProviderBase):
    provider_id = "etsy"
    # auth_url = "https://www.etsy.com/oauth/connect"
    # token_url = "https://api.etsy.com/v3/public/oauth/token"
    # revoke_url = None
    # default_scopes = ["email_r", "shops_r", "listings_r"]
```

- `get_authorization_url`: Standard with PKCE (mandatory)
- `exchange_code`: POST with `client_id` + `code_verifier` (no `client_secret`)
- `refresh_token`: POST with `client_id` + `refresh_token` (no `client_secret`)
- `revoke_token`: Return `False`
- `get_account_info`: GET `/v3/application/users/me` with `x-api-key` header

**Note:** Custom token exchange needed since no `client_secret` is used (PKCE-only).

## References

- [Etsy Authentication Docs](https://developer.etsy.com/documentation/essentials/authentication/)
- [Etsy API Reference](https://developers.etsy.com/documentation/reference/)
- [Etsy Open API GitHub](https://github.com/etsy/open-api)
