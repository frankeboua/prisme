"""Moteur métier de Prisme : doublons, vérification, résumé, comparaison, recommandation."""
import math
import re
from collections import Counter, defaultdict

from . import db, nlp

PUB = "COALESCE(s.publisher, s.name)"   # plusieurs flux d'un même éditeur comptent pour un seul média

# Les statuts décrivent la couverture observée : Prisme ne certifie pas la véracité d'un fait.
STATUS_LABEL = {
    "verifie": "Repris par 3 sources ou plus", "partiel": "Repris par 2 sources", "non_verifie": "Source unique",
    "conteste": "Désaccord entre sources", "en_attente": "En attente d'analyse",
}
REASON_LABEL = {"chiffres": "Chiffres divergents", "dementi": "Démenti signalé"}
CLAIM_LABEL = {"verifie": "Passage proche dans 2 sources ou plus", "partiel": "Passage proche dans 1 source",
               "non_verifie": "Aucun passage proche", "conteste": "Version différente"}
DEBUNK = ("démenti", "dément", "infondé", "infondée", "aucune preuve", "intox", "fake news",
          "n'a jamais", "no evidence", "debunk", "erroné", "erronée", "fausse information")


def status_label(status, source_count=None, reason=None):
    if status == "conteste":
        return REASON_LABEL.get(reason, STATUS_LABEL["conteste"])
    if status == "verifie" and source_count and source_count >= 3:
        return f"Repris par {source_count} sources"
    return STATUS_LABEL.get(status, "")


def article_text(a):
    return nlp.strip_html(" ".join(x for x in (a.get("summary"), a.get("content")) if x))


# =====================================================================
#  1. DÉTECTION DES DOUBLONS (clustering par similarité cosinus)
# =====================================================================
DUP_THRESHOLD = 0.42
MERGE_MEAN = 0.30
EVENT_DAYS = 4


@db.write
def recluster(conn, limit=2000):
    arts = db.rows(conn, """SELECT a.id, a.title, a.summary, a.language, a.published_at, a.source_id, a.cluster_id, a.is_demo,
                                   COALESCE(s.publisher, s.name) publisher, s.reliability FROM articles a JOIN sources s ON s.id=a.source_id
                            ORDER BY a.first_seen_at DESC LIMIT ?""", (limit,))
    n = len(arts)
    vecs = [nlp.vector(a["title"], nlp.strip_html(a["summary"] or "")) for a in arts]
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    # Index inversé sur les termes du titre : on ne compare que les paires candidates
    index = defaultdict(list)
    for i, a in enumerate(arts):
        for t in set(nlp.tokens(a["title"])):
            index[t].append(i)
    pair_hits = Counter()
    for lst in index.values():
        if len(lst) > 150:
            continue
        for x in range(len(lst)):
            for y in range(x + 1, len(lst)):
                pair_hits[(lst[x], lst[y])] += 1
    dates = [db.parse(a["published_at"]) for a in arts]
    pairs = []
    for (i, j), hits in pair_hits.items():
        if hits < 2 or arts[i]["language"] != arts[j]["language"]:
            continue
        # Un événement se couvre en quelques jours (les scénarios de démonstration gardent leur écart).
        if not (arts[i]["is_demo"] and arts[j]["is_demo"]) and dates[i] and dates[j] and abs((dates[i] - dates[j]).days) > EVENT_DAYS:
            continue
        # Un même média ne publie pas deux fois la même actualité : on n'exige alors
        # une quasi-copie (évite de regrouper les épisodes d'une même série).
        threshold = DUP_THRESHOLD if arts[i]["publisher"] != arts[j]["publisher"] else 0.8
        sim = nlp.cosine(vecs[i], vecs[j])
        if sim >= threshold:
            pairs.append((sim, i, j))

    # Regroupement par lien moyen : les meilleures paires d'abord, et une fusion n'est acceptée
    # que si les deux groupes se ressemblent dans leur ensemble (évite l'enchaînement de sujets voisins).
    members_of = {i: [i] for i in range(n)}
    for sim, i, j in sorted(pairs, reverse=True):
        a, b = find(i), find(j)
        if a == b:
            continue
        cross = [nlp.cosine(vecs[x], vecs[y]) for x in members_of[a] for y in members_of[b]]
        if sum(cross) / len(cross) >= MERGE_MEAN:
            parent[a] = b
            members_of[b] += members_of.pop(a)

    groups = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(arts[i])

    # Les identifiants de sujets restent stables d'une collecte à l'autre : les liens partagés ne cassent pas.
    taken, assigned = set(), {}
    for root, members in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        for cid, _ in Counter(a["cluster_id"] for a in members if a["cluster_id"]).most_common():
            if cid not in taken:
                taken.add(cid)
                assigned[root] = cid
                break
    for root, members in groups.items():
        dates_m = sorted(a["published_at"] for a in members if a["published_at"])
        # L'article principal est le plus fiable parmi les publications récentes du sujet
        # (une information ancienne qui recircule ne doit jamais représenter le sujet).
        latest = db.parse(dates_m[-1]) if dates_m else None
        recent = [a for a in members if latest and a["published_at"] and (latest - db.parse(a["published_at"])).days <= 7] or members
        lead = max(recent, key=lambda a: (a["reliability"], a["published_at"] or ""))
        values = (lead["title"], lead["id"], len(members), len({a["publisher"] for a in members}),
                  dates_m[0] if dates_m else None, dates_m[-1] if dates_m else None)
        cid = assigned.get(root)
        if cid:
            conn.execute("UPDATE clusters SET label=?, lead_article_id=?, size=?, source_count=?, first_published=?, last_published=?, updated_at=datetime('now') WHERE id=?", (*values, cid))
        else:
            cid = conn.execute("INSERT INTO clusters(label, lead_article_id, size, source_count, first_published, last_published) VALUES (?,?,?,?,?,?)", values).lastrowid
            taken.add(cid)
        conn.executemany("UPDATE articles SET cluster_id=?, is_cluster_lead=0 WHERE id=?", [(cid, m["id"]) for m in members])
        conn.execute("UPDATE articles SET is_cluster_lead=1 WHERE id=?", (lead["id"],))
    if taken:
        conn.execute(f"DELETE FROM clusters WHERE id NOT IN ({','.join(str(c) for c in taken)})")
    conn.commit()
    return {"articles": n, "clusters": len(groups), "duplicates": n - len(groups)}


