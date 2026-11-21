const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
} [c]));
const icon = (id, cls = "") =>
    `<svg class="icon ${cls}" aria-hidden="true"><use href="/static/assets/icons.svg#${id}"></use></svg>`;
const profileURL = id => "/profile.html?id=" + encodeURIComponent(id);
const brand =
    `<a class="brand" href="/" aria-label="CiviConnect home"><span class="brandmark">${icon("mark")}</span>CiviConnect</a>`;
const nav = [
    ["Home", "/index.html"],
    ["Candidates", "/politicians.html"],
    ["Our mission", "/mission.html"]
];
const page = location.pathname.split("/").pop() || "index.html";

function navLink([label, url]) {
    const active = page === url.slice(1) || (page === "profile.html" && label === "Candidates");
    return `<a href="${url}" ${active ? 'class="active" aria-current="page"' : ""}>${label}</a>`;
}
$("#site-header").innerHTML =
    `<div class="nav-inner">${brand}<nav class="desktop-nav" aria-label="Primary">${nav.map(navLink).join("")}</nav>
  <div class="nav-actions"><a class="btn portal-btn" href="/politician-login.html">${icon("portal")} Candidate portal</a>
  <button class="circle" id="theme" aria-label="Change color theme"></button>
  <button class="circle" id="menu" aria-label="Navigation menu" aria-expanded="false" aria-controls="menu-pop">${icon("menu")}</button></div>
  <nav id="menu-pop" class="menu-pop" aria-label="All pages" hidden>${[...nav,["Register as candidate","/submit.html"],["Politician portal","/politician-login.html"]].map(([t,u])=>`<a class="menu-link" href="${u}">${t}</a>`).join("")}</nav></div>`;
const media = matchMedia("(prefers-color-scheme: dark)");
const preference = () => document.documentElement.dataset.theme || "auto";

function showTheme() {
    const pref = preference();
    const current = pref === "auto" ? (media.matches ? "dark" : "light") : pref;
    $("#theme").innerHTML = icon(current === "dark" ? "moon" : "sun");
    const next = pref === "auto" ? (current === "dark" ? "light" : "dark") : pref === (media.matches ?
        "dark" : "light") ? "auto" : (media.matches ? "dark" : "light");
    $("#theme").dataset.next = next;
    $("#theme").title = `Theme: ${pref}. Switch to ${next}.`;
    $("#theme").setAttribute("aria-label", $("#theme").title);
}
$("#theme").onclick = () => {
    const next = $("#theme").dataset.next;
    if (next === "auto") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = next;
    try {
        localStorage.setItem("civiconnect-theme", next);
    } catch {
        /* Session-only theme. */ }
    showTheme();
};
showTheme();
media.addEventListener("change", showTheme);

function setMenu(open) {
    $("#menu-pop").hidden = !open;
    $("#menu").setAttribute("aria-expanded", String(open));
}
$("#menu").onclick = () => setMenu($("#menu-pop").hidden);
document.addEventListener("click", event => {
    if (!event.target.closest("#menu, #menu-pop")) setMenu(false);
});
document.addEventListener("keydown", event => {
    if (event.key === "Escape" && !$("#menu-pop").hidden) {
        setMenu(false);
        $("#menu").focus();
    }
});
$("#site-footer").innerHTML =
    `<div class="footer-inner">${brand}<small>© ${new Date().getFullYear()} CiviConnect</small>
  <div class="footer-links"><a href="/submit.html">Candidate registration</a><a href="/admin-login.html">Admin</a><button id="contact-open">Contact us</button></div></div>
  <dialog id="contact-dialog"><div class="dialog-head"><h2>Contact CiviConnect</h2><button class="circle" data-close aria-label="Close">${icon("close")}</button></div>
  <form class="form-stack" id="contact"><label>Name<input name="name" required maxlength="160" autocomplete="name"></label><label>Email<input type="email" name="email" required maxlength="254" autocomplete="email"></label><label>Message<textarea name="message" required maxlength="3000" rows="4"></textarea></label><button class="btn primary">Send message</button><p class="status" role="status"></p></form></dialog>`;
$("#contact-open").onclick = () => $("#contact-dialog").showModal();
document.addEventListener("click", event => {
    if (event.target.closest("[data-close]")) event.target.closest("dialog")?.close();
});
async function api(path, method = "GET", data) {
    const options = {
        method,
        headers: {}
    };
    if (data instanceof FormData) options.body = data;
    else if (data !== undefined) {
        options.headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(data);
    }
    const response = await fetch(path, options);
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
        if (response.status === 401 && ["/admin", "/politician"].includes(location.pathname)) {
            location.assign(location.pathname + "-login.html");
        }
        const message = Array.isArray(body.detail) ? body.detail.map(x => x.msg).join(". ") : body
            .detail;
        throw Error(message || `Request failed (${response.status}). Please try again.`);
    }
    return body;
}

function status(el, message = "", error = false) {
    el.textContent = message;
    el.classList.toggle("error", error);
}

