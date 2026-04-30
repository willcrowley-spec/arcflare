from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentUser, get_current_user
from app.models.organization import Organization, User

DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


async def get_current_org(
    db: DbSession,
    user: CurrentUserDep,
) -> Organization:
    if not user.org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization context required",
        )
    result = await db.execute(
        select(Organization).where(Organization.clerk_org_id == user.org_id)
    )
    org = result.scalar_one_or_none()
    if org is None:
        org = Organization(
            clerk_org_id=user.org_id,
            name=user.org_name or user.org_id,
        )
        db.add(org)
        await db.commit()
        await db.refresh(org)
    elif user.org_name and org.name == org.clerk_org_id:
        org.name = user.org_name
        await db.commit()
        await db.refresh(org)
    return org


async def get_or_create_org_user(
    db: AsyncSession,
    org: Organization,
    current_user: CurrentUser,
) -> User:
    result = await db.execute(
        select(User).where(
            User.org_id == org.id,
            User.clerk_user_id == current_user.clerk_user_id,
        )
    )
    user = result.scalar_one_or_none()
    if user is not None:
        if current_user.email and user.email != current_user.email:
            user.email = current_user.email
            await db.commit()
            await db.refresh(user)
        return user

    user = User(
        org_id=org.id,
        clerk_user_id=current_user.clerk_user_id,
        email=current_user.email,
        display_name=None,
        role="member",
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
        return user
    except IntegrityError as exc:
        await db.rollback()
        retry = await db.execute(
            select(User).where(
                User.org_id == org.id,
                User.clerk_user_id == current_user.clerk_user_id,
            )
        )
        user = retry.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not resolve user record",
            ) from exc
        return user


CurrentOrg = Annotated[Organization, Depends(get_current_org)]
