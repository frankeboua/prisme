# PRISME — Agrégateur intelligent des nouveaux médias

**École Supérieure Africaine des TIC (ESATIC) — Licence 3 TWIN — Projet de Community Management**
Groupe 7 : Eboua Franck · Kah Toily · Yao Francklin — Encadrant : M. Cédric Cissé

> « L'information sous tous ses angles. »
> Prisme agrège les médias dans un fil unique, regroupe les doublons, compare la façon dont chaque média traite un même événement, indique la fraîcheur de l'information et explique chacune de ses recommandations. Il mesure la couverture d'un événement : il ne certifie pas les faits.

Deux modes de fonctionnement :

- **Démonstration locale** (par défaut, `Lancer_Prisme.bat`) : données fictives, profils en un clic, scénarios de la soutenance.
- **Production** (`PRISME_MODE=public`) : médias réels uniquement, aucun compte fictif. Voir [docs/DEPLOIEMENT.md](docs/DEPLOIEMENT.md).

---

## 1. Lancement (Windows)

1. Double-cliquer sur **`Lancer_Prisme.bat`**.
2. Le navigateur s'ouvre automatiquement sur **http://127.0.0.1:8765**.
3. Laisser la fenêtre noire ouverte pendant l'utilisation (c'est le serveur). La fermer arrête l'application.

**Prérequis :** Python 3.9 ou plus récent (aucune bibliothèque à installer : seule la bibliothèque standard est utilisée).
Une connexion Internet est recommandée pour collecter les flux RSS réels et pour la traduction automatique. **Sans Internet, l'application fonctionne entièrement** grâce aux données de démonstration.

Au premier lancement, la base de données `database/prisme.db` est créée automatiquement et remplie.
Pour repartir de zéro : `Reinitialiser_la_base.bat`.

### Profils de démonstration (mode local uniquement)

La page *Connexion* propose une connexion en un clic : `admin`, `aminata`, `kevin`, `kouassi`, `yao`, `paul` et `sara`. Ces profils n'existent pas en production, où le compte administrateur est défini par des variables d'environnement.

Tout visiteur peut aussi **créer son propre compte** ou naviguer **sans compte**.

### Tests

```powershell
python -m unittest tests.test_public
python -m unittest tests.test_demo
python tests/e2e.py http://127.0.0.1:8765 demo captures   # navigateur réel (Playwright + Edge)
```

---

## 2. Fonctionnalités (priorisation MoSCoW)

| Priorité | Fonctionnalité | Où la trouver |
|---|---|---|
| Indispensable | Agrégation RSS (12 flux réels : France 24, RFI, BBC Afrique, Le Monde, Jeune Afrique, Franceinfo, BBC, Al Jazeera, 01net, Numerama, podcast Radio France…) | Fil d'actualité, bouton ⟳ |
| Indispensable | Recherche simple et avancée (mots-clés, date, auteur, source, format, statut, langue) | Barre du haut, *Recherche avancée* |
| Indispensable | Favoris, dossiers de veille | Étoile ☆, *Favoris*, *Veille & alertes* |
| Indispensable | Dates de publication **et** de collecte, liens vers les sources originales | Page article |
| Très important | **Détection des doublons** (une carte par événement, « N autres médias ») | Fil d'actualité |
| Très important | **Résumé automatique par extraction**, phrases citées [1] [2] renvoyant aux sources | Onglet *Résumé automatique* |
| Très important | **Statut de couverture** (Source unique, Repris par N sources, Chiffres divergents, Démenti signalé) | Badges, onglet *Recoupement*, page *Notre méthode* |
| Très important | **Indicateur de fraîcheur** et alerte « ancienne information qui recircule » | Badges, bandeau rouge |
| Ensuite | **Comparaison des sources** : vocabulaire commun, divergences chiffrées, ton, angle, chronologie | Bouton *Comparer* |
| Ensuite | **Signalement d'erreurs** + modération + correction publiée + notification du lecteur + journal des modifications | Drapeau, *Signalements*, *Administration* |
| Ensuite | **Notifications personnalisées** par mots-clés (+ notifications du navigateur) | Cloche, *Veille & alertes* |
| Ensuite | **Personnalisation sans enfermement** : quota « Découverte », indice de diversité | Fil *Pour vous*, *Paramètres* |
| Ensuite | **Transparence des recommandations** : « Pourquoi cet article ? » (6 critères pondérés) | Bouton (?) sur chaque carte |
| Ensuite | **Traduction** (6 langues) et **simplification** (glossaire, indice de lisibilité) | Onglets de la page article |
| Ensuite | Digest quotidien (export PDF, envoi par e-mail), tendances et hashtags, posts prêts à publier | *Digest du jour*, *Tendances* |
| Ensuite | Lecteur audio persistant, filtre par format, mode lecture épuré, accessibilité | *Multimédia*, *Paramètres* |
| Ensuite | Export TXT / CSV / BibTeX | *Favoris* |
| Plus tard | Vérification multimédia avancée, analyse des réseaux sociaux en temps réel, synthèses par grand modèle de langage | Page *Le projet* (feuille de route) |

---

## 3. Architecture

