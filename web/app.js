/* PRISME — Application monopage (JavaScript natif, sans framework) */
"use strict";

// ====================================================================
//  État global, API et utilitaires
// ====================================================================
const S = { user: null, token: null, cats: [], unread: 0, favs: new Set(), feedMode: "pour_vous", feedCat: "", feedMedia: "", lastUnread: null };
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const main = () => $("#main");
function nav(url) { history.pushState(null, "", url); route(); }
function setTitle(t) { document.title = t.startsWith("Prisme") ? t : `${t} | Prisme`; }
const safeUrl = (u) => /^https?:\/\//i.test(String(u || "").trim()) ? String(u).trim() : "";
function openDrawer() { $("#sidebar").classList.add("open"); $("#drawerBack").hidden = false; $("#menuBtn").setAttribute("aria-expanded", "true"); $("#nav a")?.focus(); }
function closeDrawer() { $("#sidebar").classList.remove("open"); $("#drawerBack").hidden = true; $("#menuBtn").setAttribute("aria-expanded", "false"); }
async function dateline() {
  const el = $("#dateline");
  const today = new Date().toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  el.textContent = today.charAt(0).toUpperCase() + today.slice(1);
  const st = await get("/api/stats").catch(() => null);
  if (st) el.textContent += ` · ${st.real_sources || st.sources} médias suivis` + (st.last_fetch ? ` · dernière collecte ${ago(st.last_fetch.finished_at)}` : "");
}
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* stockage indisponible */ } },
  del(k) { try { localStorage.removeItem(k); } catch { /* ignoré */ } },
};

async function api(method, path, body) {
  const headers = { "Content-Type": "application/json" };
  if (S.token) headers.Authorization = "Bearer " + S.token;
  let res;
  try { res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined }); }
  catch { throw new Error("Connexion au serveur impossible. Vérifiez votre réseau puis réessayez."); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401 && S.token && path !== "/api/login") { logoutLocal(); }
    throw new Error(data.error || "Le serveur n'a pas pu traiter la demande.");
  }
  return data;
}
const get = (p) => api("GET", p);
const post = (p, b) => api("POST", p, b || {});
const put = (p, b) => api("PUT", p, b || {});
const del = (p) => api("DELETE", p);

function esc(s) { return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
function toast(msg, err) {
  const t = document.createElement("div");
  t.className = "toast" + (err ? " err" : "");
  t.textContent = msg;
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), 4200);
}
function parseDate(s) { return s ? new Date(s.replace(" ", "T") + "Z") : null; }
function fmtDate(s, withTime = true) {
  const d = parseDate(s);
  if (!d) return "Date inconnue";
  return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "numeric", ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}) });
}
function ago(s) {
  const d = parseDate(s);
  if (!d) return "date inconnue";
  const m = (Date.now() - d) / 60000;
  if (m < 60) return `il y a ${Math.max(1, Math.round(m))} min`;
  if (m < 1440) return `il y a ${Math.round(m / 60)} h`;
  const days = m / 1440;
  if (days < 30) return `il y a ${Math.round(days)} j`;
  if (days < 365) return `il y a ${Math.round(days / 30)} mois`;
  return `il y a ${Math.floor(days / 365)} an(s)`;
}
function initials(n) { return (n || "?").split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase(); }

