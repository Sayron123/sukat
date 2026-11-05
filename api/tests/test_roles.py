import uuid

import pytest
from fastapi import HTTPException

from app.auth.deps import CurrentMember, require_role
from app.auth.models import User


def _member(role: str) -> CurrentMember:
    return CurrentMember(
        user=User(email="x@example.com", full_name="X", password_hash="-"),
        member_id=uuid.uuid4(),
        store_id=uuid.uuid4(),
        role=role,
    )


@pytest.mark.parametrize(
    ("allowed", "role", "ok"),
    [
        (("manager",), "manager", True),
        (("manager",), "secretary", False),
        (("manager",), "member", False),
        (("manager", "secretary"), "secretary", True),
        (("manager", "secretary"), "member", False),
    ],
)
def test_require_role(allowed, role, ok):
    check = require_role(*allowed)
    member = _member(role)
    if ok:
        assert check(member) is member
    else:
        with pytest.raises(HTTPException) as exc:
            check(member)
        assert exc.value.status_code == 403


def test_require_role_rejects_unknown_role_names():
    with pytest.raises(ValueError):
        require_role("manger")
    with pytest.raises(ValueError):
        require_role()
