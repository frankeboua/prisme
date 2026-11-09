# Déploiement et référencement de Prisme

Destiné à la personne qui administre le site. Prix et limites relevés le 30/10/2026 sur les pages officielles : à revérifier avant tout engagement.

## 1. Plateforme utilisée : Render gratuit

**Site en ligne : https://prisme-srbh.onrender.com** (compte Render lié au dépôt GitHub `frankeboua/prisme`, offre Free). Chaque envoi sur la branche `main` redéploie le site.

Railway était le premier choix, car sa base est persistante, mais il n'acceptait pas de nouvelles inscriptions le 30/10/2026. Render gratuit a donc été retenu.

| | Railway (à réessayer pour une exploitation durable) | Render gratuit (utilisé) | Vercel |
|---|---|---|---|
| Serveur Python permanent | Oui | Oui, mais s'endort après 15 min sans visite (réveil : environ 1 min) | Non : fonctions à la demande |
| Base SQLite conservée | Oui, volume persistant | Non : effacée à chaque endormissement ou redéploiement | Non |
| Collecte programmée dans le serveur | Oui | Seulement quand le service est éveillé | Non |
| Coût | Essai de 30 jours avec 5 $ de crédit, sans carte ; ensuite 1 $/mois limité, ou Hobby à partir de 5 $/mois | 0 $ (750 h/mois) ; disque persistant à partir de 7 $/mois + 0,25 $/Go | Non pertinent |

Vercel est écarté parce que l'architecture repose sur un processus permanent et un fichier SQLite local. Le changer imposerait une réécriture sans bénéfice pour ce projet.

**Limites de l'offre gratuite de Render :**

- le site s'endort après 15 minutes sans visite et met environ 1 minute à se réveiller ;
- la base est effacée à chaque endormissement ou redéploiement : **les comptes, favoris et signalements du site public ne durent pas** ;
- les articles reviennent seuls, en moins d'une minute après le réveil.

Avant une présentation, ouvrir le site 2 à 3 minutes à l'avance. Pour conserver les comptes, il faut un disque persistant (offre payante de Render) ou Railway, si les inscriptions rouvrent.

## 2. Variables d'environnement

| Variable | Rôle |
|---|---|
| `PRISME_MODE=public` | Production : ni contenu fictif ni profils de démonstration (déjà défini dans le Dockerfile) |
| `PRISME_ADMIN_USER`, `PRISME_ADMIN_PASSWORD` | Compte administrateur. Sans eux, aucun compte admin n'existe. Jamais dans le code |
| `PRISME_DB=/data/prisme.db` | Emplacement de la base, sur le volume (déjà défini dans le Dockerfile) |
| `PRISME_REFRESH_MINUTES` | Intervalle de collecte des flux (30 par défaut) |
| `PRISME_SITE_URL` | Adresse publique, utile avec un domaine personnalisé (les adresses Railway et Render sont détectées seules) |
| `RAILWAY_RUN_UID=0` | Sur Railway : permet d'écrire sur le volume |
| `PRISME_FIREBASE_API_KEY`, `PRISME_FIREBASE_AUTH_DOMAIN`, `PRISME_FIREBASE_PROJECT_ID` | Firebase Authentication : e-mails de confirmation et de réinitialisation, connexion avec Google (section 5). Ces valeurs sont publiques par conception |
| `PRISME_GOOGLE_SITE_VERIFICATION` | Jeton de la balise HTML fournie par la Google Search Console (section 7) |
| `GOOGLE_FACTCHECK_API_KEY` | Facultatif : affiche dans « Vérifier en 4 étapes » les vérifications publiées par des fact-checkeurs (section 7 bis) |
| `BREVO_API_KEY`, `PRISME_MAIL_FROM` | Solution de repli : envoi des codes de vérification par Brevo (section 5 bis) |

## 3. Pour migrer vers Railway plus tard

```powershell
npx @railway/cli login
npx @railway/cli init --name prisme
npx @railway/cli up --detach
npx @railway/cli volume add --mount-path /data
npx @railway/cli variables --set "PRISME_ADMIN_USER=redaction" --set "PRISME_ADMIN_PASSWORD=<mot de passe long>" --set "RAILWAY_RUN_UID=0"
npx @railway/cli domain
```

