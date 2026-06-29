from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from database import get_db
from models import PresenceReport, ReportFormAnswer, Branch, BranchUser, User, Notification
from schemas import ReportCreate, ReportOut
from auth import get_current_user, require_admin
import uuid

router = APIRouter()

@router.post("/", response_model=ReportOut, status_code=201)
async def submit_report(
    data: ReportCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Trouver la branche de l'utilisateur
    if current_user.role == "branch":
        bu = await db.execute(select(BranchUser).where(BranchUser.user_id == current_user.id))
        bu_row = bu.scalar_one_or_none()
        if not bu_row:
            raise HTTPException(status_code=403, detail="Aucune branche associée à cet utilisateur")
        branch_id = bu_row.branch_id
    else:
        raise HTTPException(status_code=403, detail="Seules les branches peuvent soumettre des rapports")

    # Créer le rapport
    report = PresenceReport(
        branch_id=branch_id,
        submitted_by=current_user.id,
        latitude=data.latitude,
        longitude=data.longitude,
        location_accuracy=data.location_accuracy,
        location_address=data.location_address,
        report_type=data.report_type,
        title=data.title,
        description=data.description,
        activity_count=data.activity_count,
        period_start=data.period_start,
        period_end=data.period_end,
    )
    db.add(report)
    await db.flush()

    # Sauvegarder les réponses au formulaire
    for ans in data.form_answers:
        fa = ReportFormAnswer(report_id=report.id, question=ans.question, answer=ans.answer)
        db.add(fa)

    # Mettre à jour la localisation de la branche si non renseignée
    branch = await db.get(Branch, branch_id)
    if branch and (branch.latitude is None or branch.longitude is None):
        branch.latitude = data.latitude
        branch.longitude = data.longitude

    # Notifier les admins
    notif = Notification(
        user_id=current_user.id,   # sera redirigé aux admins en prod
        title_fr=f"Nouveau rapport de {branch.name if branch else 'une branche'}",
        title_en=f"New report from {branch.name if branch else 'a branch'}",
        body_fr=f"Type: {data.report_type} — {data.title}",
        body_en=f"Type: {data.report_type} — {data.title}",
        type="report",
        link=f"/reports/{report.id}"
    )
    db.add(notif)
    return report

@router.get("/", response_model=List[ReportOut])
async def list_reports(
    branch_id: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    q = select(PresenceReport)

    # Les branches ne voient que leurs propres rapports
    if current_user.role == "branch":
        bu = await db.execute(select(BranchUser).where(BranchUser.user_id == current_user.id))
        bu_row = bu.scalar_one_or_none()
        if bu_row:
            q = q.where(PresenceReport.branch_id == bu_row.branch_id)
    elif branch_id:
        q = q.where(PresenceReport.branch_id == uuid.UUID(branch_id))

    if status:
        q = q.where(PresenceReport.status == status)

    q = q.offset(skip).limit(limit).order_by(PresenceReport.created_at.desc())
    result = await db.execute(q)
    return result.scalars().all()

@router.get("/{report_id}", response_model=ReportOut)
async def get_report(report_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    report = await db.get(PresenceReport, uuid.UUID(report_id))
    if not report:
        raise HTTPException(status_code=404, detail="Rapport introuvable")
    return report

@router.patch("/{report_id}/review")
async def review_report(
    report_id: str,
    status: str,
    notes: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    from datetime import datetime
    if status not in ("approved", "rejected", "reviewed"):
        raise HTTPException(status_code=400, detail="Statut invalide")
    report = await db.get(PresenceReport, uuid.UUID(report_id))
    if not report:
        raise HTTPException(status_code=404, detail="Rapport introuvable")
    report.status = status
    report.reviewed_by = current_user.id
    report.reviewed_at = datetime.utcnow()
    report.review_notes = notes

    # Si approuvé, activer la branche
    if status == "approved":
        branch = await db.get(Branch, report.branch_id)
        if branch and branch.status == "pending":
            branch.status = "active"

    return {"message": f"Rapport marqué comme {status}"}