# =====================================================================
#  2. VÉRIFICATION ASSISTÉE PAR IA (affirmations + recherche de preuves)
# =====================================================================
_VEC, _SENT = {}, {}


def _vec(a):
    if a["id"] not in _VEC:
        _VEC[a["id"]] = nlp.vector(a["title"], nlp.strip_html(a["summary"] or ""))
    return _VEC[a["id"]]


def _sents(a):
    """Phrases d'un article et leurs vecteurs (mis en cache : les textes ne changent pas)."""
    if a["id"] not in _SENT:
        _SENT[a["id"]] = [(s, nlp.vector(s)) for s in nlp.sentences(a["title"] + ". " + article_text(a))]
    return _SENT[a["id"]]


def _evidence_corpus(conn, art, max_articles=25):
    """Articles d'autres sources susceptibles de confirmer ou d'infirmer l'article."""
    same = db.rows(conn, """SELECT a.*, s.name source_name, COALESCE(s.publisher, s.name) publisher, s.reliability FROM articles a JOIN sources s ON s.id=a.source_id
                            WHERE a.cluster_id=? AND a.id<>? AND COALESCE(s.publisher, s.name)<>?""",
                   (art["cluster_id"], art["id"], art["publisher"])) if art.get("cluster_id") else []
    v = nlp.vector(art["title"], article_text(art))
    pool = db.rows(conn, """SELECT a.*, s.name source_name, COALESCE(s.publisher, s.name) publisher, s.reliability FROM articles a JOIN sources s ON s.id=a.source_id
                            WHERE a.id<>? AND COALESCE(s.publisher, s.name)<>? AND a.language=? ORDER BY a.first_seen_at DESC LIMIT 600""",
                   (art["id"], art["publisher"], art["language"]))
    scored = sorted(((nlp.cosine(v, _vec(p)), p) for p in pool),
                    key=lambda x: -x[0])
    seen = {a["id"] for a in same}
    extra = [p for s, p in scored if s > 0.18 and p["id"] not in seen][: max_articles - len(same)]
    return same + extra


