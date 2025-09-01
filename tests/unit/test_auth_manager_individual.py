from __future__ import annotations

from tests.utils.auth_manager import AuthTestManager


def test_create_individual_user_has_no_org_id():
    auth = AuthTestManager()
    user = auth.create_individual_user(user_id="individual_åäö")
    assert user.organization_id is None


def test_individual_jwt_has_no_org_claim():
    auth = AuthTestManager()
    user = auth.create_individual_user(user_id="indiv_åsa")
    token = auth.generate_jwt_token(user)
    payload = auth.validate_jwt_token(token)
    assert payload is not None
    assert payload.get("sub") == user.user_id
    assert "org_id" not in payload
