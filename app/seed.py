"""Jeu de données initial : référentiels, sources réelles, contenus de démonstration, comptes."""
import hashlib
import hmac
import math
import os
import secrets
import struct
import wave
from datetime import timedelta

from . import db, nlp
from .db import ROOT

CATEGORIES = [
    ("politique", "Politique", "#6366f1"), ("economie", "Économie", "#0ea5e9"), ("societe", "Société", "#14b8a6"),
    ("sport", "Sport", "#22c55e"), ("sante", "Santé", "#ef4444"), ("tech", "Tech & Numérique", "#8b5cf6"),
    ("culture", "Culture", "#f59e0b"), ("environnement", "Environnement", "#10b981"), ("international", "International", "#64748b"),
]

NOTE = None
# nom, site, flux, pays, langue, type, catégorie par défaut, fiabilité, certifiée
REAL_SOURCES = [
    ("France 24", "https://www.france24.com", "https://www.france24.com/fr/rss", "France", "fr", "tv", "international", 85, 1),
    ("RFI Afrique", "https://www.rfi.fr", "https://www.rfi.fr/fr/afrique/rss", "France", "fr", "radio", "international", 85, 1),
    ("BBC Afrique", "https://www.bbc.com/afrique", "https://feeds.bbci.co.uk/afrique/rss.xml", "Royaume-Uni", "fr", "tv", "international", 86, 1),
    ("Le Monde Afrique", "https://www.lemonde.fr/afrique", "https://www.lemonde.fr/afrique/rss_full.xml", "France", "fr", "presse", "international", 86, 1),
    ("Le Monde — À la une", "https://www.lemonde.fr", "https://www.lemonde.fr/rss/une.xml", "France", "fr", "presse", None, 86, 1),
    ("Jeune Afrique", "https://www.jeuneafrique.com", "https://www.jeuneafrique.com/feed/", "France", "fr", "presse", "politique", 80, 1),
    ("Franceinfo", "https://www.francetvinfo.fr", "https://www.francetvinfo.fr/titres.rss", "France", "fr", "tv", None, 82, 1),
    ("BBC News World", "https://www.bbc.com/news", "https://feeds.bbci.co.uk/news/world/rss.xml", "Royaume-Uni", "en", "tv", "international", 86, 1),
    ("Al Jazeera English", "https://www.aljazeera.com", "https://www.aljazeera.com/xml/rss/all.xml", "Qatar", "en", "tv", "international", 78, 1),
    ("01net", "https://www.01net.com", "https://www.01net.com/actualites/feed/", "France", "fr", "web", "tech", 72, 0),
    ("Numerama", "https://www.numerama.com", "https://www.numerama.com/feed/", "France", "fr", "web", "tech", 74, 0),
    ("AIP (Agence ivoirienne de presse)", "https://www.aip.ci", "https://www.aip.ci/feed/", "Côte d'Ivoire", "fr", "agence", "societe", 70, 0),
    ("RTI Info", "https://www.rti.info", "https://www.rti.info/feed", "Côte d'Ivoire", "fr", "tv", "societe", 70, 0),
    ("Connectionivoirienne", "https://www.connectionivoirienne.net", "https://www.connectionivoirienne.net/feed/", "Côte d'Ivoire", "fr", "web", "politique", 70, 0),
    ("L'Équipe", "https://www.lequipe.fr", "https://dwh.lequipe.fr/api/edito/rss?path=/Football/", "France", "fr", "presse", "sport", 70, 0),
    # Flux par rubrique des mêmes médias : plus d'articles à trouver, comptés comme un seul média par éditeur.
    ("France 24 Culture", "https://www.france24.com", "https://www.france24.com/fr/culture/rss", "France", "fr", "tv", "culture", 70, 0),
    ("France 24 Économie", "https://www.france24.com", "https://www.france24.com/fr/%C3%A9co-tech/rss", "France", "fr", "tv", "economie", 70, 0),
    ("RFI Sports", "https://www.rfi.fr", "https://www.rfi.fr/fr/sports/rss", "France", "fr", "radio", "sport", 70, 0),
    ("RFI Culture", "https://www.rfi.fr", "https://www.rfi.fr/fr/culture/rss", "France", "fr", "radio", "culture", 70, 0),
    ("RFI Économie", "https://www.rfi.fr", "https://www.rfi.fr/fr/economie/rss", "France", "fr", "radio", "economie", 70, 0),
    ("RFI Science", "https://www.rfi.fr", "https://www.rfi.fr/fr/science/rss", "France", "fr", "radio", "tech", 70, 0),
    ("Le Monde Économie", "https://www.lemonde.fr", "https://www.lemonde.fr/economie/rss_full.xml", "France", "fr", "presse", "economie", 70, 0),
    ("Le Monde Culture", "https://www.lemonde.fr", "https://www.lemonde.fr/culture/rss_full.xml", "France", "fr", "presse", "culture", 70, 0),
    ("Le Monde Sport", "https://www.lemonde.fr", "https://www.lemonde.fr/sport/rss_full.xml", "France", "fr", "presse", "sport", 70, 0),
    ("Le Monde Santé", "https://www.lemonde.fr", "https://www.lemonde.fr/sante/rss_full.xml", "France", "fr", "presse", "sante", 70, 0),
    ("Le Monde Planète", "https://www.lemonde.fr", "https://www.lemonde.fr/planete/rss_full.xml", "France", "fr", "presse", "environnement", 70, 0),
    ("Le Monde Politique", "https://www.lemonde.fr", "https://www.lemonde.fr/politique/rss_full.xml", "France", "fr", "presse", "politique", 70, 0),
    ("Franceinfo Culture", "https://www.francetvinfo.fr", "https://www.francetvinfo.fr/culture.rss", "France", "fr", "tv", "culture", 70, 0),
    ("Franceinfo Santé", "https://www.francetvinfo.fr", "https://www.francetvinfo.fr/sante.rss", "France", "fr", "tv", "sante", 70, 0),
    ("Franceinfo Économie", "https://www.francetvinfo.fr", "https://www.francetvinfo.fr/economie.rss", "France", "fr", "tv", "economie", 70, 0),
    ("Franceinfo Sports", "https://www.francetvinfo.fr", "https://www.francetvinfo.fr/sports.rss", "France", "fr", "tv", "sport", 70, 0),
    ("BBC Sport", "https://www.bbc.com/sport", "https://feeds.bbci.co.uk/sport/rss.xml", "Royaume-Uni", "en", "tv", "sport", 70, 0),
    ("Radio France — Le Cours de l'histoire", "https://www.radiofrance.fr", "https://radiofrance-podcast.net/podcast09/rss_10076.xml", "France", "fr", "podcast", "culture", 85, 1),
]