def _stance(claim, cand, sim, cand_reliability):
    claim_debunk = any(d in claim.lower() for d in DEBUNK)
    cand_debunk = any(d in cand.lower() for d in DEBUNK)
    if cand_debunk and claim_debunk:
        return "soutient"                      # deux démentis convergents
    if cand_debunk and sim >= 0.35:
        return "contredit"
    if claim_debunk:
        # la phrase candidate relaie la rumeur démentie : elle ne confirme pas le démenti
        return "neutre" if cand_reliability < 55 else ("soutient" if sim >= 0.38 else "neutre")
    cn = nlp.firm_numbers(claim)
    if cn:
        firm, stated = nlp.firm_numbers(cand), nlp.numbers(cand)
        for val, unit in cn:
            if any(u == unit and abs(v - val) <= max(abs(val) * 0.02, 0.01) for v, u in stated):
                return "soutient"
            # Seuls deux chiffres arrêtés se contredisent : « au moins 60 morts » n'infirme pas « 68 morts ».
            if any(u == unit for _, u in firm) and sim >= 0.30:
                return "contredit"
        return "neutre" if sim < 0.6 else "soutient"   # chiffre non repris : pas de confirmation
    return "soutient" if sim >= 0.38 else "neutre"


def _coverage_status(others):
    """Statut déduit du nombre d'autres médias couvrant le même événement."""
    return "verifie" if others >= 2 else "partiel" if others == 1 else "non_verifie"


def _dispute_reason(conn, article_id):
    texts = db.rows(conn, """SELECT e.excerpt FROM evidences e JOIN claims c ON c.id=e.claim_id
                             WHERE c.article_id=? AND c.status='conteste' AND e.stance='contredit'""", (article_id,))
    return "dementi" if any(any(d in t["excerpt"].lower() for d in DEBUNK) for t in texts) else "chiffres"


@db.write
def refresh_statuses(conn):
    """La couverture évolue à chaque collecte : les statuts suivent, sauf en cas de désaccord signalé."""
    others = f"""(SELECT COUNT(DISTINCT {PUB}) FROM articles x JOIN sources s ON s.id=x.source_id
                  WHERE x.cluster_id=articles.cluster_id AND {PUB}<>(SELECT {PUB} FROM sources s WHERE s.id=articles.source_id))"""
    conn.execute(f"""UPDATE articles SET verification_status=CASE WHEN {others} >= 2 THEN 'verifie' WHEN {others} = 1 THEN 'partiel' ELSE 'non_verifie' END
                     WHERE verification_status NOT IN ('conteste','en_attente')""")
    conn.commit()


