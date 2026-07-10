from __future__ import annotations

import uuid

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_profile import AgentProfile
from app.schemas.agent_profile import AgentProfileCreate, AgentProfileUpdate


async def list_profiles(session: AsyncSession, user_id: uuid.UUID) -> list[AgentProfile]:
    result = await session.execute(
        select(AgentProfile)
        .where(AgentProfile.user_id == user_id)
        .order_by(AgentProfile.is_default.desc(), AgentProfile.name.asc())
    )
    return result.scalars().all()


async def get_profile(session: AsyncSession, user_id: uuid.UUID, profile_id: uuid.UUID) -> AgentProfile | None:
    result = await session.execute(
        select(AgentProfile).where(
            and_(
                AgentProfile.id == profile_id,
                AgentProfile.user_id == user_id,
            )
        )
    )
    return result.scalar_one_or_none()


async def get_default_profile(session: AsyncSession, user_id: uuid.UUID) -> AgentProfile | None:
    result = await session.execute(
        select(AgentProfile).where(
            and_(
                AgentProfile.user_id == user_id,
                AgentProfile.is_default.is_(True),
            )
        )
    )
    return result.scalar_one_or_none()


async def create_profile(session: AsyncSession, user_id: uuid.UUID, body: AgentProfileCreate) -> AgentProfile:
    profile = AgentProfile(
        user_id=user_id,
        name=body.name.strip(),
        persona=(body.persona.strip() if body.persona else None),
        config=body.config.model_dump(exclude_none=True),
        is_default=body.is_default,
    )
    session.add(profile)
    await session.flush()

    if profile.is_default:
        await _clear_other_defaults(session, user_id, profile.id)

    await session.refresh(profile)
    return profile


async def update_profile(session: AsyncSession, profile: AgentProfile, body: AgentProfileUpdate) -> AgentProfile:
    if body.name is not None:
        profile.name = body.name.strip()
    if body.persona is not None:
        profile.persona = body.persona.strip() if body.persona else None
    if body.config is not None:
        profile.config = body.config.model_dump(exclude_none=True)
    if body.is_default is not None:
        profile.is_default = body.is_default

    await session.flush()
    if profile.is_default:
        await _clear_other_defaults(session, profile.user_id, profile.id)

    await session.refresh(profile)
    return profile


async def delete_profile(session: AsyncSession, profile: AgentProfile) -> None:
    await session.delete(profile)
    await session.flush()


def profile_overrides(profile: AgentProfile | None) -> dict:
    if profile is None:
        return {}
    cfg = dict(profile.config or {})
    payload = {
        "model": cfg.get("model"),
        "reasoning_effort": cfg.get("reasoning_effort"),
        "max_iterations": cfg.get("max_iterations"),
        "search_top_k": cfg.get("search_top_k"),
        "search_distance_threshold": cfg.get("search_distance_threshold"),
        "persona": profile.persona,
    }
    return {key: value for key, value in payload.items() if value is not None and value != ""}


async def _clear_other_defaults(session: AsyncSession, user_id: uuid.UUID, keep_id: uuid.UUID) -> None:
    result = await session.execute(
        select(AgentProfile).where(
            and_(
                AgentProfile.user_id == user_id,
                AgentProfile.is_default.is_(True),
                AgentProfile.id != keep_id,
            )
        )
    )
    for profile in result.scalars().all():
        profile.is_default = False
    await session.flush()
