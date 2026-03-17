# Linear OAuth Integration Research

> Last updated: 2026-03-17

## OAuth Endpoints

| Purpose | URL |
|---|---|
| Authorization | `https://linear.app/oauth/authorize` |
| Token Exchange | `https://api.linear.app/oauth/token` |
| Token Revoke | `https://api.linear.app/oauth/revoke` |
| GraphQL API | `https://api.linear.app/graphql` |

---

## Available Scopes

| Scope | Description |
|---|---|
| `read` | Read access to all resources |
| `write` | Write access to all resources |
| `admin` | Administrative access |
| `issues:create` | Create issues only |
| `comments:create` | Create comments only |
| `timeSchedule:write` | Write time schedules |
| `initiative:read` / `initiative:write` | Initiatives |
| `customer:read` / `customer:write` | Customers |

**Agent scopes:** `app:assignable`, `app:mentionable`

**Critical quirk:** Scopes are **comma-separated** (not space-separated). Example: `scope=read,write`

---

## Token Lifecycle

| Token | Lifetime | Notes |
|---|---|---|
| Access token | **24 hours** | |
| Refresh token | Mandatory for apps after Oct 1, 2025 | **Single-use** — new token on each refresh |

Revocation: RFC 7009-compliant via `POST /oauth/revoke` with `token` in form body.

---

## Quirks

1. **Comma-separated scopes** — requires custom handling in `get_authorization_url`
2. **PKCE supported** — when used, `client_secret` can be omitted
3. **GraphQL-only API** — no REST endpoints; `get_account_info` must use GraphQL
4. **Actor authorization** — `actor=app` param for agent/service account identity
5. **Client credentials grant** supported for server-to-server

---

## User Info (Account Info)

GraphQL query via `POST https://api.linear.app/graphql`:

```graphql
{ viewer { id name email displayName } }
```

**Mapping:** `account_id` = `viewer.id`, `email` = `viewer.email`, `display_name` = `viewer.displayName`

---

## Implementation Plan

```python
class LinearProvider(OAuthProviderBase):
    provider_id = "linear"
    # auth_url = "https://linear.app/oauth/authorize"
    # token_url = "https://api.linear.app/oauth/token"
    # revoke_url = "https://api.linear.app/oauth/revoke"
    # default_scopes = ["read"]
```

- `get_authorization_url`: Override for comma-separated scopes
- `exchange_code`: `exchange_code_standard` (works as-is)
- `refresh_token`: `refresh_token_standard` (persist new refresh token)
- `revoke_token`: POST to revoke URL with `token` in body
- `get_account_info`: POST GraphQL `{ viewer { id name email displayName } }`

Closest existing pattern: **Asana** (standard OAuth2 + refresh), with two differences: comma scopes and GraphQL account info.

## References

- [Linear OAuth 2.0 Authentication](https://linear.app/developers/oauth-2-0-authentication)
- [Linear GraphQL API](https://linear.app/developers/graphql)
- [Linear Developers Portal](https://developers.linear.app/docs/oauth/authentication)