@db.write
def verify_article(conn, article_id):
    art = db.row(conn, "SELECT a.*, s.reliability, s.name source_name, COALESCE(s.publisher, s.name) publisher FROM articles a JOIN sources s ON s.id=a.source_id WHERE a.id=?", (article_id,))
    if not art:
        return None
    text = article_text(art)
    sents = nlp.sentences(art["title"] + ". " + text)
    candidates = [(i, s, nlp.claim_types(s)) for i, s in enumerate(sents)]
    claims = [c for c in candidates if c[2]][:8]
    corpus = []
    pub = db.parse(art["published_at"])
    for p in _evidence_corpus(conn, art):
        ppub = db.parse(p["published_at"])
        # Une preuve doit être contemporaine : un article publié des mois plus tard
        # ne peut pas confirmer un fait ancien (et inversement).
        if pub and ppub and abs((pub - ppub).days) > 30:
            continue
        for s, sv in _sents(p):
            corpus.append((p, s, sv))

    conn.execute("DELETE FROM claims WHERE article_id=?", (article_id,))
    claim_scores = []
    for pos, sentence, types in claims:
        cv = nlp.vector(sentence)
        hits = []
        for p, s, sv in corpus:
            sim = nlp.cosine(cv, sv)
            if sim >= 0.25:
                hits.append((sim, p, s))
        hits.sort(key=lambda h: -h[0])
        evid, used_sources = [], set()
        for sim, p, s in hits:
            if p["publisher"] in used_sources:
                continue
            used_sources.add(p["publisher"])
            evid.append((p, s, _stance(sentence, s, sim, p["reliability"]), sim))
            if len(evid) == 4:
                break
        support = [e for e in evid if e[2] == "soutient"]
        contra = [e for e in evid if e[2] == "contredit" and e[0]["reliability"] >= 55]
        if contra and (len(contra) >= len(support) or "rumeur" in types):
            status, conf = "conteste", 70 + 10 * min(len(contra), 2)
            why = f"{len(contra)} autre(s) source(s) rapportent une version différente ou un démenti."
        elif len(support) >= 2:
            status, conf = "verifie", min(95, 70 + 10 * len(support))
            why = f"Un passage proche figure chez {len(support)} autres médias. Cela indique une reprise, pas une preuve."
        elif len(support) == 1:
            status, conf = "partiel", 55
            why = f"Un passage proche figure chez un autre média ({support[0][0]['source_name']})."
        else:
            status, conf = "non_verifie", 35 if "rumeur" not in types else 20
            why = "Aucun passage proche chez les autres médias suivis par Prisme."
            if "rumeur" in types:
                why += " Formulation conditionnelle ou sensationnaliste détectée."
        cur = conn.execute("INSERT INTO claims(article_id, position, sentence, claim_types, status, confidence, rationale) VALUES (?,?,?,?,?,?,?)",
                           (article_id, pos, sentence, ",".join(types), status, conf, why))
        for p, s, stance, sim in evid:
            conn.execute("INSERT INTO evidences(claim_id, article_id, excerpt, stance, similarity) VALUES (?,?,?,?,?)",
                         (cur.lastrowid, p["id"], s[:400], stance, round(sim, 3)))
        claim_scores.append({"verifie": 100, "partiel": 65, "non_verifie": 30, "conteste": 0}[status])

    rel = art["reliability"]
    sens = nlp.tone(art["title"] + " " + text)["sensational"]
    corroborating = db.scalar(conn, "SELECT COUNT(DISTINCT COALESCE(s.publisher, s.name)) FROM articles a JOIN sources s ON s.id=a.source_id WHERE a.cluster_id=? AND COALESCE(s.publisher, s.name)<>?",
                              (art["cluster_id"], art["publisher"])) or 0
    if claim_scores:
        base = sum(claim_scores) / len(claim_scores)
    else:
        base = 60 + 15 * min(corroborating, 2)
    score = round(0.65 * base + 0.35 * rel - 8 * min(sens, 3) + 6 * min(corroborating, 2))
    latest = db.parse(db.scalar(conn, "SELECT MAX(published_at) FROM articles WHERE cluster_id=?", (art["cluster_id"],)))
    if pub and latest and (latest - pub).days > 30:
        score = min(score, 45)                 # information ancienne qui recircule : non confirmée pour l'actualité
    score = max(0, min(100, score))
    contested = claim_scores.count(0)
    status, reason = _coverage_status(corroborating), None
    if contested and (contested * 3 >= len(claim_scores) or rel < 50):
        status, reason = "conteste", _dispute_reason(conn, article_id)
    previous = art["verification_status"]
    conn.execute("UPDATE articles SET verification_status=?, verification_score=?, verified_at=?, status_reason=? WHERE id=?",
                 (status, score, db.now_str(), reason, article_id))
    if previous != status and previous != "en_attente":
        db.log_change(conn, "moteur", "article", article_id, "statut", f"{previous} -> {status}")
    conn.commit()
    return {"status": status, "score": score}


def verify_pending(conn, limit=400):
    ids = [r["id"] for r in db.rows(conn, "SELECT id FROM articles WHERE verification_status='en_attente' ORDER BY first_seen_at DESC LIMIT ?", (limit,))]
    for i in ids:
        verify_article(conn, i)
    _VEC.clear()
    _SENT.clear()    # caches libérés après chaque lot : la mémoire reste bornée en production
    return len(ids)


def get_verification(conn, article_id):
    claims = db.rows(conn, "SELECT * FROM claims WHERE article_id=? ORDER BY position", (article_id,))
    for c in claims:
        c["status_label"] = CLAIM_LABEL[c["status"]]
        c["evidences"] = db.rows(conn, """SELECT e.*, a.title, a.url, a.published_at, s.name source_name, s.reliability
                                          FROM evidences e JOIN articles a ON a.id=e.article_id JOIN sources s ON s.id=a.source_id
                                          WHERE e.claim_id=? ORDER BY e.similarity DESC""", (c["id"],))
    return claims


