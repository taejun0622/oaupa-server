# Spotify OAuth Integration Research

> Last updated: 2026-03-17

## 1. OAuth Endpoints (Shared Across All Services)

Spotify uses a **single OAuth system** for all APIs. Scopes control which API surfaces the token can access.

| Endpoint | URL |
|---|---|
| Authorization | `https://accounts.spotify.com/authorize` |
| Token | `https://accounts.spotify.com/api/token` |
| Revoke | **Not available** — users revoke via spotify.com/account/apps |
| User Info | `https://api.spotify.com/v1/me` |

---

## 2. Token Lifecycle

| Property | Value |
|---|---|
| Access token expiry | **1 hour** (3600s) |
| Refresh token expiry | **Never** (until user revokes) |
| Refresh token rotation | **No** — same refresh token reused indefinitely |
| Token type | Bearer |

Refresh response does NOT return a new `refresh_token`. The `refresh_token_standard` helper handles this via `body.get("refresh_token", refresh_token)` fallback.

**Auth method:** HTTP Basic Auth preferred (`Authorization: Basic base64(client_id:client_secret)`). Body params also work.

---

## 3. Available Scopes

### User Library & Profile
| Scope | Description |
|---|---|
| `user-read-private` | Subscription details, country |
| `user-read-email` | Email address |
| `user-library-read` | Saved tracks, albums, shows |
| `user-library-modify` | Add/remove from library |
| `user-top-read` | Top artists and tracks |
| `user-read-recently-played` | Recently played tracks |
| `user-follow-read` / `user-follow-modify` | Follow/unfollow artists/users |

### Playlists
| Scope | Description |
|---|---|
| `playlist-read-private` | Private playlists |
| `playlist-read-collaborative` | Collaborative playlists |
| `playlist-modify-public` / `playlist-modify-private` | Create/edit playlists |

### Player API (Playback Control)
| Scope | Description |
|---|---|
| `user-read-playback-state` | Current playback state, devices |
| `user-modify-playback-state` | Play, pause, skip, seek, volume, transfer |
| `user-read-currently-playing` | Currently playing track |

### Other
| Scope | Description |
|---|---|
| `ugc-image-upload` | Upload playlist cover images |
| `streaming` | Web Playback SDK |
| `app-remote-control` | iOS/Android SDK |

---

## 4. User Info Endpoint

```
GET https://api.spotify.com/v1/me
```

Required scope: `user-read-private` (+ `user-read-email` for email)

**Mapping:** `account_id` = `id`, `email` = `email`, `display_name` = `display_name`

---

## 5. Quirks & Implementation Notes

1. **No revocation endpoint** — `revoke_token()` returns `False`
2. **PKCE supported** — S256, handled by existing helpers
3. **Basic Auth preferred** — use `use_basic_auth=True`
4. **`show_dialog` param** — force re-consent via `extra_auth_params`
5. **Strict scope enforcement** — 403 with `"reason": "MISSING_SCOPE"` for missing scopes
6. **Space-separated scopes** — standard behavior

### Provider Config

```python
SpotifyProvider(
    client_id=settings.spotify_client_id,
    client_secret=settings.spotify_client_secret,
    auth_url="https://accounts.spotify.com/authorize",
    token_url="https://accounts.spotify.com/api/token",
    revoke_url=None,
    default_scopes=["user-read-private", "user-read-email"],
)
```

### Method Mapping

| Method | Notes |
|---|---|
| `get_authorization_url` | `build_authorization_url` with default separator |
| `exchange_code` | `exchange_code_standard(use_basic_auth=True)` |
| `refresh_token` | `refresh_token_standard(use_basic_auth=True)` |
| `revoke_token` | Return `False` |
| `get_account_info` | `GET /v1/me` |

**Complexity: Low.** Well-aligned with existing helpers.
