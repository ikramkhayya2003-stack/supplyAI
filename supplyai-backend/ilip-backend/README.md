# ILIP Backend — Étape 4.1

API FastAPI de lecture, reliée au schéma PostgreSQL `ilip` déjà importé dans Neon. Version 0.1.0, développement local. Aucun import ni aucune création de table au démarrage.

## Objectif de cette étape

Faire apparaître les **37 articles** de ta base depuis `GET /items`, puis consulter stocks, achats et production. Ce lot couvre la connexion, les lectures et leur validation. L’authentification utilisateur, les écritures, imports récurrents, KPI avancés et le chatbot viendront dans les lots suivants.

## 1. Ouvrir le projet

Extraire le ZIP. Ouvrir dans VS Code le dossier **ilip-backend** qui contient `requirements.txt` et le sous-dossier `app`.

Ouvrir **Terminal → New Terminal**, puis vérifier que le terminal se trouve dans ce dossier. Les commandes Windows ci-dessous utilisent directement le Python de l’environnement; aucune modification d’ExecutionPolicy n’est nécessaire.

Prérequis : Python **3.12** installé sur l’ordinateur. Vérifier avec `py -3.12 --version`.

## 2. Installer les dépendances — Windows / PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

La dernière commande est à faire une seule fois, avant de renseigner `.env`. Ne pas l’utiliser ensuite pour écraser une configuration existante.

## 3. Renseigner Neon localement

Dans Neon, cliquer sur **Connect**, sélectionner la même branche et la même base `neondb` que celles où les tables ont été créées. Copier la chaîne de connexion PostgreSQL. Si Neon propose une connexion avec pool, elle convient à ce backend; les instructions préparées automatiques sont désactivées côté pilote pour éviter de dépendre de l’état d’une session du pool distant.

Dans VS Code, ouvrir `.env` et renseigner :

```dotenv
DATABASE_URL="COLLER_ICI_LA_CHAINE_POSTGRESQL_DE_NEON"
```

Remplacer entièrement le texte indicatif. Conserver les paramètres de connexion fournis, notamment `sslmode=require` et `channel_binding=require` s’il est présent. Ne pas copier le mot `psql` ni les quotes extérieures d’une commande shell : seule la chaîne commençant par `postgresql://` est nécessaire.

**Garder cette valeur sur ton ordinateur.** Il n’est pas nécessaire de l’envoyer dans une conversation. `.env` est exclu de Git; `.env.example` ne contient aucun secret.

Le rôle utilisé doit pouvoir lire les tables et utiliser le schéma `ilip`. Le rôle qui a créé la base permet le premier test. Un rôle dédié en lecture seule sera préférable avant une utilisation partagée; ce projet ne crée pas de comptes ni de mots de passe.

## 4. Lancer l’API

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Garder ce terminal ouvert. Ouvrir ensuite :

