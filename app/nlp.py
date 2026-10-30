"""Moteur de traitement automatique du langage (TAL) de Prisme.

Algorithmes statistiques explicables, sans dépendance externe :
  - normalisation, tokenisation, racinisation légère (FR/EN) ;
  - vectorisation TF pondérée et similarité cosinus (détection des doublons) ;
  - découpage en phrases, détection d'affirmations vérifiables ;
  - lisibilité (formule de Kandel & Moles), simplification par glossaire ;
  - analyse de tonalité par lexique, indicateur de fraîcheur.
"""
import html
import math
import re
import unicodedata
from collections import Counter

STOPWORDS = set("""
a à au aux avec ce ces cet cette dans de des du elle elles en et eux il ils je la le les leur leurs lui ma mais me même mes moi mon ne nos notre nous on ou où par pas pour qu que qui sa se ses son sur ta te tes toi ton tu un une vos votre vous c d j l m n s t y été être avoir a ai as avons avez ont avait était sont est sera seront fait faire plus moins très tout tous toute toutes aussi comme donc alors ainsi après avant depuis entre sans sous selon vers chez lors dont cela ceci celui celle ceux deux trois autre autres bien encore déjà peu jour jours année ans an hier aujourd hui demain contre près cours fin si non oui ni car quand comment pourquoi lequel laquelle afin ici là leurs quel quelle quels quelles sest cest qu il elle doit peut peuvent pourrait selon via plus
the of and to in a is that for on with as was are be by at it from this an has have had not but or were which their its they he she his her been will would can could also more after over new said says into than about who up out one two all first last year years we our us
""".split())

# Marqueurs d'affirmations à vérifier (classes de la vérification assistée)
CLAIM_PATTERNS = {
    "chiffre": re.compile(r"\d[\d\s.,]*\s?(%|pour ?cent|fcfa|f cfa|euros?|dollars?|\$|€|milliards?|millions?|tonnes?|km|morts?|décès|victimes|personnes|habitants|emplois|mw|hectares)", re.I),
    "citation": re.compile(r"[«“\"][^»”\"]{12,}[»”\"]"),
    "attribution": re.compile(r"\b(selon|d'après|a déclaré|a affirmé|affirme|a annoncé|annonce|indique|a indiqué|estime|according to|said|told|announced|claims?)\b", re.I),
    "causalite": re.compile(r"\b(à cause de|en raison de|provoqu|entraîn|causé|grâce à|conséquence|due to|caused|because of|led to)\w*", re.I),
    "absolu": re.compile(r"\b(jamais|toujours|aucun|tous les|record|historique|sans précédent|le plus|la plus|premier pays|never|always|record|unprecedented|first ever)\b", re.I),
    "rumeur": re.compile(r"\b(aurait|auraient|serait|seraient|rumeur|on raconte|il paraît|partagez|miracle|choc|incroyable|secret|ils ne veulent pas|reportedly|allegedly|rumou?r)\b", re.I),
}
SENSATIONAL = re.compile(r"(!{2,}|\b(urgent|choc|incroyable|scandale|miracle|partagez avant|exclusif|révélation|hallucinant|breaking)\b)", re.I)

POSITIVE = set("succès réussite progrès croissance victoire qualifié qualifiés record accord salué positive amélioration innovation lancement inauguré soutien opportunité stabilité rebond bénéfice gagne gagné growth success win wins victory improve agreement boost".split())
NEGATIVE = set("crise baisse chute mort morts décès victimes inondations catastrophe pénurie colère grève conflit attaque accident inquiétude flambée menace drame échec perte pertes tension violences scandale crisis death killed flood drop fall attack conflict loss fear".split())

CATEGORY_KEYWORDS = {
    "politique": "gouvernement ministre président élection élections assemblée parti politique député sénat présidentielle opposition réforme vote décret conseil premier government election minister president parliament",
    "economie": "économie économique prix inflation carburant banque fcfa croissance pib entreprise marché investissement budget dette exportation cacao commerce emploi bourse economy market prices bank trade investment",
    "societe": "société population école éducation transport logement santé publique jeunesse femmes habitants quartier social justice police tribunal grève citoyens",
    "sport": "football match équipe coupe can championnat joueur sélection éléphants ligue but victoire sport olympique athlétisme basket tennis",
    "sante": "santé hôpital médecin maladie paludisme vaccin épidémie patients soins médicament covid choléra oms health hospital disease vaccine",
    "tech": "numérique technologie internet intelligence artificielle ia startup application smartphone fibre données cybersécurité logiciel innovation tech digital apple google microsoft robot ordinateur",
    "culture": "culture musique film cinéma festival artiste livre exposition art concert théâtre littérature histoire patrimoine",
    "environnement": "climat environnement inondations pluie pluies sécheresse forêt pollution énergie solaire renouvelable biodiversité météo déchets climate environment flood energy solar",
    "international": "international monde onu union africaine diplomatie guerre conflit frontière sommet étranger etats-unis europe chine russie ukraine israël gaza soudan sahel world war summit",
}

