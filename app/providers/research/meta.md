# Meta (Facebook/Instagram/WhatsApp) OAuth Integration Research

> Last updated: 2026-03-17

## Overview

All Meta services share a single OAuth infrastructure built on Facebook Login. A single Meta App (developers.facebook.com) serves Facebook, Instagram, WhatsApp, and Business Suite. The differentiator is **which scopes are requested**.

- **Single App ID / App Secret** across all Meta services.
- **One authorization dialog** for Facebook, Instagram (via Facebook Login), and WhatsApp.
- Instagram also has a **separate direct login flow** at `api.instagram.com/oauth/authorize`.
- Current stable API version: **v22.0**.

## OAuth Endpoints

| Endpoint | URL |
|---|---|
| Authorization (Facebook Login) | `https://www.facebook.com/v{VERSION}/dialog/oauth` |
| Authorization (Instagram Direct) | `https://api.instagram.com/oauth/authorize` |
| Token Exchange | `https://graph.facebook.com/v{VERSION}/oauth/access_token` |
| Token Debug | `https://graph.facebook.com/debug_token?input_token={token}&access_token={app_token}` |
| Token Revoke | `DELETE https://graph.facebook.com/v{VERSION}/{user-id}/permissions` |
| User Info (Facebook) | `https://graph.facebook.com/v{VERSION}/me?fields=id,name,email,picture` |
| User Info (Instagram) | `https://graph.instagram.com/v{VERSION}/me?fields=user_id,username,account_type` |

---

## Token Lifecycle Deep Dive

This is Meta's most unusual aspect compared to standard OAuth providers.

### Token Types and Expiry

| Token Type | Expiry | How to Obtain |
|---|---|---|
| Short-lived User Token | ~1-2 hours | OAuth code exchange |
| Long-lived User Token | ~60 days | Exchange short-lived via `fb_exchange_token` |
| Page Access Token (from long-lived user) | Never expires* | `/me/accounts` with long-lived user token |
| App Access Token | Never expires | `client_credentials` grant |
| System User Token | Never expires | Business Manager UI/API |
| Instagram (Direct) Short-lived | ~1 hour | `api.instagram.com/oauth/access_token` |
| Instagram (Direct) Long-lived | ~60 days | Exchange via `ig_exchange_token` |

### Short-lived to Long-lived Exchange (Facebook)

```
GET https://graph.facebook.com/v{VERSION}/oauth/access_token
  ?grant_type=fb_exchange_token
  &client_id={app-id}
  &client_secret={app-secret}
  &fb_exchange_token={short-lived-token}
```

### Refreshing Long-lived Tokens

**Facebook:** NO true refresh mechanism. Long-lived tokens cannot be refreshed after expiry. User must re-authenticate after ~60 days.

**Instagram (Direct):** CAN be refreshed before expiry:
```
GET https://graph.instagram.com/refresh_access_token
  ?grant_type=ig_refresh_token
  &access_token={valid-long-lived-token}
```

---

## 1. Facebook Login / Graph API

### OAuth Flow

**Authorization URL:**
```
https://www.facebook.com/v{VERSION}/dialog/oauth
  ?client_id={app-id}
  &redirect_uri={redirect-uri}
  &state={state}
  &scope={comma-separated-scopes}
  &response_type=code
```

**Token Exchange:**
```
GET https://graph.facebook.com/v{VERSION}/oauth/access_token
  ?client_id={app-id}
  &redirect_uri={redirect-uri}
  &client_secret={app-secret}
  &code={code}
```

**Note:** Facebook does NOT return a `refresh_token` field.

### Available Scopes

**Default (no review required):**
- `public_profile` — Always included implicitly
- `email` — User's primary email

**User Data (require App Review):**
- `user_age_range`, `user_birthday`, `user_friends`, `user_gender`
- `user_hometown`, `user_likes`, `user_link`, `user_location`
- `user_photos`, `user_posts`, `user_videos`

**Pages:**
- `pages_show_list`, `pages_read_engagement`, `pages_read_user_content`
- `pages_manage_posts`, `pages_manage_engagement`, `pages_manage_metadata`
- `pages_manage_ads`, `pages_messaging`

