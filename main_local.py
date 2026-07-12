"""
CODISS Cartographie — Backend FastAPI (SQLite)
Local  : uvicorn main_local:app --reload --port 8000
Render : uvicorn main_local:app --host 0.0.0.0 --port $PORT
"""
from fastapi import FastAPI, Depends, HTTPException, Request, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, date as _date
from typing import Optional, List
import uuid, os, random, string, secrets, smtplib, ssl, asyncio, urllib.request, urllib.error, base64, json as _json, calendar
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
    ReportFormAnswer, ActivityLog, Notification, Region, ActiveSession, Department,
    ReportPhoto
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, distinct, text, case

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

def superadmin_only(u: User = Depends(current_user)):
    if u.role != "superadmin":
        raise HTTPException(403, "Réservé au super administrateur")
    return u


async def journaliser(db: AsyncSession, user: User, action: str, details: dict = None,
                       branch_id: str = None, request: Request = None):
    """Enregistre une entrée dans le journal d'activité. Best-effort : une erreur ici
    ne doit jamais faire échouer l'action métier en cours."""
    try:
        ip = None
        if request is not None:
            ip = request.headers.get("x-forwarded-for", request.client.host if request.client else None)
            if ip and "," in ip:
                ip = ip.split(",")[0].strip()
        db.add(ActivityLog(
            user_id=user.id if user else None,
            branch_id=branch_id,
            action=action,
            details=details or {},
            ip_address=ip,
        ))
        await db.flush()
    except Exception as e:
        print(f"⚠️ journaliser: {type(e).__name__}: {e}")

# ── Démarrage + auto-seed ─────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Créer les tables SQLite
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # 2. Migrations — ajouter colonnes si absentes (SQLite ALTER TABLE)
    async with engine.begin() as conn:
        for col, typedef in [
            ("plain_password", "TEXT"),
            ("region_id",      "INTEGER REFERENCES regions(id)"),
            ("department_id",  "INTEGER REFERENCES departments(id)"),
        ]:
            try:
                await conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {typedef}"))
            except Exception:
                pass  # colonne déjà présente
    # 3. Auto-seed si la base est vide
    await auto_seed()
    # 4. Auto-créer les branches manquantes (1 par département)
    try:
        async with AsyncSessionLocal() as db:
            depts = (await db.execute(select(Department))).scalars().all()
            regions = {r.id: r for r in (await db.execute(select(Region))).scalars().all()}
            existing_dept_ids = {
                b.department_id
                for b in (await db.execute(select(Branch))).scalars().all()
                if b.department_id
            }
            created = 0
            for dept in depts:
                if dept.id not in existing_dept_ids:
                    reg = regions.get(dept.region_id)
                    db.add(Branch(
                        code=f"CODISS-{dept.code}",
                        name=f"CODISS {dept.name_fr}",
                        city=dept.name_fr,
                        region_id=dept.region_id,
                        department_id=dept.id,
                        status="pending",
                        address=f"{dept.name_fr}, {reg.name_fr if reg else ''}, Cote d'Ivoire",
                    ))
                    created += 1
            if created:
                await db.commit()
                print(f"✅ {created} branches auto-créées depuis les départements")
            else:
                print("✅ Toutes les branches existent déjà")
    except Exception as e:
        print(f"⚠️  Auto-branches erreur : {type(e).__name__}: {e}")
    global _backup_task_handle
    _backup_task_handle = asyncio.create_task(_backup_scheduler_loop())
    yield
    if _backup_task_handle:
        _backup_task_handle.cancel()
    await engine.dispose()


# ══════════════════════════════════════════════════════
# PERSISTANCE GITHUB — Sauvegarde / Restauration users
# ══════════════════════════════════════════════════════
_GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")  # Définir GITHUB_TOKEN dans Render env vars
_GH_REPO  = "tolobayounousaa225-prog/codiss-cartographie"
_GH_FILE  = "data/backup_users.json"

def _gh_api(method, payload=None, file_path=None):
    """Appel synchrone GitHub API (appellé via asyncio.to_thread)."""
    path = file_path or _GH_FILE
    url = f"https://api.github.com/repos/{_GH_REPO}/contents/{path}"
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
    """Sauvegarde tous les utilisateurs non-superadmin sur GitHub.
    Lit directement depuis SQLite3 (sync) pour éviter tout problème d'isolation.
    """
    if not _GH_TOKEN: return
    try:
        def _read_users_sync():
            import sqlite3 as _sqlite3
            db_path = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "codiss_local.db"))
            conn = _sqlite3.connect(db_path)
            conn.row_factory = _sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT email, password_hash, plain_password, full_name, phone, role, language, "
                "is_active, must_set_password, region_id, department_id FROM users "
                "WHERE role != 'superadmin' ORDER BY created_at"
            )
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return rows

        users_data = await asyncio.to_thread(_read_users_sync)
        # Normaliser les types
        for u in users_data:
            u["language"] = u.get("language") or "fr"
            u["is_active"] = bool(u.get("is_active", 1))
            u["must_set_password"] = bool(u.get("must_set_password", 0))

        print(f"📋 Backup: {len(users_data)} utilisateurs trouvés en DB")
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

async def restore_users_from_github():
    """Restaure les utilisateurs depuis GitHub au démarrage (session propre)."""
    if not _GH_TOKEN:
        print("⚠️  GITHUB_TOKEN non défini — restauration ignorée"); return
    try:
        def _fetch():
            res = _gh_api("GET")
            if not res or "content" not in res: return []
            raw = base64.b64decode(res["content"].replace("\n","")).decode()
            return _json.loads(raw)

        users_data = await asyncio.to_thread(_fetch)
        if not users_data:
            print("GitHub: aucun utilisateur à restaurer"); return

        async with AsyncSessionLocal() as db:
            restored = 0
            for ud in users_data:
                ex = (await db.execute(select(User).where(User.email == ud["email"]))).scalar_one_or_none()
                if ex: continue
                db.add(User(
                    email=ud["email"], password_hash=ud["password_hash"],
                    plain_password=ud.get("plain_password"),
                    full_name=ud["full_name"], phone=ud.get("phone"),
                    role=ud.get("role","branch"), language=ud.get("language","fr"),
                    is_active=ud.get("is_active", True),
                    must_set_password=ud.get("must_set_password", False),
                    region_id=ud.get("region_id"),
                    department_id=ud.get("department_id"),
                ))
                restored += 1
            if restored > 0:
                await db.commit()
                print(f"✅ GitHub restauration: {restored} utilisateurs restaurés")
            else:
                print(f"GitHub: tous les {len(users_data)} users déjà présents")
    except Exception as e:
        print(f"⚠️  restore_users_from_github: {type(e).__name__}: {e}")


