# Déploiement et référencement de Prisme

Destiné à la personne qui administre le site. Prix et limites relevés le 30/10/2026 sur les pages officielles : à revérifier avant tout engagement.

## 1. Plateforme retenue : Railway

| | Railway (retenu) | Render gratuit (secours) | Vercel |
|---|---|---|---|
| Serveur Python permanent | Oui | Oui, mais s'endort après 15 min sans visite (réveil : environ 1 min) | Non : fonctions à la demande |
| Base SQLite conservée | Oui, volume persistant | Non : effacée à chaque endormissement ou redéploiement | Non |
| Collecte programmée dans le serveur | Oui | Seulement quand le service est éveillé | Non |
| Coût | Essai de 30 jours avec 5 $ de crédit, sans carte ; ensuite 1 $/mois limité, ou Hobby à partir de 5 $/mois | 0 $ (750 h/mois) ; disque persistant à partir de 7 $/mois + 0,25 $/Go | Non pertinent |

Vercel est écarté parce que l'architecture repose sur un processus permanent et un fichier SQLite local. Le changer imposerait une réécriture sans bénéfice pour ce projet.

**Attention :** l'essai Railway se termine 30 jours après sa création. Sans passage à une offre payante, le site s'arrête.

## 2. Variables d'environnement

| Variable | Rôle |
|---|---|
| `PRISME_MODE=public` | Production : ni contenu fictif ni profils de démonstration (déjà défini dans le Dockerfile) |
| `PRISME_ADMIN_USER`, `PRISME_ADMIN_PASSWORD` | Compte administrateur. Sans eux, aucun compte admin n'existe. Jamais dans le code |
| `PRISME_DB=/data/prisme.db` | Emplacement de la base, sur le volume (déjà défini dans le Dockerfile) |
| `PRISME_REFRESH_MINUTES` | Intervalle de collecte des flux (30 par défaut) |
| `PRISME_SITE_URL` | Adresse publique, utile avec un domaine personnalisé (les adresses Railway et Render sont détectées seules) |
| `RAILWAY_RUN_UID=0` | Sur Railway : permet d'écrire sur le volume |

## 3. Mise en ligne avec Railway

```powershell
npx @railway/cli login
npx @railway/cli init --name prisme
npx @railway/cli up --detach
npx @railway/cli volume add --mount-path /data
npx @railway/cli variables --set "PRISME_ADMIN_USER=redaction" --set "PRISME_ADMIN_PASSWORD=<mot de passe long>" --set "RAILWAY_RUN_UID=0"
npx @railway/cli domain
```

Contrôle : `https://<adresse>/healthz` doit répondre `"status": "ok"`.

## 4. Solution de secours : Render

Pousser le dépôt sur GitHub, puis dans Render : *New > Blueprint*, choisir le dépôt (le fichier `render.yaml` est lu automatiquement) et renseigner `PRISME_ADMIN_PASSWORD`. Ouvrir le site 2 minutes avant toute présentation. Les comptes créés disparaissent à chaque endormissement.

## 5. Fonctionnement en production

- **Serveur :** gunicorn, 1 processus et 8 fils. Ne pas augmenter le nombre de processus : la collecte programmée et la limitation de débit vivent en mémoire.
- **Sauvegarde :** le fichier `/data/prisme.db` contient les comptes et les favoris. Railway ne le sauvegarde pas pour vous sur l'offre d'essai.
- **Journaux :** visibles dans le tableau de bord Railway. Les erreurs détaillées n'y figurent que côté serveur, jamais dans les réponses.
- **HTTPS :** fourni par la plateforme ; l'en-tête HSTS est envoyé par l'application.

## 6. Google Search Console

Un site déployé n'est pas pour autant référencé. L'indexation prend de quelques jours à plusieurs semaines et n'est pas garantie. Une adresse `*.up.railway.app` fonctionne, mais un domaine à vous est préférable.

1. Sur [search.google.com/search-console](https://search.google.com/search-console), ajouter la propriété en mode **Préfixe de l'URL** (ou **Domaine** avec un nom de domaine à vous).
2. Vérifier la propriété. Avec une adresse Railway : méthode **balise HTML**, puis ajouter la balise dans `web/index.html` et redéployer. Avec un domaine : enregistrement DNS TXT.
3. Soumettre le sitemap : `https://<adresse>/sitemap.xml`.
4. Dans *Inspection de l'URL*, demander l'indexation de l'accueil et de 2 ou 3 pages `/sujet/…`.
5. Après 1 à 2 semaines, consulter *Pages* (erreurs d'indexation) et *Performances* (impressions, clics, requêtes).

### Choix SEO appliqués

- Pages lisibles sans JavaScript, URL propres, titres, descriptions, canonique, Open Graph, `robots.txt`, `sitemap.xml`, vrais codes 404.
- **Indexées :** accueil, rubriques, tendances, digest, méthode, médias suivis et pages de comparaison entre plusieurs médias. Ce sont celles qui apportent une valeur propre.
- **Non indexées (`noindex`) :** pages d'un article seul. Un extrait n'apporte rien de plus que l'original, et les multiplier exposerait le site aux règles de Google sur le contenu de faible valeur.
- **Données structurées :** `WebSite` sur l'accueil ; sur les comparaisons, une liste de `NewsArticle` décrivant les articles originaux, avec leur URL et leur éditeur. Prisme ne se présente pas comme l'auteur de ces articles.

### Google Analytics

Non installé. Il exigerait une bannière de consentement et un assouplissement de la politique de sécurité (CSP). Les données de la Search Console suffisent pour commencer.

## 7. Conditions d'utilisation des flux

À vérifier avant une exploitation durable ou commerciale : les conditions de réutilisation des flux RSS de chaque média. Prisme affiche titres et extraits et renvoie vers l'original, mais cela ne remplace pas une lecture de ces conditions, ni un avis juridique.