def strip_html(text):
    if not text:
        return ""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</p>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def deaccent(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def stem(w):
    for suf in ("ements", "ement", "ations", "ation", "ités", "ité", "euses", "euse", "eux", "aux", "ies", "es", "s", "e"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def tokens(text, keep_stop=False):
    text = deaccent((text or "").lower())
    words = re.findall(r"[a-z0-9]+", text)
    stop = {deaccent(s) for s in STOPWORDS}
    return [stem(w) for w in words if (keep_stop or (w not in stop and len(w) > 2))]


def vector(title, body=""):
    v = Counter()
    for t in tokens(title):
        v[t] += 2.0          # le titre porte davantage le sens de l'actualité
    for t in tokens(body)[:120]:
        v[t] += 1.0
    return v


def cosine(a, b):
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    num = sum(a[k] * b[k] for k in common)
    den = math.sqrt(sum(x * x for x in a.values())) * math.sqrt(sum(x * x for x in b.values()))
    return num / den if den else 0.0


def sentences(text):
    text = strip_html(text)
    parts = re.split(r"(?<=[.!?…])\s+(?=[A-ZÀ-Ý«\"“0-9])|\n+", text)
    return [p.strip() for p in parts if len(p.strip()) > 25]


GENERIC = set("""nouveau nouvelle nouveaux nouvelles grand grande grands grandes national nationale nationaux pays
monde premier première dernier dernière mardi mercredi jeudi vendredi samedi dimanche lundi semaine heures heure mois
selon après avant ainsi cette leurs entre faire plusieurs depuis toujours encore comment pourquoi votre notre avoir
direct vidéo video replay article lire suivre quoi voici what with from your about more news live""".split())


def keywords(text, n=8):
    words = re.findall(r"[A-Za-zÀ-ÿ0-9’'-]+", text or "")
    out = []
    for w in words:
        w = re.sub(r"^(?:[ldjmnstc]|qu|jusqu|lorsqu|puisqu)['’]", "", w.lower()).strip("'’-")
        if len(w) > 3 and not w.isdigit() and w not in STOPWORDS and w not in GENERIC:
            out.append(w)
    c = Counter(out)
    return [w for w, _ in c.most_common(n)]


def numbers(sentence):
    out = []
    for m in re.finditer(r"(\d+(?:[\s.]\d{3})*(?:[.,]\d+)?)\s?(%|pour ?cent|milliards?|millions?|fcfa|euros?|dollars?|morts?|décès|victimes|mw)?", sentence, re.I):
        raw = m.group(1).replace(" ", "").replace(",", ".")
        if raw.count(".") > 1:
            raw = raw.replace(".", "")
        try:
            val = float(raw)
        except ValueError:
            continue
        unit = (m.group(2) or "").lower().replace("pour cent", "%").replace("pourcent", "%")
        if 1900 <= val <= 2100 and not unit:
            continue                       # une année n'est pas une donnée chiffrée
        out.append((val, unit.rstrip("s")))
    return out


def claim_types(sentence):
    return [k for k, rx in CLAIM_PATTERNS.items() if rx.search(sentence)]


def tone(text):
    t = [w.strip(".,;:!?«»\"'()").lower() for w in (text or "").split()]
    pos = sum(1 for w in t if w in POSITIVE)
    neg = sum(1 for w in t if w in NEGATIVE)
    sens = len(SENSATIONAL.findall(text or ""))
    total = max(pos + neg, 1)
    polarity = (pos - neg) / total
    if sens >= 2:
        label = "sensationnaliste"
    elif polarity > 0.3:
        label = "positif"
    elif polarity < -0.3:
        label = "alarmiste" if neg >= 3 else "négatif"
    else:
        label = "neutre / factuel"
    return {"label": label, "polarity": round(polarity, 2), "sensational": sens, "pos": pos, "neg": neg}


def syllables(word):
    word = deaccent(word.lower())
    groups = re.findall(r"[aeiouy]+", word)
    n = len(groups)
    if word.endswith("e") and n > 1:
        n -= 1
    return max(n, 1)


def readability(text):
    """Indice de lisibilité de Kandel & Moles (adaptation française de Flesch)."""
    sents = sentences(text) or [text]
    words = re.findall(r"[A-Za-zÀ-ÿ]+", text or "")
    if not words:
        return {"score": 0, "level": "—", "words_per_sentence": 0}
    wps = len(words) / max(len(sents), 1)
    spw = sum(syllables(w) for w in words) / len(words)
    score = 207 - 1.015 * wps - 73.6 * spw
    score = max(0, min(100, round(score)))
    if score >= 70:
        level = "Très facile"
    elif score >= 60:
        level = "Facile"
    elif score >= 50:
        level = "Standard"
    elif score >= 30:
        level = "Difficile"
    else:
        level = "Très difficile"
    return {"score": score, "level": level, "words_per_sentence": round(wps, 1)}


SPLITTERS = re.compile(r",\s+(?=(?:qui|dont|alors que|tandis que|mais|car|puisque|lorsque|ce qui)\b)|;\s+|\s+—\s+")


def simplify(text, glossary):
    """Simplification lexicale (glossaire) et syntaxique (phrases plus courtes)."""
    used = []
    out_sents = []
    for s in sentences(text):
        parts = SPLITTERS.split(s)
        for p in parts:
            p = p.strip(" ,;")
            if not p:
                continue
            p = re.sub(r"^(qui|dont|mais|car|puisque|lorsque|alors que|tandis que|ce qui)\s+", lambda m: {"qui": "Cela ", "dont": "Cela ", "ce qui": "Cela "}.get(m.group(1).lower(), m.group(1).capitalize() + " "), p, flags=re.I)
            p = p[0].upper() + p[1:]
            if not p.endswith((".", "!", "?", "…")):
                p += "."
            out_sents.append(p)
    result = " ".join(out_sents)
    for term, simple, definition in sorted(glossary, key=lambda g: -len(g[0])):
        rx = re.compile(r"\b" + re.escape(term) + r"\b", re.I)
        if rx.search(result):
            used.append({"term": term, "simple": simple, "definition": definition})
            result = rx.sub(simple, result)
    # Élision devenue incorrecte après remplacement : « d'niveau » → « de niveau »
    elision = re.compile(r"(?<![A-Za-zÀ-ÿ])([dDlL])['’](?=[bcdfgjklmnpqrstvwxzBCDFGJKLMNPQRSTVWXZ])")
    result = elision.sub(lambda m: {"d": "de ", "D": "De ", "l": "le ", "L": "Le "}[m.group(1)], result)
    return result, used


def classify(text, slugs_to_ids, default=None):
    toks = set(tokens(text))
    best, best_score = default, 0
    for slug, kw in CATEGORY_KEYWORDS.items():
        kws = {stem(deaccent(k)) for k in kw.split()}
        score = len(toks & kws)
        if score > best_score and slug in slugs_to_ids:
            best, best_score = slugs_to_ids[slug], score
    return best


def human_delta(hours):
    if hours < 1:
        return f"il y a {max(1, int(hours * 60))} min"
    if hours < 24:
        return f"il y a {int(hours)} h"
    days = hours / 24
    if days < 30:
        return f"il y a {int(days)} jour{'s' if int(days) > 1 else ''}"
    if days < 365:
        return f"il y a {int(days // 30)} mois"
    years = int(days // 365)
    return f"il y a {years} an{'s' if years > 1 else ''}"


def freshness(published, first_seen, now, cluster_latest=None):
    """Indicateur de fraîcheur : récence + détection d'une information ancienne qui recircule."""
    if not published:
        return {"level": "inconnue", "label": "Date non communiquée", "score": 30, "age": "date inconnue",
                "recirculating": False, "warning": "Le média n'indique pas de date de publication : prudence."}
    hours = max((now - published).total_seconds() / 3600, 0)
    score = round(100 * math.exp(-hours / 36))
    if hours < 6:
        level, label = "brulant", "À chaud"
    elif hours < 48:
        level, label = "recent", "Récent"
    elif hours < 24 * 7:
        level, label = "semaine", "Cette semaine"
    elif hours < 24 * 90:
        level, label = "ancien", "Ancien"
    else:
        level, label = "archive", "Archive"
    recirculating = False
    warning = None
    seen_gap = (first_seen - published).total_seconds() / 86400 if first_seen else 0
    if hours > 24 * 30 and (seen_gap > 30 or (cluster_latest and (cluster_latest - published).days > 30)):
        recirculating = True
        warning = (f"Information ancienne qui circule à nouveau : publiée {human_delta(hours)} "
                   f"({published.strftime('%d/%m/%Y')}), mais réapparue récemment dans les flux.")
    elif hours > 24 * 90:
        warning = f"Article d'archive publié le {published.strftime('%d/%m/%Y')}. Le contexte a pu évoluer."
    return {"level": level, "label": label, "score": score, "age": human_delta(hours),
            "recirculating": recirculating, "warning": warning}