// ====================================================================
//  Icônes (SVG en ligne)
// ====================================================================
const P = {
  home: '<path d="M3 10.5 12 3l9 7.5V21H3z"/><path d="M9 21v-7h6v7"/>',
  trend: '<path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/>',
  digest: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 8h10M7 12h10M7 16h6"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  headphones: '<path d="M3 14v-2a9 9 0 0 1 18 0v2"/><rect x="3" y="14" width="4" height="7" rx="1"/><rect x="17" y="14" width="4" height="7" rx="1"/>',
  eye: '<circle cx="12" cy="12" r="3"/><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/>',
  star: '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z"/>',
  flag: '<path d="M4 21V4"/><path d="M4 4h12l-2 4 2 4H4"/>',
  db: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
  shield: '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/><path d="m9 12 2 2 4-4"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 8h.01M11 12h1v5h1"/>',
  bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.9 1.9 0 0 0 3.4 0"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
  share: '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.6 13.5 6.8 4M15.4 6.5l-6.8 4"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  alert: '<path d="M12 3 2 21h20z"/><path d="M12 10v5M12 18h.01"/>',
  check: '<path d="m5 12 5 5 9-10"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17h.01"/>',
  ai: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  text: '<path d="M4 7V5h16v2M9 19h6M12 5v14"/>',
  columns: '<rect x="3" y="4" width="7" height="16" rx="1"/><rect x="14" y="4" width="7" height="16" rx="1"/>',
  download: '<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',
  ext: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  logout: '<path d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 17l5-5-5-5M15 12H3"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  folder: '<path d="M3 6a1 1 0 0 1 1-1h5l2 2h9a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/>',
  video: '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="m16 10 5-3v10l-5-3z"/>',
  hash: '<path d="M5 9h14M5 15h14M10 3 8 21M16 3l-2 18"/>',
  print: '<path d="M6 9V3h12v6"/><rect x="3" y="9" width="18" height="8" rx="2"/><path d="M6 14h12v7H6z"/>',
  copy: '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V4a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v11a1 1 0 0 0 1 1h4"/>',
  book: '<path d="M4 4h6a3 3 0 0 1 3 3v14a2 2 0 0 0-2-2H4z"/><path d="M20 4h-6a3 3 0 0 0-3 3v14a2 2 0 0 1 2-2h7z"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  play: '<path d="M7 4v16l13-8z"/>',
  users: '<circle cx="9" cy="8" r="4"/><path d="M2 21a7 7 0 0 1 14 0M16 4a4 4 0 0 1 0 8M22 21a7 7 0 0 0-5-6.7"/>',
  social: '<path d="M21 12a8 8 0 0 1-11.8 7L3 21l2-6A8 8 0 1 1 21 12z"/>',
  reader: '<path d="M3 5h7a2 2 0 0 1 2 2v12a2 2 0 0 0-2-2H3zM21 5h-7a2 2 0 0 0-2 2v12a2 2 0 0 1 2-2h7z"/>',
};
const ico = (n) => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${P[n] || ""}</svg>`;

// ====================================================================
//  Badges métier
// ====================================================================
const STATUS = {
  verifie: ["b-ok", "layers", "Repris par 3 sources ou plus"], partiel: ["b-info", "layers", "Repris par 2 sources"],
  non_verifie: ["", "user", "Source unique"], conteste: ["b-warn", "alert", "Désaccord entre sources"], en_attente: ["", "clock", "En attente"],
};
const statusBadge = (s, label) => { const [c, i, l] = STATUS[s] || STATUS.en_attente; return `<span class="badge ${c}" title="Couverture observée. Prisme ne certifie pas les faits : voir Notre méthode.">${ico(i)}${esc(label || l)}</span>`; };
const mediaCount = (a) => new Set([a.source_name, ...(a.others || []).map((o) => o.source_name)]).size;
const spectre = (n) => { n = Math.max(1, n || 1); return `<span class="spectre ${n === 1 ? "one" : ""}" title="${n} média${n > 1 ? "s" : ""} sur ce sujet"><span class="bars" aria-hidden="true">${"<i></i>".repeat(Math.min(n, 12))}</span>${n === 1 ? "1 média" : `${n} médias`}</span>`; };
const freshBadge = (f) => {
  if (!f) return "";
  if (f.recirculating) return `<span class="badge b-warn" title="${esc(f.warning || "")}">${ico("alert")}Ancienne info qui recircule</span>`;
  return f.level === "brulant" ? `<span class="fresh hot">${esc(f.label)}</span>` : "";
};
const MEDIA = { article: ["digest", "Article"], podcast: ["headphones", "Podcast"], video: ["video", "Vidéo"], social: ["social", "Réseaux sociaux"] };
const mediaBadge = (m) => m && m !== "article" ? `<span class="badge b-info">${ico(MEDIA[m][0])}${MEDIA[m][1]}</span>` : "";
const catBadge = (a) => a.category_name ? `<a class="kicker" href="/rubrique/${esc(a.category_slug)}">${esc(a.category_name)}</a>` : `<span class="kicker">Actualité</span>`;
const when = (s) => s ? `<time datetime="${esc(s.replace(" ", "T"))}Z" title="${esc(ago(s))}">${esc(fmtDate(s))}</time>` : "Date inconnue";
const relBadge = (r, cert, demo) => demo ? `<span class="badge" title="Score fictif du scénario de démonstration">${r}/100 (démo)</span>` : "";
const demoBadge = (a) => a.is_demo ? `<span class="badge b-demo" title="Contenu fictif créé pour la démonstration">Démo</span>` : "";

// ====================================================================
//  Navigation
// ====================================================================
function navItems() {
  const admin = S.user && S.user.role === "admin";
  return [
    ["Lire"],
    ["/", "home", "À la une"], ["/tendances", "trend", "Tendances"], ["/digest", "digest", "Le digest du jour"],
    ["/multimedia", "headphones", "Podcasts et vidéos"], ["/recherche", "search", "Recherche avancée"],
    ["Mon espace"],
    ["/veille", "eye", "Veille et alertes"], ["/favoris", "star", "Favoris"],
    ["/notifications", "bell", "Notifications", S.unread], ["/signalements", "flag", "Signalements"],
    ["Prisme"],
    ["/sources", "db", "Médias suivis"], ["/methode", "shield", "Notre méthode"], ...(admin ? [["/admin", "chart", "Administration"]] : []),
    ["/parametres", "gear", "Paramètres et accessibilité"], ["/projet", "info", "Le projet"],
  ];
}
function renderNav() {
  const cur = location.pathname;
  $("#nav").innerHTML = navItems().map((n) => n.length === 1 ? `<div class="nav-sec">${n[0]}</div>` :
    `<a class="nav-a ${(cur === n[0] || (n[0] !== "/" && cur.startsWith(n[0]))) ? "active" : ""}" href="${n[0]}" ${cur === n[0] ? 'aria-current="page"' : ""}>${ico(n[1])}<span>${n[2]}</span>${n[3] ? `<span class="count">${n[3]}</span>` : ""}</a>`).join("");
  $$("#rubrics a").forEach((a) => a.classList.toggle("active", a.getAttribute("href") === cur));
  $("#notifBtn").innerHTML = ico("bell") + (S.unread ? `<span class="dot">${S.unread > 99 ? "99+" : S.unread}</span>` : "");
  $("#refreshBtn").hidden = !(S.user && S.user.role === "admin");
  $("#userBox").innerHTML = S.user
    ? `<button class="user-chip" data-act="usermenu" aria-label="Mon compte"><span class="avatar">${esc(initials(S.user.display_name))}</span><span class="nm small"><b>${esc(S.user.display_name)}</b></span></button>`
    : `<a class="btn" href="/connexion">${ico("user")}<span class="nm">Se connecter</span></a>`;
}

function applyPrefs() {
  const p = S.user || store.get("prisme_prefs", { font_scale: 1, high_contrast: 0, theme: "auto", simple_mode: 0 });
  const r = document.documentElement;
  r.style.setProperty("--fs", p.font_scale || 1);
  if (p.theme && p.theme !== "auto") r.dataset.theme = p.theme; else delete r.dataset.theme;
  if (p.high_contrast) r.dataset.contrast = "high"; else delete r.dataset.contrast;
  document.body.classList.toggle("simple", !!p.simple_mode);
}

// ====================================================================
//  Composant : carte d'article
// ====================================================================
const illustration = (a) => `/illustrations/${esc(a.category_slug || "actualite")}-${(a.id || 0) % 3}.svg`;
const picture = (a, big) => safeUrl(a.image_url)
  ? `<img src="/img/${a.id}-${big ? 960 : 480}.webp" srcset="/img/${a.id}-480.webp 480w, /img/${a.id}-960.webp 960w" sizes="${big ? "(max-width: 820px) 100vw, 66vw" : "(max-width: 820px) 100vw, 320px"}" alt="" ${big ? 'fetchpriority="high"' : 'loading="lazy"'} decoding="async" data-fallback="${illustration(a)}">`
  : `<img src="${illustration(a)}" alt="" loading="lazy"><span class="illu-tag">Illustration</span>`;
function card(a) {
  const others = a.others || [];
  const names = [...new Set(others.map((o) => o.source_name))].filter((n) => n !== a.source_name);
  const why = a.why;
  return `<article class="card" data-id="${a.id}">
    <a class="card-img" href="/article/${a.id}" tabindex="-1" aria-hidden="true"><span class="media-tag">${mediaBadge(a.media_type)}</span>${picture(a)}</a>
    <div class="card-body">
      <div class="row" style="gap:6px 10px">${catBadge(a)}${freshBadge(a.freshness)}${why && why.discovery ? `<span class="badge discovery-tag">${ico("globe")}Découverte</span>` : ""}${demoBadge(a)}</div>
      <h3><a href="/article/${a.id}">${esc(a.title)}</a></h3>
      ${a.freshness && a.freshness.recirculating ? `<div class="alert-line warn small">${ico("alert")}<span>${esc(a.freshness.warning)}</span></div>` : ""}
      ${a.correction_note ? `<div class="alert-line ok small">${ico("check")}<span>Correction publiée suite à un signalement.</span></div>` : ""}
      <p class="sum">${esc(a.summary)}</p>
      <div class="byline"><strong>${esc(a.source_name)}</strong>${relBadge(a.source_reliability, a.source_certified, a.is_demo)}${when(a.published_at)}${a.verification_status === "conteste" ? statusBadge(a.verification_status, a.verification_label) : ""}</div>
      ${others.length ? `<button class="dup" data-act="compare" data-cluster="${a.cluster_id}">${spectre(mediaCount(a))} <span>${names.length ? `Comparer : ${esc(names.slice(0, 2).join(", "))}${names.length > 2 ? "…" : ""}` : `Comparer les ${others.length + 1} articles`}</span></button>` : ""}
      <div class="why" hidden></div>
    </div>
    <div class="card-foot">
      ${a.media_type === "podcast" && a.media_url ? `<button class="btn ghost" data-act="play" data-id="${a.id}" aria-label="Écouter">${ico("play")}<span class="lbl">Écouter</span></button>` : ""}
      <button class="btn ghost" data-act="why" title="Pourquoi cet article est-il proposé ?" aria-label="Pourquoi cet article est-il proposé ?">${ico("help")}<span class="lbl">Pourquoi ?</span></button>
      <span class="grow"></span>
      <button class="btn ghost" data-act="fav" data-id="${a.id}" title="Ajouter aux favoris" aria-label="Ajouter aux favoris" aria-pressed="${S.favs.has(a.id)}" style="${S.favs.has(a.id) ? "color:var(--accent)" : ""}">${ico("star")}<span class="lbl">Favori</span></button>
      <button class="btn ghost" data-act="share" data-id="${a.id}" title="Partager" aria-label="Partager">${ico("share")}<span class="lbl">Partager</span></button>
      <button class="btn ghost" data-act="report" data-id="${a.id}" title="Signaler une erreur" aria-label="Signaler une erreur">${ico("flag")}<span class="lbl">Signaler</span></button>
    </div>
  </article>`;
}
const CARD_CACHE = new Map();
function cards(items) {
  items.forEach((a) => CARD_CACHE.set(a.id, a));
  return items.length ? `<div class="feed">${items.map(card).join("")}</div>` : empty("Aucun contenu ne correspond à ces critères.");
}
function whyHtml(w) {
  if (!w) return "";
  return `<b>${ico("help")} Pourquoi cet article ?</b>
    <ul>${(w.reasons.length ? w.reasons : ["Classement par défaut : fraîcheur et couverture médiatique"]).map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
    <div class="small muted" style="margin-top:6px">Score de recommandation : <b>${w.score}</b>/100 — contribution de chaque critère :</div>
    ${w.components.map((c) => `<div class="bar"><span>${esc(c.label.replace("Correspond à vos centres d'intérêt", "Centres d'intérêt"))}</span><span class="track"><i style="width:${c.value}%"></i></span><span class="muted">${c.weight}%</span></div>`).join("")}`;
}
const empty = (msg, icon = "search") => `<div class="empty">${ico(icon)}<div>${msg}</div></div>`;
const ssrShown = () => !!$("#main [data-ssr]");
const skeleton = (n = 6) => `<div class="feed">${'<div class="skeleton"></div>'.repeat(n)}</div>`;

// ====================================================================
//  Pages
// ====================================================================
async function pageFeed() {
  const cat = S.cats.find((c) => c.slug === S.feedCat);
  if (cat) setTitle(`${cat.name} : l'actualité comparée`);
  if (ssrShown()) {   // la page reçue du serveur reste visible jusqu'à ce que les données soient prêtes
    const qs = new URLSearchParams({ mode: S.feedMode, category: S.feedCat, media: S.feedMedia, offset: 0, limit: 24 });
    await get("/api/feed?" + qs).catch(() => null);
  }
  const isHome = !S.feedCat && !S.feedMedia && S.feedMode === "pour_vous";
  main().innerHTML = `
    ${cat ? `<div class="page-head"><div><span class="kicker">Rubrique</span><h1>${esc(cat.name)}</h1></div></div>` : `<h1 class="sr">Prisme : l'actualité comparée, média par média</h1>`}
    <div id="recall"></div>
    <div id="front">${isHome || cat ? `<div class="skeleton"></div>` : ""}</div>
    ${!cat ? `<div id="topics"></div>` : ""}
    <div class="sec-title"><h2>${cat ? "Tous les sujets" : "Le fil"}</h2><small id="feedCount"></small></div>
    <div class="page-head" style="margin-bottom:12px">
      <div class="tabs" style="margin:0;flex:1">
        ${[["pour_vous", "ai", S.user ? "Pour vous" : "Sélection"], ["recent", "clock", "Les plus récents"], ["tendances", "trend", "Les plus couverts"]].map(([k, i, l]) => `<button class="tab ${S.feedMode === k ? "active" : ""}" data-act="mode" data-mode="${k}" aria-pressed="${S.feedMode === k}">${ico(i)}${l}</button>`).join("")}
      </div>
      <label class="sr" for="mediaSel">Filtrer par format</label>
      <select class="input" id="mediaSel" style="width:auto">
        <option value="">Tous les formats</option>${Object.entries(MEDIA).map(([k, v]) => `<option value="${k}" ${S.feedMedia === k ? "selected" : ""}>${v[1]}</option>`).join("")}
      </select>
    </div>
    <div id="feedInfo"></div>
    <div class="feed-wrap">
      <div><div id="feedList">${skeleton()}</div>
        <div class="row" style="justify-content:center;margin-top:24px"><button class="btn" id="moreBtn" hidden>Afficher plus de sujets</button></div></div>
      <aside class="rail stack" id="rail" aria-label="Tendances"></aside>
    </div>`;
  $("#mediaSel").onchange = (e) => { S.feedMedia = e.target.value; pageFeed(); };
  loadFeed(true);
  if (!cat) loadHomeExtras();
  else get(`/api/recall?category=${encodeURIComponent(cat.slug)}`).then((d) => { if (d.recall && $("#recall")) $("#recall").innerHTML = recallBox(d.recall); }).catch(() => {});
}
function recallBox(r) {
  return `<section class="recall" aria-labelledby="recallTitle"><span class="kicker">Rappel</span><h2 id="recallTitle">${esc(r.title)}</h2>
    <ul>${r.items.map((i) => `<li><b>${esc(i.match)}</b><span class="byline"><time datetime="${esc(i.date)}">${esc(new Date(i.date + "T12:00:00Z").toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" }))}</time><span>${esc(i.competition)}</span>${i.detail ? `<span>${esc(i.detail)}</span>` : ""}</span>
      <span class="small">Sources : ${i.sources.map((x) => `<a href="${esc(safeUrl(x.url))}" target="_blank" rel="noopener">${esc(x.name)}</a>`).join(", ")}</span></li>`).join("")}</ul>
    <p class="small muted">${esc(r.note)}</p></section>`;
}
const byline = (a) => `<div class="byline"><strong>${esc(a.source_name)}</strong>${when(a.published_at)}${demoBadge(a)}</div>`;
function leadStory(a) {
  const n = mediaCount(a);
  return `<article class="lead-story">
    <a class="frame" href="/article/${a.id}" tabindex="-1" aria-hidden="true">${picture(a, true)}</a>
    <div class="row" style="gap:6px 10px">${catBadge(a)}${freshBadge(a.freshness)}</div>
    <h2 class="lead-title"><a href="/article/${a.id}">${esc(a.title)}</a></h2>
    <p class="sum">${esc(a.summary)}</p>
    <div class="row">${byline(a)}${a.others && a.others.length ? `<a href="/sujet/${a.cluster_id}" class="small" style="font-weight:600">${spectre(n)} Comparer</a>` : ""}</div>
  </article>`;
}
function sideStory(a) {
  const n = mediaCount(a);
  return `<article class="side-story"><div class="row" style="gap:6px 10px">${catBadge(a)}${freshBadge(a.freshness)}</div>
    <h3><a href="/article/${a.id}">${esc(a.title)}</a></h3>${byline(a)}${n > 1 ? `<div style="margin-top:6px"><a href="/sujet/${a.cluster_id}" style="text-decoration:none">${spectre(n)}</a></div>` : ""}</article>`;
}
async function loadHomeExtras() {
  const t = await get("/api/trends").catch(() => null);
  if (!t || !$("#rail")) return;
  const multi = t.topics.filter((x) => x.source_count > 1).slice(0, 6);
  if ($("#topics") && multi.length && !S.feedMedia) {
    $("#topics").innerHTML = `<div class="sec-title"><h2>Un événement, plusieurs regards</h2><small>Chaque barre représente un média</small></div>
      <div class="topics">${multi.map((c) => `<article class="topic"><div class="row" style="justify-content:space-between"><span class="kicker">${esc(c.category_name || "Actualité")}</span>${spectre(c.source_count)}</div>
        <h3><a href="/sujet/${c.id}">${esc(c.title)}</a></h3><div class="byline">${when(c.last_published)}</div><a class="go" href="/sujet/${c.id}">Comparer les ${c.size} articles</a></article>`).join("")}</div>`;
  }
  $("#rail").innerHTML = `<div class="panel"><h3>Les mots du moment</h3><ol class="rank">${t.keywords.slice(0, 8).map((k) => `<li><a href="/recherche?q=${encodeURIComponent(k.word)}&dedup=1">${esc(k.word)}</a></li>`).join("")}</ol></div>
    <div class="panel"><h3>Le digest du jour</h3><p class="small muted">L'essentiel en quelques minutes, à partir de plusieurs sources citées.</p><a class="btn sm" href="/digest">${ico("digest")} Lire le digest</a></div>
    <div class="panel"><h3>Comment lire Prisme</h3><p class="small muted">Le spectre indique combien de médias couvrent un même événement. C'est une mesure de couverture, pas une preuve de véracité.</p><a class="small" href="/methode">Notre méthode</a></div>`;
}
let feedOffset = 0;
async function loadFeed(reset) {
  if (reset) feedOffset = 0;
  const qs = new URLSearchParams({ mode: S.feedMode, category: S.feedCat, media: S.feedMedia, offset: feedOffset, limit: 24 });
  let data;
  try { data = await get("/api/feed?" + qs); }
  catch (e) { const l = $("#feedList"); if (l) l.innerHTML = `<div class="alert-line bad">${ico("alert")}<span>${esc(e.message)}</span></div>`; return; }
  const list = $("#feedList");
  if (!list) return;
  let items = data.items;
  if (reset) {
    const front = $("#front");
    const useFront = !S.feedMedia && S.feedMode === "pour_vous" && items.length >= 5;
    if (useFront) {
      items.forEach((a) => CARD_CACHE.set(a.id, a));
      const lead = items.find((a) => safeUrl(a.image_url)) || items[0];
      const rest = items.filter((a) => a !== lead);
      front.innerHTML = `<section class="front" aria-label="À la une">${leadStory(lead)}<div class="side-col">${rest.slice(0, 4).map(sideStory).join("")}</div></section>`;
      items = rest.slice(4);
    } else front.innerHTML = "";
    if (!data.total) {
      front.innerHTML = "";
      list.innerHTML = `<div class="empty">${ico("refresh")}<h2>Les premiers articles arrivent</h2><p>La collecte des flux est en cours. Revenez dans une minute.</p></div>`;
    } else list.innerHTML = cards(items);
  } else list.querySelector(".feed")?.insertAdjacentHTML("beforeend", items.map((a) => (CARD_CACHE.set(a.id, a), card(a))).join(""));
  feedOffset += data.items.length;
  $("#moreBtn").hidden = feedOffset >= data.total;
  $("#moreBtn").onclick = () => loadFeed(false);
  $("#feedCount").textContent = data.total ? `${data.total} sujets` : "";
  const info = $("#feedInfo");
  if (data.profile && S.feedMode === "pour_vous") {
    const d = data.profile.diversity_index;
    info.innerHTML = `<div class="alert-line ${d >= 60 ? "ok" : "info"}" style="margin-bottom:16px">${ico("globe")}<span><b>Diversité de vos lectures : ${d}/100.</b>
      ${d >= 60 ? "Vos lectures sont variées." : "Vos lectures se concentrent sur peu de thèmes : Prisme insère des articles « Découverte »."}
      Part réservée à la découverte : ${Math.round((S.user.diversity_ratio || 0.25) * 100)} %. <a href="/parametres">Ajuster</a></span></div>`;
  } else info.innerHTML = "";
}