# =====================================================================
#  3. RÉSUMÉ IA AVEC CITATIONS VÉRIFIABLES (extractif multi-sources)
# =====================================================================
def summarize(conn, article_id, max_sentences=4):
    art = db.row(conn, "SELECT * FROM v_articles WHERE id=?", (article_id,))
    if not art:
        return None
    members = db.rows(conn, "SELECT * FROM v_articles WHERE cluster_id=? ORDER BY source_reliability DESC", (art["cluster_id"],)) if art["cluster_id"] else [art]
    if len(members) > 1:
        # Le résumé s'appuie sur les sources fiables et non contestées du sujet
        reliable = [m for m in members if m["source_reliability"] >= 50 and m["verification_status"] != "conteste"]
        members = reliable or members
    pool = []
    for m in members:
        for pos, s in enumerate(nlp.sentences(article_text(m))):
            pool.append({"article": m, "pos": pos, "text": s, "vec": nlp.vector(s)})
    if not pool:
        return {"sentences": [], "sources": [], "method": "—"}
    centroid = Counter()
    for p in pool:
        centroid.update(p["vec"])
    for p in pool:
        p["score"] = nlp.cosine(p["vec"], centroid) + 0.15 / (1 + p["pos"]) + p["article"]["source_reliability"] / 1000
        if nlp.SENSATIONAL.search(p["text"]):
            p["score"] -= 0.2
    chosen, used_src = [], Counter()
    for p in sorted(pool, key=lambda x: -x["score"]):
        if any(nlp.cosine(p["vec"], c["vec"]) > 0.45 for c in chosen):
            continue
        if used_src[p["article"]["source_id"]] >= 2 and len(members) > 1:
            continue
        chosen.append(p)
        used_src[p["article"]["source_id"]] += 1
        if len(chosen) == max_sentences:
            break
    chosen.sort(key=lambda c: (c["article"]["id"] != art["id"], c["pos"]))
    sources, ref = [], {}
    out = []
    for c in chosen:
        a = c["article"]
        if a["id"] not in ref:
            ref[a["id"]] = len(sources) + 1
            sources.append({"n": ref[a["id"]], "article_id": a["id"], "source": a["source_name"], "title": a["title"],
                            "url": a["url"], "published_at": a["published_at"], "reliability": a["source_reliability"]})
        out.append({"text": c["text"], "cite": ref[a["id"]]})
    return {"sentences": out, "sources": sources,
            "method": f"Synthèse extractive : {len(pool)} phrases analysées dans {len(members)} article(s), "
                      f"sélection par centralité (similarité au centroïde), anti-redondance et fiabilité des sources."}


# =====================================================================
#  4. COMPARAISON DES SOURCES
# =====================================================================
def compare_cluster(conn, cluster_id):
    cl = db.row(conn, "SELECT * FROM clusters WHERE id=?", (cluster_id,))
    if not cl:
        return None
    arts = db.rows(conn, "SELECT * FROM v_articles WHERE cluster_id=? ORDER BY published_at", (cluster_id,))
    publishers = {r["id"]: r["publisher"] for r in db.rows(conn, "SELECT s.id, COALESCE(s.publisher, s.name) publisher FROM sources s")}
    kw_sets = {}
    for a in arts:
        txt = a["title"] + " " + article_text(a)
        kw_sets[a["id"]] = set(nlp.keywords(txt, 14))
    counts = Counter(k for s in kw_sets.values() for k in s)
    threshold = max(2, math.ceil(len(arts) * 0.6))
    common = [k for k, c in counts.most_common() if c >= threshold][:10]
    items = []
    for rank, a in enumerate(arts):
        txt = a["title"] + " " + article_text(a)
        st = Counter(c["status"] for c in db.rows(conn, "SELECT status FROM claims WHERE article_id=?", (a["id"],)))
        items.append({
            "id": a["id"], "title": a["title"], "source": a["source_name"], "publisher": publishers.get(a["source_id"], a["source_name"]), "reliability": a["source_reliability"],
            "certified": a["source_certified"], "url": a["url"], "published_at": a["published_at"],
            "author": a["author"], "rank": rank + 1, "word_count": a["word_count"],
            "tone": nlp.tone(txt), "readability": nlp.readability(article_text(a)),
            "unique_keywords": [k for k in kw_sets[a["id"]] if counts[k] == 1][:6],
            "numbers": list(dict.fromkeys(f"{v:g}{(' ' + u) if u else ''}" for v, u in nlp.numbers(txt) if u))[:6],
            "claims": dict(st), "verification_status": a["verification_status"],
            "verification_label": status_label(a["verification_status"], cl["source_count"], a.get("status_reason")),
            "is_demo": a["is_demo"],
        })
    # Divergences chiffrées : même unité, valeurs différentes selon les médias
    by_unit = defaultdict(lambda: defaultdict(set))
    for a in arts:
        for v, u in nlp.numbers(a["title"] + " " + article_text(a)):
            if u:
                by_unit[u][f"{v:g}"].add(a["source_name"])
    divergences = []
    for unit, vals in by_unit.items():
        if len(vals) > 1 and len({s for ss in vals.values() for s in ss}) > 1:
            divergences.append({"unit": unit, "values": [{"value": k, "sources": sorted(v)} for k, v in vals.items()]})
    return {"cluster": cl, "articles": items, "common_keywords": common, "divergences": divergences[:6],
            "first": items[0]["source"] if items else None}


