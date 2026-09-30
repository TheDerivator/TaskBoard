"""External identity providers (SSO). None are configured by default: built-in accounts only.

Concrete providers (Entra ID via OIDC, trusted reverse-proxy header, Windows sign-in through
Negotiate) are registered in `IdentityProviders.from_settings`.
"""

from taskboard.identity.providers.base import (
    AmbientIdentityProvider,
    ExternalIdentity,
    IdentityProviders,
    NegotiateIdentityProvider,
    NegotiateStep,
    RedirectIdentityProvider,
)

__all__ = [
    "AmbientIdentityProvider",
    "ExternalIdentity",
    "IdentityProviders",
    "NegotiateIdentityProvider",
    "NegotiateStep",
    "RedirectIdentityProvider",
]
