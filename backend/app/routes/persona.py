from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.persona import PersonaCreate, PersonaUpdate, PersonaRead
from app.services.persona_service import PersonaService

router = APIRouter(prefix="/api/persona", tags=["persona"])


@router.get("", response_model=list[PersonaRead])
async def list_personas(db: AsyncSession = Depends(get_db)):
    svc = PersonaService(db)
    return await svc.list_all()


@router.get("/active", response_model=PersonaRead)
async def get_active_persona(db: AsyncSession = Depends(get_db)):
    svc = PersonaService(db)
    persona = await svc.get_active()
    if not persona:
        persona = await svc.seed_default()
    return persona


@router.get("/{persona_id}", response_model=PersonaRead)
async def get_persona(persona_id: str, db: AsyncSession = Depends(get_db)):
    svc = PersonaService(db)
    persona = await svc.get_by_id(persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    return persona


@router.post("", response_model=PersonaRead)
async def create_persona(data: PersonaCreate, db: AsyncSession = Depends(get_db)):
    svc = PersonaService(db)
    existing = await svc.get_by_slug(data.slug)
    if existing:
        raise HTTPException(status_code=400, detail="Slug already exists")
    return await svc.create(data.model_dump())


@router.patch("/{persona_id}", response_model=PersonaRead)
async def update_persona(persona_id: str, data: PersonaUpdate, db: AsyncSession = Depends(get_db)):
    svc = PersonaService(db)
    persona = await svc.get_by_id(persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    return await svc.update(persona, data.model_dump(exclude_none=True))


@router.put("/{persona_id}/activate", response_model=PersonaRead)
async def activate_persona(persona_id: str, db: AsyncSession = Depends(get_db)):
    svc = PersonaService(db)
    persona = await svc.get_by_id(persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    return await svc.set_active(persona)