# =====================================================================
#  5. RECOMMANDATION PERSONNALISÉE, DIVERSIFIÉE ET EXPLICABLE
# =====================================================================
WEIGHTS = {"interet": 0.30, "fraicheur": 0.25, "fiabilite": 0.15, "couverture": 0.15, "mots_cles": 0.10, "historique": 0.05}
LABELS = {"interet": "Correspond à vos centres d'intérêt", "fraicheur": "Information récente",
          "fiabilite": "Pondération de la source", "couverture": "Sujet couvert par plusieurs médias",
          "mots_cles": "Contient un mot-clé que vous suivez", "historique": "Proche de vos lectures récentes"}


def user_profile(conn, user_id):
    explicit = {r["category_id"]: r["weight"] for r in db.rows(conn, "SELECT * FROM interests WHERE user_id=?", (user_id,))}
    hist = db.rows(conn, """SELECT a.category_id, a.title, a.summary FROM reading_history h JOIN articles a ON a.id=h.article_id
                            WHERE h.user_id=? ORDER BY h.read_at DESC LIMIT 50""", (user_id,))
    implicit = Counter(h["category_id"] for h in hist if h["category_id"])
    weights = defaultdict(float)
    for c, w in explicit.items():
        weights[c] += w
    total_hist = sum(implicit.values()) or 1
    for c, k in implicit.items():
        weights[c] += 0.6 * k / total_hist
    mx = max(weights.values()) if weights else 1
    weights = {c: w / mx for c, w in weights.items()}
    centroid = Counter()
    for h in hist[:30]:
        centroid.update(nlp.vector(h["title"], nlp.strip_html(h["summary"] or "")))
    alerts = [a["keyword"] for a in db.rows(conn, "SELECT keyword FROM alerts WHERE user_id=? AND active=1", (user_id,))]
    read_ids = {r["article_id"] for r in db.rows(conn, "SELECT article_id FROM reading_history WHERE user_id=?", (user_id,))}
    # Indice de diversité (entropie de Shannon normalisée) des lectures
    ncat = db.scalar(conn, "SELECT COUNT(*) FROM categories") or 1
    ent = -sum((k / total_hist) * math.log(k / total_hist) for k in implicit.values()) if implicit else 0
    diversity = round(100 * ent / math.log(ncat)) if ncat > 1 else 0
    return {"weights": weights, "centroid": centroid, "alerts": alerts, "read_ids": read_ids,
            "diversity_index": diversity, "history_size": len(hist), "implicit": dict(implicit)}


def explain(a, profile, now):
    pub = db.parse(a["published_at"])
    hours = (now - pub).total_seconds() / 3600 if pub else 500
    comp = {
        "fraicheur": math.exp(-max(hours, 0) / 48),
        "fiabilite": a["source_reliability"] / 100,
        "couverture": min((a.get("source_count") or 1) - 1, 3) / 3,
        "interet": 0.0, "mots_cles": 0.0, "historique": 0.0,
    }
    matched = []
    if profile:
        comp["interet"] = profile["weights"].get(a["category_id"], 0.0)
        hay = nlp.deaccent((a["title"] + " " + (a["summary"] or "")).lower())
        matched = [k for k in profile["alerts"] if _kw_match(k, hay)]
        comp["mots_cles"] = 1.0 if matched else 0.0
        comp["historique"] = min(nlp.cosine(profile["centroid"], nlp.vector(a["title"], nlp.strip_html(a["summary"] or ""))) * 3, 1.0)
        weights = WEIGHTS
    else:
        weights = {"fraicheur": 0.5, "fiabilite": 0.25, "couverture": 0.25, "interet": 0, "mots_cles": 0, "historique": 0}
    score = sum(weights[k] * comp[k] for k in comp)
    if a["verification_status"] == "conteste":
        score *= 0.6
    if profile and a["id"] in profile["read_ids"]:
        score *= 0.5
    details = sorted(({"key": k, "label": LABELS[k], "value": round(comp[k] * 100), "weight": round(weights[k] * 100),
                       "contribution": round(weights[k] * comp[k] * 100, 1)} for k in comp if weights[k] > 0),
                     key=lambda d: -d["contribution"])
    reasons = []
    for d in details[:3]:
        if d["contribution"] < 2:
            continue
        txt = d["label"]
        if d["key"] == "interet" and a.get("category_name"):
            txt += f" (« {a['category_name']} »)"
        if d["key"] == "mots_cles":
            txt += f" : « {', '.join(matched)} »"
        if d["key"] == "couverture":
            txt += f" ({a.get('source_count') or 1} sources)"
        if d["key"] == "fiabilite":
            if not a.get("is_demo"):
                continue
            txt += f" ({a['source_name']} : {a['source_reliability']}/100)"
        reasons.append(txt)
    if a["verification_status"] == "conteste":
        reasons.append("Rang abaissé : d'autres médias rapportent une version différente")
    return {"score": round(score * 100, 1), "components": details, "reasons": reasons, "discovery": False}


