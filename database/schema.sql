-- =====================================================================
--  PRISME — Agrégateur intelligent des nouveaux médias
--  ESATIC — TWIN 3 — Groupe 7 (Eboua Franck, Kah Toily, Yao Francklin)
--  Schéma relationnel SQLite (3NF)
-- =====================================================================
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- 1. Utilisateurs, sessions et préférences
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    username         TEXT    NOT NULL UNIQUE,
    email            TEXT    NOT NULL UNIQUE,
    display_name     TEXT    NOT NULL,
    password_hash    TEXT    NOT NULL,           -- PBKDF2-SHA256
    salt             TEXT    NOT NULL,
    role             TEXT    NOT NULL DEFAULT 'user' CHECK (role IN ('user','admin')),
    persona          TEXT,                       -- profil de référence (cahier des charges)
    font_scale       REAL    NOT NULL DEFAULT 1.0,
    font_family      TEXT    NOT NULL DEFAULT 'prisme',
    high_contrast    INTEGER NOT NULL DEFAULT 0,
    theme            TEXT    NOT NULL DEFAULT 'auto' CHECK (theme IN ('auto','light','dark')),
    simple_mode      INTEGER NOT NULL DEFAULT 0, -- grands boutons, navigation simplifiée
    preferred_lang   TEXT    NOT NULL DEFAULT 'fr',
    diversity_ratio  REAL    NOT NULL DEFAULT 0.25, -- part du fil réservée à la découverte
    email_verified   INTEGER NOT NULL DEFAULT 0,
    country          TEXT,                       -- pays de résidence déclaré à l'inscription
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Codes à usage unique envoyés par e-mail (seule leur empreinte est conservée)
CREATE TABLE IF NOT EXISTS email_codes (
    email       TEXT NOT NULL,
    purpose     TEXT NOT NULL CHECK (purpose IN ('register','reset')),
    code_hash   TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (email, purpose)
);

CREATE TABLE IF NOT EXISTS sessions (
    token       TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at  TEXT NOT NULL
);

-- ---------------------------------------------------------------------
-- 2. Référentiels : catégories et sources
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS categories (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    slug   TEXT NOT NULL UNIQUE,
    name   TEXT NOT NULL,
    color  TEXT NOT NULL DEFAULT '#6366f1'
);

CREATE TABLE IF NOT EXISTS sources (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    name               TEXT    NOT NULL UNIQUE,
    publisher          TEXT,                      -- éditeur : plusieurs flux d'un même média comptent pour un seul
    website            TEXT,
    feed_url           TEXT,                      -- NULL = source de démonstration
    country            TEXT,
    language           TEXT    NOT NULL DEFAULT 'fr',
    kind               TEXT    NOT NULL DEFAULT 'presse'
                       CHECK (kind IN ('presse','tv','radio','web','podcast','social','agence')),
    default_category   INTEGER REFERENCES categories(id),
    reliability        INTEGER NOT NULL DEFAULT 60 CHECK (reliability BETWEEN 0 AND 100),
    certified          INTEGER NOT NULL DEFAULT 0,
    reliability_note   TEXT,
    is_demo            INTEGER NOT NULL DEFAULT 0,
    active             INTEGER NOT NULL DEFAULT 1,
    last_fetched_at    TEXT,
    last_error         TEXT
);

