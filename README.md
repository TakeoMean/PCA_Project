# ContinuityOS — cartographie des risques SMCA

ContinuityOS est une application web de management de la continuité d’activité. Elle couvre le processus allant du cadrage du SMCA à la surveillance du risque résiduel, avec une interface React en français, une API FastAPI, PostgreSQL et un contrôle d’accès par rôles.

## Fonctions principales

- périmètre et objectifs du SMCA, seuil d’acceptation et date de revue ;
- BIA par activité avec impacts, criticité, MTPD, RTO, RPO et exigences de reprise ;
- cartographie structurée des dépendances entre activités ;
- bibliothèque réutilisable de menaces, causes et vulnérabilités ;
- registre des risques avec cycle de vie, responsable, sources, mesures existantes et historique ;
- matrice interactive 5×5 avec comparaison du risque inhérent, courant et résiduel ;
- contrôles préventifs, détectifs et correctifs avec efficacité, preuve et calendrier de test ;
- plans de traitement soumis à une validation indépendante, actions et réévaluation résiduelle ;
- KRI avec seuils d’alerte et seuils critiques ;
- incidents, impacts constatés et enseignements liés aux risques ;
- pièces justificatives privées rattachées aux risques ;
- alertes sur les revues, contrôles, actions, traitements et BIA manquantes ;
- rôles, périmètres départementaux, journal d’audit et exports PDF/XLSX.

## Démarrage avec Docker

1. Créer le fichier d’environnement :

   ```powershell
   Copy-Item .env.example .env
   ```

2. Remplacer au minimum `POSTGRES_PASSWORD` et `SECRET_KEY`.

3. Démarrer l’application :

   ```powershell
   docker compose up --build
   ```

4. Ouvrir <http://localhost:5173>. L’API et sa documentation sont disponibles sur <http://localhost:8000/docs>.

Le frontend Docker est compilé pour la production puis servi par Nginx. L’API applique automatiquement les migrations Alembic au démarrage. Les données PostgreSQL et les pièces justificatives sont conservées dans des volumes séparés.

### Comptes de démonstration

Uniquement lorsque `SEED_DEMO_DATA=true` :

- `admin` / `admin123`
- `riskmanager` / `admin123`
- `smcamanager` / `admin123`

Changez les variables `DEMO_*_PASSWORD` avant la première initialisation.

## Production

Configurer au minimum :

```text
APP_ENV=production
SEED_DEMO_DATA=false
COOKIE_SECURE=true
SECRET_KEY=<secret fort et unique>
BOOTSTRAP_ADMIN_USERNAME=<administrateur initial>
BOOTSTRAP_ADMIN_EMAIL=<adresse contrôlée>
BOOTSTRAP_ADMIN_PASSWORD=<mot de passe temporaire fort>
```

Le démarrage échoue volontairement en production si la clé de signature reste la valeur locale ou si une base vide ne possède aucun administrateur d’amorçage. Le compte initial doit changer son mot de passe à la première connexion.

Pour l’architecture AWS cible, consulter [DEPLOY_AWS.md](./DEPLOY_AWS.md). Pour RHEL 9.5, consulter [DEPLOY_RHEL_9_5.md](./DEPLOY_RHEL_9_5.md).

## Développement local

Backend :

```powershell
$env:DATABASE_URL = "postgresql+psycopg://smca:mot-de-passe@localhost:5432/smca"
$env:SECRET_KEY = "une-cle-locale-longue-et-aleatoire"
Set-Location backend
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload
```

Frontend :

```powershell
Set-Location frontend
npm ci
npm run dev
```

Le serveur Vite relaie `/api` vers `http://localhost:8000`. Utiliser `VITE_BACKEND_PROXY` pour une autre adresse.

## Migrations

Les migrations se trouvent dans `backend/alembic/versions`. Elles sont appliquées automatiquement par l’API. Elles peuvent aussi être lancées manuellement :

```powershell
Set-Location backend
alembic upgrade head
```

## Tests

```powershell
Set-Location backend
python -m pytest -q

Set-Location ..\frontend
npm test
npm run build
```

Les tests couvrent le workflow de traitement, les droits départementaux, l’audit, le périmètre SMCA, la BIA, les contrôles, les dépendances, les incidents, les KRI, les pièces justificatives, les exports et l’authentification par cookie.

## Sécurité intégrée

- autorisations vérifiées côté API ;
- cookie de session `HttpOnly`, `SameSite=Lax` et `Secure` en production ;
- limitation des tentatives de connexion ;
- séparation entre auteur et approbateur d’un traitement ;
- mots de passe temporaires avec changement obligatoire ;
- exports générés en mémoire et protégés contre l’injection de formules ;
- fichiers limités en taille et en extensions, stockés hors du frontend ;
- image backend exécutée avec un utilisateur non privilégié ;
- en-têtes de sécurité et CSP sur le frontend Nginx.
