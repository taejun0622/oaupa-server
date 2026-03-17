# Monday.com OAuth Integration Research

> Last updated: 2026-03-17

## 1. OAuth Endpoints

| Purpose | URL |
|---|---|
| Authorization | `https://auth.monday.com/oauth2/authorize` |
| Token exchange | `https://auth.monday.com/oauth2/token` |
| Revoke | **None** (no revoke endpoint exists) |
| API base | `https://api.monday.com/v2` (GraphQL) |

**Note:** Monday.com uses `scopes` (plural) query param, not standard `scope` (singular).

---

## 2. Available Scopes

| Scope | Description |
|---|---|
| `me:read` | Read authenticated user info |
| `account:read` | Read account-level data |
| `boards:read` / `boards:write` | Read/create boards, items, columns |
| `workspaces:read` / `workspaces:write` | Read/create workspaces |
| `docs:read` / `docs:write` | Read/create documents |
| `updates:read` / `updates:write` | Read/create item updates |
| `assets:read` | Read file assets |
| `notifications:write` | Send notifications |
| `tags:read` | Read tags |
| `teams:read` / `teams:write` | Read/manage teams |
| `users:read` / `users:write` | Read/manage users |
| `webhooks:read` / `webhooks:write` | Read/manage webhooks |

---

## 3. Token Lifecycle

| Property | Value |
|---|---|
| Token type | Bearer |
| Expires | **Never** — valid until user uninstalls the app |
| Refresh token | **Not supported** |
| Revocation | **No API endpoint** — only on app uninstall |
| Auth code validity | 10 minutes |

---

## 4. Quirks

- **No refresh / no expiry**: `refresh_token` should raise `NotImplementedError`
- **No revoke endpoint**: `revoke_token` returns `False`
- **Plural "scopes" param**: Auth URL uses `scopes`, not `scope` — must override URL builder
- **GraphQL-only API**: All API calls are POST to `https://api.monday.com/v2`
- **Rate limits**: Complexity-based (10M points/min paid, 1M free)
- **App lifecycle webhooks**: `app_uninstall` events for token cleanup

---

## 5. User Info

GraphQL query (scope: `me:read`):
```
POST https://api.monday.com/v2
{"query": "{ me { id name email account { id name } } }"}
```

**Mapping:** `account_id` = `me.id`, `email` = `me.email`, `display_name` = `me.name`

---

## 6. Implementation Plan

```python
class MondayProvider(OAuthProviderBase):
    provider_id = "monday"
    # auth_url = "https://auth.monday.com/oauth2/authorize"
    # token_url = "https://auth.monday.com/oauth2/token"
    # revoke_url = None
    # default_scopes = ["me:read", "boards:read"]
```

- `get_authorization_url`: Override to use `scopes` (plural) query param
- `exchange_code`: Standard POST, can use `exchange_code_standard`
- `refresh_token`: Raise `NotImplementedError`
- `revoke_token`: Return `False`
- `get_account_info`: POST GraphQL `{ me { id name email } }`

## References

- [OAuth and Permissions](https://developer.monday.com/apps/docs/oauth)
- [Authentication (API Reference)](https://developer.monday.com/api-reference/docs/authentication)
- [Rate limits](https://developer.monday.com/api-reference/docs/rate-limits)
