# X (Twitter) OAuth 2.0 Integration Research

> Last updated: 2026-03-17

## 1. OAuth 2.0 Core (Authorization Code Flow with PKCE)

### Endpoints

| Purpose | URL |
|---|---|
| Authorization | `https://twitter.com/i/oauth2/authorize` |
| Token | `https://api.twitter.com/2/oauth2/token` |
| Revoke | `https://api.twitter.com/2/oauth2/revoke` |
| User Info | `https://api.twitter.com/2/users/me` |

### PKCE Requirement

PKCE is **mandatory** for all OAuth 2.0 flows — both confidential and public clients. `code_challenge_method` must be `S256`.

### Confidential vs Public Clients

| Aspect | Confidential | Public |
|---|---|---|
| Token endpoint auth | HTTP Basic (`client_id:client_secret` base64) | `client_id` in body |
| Refresh tokens | With `offline.access` scope | With `offline.access` scope |
| PKCE | Required | Required |

**Important**: Confidential clients must use **HTTP Basic Auth** on the token endpoint, NOT body parameters.

### Token Lifecycle

| Token Type | Lifetime | Notes |
|---|---|---|
| Access token | **2 hours** | Must implement proactive refresh |
| Refresh token | **6 months** from last use | Rolling: each refresh returns a new refresh token |

**Critical**: Each refresh returns a **new** refresh token. Old one is invalidated immediately. Must persist new refresh token on every refresh.

---

## 2. Available Scopes (20 total)

| Scope | Description |
|---|---|
| `tweet.read` | Read tweets, timelines, lists |
| `tweet.write` | Create and delete tweets |
| `tweet.moderate.write` | Hide/unhide replies |
| `users.read` | Read user profile info |
| `follows.read` | Read follows/following lists |
| `follows.write` | Follow/unfollow users |
| `offline.access` | Obtain a refresh token (essential for oaupa) |
| `space.read` | Read Spaces data |
| `mute.read` / `mute.write` | Read/manage muted accounts |
| `like.read` / `like.write` | Read/manage liked tweets |
| `list.read` / `list.write` | Read/manage lists |
| `block.read` / `block.write` | Read/manage blocked accounts |
| `bookmark.read` / `bookmark.write` | Read/manage bookmarks |
| `dm.read` / `dm.write` | Read/send direct messages |

---

## 3. Services Breakdown

### 3.1 Tweets API
- **Read:** `GET /2/tweets/{id}`, `GET /2/users/{id}/tweets` — scopes: `tweet.read`, `users.read`
- **Write:** `POST /2/tweets`, `DELETE /2/tweets/{id}` — scopes: `tweet.read`, `tweet.write`, `users.read`
- Media upload uses **v1.1 endpoint** (`upload.twitter.com/1.1/media/upload.json`)

### 3.2 Users API
- **Lookup:** `GET /2/users/me`, `GET /2/users/{id}` — scope: `users.read`
- **Follows:** `POST/DELETE /2/users/{id}/following` — scopes: `follows.write`, `users.read`
- **Blocks/Mutes:** respective read/write scopes + `users.read`

### 3.3 Spaces API
- **Read-only** via API. Scopes: `space.read`, `users.read`
- Spaces cannot be created programmatically

### 3.4 Direct Messages API
- **User context only** (no app-only auth)
- Rate limit: 200/15min per user, 1000/24hr per user

### 3.5 Twitter Ads API
- **OAuth 1.0a ONLY** — does NOT support OAuth 2.0
- Requires separate application approval
- Would need separate provider implementation

---

## 4. User Info Endpoint

```
GET https://api.twitter.com/2/users/me
  ?user.fields=id,name,username,profile_image_url,description
```

**Mapping:** `account_id` = `data.id`, `email` = **Not available** (v2 API), `display_name` = `data.name`

---

## 5. Implementation Notes

1. **PKCE mandatory** — `code_challenge` in auth URL and `code_verifier` in token exchange are required
2. **Basic Auth for token endpoint** — use `use_basic_auth=True` in helpers
3. **Rolling refresh tokens** — persist new refresh_token on every refresh
4. **No email** — X does not expose email via v2 API
5. **2-hour expiry** — proactively refresh at ~90 minutes

### Provider Config

```python
{
    "provider_id": "twitter",
    "auth_url": "https://twitter.com/i/oauth2/authorize",
    "token_url": "https://api.twitter.com/2/oauth2/token",
    "revoke_url": "https://api.twitter.com/2/oauth2/revoke",
    "default_scopes": ["tweet.read", "users.read", "offline.access"],
}
```

### API Access Tiers

| Tier | Cost | Notes |
|---|---|---|
| Free | $0 | 1,500 tweets/month write only |
| Basic | $100/month | 3,000 tweets/month |
| Pro | $5,000/month | 1M tweets/month read |
| Enterprise | Custom | Highest limits |