async function pageArticle(id) {
  if (!ssrShown()) main().innerHTML = skeleton(2);
  const a = await get(`/api/articles/${id}`);
  CARD_CACHE.set(a.id, a);
  setTitle(`${a.title} — ${a.source_name}`);
  if (a.path && location.pathname !== a.path) history.replaceState(null, "", a.path);
  const src = a.source || {};
  const f = a.freshness;
  const nSources = mediaCount(a);
  main().innerHTML = `
  <div class="cols article">
    <div>
      <div class="row no-print" style="margin-bottom:12px"><button class="btn sm ghost" data-act="back">← Retour</button><span class="grow" style="flex:1"></span>
        <button class="btn sm" data-act="reader">${ico("reader")} Mode lecture épuré</button><button class="btn sm" data-act="print">${ico("print")} Imprimer / PDF</button></div>
      <div class="row" style="gap:6px 10px;margin-bottom:10px">${catBadge(a)}${mediaBadge(a.media_type)}${freshBadge(f)}${statusBadge(a.verification_status, a.verification_label)}${demoBadge(a)}</div>
      <h1>${esc(a.title)}</h1>
      <div class="meta" style="margin:10px 0 16px;font-size:.88rem"><strong>${esc(a.source_name)}</strong>${a.author ? `<span>par ${esc(a.author)}</span>` : ""}
        <span>${ico("clock")} Publié le ${fmtDate(a.published_at)} (${esc(f.age)})</span><span>· Collecté le ${fmtDate(a.first_seen_at)}</span><span>· ${a.reading_time} min de lecture</span></div>
      ${f.warning ? `<div class="alert-line ${f.recirculating ? "bad" : "warn"}" style="margin-bottom:12px">${ico("alert")}<span><b>Indicateur de fraîcheur :</b> ${esc(f.warning)}</span></div>` : ""}
      ${a.correction_note ? `<div class="alert-line ok" style="margin-bottom:12px">${ico("check")}<span><b>Correction :</b> ${esc(a.correction_note)}</span></div>` : ""}
      ${a.verification_status === "conteste" ? `<div class="alert-line bad" style="margin-bottom:12px">${ico("alert")}<span><b>${esc(a.verification_label)} :</b> d'autres médias rapportent une version différente. Consultez l'onglet « Recoupement ».</span></div>` : ""}
      ${a.media_type === "podcast" && a.media_url ? `<button class="btn primary" data-act="play" data-id="${a.id}" style="margin-bottom:14px">${ico("play")} Écouter le podcast</button>` : ""}
      <div class="hero-frame">${picture(a, true)}</div>
      <div class="content" id="articleContent">${a.paragraphs.map((p) => `<p>${esc(p)}</p>`).join("")}</div>
      <div class="row no-print" style="margin:6px 0 22px">
        ${safeUrl(a.url) ? `<a class="btn primary" href="${esc(safeUrl(a.url))}" target="_blank" rel="noopener">${ico("ext")} Lire l'article original sur ${esc(a.source_name)}</a>` : `<span class="badge b-demo">Contenu de démonstration : pas de lien externe</span>`}
        <button class="btn" data-act="fav" data-id="${a.id}">${ico("star")} ${S.favs.has(a.id) ? "Retirer des favoris" : "Ajouter aux favoris"}</button>
        <button class="btn" data-act="share" data-id="${a.id}">${ico("share")} Partager</button>
        <button class="btn danger" data-act="report" data-id="${a.id}">${ico("flag")} Signaler une erreur</button>
      </div>
      <div class="panel no-print">
        <div class="tabs" id="toolTabs">
          ${[["summary", "ai", "Résumé automatique"], ["verify", "shield", "Recoupement"], ["translate", "globe", "Traduction"], ["simplify", "text", "Simplification"], ["why", "help", "Pourquoi cet article ?"]].map(([k, i, l], n) => `<button class="tab ${n === 0 ? "active" : ""}" data-act="tool" data-tool="${k}">${ico(i)}${l}</button>`).join("")}
          ${a.others.length ? `<a class="tab" href="/sujet/${a.cluster_id}">${ico("columns")}Comparer les ${a.others.length + 1} articles</a>` : ""}
        </div>
        <div id="toolBody"></div>
      </div>
    </div>
    <aside class="tools-col stack">
      <div class="panel">
        <h3>${ico("db")} La source</h3>
        <dl class="facts"><dt>Média</dt><dd><b>${esc(src.name)}</b></dd><dt>Type</dt><dd>${esc(src.kind)}</dd><dt>Pays</dt><dd>${esc(src.country || "Non renseigné")}</dd><dt>Langue</dt><dd>${esc((src.language || "").toUpperCase())}</dd><dt>Publié</dt><dd>${fmtDate(a.published_at)}</dd><dt>Collecté</dt><dd>${fmtDate(a.first_seen_at)}</dd></dl>
        ${relBadge(src.reliability, src.certified, src.is_demo)}${src.is_demo ? `<div class="small muted" style="margin-top:8px">${esc(src.reliability_note || "")}</div>` : ""}
      </div>
      <div class="panel">
        <h3>${ico("layers")} Couverture</h3>
        <div style="margin-bottom:8px">${spectre(nSources)}</div>
        <div>${statusBadge(a.verification_status, a.verification_label)}</div>
        <p class="small muted" style="margin:10px 0 0">Ce statut décrit combien de médias en parlent, pas si le fait est vrai. <a href="/methode">Notre méthode</a></p>
        <div class="small" style="margin-top:10px">Tonalité : <b>${esc(a.tone.label)}</b><br>Lisibilité : <b>${a.readability.score}/100</b> (${esc(a.readability.level)})</div>
      </div>
      ${a.others.length ? `<div class="panel"><h3>${ico("layers")} Même sujet ailleurs</h3>${a.others.map((o) => `<div style="margin-bottom:10px"><a href="/article/${o.id}">${esc(o.title)}</a><div class="small muted">${esc(o.source_name)} · ${when(o.published_at)}</div></div>`).join("")}<a class="btn sm" href="/sujet/${a.cluster_id}">${ico("columns")} Comparer les traitements</a></div>` : ""}
      <div class="panel"><h3>${ico("hash")} Mots-clés</h3><div class="chips">${a.keywords.map((k) => `<a class="chip" href="/recherche?q=${encodeURIComponent(k)}">${esc(k)}</a>`).join("")}</div></div>
      ${a.reports.length ? `<div class="panel"><h3>${ico("flag")} Signalements (${a.reports.length})</h3>${a.reports.map((r) => `<div class="small" style="margin-bottom:8px">${reportStatus(r.status)} ${esc(REASONS[r.reason])}${r.admin_response ? `<div class="muted">${esc(r.admin_response)}</div>` : ""}</div>`).join("")}</div>` : ""}
    </aside>
  </div>`;
  S.currentArticle = a;
  tool("summary");
}

async function tool(name) {
  const a = S.currentArticle;
  $$("#toolTabs [data-tool]").forEach((b) => b.classList.toggle("active", b.dataset.tool === name));
  const box = $("#toolBody");
  box.innerHTML = `<div class="muted">${ico("ai")} Analyse en cours…</div>`;
  try {
    if (name === "summary") {
      const s = await get(`/api/articles/${a.id}/summary`);
      box.innerHTML = s.sentences.length ? `
        <div class="row between" style="margin-bottom:8px"><h3 style="margin:0">Résumé généré automatiquement</h3><span class="badge b-info">${ico("ai")} Extraction automatique</span></div>
        <ol class="sum-list">${s.sentences.map((x) => `<li>${esc(x.text)}<button class="cite" data-act="cite" data-n="${x.cite}" title="Voir la source">${x.cite}</button></li>`).join("")}</ol>
        <hr class="sep"><b class="small">Sources citées</b>
        <ol class="small" id="citeList">${s.sources.map((r) => `<li id="cite-${r.n}"><b>${esc(r.source)}</b> — <a href="/article/${r.article_id}">${esc(r.title)}</a> (${fmtDate(r.published_at, false)})${safeUrl(r.url) ? ` · <a href="${esc(safeUrl(r.url))}" target="_blank" rel="noopener">original ${ico("ext")}</a>` : ""}</li>`).join("")}</ol>
        <div class="small muted">${ico("info")} ${esc(s.method)} Chaque phrase est copiée telle quelle depuis la source citée : le logiciel la choisit mais ne rédige rien. Une phrase extraite peut rester inexacte : consultez l'original.</div>` : empty("Texte trop court pour produire un résumé.");
    } else if (name === "verify") {
      renderClaims(box, a.claims, a);
    } else if (name === "translate") {
      const dst = a.language === "fr" ? "en" : "fr";
      box.innerHTML = `<div class="row" style="margin-bottom:12px"><span class="small muted">Langue d'origine : <b>${a.language.toUpperCase()}</b></span>
        <select class="input" id="trLang" style="width:auto">${[["fr", "Français"], ["en", "Anglais"], ["es", "Espagnol"], ["de", "Allemand"], ["ar", "Arabe"], ["pt", "Portugais"]].filter(([k]) => k !== a.language).map(([k, l]) => `<option value="${k}" ${k === dst ? "selected" : ""}>${l}</option>`).join("")}</select>
        <button class="btn primary sm" id="trGo">${ico("globe")} Traduire</button></div><div id="trOut"></div>`;
      const go = async () => {
        $("#trOut").innerHTML = `<div class="muted">Traduction en cours…</div>`;
        const t = await get(`/api/articles/${a.id}/translate?lang=${$("#trLang").value}`);
        $("#trOut").innerHTML = t.error ? `<div class="alert-line warn">${ico("alert")}${esc(t.error)}</div>` :
          `<h3>${esc(t.title)}</h3><p>${esc(t.body)}</p><div class="small muted">${ico("info")} Moteur : ${esc(t.engine)}${t.cached ? " (en cache)" : ""}. Traduction automatique : en cas de doute, référez-vous au texte original.</div>`;
      };
      $("#trGo").onclick = go;
      if (a.language !== "fr") go();
    } else if (name === "simplify") {
      const s = await get(`/api/articles/${a.id}/simplify`);
      let txt = esc(s.text);
      s.glossary.forEach((g) => { txt = txt.replace(new RegExp(esc(g.simple).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i"), (m) => `<span class="gloss" title="Terme d'origine : ${esc(g.term)}">${m}</span>`); });
      box.innerHTML = `
        <div class="diff" style="margin-bottom:14px">
          <div class="kpi"><span>Lisibilité du texte original</span><b>${s.original.score}/100</b><span>${esc(s.original.level)} · ${s.original.words_per_sentence} mots/phrase</span></div>
          <div class="kpi"><span>Lisibilité après simplification</span><b style="color:var(--ok)">${s.simplified.score}/100</b><span>${esc(s.simplified.level)} · ${s.simplified.words_per_sentence} mots/phrase</span></div>
        </div>
        <h3>Version simplifiée</h3><p style="font-size:1.1rem;line-height:1.8">${txt}</p>
        ${s.glossary.length ? `<b class="small">Mots expliqués (${s.glossary.length})</b><ul class="small">${s.glossary.map((g) => `<li><b>${esc(g.term)}</b> → ${esc(g.simple)}${g.definition ? ` — <span class="muted">${esc(g.definition)}</span>` : ""}</li>`).join("")}</ul>` : ""}
        <div class="small muted">${ico("info")} Méthode : découpage des phrases longues et remplacement lexical par un glossaire (base de données). Indice : formule de Kandel & Moles.</div>`;
    } else if (name === "why") {
      box.innerHTML = `<div class="why" style="background:none;padding:0">${whyHtml(a.why)}</div>
        <p class="small muted" style="margin-top:12px">${ico("info")} Transparence : Prisme n'utilise aucun critère caché. Le score combine six critères pondérés, et une part du fil est réservée à des sujets hors de vos habitudes. Vous pouvez modifier vos intérêts dans les <a href="/parametres">paramètres</a> ou effacer votre historique à tout moment.</p>`;
    }
  } catch (e) { box.innerHTML = `<div class="alert-line bad">${ico("alert")}${esc(e.message)}</div>`; }
}

const CLAIM_TYPES = { chiffre: "Donnée chiffrée", citation: "Citation", attribution: "Attribution", causalite: "Lien de causalité", absolu: "Formulation absolue", rumeur: "Formulation conditionnelle / rumeur" };
function renderClaims(box, claims, a) {
  box.innerHTML = `
    <div class="row between" style="margin-bottom:12px"><h3 style="margin:0">Passages proches chez d'autres médias</h3>${S.user && S.user.role === "admin" ? `<button class="btn sm" data-act="reverify" data-id="${a.id}">${ico("refresh")} Relancer l'analyse</button>` : ""}</div>
    <p class="small muted" style="margin-top:0">Le logiciel repère les phrases contenant des chiffres, citations ou attributions, puis cherche des formulations proches dans les autres médias suivis. Un passage proche indique une reprise, pas une preuve.</p>
    ${claims.length ? claims.map((c) => `
      <div class="claim">
        <div class="row between"><div class="chips">${c.claim_types.split(",").map((t) => `<span class="badge">${esc(CLAIM_TYPES[t] || t)}</span>`).join("")}</div>${statusBadge(c.status, c.status_label)}</div>
        <p style="margin:8px 0"><q>${esc(c.sentence)}</q></p>
        <div class="small">${esc(c.rationale)}</div>
        ${c.evidences.map((e) => `<div class="ev ${e.stance}"><b>${e.stance === "soutient" ? "Formulation proche" : e.stance === "contredit" ? "Version différente" : "Contexte"}</b> — <a href="/article/${e.article_id}">${esc(e.source_name)}</a> <span class="muted">(${fmtDate(e.published_at, false)}, similarité ${Math.round(e.similarity * 100)} %)</span><br>« ${esc(e.excerpt)} »</div>`).join("")}
      </div>`).join("") : empty("Aucune phrase de ce type dans le texte disponible : le flux fournit souvent un simple extrait.", "shield")}
    <div class="alert-line info small" style="margin-top:12px">${ico("info")}<span>Cet outil aide à comparer, il ne remplace pas le travail d'un journaliste vérificateur. Vous avez repéré une erreur ? <a href="#" data-act="report" data-id="${a.id}">Signalez-la</a>.</span></div>`;
}

async function pageCompare(cid) {
  if (!ssrShown()) main().innerHTML = skeleton(2);
  const c = await get(`/api/clusters/${cid}`);
  const s = c.summary;
  setTitle(`${c.cluster.label} : ce qu'en disent ${c.cluster.source_count} médias`);
  const tone = { "neutre / factuel": "", positif: "b-ok", négatif: "b-warn", alarmiste: "b-warn", sensationnaliste: "b-bad" };
  main().innerHTML = `
    <div class="page-head"><div><span class="kicker">Comparaison</span><h1>${esc(c.cluster.label)}</h1></div>
      <div class="row">${spectre(c.cluster.source_count)}<span class="small muted">${c.articles.length} articles</span></div></div>
    ${s && s.sentences.length ? `<div class="panel"><div class="row between"><h2 style="margin:0 0 10px">Résumé automatique</h2><span class="badge b-info">${ico("ai")} Extraction automatique</span></div><ol class="sum-list">${s.sentences.map((x) => `<li>${esc(x.text)} <span class="cite">${x.cite}</span></li>`).join("")}</ol>
      <div class="small muted">${s.sources.map((r) => `[${r.n}] ${esc(r.source)}`).join(" · ")}</div></div>` : ""}
    <div class="grid g2" style="margin-top:16px">
      <div class="panel"><h3>${ico("check")} Vocabulaire commun</h3>${c.common_keywords.length ? `<div class="chips">${c.common_keywords.map((k) => `<span class="chip">${esc(k)}</span>`).join("")}</div>` : `<span class="muted small">Peu de vocabulaire commun.</span>`}
        <p class="small muted" style="margin-bottom:0">Termes présents dans la majorité des articles.</p></div>
      <div class="panel"><h3>${ico("alert")} Divergences chiffrées</h3>${c.divergences.length ? c.divergences.map((d) => `<div class="small" style="margin-bottom:8px"><b>Unité « ${esc(d.unit)} »</b> : ${d.values.map((v) => `<span class="badge ${d.values.length > 1 ? "b-warn" : ""}">${esc(v.value)}</span> <span class="muted">(${esc(v.sources.join(", "))})</span>`).join(" — ")}</div>`).join("") : `<span class="muted small">Aucun écart de chiffres détecté dans les textes disponibles.</span>`}</div>
    </div>
    <h2 style="margin-top:22px">Traitement par média</h2>
    <div class="compare-grid">${c.articles.map((a) => `
      <div class="cmp-col">
        <div class="row between"><b>${esc(a.source)}</b>${relBadge(a.reliability, a.certified, a.is_demo)}</div>
        <a href="/article/${a.id}" style="font-weight:600">${esc(a.title)}</a>
        <div class="small muted">${a.rank === 1 ? "Premier à publier · " : `${a.rank}ᵉ à publier · `}${fmtDate(a.published_at)}</div>
        <div class="row" style="gap:6px">${a.verification_status === "conteste" ? statusBadge(a.verification_status, a.verification_label) : ""}<span class="badge ${tone[a.tone.label] || ""}">Ton : ${esc(a.tone.label)}</span></div>
        <div class="small">Longueur : <b>${a.word_count} mots</b> · Lisibilité : <b>${a.readability.score}/100</b></div>
        ${a.numbers.length ? `<div class="small">Chiffres cités : ${a.numbers.map((n) => `<span class="badge">${esc(n)}</span>`).join(" ")}</div>` : ""}
        ${a.unique_keywords.length ? `<div class="small">Angle spécifique : ${a.unique_keywords.map((k) => `<span class="chip">${esc(k)}</span>`).join(" ")}</div>` : ""}
        ${safeUrl(a.url) ? `<a class="small" href="${esc(safeUrl(a.url))}" target="_blank" rel="noopener">${ico("ext")} Lire l'original</a>` : ""}
      </div>`).join("")}</div>
    <div class="panel" style="margin-top:18px"><h3>${ico("clock")} Chronologie de publication</h3><div class="timeline">${c.articles.map((a) => `<div class="tl-item"><b>${fmtDate(a.published_at)}</b> — ${esc(a.source)} : <a href="/article/${a.id}">${esc(a.title)}</a></div>`).join("")}</div></div>`;
}

async function pageSearch(params) {
  const p = new URLSearchParams(params || "");
  const srcs = await get("/api/sources");
  main().innerHTML = `
    <div class="page-head"><div><h1>${ico("search")} Recherche avancée</h1><p class="lead">Par mots-clés, date, auteur, média, format ou niveau de couverture.</p></div></div>
    <form class="panel" id="searchForm">
      <div class="grid g4">
        <label class="f" style="grid-column:span 2"><span>Mots-clés</span><input class="input" name="q" value="${esc(p.get("q") || "")}" placeholder="ex. carburant, Union africaine…"></label>
        <label class="f"><span>Auteur</span><input class="input" name="author" value="${esc(p.get("author") || "")}"></label>
        <label class="f"><span>Source</span><select class="input" name="source"><option value="">Toutes</option>${srcs.map((s) => `<option value="${s.id}" ${p.get("source") == s.id ? "selected" : ""}>${esc(s.name)}</option>`).join("")}</select></label>
        <label class="f"><span>Du</span><input class="input" type="date" name="from" value="${esc(p.get("from") || "")}"></label>
        <label class="f"><span>Au</span><input class="input" type="date" name="to" value="${esc(p.get("to") || "")}"></label>
        <label class="f"><span>Rubrique</span><select class="input" name="category"><option value="">Toutes</option>${S.cats.map((c) => `<option value="${c.slug}" ${p.get("category") === c.slug ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></label>
        <label class="f"><span>Format</span><select class="input" name="media"><option value="">Tous</option>${Object.entries(MEDIA).map(([k, v]) => `<option value="${k}" ${p.get("media") === k ? "selected" : ""}>${v[1]}</option>`).join("")}</select></label>
        <label class="f"><span>Couverture</span><select class="input" name="status"><option value="">Toutes</option>${Object.entries(STATUS).map(([k, v]) => `<option value="${k}" ${p.get("status") === k ? "selected" : ""}>${v[2]}</option>`).join("")}</select></label>
        <label class="f"><span>Langue</span><select class="input" name="lang"><option value="">Toutes</option><option value="fr" ${p.get("lang") === "fr" ? "selected" : ""}>Français</option><option value="en" ${p.get("lang") === "en" ? "selected" : ""}>Anglais</option></select></label>
        <label class="f"><span>Trier par</span><select class="input" name="sort">${[["date", "Plus récent"], ["ancien", "Plus ancien"], ["verification", "Nombre de médias"]].map(([k, l]) => `<option value="${k}" ${p.get("sort") === k ? "selected" : ""}>${l}</option>`).join("")}</select></label>
        <label class="f" style="display:flex;align-items:center;gap:8px;margin-top:26px"><input type="checkbox" name="dedup" value="1" ${p.get("dedup") === "1" ? "checked" : ""}> Masquer les doublons</label>
      </div>
      <div class="row"><button class="btn primary">${ico("search")} Rechercher</button><a class="btn ghost" href="/recherche">Réinitialiser</a></div>
    </form>
    <div id="results" style="margin-top:18px"></div>`;
  $("#searchForm").onsubmit = (e) => {
    e.preventDefault();
    const fd = new URLSearchParams([...new FormData(e.target)].filter(([, v]) => v));
    nav("/recherche?" + fd);
  };
  if ([...p.keys()].length) {
    $("#results").innerHTML = skeleton(3);
    const r = await get("/api/search?" + p);
    $("#results").innerHTML = `<div class="muted" style="margin-bottom:10px">${r.total} résultat(s)</div>` + cards(r.items);
  }
}

async function pageTrends() {
  main().innerHTML = skeleton(3);
  const t = await get("/api/trends");
  main().innerHTML = `
    <div class="page-head"><div><h1>${ico("trend")} Tendances du moment</h1><p class="lead">Sujets les plus repris par des médias distincts et mots-clés dominants des dernières 48 heures — idéal pour la veille et le community management.</p></div></div>
    <div class="cols">
      <div class="stack">
        <h2>Sujets les plus couverts</h2>
        ${t.topics.map((c, i) => `<div class="panel row" style="gap:16px;align-items:flex-start"><div style="font-family:var(--serif);font-size:1.8rem;color:var(--accent);width:34px">${i + 1}</div>
          <div style="flex:1"><a href="/article/${c.article_id}" style="font-weight:700;font-size:1.05rem;color:var(--text)">${esc(c.title)}</a>
          <div class="meta" style="margin-top:6px"><span class="kicker">${esc(c.category_name || "Actualité")}</span>${spectre(c.source_count)}<span>${c.size} article(s)</span>${when(c.last_published)}</div></div>
          <div class="row">${c.size > 1 ? `<a class="btn sm" href="/sujet/${c.id}">${ico("columns")} Comparer</a>` : ""}<button class="btn sm" data-act="post" data-id="${c.article_id}">${ico("hash")} Créer un post</button></div></div>`).join("") || empty("Aucune tendance pour le moment.")}
      </div>
      <aside class="stack">
        <div class="panel"><h3>${ico("hash")} Mots-clés et hashtags</h3><p class="small muted">Classés selon le nombre de médias différents qui les emploient.</p>
          <div class="cloud">${t.keywords.map((k) => `<button data-act="copytag" data-tag="${esc(k.hashtag)}" title="Copier ${esc(k.hashtag)}" style="font-size:${0.8 + Math.min(k.sources, 6) * 0.07}rem">${esc(k.hashtag)}<small>${k.sources}</small></button>`).join("")}</div></div>
        <div class="panel"><h3>${ico("chart")} Médias par mot-clé</h3>${t.keywords.slice(0, 8).map((k) => `<div class="hbar"><span>${esc(k.word)}</span><span class="track"><i style="width:${(k.sources / Math.max(...t.keywords.map((x) => x.sources))) * 100}%"></i></span><span class="v">${k.sources}</span></div>`).join("")}</div>
      </aside>
    </div>`;
}

async function pageDigest() {
  main().innerHTML = skeleton(3);
  const d = await get("/api/digest");
  const today = new Date().toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const mail = `mailto:?subject=${encodeURIComponent("Digest Prisme — " + today)}&body=${encodeURIComponent(d.items.map((x, i) => `${i + 1}. ${x.article.title} (${x.article.source_name})\n${x.summary.sentences.map((s) => "   - " + s.text).join("\n")}`).join("\n\n"))}`;
  main().innerHTML = `
    <div class="page-head"><div><h1>${ico("digest")} Digest du ${esc(today)}</h1><p class="lead">L'essentiel de l'actualité en quelques minutes : les sujets les plus couverts, résumés à partir de plusieurs sources, sans les contenus signalés en désaccord.</p></div>
      <div class="row no-print"><button class="btn" data-act="print">${ico("print")} Exporter en PDF</button><a class="btn primary" href="${mail}">${ico("share")} Envoyer par e-mail</a></div></div>
    <div class="stack">${d.items.map((x, i) => `
      <div class="panel">
        <div class="row" style="gap:6px;margin-bottom:6px"><b style="color:var(--accent);font-family:var(--serif)">${i + 1}.</b>${catBadge(x.article)}${spectre(x.source_count)}${demoBadge(x.article)}</div>
        <h2 style="margin-bottom:6px"><a href="/article/${x.article.id}" style="color:var(--text)">${esc(x.article.title)}</a></h2>
        <ul class="sum-list">${x.summary.sentences.map((s) => `<li>${esc(s.text)} <span class="cite">${s.cite}</span></li>`).join("")}</ul>
        <div class="small muted">${x.summary.sources.map((r) => `[${r.n}] ${esc(r.source)}`).join(" · ")} — ${when(x.article.published_at)}</div>
      </div>`).join("") || empty("Pas encore assez de contenus pour générer le digest.")}</div>
    <p class="small muted">Généré automatiquement le ${fmtDate(d.generated_at)} (UTC).</p>`;
}

let mmTab = "podcast";
async function pageMultimedia() {
  main().innerHTML = `
    <div class="page-head"><div><h1>${ico("headphones")} Espace multimédia</h1><p class="lead">Podcasts, vidéos et contenus issus des réseaux sociaux. Le lecteur audio continue de jouer pendant la navigation (mode arrière-plan).</p></div></div>
    <section class="intro-video" aria-labelledby="introTitle">
      <video id="introVideo" controls preload="none" poster="/video/prisme-30s.jpg" playsinline><source src="/video/prisme-30s.mp4" type="video/mp4"></video>
      <div><span class="kicker">Vidéo de présentation</span><h2 id="introTitle">Prisme en 30 secondes</h2>
        <p class="small muted">Une visite du site : la une, le spectre, la comparaison entre médias et notre méthode. Vidéo sans son, avec le texte à l'écran. Il s'agit d'une capture du site, pas d'un reportage.</p></div>
    </section>
    <div class="tabs">${[["podcast", "headphones", "Podcasts"], ["video", "video", "Vidéos"], ["social", "social", "Réseaux sociaux"]].map(([k, i, l]) => `<button class="tab ${mmTab === k ? "active" : ""}" data-act="mmtab" data-tab="${k}">${ico(i)}${l}</button>`).join("")}</div>
    <div id="mmList">${skeleton(3)}</div>`;
  const r = await get(`/api/feed?mode=recent&media=${mmTab}&limit=60`);
  $("#mmList").innerHTML = cards(r.items);
}

async function pageVeille() {
  if (!S.user) return needLogin("la veille et les alertes");
  const [alerts, favs] = await Promise.all([get("/api/alerts"), get("/api/favorites")]);
  main().innerHTML = `
    <div class="page-head"><div><h1>${ico("eye")} Veille & alertes</h1><p class="lead">Suivez des mots-clés : à chaque collecte, Prisme vous notifie des nouveaux articles correspondants. Organisez vos lectures dans des dossiers de veille.</p></div></div>
    <div class="grid g2">
      <div class="panel">
        <h2>${ico("bell")} Alertes par mots-clés</h2>
        <form class="row" id="alertForm"><input class="input" name="keyword" placeholder="Nouveau mot-clé (ex. élection, cacao, IA…)" style="flex:1" required><button class="btn primary">${ico("plus")} Ajouter</button></form>
        <div style="margin-top:12px">${alerts.map((al) => `<div class="switch"><div><b>${esc(al.keyword)}</b><div class="small muted">${al.hits} article(s) détecté(s)</div></div>
          <div class="row"><a class="btn sm" href="/recherche?q=${encodeURIComponent(al.keyword)}">${ico("search")}</a><label class="small row" style="gap:4px"><input type="checkbox" data-act="alerttoggle" data-id="${al.id}" ${al.active ? "checked" : ""}> active</label><button class="btn sm danger" data-act="alertdel" data-id="${al.id}">${ico("trash")}</button></div></div>`).join("") || `<p class="muted">Aucune alerte configurée.</p>`}</div>
      </div>
      <div class="panel">
        <h2>${ico("folder")} Dossiers de veille</h2>
        <form class="row" id="folderForm"><input class="input" name="name" placeholder="Nom du dossier" style="flex:1" required><input type="color" name="color" value="#0ea5e9" style="width:44px;height:42px;border:0;background:none"><button class="btn primary">${ico("plus")} Créer</button></form>
        <div style="margin-top:12px">${favs.folders.map((f) => `<div class="switch"><div class="row"><span style="width:12px;height:12px;border-radius:4px;background:${esc(f.color)}"></span><b>${esc(f.name)}</b><span class="muted small">${f.n} article(s)</span></div>
          <div class="row"><a class="btn sm" href="/favoris?folder=${f.id}">Ouvrir</a><a class="btn sm" href="/api/export?format=txt&folder=${f.id}" data-act="download">${ico("download")} TXT</a><button class="btn sm danger" data-act="folderdel" data-id="${f.id}">${ico("trash")}</button></div></div>`).join("") || `<p class="muted">Aucun dossier.</p>`}</div>
      </div>
    </div>`;
  $("#alertForm").onsubmit = async (e) => { e.preventDefault(); const r = await post("/api/alerts", { keyword: e.target.keyword.value }); toast(`Alerte ajoutée${r.created_notifications ? ` — ${r.created_notifications} nouvelle(s) notification(s)` : ""}.`); refreshMe(); pageVeille(); };
  $("#folderForm").onsubmit = async (e) => { e.preventDefault(); try { await post("/api/folders", { name: e.target.name.value, color: e.target.color.value }); toast("Dossier créé."); pageVeille(); } catch (err) { toast(err.message, 1); } };
}

async function pageFavorites(params) {
  if (!S.user) return needLogin("les favoris");
  const p = new URLSearchParams(params || "");
  const folder = p.get("folder");
  const r = await get("/api/favorites");
  const items = folder ? r.items.filter((a) => String(a.folder_id) === folder) : r.items;
  main().innerHTML = `
    <div class="page-head"><div><h1>${ico("star")} Mes favoris</h1><p class="lead">Articles enregistrés pour une lecture ultérieure. </p></div>
      <div class="row"><a class="btn" href="/api/export?format=txt" data-act="download">${ico("download")} TXT</a><a class="btn" href="/api/export?format=csv" data-act="download">${ico("download")} CSV</a><a class="btn" href="/api/export?format=bib" data-act="download">${ico("book")} Bibliographie (BibTeX)</a></div></div>
    <div class="chips" style="margin-bottom:16px"><a class="chip ${!folder ? "active" : ""}" href="/favoris">Tous (${r.items.length})</a>${r.folders.map((f) => `<a class="chip ${folder == f.id ? "active" : ""}" href="/favoris?folder=${f.id}">${esc(f.name)} (${f.n})</a>`).join("")}</div>
    ${items.length ? cards(items) : empty("Aucun favori. Cliquez sur l'étoile d'un article pour l'enregistrer.", "star")}`;
}

async function pageNotifications() {
  if (!S.user) return needLogin("les notifications");
  const n = await get("/api/notifications");
  const KIND = { alerte: ["bell", "Alerte"], signalement: ["flag", "Signalement"], systeme: ["info", "Système"], digest: ["digest", "Digest"] };
  main().innerHTML = `
    <div class="page-head"><div><h1>${ico("bell")} Notifications</h1><p class="lead">Alertes personnalisées par mots-clés, suivi de vos signalements et messages de la plateforme.</p></div>
      <div class="row"><button class="btn" data-act="pushperm">${ico("bell")} Activer les notifications du navigateur</button><button class="btn primary" data-act="readall">${ico("check")} Tout marquer comme lu</button></div></div>
    <div class="panel" style="padding:6px 18px">${n.map((x) => `<div class="switch" style="${x.is_read ? "opacity:.65" : ""}">
      <div class="row" style="flex-wrap:nowrap;align-items:flex-start"><span class="badge ${x.is_read ? "" : "b-info"}">${ico(KIND[x.kind][0])}${KIND[x.kind][1]}</span>
      <div>${x.article_id ? `<a href="/article/${x.article_id}" data-act="readone" data-id="${x.id}">${esc(x.message)}</a>` : esc(x.message)}<div class="small muted">${fmtDate(x.created_at)}</div></div></div>
      ${x.is_read ? "" : `<button class="btn sm" data-act="readone" data-id="${x.id}">Lu</button>`}</div>`).join("") || empty("Aucune notification.", "bell")}</div>`;
}

const REASONS = { factuelle: "Erreur factuelle", date: "Date erronée / info ancienne", source: "Source douteuse", titre_trompeur: "Titre trompeur", traduction: "Erreur de traduction", doublon: "Doublon non détecté", autre: "Autre" };
const RSTAT = { en_attente: ["b-warn", "En attente"], en_cours: ["b-info", "En cours d'examen"], corrige: ["b-ok", "Corrigé"], rejete: ["", "Clôturé"] };
const reportStatus = (s) => `<span class="badge ${RSTAT[s][0]}">${RSTAT[s][1]}</span>`;

async function pageReports(params) {
  if (!S.user) return needLogin("le suivi des signalements");
  const admin = S.user.role === "admin";
  const all = admin && new URLSearchParams(params || "").get("all") !== "0";
  const list = await get("/api/reports" + (all ? "?all=1" : ""));
  main().innerHTML = `
    <div class="page-head"><div><h1>${ico("flag")} ${all ? "Modération des signalements" : "Mes signalements"}</h1><p class="lead">Les lecteurs signalent les informations incorrectes ; l'équipe de modération les examine et publie une correction visible sur l'article.</p></div>
      ${admin ? `<div class="tabs"><a class="tab ${all ? "active" : ""}" href="/signalements">File de modération</a><a class="tab ${!all ? "active" : ""}" href="/signalements?all=0">Mes signalements</a></div>` : ""}</div>
    <div class="stack">${list.map((r) => `
      <div class="panel">
        <div class="row between"><div class="row">${reportStatus(r.status)}<span class="badge">${esc(REASONS[r.reason])}</span><span class="small muted">${fmtDate(r.created_at)}${r.reporter ? " · par " + esc(r.reporter) : ""}</span></div></div>
        <h3 style="margin-top:10px"><a href="/article/${r.article_id}">${esc(r.article_title)}</a> <span class="small muted">— ${esc(r.source_name)}</span></h3>
        <p style="margin:6px 0">${esc(r.description)}</p>${safeUrl(r.evidence_url) ? `<a class="small" href="${esc(safeUrl(r.evidence_url))}" target="_blank" rel="noopener">${ico("ext")} Preuve fournie</a>` : ""}
        ${r.admin_response ? `<div class="alert-line info small" style="margin-top:8px">${ico("info")}<span><b>Réponse de la modération :</b> ${esc(r.admin_response)}</span></div>` : ""}
        ${all ? `<form class="grid g3 mod" data-id="${r.id}" style="margin-top:12px;align-items:end">
          <label class="f"><span>Statut</span><select class="input" name="status">${Object.entries(RSTAT).map(([k, v]) => `<option value="${k}" ${r.status === k ? "selected" : ""}>${v[1]}</option>`).join("")}</select></label>
          <label class="f"><span>Réponse au lecteur</span><input class="input" name="admin_response" value="${esc(r.admin_response || "")}"></label>
          <label class="f"><span>Note de correction (si corrigé)</span><input class="input" name="correction_note" placeholder="Affichée sur l'article"></label>
          <button class="btn primary">${ico("check")} Enregistrer</button></form>` : ""}
      </div>`).join("") || empty("Aucun signalement.", "flag")}</div>`;
  $$("form.mod").forEach((f) => f.onsubmit = async (e) => {
    e.preventDefault();
    await put(`/api/reports/${f.dataset.id}`, Object.fromEntries(new FormData(f)));
    toast("Signalement mis à jour, le lecteur a été notifié.");
    pageReports(params);
  });
}

async function pageSources() {
  const list = await get("/api/sources");
  const admin = S.user && S.user.role === "admin";
  main().innerHTML = `
    <div class="page-head"><div><h1>Les médias suivis</h1><p class="lead">Prisme lit les flux RSS publics de ces médias et renvoie toujours vers l'article original. Il ne note pas les médias.</p></div>
      ${admin ? `<button class="btn primary" data-act="addsource">${ico("plus")} Ajouter un flux RSS</button>` : ""}</div>
    <div class="panel table-wrap" style="padding:0"><table class="t">
      <thead><tr><th>Média</th><th>Type</th><th>Pays</th><th>Langue</th><th>Contenus</th><th>Dernière collecte</th>${admin ? "<th>Administration</th>" : ""}</tr></thead>
      <tbody>${list.map((s) => `<tr style="${s.active ? "" : "opacity:.5"}">
        <td><b>${esc(s.name)}</b> ${s.is_demo ? `<span class="badge b-demo">Démo</span> ${relBadge(s.reliability, s.certified, 1)}` : ""}<div class="small muted">${safeUrl(s.website) ? `<a href="${esc(safeUrl(s.website))}" target="_blank" rel="noopener">${esc(s.website)}</a>` : esc(s.reliability_note || "")}</div></td>
        <td>${esc(s.kind)}</td><td>${esc(s.country || "")}</td><td>${esc(s.language.toUpperCase())}</td>
        <td>${s.articles}</td>
        <td class="small">${s.feed_url ? (s.last_fetched_at ? fmtDate(s.last_fetched_at) : "jamais") : "—"}${s.last_error ? `<div class="small" style="color:var(--bad)" title="${esc(s.last_error)}">échec de collecte</div>` : ""}</td>
        ${admin ? `<td><div class="row"><label class="small row" style="gap:4px"><input type="checkbox" data-act="srcactive" data-id="${s.id}" ${s.active ? "checked" : ""}>active</label>${!s.is_demo ? `<button class="btn sm danger" data-act="srcdel" data-id="${s.id}" aria-label="Supprimer ${esc(s.name)}">${ico("trash")}</button>` : ""}</div></td>` : ""}
      </tr>`).join("")}</tbody></table></div>`;
}

function pageMethod() {
  main().innerHTML = `
    <div style="max-width:760px">
      <span class="kicker">Transparence</span><h1>Notre méthode</h1>
      <p class="lead">Prisme mesure comment plusieurs médias couvrent un même événement. Il ne dit pas si un fait est vrai.</p>
      <h2>Ce que signifient les statuts</h2>
      <dl class="facts" style="grid-template-columns:minmax(120px,190px) 1fr;gap:10px 16px;font-size:.95rem;margin-bottom:22px">
        <dt><b>Source unique</b></dt><dd>Un seul média suivi par Prisme en parle pour l'instant. Cela ne veut pas dire que l'information est fausse.</dd>
        <dt><b>Repris par N sources</b></dt><dd>N médias distincts publient sur le même événement. Ils peuvent tous reprendre une même dépêche : ce n'est donc pas une preuve.</dd>
        <dt><b>Chiffres divergents</b></dt><dd>Des médias donnent des chiffres différents pour une même donnée. Un bilan peut aussi simplement évoluer dans le temps.</dd>
        <dt><b>Démenti signalé</b></dt><dd>Un média suivi emploie un vocabulaire de démenti sur ce sujet. Lisez les sources pour juger.</dd>
      </dl>
      <h2>Comment les articles sont regroupés</h2>
      <p>Le logiciel compare les titres et les extraits (similarité statistique), sur quelques jours et dans une même langue. Il peut se tromper : réunir deux sujets voisins, ou manquer un même événement traité en français et en anglais.</p>
      <h2>Résumés automatiques</h2>
      <p>Les résumés sont produits par extraction : chaque phrase est copiée telle quelle depuis un article cité, avec son lien. Aucun texte n'est rédigé par un modèle de langage, aucune citation ni statistique n'est créée. Une phrase extraite reste à lire dans son contexte, sur le site d'origine.</p>
      <h2>Ce que Prisme conserve</h2>
      <p>Pour chaque article : le média d'origine, le lien, la date de publication déclarée et la date de collecte. Les corrections publiées et les changements de statut sont journalisés.</p>
      <h2>Rappels de la rédaction</h2>
      <p>Une rubrique peut afficher un court rappel écrit à la main, signalé comme tel. Il contient uniquement des faits vérifiés sur les pages citées, et disparaît à une date fixée.</p>
      <h2>Une erreur ?</h2>
      <p>Chaque article propose un bouton « Signaler une erreur ». Les signalements sont examinés et les corrections apparaissent sur la page concernée.</p>
    </div>`;
}

async function pageAdmin() {
  if (!S.user || S.user.role !== "admin") return needLogin("l'administration (compte administrateur)");
  const [st, users, changes] = await Promise.all([get("/api/stats"), get("/api/admin/users"), get("/api/admin/changes")]);
  const max = (arr) => Math.max(1, ...arr.map((x) => x.n));
  const ST_COL = { verifie: "var(--ok)", partiel: "var(--info)", non_verifie: "var(--warn)", conteste: "var(--bad)", en_attente: "var(--muted)" };
  main().innerHTML = `
    <div class="page-head"><div><h1>${ico("chart")} Tableau de bord d'administration</h1><p class="lead">Supervision de la collecte, de la détection des doublons, de la vérification et de la modération.</p></div>
      <div class="row"><button class="btn primary" data-act="refresh">${ico("refresh")} Collecter les flux RSS</button><button class="btn" data-act="recluster">${ico("layers")} Recalculer doublons & vérifications</button></div></div>
    <div class="grid g4">
      <div class="kpi"><span>Contenus agrégés</span><b>${st.articles}</b><span>${st.real_sources} médias réels actifs</span></div>
      <div class="kpi"><span>Doublons regroupés</span><b>${st.duplicates}</b><span>${st.dedup_rate} % du volume · ${st.multi_source_topics} sujets multi-sources</span></div>
      <div class="kpi"><span>Phrases analysées</span><b>${st.claims}</b><span>${st.evidences} passages rapprochés</span></div>
      <div class="kpi"><span>Signalements ouverts</span><b>${st.reports_open}</b><span>sur ${st.reports_total} au total · <a href="/signalements">modérer</a></span></div>
    </div>
    <div class="grid g3" style="margin-top:16px">
      <div class="panel"><h3>Couverture</h3>${st.verification.map((v) => `<div class="hbar"><span>${STATUS[v.status][2]}</span><span class="track"><i style="width:${v.n / max(st.verification) * 100}%;background:${ST_COL[v.status]}"></i></span><span class="v">${v.n}</span></div>`).join("")}</div>
      <div class="panel"><h3>Contenus par rubrique</h3>${st.by_category.map((v) => `<div class="hbar"><span>${esc(v.name)}</span><span class="track"><i style="width:${v.n / max(st.by_category) * 100}%"></i></span><span class="v">${v.n}</span></div>`).join("")}</div>
      <div class="panel"><h3>Contenus par source (top 12)</h3>${st.by_source.map((v) => `<div class="hbar"><span class="small" title="${esc(v.name)}" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(v.name)}</span><span class="track"><i style="width:${v.n / max(st.by_source) * 100}%"></i></span><span class="v">${v.n}</span></div>`).join("")}</div>
    </div>
    <div class="panel" style="margin-top:16px"><h3>${ico("refresh")} Dernière collecte</h3>${st.last_fetch ? `<p class="small">${fmtDate(st.last_fetch.finished_at)} — ${st.last_fetch.sources_ok} source(s) OK, ${st.last_fetch.sources_ko} en échec, <b>${st.last_fetch.new_articles}</b> nouveau(x) contenu(s), ${esc(st.last_fetch.message || "")}.</p>` : `<p class="small muted">Aucune collecte terminée (connexion Internet requise).</p>`}${st.fetching ? `<span class="badge b-info">Collecte en cours…</span>` : ""}</div>
    <div class="panel table-wrap" style="margin-top:16px"><h3>${ico("clock")} Journal des modifications</h3>${changes.length ? `<table class="t"><thead><tr><th>Date</th><th>Auteur</th><th>Objet</th><th>Action</th><th>Détail</th></tr></thead><tbody>${changes.slice(0, 20).map((c) => `<tr><td class="small">${fmtDate(c.at)}</td><td>${esc(c.actor)}</td><td>${esc(c.entity)} ${c.entity_id ?? ""}</td><td>${esc(c.action)}</td><td class="small">${esc(c.detail || "")}</td></tr>`).join("")}</tbody></table>` : `<p class="small muted">Aucune modification enregistrée.</p>`}</div>
    <div class="panel table-wrap" style="margin-top:16px"><h3>${ico("users")} Utilisateurs (${users.length})</h3><table class="t"><thead><tr><th>Nom</th><th>Identifiant</th><th>Rôle</th><th>Profil</th><th>Lectures</th><th>Favoris</th><th>Signalements</th><th>Inscription</th></tr></thead>
      <tbody>${users.map((u) => `<tr><td><b>${esc(u.display_name)}</b><div class="small muted">${esc(u.email)}</div></td><td>${esc(u.username)}</td><td>${u.role === "admin" ? `<span class="badge b-info">admin</span>` : "utilisateur"}</td><td class="small">${esc(u.persona || "—")}</td><td>${u.lectures}</td><td>${u.favoris}</td><td>${u.signalements}</td><td class="small">${fmtDate(u.created_at, false)}</td></tr>`).join("")}</tbody></table></div>`;
}

async function pageSettings() {
  const u = S.user;
  const p = u || store.get("prisme_prefs", { font_scale: 1, high_contrast: 0, theme: "auto", simple_mode: 0 });
  const ints = u ? await get("/api/interests") : [];
  main().innerHTML = `
    <div class="page-head"><div><h1>${ico("gear")} Paramètres & accessibilité</h1><p class="lead">Adaptez l'affichage à vos besoins et contrôlez la personnalisation de votre fil.</p></div></div>
    <div class="grid g2">
      <div class="panel">
        <h2>${ico("eye")} Accessibilité et confort de lecture</h2>
        <label class="f"><span>Taille du texte : <b id="fsv">${Math.round(p.font_scale * 100)} %</b></span><input type="range" id="fs" min="0.85" max="1.6" step="0.05" value="${p.font_scale}"></label>
        <div class="switch"><div><b>Thème</b><div class="small muted">Clair, sombre ou selon le système</div></div><select class="input" id="theme" aria-label="Thème" style="width:auto">${[["auto", "Automatique"], ["light", "Clair"], ["dark", "Sombre"]].map(([k, l]) => `<option value="${k}" ${p.theme === k ? "selected" : ""}>${l}</option>`).join("")}</select></div>
        <div class="switch"><div><b>Contraste élevé</b><div class="small muted">Pour les personnes malvoyantes</div></div><input type="checkbox" id="hc" aria-label="Contraste élevé" ${p.high_contrast ? "checked" : ""}></div>
        <div class="switch"><div><b>Mode simplifié</b><div class="small muted">Grands boutons et libellés toujours visibles</div></div><input type="checkbox" id="sm" aria-label="Mode simplifié" ${p.simple_mode ? "checked" : ""}></div>
        <button class="btn primary" id="saveA" style="margin-top:10px">${ico("check")} Enregistrer</button>
      </div>
      ${u ? `<div class="panel">
        <h2>${ico("ai")} Personnalisation du fil</h2>
        <p class="small muted">Poids de chaque rubrique dans vos recommandations (0 = non suivie).</p>
        ${ints.map((c) => `<div class="hbar"><span>${esc(c.name)}</span><input type="range" min="0" max="1" step="0.1" value="${c.weight}" data-cat="${c.id}" class="intr"><span class="v" id="iv-${c.id}">${Math.round(c.weight * 100)}</span></div>`).join("")}
        <hr class="sep">
        <label class="f"><span>Part du fil réservée à la découverte (anti-bulle de filtres) : <b id="drv">${Math.round(u.diversity_ratio * 100)} %</b></span><input type="range" id="dr" min="0" max="0.5" step="0.05" value="${u.diversity_ratio}"></label>
        <div class="row"><button class="btn primary" id="saveP">${ico("check")} Enregistrer</button><button class="btn danger" id="clearH">${ico("trash")} Effacer mon historique de lecture</button></div>
      </div>
      <div class="panel">
        <h2>${ico("user")} Mon compte</h2>
        <form id="accForm"><label class="f"><span>Nom affiché</span><input class="input" name="display_name" value="${esc(u.display_name)}"></label>
        <label class="f"><span>E-mail</span><input class="input" type="email" name="email" value="${esc(u.email)}"></label>
        <label class="f"><span>Mot de passe actuel (requis pour en changer)</span><input class="input" type="password" name="current_password" autocomplete="current-password"></label>
        <label class="f"><span>Nouveau mot de passe, 8 caractères minimum (facultatif)</span><input class="input" type="password" name="new_password" minlength="8" autocomplete="new-password"></label>
        <button class="btn primary">${ico("check")} Mettre à jour</button></form>
      </div>` : `<div class="panel"><h2>Personnalisation</h2><p class="muted">Connectez-vous pour choisir vos centres d'intérêt, vos alertes et la part de découverte de votre fil. En mode invité, les préférences d'affichage sont mémorisées dans ce navigateur.</p><a class="btn primary" href="/connexion">Se connecter</a></div>`}
    </div>`;
  $("#fs").oninput = (e) => { $("#fsv").textContent = Math.round(e.target.value * 100) + " %"; document.documentElement.style.setProperty("--fs", e.target.value); };
  $("#saveA").onclick = async () => {
    const prefs = { font_scale: +$("#fs").value, theme: $("#theme").value, high_contrast: $("#hc").checked ? 1 : 0, simple_mode: $("#sm").checked ? 1 : 0 };
    if (u) { const r = await put("/api/me", prefs); S.user = r.user; } else store.set("prisme_prefs", prefs);
    applyPrefs(); toast("Préférences d'affichage enregistrées.");
  };
  if (!u) return;
  $$(".intr").forEach((r) => r.oninput = () => { $("#iv-" + r.dataset.cat).textContent = Math.round(r.value * 100); });
  $("#dr").oninput = (e) => { $("#drv").textContent = Math.round(e.target.value * 100) + " %"; };
  $("#saveP").onclick = async () => {
    const weights = {}; $$(".intr").forEach((r) => weights[r.dataset.cat] = +r.value);
    await put("/api/interests", { weights });
    const r = await put("/api/me", { diversity_ratio: +$("#dr").value }); S.user = r.user;
    toast("Personnalisation enregistrée : votre fil a été recalculé.");
  };
  $("#clearH").onclick = async () => { if (confirm("Effacer tout votre historique de lecture ?")) { await del("/api/history"); toast("Historique effacé."); } };
  $("#accForm").onsubmit = async (e) => { e.preventDefault(); try { const r = await put("/api/me", Object.fromEntries(new FormData(e.target))); S.user = r.user; renderNav(); e.target.current_password.value = ""; e.target.new_password.value = ""; toast("Compte mis à jour."); } catch (err) { toast(err.message, 1); } };
}

const PERSONAS = [
  ["aminata", "Aminata", "Journaliste / veilleuse", "Alertes temps réel, dossiers de veille, tri par pertinence"],
  ["kevin", "Kevin", "Étudiant podcasts & vidéos", "Lecteur intégré, filtre par format, mode arrière-plan"],
  ["kouassi", "Mme Kouassi", "Cadre décideuse", "Digest quotidien, partage rapide, lecture épurée"],
  ["yao", "Yao", "Community manager", "Tendances, hashtags, génération de posts"],
  ["paul", "Paul", "Senior, lecteur occasionnel", "Grande police, mode simplifié, favoris en un clic"],
  ["sara", "Sara", "Chercheuse / archiviste", "Recherche par date et auteur, export BibTeX, fiabilité"],
];
function pageLogin() {
  main().innerHTML = `
    <h1 style="text-align:center;margin-bottom:20px">Votre compte Prisme</h1>
    <div class="auth-wrap">
      <div class="panel">
        <div class="tabs"><button class="tab active" data-act="authtab" data-t="login">Connexion</button><button class="tab" data-act="authtab" data-t="register">Créer un compte</button></div>
        <form id="loginForm"><label class="f"><span>E-mail</span><input class="input" name="username" required autocomplete="username" inputmode="email"></label>
          <label class="f"><span>Mot de passe</span><input class="input" type="password" name="password" required autocomplete="current-password"></label>
          <button class="btn primary" style="width:100%;justify-content:center">Se connecter</button>
          ${S.config && S.config.email_verification ? `<p class="small" style="text-align:center;margin:10px 0 0"><button type="button" class="linklike" data-act="forgot">Mot de passe oublié ?</button></p>` : ""}</form>
        <form id="regForm" hidden><label class="f"><span>Nom complet</span><input class="input" name="display_name" required></label>
          <label class="f"><span>E-mail</span><input class="input" type="email" name="email" required autocomplete="email"></label>
          <label class="f"><span>Mot de passe (8 caractères minimum)</span><input class="input" type="password" name="password" required minlength="8" autocomplete="new-password"></label>
          <div class="f"><span style="display:block;font-weight:600;font-size:.88rem;margin-bottom:6px">Vos centres d'intérêt</span><div class="chips">${S.cats.map((c) => `<label class="chip"><input type="checkbox" name="interests" value="${c.slug}" style="margin-right:4px">${esc(c.name)}</label>`).join("")}</div></div>
          <div id="codeBox" hidden style="margin-top:10px"><div class="alert-line info small" id="codeInfo" style="margin-bottom:10px"></div>
            <label class="f"><span>Code à 6 chiffres reçu par e-mail</span><input class="input" name="code" inputmode="numeric" maxlength="6" autocomplete="one-time-code"></label></div>
          <button class="btn primary" id="regBtn" style="width:100%;justify-content:center;margin-top:8px">${S.config && S.config.email_verification ? "Recevoir mon code par e-mail" : "Créer mon compte"}</button></form>
        <p class="small muted" style="margin-bottom:0">Un compte permet de suivre des mots-clés, d'enregistrer des favoris et de personnaliser le fil. Lire Prisme n'en nécessite pas.</p>
      </div>
      ${S.config && S.config.demo_logins ? `<div class="panel">
        <h2>Profils de démonstration</h2>
        <p class="small muted">Chaque profil du cahier des charges est préconfiguré (intérêts, alertes, dossiers, historique).</p>
        <div class="stack">${PERSONAS.map(([u, n, r, f]) => `<button class="persona" data-act="demo" data-u="${u}"><span class="avatar">${initials(n)}</span><span><b>${n} — ${r}</b><span class="small muted">${f}</span></span></button>`).join("")}
          <button class="persona" data-act="demo" data-u="admin"><span class="avatar">AD</span><span><b>Administrateur</b><span class="small muted">Tableau de bord, modération, gestion des sources</span></span></button></div>
      </div>` : ""}
    </div>`;
  $("#loginForm").onsubmit = async (e) => { e.preventDefault(); doLogin(Object.fromEntries(new FormData(e.target))); };
  $("#regForm").onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const btn = $("#regBtn");
    btn.disabled = true;
    try {
      if (S.config && S.config.email_verification && $("#codeBox").hidden) {
        const c = await post("/api/email/code", { email: fd.get("email"), purpose: "register" });
        $("#codeInfo").textContent = c.demo_code
          ? `Mode démonstration : aucun e-mail n'est envoyé. Votre code est ${c.demo_code}.`
          : `Si cette adresse peut créer un compte, un code vient d'y être envoyé. Regardez aussi dans les indésirables. Il est valable 15 minutes.`;
        $("#codeBox").hidden = false;
        btn.textContent = "Créer mon compte";
        e.target.code.focus();
      } else {
        const r = await post("/api/register", { ...Object.fromEntries(fd), interests: fd.getAll("interests") });
        await onLogged(r); toast("Bienvenue sur Prisme !");
      }
    } catch (err) { toast(err.message, 1); }
    btn.disabled = false;
  };
}
async function doLogin(body) {
  try { const r = await post("/api/login", body); await onLogged(r); toast(`Connecté(e) : ${r.user.display_name}`); }
  catch (e) { toast(e.message, 1); }
}
async function onLogged(r) {
  S.token = r.token; S.user = r.user; store.set("prisme_token", r.token);
  await refreshMe(); applyPrefs(); S.feedMode = "pour_vous"; nav("/");
}
function logoutLocal() { S.token = null; S.user = null; S.favs = new Set(); S.unread = 0; store.del("prisme_token"); applyPrefs(); renderNav(); }
function needLogin(what) {
  main().innerHTML = `<div class="panel empty">${ico("user")}<h2>Connexion requise</h2><p>Connectez-vous pour accéder à ${esc(what)}.</p><a class="btn primary" href="/connexion">Se connecter</a></div>`;
}

