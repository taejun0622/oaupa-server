# Snapchat OAuth Integration Research

> Last updated: 2026-03-17

## Overview

Snapchat has **two distinct OAuth systems** requiring separate provider implementations. Creative Kit is client-side only — no OAuth needed.

---

## 1. Login Kit (snapchat.py)

### OAuth Endpoints

| Purpose | URL |
|---|---|
| Authorization | `https://accounts.snapchat.com/accounts/oauth2/auth` |
| Token | `https://accounts.snapchat.com/accounts/oauth2/token` |
| Revoke | `https://accounts.snapchat.com/accounts/oauth2/revoke` |
| User Info | `POST https://kit.snapchat.com/v1/me` |

### Scopes

Scopes are **full URIs**:

| Scope | Description |
|---|---|
| `https://auth.snapchat.com/oauth2/api/user.display_name` | Display name |
| `https://auth.snapchat.com/oauth2/api/user.bitmoji.avatar` | Bitmoji avatar |
| `https://auth.snapchat.com/oauth2/api/user.external_id` | External ID |

### Token Lifecycle

| Token | Lifetime |
|---|---|
| Access token | **60 minutes** |
| Refresh token | Long-lived (undocumented exact expiry) |

### Quirks

- **No email available** — only external_id, display_name, bitmoji
- **PKCE supported** and required for public clients
- **User info is POST with GraphQL-style body** (unusual):
  ```json
  {"query": "{me{displayName bitmoji{avatar} externalId}}"}
  ```

### Account Info Mapping

`account_id` = `externalId`, `email` = None, `display_name` = `displayName`

---

## 2. Marketing API (snapchat_marketing.py)

### OAuth Endpoints

| Purpose | URL |
|---|---|
| Authorization | `https://accounts.snapchat.com/login/oauth2/authorize` |
| Token | `https://accounts.snapchat.com/login/oauth2/access_token` |
| User Info | `GET https://adsapi.snapchat.com/v1/me` |

### Scopes

| Scope | Description |
|---|---|
| `snapchat-marketing-api` | Ad account management |
| `snapchat-offline-conversions-api` | Offline conversions |
| `snapchat-profile-api` | Profile access |

### Token Lifecycle

| Token | Lifetime |
|---|---|
| Access token | **60 minutes** |
| Refresh token | Long-lived |

### Quirks

- **Email available** via user info endpoint
- Includes org and ad account data
- Requires developer approval for API access
- Standard REST user info (not GraphQL)

### Account Info Mapping

`account_id` = `me.id`, `email` = `me.email`, `display_name` = `me.display_name`

---

## Implementation Notes

- Two separate providers needed due to different auth endpoints, scope formats, and user info mechanisms
- Login Kit: Override `get_account_info` for POST GraphQL-style user info
- Marketing API: Standard REST pattern, closer to existing providers

## References

- [Snap Kit Login](https://developers.snap.com/snap-kit/login-kit)
- [Snapchat Marketing API](https://developers.snap.com/api/marketing-api)
