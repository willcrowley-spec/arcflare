from sqlalchemy import UniqueConstraint

from app.models.organization import User


def test_user_clerk_id_is_unique_per_org_not_global():
    constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in User.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert constraints["uq_users_org_clerk_user"] == ("org_id", "clerk_user_id")
    assert User.__table__.c.clerk_user_id.unique is not True
