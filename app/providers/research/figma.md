# Figma OAuth Integration Research

> Last updated: 2026-03-17

## OAuth Endpoints

| Purpose | URL |
|---|---|
| Authorization | `https://www.figma.com/oauth` |
| Token Exchange | `POST https://api.figma.com/v1/oauth/token` |
| Token Refresh | `POST https://api.figma.com/v1/oauth/refresh` |
| Revoke | **None** — users revoke via Figma UI only |
| User Info | `GET https://api.figma.com/v1/me` |

**Note:** Refresh uses a **separate endpoint** (`/v1/oauth/refresh`), not the same token URL.

---

## Available Scopes

Scopes use `resource:permission` format and are **comma-separated** (not space-separated).

| Scope | Description |
|---|---|
| `current_user:read` | Read user profile |
| `file_content:read` | Read file content |
| `file_content:write` | Write file content |
| `file_metadata:read` | Read file metadata |
| `file_comments:read` | Read comments |
| `file_comments:write` | Write comments |
| `file_dev_resources:read` | Read dev resources |
| `file_dev_resources:write` | Write dev resources |
| `file_variables:read` | Read variables (Enterprise only) |
| `file_variables:write` | Write variables (Enterprise only) |
| `webhooks:write` | Manage webhooks |
| `library_analytics:read` | Read library analytics |

Old scopes `file_read` / `files:read` are deprecated.

---

## Token Lifecycle

| Token | Lifetime | Notes |
|---|---|---|
| Access token | **24 hours** | |
| Refresh token | Long-lived (exact expiry undocumented) | **Rotating** — old token invalidated on each use |

---

## Quirks

1. **No revoke endpoint** — `revoke_token()` returns `False`
2. **Separate refresh URL** — `/v1/oauth/refresh` instead of token URL
3. **Comma-separated scopes** — requires custom scope joining
4. **No PKCE support** documented
5. **Basic Auth recommended** (2025 update) for client credentials
6. **Form-encoded body** for token requests
7. **Rate limits** — per-user, per-plan, per-app with tiered endpoints

---

## User Info Endpoint

```
GET https://api.figma.com/v1/me
Authorization: Bearer {access_token}
```

Required scope: `current_user:read`

**Mapping:** `account_id` = `id`, `email` = `email`, `display_name` = `handle`

---

## REST API Services

| Service | Key Endpoints |
|---|---|
| Files | `GET /v1/files/{key}`, `GET /v1/files/{key}/nodes` |
| Images | `GET /v1/images/{key}` |
| Comments | `GET /v1/files/{key}/comments`, `POST /v1/files/{key}/comments` |
| Components | `GET /v1/files/{key}/components`, `GET /v1/files/{key}/component_sets` |
| Styles | `GET /v1/files/{key}/styles` |
| Teams/Projects | `GET /v1/teams/{id}/projects`, `GET /v1/projects/{id}/files` |
| Webhooks | `POST /v2/webhooks`, `GET /v2/webhooks/{id}` |

---

## Implementation Plan

```python
class FigmaProvider(OAuthProviderBase):
    provider_id = "figma"
    # auth_url = "https://www.figma.com/oauth"
    # token_url = "https://api.figma.com/v1/oauth/token"
    # revoke_url = None
    # default_scopes = ["current_user:read", "file_content:read"]
```

- `get_authorization_url`: Override for comma-separated scopes
- `exchange_code`: Standard POST to token URL
- `refresh_token`: **Custom** — must POST to `/v1/oauth/refresh` (not token URL)
- `revoke_token`: Return `False`
- `get_account_info`: `GET /v1/me`

## References

- [Figma OAuth Documentation](https://www.figma.com/developers/api#oauth2)
- [Figma REST API](https://www.figma.com/developers/api)
