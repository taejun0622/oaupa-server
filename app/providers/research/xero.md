# Xero OAuth Integration Research

> Last updated: 2026-03-17

## OAuth Endpoints (Shared Across All Xero APIs)

| Purpose | URL |
|---|---|
| Authorization | `https://login.xero.com/identity/connect/authorize` |
| Token (exchange + refresh) | `https://identity.xero.com/connect/token` |
| Revoke | `https://identity.xero.com/connect/revocation` |
| Connections (tenant list) | `https://api.xero.com/connections` |

---

## Token Lifecycle

| Token | Lifetime | Notes |
|---|---|---|
| Access token | **30 minutes** | Very short — aggressive refresh needed |
| Refresh token | **60 days** | Rolling — resets on each use, single-use |

- Refresh token rotation is **mandatory** — each refresh invalidates the old token
- `offline_access` scope required to get a refresh token
- **Auth method:** HTTP Basic Auth (`base64(client_id:client_secret)`)

---

## Scopes by Service

### Accounting API
| Scope | Description |
|---|---|
| `accounting.transactions` | Invoices, bills, payments, credit notes |
| `accounting.transactions.read` | Read-only transactions |
| `accounting.contacts` | Contacts management |
| `accounting.contacts.read` | Read-only contacts |
| `accounting.settings` | Chart of accounts, tax rates |
| `accounting.settings.read` | Read-only settings |
| `accounting.reports.read` | Financial reports |
| `accounting.journals.read` | Journals |
| `accounting.attachments` | File attachments |
| `accounting.attachments.read` | Read-only attachments |

**New granular scopes (mandatory for apps after March 2, 2026):** `accounting.invoices`, `accounting.payments`, `accounting.banktransactions`, `accounting.manualjournals`, plus granular report scopes.

### Payroll API (Region-Specific)
| Scope | Description |
|---|---|
| `payroll.employees` | Employees (AU/NZ/UK) |
| `payroll.payruns` | Pay runs |
| `payroll.payslip` | Payslips |
| `payroll.timesheets` | Timesheets |
| `payroll.settings` | Payroll settings |
| `payroll.superfunds` | Superannuation (AU only) |
| `payroll.payitems` | Pay items (AU only) |

### Other APIs
| Scope | Description |
|---|---|
| `projects` / `projects.read` | Projects API |
| `files` / `files.read` | Files API |
| `bankfeeds` | Bank Feeds API (requires partner agreement) |
| `assets` / `assets.read` | Fixed Assets |

### Identity
| Scope | Description |
|---|---|
| `openid` | OpenID Connect |
| `profile` | User profile |
| `email` | User email |
| `offline_access` | Refresh token (essential) |

---

## Critical Quirk: Multi-Org Tenant ID

Access tokens are **user-scoped, not org-scoped**. A single token can access multiple Xero organisations.

1. After token exchange, call `GET https://api.xero.com/connections` to get tenant IDs
2. Every API call requires `Xero-Tenant-Id` header
3. `DELETE /connections/{id}` removes a single tenant (vs revoke which kills all)

This means `TokenResponse.raw_response` or `extra_data` must store tenant IDs.

---

## User Info

Decode the `id_token` JWT for user identity (`sub`, `name`, `email`). Call `/connections` for tenant list.

---

## Quirks

1. **30-minute access tokens** — very short, needs aggressive refresh
2. **Multi-tenant** — one token, many orgs, `Xero-Tenant-Id` header required
3. **PKCE supported** (S256 only), optional for server apps, required for public clients
4. **Revoke vs disconnect**: Revocation kills all connections; `DELETE /connections/{id}` removes single tenant
5. **Rate limits:** 60/min per tenant, 5,000/day per tenant, 5 concurrent requests app-wide
6. **Granular scope migration** — new apps must use granular scopes after March 2026

---

## Implementation Plan

```python
class XeroProvider(OAuthProviderBase):
    provider_id = "xero"
    # auth_url = "https://login.xero.com/identity/connect/authorize"
    # token_url = "https://identity.xero.com/connect/token"
    # revoke_url = "https://identity.xero.com/connect/revocation"
    # default_scopes = ["openid", "profile", "email", "offline_access", "accounting.transactions.read"]
```

- `exchange_code`: `exchange_code_standard(use_basic_auth=True)` + call `/connections` for tenants
- `refresh_token`: `refresh_token_standard(use_basic_auth=True)`, persist new tokens
- `revoke_token`: POST to revoke URL with token in body
- `get_account_info`: Decode `id_token` JWT
- **Custom:** `get_connections()` method for tenant list

## References

- [Xero OAuth 2.0](https://developer.xero.com/documentation/guides/oauth2/overview)
- [Xero Scopes](https://developer.xero.com/documentation/guides/oauth2/scopes)
- [Xero Connections](https://developer.xero.com/documentation/guides/oauth2/tenants)
