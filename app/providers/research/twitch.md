# Twitch OAuth Integration Research

> Last updated: 2026-03-17

## OAuth Endpoints (Shared Across All Services)

| Purpose | URL |
|---|---|
| Authorization | `https://id.twitch.tv/oauth2/authorize` |
| Token | `https://id.twitch.tv/oauth2/token` |
| Revoke | `https://id.twitch.tv/oauth2/revoke` |
| Validate | `https://id.twitch.tv/oauth2/validate` |
| OIDC UserInfo | `https://id.twitch.tv/oauth2/userinfo` |

---

## Token Lifecycle

| Token | Lifetime | Notes |
|---|---|---|
| Access token | **~4 hours** | |
| Refresh token (confidential) | **Never expires** | |
| Refresh token (public) | **30 days** | |
| App access token | **~60 days** | No refresh, re-request via client credentials |

**Mandatory hourly validation:** Twitch requires calling `GET /oauth2/validate` at least once per hour to check token validity.

---

## Available Scopes

### Twitch API (Helix)
| Scope | Description |
|---|---|
| `user:read:email` | Read user email |
| `user:read:subscriptions` | Read user subscriptions |
| `user:edit` | Edit user profile |
| `channel:read:subscriptions` | Read channel subscriptions |
| `channel:manage:broadcast` | Manage stream settings |
| `channel:manage:videos` | Manage VODs |
| `channel:read:editors` | Read channel editors |
| `clips:edit` | Create clips |
| `moderation:read` | Read moderation events |
| `moderator:manage:banned_users` | Ban/unban users |
| `analytics:read:extensions` | Read extension analytics |
| `analytics:read:games` | Read game analytics |
| `bits:read` | Read bits events |

### Chat
| Scope | Description |
|---|---|
| `chat:read` | Read chat messages (IRC) |
| `chat:edit` | Send chat messages (IRC) |
| `user:read:chat` | Read chat via EventSub |
| `user:write:chat` | Send chat via EventSub |
| `channel:moderate` | Moderate chat |

---

## Services

### 1. Twitch API (Helix)

Standard OAuth with a unique quirk: requires **both** `Authorization: Bearer` AND `Client-Id` headers on all API calls.

```
GET https://api.twitch.tv/helix/users
Authorization: Bearer {access_token}
Client-Id: {client_id}
```

### 2. Chat (IRC)

Uses same OAuth tokens. Authenticates to IRC with `PASS oauth:{token}`.

### 3. EventSub (Webhooks)

- **Webhook transport:** Requires App Access Tokens (client_credentials), not user tokens
- **WebSocket transport:** Uses user tokens
- Webhook subscriptions need HMAC-SHA256 signature verification

### 4. Extensions

Uses **JWT** (not OAuth). Does NOT fit `OAuthProviderBase`. Out of scope.

---

## User Info

```
GET https://api.twitch.tv/helix/users
Authorization: Bearer {access_token}
Client-Id: {client_id}
```

**Mapping:** `account_id` = `data[0].id`, `email` = `data[0].email` (requires `user:read:email`), `display_name` = `data[0].display_name`

---

## Quirks

1. **Revoke only needs `client_id` + `token`** (no `client_secret`)
2. **OIDC fully supported** with standard claims
3. **`force_verify=true`** parameter to force re-consent
4. **Dual header requirement** — Bearer token AND Client-Id on all API calls
5. **Mandatory token validation** — hourly via validate endpoint
6. **Token type** in responses is lowercase `"bearer"`

---

## Implementation Plan

```python
class TwitchProvider(OAuthProviderBase):
    provider_id = "twitch"
    # auth_url = "https://id.twitch.tv/oauth2/authorize"
    # token_url = "https://id.twitch.tv/oauth2/token"
    # revoke_url = "https://id.twitch.tv/oauth2/revoke"
    # default_scopes = ["user:read:email"]
```

- `exchange_code`: Standard POST
- `refresh_token`: Standard POST
- `revoke_token`: POST with `client_id` + `token` (no secret needed)
- `get_account_info`: `GET /helix/users` with `Client-Id` header

## References

- [Twitch Authentication](https://dev.twitch.tv/docs/authentication/)
- [Twitch API Reference](https://dev.twitch.tv/docs/api/reference/)
- [Twitch EventSub](https://dev.twitch.tv/docs/eventsub/)