DEMO_NOTE = "Source fictive créée pour la démonstration pédagogique (aucun lien avec un média réel)."
DEMO_SOURCES = {
    "matin": ("Abidjan Matin (démo)", "presse", "fr", "societe", 82, 1),
    "lagunaire": ("Le Quotidien Lagunaire (démo)", "presse", "fr", "societe", 78, 1),
    "eco": ("Afrique Éco Hebdo (démo)", "presse", "fr", "economie", 85, 1),
    "plateau": ("Radio Plateau FM (démo)", "radio", "fr", "societe", 74, 0),
    "techivoire": ("TechIvoire (démo)", "web", "fr", "tech", 76, 0),
    "buzz": ("InfoBuzz225 (démo)", "web", "fr", "societe", 25, 0),
    "sahel": ("Sahel Observateur (démo)", "presse", "fr", "international", 70, 0),
    "reseaux": ("Tendances Réseaux (démo)", "social", "fr", "culture", 40, 0),
    "campus": ("Podcast Campus ESATIC (démo)", "podcast", "fr", "tech", 70, 0),
    "global": ("Global Daily (demo)", "presse", "en", "international", 80, 1),
}

H = 1
D = 24
Y = 24 * 365
# clé, source, catégorie, âge (h), titre, texte, [type média], [auteur], [vu depuis (h)]
ARTICLES = [
    # --- Doublons A : hausse du carburant (4 médias, dont 1 peu fiable qui exagère) ---
    ("A1", "matin", "economie", 5, "Le prix du carburant augmente de 5 % à partir du 1er novembre",
     "Le gouvernement a annoncé ce mardi une hausse de 5 % du prix du super sans plomb et du gasoil à compter du 1er novembre. "
     "Selon le ministère des Mines et de l'Énergie, cette décision est liée à la hausse des cours du pétrole sur les marchés internationaux. "
     "Le litre de super passera ainsi à 920 FCFA. Les syndicats de transporteurs ont exprimé leur inquiétude face à l'impact sur les tarifs des transports en commun. "
     "Le ministère assure que le prix du gaz butane restera inchangé jusqu'à la fin de l'année.", None, "Awa Koné"),
    ("A2", "lagunaire", "economie", 4, "Carburant : le gouvernement annonce une hausse de 5 % du prix à la pompe",
     "Les automobilistes paieront plus cher leur carburant dès le 1er novembre. Le gouvernement a confirmé une hausse de 5 % du prix du super et du gasoil. "
     "Le litre de super passera à 920 FCFA, a indiqué le porte-parole du gouvernement à l'issue du Conseil des ministres. "
     "Les transporteurs menacent d'une grève si les tarifs des transports ne sont pas encadrés. "
     "Le gouvernement explique cette mesure par l'envolée des cours du pétrole.", None, "Jean-Marc Yao"),
    ("A3", "plateau", "economie", 3, "Hausse du prix du carburant : le super à 920 FCFA dès novembre",
     "« Cette hausse de 5 % est indispensable pour préserver l'équilibre budgétaire », a déclaré le porte-parole du gouvernement au micro de Radio Plateau FM. "
     "Le litre de super passera à 920 FCFA à partir du 1er novembre. Les associations de consommateurs dénoncent une mesure qui pèsera sur le pouvoir d'achat des ménages. "
     "Le gouvernement promet des mesures d'accompagnement pour les taxis communaux.", None, None),
    ("A4", "buzz", "economie", 2, "URGENT !! Le prix du carburant augmente de 15 % : le gouvernement cache la vérité",
     "Selon nos informations, la hausse du prix du carburant serait en réalité de 15 % et non de 5 % comme annoncé. "
     "Le litre de super atteindrait 1 060 FCFA dès la fin du mois. Les autorités ne veulent pas que vous le sachiez. "
     "Partagez avant que ce soit supprimé !!", None, None),
    # --- Doublons B : programme national de fibre optique ---
    ("B1", "techivoire", "tech", 8, "Lancement d'un programme national de fibre optique pour connecter 5 000 villages",
     "Le ministère de la Transition numérique a lancé lundi un programme visant à connecter 5 000 villages à la fibre optique d'ici 2028. "
     "Le projet est estimé à 150 milliards FCFA. Selon le ministre, plus de 2 millions d'habitants bénéficieront d'un accès Internet haut débit. "
     "Des centres numériques communautaires seront installés dans chaque chef-lieu de département afin de former les jeunes aux métiers du numérique.", None, "Koffi N'Guessan"),
    ("B2", "matin", "tech", 7, "Fibre optique : 5 000 villages bientôt connectés selon le programme national",
     "Le gouvernement a présenté un programme national de fibre optique qui doit raccorder 5 000 villages d'ici 2028. "
     "Le coût total est évalué à 150 milliards FCFA. Selon le ministre de la Transition numérique, plus de 2 millions d'habitants auront accès à l'Internet haut débit. "
     "Les opérateurs de téléphonie seront associés au déploiement.", None, "Awa Koné"),
    ("B3", "eco", "economie", 6, "Programme national de fibre optique : un investissement de 150 milliards FCFA pour les villages",
     "Le programme national de fibre optique représente un investissement de 150 milliards FCFA, financé en partie par la Banque africaine de développement. "
     "Pour les économistes, la connexion de 5 000 villages pourrait stimuler l'inclusion financière grâce au mobile money. "
     "La rentabilité du projet dépendra toutefois du taux d'adoption dans les zones rurales.", None, "Mariam Diallo"),
    # --- Doublons C : inondations + article ancien qui recircule ---
    ("C1", "lagunaire", "environnement", 10, "Fortes pluies à Abidjan : plusieurs quartiers inondés, la protection civile mobilisée",
     "De fortes pluies se sont abattues sur Abidjan dans la nuit de lundi à mardi. Les communes de Cocody, Yopougon et Abobo sont les plus touchées. "
     "Selon la protection civile, 3 personnes ont été blessées et aucun décès n'a été enregistré. "
     "La SODEXAM prévoit de nouvelles pluies dans les prochaines 48 heures et appelle les habitants des zones à risque à la prudence.", None, "Jean-Marc Yao"),
    ("C2", "plateau", "environnement", 9, "Inondations à Abidjan : Cocody, Yopougon et Abobo sous les eaux après de fortes pluies",
     "Plusieurs quartiers d'Abidjan sont inondés après les fortes pluies de la nuit. Selon la protection civile, 3 personnes ont été blessées. "
     "Les secours sont intervenus à Cocody, Yopougon et Abobo. La circulation reste perturbée sur plusieurs axes du district.", None, None),
    ("C3", "reseaux", "environnement", 6, "#AbidjanSousLaPluie : une vidéo virale montre une rue d'Abidjan transformée en rivière après les fortes pluies",
     "La vidéo, partagée plus de 40 000 fois en quelques heures, montre une rue inondée de Yopougon. "
     "Certains internautes affirment à tort qu'elle date d'aujourd'hui alors que des images similaires circulaient déjà en 2024.", "social", None),
    ("C4", "matin", "environnement", 2 * Y + 130 * D, "Inondations à Abidjan : 18 morts après des pluies diluviennes",
     "Des pluies diluviennes ont provoqué la mort de 18 personnes à Abidjan, selon un bilan provisoire de la protection civile. "
     "Les communes d'Abobo et d'Attécoubé sont les plus touchées. Le gouvernement a décrété un deuil national de trois jours.", None, "Rédaction", 20),
    # --- Doublons D : sport ---
    ("D1", "matin", "sport", 20, "CAN 2027 : les Éléphants qualifiés après leur victoire 2-0 face au Bénin",
     "La Côte d'Ivoire a validé son billet pour la CAN 2027 en s'imposant 2-0 face au Bénin. "
     "Les deux buts ont été inscrits en seconde période. Le sélectionneur a salué « un groupe solidaire et ambitieux ».", None, "Ibrahim Traoré"),
    ("D2", "sahel", "sport", 18, "Football : les Éléphants de Côte d'Ivoire qualifiés pour la CAN 2027 face au Bénin",
     "Grâce à une victoire 2-0 face au Bénin, les Éléphants sont qualifiés pour la CAN 2027. "
     "Il s'agit de la neuvième qualification consécutive de la sélection ivoirienne.", None, None),
    ("D3", "plateau", "sport", 19, "Les Éléphants qualifiés pour la CAN 2027 : victoire 2-0 contre le Bénin",
     "Soirée de fête au stade : les Éléphants battent le Bénin 2-0 et se qualifient pour la CAN 2027. Les supporters ont célébré la victoire jusque tard dans la nuit.", None, None),
    # --- Doublons E : rumeur santé et démentis ---
    ("E1", "buzz", "sante", 30, "Incroyable : une plante miracle guérit le paludisme en 24 heures, les médecins ne veulent pas que vous le sachiez",
     "Selon un guérisseur, une infusion de feuilles guérirait 100 % des cas de paludisme en 24 heures. "
     "Les hôpitaux seraient déjà en rupture de stock de médicaments à cause de cette découverte. Partagez avant que ce soit supprimé !!", None, None),
    ("E2", "matin", "sante", 26, "Paludisme : le ministère de la Santé dément l'existence d'une plante miracle qui guérit en 24 heures",
     "Le ministère de la Santé a démenti mercredi les informations circulant sur les réseaux sociaux selon lesquelles une plante guérirait le paludisme en 24 heures. "
     "Il n'existe aucune preuve scientifique de cette affirmation, a indiqué le directeur du Programme national de lutte contre le paludisme. "
     "Le ministère rappelle que le traitement recommandé reste les combinaisons thérapeutiques à base d'artémisinine, disponibles dans les centres de santé.", None, "Awa Koné"),
    ("E3", "lagunaire", "sante", 25, "Plante miracle contre le paludisme : une fausse information selon les autorités sanitaires",
     "Les autorités sanitaires qualifient de fausse information la rumeur d'une plante qui guérirait le paludisme en 24 heures. "
     "Aucune rupture de stock de médicaments n'a été constatée dans les hôpitaux, selon la Nouvelle pharmacie de la santé publique.", None, None),
    # --- Doublons F : startup IA ---
    ("F1", "techivoire", "tech", 30, "Une startup ivoirienne d'intelligence artificielle lève 2 milliards FCFA",
     "La startup abidjanaise spécialisée en intelligence artificielle a annoncé une levée de fonds de 2 milliards FCFA. "
     "L'entreprise développe des outils de traduction automatique vers les langues locales comme le baoulé et le dioula. "
     "Elle prévoit de recruter 40 ingénieurs d'ici fin 2027.", None, "Koffi N'Guessan"),
    ("F2", "eco", "tech", 28, "Intelligence artificielle : une startup ivoirienne lève 2 milliards FCFA pour s'étendre en Afrique de l'Ouest",
     "Avec une levée de 2 milliards FCFA, la startup ivoirienne d'intelligence artificielle souhaite s'implanter au Sénégal et au Ghana. "
     "Selon son fondateur, l'IA appliquée aux langues africaines représente un marché en forte croissance.", None, "Mariam Diallo"),
    # --- Doublons G : cacao ---
    ("G1", "eco", "economie", 60, "Cacao : le prix bord champ fixé à 2 200 FCFA le kilogramme pour la campagne principale",
     "Le Conseil du café-cacao a fixé le prix bord champ du cacao à 2 200 FCFA le kilogramme pour la campagne principale. "
     "Selon le Conseil, cette hausse doit améliorer le revenu des producteurs dans un contexte de prix mondiaux élevés.", None, "Mariam Diallo"),
    ("G2", "matin", "economie", 58, "Campagne cacao : le prix bord champ passe à 2 200 FCFA le kilogramme",
     "Les producteurs de cacao percevront 2 200 FCFA par kilogramme pendant la campagne principale, a annoncé le Conseil du café-cacao. "
     "Les coopératives saluent une décision attendue.", None, None),
    # --- Articles uniques (diversité thématique) ---
    ("S1", "lagunaire", "politique", 14, "Assemblée nationale : les députés adoptent le budget de l'État pour 2027",
     "Les députés ont adopté en séance plénière le projet de loi de finances pour 2027. Selon le ministre du Budget, le budget s'élève à 15 000 milliards FCFA, "
     "en hausse de 8 % par rapport à l'exercice précédent. L'éducation et la santé restent les premiers postes de dépenses. "
     "L'opposition a dénoncé un niveau d'endettement trop élevé.", None, "Jean-Marc Yao"),
    ("S2", "matin", "culture", 40, "Festival des musiques urbaines d'Anoumabo : 100 000 festivaliers attendus",
     "La nouvelle édition du Festival des musiques urbaines d'Anoumabo s'ouvre ce week-end. Les organisateurs attendent 100 000 festivaliers durant cinq jours. "
     "Des artistes de huit pays sont annoncés à l'affiche.", None, None),
    ("S3", "plateau", "societe", 12, "Rentrée universitaire : les inscriptions en ligne prolongées jusqu'au 15 novembre",
     "Le ministère de l'Enseignement supérieur a prolongé la période d'inscription en ligne jusqu'au 15 novembre. "
     "Cette décision fait suite à des difficultés techniques signalées par de nombreux étudiants sur la plateforme.", None, None),
    ("S4", "sahel", "international", 15, "Sommet de l'Union africaine : les chefs d'État réunis à Addis-Abeba sur la sécurité au Sahel",
     "Les chefs d'État de l'Union africaine sont réunis à Addis-Abeba pour un sommet consacré à la sécurité au Sahel. "
     "Selon la Commission de l'UA, plus de 4 millions de personnes sont déplacées dans la région. Une déclaration commune est attendue jeudi.", None, "Oumar Sangaré"),
    ("S5", "eco", "environnement", 50, "Reboisement : 50 millions d'arbres plantés en 2026 selon le ministère des Eaux et Forêts",
     "Le ministère des Eaux et Forêts affirme que 50 millions d'arbres ont été plantés en 2026 dans le cadre de l'opération « Un jour, 50 millions d'arbres ». "
     "Des ONG environnementales demandent un suivi indépendant du taux de survie des plants.", None, None),
    ("S6", "lagunaire", "sante", 70, "Vaccination contre la rougeole : 3 millions d'enfants ciblés par une campagne nationale",
     "Une campagne nationale de vaccination contre la rougeole vise 3 millions d'enfants âgés de 9 mois à 5 ans. "
     "Les équipes mobiles se déploieront dans les écoles, les marchés et les lieux de culte pendant dix jours.", None, None),
    ("S7", "techivoire", "tech", 16, "Cybersécurité : hausse des arnaques au mobile money, la police appelle à la vigilance",
     "La Plateforme de lutte contre la cybercriminalité signale une hausse des arnaques au mobile money. "
     "Les escrocs se font passer pour des agents d'opérateurs et demandent le code secret des victimes. "
     "La police rappelle qu'aucun opérateur ne demande jamais votre code confidentiel.", None, "Koffi N'Guessan"),
    ("S8", "sahel", "sport", 80, "Athlétisme : un record national battu au 100 mètres lors du meeting d'Abidjan",
     "Un sprinteur ivoirien a battu le record national du 100 mètres en 9 secondes 94 lors du meeting international d'Abidjan.", None, None),
    ("S9", "matin", "societe", 100, "Métro d'Abidjan : point d'étape sur les travaux de la ligne 1",
     "Les travaux de la ligne 1 du métro d'Abidjan avancent selon le calendrier prévu, a indiqué le ministère des Transports. "
     "La ligne reliera Anyama au nord à l'aéroport au sud sur 37 km.", None, None),
    ("S10", "eco", "economie", 200 * D, "Analyse : dix ans de croissance économique en Côte d'Ivoire",
     "Depuis dix ans, la Côte d'Ivoire affiche une croissance moyenne supérieure à 6 % par an selon la Banque mondiale. "
     "Les économistes soulignent cependant la persistance des inégalités entre zones urbaines et rurales.", None, "Mariam Diallo", 200 * D),
    ("S11", "reseaux", "culture", 30, "Le challenge « Zouglou Dance » enflamme TikTok avec plus de 2 millions de vues",
     "Lancé par un collectif d'étudiants, le challenge « Zouglou Dance » cumule plus de 2 millions de vues sur TikTok. "
     "Plusieurs artistes ont repris la chorégraphie, contribuant à la viralité du mouvement.", "social", None),
    ("S12", "reseaux", "societe", 4, "Publication virale : « les cours seront suspendus toute la semaine », une affirmation non confirmée",
     "Un message affirmant que les cours seraient suspendus toute la semaine à cause des pluies circule sur WhatsApp. "
     "Aucune annonce officielle du ministère de l'Éducation n'a été publiée à ce stade.", "social", None),
    # --- Contenus en anglais (traduction) ---
    ("EN1", "global", "environnement", 12, "Africa's largest solar power plant begins operations in the Sahel",
     "The largest solar power plant in Africa has begun operations in the Sahel, according to the regional energy agency. "
     "The facility will produce 500 MW of electricity and supply power to more than one million homes. "
     "Officials said the project was financed by a consortium of international development banks.", None, "Sarah Mitchell"),
    ("EN2", "global", "economie", 20, "Cocoa prices reach new highs as global supply tightens",
     "Cocoa prices reached new highs on international markets this week as supply from West Africa tightened. "
     "Analysts said weather conditions and ageing plantations explain the drop in production. "
     "Ivory Coast and Ghana produce more than 60% of the world's cocoa.", None, "David Brown"),
    # --- Podcasts de démonstration ---
    ("P1", "campus", "tech", 9, "Épisode 12 — Comment reconnaître une fausse information en moins de 2 minutes ?",
     "Dans cet épisode, l'équipe du podcast Campus présente une méthode simple pour vérifier une information : identifier la source, vérifier la date, "
     "rechercher d'autres médias qui traitent le même sujet et se méfier des titres sensationnalistes.", "podcast", "Groupe 7"),
    ("P2", "campus", "culture", 50, "Épisode 11 — Les métiers du community management en 2026",
     "Veille, création de contenus, modération et analyse des statistiques : tour d'horizon des compétences attendues d'un community manager.", "podcast", "Groupe 7"),
]