function pageProject() {
  const done = (t) => `<li>${ico("check")}<span>${t}</span></li>`;
  const later = (t) => `<li style="color:var(--muted)">${ico("clock")}<span>${t}</span></li>`;
  main().innerHTML = `
    <section style="margin-bottom:22px"><span class="kicker">Le projet</span><h1>Prisme, agrégateur intelligent des nouveaux médias</h1>
      <p class="lead">Projet de Community Management · ESATIC — Licence 3 TWIN · Groupe 7 : Eboua Franck, Kah Toily, Yao Francklin · Encadrant : M. Cédric Cissé</p></section>
    <div class="grid g2">
      <div class="panel"><h2>Problématique</h2><p>L'information est fragmentée entre des dizaines de médias, de réseaux sociaux et de formats. Le lecteur voit dix fois la même actualité, ne sait pas quelle source croire, ne distingue pas une information récente d'un article ancien qui recircule, et se retrouve enfermé dans une bulle de filtres.</p>
        <h3>Réponse apportée</h3><p style="margin:0">Un agrégateur unique qui <b>regroupe</b> les doublons, <b>compare</b> les traitements, <b>recoupe</b> les affirmations, <b>date</b> clairement l'information, <b>explique</b> ses recommandations et permet aux lecteurs de <b>signaler</b> les erreurs.</p></div>
      <div class="panel"><h2>Objectifs SMART</h2><ul><li>Livraison du MVP au <b>30/11/2026</b></li><li>Temps de chargement <b>&lt; 2 s</b> (serveur local, requêtes indexées)</li><li>Score d'utilisabilité <b>SUS ≥ 85/100</b></li><li>Accessibilité : taille de texte, contraste élevé, mode simplifié</li><li>Utilisable par <b>tout public</b>, au-delà des six personas</li></ul></div>
    </div>
    <h2 style="margin-top:22px">Priorisation MoSCoW — état d'avancement</h2>
    <div class="moscow">
      <div class="panel"><h3>Indispensable <span class="badge b-ok">100 %</span></h3><ul>${done("Agrégation RSS multi-sources")}${done("Recherche simple et avancée")}${done("Favoris et dossiers")}${done("Dates de publication et de collecte")}${done("Liens vers les sources originales")}${done("Lecteur audio intégré")}${done("Design responsive")}</ul></div>
      <div class="panel"><h3>Très important <span class="badge b-ok">100 %</span></h3><ul>${done("Détection des doublons")}${done("Résumé IA avec citations vérifiables")}${done("Statut de couverture")}${done("Indicateur de fraîcheur / recirculation")}${done("Transparence des recommandations")}</ul></div>
      <div class="panel"><h3>Ensuite <span class="badge b-ok">100 %</span></h3><ul>${done("Comparaison de plusieurs sources")}${done("Signalement d'erreurs + modération")}${done("Notifications personnalisées par mots-clés")}${done("Digest quotidien")}${done("Traduction et simplification")}${done("Personnalisation anti-bulle")}${done("Export TXT / CSV / BibTeX")}</ul></div>
      <div class="panel"><h3>Plus tard <span class="badge">Prévu</span></h3><ul>${later("Vérification multimédia avancée (images, vidéos truquées)")}${later("Analyse des réseaux sociaux en temps réel")}${later("Synthèses complexes par grand modèle de langage")}${later("Application mobile et notifications push natives")}${later("Montée en charge de l'hébergement")}</ul></div>
    </div>
    <h2 style="margin-top:22px">Personas et fonctionnalités associées</h2>
    <div class="panel table-wrap" style="padding:0"><table class="t"><thead><tr><th>Persona</th><th>Besoin principal</th><th>Fonctionnalités Prisme</th><th>Démo</th></tr></thead><tbody>
      ${PERSONAS.map(([u, n, r, f]) => `<tr><td><b>${n}</b><div class="small muted">${r}</div></td><td class="small">${{ aminata: "Regrouper tous les flux, alertes temps réel", kevin: "Écouter sans interruption, filtrer le multimédia", kouassi: "Synthèse rapide, partage interne", yao: "Repérer les sujets tendance à relayer", paul: "Lisibilité et navigation très simple", sara: "Retrouver et citer d'anciens articles fiables" }[u]}</td><td class="small">${f}</td><td>${S.config && S.config.demo_logins ? `<button class="btn sm" data-act="demo" data-u="${u}">Se connecter</button>` : "—"}</td></tr>`).join("")}
      <tr><td><b>Tout public</b><div class="small muted">Visiteur non inscrit</div></td><td class="small">S'informer rapidement et de façon fiable</td><td class="small">Fil non personnalisé, vérification, fraîcheur, comparaison, traduction, simplification</td><td><a class="btn sm" href="/">Explorer</a></td></tr>
    </tbody></table></div>
    <h2 style="margin-top:22px">Architecture technique</h2>
    <div class="arch">
      <div><b>Interface (client)</b>Pages rendues côté serveur puis application monopage en JavaScript natif, thèmes clair/sombre, responsive.</div>
      <div><b>API REST (serveur)</b>Python 3 (bibliothèque standard) : serveur HTTP multi-thread, 40+ routes JSON, sessions par jeton.</div>
      <div><b>Moteur IA explicable</b>TAL statistique : vecteurs TF, similarité cosinus, extraction d'affirmations, lisibilité, tonalité.</div>
      <div><b>Base de données</b>SQLite relationnelle (21 tables + 1 vue), clés étrangères et index.</div>
    </div>
    <div class="grid g2" style="margin-top:16px">
      <div class="panel"><h3>Algorithmes clés</h3><ul class="small">
        <li><b>Doublons</b> : index inversé sur les titres, similarité cosinus ≥ 0,42 entre vecteurs pondérés (titre ×2), regroupement par union-find.</li>
        <li><b>Recoupement</b> : détection de 6 types d'affirmations ; recherche de phrases proches dans d'autres médias contemporains (± 30 jours) ; comparaison des chiffres arrêtés ; repérage des démentis. Le statut décrit la couverture, pas la véracité.</li>
        <li><b>Résumé</b> : extraction des phrases les plus centrales du sujet (multi-sources), anti-redondance, citation numérotée de chaque phrase.</li>
        <li><b>Fraîcheur</b> : décroissance exponentielle ; alerte si l'écart entre date de publication et date de reprise dépasse 30 jours.</li>
        <li><b>Recommandation</b> : score pondéré sur 6 critères affichés à l'utilisateur ; quota de « découverte » réglable ; indice de diversité de Shannon.</li></ul></div>
      <div class="panel"><h3>Base de données</h3><p class="small">users · sessions · categories · sources · articles · clusters · claims · evidences · interests · reading_history · folders · favorites · alerts · notifications · reports · shares · translations · glossary · fetch_log · change_log · meta — vue <i>v_articles</i>.</p>
        <p class="small muted">Le schéma complet est fourni dans <b>database/schema.sql</b>. Les contenus marqués « Démo » sont fictifs et servent à illustrer les scénarios (doublons, rumeur démentie, information ancienne qui recircule).</p>
        <h3>Éthique et limites</h3><p class="small" style="margin:0">Prisme aide à comparer sans prétendre établir la vérité, et il n'attribue aucune note aux médias réels. Aucune donnée personnelle n'est transmise à des tiers ; l'utilisateur peut effacer son historique.</p></div>
    </div>`;
}

