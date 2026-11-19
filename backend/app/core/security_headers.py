"""Security headers middleware for financial-grade HTTP response hardening."""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.config import get_settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject standard financial-grade security headers on all HTTP responses.

    Enforces:
    - Strict-Transport-Security (HSTS)
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY (clickjacking protection)
    - Referrer-Policy: strict-origin-when-cross-origin
    - X-XSS-Protection: 0
    - Content-Security-Policy (CSP) restricting external injection and frames
    - Permissions-Policy restricting sensitive browser features
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        settings = get_settings()

        if settings.security_headers_enabled:
            # Prevent MIME type sniffing
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            # Prevent clickjacking
            response.headers.setdefault("X-Frame-Options", "DENY")
            # Referrer privacy
            response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
            # Disable legacy XSS filter that could introduce vulnerabilities
            response.headers.setdefault("X-XSS-Protection", "0")
            # HTTP Strict Transport Security
            response.headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={settings.hsts_max_age_seconds}; includeSubDomains; preload",
            )
            # Safe Content Security Policy allowing OpenAPI docs assets from CDN
            # while forbidding frame ancestors
            csp_directives = [
                "default-src 'self'",
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
                "img-src 'self' data: https://fastapi.tiangolo.com",
                "frame-ancestors 'none'",
            ]
            response.headers.setdefault("Content-Security-Policy", "; ".join(csp_directives))
            # Restrict hardware API access
            response.headers.setdefault(
                "Permissions-Policy",
                "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
                "magnetometer=(), microphone=(), payment=(), usb=()",
            )

        return response