TRANSLATIONS = {
    "EN1": ("La plus grande centrale solaire d'Afrique entre en service au Sahel",
            "La plus grande centrale solaire d'Afrique est entrée en service au Sahel, selon l'agence régionale de l'énergie. "
            "L'installation produira 500 MW d'électricité et alimentera plus d'un million de foyers. "
            "Les responsables ont indiqué que le projet a été financé par un consortium de banques internationales de développement."),
    "EN2": ("Les prix du cacao atteignent de nouveaux records alors que l'offre mondiale se resserre",
            "Les prix du cacao ont atteint de nouveaux sommets sur les marchés internationaux cette semaine, l'offre en provenance d'Afrique de l'Ouest se resserrant. "
            "Selon les analystes, les conditions météorologiques et le vieillissement des plantations expliquent la baisse de la production. "
            "La Côte d'Ivoire et le Ghana produisent plus de 60 % du cacao mondial."),
}

GLOSSARY = [
    ("conseil des ministres", "réunion du gouvernement", "Réunion hebdomadaire du Président et des ministres."),
    ("loi de finances", "loi qui fixe le budget", "Texte voté chaque année qui fixe les recettes et les dépenses de l'État."),
    ("équilibre budgétaire", "équilibre entre dépenses et recettes de l'État", None),
    ("pouvoir d'achat", "ce que l'on peut acheter avec son argent", None),
    ("endettement", "dettes", None),
    ("inflation", "hausse générale des prix", None),
    ("cours du pétrole", "prix du pétrole", None),
    ("marchés internationaux", "marchés mondiaux", None),
    ("prix bord champ", "prix payé au producteur", "Prix minimum garanti payé aux planteurs pour leur récolte."),
    ("campagne principale", "principale période de récolte", None),
    ("inclusion financière", "accès de tous aux services bancaires", None),
    ("rentabilité", "capacité à rapporter de l'argent", None),
    ("levée de fonds", "collecte d'argent auprès d'investisseurs", None),
    ("séance plénière", "réunion de tous les députés", None),
    ("exercice précédent", "année précédente", None),
    ("diluviennes", "très fortes", None),
    ("protection civile", "service des secours", None),
    ("deuil national", "période officielle de tristesse nationale", None),
    ("combinaisons thérapeutiques à base d'artémisinine", "médicaments recommandés contre le paludisme", "Traitement de référence de l'OMS contre le paludisme."),
    ("artémisinine", "médicament contre le paludisme", None),
    ("épidémie", "maladie qui se propage rapidement", None),
    ("cybercriminalité", "délits commis sur Internet", None),
    ("haut débit", "connexion rapide", None),
    ("déploiement", "installation", None),
    ("consortium", "groupement d'entreprises", None),
    ("déplacées", "obligées de quitter leur maison", None),
    ("nonobstant", "malgré", None),
    ("en dépit de", "malgré", None),
    ("préalablement", "avant", None),
    ("ultérieurement", "plus tard", None),
    ("a indiqué", "a dit", None),
    ("a démenti", "a dit que c'était faux", None),
    ("dément", "dit que c'est faux", None),
    ("subséquemment", "ensuite", None),
    ("à l'issue de", "après", None),
    ("à compter du", "à partir du", None),
    ("dénoncent", "critiquent", None),
    ("préserver", "protéger", None),
    ("mesures d'accompagnement", "aides", None),
    ("chef-lieu de département", "ville principale du département", None),
]