// ====================================================================
//  Modales : partage, signalement, favori, ajout de source
// ====================================================================
function modal(html) {
  const m = $("#modal");
  m.innerHTML = `<div class="modal-box" role="dialog" aria-modal="true">${html}</div>`;
  m.hidden = false;
  m.onclick = (e) => { if (e.target === m || e.target.closest("[data-close]")) closeModal(); };
  setTimeout(() => m.querySelector("input, select, textarea, button")?.focus(), 30);
}
function closeModal() { $("#modal").hidden = true; $("#modal").innerHTML = ""; }
const articleLink = (a) => a.url || `${location.origin}/article/${a.id}`;
function postText(a) {
  const tags = (a.keywords || [a.category_name || "Actualité"]).slice(0, 3).map((k) => "#" + String(k).normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^A-Za-z0-9]/g, ""));
  return `📰 ${a.title}\n\nSource : ${a.source_name} — ${fmtDate(a.published_at, false)}\nStatut Prisme : ${STATUS[a.verification_status]?.[2] || "—"}\n\n👉 ${articleLink(a)}\n\n${tags.join(" ")} #Prisme`;
}
async function getArticle(id) { return CARD_CACHE.get(+id) || await get(`/api/articles/${id}`); }
async function openShare(id) {
  const a = await getArticle(id);
  const link = encodeURIComponent(articleLink(a)), title = encodeURIComponent(a.title);
  const ch = [["whatsapp", "WhatsApp", `https://wa.me/?text=${title}%20${link}`], ["email", "E-mail", `mailto:?subject=${title}&body=${link}`],
    ["linkedin", "LinkedIn", `https://www.linkedin.com/sharing/share-offsite/?url=${link}`], ["facebook", "Facebook", `https://www.facebook.com/sharer/sharer.php?u=${link}`], ["x", "X (Twitter)", `https://twitter.com/intent/tweet?text=${title}&url=${link}`]];
  modal(`<div class="row between"><h2 style="margin:0">${ico("share")} Partager</h2><button class="btn ghost sm" data-close>${ico("x")}</button></div>
    <p class="small muted">${esc(a.title)}</p>
    <div class="row">${ch.map(([k, l, u]) => `<a class="btn" href="${u}" target="_blank" rel="noopener" data-act="sharelog" data-id="${a.id}" data-ch="${k}">${l}</a>`).join("")}<button class="btn" data-act="copy" data-text="${esc(articleLink(a))}">${ico("copy")} Copier le lien</button></div>
    <hr class="sep"><h3>${ico("hash")} Publication prête à l'emploi (community management)</h3><div class="post-box" id="postBox">${esc(postText(a))}</div>
    <button class="btn primary" style="margin-top:10px" data-act="copy" data-text="${esc(postText(a))}">${ico("copy")} Copier la publication</button>`);
}
function openForgot() {
  modal(`<div class="row between"><h2 style="margin:0">Mot de passe oublié</h2><button class="btn ghost sm" data-close aria-label="Fermer">${ico("x")}</button></div>
    <p class="small muted">Prisme n'envoie jamais de mot de passe. Vous recevez un code, puis vous en choisissez un nouveau.</p>
    <form id="forgotForm"><label class="f"><span>E-mail</span><input class="input" type="email" name="email" required autocomplete="email"></label>
      <div id="forgotStep" hidden><div class="alert-line info small" id="forgotInfo" style="margin-bottom:10px"></div>
        <label class="f"><span>Code à 6 chiffres</span><input class="input" name="code" inputmode="numeric" maxlength="6" autocomplete="one-time-code"></label>
        <label class="f"><span>Nouveau mot de passe, 8 caractères minimum</span><input class="input" type="password" name="new_password" minlength="8" autocomplete="new-password"></label></div>
      <button class="btn primary" id="forgotBtn">Recevoir un code</button></form>`);
  $("#forgotForm").onsubmit = async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target));
    try {
      if ($("#forgotStep").hidden) {
        const c = await post("/api/email/code", { email: data.email, purpose: "reset" });
        $("#forgotInfo").textContent = c.demo_code ? `Mode démonstration : aucun e-mail n'est envoyé. Votre code est ${c.demo_code}.`
          : "Si un compte existe avec cette adresse, un code vient d'y être envoyé. Il est valable 15 minutes.";
        $("#forgotStep").hidden = false;
        $("#forgotBtn").textContent = "Changer mon mot de passe";
        e.target.code.focus();
      } else {
        const r = await post("/api/password/reset", data);
        closeModal(); await onLogged(r); toast("Mot de passe changé.");
      }
    } catch (err) { toast(err.message, 1); }
  };
}
function openReport(id) {
  if (!S.user) toast("Signalement anonyme : connectez-vous pour suivre son traitement.");
  modal(`<div class="row between"><h2 style="margin:0">${ico("flag")} Signaler une erreur</h2><button class="btn ghost sm" data-close>${ico("x")}</button></div>
    <p class="small muted">Votre signalement sera examiné par l'équipe de modération. Merci d'être précis et, si possible, de fournir une preuve.</p>
    <form id="repForm"><label class="f"><span>Type d'erreur</span><select class="input" name="reason">${Object.entries(REASONS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></label>
      <label class="f"><span>Description</span><textarea class="input" name="description" required minlength="10" placeholder="Expliquez ce qui est incorrect…"></textarea></label>
      <label class="f"><span>Lien vers une preuve (facultatif)</span><input class="input" type="url" name="evidence_url" placeholder="https://…"></label>
      <div class="row"><button class="btn primary">${ico("flag")} Envoyer le signalement</button><button type="button" class="btn ghost" data-close>Annuler</button></div></form>`);
  $("#repForm").onsubmit = async (e) => {
    e.preventDefault();
    try { await post("/api/reports", { article_id: id, ...Object.fromEntries(new FormData(e.target)) }); closeModal(); toast("Merci ! Votre signalement a été transmis à la modération."); }
    catch (err) { toast(err.message, 1); }
  };
}
async function toggleFav(id, btn) {
  if (!S.user) { toast("Connectez-vous pour enregistrer des favoris."); nav("/connexion"); return; }
  id = +id;
  if (S.favs.has(id)) { await del(`/api/favorites/${id}`); S.favs.delete(id); toast("Retiré des favoris."); }
  else {
    const f = await get("/api/favorites");
    if (f.folders.length) {
      modal(`<h2>${ico("star")} Enregistrer dans…</h2><div class="stack"><button class="persona" data-folder="">${ico("star")} <b>Favoris (sans dossier)</b></button>${f.folders.map((x) => `<button class="persona" data-folder="${x.id}"><span style="width:12px;height:12px;border-radius:4px;background:${esc(x.color)}"></span><b>${esc(x.name)}</b></button>`).join("")}</div>`);
      $$("#modal [data-folder]").forEach((b) => b.onclick = async () => { await post("/api/favorites", { article_id: id, folder_id: b.dataset.folder || null }); S.favs.add(id); closeModal(); toast("Ajouté aux favoris."); markFav(id); });
      return;
    }
    await post("/api/favorites", { article_id: id }); S.favs.add(id); toast("Ajouté aux favoris.");
  }
  markFav(id);
}
function markFav(id) { $$(`[data-act="fav"][data-id="${id}"]`).forEach((b) => { b.style.color = S.favs.has(id) ? "var(--accent)" : ""; b.setAttribute("aria-pressed", S.favs.has(id)); }); }
function openAddSource() {
  modal(`<div class="row between"><h2 style="margin:0">${ico("plus")} Ajouter un flux RSS</h2><button class="btn ghost sm" data-close>${ico("x")}</button></div>
    <form id="srcForm"><label class="f"><span>Nom du média</span><input class="input" name="name" required></label>
      <label class="f"><span>URL du flux RSS / Atom</span><input class="input" type="url" name="feed_url" required placeholder="https://exemple.com/rss"></label>
      <div class="grid g2"><label class="f"><span>Site web</span><input class="input" name="website"></label><label class="f"><span>Pays</span><input class="input" name="country"></label>
      <label class="f"><span>Langue</span><select class="input" name="language"><option value="fr">Français</option><option value="en">Anglais</option></select></label>
      <label class="f"><span>Type</span><select class="input" name="kind">${["presse", "tv", "radio", "web", "podcast", "agence", "social"].map((k) => `<option>${k}</option>`).join("")}</select></label>
      <label class="f"><span>Rubrique par défaut</span><select class="input" name="category"><option value="">Classement automatique</option>${S.cats.map((c) => `<option value="${c.slug}">${esc(c.name)}</option>`).join("")}</select></label>
      </div>
      <button class="btn primary">${ico("check")} Tester et ajouter</button></form>`);
  $("#srcForm").onsubmit = async (e) => {
    e.preventDefault();
    try { const r = await post("/api/sources", Object.fromEntries(new FormData(e.target))); closeModal(); toast(`Source ajoutée : ${r.items_detected} contenu(s) détecté(s). Lancez une collecte.`); pageSources(); }
    catch (err) { toast(err.message, 1); }
  };
}

