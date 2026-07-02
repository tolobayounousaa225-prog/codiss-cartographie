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
from models_local import User, Branch, BranchUser, Region, Notification, Department

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

    # ── Départements liés aux régions ──────────────────────────
    existing_depts = (await db.execute(Department.__table__.select())).fetchall()
    if not existing_depts:
        print("  → Création des départements/communes par région...")
        region_code_to_id = {row[1]: row[0] for row in all_regions}  # code→id
        for region_code, depts in DEPARTMENTS_BY_REGION.items():
            rid = region_code_to_id.get(region_code)
            if not rid: continue
            for code, name_fr, name_en in depts:
                db.add(Department(code=code, name_fr=name_fr, name_en=name_en, region_id=rid))
        await db.flush()
        print(f"  ✅ Départements créés")

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

# ══ Données départements/communes par région ══════════════════════════════
DEPARTMENTS_BY_REGION = {
    "ABJ": [
        ("ABJ-ADJ","Adjamé","Adjamé"),("ABJ-ABO","Abobo","Abobo"),
        ("ABJ-ATT","Attécoubé","Attécoubé"),("ABJ-COC","Cocody","Cocody"),
        ("ABJ-KOU","Koumassi","Koumassi"),("ABJ-MAR","Marcory","Marcory"),
        ("ABJ-PLA","Plateau","Plateau"),("ABJ-PBO","Port-Bouët","Port-Bouët"),
        ("ABJ-TRE","Treichville","Treichville"),("ABJ-YOP","Yopougon","Yopougon"),
        ("ABJ-SON","Songon","Songon"),
    ],
    "LAG": [("LAG-AGB","Agboville","Agboville"),("LAG-ADZ","Adzopé","Adzopé"),("LAG-TIA","Tiassalé","Tiassalé"),("LAG-SIK","Sikensi","Sikensi")],
    "COM": [("COM-ABO","Aboisso","Aboisso"),("COM-ADI","Adiaké","Adiaké"),("COM-AYA","Ayamé","Ayamé"),("COM-GBS","Grand-Bassam","Grand-Bassam")],
    "MON": [("MON-BIA","Biankouma","Biankouma"),("MON-DAN","Danané","Danané"),("MON-ZOU","Zouan-Hounien","Zouan-Hounien"),("MON-SIP","Sipilou","Sipilou")],
    "BAF": [("BAF-TOU","Touba","Touba"),("BAF-OUA","Ouaninou","Ouaninou")],
    "BAG": [("BAG-BOU","Boundiali","Boundiali"),("BAG-KOU","Kouto","Kouto"),("BAG-TEN","Tengrela","Tengrela")],
    "BER": [("BER-MAN","Mankono","Mankono"),("BER-KNA","Kounahiri","Kounahiri"),("BER-DIA","Dianra","Dianra")],
    "BOU": [("BOU-BON","Bouna","Bouna"),("BOU-DOR","Doropo","Doropo"),("BOU-TEH","Téhini","Téhini"),("BOU-NAS","Nassian","Nassian")],
    "FOL": [("FOL-MIN","Minignan","Minignan"),("FOL-KAN","Kaniasso","Kaniasso")],
    "GBK": [("GBK-SAS","Sassandra","Sassandra"),("GBK-FRE","Fresco","Fresco"),("GBK-GBE","Grand-Béréby","Grand-Béréby")],
    "GOH": [("GOH-GAG","Gagnoa","Gagnoa"),("GOH-OUM","Oumé","Oumé")],
    "GON": [("GON-BON","Bondoukou","Bondoukou"),("GON-TAN","Tanda","Tanda"),("GON-TRA","Transua","Transua"),("GON-NIB","Niablé","Niablé")],
    "GPO": [("GPO-DAB","Dabou","Dabou"),("GPO-JAC","Jacqueville","Jacqueville"),("GPO-GLA","Grand-Lahou","Grand-Lahou")],
    "GUE": [("GUE-DUE","Duékoué","Duékoué"),("GUE-KOB","Kouibly","Kouibly"),("GUE-BAN","Bangolo","Bangolo")],
    "HAM": [("HAM-KAT","Katiola","Katiola"),("HAM-DAB","Dabakala","Dabakala"),("HAM-NIA","Niakaramadougou","Niakaramadougou")],
    "HSA": [("HSA-DAL","Daloa","Daloa"),("HSA-ISS","Issia","Issia"),("HSA-VAV","Vavoua","Vavoua"),("HSA-ZOK","Zoukougbeu","Zoukougbeu")],
    "IFF": [("IFF-DIM","Dimbokro","Dimbokro"),("IFF-MBH","M'Bahiakro","M'Bahiakro"),("IFF-BOC","Bocanda","Bocanda")],
    "IND": [("IND-ABE","Abengourou","Abengourou"),("IND-AGN","Agnibilékrou","Agnibilékrou"),("IND-BET","Bettié","Bettié")],
    "KAB": [("KAB-ODI","Odienné","Odienné"),("KAB-BAK","Bako","Bako"),("KAB-GBE","Gbéléban","Gbéléban"),("KAB-SAM","Samatiguila","Samatiguila")],
    "LAM": [("LAM-ALE","Alépé","Alépé"),("LAM-AKO","Akoupé","Akoupé"),("LAM-YAK","Yakassé-Attobrou","Yakassé-Attobrou")],
    "LOH": [("LOH-DIV","Divo","Divo"),("LOH-GUI","Guitry","Guitry"),("LOH-LAK","Lakota","Lakota")],
    "MAR": [("MAR-BOF","Bouaflé","Bouaflé"),("MAR-SIN","Sinfra","Sinfra")],
    "MOR": [("MOR-MBT","M'Batto","M'Batto"),("MOR-ARR","Arrah","Arrah"),("MOR-ETT","Ettrokro","Ettrokro")],
    "NZI": [("NZI-DIM","N'Zi-Dimbokro","N'Zi-Dimbokro"),("NZI-BOC","N'Zi-Bocanda","N'Zi-Bocanda"),("NZI-KKS","Kouassi-Kouassikro","Kouassi-Kouassikro")],
    "POR": [("POR-KOR","Korhogo","Korhogo"),("POR-SIN","Sinématiali","Sinématiali"),("POR-DIK","Dikodougou","Dikodougou"),("POR-MBE","M'Bengué","M'Bengué")],
    "SAN": [("SAN-SPE","San-Pédro","San-Pedro"),("SAN-TAB","Tabou","Tabou"),("SAN-MEA","Méagui","Méagui")],
    "SUD": [("SUD-ABO","Sud-Aboisso","Sud-Aboisso"),("SUD-ADI","Sud-Adiaké","Sud-Adiaké"),("SUD-GBS","Sud-Grand-Bassam","Sud-Grand-Bassam")],
    "TON": [("TON-MAN","Man","Man"),("TON-DAN","Dan-Danané","Dan-Danané"),("TON-BIA","Biankouma-Ton","Biankouma"),("TON-ZOH","Zouan-Hounien","Zouan-Hounien"),("TON-SIP","Sipilou","Sipilou")],
    "WOR": [("WOR-SEG","Séguéla","Séguéla"),("WOR-KEA","Kéably","Kéably"),("WOR-BOG","Bogopé","Bogopé")],
    "YAM": [("YAM-YAM","Yamoussoukro","Yamoussoukro"),("YAM-TIE","Tiébissou","Tiébissou"),("YAM-TOU","Toumodi","Toumodi"),("YAM-DID","Didiévi","Didiévi")],
    "ZUE": [("ZUE-ZUE","Zuénoula","Zuénoula"),("ZUE-KON","Kononfla","Kononfla")],
}
