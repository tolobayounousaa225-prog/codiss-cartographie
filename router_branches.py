from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from database import get_db
from models import Branch, BranchUser, User, Notification
from schemas import BranchCreate, BranchUpdate, BranchOut
from auth import get_current_user, require_admin
import uuid

router = APIRouter()

@router.get("/", response_model=List[BranchOut])
async def list_branches(
    status: Optional[str] = None,
    region_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    q = select(Branch)
    if status:
        q = q.where(Branch.status == status)
    if region_id:
        q = q.where(Branch.region_id == region_id)
    q = q.offset(skip).limit(limit).order_by(Branch.name)
    result = await db.execute(q)
    return result.scalars().all()

@router.get("/my", response_model=BranchOut)
async def my_branch(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if current_user.role not in ("branch",):
        raise HTTPException(status_code=403, detail="Réservé aux comptes de branche")
    bu = await db.execute(select(BranchUser).where(BranchUser.user_id == current_user.id))
    bu_row = bu.scalar_one_or_none()
    if not bu_row:
        raise HTTPException(status_code=404, detail="Aucune branche associée")
    branch = await db.get(Branch, bu_row.branch_id)
    return branch

@router.get("/{branch_id}", response_model=BranchOut)
async def get_branch(branch_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    branch = await db.get(Branch, uuid.UUID(branch_id))
    if not branch:
        raise HTTPException(status_code=404, detail="Branche introuvable")
    return branch

@router.post("/", response_model=BranchOut, status_code=201)
async def create_branch(
    data: BranchCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    existing = await db.execute(select(Branch).where(Branch.code == data.code))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Code branche déjà utilisé")
    branch = Branch(**data.model_dump())
    db.add(branch)
    await db.flush()
    return branch

@router.patch("/{branch_id}", response_model=BranchOut)
async def update_branch(
    branch_id: str,
    data: BranchUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    branch = await db.get(Branch, uuid.UUID(branch_id))
    if not branch:
        raise HTTPException(status_code=404, detail="Branche introuvable")

    # Seul admin ou le propre utilisateur de la branche peut modifier
    if current_user.role not in ("superadmin", "admin"):
        bu = await db.execute(
            select(BranchUser).where(
                BranchUser.user_id == current_user.id,
                BranchUser.branch_id == branch.id
            )
        )
        if not bu.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Accès refusé")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(branch, field, value)
    return branch

@router.post("/{branch_id}/verify")
async def verify_branch(
    branch_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    from datetime import datetime
    branch = await db.get(Branch, uuid.UUID(branch_id))
    if not branch:
        raise HTTPException(status_code=404, detail="Branche introuvable")
    branch.is_verified = True
    branch.verified_at = datetime.utcnow()
    branch.verified_by = current_user.id
    branch.status = "active"
    return {"message": f"Branche {branch.name} vérifiée et activée"}

@router.post("/{branch_id}/assign-user")
async def assign_user_to_branch(
    branch_id: str,
    user_id: str,
    role: str = "secretary",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    branch = await db.get(Branch, uuid.UUID(branch_id))
    user = await db.get(User, uuid.UUID(user_id))
    if not branch or not user:
        raise HTTPException(status_code=404, detail="Branche ou utilisateur introuvable")
    bu = BranchUser(user_id=user.id, branch_id=branch.id, role=role)
    db.add(bu)
    return {"message": f"{user.full_name} assigné à {branch.name} en tant que {role}"}