def _serial(v):
    """Sérialise les types non-JSON natifs (dates, bytes) pour l'export."""
    if isinstance(v, (datetime, _date)):
        return v.isoformat()
    if isinstance(v, bytes):
        return base64.b64encode(v).decode("ascii")
    return v


def _dump_all(model, exclude=()):
    """Retourne toutes les lignes d'un modèle sous forme de dicts sérialisables."""
    async def _run(db):
        rows = (await db.execute(select(model))).scalars().all()
        out = []
        for obj in rows:
            d = {}
            for col in model.__table__.columns:
                if col.name in exclude:
                    continue
                d[col.name] = _serial(getattr(obj, col.name))
            out.append(d)
        return out
    return _run


_GH_FILE_FULL = "data/backup_complete.json"
_last_full_backup_info = {"date": None, "ok": None, "compteurs": None}


async def _build_full_backup_dict():
    """Construit le dict d'export complet (mêmes données que /api/admin/sauvegarde)."""
    async with AsyncSessionLocal() as db:
        return {
            "meta": {
                "application": "CODISS Cartographie",
                "genere_le": datetime.utcnow().isoformat(),
                "genere_par": "sauvegarde_automatique",
                "version": 1,
            },
            "regions": await _dump_all(Region)(db),
            "departments": await _dump_all(Department)(db),
            "users": await _dump_all(User)(db),
            "branches": await _dump_all(Branch)(db),
            "branch_users": await _dump_all(BranchUser)(db),
            "presence_reports": await _dump_all(PresenceReport)(db),
            "report_form_answers": await _dump_all(ReportFormAnswer)(db),
            "report_photos": await _dump_all(ReportPhoto)(db),
            "notifications": await _dump_all(Notification)(db),
        }


async def backup_complete_to_github():
    """Pousse une sauvegarde JSON complète de toute la base vers GitHub
    (fichier data/backup_complete.json, écrasé à chaque exécution).
    Filet de sécurité contre une erreur humaine ou un incident, en complément
    du disque persistant Render."""
    if not _GH_TOKEN:
        print("⚠️  GITHUB_TOKEN non défini — sauvegarde automatique ignorée")
        return
    try:
        data = await _build_full_backup_dict()
        compteurs = {k: len(v) for k, v in data.items() if isinstance(v, list)}
        encoded = base64.b64encode(
            _json.dumps(data, ensure_ascii=False).encode()
        ).decode()

        def _push():
            existing = _gh_api("GET", file_path=_GH_FILE_FULL)
            sha = existing.get("sha") if existing else None
            resume = ", ".join(f"{k}:{v}" for k, v in compteurs.items())
            payload = {
                "message": f"backup complet auto — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC ({resume})",
                "content": encoded,
            }
            if sha: payload["sha"] = sha
            return _gh_api("PUT", payload, file_path=_GH_FILE_FULL)

        res = await asyncio.to_thread(_push)
        ok = bool(res)
        _last_full_backup_info["date"] = datetime.utcnow().isoformat()
        _last_full_backup_info["ok"] = ok
        _last_full_backup_info["compteurs"] = compteurs
        if ok:
            print(f"✅ Sauvegarde automatique complète poussée sur GitHub ({compteurs})")
        else:
            print("⚠️  Sauvegarde automatique complète : échec de l'envoi GitHub")
    except Exception as e:
        _last_full_backup_info["date"] = datetime.utcnow().isoformat()
        _last_full_backup_info["ok"] = False
        print(f"⚠️  backup_complete_to_github: {type(e).__name__}: {e}")


_BACKUP_INTERVAL_SECONDS = int(os.environ.get("BACKUP_INTERVAL_HOURS", "24")) * 3600
_backup_task_handle = None


