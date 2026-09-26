"""ID token verification against signature-algorithm attacks (none, HMAC with the public key)."""

import base64
import hashlib
import hmac
import json
import time

import pytest
from cryptography.hazmat.primitives import serialization

from taskboard.identity.providers.oidc import OidcError
from tests.fake_idp import CLIENT_ID, ISSUER, FakeIdentityProvider, fake_oidc_provider


def _b64(data: dict[str, object]) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def _claims() -> dict[str, object]:
    now = int(time.time())
    return {"iss": ISSUER, "aud": CLIENT_ID, "iat": now, "exp": now + 60, "nonce": "n", "oid": "x"}


def test_a_valid_token_passes() -> None:
    idp = FakeIdentityProvider()
    claims = fake_oidc_provider(idp).verify(idp.sign(_claims()), nonce="n")
    assert claims["oid"] == "x"


def test_unsigned_tokens_are_refused() -> None:
    idp = FakeIdentityProvider()
    token = f"{_b64({'alg': 'none', 'kid': idp.kid})}.{_b64(_claims())}."
    with pytest.raises(OidcError, match="unsupported"):
        fake_oidc_provider(idp).verify(token, nonce="n")


def test_hmac_signed_with_the_public_key_is_refused() -> None:
    """The classic key-confusion attack: HS256 using the published RSA key as the secret."""
    idp = FakeIdentityProvider()
    public_pem = idp.key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    # Forged by hand: PyJWT itself refuses to produce such a token.
    signing_input = f"{_b64({'alg': 'HS256', 'kid': idp.kid})}.{_b64(_claims())}"
    signature = hmac.new(public_pem, signing_input.encode(), hashlib.sha256).digest()
    token = f"{signing_input}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"
    with pytest.raises(OidcError, match="unsupported"):
        fake_oidc_provider(idp).verify(token, nonce="n")


def test_identity_needs_a_subject_and_takes_the_first_real_email() -> None:
    provider = fake_oidc_provider(FakeIdentityProvider())
    identity = provider.identity_from(
        {"oid": "o-1", "email": None, "preferred_username": "jan@corp.example", "groups": ["g"]}
    )
    assert (identity.subject, identity.email, identity.groups) == (
        "o-1",
        "jan@corp.example",
        ("g",),
    )
    with pytest.raises(OidcError, match="'oid'"):
        provider.identity_from({"sub": "only-sub"})
