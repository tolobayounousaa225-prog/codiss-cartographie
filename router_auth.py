from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime, timedelta
from database import get_db
from models import User, BranchUser, ActivityLog
from schemas import LoginRequest, TokenResponse, UserCreate, UserOut
from auth import hash_password, verify_password, create_access_token, get_current_user
from config import settings

router = APIRouter()

@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou mot de passe incorrect")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Compte désactivé")

    # Mettre à jour last_login
    await db.execute(update(User).where(User.id == user.id).values(last_login=datetime.utcnow()))

    # Chercher la branche associée (si rôle branch)
    branch_id = None
    if user.role == "branch":
        bu = await db.execute(select(BranchUser).where(BranchUser.user_id == user.id))
        bu_row = bu.scalar_one_or_none()
        if bu_row:
            branch_id = str(bu_row.branch_id)

    # Log d'activité
    log = ActivityLog(
        user_id=user.id,
        action="login",
        details={"email": user.email},
        ip_address=request.client.host if request.client else None
    )
    db.add(log)

    token = create_access_token({"sub": str(user.id), "role": user.role})
    return TokenResponse(
        access_token=token,
        user_id=str(user.id),
        full_name=user.full_name,
        role=user.role,
        language=user.language,
        branch_id=branch_id
    )

@router.post("/register", response_model=UserOut, status_code=201)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
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

@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user

@router.patch("/me/language")
async def update_language(
    language: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if language not in ("fr", "en"):
        raise HTTPException(status_code=400, detail="Langue non supportée")
    await db.execute(update(User).where(User.id == current_user.id).values(language=language))
    return {"message": "Langue mise à jour"}
