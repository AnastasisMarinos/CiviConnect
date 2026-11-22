import {
    $,
    api,
    esc,
    icon,
    socialLabels,
    avatar,
    empty,
    loadProfileNews
} from "./common.js?v=profile-networks";

const id = new URLSearchParams(location.search).get("id");
const isDemo = id === "demo-fictional-profile";
const profile = $("#profile");
let renderedProfile = null;

function renderProfile(p) {
    const existingNews = p.name === renderedProfile?.name ? $("#profile-news", profile) : null;
    document.title = p.name + " · CiviConnect";
    const links = Object.entries(socialLabels)
        .filter(([network]) => /^https?:\/\//i.test(p.socials[network] ?? ""))
        .map(([network, label]) =>
            `<a class="btn profile-social" href="${esc(p.socials[network])}" rel="noopener noreferrer" target="_blank">${icon("social-" + network)}<span>${label}</span></a>`
        ).join("");
    const claim = p.status === "unclaimed"
        ? `<a class="btn profile-claim" href="/claim-profile.html?id=${encodeURIComponent(p.id)}">Διεκδίκηση προφίλ</a>`
        : "";
    const label = p.status === "demo" ? "Δοκιμαστικό προφίλ · Φανταστικό πρόσωπο" :
        p.status === "verified" ? icon("badge","verified") + " Επαληθευμένο προφίλ" : "Δημόσια στοιχεία OpenCouncil";
    profile.innerHTML =
        `<div class="profile-hero"><div class="profile-details"><div class="eyebrow">${label}</div><h1>${esc(p.name)}</h1><p>${esc(p.party)}</p><p>${esc(p.role)}</p></div><div class="profile-portrait">${avatar(p)}${claim}</div></div>
      <div class="profile-info">${p.description || links ? `<article class="panel"><h2>Βιογραφικό</h2>${p.description ? `<p>${esc(p.description)}</p>` : ""}${links ? `<div class="socials">${links}</div>` : ""}</article>` : ""}
      ${p.statements.length ? `<article class="panel"><h2>Προγραμματικές θέσεις</h2><ul>${p.statements.map(s=>`<li>${esc(s)}</li>`).join("")}</ul></article>` : ""}</div>
      <section id="profile-news" class="panel profile-news" aria-labelledby="profile-news-title">
        <h2 id="profile-news-title">Πρόσφατα δημοσιεύματα από το Google News</h2>
        <p class="profile-news-status" role="status">Αναζήτηση δημοσιευμάτων…</p>
      </section>
      ${p.opencouncil_id ? '<p class="notice">Πηγή: <a href="https://opencouncil.gr/athens/people">OpenCouncil – Δήμος Αθηναίων</a></p>' : ""}`;
    const news = $("#profile-news", profile);
    if (existingNews) news.replaceWith(existingNews);
    else loadProfileNews(news, p.id);
    renderedProfile = p;
}

async function refreshProfile() {
    try {
        if (!id) throw Error("Επιλέξτε εκπρόσωπο από τον κατάλογο για να δείτε το προφίλ του.");
        const url = "/api/politicians/" + encodeURIComponent(id);
        const p = await api(url, "GET", undefined, isDemo ? "no-store" : "default");
        if (JSON.stringify(p) !== JSON.stringify(renderedProfile)) renderProfile(p);
    } catch (error) {
        if (!renderedProfile || error.status === 404) {
            profile.innerHTML = empty(error.message);
            renderedProfile = null;
        }
    }
}

async function watchDemo() {
    if (!document.hidden) await refreshProfile();
    setTimeout(watchDemo, 3000);
}

await refreshProfile();
if (isDemo) setTimeout(watchDemo, 3000);