function bindForm(form, handler) {
    form.addEventListener("submit", async event => {
        event.preventDefault();
        const button = event.submitter || $("button[type=submit],button:not([type])", form);
        const output = $(".status", form);
        if (button) button.disabled = true;
        if (output) status(output);
        try {
            await handler(new FormData(form));
        } catch (error) {
            if (output) status(output, error.message, true);
        } finally {
            if (button) button.disabled = false;
        }
    });
}
bindForm($("#contact"), async data => {
    await api("/api/contact", "POST", Object.fromEntries(data));
    $("#contact").reset();
    status($("#contact .status"), "Message received. Thank you for contacting us.");
});

function detailFields(person = {}) {
    const statements = Array.from({length: 5}, (_, i) => {
        const requirement = i < 3 ? "required" : "";
        const optional = i < 3 ? "" : '<span class="optional">Optional</span>';
        return `<label>Statement ${i+1} ${optional}
            <input name="statement" maxlength="600" value="${esc(person.statements?.[i])}" ${requirement}></label>`;
    }).join("");
    const networks = {x: "X", instagram: "Instagram", tiktok: "TikTok", website: "Website"};
    const socialFields = Object.entries(networks).map(([key, label]) =>
        `<label>${label}<input name="${key}" type="url" maxlength="512"
            placeholder="https://" value="${esc(person.socials?.[key])}"></label>`
    ).join("");
    return `<label>Biography<textarea name="description" required maxlength="3000" rows="4">${esc(person.description)}</textarea></label>
        <fieldset class="field-stack"><legend>Policy statements</legend>${statements}</fieldset>
        <fieldset><legend>Social links <span class="optional">Optional</span></legend>
        <div class="two-col">${socialFields}</div></fieldset>`;
}

function detailData(data) {
    return {
        description: data.get("description"),
        statements: data.getAll("statement").map(value => value.trim()).filter(Boolean),
        socials: Object.fromEntries(["x","instagram","tiktok","website"].map(key => [key, data.get(key) || ""]))
    };
}

function login(role) {
    bindForm($("#login"), async data => {
        await api(`/api/${role}/login`, "POST", Object.fromEntries(data));
        location.assign("/" + role);
    });
}

function bindLogout(role) {
    $("#logout").onclick = async () => {
        try {
            await api(`/api/${role}/logout`, "POST");
            location.assign("/" + role + "-login.html");
        } catch (e) {
            status($("#dashboard-status"), e.message, true);
        }
    };
}
const poster = r => r.poster_url || (r.youtube_id ?
    `https://i.ytimg.com/vi/${encodeURIComponent(r.youtube_id)}/hqdefault.jpg` : "");

function previewImage(r, cls) {
    const src = esc(poster(r));
    if (src) return `<img class="${cls}" src="${src}" alt="">`;
    return `<video class="${cls}" src="${esc(r.video_url)}#t=0.1" muted playsinline preload="metadata" aria-hidden="true"></video>`;
}

function queueItem(r, index) {
    return `<button class="queue-item" data-index="${index}"><span class="thumbnail">${previewImage(r,"")}<span class="mini-play">${icon("play")}</span></span>
        <span class="queue-copy"><span class="reply-type">${esc(r.topic||"Video reply")}</span><strong>${esc(r.question_prompt)}</strong><small>${esc(r.name)}</small></span></button>`;
}

function stage(el, r, number = "") {
    const restore = () => stage(el, r, number);
    el.innerHTML =
        `${previewImage(r,"stage-photo")}<div class="stage-shade"></div>
      <div class="stage-top"><span class="feature-chip">${icon("video")} Candidate reply</span>${number?`<span class="stage-num">${esc(number)}</span>`:""}</div>
      <button class="play-main" aria-label="Play reply from ${esc(r.name)}">${icon("play")}</button>
      <div class="featured-content"><span class="topic-chip">${esc(r.topic||"Citizen question")}</span><h3>${esc(r.question_prompt)}</h3>
      <a class="person-line" href="${profileURL(r.politician_id)}"><img src="${esc(r.photo_url)}" alt=""><span><strong>${esc(r.name)} ${icon("badge","verified")}</strong><small>${esc(r.party)}</small></span></a></div>`;
    $(".play-main", el).onclick = () => {
        el.innerHTML = `<div class="stage-player ${r.aspect_ratio==="vertical"?"vertical":""}">${previewImage(r,"ambient")}
          ${r.source_type==="youtube" ? `<iframe src="https://www.youtube-nocookie.com/embed/${encodeURIComponent(r.youtube_id)}?autoplay=1" title="${esc(r.question_prompt)}" allow="autoplay; fullscreen" allowfullscreen></iframe>` :
          `<video controls autoplay playsinline preload="metadata" src="${esc(r.video_url)}" aria-label="${esc(r.question_prompt)}"></video>`}
          <button class="circle stop" aria-label="Close video player">${icon("close")}</button></div>`;
        $(".stop", el).onclick = () => {
            restore();
            $(".play-main", el).focus();
        };
        $(".stop", el).focus();
    };
}
const empty = message => `<p class="empty">${esc(message)}</p>`;
const dateText = value => new Date(value).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric"
});

export {
    $,
    $$,
    esc,
    icon,
    profileURL,
    api,
    status,
    bindForm,
    detailFields,
    detailData,
    login,
    bindLogout,
    queueItem,
    stage,
    empty,
    dateText
};