async def _backup_scheduler_loop():
    """Boucle de fond : sauvegarde complète automatique à intervalle régulier.
    Le premier passage est différé de 2 minutes pour laisser l'app démarrer sereinement."""
    await asyncio.sleep(120)
    while True:
        await backup_complete_to_github()
        await asyncio.sleep(_BACKUP_INTERVAL_SECONDS)

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
                await restore_users_from_github()
                return
            from seed_db import do_seed
            await do_seed(db)
            await db.commit()
            print("✅ Base de données initialisée automatiquement.")
            # Restaurer les utilisateurs sauvegardés sur GitHub
            await restore_users_from_github()
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
        content={"status": "ok", "mode": DB_MODE, "version": "departments-fix"},
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
    await journaliser(db, u, "connexion", {"role": u.role}, branch_id=branch_id, request=request)
    await db.commit()
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
async def me(u: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    region_name = None
    dept_name   = None
    if u.region_id:
        reg = await db.get(Region, u.region_id)
        if reg: region_name = reg.name_fr
    if u.department_id:
        dept = await db.get(Department, u.department_id)
        if dept: dept_name = dept.name_fr
    return {
        "id": u.id, "email": u.email, "full_name": u.full_name,
        "role": u.role, "language": u.language, "is_active": u.is_active,
        "region_id": u.region_id, "region_name": region_name,
        "department_id": u.department_id, "department_name": dept_name,
    }

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


@app.get("/api/branches/{bid}/fiche")
async def get_branch_fiche(bid: str, db: AsyncSession = Depends(get_db), u: User = Depends(current_user)):
    """Fiche complète d'un secrétariat : infos, région/département, secrétaire(s) assigné(s),
    historique des rapports avec compteur de photos, statistiques d'activité."""
    b = await db.get(Branch, bid)
    if not b:
        raise HTTPException(404, "Branche introuvable")

    region = await db.get(Region, b.region_id) if b.region_id else None
    department = await db.get(Department, b.department_id) if b.department_id else None

    # Secrétaire(s) assigné(s) à cette branche
    links = (await db.execute(select(BranchUser).where(BranchUser.branch_id == bid))).scalars().all()
    secretaires = []
    for link in links:
        user = await db.get(User, link.user_id)
        if user:
            secretaires.append({
                "id": user.id, "full_name": user.full_name, "email": user.email,
                "phone": user.phone, "is_active": user.is_active,
                "last_login": user.last_login.isoformat() if user.last_login else None,
            })

    # Historique des rapports (avec compteur de photos)
    reports = (await db.execute(
        select(PresenceReport).where(PresenceReport.branch_id == bid).order_by(PresenceReport.created_at.desc())
    )).scalars().all()
    reports_data = []
    for r in reports:
        nb_photos = (await db.execute(
            select(func.count()).select_from(ReportPhoto).where(ReportPhoto.report_id == r.id)
        )).scalar()
        reports_data.append({
            "id": r.id, "title": r.title, "report_type": r.report_type, "status": r.status,
            "activity_count": r.activity_count,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "period_start": str(r.period_start) if r.period_start else None,
            "period_end": str(r.period_end) if r.period_end else None,
            "nb_photos": nb_photos,
        })

    total_reports = len(reports_data)
    approved = sum(1 for r in reports_data if r["status"] == "approved")
    pending = sum(1 for r in reports_data if r["status"] == "submitted")
    total_activities = sum(r["activity_count"] or 0 for r in reports_data)
    last_report_date = reports_data[0]["created_at"] if reports_data else None

    return {
        "branch": _branch_dict(b),
        "region": {"id": region.id, "name_fr": region.name_fr, "code": region.code} if region else None,
        "department": {"id": department.id, "name_fr": department.name_fr} if department else None,
        "secretaires": secretaires,
        "reports": reports_data,
        "stats": {
            "total_reports": total_reports,
            "approved_reports": approved,
            "pending_reports": pending,
            "total_activities": total_activities,
            "last_report_date": last_report_date,
        },
    }

@app.post("/api/branches", status_code=201)
async def create_branch(data: dict, request: Request, db: AsyncSession = Depends(get_db), u=Depends(admin_only)):
    ex = await db.execute(select(Branch).where(Branch.code == data.get("code","")))
    if ex.scalar_one_or_none(): raise HTTPException(400, "Code déjà utilisé")
    b = Branch(**{k: v for k, v in data.items() if hasattr(Branch, k)})
    db.add(b)
    await db.flush()
    await journaliser(db, u, "creation_branche", {"nom": b.name, "code": b.code}, branch_id=b.id, request=request)
    await db.commit()
    await db.refresh(b)
    return _branch_dict(b)

@app.patch("/api/branches/{bid}")
async def update_branch(bid: str, data: dict, db: AsyncSession = Depends(get_db), _=Depends(admin_only)):
    b = await db.get(Branch, bid)
    if not b: raise HTTPException(404)
    for k, v in data.items():
        if hasattr(b, k) and v is not None: setattr(b, k, v)
    await db.commit()
    await db.refresh(b)
    return _branch_dict(b)

@app.post("/api/branches/{bid}/verify")
async def verify_branch(bid: str, request: Request, db: AsyncSession = Depends(get_db), u=Depends(admin_only)):
    b = await db.get(Branch, bid)
    if not b: raise HTTPException(404)
    b.is_verified = True; b.verified_at = datetime.utcnow()
    b.verified_by = u.id; b.status = "active"
    await journaliser(db, u, "verification_branche", {"nom": b.name}, branch_id=b.id, request=request)
    await db.commit()
    return {"message": f"{b.name} vérifiée et activée"}

@app.post("/api/branches/{bid}/assign-user")
async def assign_user(bid: str, user_id: str, request: Request, role: str = "secretary", db: AsyncSession = Depends(get_db), u=Depends(admin_only)):
    # Vérifier que la branche existe
    b = await db.get(Branch, bid)
    if not b: raise HTTPException(404, "Branche introuvable")
    # Vérifier que l'utilisateur existe
    assigned_user = await db.get(User, user_id)
    if not assigned_user: raise HTTPException(404, "Utilisateur introuvable")
    # Supprimer l'éventuelle liaison précédente de cet utilisateur
    existing = await db.execute(select(BranchUser).where(BranchUser.user_id == user_id))
    old = existing.scalar_one_or_none()
    if old:
        await db.delete(old)
    bu = BranchUser(user_id=user_id, branch_id=bid, role=role)
    db.add(bu)
    await journaliser(db, u, "affectation_secretaire", {"secretaire": assigned_user.full_name, "branche": b.name},
                       branch_id=bid, request=request)
    await db.commit()
    return {"ok": True, "user": assigned_user.full_name, "branch": b.name}

@app.get("/api/admin/branches")
async def list_branches_admin(db: AsyncSession = Depends(get_db), _=Depends(admin_only)):
    """Liste enrichie des branches pour l'admin (région, département, secrétaire)."""
    branches = (await db.execute(select(Branch).order_by(Branch.region_id, Branch.name))).scalars().all()
    regions_map  = {r.id: r.name_fr for r in (await db.execute(select(Region))).scalars().all()}
    depts_map    = {d.id: d.name_fr for d in (await db.execute(select(Department))).scalars().all()}
    # Charger les secrétaires associés
    bu_rows = (await db.execute(select(BranchUser))).scalars().all()
    users_map = {u.id: u for u in (await db.execute(select(User))).scalars().all()}
    secretaire_by_branch = {}
    for bu in bu_rows:
        if bu.role == "secretary":
            u = users_map.get(bu.user_id)
            if u:
                secretaire_by_branch[bu.branch_id] = {"name": u.full_name, "email": u.email}
    result = []
    for b in branches:
        d = _branch_dict(b)
        d["region_name"]    = regions_map.get(b.region_id, "")
        d["dept_name"]      = depts_map.get(b.department_id, "")
        d["secretaire"]     = secretaire_by_branch.get(b.id)
        d["notes"]          = b.notes
        result.append(d)
    return result

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


# ══════════════════════════════════════════════════════
# PHOTOS DE RAPPORT
# ══════════════════════════════════════════════════════
PHOTO_TYPES_AUTORISES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
PHOTO_MAX_TAILLE = 8 * 1024 * 1024  # 8 Mo


async def _report_accessible(rp: PresenceReport, u: User, db: AsyncSession) -> bool:
    """Un rapport est accessible : à tout admin/superadmin, ou au secrétaire de la branche concernée."""
    if u.role in ("superadmin", "admin", "viewer"):
        return True
    if u.role == "branch":
        bu = (await db.execute(select(BranchUser).where(BranchUser.user_id == u.id))).scalar_one_or_none()
        return bool(bu and bu.branch_id == rp.branch_id)
    return False


@app.post("/api/reports/{rid}/photos", status_code=201)
async def upload_report_photo(
    rid: str,
    legende: str = Form(None),
    fichier: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    u: User = Depends(current_user),
):
    rp = await db.get(PresenceReport, rid)
    if not rp:
        raise HTTPException(404, "Rapport introuvable")
    if not await _report_accessible(rp, u, db):
        raise HTTPException(403, "Accès refusé à ce rapport")

    type_mime = (fichier.content_type or "").lower()
    if type_mime not in PHOTO_TYPES_AUTORISES:
        raise HTTPException(400, "Format non autorisé (image JPG, PNG, WEBP ou GIF)")
    contenu = await fichier.read()
    if not contenu:
        raise HTTPException(400, "Fichier vide")
    if len(contenu) > PHOTO_MAX_TAILLE:
        raise HTTPException(400, "Image trop volumineuse (maximum 8 Mo)")

    photo = ReportPhoto(
        report_id=rid,
        nom_fichier=fichier.filename or f"photo{PHOTO_TYPES_AUTORISES[type_mime]}",
        type_mime=type_mime,
        taille=len(contenu),
        contenu=contenu,
        legende=(legende or "").strip() or None,
        uploaded_by=u.id,
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    return {
        "id": photo.id, "nom_fichier": photo.nom_fichier, "type_mime": photo.type_mime,
        "taille": photo.taille, "legende": photo.legende,
        "created_at": photo.created_at.isoformat() if photo.created_at else None,
    }


@app.get("/api/reports/{rid}/photos")
async def list_report_photos(rid: str, db: AsyncSession = Depends(get_db), u: User = Depends(current_user)):
    rp = await db.get(PresenceReport, rid)
    if not rp:
        raise HTTPException(404, "Rapport introuvable")
    if not await _report_accessible(rp, u, db):
        raise HTTPException(403, "Accès refusé à ce rapport")
    photos = (await db.execute(
        select(ReportPhoto).where(ReportPhoto.report_id == rid).order_by(ReportPhoto.created_at)
    )).scalars().all()
    return [{
        "id": p.id, "nom_fichier": p.nom_fichier, "type_mime": p.type_mime,
        "taille": p.taille, "legende": p.legende,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    } for p in photos]


@app.get("/api/report-photos/{photo_id}/fichier")
async def get_report_photo_file(photo_id: str, db: AsyncSession = Depends(get_db), u: User = Depends(current_user)):
    photo = await db.get(ReportPhoto, photo_id)
    if not photo:
        raise HTTPException(404, "Photo introuvable")
    rp = await db.get(PresenceReport, photo.report_id)
    if not rp or not await _report_accessible(rp, u, db):
        raise HTTPException(403, "Accès refusé")
    nom_ascii = "".join(c if c.isascii() and c not in '"\\' else "_" for c in photo.nom_fichier)
    return Response(
        content=photo.contenu, media_type=photo.type_mime,
        headers={"Content-Disposition": f'inline; filename="{nom_ascii}"'},
    )


@app.delete("/api/report-photos/{photo_id}")
async def delete_report_photo(photo_id: str, db: AsyncSession = Depends(get_db), u: User = Depends(current_user)):
    photo = await db.get(ReportPhoto, photo_id)
    if not photo:
        raise HTTPException(404, "Photo introuvable")
    rp = await db.get(PresenceReport, photo.report_id)
    if not rp or not await _report_accessible(rp, u, db):
        raise HTTPException(403, "Accès refusé")
    await db.delete(photo)
    await db.commit()
    return {"ok": True}

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
async def review_report(rid: str, data: dict, request: Request, db: AsyncSession = Depends(get_db), u=Depends(admin_only)):
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
    await journaliser(db, u, "revue_rapport", {"titre": rp.title, "statut": status}, branch_id=rp.branch_id, request=request)
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

@app.get("/api/regions/{code}/departments")
async def get_region_departments(code: str, db: AsyncSession = Depends(get_db), _=Depends(current_user)):
    """Retourne les départements/communes d'une région donnée (par code)."""
    region = (await db.execute(select(Region).where(Region.code == code.upper()))).scalar_one_or_none()
    if not region:
        raise HTTPException(404, f"Région '{code}' introuvable")
    depts = (await db.execute(
        select(Department).where(Department.region_id == region.id).order_by(Department.name_fr)
    )).scalars().all()
    return {
        "region_code": region.code,
        "region_name": region.name_fr,
        "district": region.district,
        "departments": [{"code": d.code, "name_fr": d.name_fr, "name_en": d.name_en} for d in depts]
    }

@app.get("/api/regions/all-with-departments")
@app.get("/api/map/regions-with-departments")
async def all_regions_with_departments(db: AsyncSession = Depends(get_db), _=Depends(current_user)):
    """Retourne toutes les régions avec leurs départements (IDs inclus)."""
    regions = (await db.execute(select(Region).order_by(Region.name_fr))).scalars().all()
    result = []
    for r in regions:
        depts = (await db.execute(
            select(Department).where(Department.region_id == r.id).order_by(Department.name_fr)
        )).scalars().all()
        result.append({
            "id": r.id, "code": r.code, "name_fr": r.name_fr, "name_en": r.name_en,
            "district": r.district,
            "departments": [{"id": d.id, "code": d.code, "name_fr": d.name_fr} for d in depts]
        })
    return result

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
@app.get("/api/viewer/stats")
async def viewer_stats(db: AsyncSession = Depends(get_db), _=Depends(current_user)):
    """Stats basiques accessibles à tous les rôles authentifiés (viewer inclus)."""
    total_branches  = (await db.execute(select(func.count()).select_from(Branch))).scalar()
    active_branches = (await db.execute(select(func.count()).select_from(Branch).where(Branch.status == "active"))).scalar()
    total_regions   = (await db.execute(select(func.count()).select_from(Region))).scalar()
    coverage        = (await db.execute(select(func.count()).select_from(Branch).where(Branch.status == "active", Branch.region_id != None).distinct())).scalar()
    return {
        "total_branches": total_branches,
        "active_branches": active_branches,
        "total_regions": total_regions,
        "coverage_regions": coverage,
    }

@app.get("/api/admin/stats")
async def admin_stats(db: AsyncSession = Depends(get_db), _=Depends(admin_only)):
    # Statuts des branches
    branch_rows = (await db.execute(select(Branch.status, func.count()).group_by(Branch.status))).all()
    branch_by_status = {r[0]: r[1] for r in branch_rows}
    # Rapports des 6 derniers mois
    six_months_ago = datetime.utcnow().replace(day=1) - timedelta(days=150)
    rpt_rows = (await db.execute(
        select(PresenceReport.created_at).where(PresenceReport.created_at >= six_months_ago)
    )).scalars().all()
    monthly = {}
    for dt in rpt_rows:
        if dt:
            key = dt.strftime("%Y-%m")
            monthly[key] = monthly.get(key, 0) + 1
    # Trier les 6 derniers mois
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

@app.get("/api/admin/department-coverage")
async def department_coverage(db: AsyncSession = Depends(get_db), _=Depends(current_user)):
    """Taux de couverture des départements par les Secrétaires actifs."""
    regions     = (await db.execute(select(Region).order_by(Region.name_fr))).scalars().all()
    departments = (await db.execute(select(Department).order_by(Department.name_fr))).scalars().all()
    # Départements ayant au moins un secrétaire actif
    covered_ids = set((await db.execute(
        select(User.department_id)
        .where(User.role == "branch", User.is_active == True, User.department_id != None)
        .distinct()
    )).scalars().all())
    total   = len(departments)
    covered = len(covered_ids)
    by_region = []
    for r in regions:
        r_depts   = [d for d in departments if d.region_id == r.id]
        r_covered = [d for d in r_depts if d.id in covered_ids]
        by_region.append({
            "region_id":    r.id,
            "region_code":  r.code,
            "region_name":  r.name_fr,
            "total_depts":  len(r_depts),
            "covered_depts": len(r_covered),
            "coverage_pct": round(len(r_covered) / len(r_depts) * 100) if r_depts else 0,
            "departments":  [{"id": d.id, "name": d.name_fr, "covered": d.id in covered_ids} for d in r_depts],
        })
    return {
        "total_departments":     total,
        "covered_departments":   covered,
        "uncovered_departments": total - covered,
        "coverage_pct":          round(covered / total * 100) if total else 0,
        "by_region":             by_region,
    }


@app.get("/api/admin/regions-ranking")
async def regions_ranking(db: AsyncSession = Depends(get_db), _=Depends(admin_only)):
    """Classement des régions par nombre de branches (actives + total), du mieux couvert au moins couvert."""
    regions = (await db.execute(select(Region).order_by(Region.name_fr))).scalars().all()
    branch_rows = (await db.execute(
        select(Branch.region_id, Branch.status, func.count()).group_by(Branch.region_id, Branch.status)
    )).all()
    counts = {}
    for region_id, status, cnt in branch_rows:
        if region_id is None:
            continue
        counts.setdefault(region_id, {"active": 0, "pending": 0, "other": 0, "total": 0})
        if status == "active":
            counts[region_id]["active"] += cnt
        elif status == "pending":
            counts[region_id]["pending"] += cnt
        else:
            counts[region_id]["other"] += cnt
        counts[region_id]["total"] += cnt

    ranking = []
    for r in regions:
        c = counts.get(r.id, {"active": 0, "pending": 0, "other": 0, "total": 0})
        ranking.append({
            "region_id": r.id, "code": r.code, "name_fr": r.name_fr, "name_en": r.name_en,
            "district": r.district,
            "active_branches": c["active"], "pending_branches": c["pending"],
            "other_branches": c["other"], "total_branches": c["total"],
        })
    ranking.sort(key=lambda x: x["total_branches"], reverse=True)
    top5 = ranking[:5]
    bottom5 = sorted(ranking, key=lambda x: x["total_branches"])[:5]
    return {"ranking": ranking, "top5": top5, "bottom5": bottom5}


# ══════════════════════════════════════════════════════
# JOURNAL D'ACTIVITÉ
# ══════════════════════════════════════════════════════
ACTION_LABELS = {
    "connexion": "🔑 Connexion",
    "creation_branche": "🏛 Création de branche",
    "verification_branche": "✅ Vérification de branche",
    "rejet_branche": "❌ Rejet de branche",
    "affectation_secretaire": "👤 Affectation de secrétaire",
    "creation_utilisateur": "➕ Création d'utilisateur",
    "suppression_utilisateur": "🗑 Suppression d'utilisateur",
    "revue_rapport": "📄 Revue de rapport",
    "sauvegarde_auto_manuelle": "💾 Sauvegarde automatique déclenchée",
}


@app.get("/api/admin/journal")
async def get_journal(
    action: str = None, limit: int = 100, offset: int = 0,
    db: AsyncSession = Depends(get_db), _=Depends(admin_only),
):
    """Journal d'activité paginé, filtrable par type d'action."""
    limit = max(1, min(limit, 200))
    q = select(ActivityLog)
    if action:
        q = q.where(ActivityLog.action == action)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar()
    rows = (await db.execute(
        q.order_by(ActivityLog.created_at.desc()).limit(limit).offset(offset)
    )).scalars().all()

    user_ids = {r.user_id for r in rows if r.user_id}
    branch_ids = {r.branch_id for r in rows if r.branch_id}
    users_map = {}
    if user_ids:
        for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all():
            users_map[u.id] = u.full_name
    branches_map = {}
    if branch_ids:
        for b in (await db.execute(select(Branch).where(Branch.id.in_(branch_ids)))).scalars().all():
            branches_map[b.id] = b.name

    entries = [{
        "id": r.id,
        "action": r.action,
        "action_label": ACTION_LABELS.get(r.action, r.action),
        "details": r.details or {},
        "user_name": users_map.get(r.user_id, "Système"),
        "branch_name": branches_map.get(r.branch_id),
        "ip_address": r.ip_address,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]

    return {"total": total, "limit": limit, "offset": offset, "entries": entries,
            "action_types": list(ACTION_LABELS.keys())}


# ══════════════════════════════════════════════════════
# SAUVEGARDE & RESTAURATION COMPLÈTES
# ══════════════════════════════════════════════════════
@app.get("/api/admin/sauvegarde")
async def sauvegarde_complete(db: AsyncSession = Depends(get_db), current: User = Depends(superadmin_only)):
    """Export JSON complet de toute la base CODISS (y compris les photos de rapports en base64),
    pour archivage local avant une migration ou en sauvegarde régulière."""
    data = {
        "meta": {
            "application": "CODISS Cartographie",
            "genere_le": datetime.utcnow().isoformat(),
            "genere_par": current.full_name,
            "version": 1,
        },
        "regions": await _dump_all(Region)(db),
        "departments": await _dump_all(Department)(db),
        "users": await _dump_all(User)(db),
        "branches": await _dump_all(Branch)(db),
        "branch_users": await _dump_all(BranchUser)(db),
        "presence_reports": await _dump_all(PresenceReport)(db),
        "report_form_answers": await _dump_all(ReportFormAnswer)(db),
        "report_photos": await _dump_all(ReportPhoto)(db),  # contenu binaire inclus en base64
        "notifications": await _dump_all(Notification)(db),
    }
    contenu = _json.dumps(data, ensure_ascii=False, indent=2)
    nom = f"sauvegarde_codiss_{_date.today().strftime('%Y%m%d_%H%M')}.json"
    return Response(
        content=contenu,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nom}"'},
    )


def _deserial_dates(d: dict, date_fields=(), datetime_fields=()):
    """Reconvertit les chaînes ISO en objets date/datetime pour la restauration."""
    out = dict(d)
    for f in date_fields:
        if out.get(f):
            out[f] = _date.fromisoformat(out[f])
    for f in datetime_fields:
        if out.get(f):
            out[f] = datetime.fromisoformat(out[f])
    return out


@app.post("/api/admin/restaurer")
async def restaurer_complete(
    payload: dict,
    mode: str = "fusion",
    db: AsyncSession = Depends(get_db),
    current: User = Depends(superadmin_only),
):
    """Restaure une sauvegarde JSON complète.
    mode='fusion' (défaut) : n'ajoute que les enregistrements dont l'id n'existe pas encore (ne touche jamais l'existant).
    mode='remplacer' : vide chaque table avant de réinjecter (destructif, à utiliser uniquement pour une migration à froid)."""
    if mode not in ("fusion", "remplacer"):
        raise HTTPException(400, "mode invalide (fusion ou remplacer)")

    compteurs = {}

    async def _restore_table(model, rows, date_fields=(), datetime_fields=(), skip_existing_check=False, unique_field=None):
        if not rows:
            compteurs[model.__tablename__] = 0
            return
        if mode == "remplacer":
            await db.execute(model.__table__.delete())
            await db.flush()
        ajoutes = 0
        for row in rows:
            row = _deserial_dates(row, date_fields, datetime_fields)
            # Reconvertir les champs binaires base64 -> bytes
            for col in model.__table__.columns:
                if col.type.python_type is bytes and isinstance(row.get(col.name), str):
                    row[col.name] = base64.b64decode(row[col.name])
            if mode == "fusion" and not skip_existing_check:
                if unique_field:
                    existing = (await db.execute(
                        select(model).where(getattr(model, unique_field) == row.get(unique_field))
                    )).scalar_one_or_none()
                else:
                    pk_col = list(model.__table__.primary_key.columns)[0].name
                    existing = await db.get(model, row.get(pk_col))
                if existing:
                    continue
            db.add(model(**row))
            ajoutes += 1
        await db.flush()
        compteurs[model.__tablename__] = ajoutes

    try:
        await _restore_table(Region, payload.get("regions", []), datetime_fields=("created_at",), unique_field="code")
        await _restore_table(Department, payload.get("departments", []), datetime_fields=("created_at",), unique_field="code")
        await _restore_table(User, payload.get("users", []),
                              datetime_fields=("last_login", "created_at", "updated_at", "setup_token_expires"),
                              unique_field="email")
        await db.flush()
        await _restore_table(Branch, payload.get("branches", []),
                              date_fields=("founded_date",), datetime_fields=("verified_at", "created_at", "updated_at"),
                              unique_field="code")
        await _restore_table(BranchUser, payload.get("branch_users", []), datetime_fields=("created_at",),
                              skip_existing_check=True)
        await _restore_table(PresenceReport, payload.get("presence_reports", []),
                              date_fields=("period_start", "period_end"),
                              datetime_fields=("reviewed_at", "viewed_at", "created_at", "updated_at"))
        await _restore_table(ReportFormAnswer, payload.get("report_form_answers", []), datetime_fields=("created_at",),
                              skip_existing_check=True)
        await _restore_table(ReportPhoto, payload.get("report_photos", []), datetime_fields=("created_at",))
        await _restore_table(Notification, payload.get("notifications", []), datetime_fields=("created_at",))
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(400, f"Échec de la restauration : {type(e).__name__}: {e}")

    return {"ok": True, "mode": mode, "compteurs": compteurs}


@app.get("/api/admin/sauvegarde-auto/statut")
async def statut_sauvegarde_auto(_=Depends(superadmin_only)):
    """État de la sauvegarde automatique programmée : dernière exécution, résultat, intervalle."""
    return {
        "activee": bool(_GH_TOKEN),
        "intervalle_heures": _BACKUP_INTERVAL_SECONDS // 3600,
        "derniere_execution": _last_full_backup_info["date"],
        "derniere_reussie": _last_full_backup_info["ok"],
        "derniers_compteurs": _last_full_backup_info["compteurs"],
    }


@app.post("/api/admin/sauvegarde-auto/declencher")
async def declencher_sauvegarde_auto(current: User = Depends(superadmin_only), db: AsyncSession = Depends(get_db)):
    """Déclenche immédiatement une sauvegarde automatique complète vers GitHub (hors attente du prochain cycle)."""
    if not _GH_TOKEN:
        raise HTTPException(400, "GITHUB_TOKEN non configuré sur ce déploiement — sauvegarde automatique indisponible")
    await backup_complete_to_github()
    await journaliser(db, current, "sauvegarde_auto_manuelle", {"reussie": _last_full_backup_info["ok"]})
    await db.commit()
    if not _last_full_backup_info["ok"]:
        raise HTTPException(502, "La sauvegarde vers GitHub a échoué (voir les logs serveur)")
    return _last_full_backup_info


def _csv_response(headers: list, rows: list, filename: str):
    """Construit une réponse CSV (UTF-8 avec BOM pour Excel)."""
    import io as _io, csv as _csv
    buf = _io.StringIO()
    writer = _csv.writer(buf, delimiter=";")
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    content = "\ufeff" + buf.getvalue()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/admin/export/branches.csv")
async def export_branches_csv(db: AsyncSession = Depends(get_db), _=Depends(admin_only)):
    branches = (await db.execute(select(Branch).order_by(Branch.name))).scalars().all()
    regions = {r.id: r.name_fr for r in (await db.execute(select(Region))).scalars().all()}
    rows = [[
        b.code, b.name, b.city or "", regions.get(b.region_id, ""), b.status,
        "Oui" if b.is_verified else "Non", b.member_count or 0,
        b.president_name or "", b.president_phone or "",
        b.latitude or "", b.longitude or "",
    ] for b in branches]
    headers = ["Code", "Nom", "Ville", "Région", "Statut", "Vérifiée", "Membres",
               "Président", "Téléphone président", "Latitude", "Longitude"]
    return _csv_response(headers, rows, "branches_codiss.csv")


@app.get("/api/admin/export/reports.csv")
async def export_reports_csv(db: AsyncSession = Depends(get_db), _=Depends(admin_only)):
    reports = (await db.execute(select(PresenceReport).order_by(PresenceReport.created_at.desc()))).scalars().all()
    branches = {b.id: b.name for b in (await db.execute(select(Branch))).scalars().all()}
    rows = [[
        r.id, branches.get(r.branch_id, ""), r.report_type or "", r.status,
        r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
        r.latitude or "", r.longitude or "",
    ] for r in reports]
    headers = ["ID", "Branche", "Type", "Statut", "Date", "Latitude", "Longitude"]
    return _csv_response(headers, rows, "rapports_codiss.csv")


@app.get("/api/admin/export/users.csv")
async def export_users_csv(db: AsyncSession = Depends(get_db), _=Depends(admin_only)):
    users = (await db.execute(select(User).order_by(User.full_name))).scalars().all()
    regions = {r.id: r.name_fr for r in (await db.execute(select(Region))).scalars().all()}
    rows = [[
        u.full_name, u.email, u.role, regions.get(u.region_id, ""),
        "Actif" if u.is_active else "Inactif",
        u.last_login.strftime("%Y-%m-%d %H:%M") if getattr(u, "last_login", None) else "",
    ] for u in users]
    headers = ["Nom", "Email", "Rôle", "Région", "Statut", "Dernière connexion"]
    return _csv_response(headers, rows, "utilisateurs_codiss.csv")


@app.get("/api/admin/export/coverage.csv")
async def export_coverage_csv(db: AsyncSession = Depends(get_db), _=Depends(admin_only)):
    regions = (await db.execute(select(Region).order_by(Region.name_fr))).scalars().all()
    branch_rows = (await db.execute(
        select(Branch.region_id, func.count()).where(Branch.status.in_(["active", "pending"])).group_by(Branch.region_id)
    )).all()
    counts = {region_id: cnt for region_id, cnt in branch_rows}
    rows = [[r.code, r.name_fr, r.district or "", counts.get(r.id, 0)] for r in regions]
    headers = ["Code", "Région", "District", "Branches (actives + en attente)"]
    return _csv_response(headers, rows, "couverture_regionale_codiss.csv")

@app.get("/api/admin/secretaire-activity")
async def secretaire_activity(db: AsyncSession = Depends(get_db), _=Depends(admin_only)):
    """Classement des secrétaires par nombre de rapports soumis."""
    rows = (await db.execute(
        select(
            User.id, User.full_name, User.email, User.region_id, User.department_id, User.is_active,
            func.count(PresenceReport.id).label("total_reports"),
            func.sum(case((PresenceReport.status == "approved", 1), else_=0)).label("approved"),
            func.sum(case((PresenceReport.status == "submitted", 1), else_=0)).label("pending"),
            func.max(PresenceReport.created_at).label("last_report"),
        )
        .outerjoin(PresenceReport, PresenceReport.submitted_by == User.id)
        .where(User.role == "branch")
        .group_by(User.id)
        .order_by(func.count(PresenceReport.id).desc())
    )).all()

    regions_map = {r.id: r.name_fr for r in (await db.execute(select(Region))).scalars().all()}
    depts_map   = {d.id: d.name_fr for d in (await db.execute(select(Department))).scalars().all()}

    return [{
        "id": r.id, "full_name": r.full_name, "email": r.email,
        "region_name": regions_map.get(r.region_id, "—"),
        "department_name": depts_map.get(r.department_id, "—"),
        "is_active": r.is_active,
        "total_reports": r.total_reports or 0,
        "approved": int(r.approved or 0),
        "pending": int(r.pending or 0),
        "last_report": r.last_report.isoformat() if r.last_report else None,
    } for r in rows]

@app.get("/api/admin/users")
async def list_users(db: AsyncSession = Depends(get_db), _=Depends(admin_only)):
    users = (await db.execute(select(User).order_by(User.created_at.desc()))).scalars().all()
    # Charger les noms de régions et départements
    regions_map = {r.id: r.name_fr for r in (await db.execute(select(Region))).scalars().all()}
    depts_map   = {d.id: d.name_fr for d in (await db.execute(select(Department))).scalars().all()}
    return [{"id": u.id, "email": u.email, "full_name": u.full_name, "phone": u.phone,
             "role": u.role, "language": u.language, "is_active": u.is_active,
             "created_at": u.created_at.isoformat() if u.created_at else None,
             "last_login": u.last_login.isoformat() if u.last_login else None,
             "has_plain_password": bool(u.plain_password),
             "region_id": u.region_id,
             "region_name": regions_map.get(u.region_id) if u.region_id else None,
             "department_id": u.department_id,
             "department_name": depts_map.get(u.department_id) if u.department_id else None}
            for u in users]

async def _auto_link_branch(u, db: AsyncSession):
    """Si le user est secrétaire (role='branch') avec un département défini,
    lie automatiquement à la branche de ce département et active la branche."""
    if u.role != "branch" or not u.department_id:
        return
    branch = (await db.execute(
        select(Branch).where(Branch.department_id == u.department_id)
    )).scalar_one_or_none()
    if not branch:
        return
    # Supprimer toute ancienne liaison de cet utilisateur
    old_link = (await db.execute(
        select(BranchUser).where(BranchUser.user_id == u.id)
    )).scalar_one_or_none()
    if old_link:
        await db.delete(old_link)
    db.add(BranchUser(user_id=u.id, branch_id=branch.id, role="secretary"))
    branch.status = "active"
    await db.commit()

@app.post("/api/admin/users", status_code=201)
async def create_user(data: dict, request: Request, db: AsyncSession = Depends(get_db), admin_user=Depends(admin_only)):
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
            region_id=data.get("region_id") or None,
            department_id=data.get("department_id") or None,
        )
        db.add(u)
        await db.flush()
        await journaliser(db, admin_user, "creation_utilisateur", {"nom": u.full_name, "email": u.email, "role": u.role}, request=request)
        await db.commit()
        await db.refresh(u)
        await _auto_link_branch(u, db)
        await backup_users_to_github(db=db)
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
            region_id=data.get("region_id") or None,
            department_id=data.get("department_id") or None,
        )
        db.add(u)
        await db.flush()
        await journaliser(db, admin_user, "creation_utilisateur", {"nom": u.full_name, "email": u.email, "role": u.role, "invitation": True}, request=request)
        await db.commit()
        await db.refresh(u)
        await _auto_link_branch(u, db)
        await backup_users_to_github(db=db)
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

