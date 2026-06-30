"""
CODISS Cartographie — Backend FastAPI (SQLite)
Local  : uvicorn main_local:app --reload --port 8000
Render : uvicorn main_local:app --host 0.0.0.0 --port $PORT
"""
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, date as _date
from typing import Optional, List
import uuid, os, random, string, secrets, smtplib, ssl, asyncio, urllib.request, urllib.error, base64, json as _json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

def parse_date(val):
    """Convertit une chaîne ISO ou None en objet date Python."""
    if not val:
        return None
    if isinstance(val, _date):
        return val
    try:
        return _date.fromisoformat(str(val))
    except Exception:
        return None

from database_local import engine, Base, get_db, AsyncSessionLocal
from models_local import (
    User, Branch, BranchUser, PresenceReport,
    ReportFormAnswer, ActivityLog, Notification, Region, ActiveSession
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, distinct

# Auth
import bcrypt as _bcrypt
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer

SECRET_KEY  = "codiss_local_test_secret_key_2024_ne_pas_utiliser_en_prod"
ALGORITHM   = "HS256"
EXPIRE_MINS = 43200  # 30 jours — session persistante

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def hash_password(p):
    return _bcrypt.hashpw(p.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")

def verify_password(p, h):
    try:
        return _bcrypt.checkpw(p.encode("utf-8"), h.encode("utf-8"))
    except Exception:
        return False

# ── Email d'invitation (SMTP générique — Brevo, Gmail, etc.) ──
SMTP_HOST     = os.environ.get("SMTP_HOST", "smtp-relay.brevo.com")
SMTP_PORT     = int(os.environ.get("SMTP_PORT", "587"))
SMTP_LOGIN    = os.environ.get("SMTP_LOGIN", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM     = os.environ.get("SMTP_FROM", SMTP_LOGIN)

def send_invitation_email(to_email: str, full_name: str, setup_link: str) -> bool:
    """Envoie l'email d'invitation avec le lien de définition de mot de passe."""
    if not SMTP_LOGIN or not SMTP_PASSWORD:
        print(f"⚠️  SMTP non configuré. Lien de setup : {setup_link}")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Votre accès CODISS — Définissez votre mot de passe"
        msg["From"]    = f"CODISS Cartographie <{SMTP_FROM}>"
        msg["To"]      = to_email

        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;background:#0f1623;color:#e2e8f0;border-radius:12px;overflow:hidden;">
          <div style="background:linear-gradient(135deg,#00e676,#1de9b6);padding:30px;text-align:center;">
            <h1 style="color:#0a0e1a;margin:0;font-size:24px;">🗺️ CODISS</h1>
            <p style="color:#0a0e1a;margin:8px 0 0;font-size:14px;">Cartographie Nationale</p>
          </div>
          <div style="padding:32px;">
            <h2 style="color:#00e676;font-size:20px;">Bonjour {full_name},</h2>
            <p style="line-height:1.6;">Un compte a été créé pour vous sur la plateforme <strong>CODISS Cartographie</strong>.</p>
            <p style="line-height:1.6;">Cliquez sur le bouton ci-dessous pour définir votre mot de passe et accéder à votre espace :</p>
            <div style="text-align:center;margin:32px 0;">
              <a href="{setup_link}"
                 style="background:linear-gradient(135deg,#00e676,#1de9b6);color:#0a0e1a;padding:14px 32px;
                        border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px;display:inline-block;">
                🔑 Définir mon mot de passe
              </a>
            </div>
            <p style="color:#94a3b8;font-size:13px;line-height:1.6;">
              Ce lien est valable <strong style="color:#e2e8f0;">48 heures</strong>.<br>
              Si vous n'avez pas demandé ce compte, ignorez cet email.
            </p>
            <hr style="border:none;border-top:1px solid #1e3a5f;margin:24px 0;">
            <p style="color:#64748b;font-size:12px;text-align:center;">
              CODISS — Système de Cartographie Nationale de Côte d'Ivoire
            </p>
          </div>
        </div>"""

        text = f"""Bonjour {full_name},\n\nUn compte a été créé pour vous sur CODISS Cartographie.\n\nDéfinissez votre mot de passe via ce lien (valable 48h) :\n{setup_link}\n\nCODISS Cartographie Nationale"""

        msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_LOGIN, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"❌ Erreur envoi email : {e}")
        return False

def make_token(data):
    d = data.copy()
    d["exp"] = datetime.utcnow() + timedelta(minutes=EXPIRE_MINS)
    return jwt.encode(d, SECRET_KEY, algorithm=ALGORITHM)

async def current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        uid = payload.get("sub")
    except JWTError:
        raise HTTPException(401, "Token invalide")
    u = await db.get(User, uid)
    if not u or not u.is_active:
        raise HTTPException(401, "Utilisateur introuvable")
    return u

def admin_only(u: User = Depends(current_user)):
    if u.role not in ("superadmin", "admin"):
        raise HTTPException(403, "Accès admin requis")
    return u

# ── Démarrage + auto-seed ─────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Créer les tables SQLite
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # 2. Auto-seed si la base est vide
    await auto_seed()
    yield
    await engine.dispose()


# ══════════════════════════════════════════════════════
# PERSISTANCE GITHUB — Sauvegarde / Restauration users
# ══════════════════════════════════════════════════════
_GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")  # Définir GITHUB_TOKEN dans Render env vars
_GH_REPO  = "tolobayounousaa225-prog/codiss-cartographie"
_GH_FILE  = "data/backup_users.json"

def _gh_api(method, payload=None):
    """Appel synchrone GitHub API (appellé via asyncio.to_thread)."""
    url = f"https://api.github.com/repos/{_GH_REPO}/contents/{_GH_FILE}"
    data = _json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"token {_GH_TOKEN}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return _json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"GitHub {method}: HTTP {e.code} — {body[:200]}")
        return None
    except Exception as e:
        print(f"GitHub {method} erreur: {e}")
        return None

async def backup_users_to_github(db=None):
    """Sauvegarde tous les utilisateurs non-superadmin sur GitHub (session propre)."""
    if not _GH_TOKEN: return
    try:
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(User).where(User.role != "superadmin").order_by(User.created_at)
            )).scalars().all()
        users_data = [
            {"email": u.email, "password_hash": u.password_hash,
             "full_name": u.full_name, "phone": u.phone, "role": u.role,
             "language": u.language or "fr", "is_active": u.is_active,
             "must_set_password": bool(u.must_set_password)}
            for u in rows
        ]
        encoded = base64.b64encode(
            _json.dumps(users_data, ensure_ascii=False, indent=2).encode()
        ).decode()

        def _push():
            existing = _gh_api("GET")
            sha = existing.get("sha") if existing else None
            payload = {
                "message": f"backup: {len(users_data)} users — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC",
                "content": encoded,
            }
            if sha: payload["sha"] = sha
            return _gh_api("PUT", payload)

        res = await asyncio.to_thread(_push)
        if res: print(f"✅ GitHub backup: {len(users_data)} utilisateurs sauvegardés")
        else:    print("⚠️  GitHub backup échoué (non bloquant)")
    except Exception as e:
        print(f"⚠️  backup_users_to_github: {e}")

async def restore_users_from_github(db: AsyncSession):
    """Restaure les utilisateurs depuis GitHub au démarrage."""
    if not _GH_TOKEN: return
    try:
        def _fetch():
            res = _gh_api("GET")
            if not res or "content" not in res: return []
            raw = base64.b64decode(res["content"].replace("\n","")).decode()
            return _json.loads(raw)

        users_data = await asyncio.to_thread(_fetch)
        if not users_data:
            print("GitHub: aucun utilisateur à restaurer"); return

        restored = 0
        for ud in users_data:
            ex = (await db.execute(select(User).where(User.email == ud["email"]))).scalar_one_or_none()
            if ex: continue
            db.add(User(
                email=ud["email"], password_hash=ud["password_hash"],
                full_name=ud["full_name"], phone=ud.get("phone"),
                role=ud.get("role","branch"), language=ud.get("language","fr"),
                is_active=ud.get("is_active", True),
                must_set_password=ud.get("must_set_password", False),
            ))
            restored += 1
        if restored > 0:
            await db.commit()
            print(f"✅ GitHub restauration: {restored} utilisateurs restaurés")
        else:
            print(f"GitHub: tous les {len(users_data)} users déjà présents")
    except Exception as e:
        print(f"⚠️  restore_users_from_github: {e}")

async def auto_seed():
    """Crée le super-admin et les régions si la base est vierge."""
    from database_local import DB_MODE
    print(f"🗄️  Mode base de données : {DB_MODE}")
    try:
        async with AsyncSessionLocal() as db:
            existing = (await db.execute(select(User).limit(1))).scalar_one_or_none()
            if existing:
                print(f"✅ Base déjà peuplée — seed ignoré.")
                # Restaurer quand même les users GitHub (ils auraient pu être perdus)
                await restore_users_from_github(db)
                return
            from seed_db import do_seed
            await do_seed(db)
            await db.commit()
            print("✅ Base de données initialisée automatiquement.")
            # Restaurer les utilisateurs sauvegardés sur GitHub
            await restore_users_from_github(db)
    except Exception as e:
        print(f"⚠️  Auto-seed erreur : {type(e).__name__}: {e}")

app = FastAPI(
    title="CODISS Cartographie",
    version="1.0.0",
    docs_url="/api/docs",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Désactiver le cache CDN Render sur les endpoints dynamiques
@app.middleware("http")
async def no_cache_middleware(request, call_next):
    response = await call_next(request)
    # Bloquer le cache CDN sur toutes les routes dynamiques ET statiques critiques
    _no_cache_paths = {"/", "/health", "/openapi.json"}
    if request.url.path.startswith("/api/") or request.url.path in _no_cache_paths:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response

# ── Fichiers statiques (CSS, JS, images éventuels) ────────────
_HERE = os.path.dirname(os.path.abspath(__file__))

_NO_CACHE = {"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}

@app.get("/", include_in_schema=False)
@app.head("/", include_in_schema=False)
@app.get("/app", include_in_schema=False)
@app.get("/login", include_in_schema=False)
async def serve_index():
    return FileResponse(os.path.join(_HERE, "index.html"), headers=_NO_CACHE)

@app.head("/health", include_in_schema=False)
async def health_head():
    return Response(status_code=200)

@app.get("/health")
async def health():
    from fastapi.responses import JSONResponse
    from database_local import DB_MODE
    return JSONResponse(
        content={"status": "ok", "mode": DB_MODE, "version": "b9cceb4"},
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}
    )

@app.get("/api/version")
async def api_version():
    from fastapi.responses import JSONResponse
    return JSONResponse(
        content={"version": "4138ed7", "status": "ok", "mode": "sqlite", "features": ["heartbeat", "email-invitation", "brevo-smtp", "head-fix", "api-version"]},
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}
    )

# ══════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════
@app.post("/api/auth/login")
async def login(data: dict, request: Request, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(User).where(User.email == data["email"]))
    u = r.scalar_one_or_none()
    if not u or not verify_password(data["password"], u.password_hash):
        raise HTTPException(401, "Email ou mot de passe incorrect")
    if not u.is_active:
        raise HTTPException(403, "Compte désactivé")
    await db.execute(update(User).where(User.id == u.id).values(last_login=datetime.utcnow()))
    branch_id = None
    if u.role == "branch":
        bu = await db.execute(select(BranchUser).where(BranchUser.user_id == u.id))
        row = bu.scalar_one_or_none()
        if row: branch_id = row.branch_id
    return {
        "access_token": make_token({"sub": u.id, "role": u.role}),
        "token_type": "bearer",
        "user_id": u.id,
        "full_name": u.full_name,
        "role": u.role,
        "language": u.language,
        "branch_id": branch_id
    }

@app.get("/api/auth/me")
async def me(u: User = Depends(current_user)):
    return {"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role, "language": u.language, "is_active": u.is_active}

@app.patch("/api/auth/me/language")
async def set_lang(language: str, u: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(update(User).where(User.id == u.id).values(language=language))
    return {"ok": True}

# ══════════════════════════════════════════════════════
# SESSIONS EN TEMPS RÉEL (heartbeat / qui est en ligne)
# ══════════════════════════════════════════════════════
@app.post("/api/auth/heartbeat")
async def heartbeat(data: dict, u: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    page = (data.get("page") or "dashboard")[:100]
    r = await db.execute(select(ActiveSession).where(ActiveSession.user_id == u.id))
    sess = r.scalar_one_or_none()
    if sess:
        await db.execute(
            update(ActiveSession)
            .where(ActiveSession.user_id == u.id)
            .values(last_seen=datetime.utcnow(), current_page=page)
        )
    else:
        db.add(ActiveSession(user_id=u.id, current_page=page, connected_at=datetime.utcnow()))
    await db.commit()
    return {"ok": True}

@app.delete("/api/auth/logout")
async def logout(u: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(ActiveSession).where(ActiveSession.user_id == u.id))
    sess = r.scalar_one_or_none()
    if sess:
        await db.delete(sess)
        await db.commit()
    return {"ok": True}

@app.get("/api/admin/online-users")
async def online_users(u: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if u.role != "superadmin":
        raise HTTPException(403, "Réservé au super admin")
    cutoff = datetime.utcnow() - timedelta(seconds=90)
    r = await db.execute(
        select(ActiveSession, User)
        .join(User, ActiveSession.user_id == User.id)
        .where(ActiveSession.last_seen >= cutoff)
        .order_by(ActiveSession.connected_at)
    )
    rows = r.all()
    now = datetime.utcnow()
    result = []
    for sess, usr in rows:
        duration = int((now - sess.connected_at).total_seconds())
        result.append({
            "user_id": usr.id, "full_name": usr.full_name, "role": usr.role,
            "email": usr.email, "current_page": sess.current_page,
            "connected_at": sess.connected_at.isoformat(),
            "last_seen": sess.last_seen.isoformat(),
            "duration_secs": duration,
        })
    return result


# ══════════════════════════════════════════════════════
# BRANCHES
# ══════════════════════════════════════════════════════
@app.get("/api/branches")
async def list_branches(status: Optional[str] = None, db: AsyncSession = Depends(get_db), _=Depends(current_user)):
    q = select(Branch)
    if status: q = q.where(Branch.status == status)
    r = await db.execute(q.order_by(Branch.name))
    branches = r.scalars().all()
    return [_branch_dict(b) for b in branches]

@app.get("/api/branches/my")
async def my_branch(u: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    bu = await db.execute(select(BranchUser).where(BranchUser.user_id == u.id))
    row = bu.scalar_one_or_none()
    if not row: raise HTTPException(404, "Aucune branche associée")
    b = await db.get(Branch, row.branch_id)
    return _branch_dict(b)

@app.get("/api/branches/{bid}")
async def get_branch(bid: str, db: AsyncSession = Depends(get_db), _=Depends(current_user)):
    b = await db.get(Branch, bid)
    if not b: raise HTTPException(404, "Branche introuvable")
    return _branch_dict(b)

@app.post("/api/branches", status_code=201)
async def create_branch(data: dict, db: AsyncSession = Depends(get_db), _=Depends(admin_only)):
    ex = await db.execute(select(Branch).where(Branch.code == data.get("code","")))
    if ex.scalar_one_or_none(): raise HTTPException(400, "Code déjà utilisé")
    b = Branch(**{k: v for k, v in data.items() if hasattr(Branch, k)})
    db.add(b)
    await db.commit()
    await db.refresh(b)
    return _branch_dict(b)

@app.patch("/api/branches/{bid}")
async def update_branch(bid: str, data: dict, db: AsyncSession = Depends(get_db), _=Depends(current_user)):
    b = await db.get(Branch, bid)
    if not b: raise HTTPException(404)
    for k, v in data.items():
        if hasattr(b, k) and v is not None: setattr(b, k, v)
    await db.commit()
    await db.refresh(b)
    return _branch_dict(b)

@app.post("/api/branches/{bid}/verify")
async def verify_branch(bid: str, db: AsyncSession = Depends(get_db), u=Depends(admin_only)):
    b = await db.get(Branch, bid)
    if not b: raise HTTPException(404)
    b.is_verified = True; b.verified_at = datetime.utcnow()
    b.verified_by = u.id; b.status = "active"
    await db.commit()
    return {"message": f"{b.name} vérifiée et activée"}

@app.post("/api/branches/{bid}/assign-user")
async def assign_user(bid: str, user_id: str, role: str = "secretary", db: AsyncSession = Depends(get_db), _=Depends(admin_only)):
    # Vérifier que la branche existe
    b = await db.get(Branch, bid)
    if not b: raise HTTPException(404, "Branche introuvable")
    # Vérifier que l'utilisateur existe
    u = await db.get(User, user_id)
    if not u: raise HTTPException(404, "Utilisateur introuvable")
    # Supprimer l'éventuelle liaison précédente de cet utilisateur
    existing = await db.execute(select(BranchUser).where(BranchUser.user_id == user_id))
    old = existing.scalar_one_or_none()
    if old:
        await db.delete(old)
    bu = BranchUser(user_id=user_id, branch_id=bid, role=role)
    db.add(bu)
    return {"ok": True, "user": u.full_name, "branch": b.name}

def _branch_dict(b):
    return {
        "id": b.id, "code": b.code, "name": b.name, "city": b.city,
        "address": b.address, "region_id": b.region_id, "department_id": b.department_id,
        "latitude": b.latitude, "longitude": b.longitude, "status": b.status,
        "is_verified": b.is_verified, "president_name": b.president_name,
        "president_phone": b.president_phone, "president_email": b.president_email,
        "member_count": b.member_count, "founded_date": str(b.founded_date) if b.founded_date else None,
        "created_at": b.created_at.isoformat() if b.created_at else None
    }

# ══════════════════════════════════════════════════════
# REPORTS
# ══════════════════════════════════════════════════════
@app.post("/api/reports", status_code=201)
async def submit_report(data: dict, db: AsyncSession = Depends(get_db), u: User = Depends(current_user)):
    if u.role != "branch":
        raise HTTPException(403, "Réservé aux secrétaires de branche")

    bu = await db.execute(select(BranchUser).where(BranchUser.user_id == u.id))
    row = bu.scalar_one_or_none()
    if not row:
        raise HTTPException(403, "Aucune branche associée à votre compte. Allez dans 'Ma branche' pour en choisir une.")

    title = (data.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "Le titre du rapport est obligatoire")

    # Coordonnées GPS — fallback sur celles de la branche
    branch = await db.get(Branch, row.branch_id)
    raw_lat = data.get("latitude")
    raw_lng = data.get("longitude")
    # Traiter explicitement 0.0 comme valeur valide (pas falsy)
    lat = raw_lat if raw_lat is not None else (branch.latitude if branch else None)
    lng = raw_lng if raw_lng is not None else (branch.longitude if branch else None)

    # Convertir les dates proprement
    period_start = parse_date(data.get("period_start"))
    period_end   = parse_date(data.get("period_end"))

    # Activités — s'assurer que c'est un entier
    try:
        activity_count = int(data.get("activity_count") or 0)
    except (TypeError, ValueError):
        activity_count = 0

    report = PresenceReport(
        branch_id         = row.branch_id,
        submitted_by      = u.id,
        latitude          = lat,
        longitude         = lng,
        location_accuracy = data.get("location_accuracy"),
        location_address  = data.get("location_address"),
        report_type       = data.get("report_type") or "presence",
        title             = title,
        description       = (data.get("description") or "").strip() or None,
        activity_count    = activity_count,
        period_start      = period_start,
        period_end        = period_end,
    )
    db.add(report)
    await db.flush()

    for ans in data.get("form_answers") or []:
        q = (ans.get("question") or "").strip()
        a = (ans.get("answer") or "").strip()
        if q:
            db.add(ReportFormAnswer(report_id=report.id, question=q, answer=a))

    # Mettre à jour les coords de la branche si elles manquaient
    if branch and branch.latitude is None and lat is not None:
        branch.latitude  = lat
        branch.longitude = lng

    await db.commit()
    await db.refresh(report)
    return _report_dict(report)

@app.get("/api/reports")
async def list_reports(db: AsyncSession = Depends(get_db), u: User = Depends(current_user)):
    q = select(PresenceReport)
    if u.role == "branch":
        bu = await db.execute(select(BranchUser).where(BranchUser.user_id == u.id))
        row = bu.scalar_one_or_none()
        if row: q = q.where(PresenceReport.branch_id == row.branch_id)
    r = await db.execute(q.order_by(PresenceReport.created_at.desc()).limit(100))
    return [_report_dict(rp) for rp in r.scalars().all()]

@app.patch("/api/reports/{rid}/review")
async def review_report(rid: str, data: dict, db: AsyncSession = Depends(get_db), u=Depends(admin_only)):
    rp = await db.get(PresenceReport, rid)
    if not rp: raise HTTPException(404)
    status = data.get("status")
    if status not in ("approved", "rejected"):
        raise HTTPException(400, "Statut invalide : 'approved' ou 'rejected'")
    rp.status      = status
    rp.reviewed_by = u.id
    rp.reviewed_at = datetime.utcnow()
    rp.review_notes = (data.get("notes") or "").strip() or None
    rp.branch_response = None   # réinitialiser la réponse si re-review
    if status == "approved":
        b = await db.get(Branch, rp.branch_id)
        if b and b.status == "pending": b.status = "active"
    # Notifier le secrétaire
    submitter = await db.get(User, rp.submitted_by) if rp.submitted_by else None
    if submitter:
        verdict = "approuvé" if status == "approved" else "rejeté"
        verdict_en = "approved" if status == "approved" else "rejected"
        motif_fr = f" Motif : {rp.review_notes}" if rp.review_notes else ""
        motif_en = f" Reason: {rp.review_notes}" if rp.review_notes else ""
        db.add(Notification(
            user_id=submitter.id,
            title_fr=f"Rapport {verdict} : {rp.title}",
            title_en=f"Report {verdict_en}: {rp.title}",
            body_fr=f"Votre rapport a été {verdict} par l'administration.{motif_fr}",
            body_en=f"Your report has been {verdict_en} by administration.{motif_en}",
            type="success" if status == "approved" else "warning",
        ))
    await db.commit()
    return {"ok": True, "status": status}

@app.patch("/api/reports/{rid}/respond")
async def respond_to_rejection(rid: str, data: dict, db: AsyncSession = Depends(get_db), u: User = Depends(current_user)):
    rp = await db.get(PresenceReport, rid)
    if not rp: raise HTTPException(404)
    if rp.submitted_by != u.id:
        raise HTTPException(403, "Vous ne pouvez répondre qu'à vos propres rapports")
    if rp.status != "rejected":
        raise HTTPException(400, "Ce rapport n'est pas rejeté")
    response = (data.get("response") or "").strip()
    if not response:
        raise HTTPException(400, "La réponse ne peut pas être vide")
    rp.branch_response = response
    # Notifier les admins
    admins = (await db.execute(select(User).where(User.role.in_(["admin","superadmin"]), User.is_active==True))).scalars().all()
    for admin in admins:
        db.add(Notification(
            user_id=admin.id,
            title_fr=f"Réponse au rejet : {rp.title}",
            title_en=f"Reply to rejection: {rp.title}",
            body_fr=f"{u.full_name} a répondu au rejet de son rapport.",
            body_en=f"{u.full_name} replied to their report rejection.",
            type="info",
        ))
    await db.commit()
    return {"ok": True}

def _report_dict(r):
    return {
        "id": r.id, "branch_id": r.branch_id, "title": r.title,
        "description": r.description, "report_type": r.report_type,
        "latitude": r.latitude, "longitude": r.longitude,
        "location_address": r.location_address, "activity_count": r.activity_count,
        "status": r.status,
        "review_notes": r.review_notes,
        "branch_response": r.branch_response,
        "viewed_by_admin": r.viewed_by_admin or False,
        "viewed_at": r.viewed_at.isoformat() if r.viewed_at else None,
        "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        "period_start": str(r.period_start) if r.period_start else None,
        "period_end": str(r.period_end) if r.period_end else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }

# ══════════════════════════════════════════════════════
# MAP
# ══════════════════════════════════════════════════════
@app.get("/api/map/stats")
async def map_stats(db: AsyncSession = Depends(get_db), _=Depends(current_user)):
    total    = (await db.execute(select(func.count()).select_from(Branch))).scalar() or 0
    active   = (await db.execute(select(func.count()).select_from(Branch).where(Branch.status=="active"))).scalar() or 0
    pending  = (await db.execute(select(func.count()).select_from(Branch).where(Branch.status=="pending"))).scalar() or 0
    verified = (await db.execute(select(func.count()).select_from(Branch).where(Branch.is_verified==True))).scalar() or 0
    covered  = (await db.execute(select(func.count(distinct(Branch.region_id))).select_from(Branch).where(Branch.region_id!=None))).scalar() or 0
    tot_reg  = (await db.execute(select(func.count()).select_from(Region))).scalar() or 31

    bq = await db.execute(
        select(Branch, Region.name_fr).outerjoin(Region, Branch.region_id==Region.id)
        .where(Branch.latitude!=None, Branch.longitude!=None)
    )
    rows = bq.all()

    rc = {r.branch_id: r.cnt for r in (await db.execute(
        select(PresenceReport.branch_id, func.count().label("cnt")).group_by(PresenceReport.branch_id)
    )).all()}

    points = [{"id": b.id, "name": b.name, "code": b.code, "city": b.city,
               "latitude": b.latitude, "longitude": b.longitude,
               "status": b.status, "is_verified": b.is_verified,
               "region_id": b.region_id, "region_name": rname,
               "report_count": rc.get(b.id, 0)}
              for b, rname in rows]

    return {
        "total_branches": total, "active_branches": active,
        "pending_branches": pending, "verified_branches": verified,
        "covered_regions": covered, "total_regions": tot_reg,
        "coverage_pct": round((covered/tot_reg)*100, 1) if tot_reg else 0,
        "points": points
    }

@app.get("/api/map/regions")
async def list_regions(db: AsyncSession = Depends(get_db), _=Depends(current_user)):
    r = await db.execute(select(Region).order_by(Region.name_fr))
    return [{"id": rg.id, "code": rg.code, "name_fr": rg.name_fr, "name_en": rg.name_en, "district": rg.district}
            for rg in r.scalars().all()]

@app.get("/api/map/coverage-summary")
async def coverage_summary(db: AsyncSession = Depends(get_db), _=Depends(current_user)):
    regions = (await db.execute(select(Region).order_by(Region.name_fr))).scalars().all()
    counts  = {r.region_id: r.cnt for r in (await db.execute(
        select(Branch.region_id, func.count().label("cnt"))
        .where(Branch.status.in_(["active","pending"]))
        .group_by(Branch.region_id)
    )).all()}
    return [{"region_id": r.id, "code": r.code, "name_fr": r.name_fr, "name_en": r.name_en,
             "district": r.district, "branch_count": counts.get(r.id, 0),
             "has_presence": counts.get(r.id, 0) > 0,
             "coverage_level": "high" if counts.get(r.id,0)>=3 else "medium" if counts.get(r.id,0)>=1 else "none"}
            for r in regions]

# ══════════════════════════════════════════════════════
# ADMIN
# ══════════════════════════════════════════════════════
@app.get("/api/admin/stats")
async def admin_stats(db: AsyncSession = Depends(get_db), _=Depends(admin_only)):
    # Statuts des branches
    branch_rows = (await db.execute(select(Branch.status, func.count()).group_by(Branch.status))).all()
    branch_by_status = {r[0]: r[1] for r in branch_rows}
    # Rapports des 6 derniers mois
    six_months_ago = datetime.utcnow().replace(day=1) - timedelta(days=150)
    rpt_rows = (await db.execute(
        select(PresenceReport.submitted_at).where(PresenceReport.submitted_at >= six_months_ago)
    )).scalars().all()
    monthly = {}
    for dt in rpt_rows:
        if dt:
            key = dt.strftime("%Y-%m")
            monthly[key] = monthly.get(key, 0) + 1
    # Trier les 6 derniers mois
    import calendar
    months_labels = []
    months_data = []
    for i in range(5, -1, -1):
        d = datetime.utcnow().replace(day=1) - timedelta(days=i*30)
        key = d.strftime("%Y-%m")
        label = d.strftime("%b %Y")
        months_labels.append(label)
        months_data.append(monthly.get(key, 0))
    return {
        "total_users":    (await db.execute(select(func.count()).select_from(User))).scalar(),
        "total_branches": (await db.execute(select(func.count()).select_from(Branch))).scalar(),
        "active_branches": branch_by_status.get("active", 0),
        "pending_branches": branch_by_status.get("pending", 0),
        "suspended_branches": branch_by_status.get("suspended", 0) + branch_by_status.get("rejected", 0),
        "total_reports":  (await db.execute(select(func.count()).select_from(PresenceReport))).scalar(),
        "pending_reports":(await db.execute(select(func.count()).select_from(PresenceReport).where(PresenceReport.status=="submitted"))).scalar(),
        "approved_reports":(await db.execute(select(func.count()).select_from(PresenceReport).where(PresenceReport.status=="approved"))).scalar(),
        "branch_by_status": branch_by_status,
        "reports_by_month": {"labels": months_labels, "data": months_data},
    }

@app.get("/api/admin/users")
async def list_users(db: AsyncSession = Depends(get_db), _=Depends(admin_only)):
    r = await db.execute(select(User).order_by(User.created_at.desc()))
    return [{"id": u.id, "email": u.email, "full_name": u.full_name, "phone": u.phone,
             "role": u.role, "language": u.language, "is_active": u.is_active,
             "created_at": u.created_at.isoformat() if u.created_at else None,
             "last_login": u.last_login.isoformat() if u.last_login else None,
             "has_plain_password": bool(u.plain_password)}
            for u in r.scalars().all()]

@app.post("/api/admin/users", status_code=201)
async def create_user(data: dict, request: Request, db: AsyncSession = Depends(get_db), _=Depends(admin_only)):
    ex = await db.execute(select(User).where(User.email == data["email"]))
    if ex.scalar_one_or_none(): raise HTTPException(400, "Email déjà utilisé")

    password_provided = data.get("password", "").strip()

    if password_provided:
        # ── Mode direct : admin fournit le mot de passe ──────────────────
        u = User(
            email=data["email"],
            password_hash=hash_password(password_provided),
            full_name=data["full_name"],
            phone=data.get("phone"),
            role=data.get("role", "branch"),
            language=data.get("language", "fr"),
        )
        db.add(u)
        await db.commit()
        await db.refresh(u)
        asyncio.create_task(backup_users_to_github(db))
        return {
            "id": u.id, "email": u.email, "full_name": u.full_name,
            "role": u.role, "is_active": u.is_active,
            "created_at": u.created_at.isoformat(),
            "email_sent": False,
            "setup_link": None,
        }
    else:
        # ── Mode invitation : génère token + tente envoi email ───────────
        token = secrets.token_urlsafe(32)
        expires = datetime.utcnow() + timedelta(hours=48)
        placeholder_pw = secrets.token_urlsafe(24)
        u = User(
            email=data["email"],
            password_hash=hash_password(placeholder_pw),
            full_name=data["full_name"],
            phone=data.get("phone"),
            role=data.get("role", "branch"),
            language=data.get("language", "fr"),
            setup_token=token,
            setup_token_expires=expires,
            must_set_password=True,
        )
        db.add(u)
        await db.commit()
        await db.refresh(u)
        asyncio.create_task(backup_users_to_github(db))
        base_url = str(request.base_url).rstrip("/")
        setup_link = f"{base_url}/?setup_token={token}"
        email_sent = send_invitation_email(u.email, u.full_name, setup_link)
        return {
            "id": u.id, "email": u.email, "full_name": u.full_name,
            "role": u.role, "is_active": u.is_active,
            "created_at": u.created_at.isoformat(),
            "email_sent": email_sent,
            "setup_link": setup_link,
        }

@app.get("/api/auth/check-setup-token")
async def check_setup_token(token: str, db: AsyncSession = Depends(get_db)):
    """Vérifie qu'un token de setup est valide et retourne l'email masqué."""
    r = await db.execute(select(User).where(User.setup_token == token))
    u = r.scalar_one_or_none()
    if not u:
        raise HTTPException(404, "Lien invalide ou déjà utilisé")
    if u.setup_token_expires and datetime.utcnow() > u.setup_token_expires:
        raise HTTPException(410, "Ce lien a expiré. Contactez l'administration.")
    parts = u.email.split("@")
    local = parts[0]
    masked = local[:2] + "***" + local[-1:] + "@" + parts[1]
    return {"valid": True, "full_name": u.full_name, "email_masked": masked}

@app.post("/api/auth/setup-password")
async def setup_password(data: dict, db: AsyncSession = Depends(get_db)):
    """Définit le mot de passe d'un nouvel utilisateur via son token d'invitation."""
    token    = (data.get("token") or "").strip()
    password = (data.get("password") or "").strip()
    if not token or not password:
        raise HTTPException(400, "Token et mot de passe requis")
    if len(password) < 6:
        raise HTTPException(400, "Le mot de passe doit contenir au moins 6 caractères")
    r = await db.execute(select(User).where(User.setup_token == token))
    u = r.scalar_one_or_none()
    if not u:
        raise HTTPException(404, "Lien invalide ou déjà utilisé")
    if u.setup_token_expires and datetime.utcnow() > u.setup_token_expires:
        raise HTTPException(410, "Ce lien a expiré. Contactez l'administration.")
    u.password_hash       = hash_password(password)
    u.setup_token         = None
    u.setup_token_expires = None
    u.must_set_password   = False
    u.is_active           = True
    await db.commit()
    return {"ok": True, "message": "Mot de passe défini avec succès. Vous pouvez maintenant vous connecter."}

@app.patch("/api/admin/users/{uid}/toggle-active")
async def toggle_user(uid: str, db: AsyncSession = Depends(get_db), _=Depends(admin_only)):
    u = await db.get(User, uid)
    if not u: raise HTTPException(404)
    if u.role == "superadmin":
        raise HTTPException(403, "Le compte super administrateur ne peut pas être désactivé")
    u.is_active = not u.is_active
    await db.commit()
    return {"is_active": u.is_active}

@app.get("/api/admin/users/{uid}/password")
async def get_user_password(uid: str, u: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Retourne le mot de passe en clair (super admin uniquement)."""
    if u.role != "superadmin":
        raise HTTPException(403, "Réservé au super administrateur")
    target = await db.get(User, uid)
    if not target: raise HTTPException(404, "Utilisateur introuvable")
    return {
        "id": target.id,
        "email": target.email,
        "full_name": target.full_name,
        "plain_password": target.plain_password or "(non disponible — défini avant cette version)"
    }

@app.post("/api/admin/users/{uid}/reset-password")
async def admin_reset_password_visible(uid: str, u: User = Depends(current_user), db: AsyncSession = Depends(get_db), _=Depends(admin_only)):
    """Réinitialise le mot de passe et retourne le nouveau en clair (admin+)."""
    target = await db.get(User, uid)
    if not target: raise HTTPException(404, "Utilisateur introuvable")
    first = target.full_name.split()[0].capitalize() if target.full_name else "User"
    digits = "".join(random.choices(string.digits, k=4))
    new_pw = f"{first}@{digits}"
    target.password_hash = hash_password(new_pw)
    target.plain_password = new_pw
    await db.commit()
    return {"id": uid, "email": target.email, "new_password": new_pw}

@app.get("/api/admin/notifications")
async def get_notifs(db: AsyncSession = Depends(get_db), u: User = Depends(current_user)):
    r = await db.execute(select(Notification).where(Notification.user_id==u.id).order_by(Notification.created_at.desc()).limit(50))
    return [{"id": n.id, "title": n.title_fr if u.language=="fr" else (n.title_en or n.title_fr),
             "body": n.body_fr if u.language=="fr" else (n.body_en or n.body_fr),
             "type": n.type, "is_read": n.is_read, "created_at": n.created_at.isoformat()}
            for n in r.scalars().all()]

@app.patch("/api/admin/notifications/{nid}/read")
async def mark_read(nid: str, db: AsyncSession = Depends(get_db), u: User = Depends(current_user)):
    n = await db.get(Notification, nid)
    if n and n.user_id == u.id:
        n.is_read = True
        await db.commit()
    return {"ok": True}

# ══════════════════════════════════════════════════════
# PROFIL UTILISATEUR
# ══════════════════════════════════════════════════════
@app.patch("/api/auth/me")
async def update_profile(data: dict, u: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    allowed = ["full_name", "phone", "language"]
    for k, v in data.items():
        if k in allowed and v is not None:
            setattr(u, k, v)
    await db.commit()
    return {"id": u.id, "email": u.email, "full_name": u.full_name,
            "phone": u.phone, "role": u.role, "language": u.language}

@app.patch("/api/auth/me/password")
async def change_password(data: dict, u: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if not verify_password(data.get("current_password", ""), u.password_hash):
        raise HTTPException(400, "Mot de passe actuel incorrect")
    u.password_hash = hash_password(data["new_password"])
    u.plain_password = data["new_password"]
    await db.commit()
    return {"ok": True}

# ══════════════════════════════════════════════════════
# RAPPORT DETAIL
# ══════════════════════════════════════════════════════
@app.get("/api/reports/{rid}")
async def get_report(rid: str, db: AsyncSession = Depends(get_db), u: User = Depends(current_user)):
    rp = await db.get(PresenceReport, rid)
    if not rp: raise HTTPException(404)
    if u.role in ("admin", "superadmin") and not rp.viewed_by_admin:
        rp.viewed_by_admin = True
        rp.viewed_at = datetime.utcnow()
        await db.commit()
    answers = (await db.execute(
        select(ReportFormAnswer).where(ReportFormAnswer.report_id == rid)
    )).scalars().all()
    d = _report_dict(rp)
    d["form_answers"] = [{"question": a.question, "answer": a.answer} for a in answers]
    return d

# ══════════════════════════════════════════════════════
# BRANCHES — REJET
# ══════════════════════════════════════════════════════
@app.post("/api/branches/{bid}/reject")
async def reject_branch(bid: str, db: AsyncSession = Depends(get_db), u=Depends(admin_only)):
    b = await db.get(Branch, bid)
    if not b: raise HTTPException(404)
    b.status = "rejected"
    await db.commit()
    return {"message": f"{b.name} rejetée"}

@app.delete("/api/admin/users/{uid}")
async def delete_user(uid: str, db: AsyncSession = Depends(get_db), u=Depends(admin_only)):
    user = await db.get(User, uid)
    if not user: raise HTTPException(404)
    await db.delete(user)
    await db.commit()
    asyncio.create_task(backup_users_to_github(db))
    return {"ok": True}

# ══════════════════════════════════════════════════════
# AUTO-SÉLECTION DE BRANCHE (par le secrétaire lui-même)
# ══════════════════════════════════════════════════════
@app.post("/api/auth/me/select-branch")
async def self_select_branch(data: dict, u: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if u.role != "branch":
        raise HTTPException(403, "Réservé aux secrétaires de branche")
    branch_id = data.get("branch_id")
    if not branch_id:
        raise HTTPException(400, "branch_id requis")
    b = await db.get(Branch, branch_id)
    if not b:
        raise HTTPException(404, "Branche introuvable")
    existing = await db.execute(select(BranchUser).where(BranchUser.user_id == u.id))
    old = existing.scalar_one_or_none()
    if old:
        await db.delete(old)
        await db.flush()
    bu = BranchUser(user_id=u.id, branch_id=branch_id, role="secretary")
    db.add(bu)
    await db.commit()
    return {"ok": True, "branch": _branch_dict(b)}

# ══════════════════════════════════════════════════════
# RÉCUPÉRATION D'ACCÈS
# ══════════════════════════════════════════════════════
import random, string

def gen_temp_password(length=10):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))

@app.post("/api/auth/forgot-password")
async def forgot_password(data: dict, db: AsyncSession = Depends(get_db)):
    """Génère un mot de passe temporaire — affiche sur écran (pas d'email en local)."""
    email = (data.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(400, "Email requis")
    r = await db.execute(select(User).where(User.email == email))
    u = r.scalar_one_or_none()
    if not u:
        raise HTTPException(404, "Aucun compte trouvé pour cet email.")
    temp = gen_temp_password()
    u.password_hash = hash_password(temp)
    await db.commit()
    return {"ok": True, "full_name": u.full_name, "temp_password": temp,
            "message": "Mot de passe temporaire généré. Connectez-vous puis changez-le immédiatement."}

@app.post("/api/auth/find-by-name")
async def find_by_name(data: dict, db: AsyncSession = Depends(get_db)):
    """Retrouve un email à partir d'un nom complet (partiel)."""
    name = (data.get("name") or "").strip()
    if len(name) < 3:
        raise HTTPException(400, "Entrez au moins 3 caractères")
    r = await db.execute(
        select(User).where(User.full_name.ilike(f"%{name}%")).limit(5)
    )
    users = r.scalars().all()
    if not users:
        raise HTTPException(404, "Aucun compte trouvé pour ce nom.")
    def mask_email(email):
        parts = email.split("@")
        local = parts[0]
        shown = local[:2] + "*" * max(2, len(local)-4) + local[-2:] if len(local) > 4 else local[:1] + "***"
        return shown + "@" + parts[1]
    return [{"full_name": u.full_name, "email_masked": mask_email(u.email)} for u in users]

@app.post("/api/admin/users/{uid}/reset-password")
async def admin_reset_password(uid: str, db: AsyncSession = Depends(get_db), _=Depends(admin_only)):
    """Réinitialise le mot de passe d'un utilisateur (admin uniquement)."""
    u = await db.get(User, uid)
    if not u: raise HTTPException(404)
    temp = gen_temp_password()
    u.password_hash = hash_password(temp)
    await db.commit()
    return {"ok": True, "full_name": u.full_name, "temp_password": temp}
