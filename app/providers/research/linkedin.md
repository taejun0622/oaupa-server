# LinkedIn OAuth Integration Research

> Last updated: 2026-03-17

## Shared OAuth Infrastructure

All LinkedIn APIs share the same OAuth 2.0 endpoints. The differentiation is in **scopes** and **API product access**.

### Core Endpoints

| Endpoint | URL |
|---|---|
| Authorization | `https://www.linkedin.com/oauth/v2/authorization` |
| Token Exchange | `https://www.linkedin.com/oauth/v2/accessToken` |
| Token Introspection | `https://www.linkedin.com/oauth/v2/introspectToken` |
| OIDC Discovery | `https://www.linkedin.com/oauth/.well-known/openid-configuration` |
| OIDC UserInfo | `https://api.linkedin.com/v2/userinfo` |
| JWKS URI | `https://www.linkedin.com/oauth/openid/jwks` |

### Token Revocation — NOTABLE GAP

LinkedIn does **NOT** expose a standard RFC 7009 revocation endpoint. Tokens invalidated via: member settings, scope changes triggering re-auth, or LinkedIn server-side action.

### Token Lifecycle

| Token Type | Lifetime |
|---|---|
| Access Token | **60 days** (5,184,000s) |
| Refresh Token | **365 days** — MDP partners only |
| Authorization Code | **30 minutes** |

Refresh tokens use a **fixed countdown** (not rolling). Programmatic refresh tokens only available for **Marketing Developer Platform (MDP) approved partners**. Sign In with LinkedIn does NOT get refresh tokens.

---

## 1. LinkedIn Sign In (OpenID Connect)

**Scopes:** `openid`, `profile`, `email`

**ID Token:** JWT signed with RS256. Claims: `sub` (pairwise), `name`, `given_name`, `family_name`, `picture`, `email`, `email_verified`, `locale`.

**UserInfo endpoint:** `GET https://api.linkedin.com/v2/userinfo`

**Quirks:**
- `email` and `email_verified` may be absent even with `email` scope
- Subject identifiers are pairwise (unique per app)
- No refresh tokens — "refresh" is a silent re-auth if user is logged into linkedin.com

---

## 2. LinkedIn Marketing API (Advertising)

**Key scopes:** `r_ads`, `rw_ads`, `r_ads_reporting`, `r_basicprofile`, `r_organization_admin`

**Additional:** `rw_dmp_segments`, `rw_conversions`, `r_marketing_leadgen_automation`, `rw_media_plans`

**Requirements:**
- 3-legged OAuth only (2-legged NOT supported)
- Members need Ad Account roles: `ACCOUNT_BILLING_ADMIN`, `ACCOUNT_MANAGER`, `CAMPAIGN_MANAGER`, or `CREATIVE_MANAGER`
- Ad Account must be mapped to dev app in Developer Portal

**Access tiers:** Development (read unlimited, edit 5 accounts) and Standard (unlimited).

---

## 3. LinkedIn Pages / Community Management API

**Key scopes:** `r_organization_social_feed`, `r_organization_followers`, `rw_organization_admin`, `w_organization_social_feed`, `w_member_social_feed`, `r_basicprofile`, `r_1st_connections_size`

**Newer scopes (v202504+):** `r_member_profileAnalytics`, `r_member_postAnalytics`

**Rate limits (Dev tier):** 500 calls/app/24hr, 100 calls/member/24hr.

---

## Implementation Plan

**Architecture:** One `LinkedInProvider` with service parameter determining scopes.

**Method mapping:**
- `get_authorization_url()` — same endpoint, different scopes per service
- `exchange_code()` — `POST /oauth/v2/accessToken` with `grant_type=authorization_code`
- `refresh_token()` — `POST /oauth/v2/accessToken` with `grant_type=refresh_token` (MDP only)
- `revoke_token()` — No API. Delete from DB + introspect to verify. Return `False`.
- `get_account_info()` — `/v2/userinfo` (Sign In), `/rest/adAccounts` (Marketing)

**Key considerations:** Plan for 1000+ char tokens in DB. PKCE support available. Scope changes invalidate all prior tokens.

## References

- [Authorization Code Flow](https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow)
- [Sign In with LinkedIn (OIDC)](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2)
- [Refresh Tokens](https://learn.microsoft.com/en-us/linkedin/shared/authentication/programmatic-refresh-tokens)
- [Token Introspection](https://learn.microsoft.com/en-us/linkedin/shared/authentication/token-introspection)
- [Community Management Overview](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/community-management-overview)