USERS = [
    ("admin", "admin@prisme.local", "Administrateur Prisme", "admin123", "admin", None, {}),
    ("aminata", "aminata@demo.ci", "Aminata Coulibaly", "demo123", "user", "Journaliste / Veilleuse d'actualité", {"theme": "light"}),
    ("kevin", "kevin@demo.ci", "Kevin Konan", "demo123", "user", "Étudiant — podcasts & vidéos", {"theme": "dark"}),
    ("kouassi", "kouassi@demo.ci", "Mme Kouassi", "demo123", "user", "Cadre de direction (décideuse)", {"theme": "light"}),
    ("yao", "yao@demo.ci", "Yao Francklin", "demo123", "user", "Créateur de contenu / Community Manager", {}),
    ("paul", "paul@demo.ci", "Paul Ahoussou", "demo123", "user", "Senior retraité / lecteur occasionnel", {"font_scale": 1.3, "simple_mode": 1, "theme": "light"}),
    ("sara", "sara@demo.ci", "Sara Bamba", "demo123", "user", "Chercheuse / Archiviste web", {}),
]
INTERESTS = {
    "aminata": {"politique": 1, "international": 1, "economie": 0.8}, "kevin": {"tech": 1, "sport": 0.8, "culture": 0.7},
    "kouassi": {"economie": 1, "politique": 0.9}, "yao": {"culture": 1, "tech": 0.8, "societe": 0.7},
    "paul": {"sante": 1, "societe": 0.8}, "sara": {"international": 1, "environnement": 0.8, "culture": 0.6},
}
ALERTS = {"aminata": ["carburant", "Union africaine"], "kouassi": ["budget", "cacao"], "yao": ["TikTok", "festival"],
          "kevin": ["intelligence artificielle"], "sara": ["inondations"], "paul": ["paludisme"]}
