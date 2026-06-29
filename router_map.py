from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, distinct
from typing import List
from database import get_db
from models import Branch, Region, PresenceReport, User
from schemas import MapStatsOut, MapBranchPoint, RegionOut
from auth import get_current_user

router = APIRouter()

@router.get("/stats", response_model=MapStatsOut)
async def get_map_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    # Compter les branches par statut
    total_q   = await db.execute(select(func.count()).select_from(Branch))
    active_q  = await db.execute(select(func.count()).select_from(Branch).where(Branch.status == "active"))
    pending_q = await db.execute(select(func.count()).select_from(Branch).where(Branch.status == "pending"))
    verified_q= await db.execute(select(func.count()).select_from(Branch).where(Branch.is_verified == True))
    regions_q = await db.execute(select(func.count(distinct(Branch.region_id))).select_from(Branch).where(Branch.region_id != None))
    total_reg = await db.execute(select(func.count()).select_from(Region))

    total      = total_q.scalar() or 0
    active     = active_q.scalar() or 0
    pending    = pending_q.scalar() or 0
    verified   = verified_q.scalar() or 0
    covered    = regions_q.scalar() or 0
    tot_reg    = total_reg.scalar() or 31

    # Points carte (branches avec coordonnées)
    branches_q = await db.execute(
        select(Branch, Region.name_fr, Region.name_en)
        .outerjoin(Region, Branch.region_id == Region.id)
        .where(Branch.latitude != None, Branch.longitude != None)
    )
    rows = branches_q.all()

    # Compter les rapports par branche
    reports_q = await db.execute(
        select(PresenceReport.branch_id, func.count().label("cnt"))
        .group_by(PresenceReport.branch_id)
    )
    report_counts = {str(r.branch_id): r.cnt for r in reports_q.all()}

    points: List[MapBranchPoint] = []
    for branch, reg_name_fr, reg_name_en in rows:
        points.append(MapBranchPoint(
            id=str(branch.id),
            name=branch.name,
            code=branch.code,
            city=branch.city,
            latitude=branch.latitude,
            longitude=branch.longitude,
            status=branch.status,
            is_verified=branch.is_verified,
            region_id=branch.region_id,
            region_name=reg_name_fr,
            report_count=report_counts.get(str(branch.id), 0)
        ))

    return MapStatsOut(
        total_branches=total,
        active_branches=active,
        pending_branches=pending,
        verified_branches=verified,
        covered_regions=covered,
        total_regions=tot_reg,
        coverage_pct=round((covered / tot_reg) * 100, 1) if tot_reg else 0,
        points=points
    )

@router.get("/regions", response_model=List[RegionOut])
async def list_regions(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    result = await db.execute(select(Region).order_by(Region.name_fr))
    return result.scalars().all()

@router.get("/regions/{region_id}/branches")
async def branches_by_region(
    region_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Branch).where(Branch.region_id == region_id).order_by(Branch.name)
    )
    branches = result.scalars().all()
    return [
        {
            "id": str(b.id), "name": b.name, "city": b.city,
            "status": b.status, "is_verified": b.is_verified,
            "latitude": b.latitude, "longitude": b.longitude,
            "member_count": b.member_count
        }
        for b in branches
    ]

@router.get("/coverage-summary")
async def coverage_summary(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    """Retourne la liste de toutes les régions avec leur statut de couverture."""
    all_regions = await db.execute(select(Region).order_by(Region.name_fr))
    regions = all_regions.scalars().all()

    branch_per_region = await db.execute(
        select(Branch.region_id, func.count().label("cnt"), func.sum(
            func.cast(Branch.is_verified, Integer := None)
        ))
        .group_by(Branch.region_id)
    )

    # Approche plus simple
    branch_counts = {}
    for row in (await db.execute(
        select(Branch.region_id, func.count().label("cnt"))
        .where(Branch.status.in_(["active","pending"]))
        .group_by(Branch.region_id)
    )).all():
        branch_counts[row.region_id] = row.cnt

    return [
        {
            "region_id": r.id,
            "code": r.code,
            "name_fr": r.name_fr,
            "name_en": r.name_en,
            "district": r.district,
            "branch_count": branch_counts.get(r.id, 0),
            "has_presence": branch_counts.get(r.id, 0) > 0,
            "coverage_level": (
                "high" if branch_counts.get(r.id, 0) >= 3 else
                "medium" if branch_counts.get(r.id, 0) >= 1 else
                "none"
            )
        }
        for r in regions
    ]