@app.put("/api/admin/users/{uid}")
async def update_user(uid: str, data: dict, db: AsyncSession = Depends(get_db), _=Depends(admin_only)):
    """Modifier nom, email, téléphone, région, département d'un utilisateur."""
    u = await db.get(User, uid)
    if not u: raise HTTPException(404, "Utilisateur introuvable")
    if u.role == "superadmin": raise HTTPException(403, "Impossible de modifier le superadmin")
    if "full_name" in data and data["full_name"].strip():
        u.full_name = data["full_name"].strip()
    if "email" in data and data["email"].strip():
        # Vérifier unicité email
        other = (await db.execute(select(User).where(User.email == data["email"].lower().strip(), User.id != uid))).scalar_one_or_none()
        if other: raise HTTPException(400, "Cet email est déjà utilisé par un autre compte")
        u.email = data["email"].lower().strip()
    if "phone" in data:
        u.phone = data.get("phone") or None
    if "region_id" in data:
        u.region_id = data.get("region_id") or None
    if "department_id" in data:
        u.department_id = data.get("department_id") or None
    await db.commit()
    await _auto_link_branch(u, db)
    await backup_users_to_github(db=db)
    return {"ok": True, "message": "Utilisateur mis à jour"}

@app.patch("/api/admin/users/{uid}/toggle-active")
async def toggle_user(uid: str, db: AsyncSession = Depends(get_db), _=Depends(admin_only)):
    u = await db.get(User, uid)
    if not u: raise HTTPException(404)
    if u.role == "superadmin":
        raise HTTPException(403, "Le compte super administrateur ne peut pas être désactivé")
    u.is_active = not u.is_active
    await db.commit()
    return {"is_active": u.is_active}