FOLDERS = {"aminata": [("Veille économie", "#0ea5e9", ["A1", "B3", "G1"]), ("Dossier Sahel", "#f59e0b", ["S4"])],
           "sara": [("Archives climat", "#10b981", ["C4", "S5", "EN1"])], "kouassi": [("À partager à l'équipe", "#6366f1", ["S1", "G2"])],
           "paul": [("Mes lectures", "#ef4444", ["E2", "S6"])], "kevin": [("À écouter", "#8b5cf6", ["P1", "P2"])],
           "yao": [("Idées de posts", "#f97316", ["S11", "C3", "D1"])]}
HISTORY = {"aminata": ["A1", "S1", "S4", "B3", "G1", "EN2"], "kevin": ["F1", "D1", "P1", "S7"], "kouassi": ["S1", "G1", "A2"],
           "yao": ["S11", "S2", "C3", "F1"], "paul": ["E2", "S6"], "sara": ["C4", "S5", "EN1", "S4", "S10"]}
REPORTS = [
    ("kevin", "A4", "factuelle", "Le taux de 15 % ne correspond à aucune annonce officielle : les autres médias parlent de 5 %.", None, "en_attente", None),
    ("sara", "C4", "date", "Cet article sur les 18 morts date de 2024 mais il est repartagé comme s'il s'agissait des pluies de cette semaine.", None, "en_cours", None),
    ("paul", "E1", "factuelle", "Le ministère de la Santé a démenti cette information sur la plante miracle.", None, "corrige",
     "Signalement validé : un bandeau de correction renvoie vers le démenti officiel."),
    ("yao", "D2", "doublon", "Même information que l'article d'Abidjan Matin.", None, "rejete",
     "Les doublons sont déjà regroupés automatiquement par Prisme : pas d'action nécessaire."),
]
CORRECTIONS = {"E1": "Information démentie par le ministère de la Santé : aucune plante ne guérit le paludisme en 24 heures. Consultez l'article d'Abidjan Matin du même jour."}


