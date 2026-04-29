"""
Authentication — Supabase JWT verification.

Modern Supabase (2024+) signs JWTs with **asymmetric keys** (ES256 or RS256).
Public keys are published at the project's JWKS endpoint. We verify
signatures by fetching those public keys, caching them, and using them
to verify each incoming JWT.

For backwards compatibility with **legacy projects** still using HS256
(the older "shared JWT secret" model), we fall back to HS256 verification
when the JWT header advertises that algorithm.

Phase A supports:
- Authenticated user (valid JWT — modern or legacy)
- Anonymous user (no JWT, e.g., Chrome extension free tier)

Anonymous callers get a lower rate limit and restricted feature access.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, Header, HTTPException, status

from scalemyprints.api.middleware.jwks import JWKSClient
from scalemyprints.core.config import Settings, get_settings
from scalemyprints.core.errors import UnauthorizedError
from scalemyprints.core.logging import get_logger

logger = get_logger(__name__)


# Algorithms we accept. Order matters only for documentation.
SUPPORTED_ASYMMETRIC_ALGS = ("ES256", "RS256")
SUPPORTED_SYMMETRIC_ALGS = ("HS256",)


# -----------------------------------------------------------------------------
# CurrentUser
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """
    Represents the caller of a request.

    `is_anonymous` differentiates unauthenticated public users (extension)
    from logged-in dashboard users.
    """

    id: str
    email: str | None
    is_anonymous: bool

    @classmethod
    def anonymous(cls) -> "CurrentUser":
        return cls(id="anonymous", email=None, is_anonymous=True)


# -----------------------------------------------------------------------------
# JWKS client (process-wide cached singleton)
# -----------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _get_jwks_client(jwks_url: str) -> JWKSClient:
    """Process-wide JWKS client. Cached so we share key cache across requests."""
    return JWKSClient(jwks_url=jwks_url)


def _supabase_jwks_url(settings: Settings) -> str | None:
    """Derive the JWKS URL from SUPABASE_URL.

    Format: <SUPABASE_URL>/auth/v1/.well-known/jwks.json
    """
    base = settings.supabase_url.rstrip("/")
    if not base:
        return None
    return f"{base}/auth/v1/.well-known/jwks.json"


# -----------------------------------------------------------------------------
# JWT verification
# -----------------------------------------------------------------------------


async def _verify_jwt(token: str, settings: Settings) -> dict[str, Any]:
    """
    Verify a JWT and return its claims.

    Strategy:
    1. Inspect the JWT header for `alg` and `kid`
    2. If alg is asymmetric (ES256/RS256), fetch public key via JWKS
    3. If alg is symmetric (HS256), use legacy SUPABASE_JWT_SECRET
    4. Anything else → reject
    """
    try:
        header = jwt.get_unverified_header(token)
    except jwt.DecodeError as e:
        raise UnauthorizedError("Malformed JWT header") from e

    alg = header.get("alg")
    if not alg:
        raise UnauthorizedError("JWT missing 'alg' header")

    common_options = {
        "require": ["sub", "exp"],
        "verify_aud": True,
    }

    # ---- Asymmetric path (modern Supabase) ----
    if alg in SUPPORTED_ASYMMETRIC_ALGS:
        kid = header.get("kid")
        if not kid:
            raise UnauthorizedError("Asymmetric JWT missing 'kid' header")

        jwks_url = _supabase_jwks_url(settings)
        if not jwks_url:
            raise UnauthorizedError("SUPABASE_URL not configured for JWKS")

        client = _get_jwks_client(jwks_url)
        try:
            signing_key = await client.get_signing_key(kid)
        except KeyError as e:
            logger.warning("jwt_unknown_kid", kid=kid, alg=alg)
            raise UnauthorizedError(f"Unknown signing key: {kid}") from e
        except Exception as e:  # noqa: BLE001
            logger.warning("jwks_fetch_failed", error=str(e))
            raise UnauthorizedError("Could not fetch signing keys") from e

        try:
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=[alg],
                audience="authenticated",
                options=common_options,
            )
        except jwt.ExpiredSignatureError as e:
            raise UnauthorizedError("Token expired") from e
        except jwt.InvalidTokenError as e:
            logger.warning("jwt_invalid_asymmetric", alg=alg, error=str(e))
            raise UnauthorizedError("Invalid token") from e

    # ---- Symmetric path (legacy HS256) ----
    if alg in SUPPORTED_SYMMETRIC_ALGS:
        secret = settings.supabase_jwt_secret.get_secret_value()
        if not secret:
            logger.error("supabase_jwt_secret_not_configured_for_hs256")
            raise UnauthorizedError("Auth not configured for HS256")

        try:
            return jwt.decode(
                token,
                secret,
                algorithms=list(SUPPORTED_SYMMETRIC_ALGS),
                audience="authenticated",
                options=common_options,
            )
        except jwt.ExpiredSignatureError as e:
            raise UnauthorizedError("Token expired") from e
        except jwt.InvalidTokenError as e:
            logger.warning("jwt_invalid_symmetric", error=str(e))
            raise UnauthorizedError("Invalid token") from e

    # ---- Unsupported algorithm ----
    logger.warning("jwt_unsupported_alg", alg=alg)
    raise UnauthorizedError(f"Algorithm not allowed: {alg}")


# -----------------------------------------------------------------------------
# FastAPI dependencies
# -----------------------------------------------------------------------------


def _user_from_claims(claims: dict[str, Any]) -> CurrentUser:
    user_id = claims.get("sub")
    if not user_id:
        raise UnauthorizedError("Token missing subject")
    return CurrentUser(
        id=str(user_id),
        email=claims.get("email"),
        is_anonymous=False,
    )


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
) -> CurrentUser:
    """
    FastAPI dependency: returns CurrentUser or raises 401.

    Use with `user: CurrentUser = Depends(get_current_user)` on routes
    that REQUIRE authentication.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must use Bearer scheme",
        )

    token = authorization[7:].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty bearer token",
        )

    try:
        claims = await _verify_jwt(token, settings)
    except UnauthorizedError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=e.message
        ) from e

    return _user_from_claims(claims)


async def get_current_user_or_anonymous(
    authorization: Annotated[str | None, Header()] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
) -> CurrentUser:
    """
    FastAPI dependency: returns a CurrentUser, falling back to anonymous.

    Use on endpoints that ALLOW unauthenticated access (e.g., Chrome
    extension free-tier trademark searches).
    """
    if not authorization:
        return CurrentUser.anonymous()

    try:
        return await get_current_user(authorization=authorization, settings=settings)
    except HTTPException:
        return CurrentUser.anonymous()
