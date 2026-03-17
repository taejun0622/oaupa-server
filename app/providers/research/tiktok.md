# TikTok OAuth Integration Research

> Last updated: 2026-03-17

## Overview

TikTok has **THREE completely separate OAuth systems**, each with its own domain, app registration, and conventions. Recommend implementing as three separate providers.

---

## 1. Login Kit + Content API (tiktok.py) — Priority P0

### OAuth Endpoints

| Purpose | URL |
|---|---|
| Authorization | `https://www.tiktok.com/v2/auth/authorize/` |
| Token | `https://open.tiktokapis.com/v2/oauth/token/` |
| Revoke | `https://open.tiktokapis.com/v2/oauth/revoke/` |
| User Info | `https://open.tiktokapis.com/v2/user/info/` |

### Key Differences from Standard OAuth

- Uses `client_key` (not `client_id`)
- **Comma-separated scopes** (not space-separated)
- **PKCE mandatory** (S256 only)
- No email available — TikTok never exposes user email

### Scopes

| Scope | Description |
|---|---|
| `user.info.basic` | Display name, avatar, open_id |
| `user.info.profile` | Bio, profile deep link |
| `user.info.stats` | Follower/following/likes counts |
| `video.list` | Read user's video list |
| `video.upload` | Upload videos |
| `video.publish` | Publish uploaded videos |

### Token Lifecycle

| Token | Lifetime | Notes |
|---|---|---|
| Access token | **24 hours** | |
| Refresh token | **365 days** | Rotating/single-use — new one on each refresh |

### User Info

`POST https://open.tiktokapis.com/v2/user/info/` with fields in query params.

**Mapping:** `account_id` = `open_id`, `email` = None, `display_name` = `display_name`

---

## 2. Marketing API (tiktok_business.py) — Priority P1

### OAuth Endpoints

| Purpose | URL |
|---|---|
| Authorization | `https://business-api.tiktok.com/portal/auth` |
| Token | `https://business-api.tiktok.com/open_api/v1.3/oauth2/access_token/` |

### Key Differences

- Entirely different domain: `business-api.tiktok.com`
- Uses `app_id` / `secret` naming
- **JSON body** for token exchange (not form-encoded)
- Numeric scope IDs
- **No PKCE**, no standard refresh flow
- Multi-advertiser support (one auth grants access to multiple ad accounts)

### Token Lifecycle

- Access token: varies by grant
- No standard refresh mechanism — re-authorization required

---

## 3. Shop API (tiktok_shop.py) — Priority P2

### OAuth Endpoints

| Purpose | URL |
|---|---|
| Authorization | `https://auth.tiktok-shops.com/oauth/authorize` |
| Token | `https://auth.tiktok-shops.com/api/v2/token/get` |
| Refresh | `https://auth.tiktok-shops.com/api/v2/token/refresh` |

### Key Differences

- Domain: `services.tiktokshop.com` / `auth.tiktok-shops.com`
- Uses `app_key` / `app_secret`
- **GET-based token exchange** with `grant_type=authorized_code`
- Requires **HMAC request signing** on all API calls
- Shorter token lifetime (~4 hours)

---

## Implementation Notes

- Implement as **three separate providers** since they share no OAuth infrastructure
- Start with Login Kit + Content API (closest to standard OAuth 2.0)
- Login Kit requires custom `get_authorization_url` for `client_key` and comma scopes
- Marketing API requires custom `exchange_code` for JSON body format

## References

- [TikTok Login Kit](https://developers.tiktok.com/doc/login-kit-web/)
- [TikTok Token Management](https://developers.tiktok.com/doc/oauth-user-access-token-management)
- [TikTok Marketing API](https://business-api.tiktok.com/portal/docs)
- [TikTok Shop API](https://partner.tiktokshop.com/docv2)
