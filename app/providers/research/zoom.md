# Zoom OAuth Integration Research

> Last updated: 2026-03-17

## OAuth Endpoints

| Purpose | URL |
|---|---|
| Authorization | `https://zoom.us/oauth/authorize` |
| Token | `https://zoom.us/oauth/token` |
| Revoke | `https://zoom.us/oauth/revoke` |
| User Info | `https://api.zoom.us/v2/users/me` |

---

## Token Lifecycle

| Token | Lifetime |
|---|---|
| Access token | **1 hour** (3600s) |
| Refresh token | **15 years** (effectively permanent) |

- **Auth method:** HTTP Basic Auth (`base64(client_id:client_secret)`)
- Refresh tokens are **non-rotating** — same token reused

---

## Available Scopes

### Meetings API
| Scope | Description |
|---|---|
| `meeting:read` | Read meeting details |
| `meeting:write` | Create/update/delete meetings |
| `meeting:master` | Act as scheduling privilege |

### Webinars API
| Scope | Description |
|---|---|
| `webinar:read` | Read webinar details |
| `webinar:write` | Create/update/delete webinars |

### Phone API
| Scope | Description |
|---|---|
| `phone:read` | Read phone settings |
| `phone:write` | Manage phone settings |
| `phone_call_log:read` | Read call logs |
| `phone_recording:read` | Read call recordings |

### Team Chat API
| Scope | Description |
|---|---|
| `chat_message:read` | Read chat messages |
| `chat_message:write` | Send chat messages |
| `chat_channel:read` | Read channel info |
| `chat_channel:write` | Manage channels |

### User/Account
| Scope | Description |
|---|---|
| `user:read` | Read user profile |
| `user:write` | Update user profile |
| `account:read` | Read account info |
| `recording:read` | Read cloud recordings |
| `recording:write` | Manage cloud recordings |

---

## Server-to-Server OAuth (No User Interaction)

Zoom also supports **Server-to-Server OAuth** apps:
- Uses `client_credentials` grant type
- Same token endpoint
- Account-wide access (no per-user consent)
- Access token: 1 hour, no refresh token
- Different app type in Zoom Marketplace

---

## User Info Endpoint

```
GET https://api.zoom.us/v2/users/me
Authorization: Bearer {access_token}
```

**Mapping:** `account_id` = `id`, `email` = `email`, `display_name` = `first_name + " " + last_name`

---

## Quirks

1. **HTTP Basic Auth** for token endpoint
2. **Scopes are granular** — `meeting:read:meeting:admin` format for admin-level access
3. **Rate limits:** 10 requests/second per app, varies by endpoint
4. **Webhook validation:** Uses CRC challenge for endpoint URL validation
5. **`force_verify=true`** param to force re-consent

---

## Implementation Plan

```python
class ZoomProvider(OAuthProviderBase):
    provider_id = "zoom"
    # auth_url = "https://zoom.us/oauth/authorize"
    # token_url = "https://zoom.us/oauth/token"
    # revoke_url = "https://zoom.us/oauth/revoke"
    # default_scopes = ["user:read", "meeting:read"]
```

- `exchange_code`: `exchange_code_standard(use_basic_auth=True)`
- `refresh_token`: `refresh_token_standard(use_basic_auth=True)`
- `revoke_token`: POST to revoke URL with token in body
- `get_account_info`: `GET /v2/users/me`

**Complexity: Low.** Standard OAuth 2.0 with Basic Auth, well-aligned with existing helpers.

## References

- [Zoom OAuth Overview](https://developers.zoom.us/docs/integrations/oauth/)
- [Zoom API Reference](https://developers.zoom.us/docs/api/)
- [Zoom Scopes](https://developers.zoom.us/docs/integrations/oauth-scopes/)