PBKDF2_ROUNDS = 600_000


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", str(password).encode(), salt.encode(), PBKDF2_ROUNDS).hex()
    return f"{PBKDF2_ROUNDS}${h}", salt


def check_password(password, stored, salt):
    """Vérifie un mot de passe (les anciennes empreintes à 120 000 itérations restent acceptées)."""
    rounds, _, digest = stored.rpartition("$")
    h = hashlib.pbkdf2_hmac("sha256", str(password).encode(), salt.encode(), int(rounds or 120_000)).hex()
    return hmac.compare_digest(h, digest)


def make_demo_audio(path, seconds=24):
    """Génère un court habillage sonore (accords doux) pour le podcast de démonstration."""
    if os.path.exists(path):
        return
    rate = 8000
    chords = [(261.6, 329.6, 392.0), (220.0, 261.6, 329.6), (174.6, 220.0, 261.6), (196.0, 246.9, 293.7)]
    with wave.open(path, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        frames = bytearray()
        per = seconds * rate // len(chords)
        for ch in chords * 1:
            for i in range(per):
                t = i / rate
                env = min(1, i / 800) * min(1, (per - i) / 1600)
                v = sum(math.sin(2 * math.pi * f * t) for f in ch) / 3 * env * 0.25
                frames += struct.pack("<h", int(v * 32767))
        w.writeframes(bytes(frames))


@db.write
def seed_public(conn, admin_user=None, admin_password=None):
    """Base de production : référentiels et médias réels uniquement, aucun contenu ni compte fictif."""
    cat = {}
    for slug, name, color in CATEGORIES:
        cat[slug] = conn.execute("INSERT INTO categories(slug, name, color) VALUES (?,?,?)", (slug, name, color)).lastrowid
    for name, site, feed, country, lang, kind, dcat, _rel, _cert in REAL_SOURCES:
        conn.execute("""INSERT INTO sources(name, website, feed_url, country, language, kind, default_category, reliability, certified)
                        VALUES (?,?,?,?,?,?,?,70,0)""", (name, site, feed, country, lang, kind, cat.get(dcat)))
    for term, simple, definition in GLOSSARY:
        conn.execute("INSERT INTO glossary(term, simple, definition) VALUES (?,?,?)", (term, simple, definition))
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('neutral_sources', '1')")
    db.fill_publishers(conn)
    conn.commit()
    ensure_admin(conn, admin_user, admin_password)


@db.write
def ensure_admin(conn, username, password):
    """Crée ou met à jour le compte administrateur défini par les variables d'environnement."""
    if not username or not password:
        return
    h, salt = hash_password(password)
    u = db.row(conn, "SELECT id FROM users WHERE username=?", (username,))
    if u:
        conn.execute("UPDATE users SET password_hash=?, salt=?, role='admin' WHERE id=?", (h, salt, u["id"]))
    else:
        conn.execute("INSERT INTO users(username, email, display_name, password_hash, salt, role) VALUES (?,?,?,?,?,'admin')",
                     (username, f"{username}@prisme.invalid", "Administration Prisme", h, salt))
    conn.commit()


@db.write
def seed(conn):
    cat = {}
    for slug, name, color in CATEGORIES:
        cat[slug] = conn.execute("INSERT INTO categories(slug, name, color) VALUES (?,?,?)", (slug, name, color)).lastrowid
    for name, site, feed, country, lang, kind, dcat, rel, cert in REAL_SOURCES:
        conn.execute("""INSERT INTO sources(name, website, feed_url, country, language, kind, default_category, reliability, certified, reliability_note)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""", (name, site, feed, country, lang, kind, cat.get(dcat), rel, cert, NOTE))
    src = {}
    for key, (name, kind, lang, dcat, rel, cert) in DEMO_SOURCES.items():
        src[key] = conn.execute("""INSERT INTO sources(name, website, country, language, kind, default_category, reliability, certified, reliability_note, is_demo)
                                   VALUES (?,?,?,?,?,?,?,?,?,1)""", (name, None, "Côte d'Ivoire", lang, kind, cat[dcat], rel, cert, DEMO_NOTE)).lastrowid
    for term, simple, definition in GLOSSARY:
        conn.execute("INSERT INTO glossary(term, simple, definition) VALUES (?,?,?)", (term, simple, definition))

    now = db.now()
    art = {}
    for entry in ARTICLES:
        key, s, c, age, title, text = entry[:6]
        media = entry[6] if len(entry) > 6 and entry[6] else "article"
        author = entry[7] if len(entry) > 7 else None
        seen_age = entry[8] if len(entry) > 8 else min(age, 1)
        pub = now - timedelta(hours=age)
        seen = now - timedelta(hours=seen_age)
        lang = DEMO_SOURCES[s][2]
        sents = nlp.sentences(text)
        summary = " ".join(sents[:2]) if len(sents) > 2 else text
        media_url = "/media/demo_podcast.wav" if media == "podcast" else None
        art[key] = conn.execute(
            """INSERT INTO articles(source_id, guid, title, summary, content, url, author, media_type, media_url, duration_sec,
                   language, category_id, published_at, first_seen_at, word_count, views, shares, is_demo, correction_note)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)""",
            (src[s], f"demo-{key}", title, summary, text, None, author, media, media_url, 24 if media_url else None, lang, cat[c],
             db.to_str(pub), db.to_str(seen), len(text.split()), secrets.randbelow(900) + 40, secrets.randbelow(120),
             CORRECTIONS.get(key))).lastrowid
    for key, (t, body) in TRANSLATIONS.items():
        conn.execute("INSERT INTO translations(article_id, lang, title, body, engine) VALUES (?,?,?,?,?)", (art[key], "fr", t, body, "Traduction de démonstration (pré-calculée)"))

    uid = {}
    for username, email, name, pwd, role, persona, prefs in USERS:
        h, salt = hash_password(pwd)
        uid[username] = conn.execute("""INSERT INTO users(username, email, display_name, password_hash, salt, role, persona, font_scale, simple_mode, theme)
                                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                                     (username, email, name, h, salt, role, persona, prefs.get("font_scale", 1.0),
                                      prefs.get("simple_mode", 0), prefs.get("theme", "auto"))).lastrowid
    for u, ints in INTERESTS.items():
        for slug, w in ints.items():
            conn.execute("INSERT INTO interests VALUES (?,?,?)", (uid[u], cat[slug], w))
    for u, kws in ALERTS.items():
        for k in kws:
            conn.execute("INSERT INTO alerts(user_id, keyword) VALUES (?,?)", (uid[u], k))
    for u, folders in FOLDERS.items():
        for name, color, keys in folders:
            fid = conn.execute("INSERT INTO folders(user_id, name, color) VALUES (?,?,?)", (uid[u], name, color)).lastrowid
            for k in keys:
                conn.execute("INSERT OR IGNORE INTO favorites(user_id, article_id, folder_id) VALUES (?,?,?)", (uid[u], art[k], fid))
    for u, keys in HISTORY.items():
        for i, k in enumerate(keys):
            conn.execute("INSERT INTO reading_history(user_id, article_id, read_at) VALUES (?,?,?)", (uid[u], art[k], db.ago(hours=i * 5 + 1)))
    for u, k, reason, desc, url, status, resp in REPORTS:
        conn.execute("""INSERT INTO reports(user_id, article_id, reason, description, evidence_url, status, admin_response, resolved_at)
                        VALUES (?,?,?,?,?,?,?,?)""", (uid[u], art[k], reason, desc, url, status, resp, db.now_str() if status in ("corrige", "rejete") else None))
    conn.execute("INSERT INTO notifications(user_id, kind, message) SELECT id, 'systeme', 'Bienvenue sur Prisme ! Configurez vos centres d''intérêt et vos alertes dans Paramètres.' FROM users")
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('demo_anchor', ?)", (db.now_str(),))
    db.fill_publishers(conn)
    conn.commit()
    make_demo_audio(os.path.join(ROOT, "web", "media", "demo_podcast.wav"))


@db.write
def refresh_demo_dates(conn):
    """Décale les dates des contenus de démonstration pour qu'ils restent « d'actualité » à chaque lancement."""
    anchor = db.parse(db.scalar(conn, "SELECT value FROM meta WHERE key='demo_anchor'"))
    if not anchor:
        return 0
    delta = db.now() - anchor
    secs = int(delta.total_seconds())
    if secs < 3600:
        return 0
    mod = f"+{secs} seconds"
    conn.execute("UPDATE articles SET published_at=datetime(published_at, ?), first_seen_at=datetime(first_seen_at, ?) WHERE is_demo=1", (mod, mod))
    conn.execute("UPDATE reading_history SET read_at=datetime(read_at, ?)", (mod,))
    conn.execute("UPDATE clusters SET first_published=datetime(first_published, ?), last_published=datetime(last_published, ?) WHERE lead_article_id IN (SELECT id FROM articles WHERE is_demo=1)", (mod, mod))
    conn.execute("UPDATE meta SET value=? WHERE key='demo_anchor'", (db.now_str(),))
    conn.commit()
    return secs