Contrôle : `https://<adresse>/healthz` doit répondre `"status": "ok"`.

## 4. Administrer le site sur Render

Identifiant : `redaction`. Le mot de passe se change dans Render : service *prisme* > *Environment* > `PRISME_ADMIN_PASSWORD`. Le site redémarre alors et applique la nouvelle valeur.

Pour recréer le service : *New > Blueprint*, choisir le dépôt (le fichier `render.yaml` est lu automatiquement) et renseigner `PRISME_ADMIN_PASSWORD`.

## 5. Activer les e-mails et la connexion avec Google (Firebase)

Firebase Authentication est gratuit (offre Spark) et envoie lui-même les e-mails : aucun serveur d'envoi n'est nécessaire, ce qui contourne le blocage des ports d'e-mail par Render. Les comptes sont conservés par Firebase : un lecteur retrouve son compte même quand la base gratuite de Render est effacée.

1. Sur [console.firebase.google.com](https://console.firebase.google.com), créer un projet (Google Analytics n'est pas nécessaire).
2. *Authentication > Commencer > Mode de connexion* : activer **Adresse e-mail/Mot de passe** et **Google** (renseigner l'adresse d'assistance demandée).
3. *Authentication > Paramètres > Domaines autorisés* : ajouter `prisme-srbh.onrender.com` (et le futur nom de domaine).
4. *Authentication > Modèles* : choisir la langue **français** et le nom d'expéditeur « Prisme ».
5. *Paramètres du projet > Vos applications > Web (</>)* : enregistrer une application, puis copier `apiKey`, `authDomain` et `projectId`.
6. Dans Render, service *prisme* > *Environment*, ajouter `PRISME_FIREBASE_API_KEY`, `PRISME_FIREBASE_AUTH_DOMAIN` et `PRISME_FIREBASE_PROJECT_ID`, puis enregistrer : le site redémarre.

Ce qui se passe ensuite :

- **Inscription :** nom, e-mail, pays et mot de passe. Firebase envoie un lien de confirmation ; le compte Prisme n'est ouvert qu'après le clic sur ce lien.
- **Connexion avec Google :** un clic, sans mot de passe à créer.
- **Mot de passe oublié :** Firebase envoie un lien pour en choisir un nouveau. Prisme n'envoie jamais de mot de passe.
- **Sécurité :** le serveur ne croit pas le navigateur sur parole. Il fait contrôler chaque jeton par Google (`accounts:lookup`) et refuse une adresse non confirmée. Le compte administrateur reste un compte local (`redaction`).

Contrôle : la page *Connexion* affiche « Continuer avec Google ». Les messages de Firebase arrivent parfois dans les indésirables au début.

## 5 bis. Solution de repli : codes envoyés par Brevo

Sans Firebase ni Brevo, le site public crée les comptes **sans vérifier l'adresse**. L'offre gratuite de Render bloque l'envoi d'e-mails classique (ports 25, 465 et 587) : cette solution passe donc par l'API HTTPS de Brevo.

1. Créer un compte sur [brevo.com](https://www.brevo.com) et y valider l'adresse d'expéditeur.
2. Créer une clé API dans Brevo (*SMTP & API > API Keys*).
3. Dans Render, service *prisme* > *Environment*, ajouter `BREVO_API_KEY` et `PRISME_MAIL_FROM` (l'adresse validée), puis enregistrer.

Le site redémarre et la vérification s'active seule. Ce qui se passe ensuite :

- **Inscription :** nom, e-mail et mot de passe, puis un code à 6 chiffres reçu par e-mail. Le compte n'est créé qu'avec ce code.
- **Mot de passe oublié :** Prisme n'envoie jamais de mot de passe. Il envoie un code, puis le lecteur en choisit un nouveau ; ses autres sessions sont fermées.
- **Protections :** un code vaut 15 minutes et 5 essais, sert une seule fois et n'est conservé que sous forme d'empreinte. Trois demandes au plus par adresse en 10 minutes. La réponse ne révèle pas si un compte existe.

Un expéditeur en `@gmail.com` peut arriver dans les indésirables : un domaine à vous améliore la livraison. En démonstration locale, aucun e-mail ne part et le code s'affiche à l'écran.

## 6. Fonctionnement en production

- **Photos :** Prisme sert des copies allégées (WebP, 480 et 960 pixels), préparées après chaque collecte et conservées dans `imgcache/`. Si une conversion échoue, le visiteur reçoit la photo d'origine. Ces copies restent à valider avec les conditions d'utilisation des médias.
- **Cache :** les réponses des visiteurs non connectés sont recalculées au plus une fois par minute.
- **Serveur :** gunicorn, 1 processus et 8 fils. Ne pas augmenter le nombre de processus : la collecte programmée et la limitation de débit vivent en mémoire.
- **Sauvegarde :** aucune sur l'offre gratuite, la base y est temporaire.
- **Journaux :** visibles dans le tableau de bord Render, onglet *Logs*. Les erreurs détaillées n'y figurent que côté serveur, jamais dans les réponses.
- **HTTPS :** fourni par la plateforme ; l'en-tête HSTS est envoyé par l'application.

## 7. Google Search Console

Un site déployé n'est pas pour autant référencé. L'indexation prend de quelques jours à plusieurs semaines et n'est pas garantie. Une adresse `*.onrender.com` fonctionne, mais un domaine à vous est préférable.

1. Sur [search.google.com/search-console](https://search.google.com/search-console), ajouter la propriété en mode **Préfixe de l'URL** (ou **Domaine** avec un nom de domaine à vous).
2. Vérifier la propriété. Avec l'adresse Render : méthode **balise HTML**. Copier seulement la valeur de `content="..."` dans la variable `PRISME_GOOGLE_SITE_VERIFICATION` de Render, attendre le redémarrage, puis cliquer sur *Valider*. Avec un domaine : enregistrement DNS TXT.
3. Soumettre le sitemap : `https://prisme-srbh.onrender.com/sitemap.xml`.
4. Dans *Inspection de l'URL*, demander l'indexation de l'accueil et de 2 ou 3 pages `/sujet/…`.
5. Après 1 à 2 semaines, consulter *Pages* (erreurs d'indexation) et *Performances* (impressions, clics, requêtes).

### 7 bis. API Google Fact Check (facultatif)

Dans [console.cloud.google.com](https://console.cloud.google.com), activer **Fact Check Tools API**, créer une clé d'API (restreinte à cette API), puis la placer dans `GOOGLE_FACTCHECK_API_KEY` sur Render. L'étape « Authentifier l'information » affiche alors les vérifications déjà publiées par des rédactions de fact-checking. Sans clé, elle propose des liens de recherche.

### Choix SEO appliqués

- Pages lisibles sans JavaScript, URL propres, titres, descriptions, canonique, Open Graph, `robots.txt`, `sitemap.xml`, vrais codes 404.
- **Indexées :** accueil, rubriques, tendances, digest, méthode, médias suivis et pages de comparaison entre plusieurs médias. Ce sont celles qui apportent une valeur propre.
- **Non indexées (`noindex`) :** pages d'un article seul. Un extrait n'apporte rien de plus que l'original, et les multiplier exposerait le site aux règles de Google sur le contenu de faible valeur.
- **Données structurées :** `WebSite` sur l'accueil ; sur les comparaisons, une liste de `NewsArticle` décrivant les articles originaux, avec leur URL et leur éditeur. Prisme ne se présente pas comme l'auteur de ces articles.

### Google Analytics

Non installé. Il exigerait une bannière de consentement et un assouplissement de la politique de sécurité (CSP). Les données de la Search Console suffisent pour commencer.

## 8. Conditions d'utilisation des flux

À vérifier avant une exploitation durable ou commerciale : les conditions de réutilisation des flux RSS de chaque média. Prisme affiche titres et extraits et renvoie vers l'original, mais cela ne remplace pas une lecture de ces conditions, ni un avis juridique.
