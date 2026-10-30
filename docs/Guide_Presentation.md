# Guide de présentation — Prisme (≈ 12 minutes)

Scénario de démonstration conçu pour la soutenance du Groupe 7 (ESATIC, L3 TWIN). Chaque étape illustre une fonctionnalité du cahier des charges.

**Avant la séance :** lancer `Lancer_Prisme.bat` 5 minutes à l'avance (collecte des flux réels), vérifier la connexion Internet, agrandir le navigateur en plein écran (F11). Ce scénario utilise le **mode démonstration local**. Le site public, lui, ne contient que des médias réels : ouvrez-le à part pour montrer la version en ligne.

---

## 1. Introduction (1 min) — page *Le projet*

- Présenter la problématique : fragmentation de l'information, doublons, désinformation, bulle de filtres.
- Montrer le tableau **MoSCoW** : tout l'indispensable, le très important et le « ensuite » sont réalisés ; le « plus tard » est planifié.
- Montrer le tableau **Personas → fonctionnalités**.

## 2. Agrégation et doublons (2 min) — *Fil d'actualité* (sans être connecté)

- Présenter la une, puis la section **« Un événement, plusieurs regards »** : le **spectre** montre une barre par média.
- Rechercher « carburant » : une seule entrée par média, et le bouton **Comparer** réunit les quatre traitements.
- Montrer une carte issue d'un flux réel (France 24, RFI…) avec le bouton *Lire l'article original*.

## 3. Comparaison des sources (1 min 30) — clic sur « comparer »

- **Résumé automatique** (extraction de phrases) avec citations numérotées.
- **Divergences chiffrées** : 5 % (3 médias) contre 15 % (InfoBuzz225).
- Colonnes par média : ton (*sensationnaliste*), angle spécifique, rang de publication, chronologie.

## 4. Recoupement (2 min) — article « URGENT !! … 15 % »

- Bandeau et statut **Chiffres divergents** ; source fictive à 25/100 (les vrais médias ne sont pas notés).
- Onglet **Recoupement** : phrases détectées (chiffre, rumeur) et passages où d'autres médias donnent une **version différente** (Abidjan Matin, Quotidien Lagunaire).
- Onglet **Résumé automatique** : chaque phrase est copiée de la source citée.
- Montrer la page **Notre méthode** : Prisme mesure la couverture, il ne certifie pas les faits. C'est un choix éthique à expliquer au jury.

## 5. Indicateur de fraîcheur (1 min) — recherche « 18 morts »

- Article « Inondations à Abidjan : 18 morts » : badge **« Ancienne info qui recircule »** et bandeau rouge (publié en 2024, réapparu cette semaine).

## 6. Personnalisation transparente (1 min 30) — se connecter en **Aminata**

- Fil *Pour vous* : **indice de diversité**, cartes **« Découverte »** (anti-bulle).
- Bouton **(?) « Pourquoi ? »** : raisons et contribution de chaque critère.
- *Paramètres* : curseurs d'intérêts et part de découverte.

## 7. Veille, alertes et notifications (1 min)

- *Veille et alertes* (menu en haut à gauche) : ajouter le mot-clé « Sénégal » → notifications créées immédiatement.
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
- *Le digest du jour* (Mme Kouassi) : export PDF et envoi par e-mail.

## 11. Conclusion (30 s) — compte **admin** → *Administration*

- Indicateurs : volume, taux de doublons, répartition de la couverture, journal des modifications.
- Rappeler les limites (pas de certification des faits, pas de regroupement entre langues) et les perspectives.

---

### Questions probables du jury

- **Pourquoi pas un grand modèle de langage ?** Choix d'une IA *explicable*, gratuite et hors-ligne : chaque décision (doublon, statut, recommandation) peut être justifiée ; un LLM est prévu en « plus tard » pour les synthèses complexes.
- **Comment éviter la bulle de filtres ?** Quota de découverte réglable + indice de diversité visible + critères affichés.
- **Fiabilité des sources ?** Prisme ne note pas les vrais médias : une note subjective publique serait contestable. Il montre des faits : pays, type de média, nombre de médias sur le sujet, écarts de chiffres.
- **Données personnelles ?** Mots de passe hachés, historique effaçable, aucune revente ni traçage, aucun outil d'analyse tiers.
- **Pourquoi « Vérifié » a disparu ?** Plusieurs médias peuvent reprendre la même dépêche : une reprise n'est pas une preuve. Le rapport écrit parle de vérification ; le produit a évolué vers un libellé plus honnête.
