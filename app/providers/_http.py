"""Shared HTTP utilities for OAuth providers."""

from urllib.parse import urlencode

import httpx

from app.providers.base import TokenResponse


async def exchange_code_standard(
    token_url: str,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str | None = None,
    use_basic_auth: bool = False,
) -> TokenResponse:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }
    if code_verifier:
        data["code_verifier"] = code_verifier

    if use_basic_auth:
        auth = httpx.BasicAuth(client_id, client_secret)
    else:
        data["client_id"] = client_id
        data["client_secret"] = client_secret
        auth = None

    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, data=data, auth=auth)
        resp.raise_for_status()
        body = resp.json()

    return TokenResponse(
        access_token=body["access_token"],
        refresh_token=body.get("refresh_token"),
        token_type=body.get("token_type", "Bearer"),
        expires_in=body.get("expires_in"),
        scope=body.get("scope"),
        raw_response=body,
    )


async def refresh_token_standard(
    token_url: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    use_basic_auth: bool = False,
) -> TokenResponse:
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }

    if use_basic_auth:
        auth = httpx.BasicAuth(client_id, client_secret)
    else:
        data["client_id"] = client_id
        data["client_secret"] = client_secret
        auth = None

    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, data=data, auth=auth)
        resp.raise_for_status()
        body = resp.json()

    return TokenResponse(
        access_token=body["access_token"],
        refresh_token=body.get("refresh_token", refresh_token),
        token_type=body.get("token_type", "Bearer"),
        expires_in=body.get("expires_in"),
        scope=body.get("scope"),
        raw_response=body,
    )


def build_authorization_url(
    auth_url: str,
    client_id: str,
    redirect_uri: str,
    state: str,
    scopes: list[str],
    response_type: str = "code",
    code_challenge: str | None = None,
    extra_params: dict | None = None,
    scope_separator: str = " ",
) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "response_type": response_type,
        "scope": scope_separator.join(scopes),
    }
    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"
    if extra_params:
        params.update(extra_params)
    return f"{auth_url}?{urlencode(params)}"
