from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from typing import List, Optional
from database import get_db
from models import User, Branch, PresenceReport, ActivityLog, Notification
from schemas import UserCreate, UserOut, BranchOut
from auth import hash_password, get_current_user, require_admin, require_superadmin
import uuid

router = APIRouter()

# ── Statistiques globales ─────────────────────────────────────
@router.get("/stats")
async def global_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    users_count    = (await db.execute(select(func.count()).select_from(User))).scalar()
    branches_count = (await db.execute(select(func.count()).select_from(Branch))).scalar()
    reports_count  = (await db.execute(select(func.count()).select_from(PresenceReport))).scalar()
    pending_reports= (await db.execute(
        select(func.count()).select_from(PresenceReport).where(PresenceReport.status == "submitted")
    )).scalar()
    active_branches= (await db.execute(
        select(func.count()).select_from(Branch).where(Branch.status == "active")
    )).scalar()

    return {
        "total_users": users_count,
        "total_branches": branches_count,
        "active_branches": active_branches,
        "total_reports": reports_count,
        "pending_reports": pending_reports,
    }

# ── Gestion des utilisateurs ─────────────────────────────────
@router.get("/users", response_model=List[UserOut])
async def list_users(
    skip: int = 0, limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    result = await db.execute(select(User).offset(skip).limit(limit).order_by(User.created_at.desc()))
    return result.scalars().all()

@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email déjà utilisé")
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        phone=data.phone,
        role=data.role,
        language=data.language,
    )
    db.add(user)
    await db.flush()
    return user

@router.patch("/users/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    user = await db.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    user.is_active = not user.is_active
    return {"message": f"Compte {'activé' if user.is_active else 'désactivé'}", "is_active": user.is_active}

@router.patch("/users/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    new_password: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_superadmin)
):
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Mot de passe trop court (min 8 caractères)")
    user = await db.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    user.password_hash = hash_password(new_password)
    return {"message": "Mot de passe réinitialisé"}

# ── Journal d'activité ────────────────────────────────────────
@router.get("/logs")
async def activity_logs(
    skip: int = 0, limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    result = await db.execute(
        select(ActivityLog).order_by(ActivityLog.created_at.desc()).offset(skip).limit(limit)
    )
    logs = result.scalars().all()
    return [
        {
            "id": l.id,
            "user_id": str(l.user_id) if l.user_id else None,
            "action": l.action,
            "details": l.details,
            "created_at": l.created_at.isoformat()
        }
        for l in logs
    ]

# ── Notifications ─────────────────────────────────────────────
@router.get("/notifications")
async def get_notifications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
    )
    notifs = result.scalars().all()
    lang = current_user.language
    return [
        {
            "id": str(n.id),
            "title": n.title_fr if lang == "fr" else (n.title_en or n.title_fr),
            "body":  n.body_fr  if lang == "fr" else (n.body_en  or n.body_fr),
            "type": n.type,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat()
        }
        for n in notifs
    ]

@router.patch("/notifications/{notif_id}/read")
async def mark_read(
    notif_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    notif = await db.get(Notification, uuid.UUID(notif_id))
    if notif and notif.user_id == current_user.id:
        notif.is_read = True
    return {"ok": True}
