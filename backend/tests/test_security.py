"""Tests for bcrypt password hashing and JWT tenant claims."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

from app.core.security import (
    AuthenticationError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_and_verify() -> None:
    hashed = hash_password("StrongP@ssword123!")
    assert hashed != "StrongP@ssword123!"
    assert verify_password("StrongP@ssword123!", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_jwt_roundtrip_preserves_tenant_and_workspace() -> None:
    user_id = uuid4()
    tenant_id = uuid4()
    workspace_id = uuid4()

    token = create_access_token(
        user_id=user_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        role="admin",
    )
    payload = decode_access_token(token)
    assert payload.sub == user_id
    assert payload.tenant_id == tenant_id
    assert payload.workspace_id == workspace_id
    assert payload.role == "admin"


def test_expired_jwt_is_rejected() -> None:
    token = create_access_token(
        user_id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        expires_delta=timedelta(seconds=-5),
    )
    with pytest.raises(AuthenticationError):
        decode_access_token(token)


def test_tampered_jwt_is_rejected() -> None:
    token = create_access_token(
        user_id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=uuid4(),
    )
    with pytest.raises(AuthenticationError):
        decode_access_token(token + "corrupted")