// ====================================================================
//  Lecteur multimédia persistant
// ====================================================================
async function play(id) {
  const a = await getArticle(id);
  const pl = $("#player");
  pl.hidden = false;
  pl.innerHTML = `${ico("headphones")}<span class="t" title="${esc(a.title)}"><b>${esc(a.source_name)}</b><br>${esc(a.title)}</span><audio controls autoplay src="${esc(a.media_url)}"></audio><button data-act="closeplayer" aria-label="Fermer le lecteur">${ico("x")}</button>`;
}

// ====================================================================
//  Délégation des événements
// ====================================================================
document.addEventListener("click", async (e) => {
  const el = e.target.closest("[data-act]");
  if (!el) return;
  const act = el.dataset.act, id = el.dataset.id;
  const prevent = () => e.preventDefault();
  try {
    switch (act) {
      case "mode": S.feedMode = el.dataset.mode; pageFeed(); break;
      case "cat": S.feedCat = el.dataset.cat; $$("[data-act=cat]").forEach((c) => c.classList.toggle("active", c === el)); loadFeed(true); break;
      case "compare": nav(`/sujet/${el.dataset.cluster}`); break;
      case "why": {
        const c = el.closest(".card"), box = c.querySelector(".why");
        box.innerHTML = whyHtml(CARD_CACHE.get(+c.dataset.id).why); box.hidden = !box.hidden; break;
      }
      case "fav": prevent(); await toggleFav(id, el); break;
      case "share": prevent(); await openShare(id); break;
      case "report": prevent(); openReport(+id); break;
      case "play": await play(id); break;
      case "closeplayer": $("#player").hidden = true; $("#player").innerHTML = ""; break;
      case "tool": tool(el.dataset.tool); break;
      case "cite": document.getElementById("cite-" + el.dataset.n)?.scrollIntoView({ behavior: "smooth", block: "center" }); break;
      case "reverify": { el.disabled = true; const r = await post(`/api/articles/${id}/verify`); S.currentArticle.claims = r.claims; renderClaims($("#toolBody"), r.claims, S.currentArticle); toast(`Analyse relancée : ${STATUS[r.status][2]} (${r.score}/100)`); break; }
      case "reader": document.body.classList.toggle("reader"); break;
      case "copy": prevent(); await navigator.clipboard.writeText(el.dataset.text); toast("Copié dans le presse-papiers."); break;
      case "copytag": await navigator.clipboard.writeText(el.dataset.tag); toast(`${el.dataset.tag} copié.`); break;
      case "post": await openShare(id); break;
      case "sharelog": post(`/api/articles/${id}/share`, { channel: el.dataset.ch }).catch(() => {}); break;
      case "mmtab": mmTab = el.dataset.tab; pageMultimedia(); break;
      case "demo": { const r = await post("/api/demo-login", { username: el.dataset.u }); await onLogged(r); toast(`Connecté(e) : ${r.user.display_name}`); break; }
      case "forgot": openForgot(); break;
      case "back": if (history.length > 1) history.back(); else nav("/"); break;
      case "print": window.print(); break;
      case "authtab": $$("[data-act=authtab]").forEach((t) => t.classList.toggle("active", t === el)); $("#loginForm").hidden = el.dataset.t !== "login"; $("#regForm").hidden = el.dataset.t === "login"; break;
      case "usermenu":
        modal(`<div class="row"><span class="avatar">${initials(S.user.display_name)}</span><div><b>${esc(S.user.display_name)}</b><div class="small muted">${esc(S.user.persona || S.user.email)}</div></div></div>
          <div class="stack" style="margin-top:16px"><a class="btn" href="/parametres" data-close>${ico("gear")} Paramètres</a><a class="btn" href="/favoris" data-close>${ico("star")} Mes favoris</a><a class="btn" href="/veille" data-close>${ico("eye")} Ma veille</a>
          <button class="btn danger" data-act="logout">${ico("logout")} Se déconnecter</button></div>`); break;
      case "logout": await post("/api/logout").catch(() => {}); logoutLocal(); closeModal(); toast("Vous êtes déconnecté(e)."); nav("/"); route(); break;
      case "alertdel": await del(`/api/alerts/${id}`); pageVeille(); break;
      case "folderdel": if (confirm("Supprimer ce dossier ? Les articles restent dans vos favoris.")) { await del(`/api/folders/${id}`); pageVeille(); } break;
      case "readall": await post("/api/notifications/read"); await refreshMe(); pageNotifications(); break;
      case "readone": await post("/api/notifications/read", { id }); refreshMe(); if (el.tagName === "BUTTON") pageNotifications(); break;
      case "pushperm":
        if (!("Notification" in window)) toast("Votre navigateur ne gère pas les notifications.", 1);
        else { const p = await Notification.requestPermission(); toast(p === "granted" ? "Notifications du navigateur activées." : "Autorisation refusée."); } break;
      case "download": prevent(); await download(el.getAttribute("href")); break;
      case "refresh": await startRefresh(); break;
      case "recluster": { el.disabled = true; toast("Recalcul en cours…"); const r = await post("/api/admin/recluster"); toast(`${r.clusters} sujets, ${r.duplicates} doublons, ${r.verified} articles vérifiés.`); pageAdmin(); break; }
      case "addsource": openAddSource(); break;
      case "srcdel": if (confirm("Supprimer cette source et ses contenus ?")) { await del(`/api/sources/${id}`); pageSources(); } break;
    }
  } catch (err) { toast(err.message, 1); }
});
document.addEventListener("change", async (e) => {
  const el = e.target, act = el.dataset.act, id = el.dataset.id;
  try {
    if (act === "alerttoggle") { await put(`/api/alerts/${id}`, { active: el.checked ? 1 : 0 }); toast(el.checked ? "Alerte activée." : "Alerte suspendue."); }
    if (act === "srcactive") { await put(`/api/sources/${id}`, { active: el.checked ? 1 : 0 }); toast("Source mise à jour."); }
    if (act === "srccert") { await put(`/api/sources/${id}`, { certified: el.checked ? 1 : 0 }); toast("Certification mise à jour."); }
    if (act === "rel") { await put(`/api/sources/${id}`, { reliability: +el.value }); $("#rel-" + id).textContent = el.value + "/100"; toast("Fiabilité mise à jour (prise en compte à la prochaine analyse)."); }
  } catch (err) { toast(err.message, 1); }
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { if (!$("#modal").hidden) closeModal(); else closeDrawer(); } });
document.addEventListener("error", (e) => {   // image distante indisponible : on garde une mise en page propre
  const img = e.target;
  if (img.tagName !== "IMG") return;
  if (img.dataset.fallback) {
    img.src = img.dataset.fallback;
    delete img.dataset.fallback;
    img.insertAdjacentHTML("afterend", `<span class="illu-tag">Illustration</span>`);
  } else img.remove();
}, true);
document.addEventListener("click", (e) => {   // liens internes sans rechargement de page
  const a = e.target.closest("a[href^='/']");
  if (!a || e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || a.target || a.dataset.act === "download" || a.getAttribute("href").startsWith("/api/")) return;
  e.preventDefault();
  closeModal();
  nav(a.getAttribute("href"));
});

