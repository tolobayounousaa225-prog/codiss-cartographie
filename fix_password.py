"""
Script de reparation - utilise bcrypt directement (sans passlib)
Lancer avec : venv\Scripts\python fix_password.py
"""
import sqlite3, os

db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "codiss_local.db")

if not os.path.exists(db_path):
    print("ERREUR: codiss_local.db introuvable.")
    input("Entree pour fermer...")
    exit(1)

try:
    import bcrypt
except ImportError:
    print("ERREUR: bcrypt non installe. Lance : venv\\Scripts\\pip install bcrypt")
    input("Entree pour fermer...")
    exit(1)

passwords = {
    "admin@codiss.ci":                   "Admin@CODISS2024",
    "secretaire.abidjan@codiss.ci":      "Branch@2024",
    "secretaire.bouake@codiss.ci":       "Branch@2024",
    "secretaire.yamoussoukro@codiss.ci": "Branch@2024",
}

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("Correction des mots de passe...")
for email, password in passwords.items():
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    cursor.execute("UPDATE users SET password_hash = ? WHERE email = ?", (hashed, email))
    if cursor.rowcount > 0:
        print(f"  OK: {email}")
    else:
        print(f"  ABSENT: {email}")

conn.commit()
conn.close()

print("\nCorrection terminee !")
print("  Email    : admin@codiss.ci")
print("  Password : Admin@CODISS2024\n")
input("Entree pour fermer...")
