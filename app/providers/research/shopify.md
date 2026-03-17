# Shopify OAuth Integration Research

> Last updated: 2026-03-17

## Overview

Only the **Shopify Admin API** has a real OAuth flow. Storefront tokens are created via Admin API, Partners API uses static tokens, and Payments is accessed via Admin scopes. oaupa needs **one provider: `shopify`**.

## OAuth Endpoints (Per-Store — Main Architectural Challenge)

| Purpose | URL Pattern |
|---|---|
| Authorization | `https://{shop}.myshopify.com/admin/oauth/authorize` |
| Token Exchange | `https://{shop}.myshopify.com/admin/oauth/access_token` |
| Revoke | **None** (no standard revoke endpoint) |
| Shop Info | `GET https://{shop}.myshopify.com/admin/api/2026-01/shop.json` |

---

## Token Lifecycle — Two Modes

### Offline Tokens (Default)

| Property | Value |
|---|---|
| One per | app/shop pair |
| Legacy expiry | **Never** |
| New (Dec 2025) | Optionally expire after **60 min** with refresh token |
| Refresh token | **90-day lifetime**, rotating |

### Online Tokens (User-Scoped)

| Property | Value |
|---|---|
| Expiry | **24 hours** or on logout |
| Refresh token | **None** |

---

## Available Scopes

Follow `read_{resource}` / `write_{resource}` pattern. 30+ scope pairs:

| Category | Scopes |
|---|---|
| Products | `read_products`, `write_products` |
| Orders | `read_orders`, `write_orders` |
| Customers | `read_customers`, `write_customers` |
| Inventory | `read_inventory`, `write_inventory` |
| Shipping | `read_shipping`, `write_shipping` |
| Themes | `read_themes`, `write_themes` |
| Discounts | `read_discounts`, `write_discounts` |
| Fulfillment | `read_fulfillments`, `write_fulfillments` |
| Payments | `read_shopify_payments_payouts`, `read_shopify_payments_disputes` |

---

## Critical Implementation Quirks

1. **Per-store dynamic URLs** — `auth_url`/`token_url` must be constructed with the shop domain. Provider must override methods and receive `shop` from connection metadata.
2. **HMAC validation** — Callback includes `hmac` param that must be validated with HMAC-SHA256 before exchanging code.
3. **No revoke endpoint** — `revoke_token()` returns False. Tokens die on app uninstall or secret rotation.
4. **Mandatory GDPR webhooks** — Must handle `customers/data_request`, `customers/redact`, `shop/redact` (fires 48h after uninstall).
5. **`redirect_uri` not sent in token request** — Unlike standard OAuth.
6. **API versioning** — All URLs include a date version (e.g., `2026-01`) rotating quarterly.

---

## Other APIs

- **Storefront API**: Tokens created via Admin API `storefrontAccessTokenCreate`. Model as feature of Admin connection.
- **Partners API**: Static tokens from Partner Dashboard. Not an OAuth provider.
- **Shopify Payments**: Admin API with payment-specific scopes.

## Implementation Notes

The `ShopifyProvider` needs significant customization over `OAuthProviderBase`:
- Dynamic URL construction per-shop
- HMAC callback validation
- `access_mode` parameter (online vs offline)
- No `redirect_uri` in token exchange

## References

- [Authorization Code Grant](https://shopify.dev/docs/apps/build/authentication-authorization/access-tokens/authorization-code-grant)
- [Access Scopes](https://shopify.dev/docs/api/usage/access-scopes)
- [Offline Access Tokens](https://shopify.dev/docs/apps/build/authentication-authorization/access-tokens/offline-access-tokens)
- [Offline Tokens Now Support Expiry and Refresh](https://shopify.dev/changelog/offline-access-tokens-now-support-expiry-and-refresh)
- [Mandatory GDPR Webhooks](https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance)
