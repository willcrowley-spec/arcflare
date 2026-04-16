from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentUser, get_current_user
from app.models.organization import Organization

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
            name=user.org_id,
        )
        db.add(org)
        await db.commit()
        await db.refresh(org)
    return org


CurrentOrg = Annotated[Organization, Depends(get_current_org)]
