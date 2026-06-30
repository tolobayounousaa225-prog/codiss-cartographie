"""
Peuplement de la base de données de test
Crée : admin + 3 comptes branches + 10 branches réparties sur la CI
Lance avec : python seed_db.py
"""
import asyncio
import uuid
from datetime import datetime, date
import bcrypt as _bcrypt
from sqlalchemy.ext.asyncio import AsyncSession

from database_local import engine, Base, AsyncSessionLocal
from models_local import User, Branch, BranchUser, Region, Notification

def pwd_hash(p):
    return _bcrypt.hashpw(p.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")

REGIONS = [
    ("ABJ","Abidjan","Abidjan","District Autonome d'Abidjan"),
    ("LAG","Lagunes","Lagoons","District des Lagunes"),
    ("COM","Comoé","Comoé","District de Comoé"),
    ("MON","Montagnes","Mountains","District des Montagnes"),
    ("BAF","Bafing","Bafing","District de Woroba"),
    ("BAG","Bagoué","Bagoué","District des Savanes"),
    ("BER","Béré","Béré","District de Woroba"),
    ("BOU","Bounkani","Bounkani","District de Zanzan"),
    ("FOL","Folon","Folon","District des Savanes"),
    ("GBK","Gbôklé","Gbôklé","District du Bas-Sassandra"),
    ("GOH","Gôh","Gôh","District du Gôh-Djiboua"),
    ("GON","Gontougo","Gontougo","District de Zanzan"),
    ("GPO","Grands-Ponts","Grands-Ponts","District des Lagunes"),
    ("GUE","Guémon","Guémon","District des Montagnes"),
    ("HAM","Hambol","Hambol","District de la Vallée du Bandama"),
    ("HSA","Haut-Sassandra","Haut-Sassandra","District du Sassandra-Marahoué"),
    ("IFF","Iffou","Iffou","District de la Vallée du Bandama"),
    ("IND","Indénié-Djuablin","Indénié-Djuablin","District du Comoé"),
    ("KAB","Kabadougou","Kabadougou","District du Denguélé"),
    ("LAM","La Mé","La Mé","District des Lagunes"),
    ("LOH","Lôh-Djiboua","Lôh-Djiboua","District du Gôh-Djiboua"),
    ("MAR","Marahoué","Marahoué","District du Sassandra-Marahoué"),
    ("MOR","Moronou","Moronou","District des Lacs"),
    ("NZI","N'Zi","N'Zi","District de la Vallée du Bandama"),
    ("POR","Poro","Poro","District des Savanes"),
    ("SAN","San-Pédro","San-Pédro","District du Bas-Sassandra"),
    ("SUD","Sud-Comoé","Sud-Comoé","District du Comoé"),
    ("TON","Tonkpi","Tonkpi","District des Montagnes"),
    ("WOR","Worodougou","Worodougou","District de Woroba"),
    ("YAM","Yamoussoukro","Yamoussoukro","District Autonome de Yamoussoukro"),
    ("ZUE","Zuénoula","Zuénoula","District du Sassandra-Marahoué"),
]

# Branches de test avec coordonnées GPS réelles des villes CI
TEST_BRANCHES = [
    dict(code="CODISS-ABJ", name="CODISS Abidjan",       city="Abidjan",       region_code="ABJ", lat=5.3600,  lng=-4.0083, status="active",  verified=True,  members=45, pres="Kouamé Jean-Baptiste"),
    dict(code="CODISS-BKE", name="CODISS Bouaké",        city="Bouaké",        region_code="HAM", lat=7.6941,  lng=-5.0311, status="active",  verified=True,  members=32, pres="Traoré Mamadou"),
    dict(code="CODISS-YAM", name="CODISS Yamoussoukro",  city="Yamoussoukro",  region_code="YAM", lat=6.8206,  lng=-5.2737, status="active",  verified=True,  members=28, pres="Koné Aboubakar"),
    dict(code="CODISS-SAN", name="CODISS San-Pédro",     city="San-Pédro",     region_code="SAN", lat=4.7485,  lng=-6.6363, status="active",  verified=False, members=18, pres="Diallo Ibrahim"),
    dict(code="CODISS-KOR", name="CODISS Korhogo",       city="Korhogo",       region_code="POR", lat=9.4580,  lng=-5.6290, status="pending", verified=False, members=15, pres="Coulibaly Souleymane"),
    dict(code="CODISS-MAN", name="CODISS Man",           city="Man",           region_code="TON", lat=7.4125,  lng=-7.5536, status="active",  verified=True,  members=22, pres="Goueu Gervais"),
    dict(code="CODISS-DAL", name="CODISS Daloa",         city="Daloa",         region_code="HSA", lat=6.8773,  lng=-6.4502, status="pending", verified=False, members=12, pres="Séri Arsène"),
    dict(code="CODISS-GAG", name="CODISS Gagnoa",        city="Gagnoa",        region_code="GOH", lat=6.1318,  lng=-5.9508, status="active",  verified=False, members=19, pres="Bah Marie-Claire"),
    dict(code="CODISS-ABO", name="CODISS Aboisso",       city="Aboisso",       region_code="SUD", lat=5.4680,  lng=-3.2082, status="pending", verified=False, members=9,  pres="Amoakon Yao"),
    dict(code="CODISS-ODI", name="CODISS Odienné",       city="Odienné",       region_code="KAB", lat=9.5094,  lng=-7.5659, status="active",  verified=True,  members=11, pres="Fofana Lacina"),
]

async def do_seed(db: AsyncSession):
    """
    Remplit la base avec régions, admin et branches de test.
    Accepte une session externe (appelée depuis main_local lifespan ou standalone).
    """
    from sqlalchemy import select

    print("🌱 Peuplement de la base de données...")

    # ── Régions ──────────────────────────────────────────────
    region_map = {}
    existing_regions = (await db.execute(Region.__table__.select())).fetchall()
    if not existing_regions:
        print("  → Création des 31 régions de Côte d'Ivoire...")
        for code, fr, en, district in REGIONS:
            db.add(Region(code=code, name_fr=fr, name_en=en, district=district))
        await db.flush()

    all_regions = (await db.execute(Region.__table__.select())).fetchall()
    for row in all_regions:
        region_map[row.code] = row.id
    print(f"  ✅ {len(region_map)} régions prêtes")

    # ── Super-admin ───────────────────────────────────────────
    SUPERADMIN_ID = "codiss-super-admin-0000-000000000001"
    ex = (await db.execute(select(User).where(User.email == "admin@codiss.ci"))).scalar_one_or_none()
    if not ex:
        admin = User(
            id=SUPERADMIN_ID,
            email="admin@codiss.ci",
            password_hash=pwd_hash("Admin@CODISS2024"), plain_password="Admin@CODISS2024",
            full_name="Administrateur CODISS National",
            role="superadmin", language="fr",
        )
        db.add(admin)
        print(f"  ✅ Admin créé (ID fixe: {SUPERADMIN_ID[:8]}...)")
    else:
        # Mettre à jour l'ID si c'est un ancien UUID aléatoire
        if ex.id != SUPERADMIN_ID:
            print(f"  🔄 Migration ID superadmin: {ex.id[:8]} → {SUPERADMIN_ID[:8]}")
            ex.id = SUPERADMIN_ID
        else:
            print("  ℹ️  Admin déjà existant (ID fixe OK)")

    # ── Branches de test ──────────────────────────────────────
    branch_ids = {}
    for b in TEST_BRANCHES:
        ex = (await db.execute(select(Branch).where(Branch.code == b["code"]))).scalar_one_or_none()
        if not ex:
            branch = Branch(
                code=b["code"], name=b["name"], city=b["city"],
                region_id=region_map.get(b["region_code"]),
                latitude=b["lat"], longitude=b["lng"],
                status=b["status"], is_verified=b["verified"],
                president_name=b["pres"], member_count=b["members"],
                founded_date=date(2020, 1, 15),
                address=f"Quartier Centre, {b['city']}, Côte d'Ivoire",
                notes="Créé via seed de test",
            )
            if b["verified"]:
                branch.verified_at = datetime.utcnow()
            db.add(branch)
            await db.flush()
            branch_ids[b["code"]] = branch.id
            print(f"     + {b['name']} ({b['status']})")

    await db.flush()
    all_branches = (await db.execute(select(Branch))).scalars().all()
    for br in all_branches:
        branch_ids[br.code] = br.id

    # ── Comptes secrétaires ───────────────────────────────────
    branch_users_data = [
        ("secretaire.abidjan@codiss.ci",     "Secrétaire Abidjan",      "CODISS-ABJ"),
        ("secretaire.bouake@codiss.ci",      "Secrétaire Bouaké",       "CODISS-BKE"),
        ("secretaire.yamoussoukro@codiss.ci","Secrétaire Yamoussoukro", "CODISS-YAM"),
    ]
    for email, name, branch_code in branch_users_data:
        ex = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if not ex:
            u = User(
                email=email, password_hash=pwd_hash("Branch@2024"), plain_password="Branch@2024",
                full_name=name, role="branch", language="fr",
            )
            db.add(u)
            await db.flush()
            if branch_code in branch_ids:
                db.add(BranchUser(user_id=u.id, branch_id=branch_ids[branch_code], role="secretary"))
            print(f"     + Compte : {email} / Branch@2024")

    # ── Notification de bienvenue ─────────────────────────────
    admin_user = (await db.execute(select(User).where(User.email == "admin@codiss.ci"))).scalar_one_or_none()
    if admin_user:
        db.add(Notification(
            user_id=admin_user.id,
            title_fr="Bienvenue sur CODISS Cartographie !",
            title_en="Bienvenue sur CODISS Cartographie !",
            body_fr="Base initialisée avec 10 branches et 31 régions.",
            body_en="Base initialisée avec 10 branches et 31 régions.",
            type="success",
        ))

    print("\n✅ Base de données prête !")
    print("  Admin    : admin@codiss.ci           / Admin@CODISS2024")
    print("  Branche1 : secretaire.abidjan@codiss.ci       / Branch@2024")
    print("  Branche2 : secretaire.bouake@codiss.ci        / Branch@2024")
    print("  Branche3 : secretaire.yamoussoukro@codiss.ci  / Branch@2024")


async def seed():
    """Point d'entrée standalone : python seed_db.py"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as db:
        await do_seed(db)
        await db.commit()

if __name__ == "__main__":
    asyncio.run(seed())