- [État de l’application](http://127.0.0.1:8000/health)
- [Connexion et schéma](http://127.0.0.1:8000/ready)
- [Documentation interactive](http://127.0.0.1:8000/docs)
- [Articles](http://127.0.0.1:8000/items)

Dans `/docs` : ouvrir **GET /items**, cliquer **Try it out**, puis **Execute**. Aucun code SQL ne doit être collé dans Swagger.

## 5. Résultats attendus sur ton dataset

| Route | Résultat attendu |
|---|---|
| `/health` | HTTP 200, `status: "ok"`. Ne prouve pas la connexion à Neon. |
| `/ready` | HTTP 200, `status: "ready"`, `database: "connected"`, `schema: "ilip"`. |
| `/items` | `total: 37`, avec 37 articles dans `data`. |
| `/items?category=FINISHED_GOOD` | `total: 6`. |
| `/items?active=false` | `total: 1`, référence ancienne inactive. |
| `/items/WH-001` | Détail de l’article WH-001. |
| `/inventory` | Dernière date disponible : `2025-12-31`; `total: 37`. |
| `/inventory?snapshot_date=2025-03-15&warehouse_id=RM` | `total: 31`, uniquement les matières de ce jour. |
| `/purchase-orders` | `total: 360`; les 50 premières commandes sont affichées. |
| `/production-orders` | `total: 288`; les 50 premiers OF sont affichés. |

Ces nombres correspondent à la démonstration 2025 uniquement. Ils changeront si tu ajoutes ou modifies des données.

Format des listes :

```json
{
  "total": 37,
  "limit": 50,
  "offset": 0,
  "data": []
}
```

Dans cet exemple de structure seulement, `data` est abrégé. Une réponse réelle contient les enregistrements. `total` indique le nombre correspondant aux filtres, pas seulement la taille de la page. `limit` accepte 1 à 200; `offset` commence à 0. Exemple : `/purchase-orders?limit=50&offset=50` retourne la deuxième page.

Les valeurs PostgreSQL NUMERIC sont sérialisées sous forme de chaînes décimales, par exemple `"18.000000"`, pour conserver leur précision. Les dates restent au format ISO. Les propriétés inconnues ou non applicables restent `null`, sans transformation en zéro.

## Routes et filtres

| Route | Paramètres |
|---|---|
| `/items` | `q`, `category`, `active`, `limit`, `offset` |
| `/items/{item_id}` | Identifiant exact dans le chemin |
| `/inventory` | `snapshot_date`, `item_id`, `warehouse_id`, `limit`, `offset` |
| `/purchase-orders` | `supplier_id`, `status`, `limit`, `offset` |
| `/production-orders` | `line_id`, `status`, `limit`, `offset` |

La recherche `q` porte sur la référence et le nom, sans distinction de casse. `%` et `_` sont traités comme des caractères littéraux, pas comme des jokers. Les valeurs des filtres sont passées comme paramètres SQL.

**Convention de stock :** une réponse ne mélange jamais plusieurs dates. Sans `snapshot_date`, la dernière date globale de la table est sélectionnée, puis les filtres s’appliquent. Une date demandée sans relevé retourne une liste vide pour cette date; le backend ne remplace pas silencieusement cette date par une autre. Pour des données réelles où certains articles ne sont pas relevés chaque jour, il faudra définir explicitement une politique d’ancienneté des relevés.

## Organisation du code

| Fichier | Responsabilité |
|---|---|
| `app/main.py` | Application, démarrage/arrêt du pool et erreurs de base |
| `app/config.py` | Lecture de `.env`, chaîne de connexion masquée |
| `app/db.py` | Connexions PostgreSQL et transactions en lecture seule |
| `app/routes.py` | Routes HTTP, filtres et validation des paramètres |
| `app/repositories.py` | Requêtes SQL explicites dans le schéma `ilip` |
| `app/models.py` | Modèles de réponse et types métier |
| `tests/test_api.py` | Tests API, validation et traitement des erreurs |

Il n’y a aucun générateur de données ou faux mode connecté dans l’application. Sans configuration valide, `/health` fonctionne mais les routes de données répondent HTTP 503. Le pool est ouvert au démarrage et connecte à la demande; le premier accès Neon peut donc prendre quelques secondes. Après modification de `.env`, arrêter avec **Ctrl+C**, puis relancer la commande.

## Dépannage

| Symptôme | Action |
|---|---|
| `py` ou Python introuvable | Installer Python 3.12, puis rouvrir le terminal. |
| `No module named app` | Se placer dans le dossier contenant `app` et `requirements.txt`. |
| `/health` OK, `/ready` 503 | Vérifier `.env`, la branche/base Neon, les paramètres TLS, l’accès réseau et les droits de lecture. Redémarrer l’API. |
| Réponse 503 après plusieurs secondes | Le pool ou la requête a expiré. Vérifier la disponibilité Neon, puis réessayer. |
| `total: 0` | Vérifier les filtres, la date demandée et que la connexion pointe vers la base chargée. |
| HTTP 422 | Paramètre mal formé : date invalide, limite supérieure à 200, offset négatif, etc. |
| HTTP 404 sur un article | La référence exacte n’existe pas. |
| Port 8000 occupé | Relancer avec `--port 8001`, puis utiliser les liens en remplaçant le port. |

## Tests et limites

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

**22 tests API passent**, avec la connexion remplacée explicitement par des doublures de test. Ils couvrent notamment la pagination, les décimales, les paramètres invalides, la recherche paramétrée, les dates de stock, l’absence de configuration et les réponses d’erreur sans secret.

**13 scénarios SQL** ont aussi été exécutés sur PostgreSQL 18.6 embarqué (PGlite) avec les 24 635 lignes du dataset, en utilisant les requêtes produites par les repositories. Les résultats sont dans `SQL_TEST_RESULTS.json`. Ce contrôle vérifie la syntaxe, les filtres et les volumes; il ne teste pas le protocole réseau psycopg vers Neon. Le démarrage local sans connexion est également vérifié.

La connexion à ton compte Neon reste à vérifier sur ton ordinateur via `/ready`, puis `/items`. Aucune opération distante n’a été réalisée pour produire ce paquet.

**Périmètre de cette version : développement local en lecture seule.** Pas encore d’authentification utilisateur, de contrôle d’accès par rôle, de CORS pour un frontend distinct, de déploiement public ou de fonctions d’écriture. Ne pas changer l’écoute en interface publique avant de traiter ces points. Les requêtes sont en lecture seule et bornées; une future API d’écriture devra avoir sa propre gestion transactionnelle.

## macOS / Linux

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
# Renseigner DATABASE_URL dans .env avant la suite.
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Références

- [FastAPI : configuration par variables d’environnement](https://fastapi.tiangolo.com/advanced/settings/).
- [Psycopg : cycle de vie du pool de connexions](https://www.psycopg.org/psycopg3/docs/advanced/pool.html).

Le contrat métier des routes provient du schéma ILIP et de la convention du dataset, pas d’une intégration ERP réelle.
