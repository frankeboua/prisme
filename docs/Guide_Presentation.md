# Guide de présentation — Prisme (≈ 12 minutes)

Scénario de démonstration conçu pour la soutenance du Groupe 7 (ESATIC, L3 TWIN). Chaque étape illustre une fonctionnalité du cahier des charges.

**Avant la séance :** lancer `Lancer_Prisme.bat` 5 minutes à l'avance (collecte des flux réels), vérifier la connexion Internet, agrandir le navigateur en plein écran (F11).

---

## 1. Introduction (1 min) — page *Le projet*

- Présenter la problématique : fragmentation de l'information, doublons, désinformation, bulle de filtres.
- Montrer le tableau **MoSCoW** : tout l'indispensable, le très important et le « ensuite » sont réalisés ; le « plus tard » est planifié.
- Montrer le tableau **Personas → fonctionnalités**.

## 2. Agrégation et doublons (2 min) — *Fil d'actualité* (sans être connecté)

- Chiffres du bandeau : contenus agrégés, sources, **doublons regroupés**.
- Carte « Le prix du carburant augmente de 5 % » : **« 3 autres médias — comparer »** → une seule carte au lieu de quatre.
- Montrer une carte issue d'un flux réel (France 24, RFI…) avec le bouton *Lire l'article original*.

## 3. Comparaison des sources (1 min 30) — clic sur « comparer »

- **Synthèse multi-sources** avec citations numérotées.
- **Divergences chiffrées** : 5 % (3 médias) contre 15 % (InfoBuzz225).
- Colonnes par média : fiabilité, ton (*sensationnaliste*), angle spécifique, rang de publication, chronologie.

## 4. Vérification assistée par IA (2 min) — article « URGENT !! … 15 % »

- Bandeau **Prudence**, statut **Contesté**, score 0/100, source à 25/100.
- Onglet **Vérification** : affirmations détectées (chiffre, rumeur), preuves qui **contredisent** (Abidjan Matin, Quotidien Lagunaire).
- Onglet **Résumé IA** : le résumé s'appuie sur les sources fiables, chaque phrase est citée.
- Ouvrir ensuite « Paludisme : le ministère dément… » : démenti **corroboré**.

## 5. Indicateur de fraîcheur (1 min) — recherche « 18 morts »

- Article « Inondations à Abidjan : 18 morts » : badge **« Ancienne info qui recircule »** et bandeau rouge (publié en 2024, réapparu cette semaine).

## 6. Personnalisation transparente (1 min 30) — se connecter en **Aminata**

- Fil *Pour vous* : **indice de diversité**, cartes **« Découverte »** (anti-bulle).
- Bouton **(?) « Pourquoi ? »** : raisons et contribution de chaque critère.
- *Paramètres* : curseurs d'intérêts et part de découverte.

## 7. Veille, alertes et notifications (1 min)

- *Veille & alertes* : ajouter le mot-clé « Sénégal » → notifications créées immédiatement.
- Cloche : notifications d'alertes et de suivi des signalements.

## 8. Signalement d'erreurs (1 min)

- Sur un article, **⚑ Signaler une erreur** (type + description + preuve).
- Se connecter en **admin** → *Signalements* : passer à « Corrigé » avec une note → la correction apparaît sur l'article et le lecteur est notifié.

## 9. Accessibilité, traduction, simplification (1 min)

- Article anglais « Africa's largest solar power plant… » → onglet **Traduction**.
- Onglet **Simplification** : score de lisibilité avant / après, mots expliqués.
- Se connecter en **Paul** : grande police, mode simplifié ; *Paramètres* → contraste élevé, thème sombre.

## 10. Community management (30 s) — se connecter en **Yao**

- *Tendances* : hashtags classés par nombre de médias, bouton **Créer un post** (texte prêt à copier pour les réseaux sociaux), partage WhatsApp / LinkedIn / X.
- *Digest du jour* (Mme Kouassi) : export PDF et envoi par e-mail.

## 11. Conclusion (30 s) — compte **admin** → *Administration*

- Indicateurs : volume, taux de doublons, répartition des statuts de vérification, sources.
- Rappeler les limites (vérification *assistée*) et les perspectives (« plus tard »).

---

### Questions probables du jury

- **Pourquoi pas un grand modèle de langage ?** Choix d'une IA *explicable*, gratuite et hors-ligne : chaque décision (doublon, statut, recommandation) peut être justifiée ; un LLM est prévu en « plus tard » pour les synthèses complexes.
- **Comment éviter la bulle de filtres ?** Quota de découverte réglable + indice de diversité visible + critères affichés.
- **Fiabilité des sources ?** Score indicatif, paramétrable par l'administrateur, combiné à la corroboration par d'autres médias.
- **Données personnelles ?** Base locale, mots de passe hachés, historique effaçable, aucune revente ni traçage.
