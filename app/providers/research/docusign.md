# DocuSign OAuth Integration Research

> Last updated: 2026-03-17

## Overview

DocuSign uses a **unified OAuth 2.0 server** for all APIs. Same endpoints handle eSignature, CLM, Admin, Rooms, Click, and Navigator — scopes determine access.

## OAuth Endpoints

| Purpose | Demo | Production |
|---|---|---|
| Authorization | `https://account-d.docusign.com/oauth/auth` | `https://account.docusign.com/oauth/auth` |
| Token | `https://account-d.docusign.com/oauth/token` | `https://account.docusign.com/oauth/token` |
| Revoke | `https://account-d.docusign.com/oauth/revoke` | `https://account.docusign.com/oauth/revoke` |
| UserInfo | `https://account-d.docusign.com/oauth/userinfo` | `https://account.docusign.com/oauth/userinfo` |

---

## Token Lifecycle

| Token | Lifetime | Notes |
|---|---|---|
| Access token (Auth Code) | **8 hours** | |
| Access token (JWT Grant) | **1 hour** | |
| Refresh token | **30 days** | With `extended` scope, each refresh resets the 30-day window |

---

## Scopes by Service

### eSignature API
| Scope | Description |
|---|---|
| `signature` | Full eSignature access |
| `extended` | Extended refresh token lifetime |
| `impersonation` | Act on behalf of users (JWT only) |
| `openid` | OpenID Connect |

### CLM (Contract Lifecycle Management)
| Scope | Description |
|---|---|
| `spring_read` | Read CLM data (legacy SpringCM naming) |
| `spring_write` | Write CLM data |

### Admin API
| Scope | Description |
|---|---|
| `organization_read` | Read org structure |
| `user_read` / `user_write` | Read/manage users |
| `account_read` | Read account info |
| `domain_read` | Read domains |
| `group_read` | Read groups |
| `permission_read` | Read permissions |
| `identity_provider_read` | Read IdP config |
| `user_data_redact` | Redact user data |

### Rooms API
| Scope | Description |
|---|---|
| `dtr.rooms.read` / `dtr.rooms.write` | Read/manage rooms |
| `dtr.documents.read` / `dtr.documents.write` | Read/manage documents |
| `dtr.profile.read` / `dtr.profile.write` | Read/manage profiles |
| `dtr.company.read` / `dtr.company.write` | Read/manage companies |
| `room_forms` | Room forms |

### Click API
| Scope | Description |
|---|---|
| `click.manage` | Manage clickwraps |
| `click.send` | Send clickwraps |

### Navigator
| Scope | Description |
|---|---|
| `adm_store_unified_repo_read` | Read Navigator data |

---

## Critical Quirk: Base URI Discovery

After token exchange, **must** call `/oauth/userinfo` to discover the correct API base URI. Users may belong to multiple accounts across data centers:

```json
{
  "accounts": [
    {
      "account_id": "abc123",
      "base_uri": "https://na3.docusign.net",
      "is_default": true
    },
    {
      "account_id": "def456",
      "base_uri": "https://eu.docusign.net",
      "is_default": false
    }
  ]
}
```

---

## User Info Endpoint

```
GET https://account.docusign.com/oauth/userinfo
Authorization: Bearer {access_token}
```

**Mapping:** `account_id` = `sub`, `email` = `email`, `display_name` = `name`

---

## JWT Grant (Server-to-Server)

- App generates JWT signed with RSA private key
- Exchanges JWT for access token (1-hour lifetime)
- Requires prior admin consent
- No refresh token — re-generate JWT as needed

---

## Implementation Plan

```python
class DocuSignProvider(OAuthProviderBase):
    provider_id = "docusign"
    # auth_url = "https://account.docusign.com/oauth/auth"
    # token_url = "https://account.docusign.com/oauth/token"
    # revoke_url = "https://account.docusign.com/oauth/revoke"
    # default_scopes = ["signature", "extended", "openid"]
```

- `exchange_code`: Standard POST, then call `/oauth/userinfo` for base URI discovery
- `refresh_token`: Standard POST, `extended` scope keeps refresh token alive
- `revoke_token`: Standard revoke endpoint
- `get_account_info`: `/oauth/userinfo` — also provides base URI and multi-account info

**Single provider class** with scope presets per service. Must store `base_uri` and `account_id` alongside token.

## References

- [DocuSign OAuth Overview](https://developers.docusign.com/platform/auth/)
- [Authorization Code Grant](https://developers.docusign.com/platform/auth/authcode/)
- [JWT Grant](https://developers.docusign.com/platform/auth/jwt/)
- [Scopes Reference](https://developers.docusign.com/platform/auth/reference/scopes/)
