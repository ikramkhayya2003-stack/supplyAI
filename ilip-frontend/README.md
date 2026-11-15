# ILIP — Étape 5 : interface React

Interface locale branchée sur votre backend FastAPI existant. Données synthétiques, consultation uniquement.

## Lancer sous Windows

1. Installer Node.js 22.12+ (ou Node 24 LTS), puis rouvrir VS Code. Vérifier `node --version` et `npm.cmd --version`.
2. Extraire entièrement le ZIP. Ouvrir le dossier `ilip-frontend` contenant `package.json` dans VS Code.
3. Laisser le backend démarré dans son propre terminal, depuis le dossier `ilip-backend` :

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

4. Dans un second terminal, placé dans `ilip-frontend` :

```powershell
npm.cmd ci
npm.cmd run dev
```

5. Ouvrir http://127.0.0.1:5173 dans votre navigateur.

`npm.cmd` évite le blocage de npm.ps1 par certaines politiques PowerShell. Aucun fichier .env à créer côté frontend. Ne copiez jamais DATABASE_URL dans ce projet.

## Vérification manuelle

- Le bandeau doit indiquer « API connectée » si /ready répond correctement.
- Articles : 37 résultats sans filtre (25 affichés par défaut). Suivant affiche les 12 suivants. Le filtre Actifs/Inactifs interroge la base.
- Stocks : 37 lignes au 2025-12-31, si la base de démonstration n'a pas été modifiée. 13 505 est le nombre de photographies historiques, pas celui d'un jour.
- Achats : 360 commandes sans filtre. Production : 288 ordres sans filtre.
- Voir ouvre les champs de la ligne dans un panneau sous le tableau.
- Une référence inexistante donne un état vide. Réinitialiser efface les filtres.
- Arrêter FastAPI puis Actualiser doit afficher une erreur, jamais des chiffres inventés. Redémarrer FastAPI puis Actualiser.
- Réduire la fenêtre : navigation compacte, tableaux défilables horizontalement.
- Les champs de date utilisent le calendrier du navigateur ; les dates reçues de l'API restent YYYY-MM-DD.

## Architecture

- src/main.jsx : navigation par URL #items/#inventory/#purchases/#production, tables, pagination, détails.
- src/api.js : client HTTP, valeurs des filtres encodées, traitement des erreurs.
- src/style.css : interface responsive bleu nuit, blanc et gris clair.
- vite.config.js : /api redirigé vers http://127.0.0.1:8000 ; /api est retiré avant transmission.

React appelle uniquement FastAPI. FastAPI seul accède à Neon. Le proxy local évite de modifier CORS dans votre backend.
Documentation du proxy : https://vite.dev/config/server-options#server-proxy

Les filtres de code/statut/catégorie sont des correspondances exactes ; recopier un code visible dans le tableau. Les filtres s'appliquent avec le bouton Appliquer et remettent la pagination à zéro. Les totaux viennent de l'API, pas de la page affichée. Les quantités ne sont pas additionnées entre unités différentes. Les décimales sont conservées sous forme de chaînes par l'API puis formatées pour l'affichage uniquement (6 décimales maximum) ; aucun calcul comptable côté client.

## Compilation

```powershell
npm.cmd run build
npm.cmd run preview
```

Preview local : http://127.0.0.1:4173. Le dossier dist contient les fichiers compilés. Le proxy Vite est prévu ici pour le développement et la prévisualisation locale. Un hébergement ultérieur nécessitera un routage /api et un backend accessible, avec authentification et autorisations. Ne publiez pas l'API actuelle sans ces protections.

## Périmètre et limites

Aucun ajout/modification de données, aucune connexion directe Neon, aucun KPI OTIF/OEE calculé, aucun assistant IA à ce stade. Le statut API décrit le dernier contrôle /ready, pas une surveillance continue. Police Google facultative, repli Arial sans réseau. Backend inchangé.

La compilation est vérifiée sur l'environnement de développement. La connexion à votre Neon privé et le rendu navigateur sur votre ordinateur restent à vérifier avec les étapes ci-dessus. Le package ne contient ni identifiants, ni données de remplacement.