FEED_SQL = """SELECT a.*, s.name source_name, s.reliability source_reliability, s.certified source_certified, s.kind source_kind, COALESCE(s.publisher, s.name) source_publisher,
                     c.slug category_slug, c.name category_name, c.color category_color,
                     cl.size cluster_size, cl.source_count
              FROM articles a JOIN sources s ON s.id=a.source_id
              LEFT JOIN categories c ON c.id=a.category_id
              LEFT JOIN clusters cl ON cl.id=a.cluster_id
              WHERE s.active=1 {where}"""


def feed(conn, user, mode="pour_vous", category=None, media=None, source=None, limit=30, offset=0):
    where, params = ["a.is_cluster_lead=1"], []
    if category:
        where.append("c.slug=?"); params.append(category)
    if media:
        where.append("a.media_type=?"); params.append(media)
    if source:
        where.append("a.source_id=?"); params.append(int(source))
    sql = FEED_SQL.format(where=" AND " + " AND ".join(where)) + " ORDER BY a.published_at DESC LIMIT 600"
    arts = db.rows(conn, sql, params)
    now = db.now()
    profile = user_profile(conn, user["id"]) if user else None
    for a in arts:
        a["why"] = explain(a, profile if mode == "pour_vous" else None, now)
    if mode == "recent":
        arts.sort(key=lambda a: a["published_at"] or "", reverse=True)
    elif mode == "tendances":
        arts.sort(key=lambda a: ((a.get("source_count") or 1) * 10 + a["views"] / 10 + a["shares"]) * math.exp(
            -max((now - (db.parse(a["published_at"]) or now)).total_seconds(), 0) / 3600 / 72), reverse=True)
    else:
        arts.sort(key=lambda a: -a["why"]["score"])
        if profile and profile["weights"] and not category:
            arts = _diversify(arts, profile, user.get("diversity_ratio", 0.25))
    page = arts[offset: offset + limit]
    return {"items": [decorate(conn, a, now) for a in page], "total": len(arts),
            "profile": {"diversity_index": profile["diversity_index"], "history_size": profile["history_size"]} if profile else None}


def _diversify(arts, profile, ratio):
    """Anti bulle de filtres : réserve une part du fil à des thèmes hors intérêts."""
    top = {c for c, w in profile["weights"].items() if w >= 0.5}
    core = [a for a in arts if a["category_id"] in top]
    disc = [a for a in arts if a["category_id"] not in top]
    step = max(2, round(1 / max(ratio, 0.05)))
    out, i = [], 0
    while core or disc:
        i += 1
        if disc and (i % step == 0 or not core):
            d = disc.pop(0)
            d["why"]["discovery"] = True
            d["why"]["reasons"].insert(0, "Découverte : thème hors de vos habitudes, proposé pour diversifier votre information")
            out.append(d)
        elif core:
            out.append(core.pop(0))
    return out


def decorate(conn, a, now=None):
    now = now or db.now()
    pub, seen = db.parse(a["published_at"]), db.parse(a["first_seen_at"])
    latest = None
    if a.get("cluster_id"):
        latest = db.parse(db.scalar(conn, "SELECT MAX(published_at) FROM articles WHERE cluster_id=?", (a["cluster_id"],)))
    a["freshness"] = nlp.freshness(pub, seen, now, latest)
    a["verification_label"] = status_label(a["verification_status"], a.get("source_count"), a.get("status_reason"))
    a["reports_count"] = db.scalar(conn, "SELECT COUNT(*) FROM reports WHERE article_id=? AND status IN ('en_attente','en_cours')", (a["id"],))
    if a.get("cluster_id"):
        a["others"] = db.rows(conn, """SELECT a.id, a.title, a.url, a.published_at, s.name source_name, COALESCE(s.publisher, s.name) publisher FROM articles a
                                       JOIN sources s ON s.id=a.source_id WHERE a.cluster_id=? AND a.id<>? ORDER BY s.reliability DESC""",
                              (a["cluster_id"], a["id"]))
    else:
        a["others"] = []
    a.pop("content", None)
    a["summary"] = nlp.strip_html(a.get("summary") or "")[:320]
    return a