async function download(href) {
  const res = await fetch(href, { headers: { Authorization: "Bearer " + S.token } });
  if (!res.ok) throw new Error("Export impossible.");
  const blob = await res.blob();
  const name = (res.headers.get("Content-Disposition") || "").match(/filename="(.+)"/)?.[1] || "export.txt";
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: name });
  document.body.appendChild(a); a.click(); a.remove();
  toast(`Fichier ${name} téléchargé.`);
}

async function startRefresh() {
  await post("/api/refresh");
  toast("Collecte des flux RSS en cours…");
  $("#refreshBtn").classList.add("spin");
  const poll = setInterval(async () => {
    const r = await get("/api/refresh");
    if (!r.running) {
      clearInterval(poll); $("#refreshBtn").classList.remove("spin");
      const l = r.last || {};
      toast(l.error ? "Collecte impossible : " + l.error : `Collecte terminée : ${l.new_articles || 0} nouveau(x) contenu(s), ${l.sources_ok || 0} source(s) joignable(s).`, !!l.error);
      refreshMe(); route();
    }
  }, 2500);
}

// ====================================================================
//  Routage et démarrage
// ====================================================================
async function refreshMe() {
  if (!S.token) { renderNav(); return; }
  const r = await get("/api/me").catch(() => ({ user: null }));
  if (!r.user) { logoutLocal(); return; }
  S.user = r.user;
  const prev = S.lastUnread;
  S.unread = r.unread; S.lastUnread = r.unread;
  if (prev !== null && r.unread > prev) {
    toast(`${r.unread - prev} nouvelle(s) notification(s).`);
    if ("Notification" in window && Notification.permission === "granted") new Notification("Prisme", { body: `${r.unread - prev} nouvelle(s) alerte(s) d'actualité` });
  }
  const f = await get("/api/favorites").catch(() => ({ items: [] }));
  S.favs = new Set(f.items.map((x) => x.id));
  renderNav();
}

