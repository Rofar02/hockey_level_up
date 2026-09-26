import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.team_event import DrillTemplate
from app.models.user import User
from app.schemas.team_event import DrillDiagram, DrillTemplateCreate, DrillTemplateRead


class DrillTemplateService:
    """A coach's own saved drills. Owner-only everywhere: someone else's
    template is a 404, same as one that doesn't exist."""

    # A busy scheme is ~15 KB, the schema's own max ~70 KB -- 200 templates
    # keep even a worst case coach well under 15 MB.
    MAX_TEMPLATES_PER_USER = 200

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_templates(self, user: User) -> list[DrillTemplateRead]:
        rows = await self._session.scalars(
            select(DrillTemplate)
            .where(DrillTemplate.user_id == user.id)
            .order_by(DrillTemplate.updated_at.desc(), DrillTemplate.id)
        )
        return [self._to_read(template) for template in rows]

    async def create_template(self, user: User, body: DrillTemplateCreate) -> DrillTemplateRead:
        count = await self._session.scalar(
            select(func.count()).select_from(DrillTemplate).where(DrillTemplate.user_id == user.id)
        )
        if (count or 0) >= self.MAX_TEMPLATES_PER_USER:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Шаблонов уже {self.MAX_TEMPLATES_PER_USER} — удали ненужные, чтобы сохранить новый.",
            )
        template = DrillTemplate(
            user_id=user.id,
            title=body.title,
            description=body.description,
            duration_minutes=body.duration_minutes,
            diagram=body.diagram.model_dump() if body.diagram is not None else None,
        )
        self._session.add(template)
        await self._session.commit()
        # created_at/updated_at are server-computed -- load them before
        # building the response (see TrainingDiaryService.save_entry).
        await self._session.refresh(template)
        return self._to_read(template)

    async def rename_template(self, user: User, template_id: uuid.UUID, title: str) -> DrillTemplateRead:
        template = await self._get_own_or_404(user, template_id)
        template.title = title
        await self._session.commit()
        await self._session.refresh(template)
        return self._to_read(template)

    async def delete_template(self, user: User, template_id: uuid.UUID) -> None:
        template = await self._get_own_or_404(user, template_id)
        await self._session.delete(template)
        await self._session.commit()

    async def _get_own_or_404(self, user: User, template_id: uuid.UUID) -> DrillTemplate:
        template = await self._session.get(DrillTemplate, template_id)
        if template is None or template.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
        return template

    @staticmethod
    def _to_read(template: DrillTemplate) -> DrillTemplateRead:
        return DrillTemplateRead(
            id=template.id,
            title=template.title,
            description=template.description,
            duration_minutes=template.duration_minutes,
            diagram=DrillDiagram.model_validate(template.diagram) if template.diagram is not None else None,
            created_at=template.created_at,
            updated_at=template.updated_at,
        )