@app.patch("/api/admin/users/{uid}/role")
async def change_user_role(uid: str, data: dict, db: AsyncSession = Depends(get_db), u=Depends(admin_only)):
    target = await db.get(User, uid)
    if not target: raise HTTPException(404, "Utilisateur introuvable")
    if target.role == "superadmin":
        raise HTTPException(403, "Impossible de modifier le rôle du super administrateur")
    allowed = ["admin", "branch", "viewer"]
    new_role = data.get("role", "")
    if new_role not in allowed:
        raise HTTPException(400, f"Rôle invalide. Valeurs acceptées : {allowed}")
    target.role = new_role
    await db.commit()
    await backup_users_to_github(db=db)
    return {"id": target.id, "email": target.email, "role": target.role}

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


@app.patch("/api/admin/notifications/read-all")
async def mark_all_read(db: AsyncSession = Depends(get_db), u: User = Depends(current_user)):
    await db.execute(
        update(Notification).where(Notification.user_id == u.id, Notification.is_read == False).values(is_read=True)
    )
    await db.commit()
    return {"ok": True}


@app.delete("/api/admin/notifications/{nid}")
async def delete_notif(nid: str, db: AsyncSession = Depends(get_db), u: User = Depends(current_user)):
    n = await db.get(Notification, nid)
    if n and n.user_id == u.id:
        await db.delete(n)
        await db.commit()
    return {"ok": True}