-- ---------------------------------------------------------------------
-- 3. Contenus agrégés
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS clusters (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    label            TEXT,
    lead_article_id  INTEGER,
    size             INTEGER NOT NULL DEFAULT 1,
    source_count     INTEGER NOT NULL DEFAULT 1,
    first_published  TEXT,
    last_published   TEXT,
    updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS articles (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id           INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    guid                TEXT    NOT NULL UNIQUE,
    title               TEXT    NOT NULL,
    summary             TEXT,
    content             TEXT,
    url                 TEXT,                      -- lien vers la source originale
    author              TEXT,
    image_url           TEXT,
    media_type          TEXT NOT NULL DEFAULT 'article'
                        CHECK (media_type IN ('article','podcast','video','social')),
    media_url           TEXT,
    duration_sec        INTEGER,
    language            TEXT NOT NULL DEFAULT 'fr',
    category_id         INTEGER REFERENCES categories(id),
    published_at        TEXT,                      -- date de publication déclarée par le média
    first_seen_at       TEXT NOT NULL DEFAULT (datetime('now')), -- date de 1re collecte
    cluster_id          INTEGER REFERENCES clusters(id) ON DELETE SET NULL,
    is_cluster_lead     INTEGER NOT NULL DEFAULT 1,
    word_count          INTEGER NOT NULL DEFAULT 0,
    views               INTEGER NOT NULL DEFAULT 0,
    shares              INTEGER NOT NULL DEFAULT 0,
    verification_status TEXT NOT NULL DEFAULT 'en_attente'
                        CHECK (verification_status IN ('en_attente','verifie','partiel','non_verifie','conteste')),
    verification_score  INTEGER,
    verified_at         TEXT,
    correction_note     TEXT,                      -- correction publiée suite à un signalement
    status_reason       TEXT,                      -- 'chiffres' ou 'dementi' lorsque le statut signale un désaccord
    is_demo             INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_cluster   ON articles(cluster_id);
CREATE INDEX IF NOT EXISTS idx_articles_source    ON articles(source_id);
CREATE INDEX IF NOT EXISTS idx_articles_url       ON articles(url);
CREATE INDEX IF NOT EXISTS idx_articles_category  ON articles(category_id);

-- ---------------------------------------------------------------------
-- 4. Vérification assistée par IA : affirmations et preuves
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS claims (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id   INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    position     INTEGER NOT NULL,
    sentence     TEXT    NOT NULL,
    claim_types  TEXT    NOT NULL,                 -- chiffre, citation, attribution, causalite, absolu, rumeur
    status       TEXT    NOT NULL DEFAULT 'non_verifie'
                 CHECK (status IN ('verifie','partiel','non_verifie','conteste')),
    confidence   INTEGER NOT NULL DEFAULT 0,
    rationale    TEXT
);
CREATE INDEX IF NOT EXISTS idx_claims_article ON claims(article_id);

CREATE TABLE IF NOT EXISTS evidences (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id           INTEGER NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    article_id         INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    excerpt            TEXT    NOT NULL,
    stance             TEXT    NOT NULL CHECK (stance IN ('soutient','contredit','neutre')),
    similarity         REAL    NOT NULL
);

-- ---------------------------------------------------------------------
-- 5. Personnalisation : intérêts, historique, favoris, veille
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS interests (
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_id  INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    weight       REAL    NOT NULL DEFAULT 1.0,
    PRIMARY KEY (user_id, category_id)
);

CREATE TABLE IF NOT EXISTS reading_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    article_id  INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    read_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_history_user ON reading_history(user_id);

CREATE TABLE IF NOT EXISTS folders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT    NOT NULL,
    color       TEXT    NOT NULL DEFAULT '#0ea5e9',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, name)
);

CREATE TABLE IF NOT EXISTS favorites (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    article_id  INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    folder_id   INTEGER REFERENCES folders(id) ON DELETE SET NULL,
    note        TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, article_id)
);

CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    keyword     TEXT    NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, keyword)
);

-- Abonnement d'un utilisateur à un média (éditeur) : notification à chaque nouvel article collecté.
CREATE TABLE IF NOT EXISTS subscriptions (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    publisher   TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, publisher)
);
CREATE INDEX IF NOT EXISTS idx_subscriptions_publisher ON subscriptions(publisher);