const ROUTES = [
  [/^\/$/, () => { S.feedCat = ""; return pageFeed(); }, "Prisme : l'actualité comparée, média par média"],
  [/^\/rubrique\/([a-z]+)/, (slug) => { S.feedCat = slug; return pageFeed(); }], [/^\/article\/(\d+)/, pageArticle], [/^\/sujet\/(\d+)/, pageCompare],
  [/^\/recherche\??(.*)/, pageSearch, "Recherche"], [/^\/tendances/, pageTrends, "Tendances"], [/^\/digest/, pageDigest, "Le digest du jour"],
  [/^\/multimedia/, pageMultimedia, "Podcasts et vidéos"], [/^\/veille/, pageVeille, "Veille et alertes"], [/^\/favoris\??(.*)/, pageFavorites, "Mes favoris"],
  [/^\/notifications/, pageNotifications, "Notifications"], [/^\/signalements\??(.*)/, pageReports, "Signalements"], [/^\/sources/, pageSources, "Médias suivis"],
  [/^\/admin/, pageAdmin, "Administration"], [/^\/parametres/, pageSettings, "Paramètres"], [/^\/projet/, pageProject, "Le projet"], [/^\/methode/, pageMethod, "Notre méthode"], [/^\/connexion/, pageLogin, "Connexion"],
];
async function route() {
  const h = location.pathname + location.search;
  document.body.classList.remove("reader");
  closeDrawer();
  renderNav();
  for (const [rx, fn, title] of ROUTES) {
    const m = h.match(rx);
    if (m) {
      if (title) setTitle(title);
      try { await fn(...m.slice(1)); } catch (e) { main().innerHTML = `<div class="empty">${ico("alert")}<h1>${esc(e.message === "Sujet introuvable." || e.message === "Article introuvable." ? e.message : "Une erreur est survenue")}</h1><p>${esc(e.message)}</p><a class="btn" href="/">Retour à l'accueil</a></div>`; }
      window.scrollTo(0, 0);
      return;
    }
  }
  setTitle("Page introuvable");
  main().innerHTML = `<div class="empty"><h1>Page introuvable</h1><p>Cette adresse n'existe pas ou plus.</p><a class="btn" href="/">Retour à l'accueil</a></div>`;
}

(async function start() {
  if (location.hash.startsWith("#/")) history.replaceState(null, "", location.hash.slice(1));   // anciens liens partagés
  $("#menuBtn").innerHTML = ico("menu");
  $("#refreshBtn").innerHTML = ico("refresh");
  $(".search-ico").innerHTML = ico("search");
  $("#menuBtn").onclick = () => ($("#sidebar").classList.contains("open") ? closeDrawer() : openDrawer());
  $("#drawerBack").onclick = closeDrawer;
  $("#refreshBtn").onclick = () => startRefresh().catch((e) => toast(e.message, 1));
  $("#quickSearch").onsubmit = (e) => { e.preventDefault(); const q = $("#quickQ").value.trim(); if (q) nav("/recherche?q=" + encodeURIComponent(q) + "&dedup=1"); };
  S.token = store.get("prisme_token", null);
  [S.cats, S.config] = await Promise.all([get("/api/categories").catch(() => []), get("/api/config").catch(() => ({}))]);
  await refreshMe();
  applyPrefs();
  window.addEventListener("popstate", route);
  route();
  dateline();
  setInterval(() => { if (S.token) refreshMe(); }, 60000);
})();
