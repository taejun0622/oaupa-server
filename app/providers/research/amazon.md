# Amazon OAuth Integration Research

> Last updated: 2026-03-17

## Overview

Amazon has **four separate OAuth-based services** sharing the Login with Amazon (LWA) token infrastructure. Recommend implementing as separate providers sharing an `AmazonProviderBase`.

---

## 1. Login with Amazon (LWA) — Priority P0

### OAuth Endpoints

| Purpose | URL |
|---|---|
| Authorization | `https://www.amazon.com/ap/oa` |
| Token | `https://api.amazon.com/auth/o2/token` |
| Revoke | **None** |
| User Info | `https://api.amazon.com/user/profile` |

### Scopes

| Scope | Description |
|---|---|
| `profile` | Name, email, user_id |
| `profile:user_id` | User ID only |
| `postal_code` | Postal code |

### Token Lifecycle

| Token | Lifetime |
|---|---|
| Access token | **60 minutes** |
| Refresh token | **Indefinite** (until user revokes) |

### Account Info

`GET https://api.amazon.com/user/profile`

**Mapping:** `account_id` = `user_id`, `email` = `email`, `display_name` = `name`

---

## 2. Selling Partner API (SP-API) — Priority P3

### OAuth Flow

- Authorization through **Seller Central consent pages** (region-specific URLs)
- Same LWA token endpoint for exchange/refresh
- Auth code returned as `spapi_oauth_code` (non-standard parameter name)
- **Role-based access** instead of OAuth scopes
- Requires **AWS IAM credentials** alongside OAuth tokens for API calls

### Regions

| Region | Authorization URL |
|---|---|
| North America | `https://sellercentral.amazon.com/apps/authorize/consent` |
| Europe | `https://sellercentral-europe.amazon.com/apps/authorize/consent` |
| Far East | `https://sellercentral-japan.amazon.com/apps/authorize/consent` |

### Quirks

- No user profile endpoint; seller info via `getMarketplaceParticipations`
- Dual-auth: OAuth token + AWS Signature V4
- Separate developer registration process

---

## 3. Amazon Advertising API — Priority P1

### OAuth Flow

Same LWA auth flow with advertising-specific scope.

### Scopes

| Scope | Description |
|---|---|
| `advertising::campaign_management` | Full ad management |

### Regional API Endpoints

| Region | Base URL |
|---|---|
| North America | `https://advertising-api.amazon.com` |
| Europe | `https://advertising-api-eu.amazon.com` |
| Far East | `https://advertising-api-fe.amazon.com` |

### Quirks

- Requires `Amazon-Advertising-API-Scope` header with profile ID on every call
- Profile ID obtained via `GET /v2/profiles` after token exchange
- Separate application approval process

---

## 4. Alexa SMAPI — Priority P4

### OAuth Flow

LWA with Alexa-specific scopes.

### Scopes

| Scope | Description |
|---|---|
| `alexa::ask:skills:readwrite` | Skill management |
| `alexa::ask:models:readwrite` | Model management |
| `alexa::ask:skills:test` | Skill testing |
| `alexa::ask:catalogs:readwrite` | Catalog management |

### API Base

`https://api.amazonalexa.com`

Vendor info via `GET /v1/vendors`

---

## Implementation Notes

- All services share LWA token endpoint (`api.amazon.com/auth/o2/token`)
- Create `AmazonProviderBase` with shared token exchange/refresh
- Subclass per service for different auth URLs and account info
- Priority: LWA first, then Ads API, then SP-API, Alexa last

## References

- [Login with Amazon Docs](https://developer.amazon.com/docs/login-with-amazon/web-docs.html)
- [SP-API Authorization](https://developer-docs.amazon.com/sp-api/docs/authorizing-selling-partner-api-applications)
- [Amazon Advertising API](https://advertising.amazon.com/API/docs/en-us)