-- Verdicts sur une information : conclusion d'un fact-checker professionnel (lien vers son analyse) ou de la rédaction
-- Prisme (explication et sources obligatoires). Le verdict vise un article ; il s'applique à tout l'événement de cet article.
CREATE TABLE IF NOT EXISTS verdicts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id  INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    verdict     TEXT    NOT NULL CHECK (verdict IN ('vrai','faux','trompeur','analyse')),
    origin      TEXT    NOT NULL CHECK (origin IN ('factcheck','redaction')),
    checker     TEXT    NOT NULL,
    url         TEXT,
    claim       TEXT,
    explanation TEXT,
    sources     TEXT,
    created_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_verdicts_article ON verdicts(article_id);

-- Médias masqués par un lecteur : leurs articles n'apparaissent plus dans ses fils (la recherche les montre toujours).
CREATE TABLE IF NOT EXISTS hidden_sources (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    publisher   TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, publisher)
);

CREATE TABLE IF NOT EXISTS notifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    article_id  INTEGER REFERENCES articles(id) ON DELETE CASCADE,
    kind        TEXT    NOT NULL DEFAULT 'alerte' CHECK (kind IN ('alerte','signalement','systeme','digest','abonnement','verdict')),
    message     TEXT    NOT NULL,
    is_read     INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, article_id, kind)
);

-- ---------------------------------------------------------------------
-- 6. Signalement d'erreurs (modération)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reports (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER REFERENCES users(id) ON DELETE SET NULL,
    article_id      INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    reason          TEXT    NOT NULL CHECK (reason IN ('factuelle','date','source','titre_trompeur','traduction','doublon','autre')),
    description     TEXT    NOT NULL,
    evidence_url    TEXT,
    status          TEXT    NOT NULL DEFAULT 'en_attente'
                    CHECK (status IN ('en_attente','en_cours','corrige','rejete')),
    admin_response  TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    resolved_at     TEXT
);

-- ---------------------------------------------------------------------
-- 7. Partage, traduction, simplification
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shares (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    article_id  INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    channel     TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS translations (
    article_id  INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    lang        TEXT    NOT NULL,
    title       TEXT    NOT NULL,
    body        TEXT    NOT NULL,
    engine      TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (article_id, lang)
);

CREATE TABLE IF NOT EXISTS glossary (
    term        TEXT PRIMARY KEY,               -- terme complexe (minuscule)
    simple      TEXT NOT NULL,                  -- équivalent simple
    definition  TEXT
);

-- ---------------------------------------------------------------------
-- 8. Journal technique (collectes RSS)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fetch_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at  TEXT,
    sources_ok   INTEGER DEFAULT 0,
    sources_ko   INTEGER DEFAULT 0,
    new_articles INTEGER DEFAULT 0,
    message      TEXT
);

-- Traçabilité : qui a changé quoi (modération, sources, statuts)
CREATE TABLE IF NOT EXISTS change_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    at         TEXT NOT NULL DEFAULT (datetime('now')),
    actor      TEXT NOT NULL,
    entity     TEXT NOT NULL,
    entity_id  INTEGER,
    action     TEXT NOT NULL,
    detail     TEXT
);

CREATE TABLE IF NOT EXISTS meta (
    key    TEXT PRIMARY KEY,
    value  TEXT
);

-- Tests utilisateurs : questionnaire SUS (System Usability Scale, 10 affirmations notées de 1 à 5)
CREATE TABLE IF NOT EXISTS feedback (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    answers     TEXT    NOT NULL,                 -- dix notes séparées par des virgules
    sus         REAL    NOT NULL CHECK (sus BETWEEN 0 AND 100),
    profile     TEXT,                             -- profil déclaré du testeur (facultatif)
    comment     TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Vue utile pour la présentation : articles + source + catégorie
CREATE VIEW IF NOT EXISTS v_articles AS
SELECT a.*, s.name AS source_name, s.reliability AS source_reliability, s.certified AS source_certified,
       s.kind AS source_kind, c.slug AS category_slug, c.name AS category_name, c.color AS category_color
FROM articles a
JOIN sources s ON s.id = a.source_id
LEFT JOIN categories c ON c.id = a.category_id;
