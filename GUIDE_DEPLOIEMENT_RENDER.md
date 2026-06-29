# 🚀 Déploiement CODISS sur Render.com (Gratuit)

**Durée estimée : 15–20 minutes**  
**Coût : 0 € / Gratuit**

---

## ⚠️ Important à savoir avant de commencer

> Sur le plan gratuit de Render, le serveur **se met en veille après 15 minutes d'inactivité**.
> Au réveil, la base de données SQLite est **réinitialisée** (les branches et rapports créés sont perdus).
> Les comptes de test sont recréés automatiquement à chaque redémarrage.
>
> **Pour une utilisation réelle / permanente**, contactez Anthropic pour une mise à niveau vers un plan payant ou utilisez une base PostgreSQL externe (Supabase).

---

## ÉTAPE 1 — Créer un compte GitHub

> Si vous avez déjà un compte GitHub, passez à l'étape 2.

1. Allez sur **https://github.com**
2. Cliquez **Sign up** (en haut à droite)
3. Renseignez : email, mot de passe, nom d'utilisateur
4. Confirmez votre email

---

## ÉTAPE 2 — Mettre le code sur GitHub

### 2a. Télécharger et installer Git
- Allez sur **https://git-scm.com/download/win**
- Téléchargez et installez Git (laissez toutes les options par défaut)

### 2b. Ouvrir une invite de commande dans le dossier CODISS

1. Ouvrez le dossier **C:\Users\TOLOBA\OneDrive\Bureau\CODISS_API** dans l'Explorateur Windows
2. Cliquez dans la barre d'adresse, tapez `cmd`, appuyez sur Entrée

### 2c. Initialiser et envoyer le code

Copiez-collez ces commandes **une par une** dans l'invite de commande :

```bash
git init
git add .
git commit -m "Initial CODISS deployment"
git branch -M main
```

Puis créez un nouveau dépôt sur GitHub :
1. Allez sur **https://github.com/new**
2. Nom du dépôt : `codiss-cartographie`
3. Laissez-le en **Public** (requis pour le plan gratuit Render)
4. Cliquez **Create repository**
5. Copiez l'URL qui s'affiche (ex: `https://github.com/VOTRE_NOM/codiss-cartographie.git`)

Puis dans l'invite de commande :
```bash
git remote add origin https://github.com/VOTRE_NOM/codiss-cartographie.git
git push -u origin main
```

---

## ÉTAPE 3 — Déployer sur Render.com

1. Allez sur **https://render.com**
2. Cliquez **Get Started for Free**
3. Connectez-vous avec votre compte **GitHub** (bouton "Continue with GitHub")
4. Autorisez Render à accéder à GitHub

### 3a. Créer un nouveau Web Service

1. Dans le tableau de bord Render, cliquez **+ New** → **Web Service**
2. Choisissez **Connect a repository**
3. Sélectionnez votre dépôt `codiss-cartographie`
4. Cliquez **Connect**

### 3b. Configurer le service

Remplissez le formulaire comme suit :

| Champ | Valeur |
|-------|--------|
| **Name** | `codiss-cartographie` |
| **Region** | Frankfurt (EU Central) |
| **Branch** | `main` |
| **Runtime** | Python 3 |
| **Build Command** | `pip install -r requirements_render.txt` |
| **Start Command** | `uvicorn main_local:app --host 0.0.0.0 --port $PORT` |
| **Instance Type** | **Free** |

5. Cliquez **Create Web Service**

---

## ÉTAPE 4 — Attendre le déploiement

Render va maintenant :
1. Télécharger votre code
2. Installer les dépendances (1–2 minutes)
3. Démarrer le serveur

Vous verrez les logs en direct. Attendez le message :
```
✅ Base de données initialisée automatiquement.
INFO: Application startup complete.
```

**L'URL de votre application** sera affichée en haut : `https://codiss-cartographie.onrender.com`

---

## ÉTAPE 5 — Accéder à l'application

Ouvrez l'URL fournie par Render dans votre navigateur.

### Comptes de connexion (recréés automatiquement) :

| Rôle | Email | Mot de passe |
|------|-------|--------------|
| Super Admin | `admin@codiss.ci` | `Admin@CODISS2024` |
| Secrétaire Abidjan | `secretaire.abidjan@codiss.ci` | `Branch@2024` |
| Secrétaire Bouaké | `secretaire.bouake@codiss.ci` | `Branch@2024` |
| Secrétaire Yamoussoukro | `secretaire.yamoussoukro@codiss.ci` | `Branch@2024` |

---

## 🔄 Mettre à jour l'application

Chaque fois que vous modifiez des fichiers, relancez ces commandes dans l'invite de commande :

```bash
git add .
git commit -m "Mise à jour"
git push
```

Render redéploiera automatiquement en quelques minutes.

---

## ❓ Problèmes courants

**L'application met longtemps à répondre au premier accès ?**  
→ Normal. Le plan gratuit met le serveur en veille. La première requête prend 30–60 secondes pour réveiller le serveur.

**Erreur "Build failed" ?**  
→ Vérifiez que le fichier `requirements_render.txt` est bien dans votre dépôt GitHub.

**Les données disparaissent après une mise en veille ?**  
→ C'est la limitation du plan gratuit SQLite. Normal. Les comptes de test sont recréés automatiquement.

**L'URL de l'API dans les logs montre des erreurs ?**  
→ Attendez que le message "Application startup complete" apparaisse avant de tester.

---

*Guide créé pour CODISS — Cartographie des secrétariats de Côte d'Ivoire*
