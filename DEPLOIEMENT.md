# 🚀 Guide de déploiement CODISS — Render + Supabase

## Architecture finale
```
Frontend (index.html)  →  GitHub Pages / Render Static
Backend (FastAPI)      →  Render Web Service (gratuit)
Base de données        →  Supabase PostgreSQL (gratuit)
Fichiers/Photos        →  Supabase Storage (gratuit)
```

---

## ÉTAPE 1 — Créer la base de données sur Supabase

1. Aller sur https://supabase.com → **Sign Up** (gratuit)
2. **New Project** → nommer le projet `codiss-carto`
3. Choisir la région la plus proche (Europe West ou Africa)
4. Copier le **mot de passe** du projet (important !)
5. Une fois créé → aller dans **SQL Editor**
6. Coller le contenu du fichier `schema.sql` et cliquer **Run**
7. Dans **Settings → Database**, copier la **Connection string** (URI)
   - Format : `postgresql://postgres:[MOT_DE_PASSE]@db.[REF].supabase.co:5432/postgres`
   - Pour asyncpg : remplacer `postgresql://` par `postgresql+asyncpg://`

---

## ÉTAPE 2 — Créer le compte admin

Dans le SQL Editor Supabase, exécuter :
```sql
-- Générer d'abord le hash avec Python :
-- python3 -c "from passlib.context import CryptContext; c=CryptContext(['bcrypt']); print(c.hash('VotreMotDePasse2024!'))"

UPDATE users
SET password_hash = '[HASH_GENERE]'
WHERE email = 'admin@codiss.ci';
```

Ou créer un nouveau superadmin :
```sql
INSERT INTO users (email, password_hash, full_name, role) VALUES (
  'admin@codiss.ci',
  '$2b$12$...hash_bcrypt...',
  'Admin CODISS National',
  'superadmin'
);
```

---

## ÉTAPE 3 — Déployer le backend sur Render

### 3a. Préparer le repo GitHub
1. Créer un repo GitHub `codiss-backend`
2. Y placer tous les fichiers `.py` + `requirements.txt`
3. Créer le fichier `render.yaml` :

```yaml
services:
  - type: web
    name: codiss-api
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: DATABASE_URL
        sync: false
      - key: SECRET_KEY
        sync: false
      - key: CORS_ORIGINS
        value: https://votre-frontend.github.io
      - key: ACCESS_TOKEN_EXPIRE_MINUTES
        value: 480
```

### 3b. Déployer sur Render
1. Aller sur https://render.com → **New Web Service**
2. Connecter le repo GitHub `codiss-backend`
3. Render détecte automatiquement Python
4. Dans **Environment Variables**, ajouter :
   - `DATABASE_URL` → la chaîne de connexion Supabase (avec `+asyncpg`)
   - `SECRET_KEY` → générer avec : `python3 -c "import secrets; print(secrets.token_hex(32))"`
   - `CORS_ORIGINS` → URL de ton frontend
5. Cliquer **Deploy** — Render build et démarre l'API
6. L'URL sera du type : `https://codiss-api.onrender.com`

---

## ÉTAPE 4 — Déployer le frontend

### Option A : GitHub Pages (gratuit, recommandé)
1. Créer un repo `codiss-frontend`
2. Y placer `index.html`
3. Dans `index.html`, changer la ligne :
   ```js
   const API = 'https://codiss-api.onrender.com/api';
   ```
4. Dans le repo → **Settings → Pages → Deploy from main branch**
5. URL : `https://[username].github.io/codiss-frontend`

### Option B : Render Static Site
1. Nouveau **Static Site** sur Render
2. Connecter le repo du frontend
3. Build command : (laisser vide)
4. Publish directory : `.`

---

## ÉTAPE 5 — Test de l'application

### Tester l'API
```bash
# Santé
curl https://codiss-api.onrender.com/health

# Login
curl -X POST https://codiss-api.onrender.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@codiss.ci","password":"VotreMotDePasse2024!"}'

# Stats carte (avec token)
curl https://codiss-api.onrender.com/api/map/stats \
  -H "Authorization: Bearer VOTRE_TOKEN"
```

### Tester en local (développement)
```bash
# 1. Créer environnement virtuel
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Créer le fichier .env (copier .env.example et remplir)
cp .env.example .env

# 4. Lancer le serveur
uvicorn main:app --reload --port 8000

# 5. Ouvrir la doc interactive
# http://localhost:8000/api/docs
```

---

## Structure des fichiers
```
codiss-backend/
├── main.py              # Point d'entrée FastAPI
├── config.py            # Configuration (variables d'env)
├── database.py          # Connexion PostgreSQL async
├── models.py            # Modèles SQLAlchemy
├── schemas.py           # Schémas Pydantic
├── auth.py              # JWT + hashing
├── router_auth.py       # Routes /api/auth/...
├── router_branches.py   # Routes /api/branches/...
├── router_reports.py    # Routes /api/reports/...
├── router_map.py        # Routes /api/map/...
├── router_admin.py      # Routes /api/admin/...
├── requirements.txt
├── .env.example
└── schema.sql           # SQL Supabase

codiss-frontend/
└── index.html           # Application SPA complète
```

---

## Sécurité en production

- [ ] Changer le mot de passe admin par défaut
- [ ] Utiliser un SECRET_KEY fort (64+ caractères hex)
- [ ] Activer HTTPS (automatique sur Render/GitHub Pages)
- [ ] Restreindre CORS aux domaines autorisés
- [ ] Activer Row Level Security (RLS) sur Supabase
- [ ] Configurer les backups automatiques Supabase

---

## Créer les premières branches

Via l'interface admin :
1. Se connecter avec `admin@codiss.ci`
2. Aller dans **Branches → + Nouvelle branche**
3. Remplir : Code (ex: `CODISS-ABJ`), Nom, Ville, Région
4. Créer un utilisateur `branch` pour chaque branche
5. Aller dans **Utilisateurs** → assigner l'utilisateur à la branche

Ou via l'API directement (utile pour import en masse) :
```bash
curl -X POST https://codiss-api.onrender.com/api/branches \
  -H "Authorization: Bearer TOKEN_ADMIN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "CODISS-ABJ",
    "name": "CODISS Abidjan",
    "city": "Abidjan",
    "region_id": 1,
    "latitude": 5.3600,
    "longitude": -4.0083
  }'
```

---

## Support

Pour toute question technique, contacter l'équipe IT CODISS.
Documentation API interactive : `https://codiss-api.onrender.com/api/docs`