@app.get("/api/search")
async def global_search(q: str, db: AsyncSession = Depends(get_db), u: User = Depends(current_user)):
    """Recherche transversale : branches, rapports, régions (et utilisateurs pour les admins)."""
    query = (q or "").strip()
    if len(query) < 2:
        return {"query": query, "branches": [], "reports": [], "regions": [], "users": []}
    like = f"%{query}%"

    branches_q = select(Branch).where(
        (Branch.name.ilike(like)) | (Branch.code.ilike(like)) | (Branch.city.ilike(like))
    ).limit(15)
    if u.role == "branch":
        bu = (await db.execute(select(BranchUser).where(BranchUser.user_id == u.id))).scalar_one_or_none()
        branches_q = branches_q.where(Branch.id == bu.branch_id) if bu else branches_q.where(Branch.id == None)
    branches = (await db.execute(branches_q)).scalars().all()

    reports_q = select(PresenceReport).where(PresenceReport.title.ilike(like)).order_by(PresenceReport.created_at.desc()).limit(15)
    if u.role == "branch":
        bu = (await db.execute(select(BranchUser).where(BranchUser.user_id == u.id))).scalar_one_or_none()
        reports_q = reports_q.where(PresenceReport.branch_id == bu.branch_id) if bu else reports_q.where(PresenceReport.branch_id == None)
    reports = (await db.execute(reports_q)).scalars().all()
    branch_names = {}
    if reports:
        bids = {r.branch_id for r in reports if r.branch_id}
        if bids:
            for b in (await db.execute(select(Branch).where(Branch.id.in_(bids)))).scalars().all():
                branch_names[b.id] = b.name

    regions = (await db.execute(
        select(Region).where((Region.name_fr.ilike(like)) | (Region.code.ilike(like))).limit(10)
    )).scalars().all()

    users = []
    if u.role in ("superadmin", "admin"):
        users = (await db.execute(
            select(User).where((User.full_name.ilike(like)) | (User.email.ilike(like))).limit(10)
        )).scalars().all()

    return {
        "query": query,
        "branches": [{"id": b.id, "name": b.name, "code": b.code, "city": b.city, "status": b.status} for b in branches],
        "reports": [{"id": r.id, "title": r.title, "status": r.status, "branch_name": branch_names.get(r.branch_id, "—"),
                     "created_at": r.created_at.isoformat() if r.created_at else None} for r in reports],
        "regions": [{"id": r.id, "name_fr": r.name_fr, "code": r.code} for r in regions],
        "users": [{"id": us.id, "full_name": us.full_name, "email": us.email, "role": us.role} for us in users],
    }

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
async def reject_branch(bid: str, request: Request, db: AsyncSession = Depends(get_db), u=Depends(admin_only)):
    b = await db.get(Branch, bid)
    if not b: raise HTTPException(404)
    b.status = "rejected"
    await journaliser(db, u, "rejet_branche", {"nom": b.name}, branch_id=bid, request=request)
    await db.commit()
    return {"message": f"{b.name} rejetée"}

@app.delete("/api/admin/users/{uid}")
async def delete_user(uid: str, request: Request, db: AsyncSession = Depends(get_db), u=Depends(admin_only)):
    user = await db.get(User, uid)
    if not user: raise HTTPException(404)
    await journaliser(db, u, "suppression_utilisateur", {"nom": user.full_name, "email": user.email}, request=request)
    await db.delete(user)
    await db.commit()
    await backup_users_to_github(db=db)
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
    u.plain_password = temp
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