```
Prisme/
├── Lancer_Prisme.bat          Lanceur Windows (double-clic)
├── Reinitialiser_la_base.bat  Remise à zéro des données
├── server.py                  Cœur HTTP + API REST (40+ routes JSON)
├── wsgi.py                    Entrée de production (gunicorn)
├── Dockerfile, railway.json, render.yaml   Déploiement
├── tests/                     Tests unitaires, d'intégration et navigateur
├── app/
│   ├── db.py                  Accès aux données SQLite
│   ├── nlp.py                 Traitement automatique du langage (TAL)
│   ├── engine.py              Doublons, recoupement, résumé, comparaison, recommandation
│   ├── pages.py               Pages rendues côté serveur, sitemap, robots.txt
│   ├── rss.py                 Collecteur RSS 2.0 / Atom (parallélisé)
│   ├── translate.py           Traduction automatique avec cache
│   └── seed.py                Données initiales et comptes de démonstration
├── database/
│   ├── schema.sql             Schéma relationnel complet (commenté)
│   └── prisme.db              Base générée au premier lancement
├── web/
│   ├── index.html             Application monopage
│   ├── app.css                Thèmes clair / sombre / contraste élevé, responsive
│   ├── app.js                 Interface (JavaScript natif, sans framework)
│   └── media/                 Fichiers audio de démonstration
└── docs/Guide_Presentation.md Scénario de démonstration pas à pas
```

- **Client** : pages rendues par le serveur, puis application monopage en JavaScript natif sur les mêmes URL.
- **Serveur** : Python 3 ; `http.server` en local, gunicorn en production ; jetons de session conservés sous forme d'empreinte, mots de passe hachés PBKDF2-SHA256 (600 000 itérations), limitation de débit, politique de sécurité CSP.
- **Base de données** : SQLite en mode WAL, 21 tables et 1 vue, clés étrangères et index.

### Modèle de données (principales tables)

`users`, `sessions`, `categories`, `sources`, `articles`, `clusters` (doublons), `claims` (affirmations), `evidences` (preuves), `interests`, `reading_history`, `folders`, `favorites`, `alerts`, `notifications`, `reports` (signalements), `shares`, `translations`, `glossary`, `fetch_log`, `change_log`, `meta` — vue `v_articles`.

---

## 4. Algorithmes (IA explicable)

| Fonction | Méthode |
|---|---|
| Doublons | Vecteurs de fréquence des termes (titre pondéré ×2), racinisation légère, **similarité cosinus ≥ 0,42**, publications à **moins de 4 jours d'écart**, regroupement **par lien moyen** pour éviter l'enchaînement de sujets voisins. Les identifiants de sujets restent stables d'une collecte à l'autre. Limite : pas de regroupement entre langues. |
| Recoupement | Détection de 6 types d'affirmations ; recherche de phrases proches chez d'autres médias contemporains (± 30 jours) ; comparaison des **chiffres arrêtés** (« au moins 60 morts » n'infirme pas « 68 morts ») ; repérage du vocabulaire de démenti. Le statut affiché décrit le nombre de médias : une reprise n'est pas une preuve. |
| Résumé | Synthèse **extractive** multi-sources : centralité (similarité au centroïde du sujet), anti-redondance, exclusion des contenus en désaccord ; chaque phrase est copiée de la source citée. Aucun texte n'est rédigé par un modèle de langage. |
| Fraîcheur | Décroissance exponentielle (constante de 36 h) ; alerte de recirculation si l'écart entre publication et reprise dépasse 30 jours. |
| Recommandation | Score = 30 % intérêts + 25 % fraîcheur + 15 % pondération de la source (identique pour tous les médias réels) + 15 % couverture + 10 % mots-clés suivis + 5 % proximité avec l'historique. Quota de découverte réglable (25 % par défaut). Indice de diversité = entropie de Shannon normalisée. |
| Simplification | Découpage des phrases longues, glossaire en base de données, indice de lisibilité de **Kandel & Moles**. |

---

## 5. Données de démonstration

Les sources suffixées **« (démo) »** et les contenus marqués **Démo** sont **fictifs** ; ils ont été rédigés pour illustrer des scénarios précis :

- hausse du carburant couverte par 4 médias, dont un site fictif qui annonce **15 %** au lieu de 5 % → doublons, statut *Chiffres divergents* ;
- rumeur d'une « plante miracle » contre le paludisme, démentie par deux médias → statut *Démenti signalé*, correction publiée ;
- inondations à Abidjan + un **article de 2024 (18 morts) qui recircule** → indicateur de fraîcheur ;
- programme de fibre optique, levée de fonds d'une startup d'IA, cacao, CAN 2027… ;
- articles en anglais (traduction), publications virales (réseaux sociaux), podcasts.

Les dates des contenus de démonstration sont recalées à chaque lancement pour rester d'actualité. Les contenus réels proviennent des flux RSS publics des médias cités, avec un lien vers l'article original.

---

## 6. Limites et éthique

- Prisme **compare** la couverture : il aide le lecteur à exercer son esprit critique, sans prétendre établir la vérité.
- Prisme n'attribue **aucune note aux médias réels**. Les scores affichés en mode démonstration concernent uniquement des sources fictives.
- Aucune donnée personnelle n'est transmise à des tiers ; l'historique peut être effacé à tout moment. Seul le texte d'un article à traduire est envoyé au service MyMemory.