# =====================================================================
#  6. NOTIFICATIONS, TENDANCES, DIGEST
# =====================================================================
def _kw_match(keyword, haystack):
    """Recherche du mot-clé en mot entier, sans tenir compte des accents ni de la casse."""
    k = nlp.deaccent(keyword.lower()).strip()
    return bool(k) and re.search(r"(?<![a-z0-9])" + re.escape(k) + r"s?(?![a-z0-9])", haystack) is not None


@db.write
def check_alerts(conn, days=7):
    created = 0
    alerts = db.rows(conn, "SELECT * FROM alerts WHERE active=1")
    if not alerts:
        return 0
    recent = db.rows(conn, "SELECT id, title, summary FROM articles WHERE first_seen_at >= ? OR published_at >= ?", (db.ago(days=days), db.ago(days=days)))
    for al in alerts:
        for a in recent:
            if _kw_match(al["keyword"], nlp.deaccent((a["title"] + " " + (a["summary"] or "")).lower())):
                cur = conn.execute("INSERT OR IGNORE INTO notifications(user_id, article_id, kind, message) VALUES (?,?,?,?)",
                                   (al["user_id"], a["id"], "alerte", f"Alerte « {al['keyword']} » : {a['title']}"))
                created += cur.rowcount
    conn.commit()
    return created


def trends(conn, hours=48):
    since = db.ago(hours=hours)
    arts = db.rows(conn, "SELECT a.title, a.summary, COALESCE(s.publisher, s.name) source_id FROM articles a JOIN sources s ON s.id=a.source_id WHERE a.published_at>=?", (since,))
    if len(arts) < 10:
        arts = db.rows(conn, "SELECT a.title, a.summary, COALESCE(s.publisher, s.name) source_id FROM articles a JOIN sources s ON s.id=a.source_id ORDER BY a.published_at DESC LIMIT 200")
    by_kw = defaultdict(set)
    count = Counter()
    for a in arts:
        for k in set(nlp.keywords(a["title"] + " " + nlp.strip_html(a["summary"] or ""), 8)):
            by_kw[k].add(a["source_id"])
            count[k] += 1
    kws = sorted(by_kw, key=lambda k: (-len(by_kw[k]), -count[k]))[:20]
    topics = db.rows(conn, """SELECT cl.*, a.id article_id, a.title, a.image_url, s.name source_name, c.name category_name, c.color category_color
                              FROM clusters cl JOIN articles a ON a.id=cl.lead_article_id JOIN sources s ON s.id=a.source_id
                              LEFT JOIN categories c ON c.id=a.category_id
                              WHERE cl.last_published>=? ORDER BY cl.source_count DESC, cl.size DESC LIMIT 10""", (db.ago(days=7),))
    return {"keywords": [{"word": k, "sources": len(by_kw[k]), "mentions": count[k],
                          "hashtag": "#" + "".join(w.capitalize() for w in nlp.deaccent(k).replace("-", " ").replace("'", " ").split())} for k in kws],
            "topics": topics}


def digest(conn, hours=36):
    topics = db.rows(conn, """SELECT cl.id cluster_id, cl.source_count, cl.size, a.id FROM clusters cl JOIN articles a ON a.id=cl.lead_article_id
                              WHERE a.published_at>=? AND a.media_type='article' AND a.verification_status<>'conteste'
                              ORDER BY cl.source_count DESC, a.verification_score DESC LIMIT 7""", (db.ago(hours=hours),))
    if len(topics) < 4:
        topics = db.rows(conn, """SELECT cl.id cluster_id, cl.source_count, cl.size, a.id FROM clusters cl JOIN articles a ON a.id=cl.lead_article_id
                                  WHERE a.media_type='article' AND a.verification_status<>'conteste'
                                  ORDER BY a.published_at DESC LIMIT 7""")
    out = []
    for t in topics:
        a = db.row(conn, "SELECT * FROM v_articles WHERE id=?", (t["id"],))
        s = summarize(conn, t["id"], 2)
        out.append({"article": decorate(conn, a), "summary": s, "source_count": t["source_count"]})
    return {"generated_at": db.now_str(), "items": out}