### Revocation

```
DELETE https://graph.facebook.com/v{VERSION}/{user-id}/permissions
  ?access_token={access-token}
```

---

## 2. Instagram Graph API

### Two Authentication Paths

**Path 1: Instagram Platform API (Direct Login)** — Business/Creator accounts only

```
https://api.instagram.com/oauth/authorize
  ?client_id={app-id}
  &redirect_uri={redirect-uri}
  &scope={scopes}
  &response_type=code
  &state={state}
```

Token exchange: `POST https://api.instagram.com/oauth/access_token`

**Path 2: Instagram via Facebook Login** — Uses standard Facebook OAuth with Instagram scopes, API calls use `graph.facebook.com`.

### Scopes

**Direct Login:** `instagram_business_basic`, `instagram_business_content_publish`, `instagram_business_manage_messages`, `instagram_business_manage_comments`

**Via Facebook:** `instagram_basic`, `instagram_content_publish`, `instagram_manage_comments`, `instagram_manage_insights`, `instagram_manage_messages`

### Special Notes

- Instagram Basic Display API **deprecated December 4, 2024**
- Only Business and Creator accounts supported
- Tokens from direct login NOT interchangeable with Facebook Graph API tokens

---

## 3. Facebook Marketing API

Same Facebook Login OAuth flow, different scopes.

### Scopes

- `ads_management` — Full read/write ad accounts, campaigns, ads
- `ads_read` — Read-only ad account data and insights
- `business_management` — Manage business assets
- `catalog_management` — Manage product catalogs

### Access Levels

| Level | Requirements |
|---|---|
| Development | App admins/developers/testers only, up to 5 ad accounts |
| Standard Access | App Review required |
| Advanced Access | App Review + Business Verification |

---

## 4. WhatsApp Business API

### Authentication Model

Primarily uses **System User Access Tokens** (never-expiring). For platform onboarding, uses **Embedded Signup** OAuth flow.

### Scopes

- `whatsapp_business_management` — Manage account settings, phone numbers, templates
- `whatsapp_business_messaging` — Send/receive messages via Cloud API

### Requirements

- Business Verification mandatory
- Phone number must be verified via SMS or voice call

---

## 5. Meta Business Suite / Business Management API

### Scopes

- `business_management` — Core Business Manager access
- `commerce_account_manage_orders`, `commerce_account_read_orders`, `commerce_account_read_settings`

---

## Implementation Plan

### Recommended: Multiple Provider Classes

```
meta_facebook.py    — Facebook Login + Graph API
meta_instagram.py   — Instagram (both paths)
meta_marketing.py   — Marketing API (extends Facebook)
meta_whatsapp.py    — WhatsApp Business
```

### Key Considerations

1. **No standard refresh_token**: `refresh_token()` must use `fb_exchange_token` / `ig_refresh_token` grant types with the current access token as input
2. **Auto-exchange in `exchange_code()`**: Immediately perform short-to-long exchange so stored token is always long-lived
3. **`appsecret_proof` support**: HMAC-SHA256 of access token using app secret on all API calls
4. **API versioning**: Include Graph API version in provider config (deprecates yearly)
5. **Revocation**: `DELETE /{user-id}/permissions` for user tokens

## References

- [Access Token Guide](https://developers.facebook.com/docs/facebook-login/guides/access-tokens/)
- [Get Long-Lived Tokens](https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived/)
- [Manually Build a Login Flow](https://developers.facebook.com/docs/facebook-login/guides/advanced/manual-flow/)
- [Permissions Reference](https://developers.facebook.com/docs/permissions/)
- [Instagram Platform - OAuth](https://developers.facebook.com/docs/instagram-platform/reference/oauth-authorize/)
- [Instagram Platform - Refresh Token](https://developers.facebook.com/docs/instagram-platform/reference/refresh_access_token/)
- [Marketing API Authorization](https://developers.facebook.com/docs/marketing-api/get-started/authorization/)
- [WhatsApp Embedded Signup](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/overview/)
