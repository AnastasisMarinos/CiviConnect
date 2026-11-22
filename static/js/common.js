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
    `<svg class="icon ${cls}" aria-hidden="true"><use href="/static/assets/icons.svg?v=profile-networks#${id}"></use></svg>`;
const socialLabels = {x: "X", instagram: "Instagram", tiktok: "TikTok", facebook: "Facebook", linkedin: "LinkedIn", youtube: "YouTube", website: "Ιστότοπος"};
function avatar(person) {
    if (person.photo_url) return `<img class="avatar" src="${esc(person.photo_url)}" alt="">`;
    const initials = person.name.trim().split(/\s+/).slice(0, 2).map(part => part[0]).join("");
    return `<span class="avatar initials" aria-hidden="true">${esc(initials)}</span>`;
}
const profileURL = id => "/profile.html?id=" + encodeURIComponent(id);
const brand =
    `<a class="brand" href="/" aria-label="Αρχική σελίδα CiviConnect"><span class="brandmark">${icon("mark")}</span>CiviConnect</a>`;
const nav = [
    ["Αρχική", "/index.html"],
    ["Εκπρόσωποι", "/politicians.html"],
    ["Η αποστολή μας", "/mission.html"]
];
const page = location.pathname.split("/").pop() || "index.html";

function navLink([label, url]) {
    const active = page === url.slice(1) || (page === "profile.html" && url === "/politicians.html");
    return `<a href="${url}" ${active ? 'class="active" aria-current="page"' : ""}>${label}</a>`;
}
$("#site-header").innerHTML =
    `<div class="nav-inner">${brand}<nav class="desktop-nav" aria-label="Κύρια πλοήγηση">${nav.map(navLink).join("")}</nav>
  <div class="nav-actions">
  <button class="circle" id="menu" aria-label="Μενού πλοήγησης" aria-expanded="false" aria-controls="menu-pop">${icon("menu")}</button></div>
  <nav id="menu-pop" class="menu-pop" aria-label="Όλες οι σελίδες" hidden>${[...nav,["Διεκδίκηση προφίλ","/claim-profile.html"],["Πύλη εκπροσώπων","/politician-login.html"]].map(([t,u])=>`<a class="menu-link" href="${u}">${t}</a>`).join("")}</nav></div>`;
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
$("#site-footer").insertAdjacentHTML("beforeend",
    `<div class="footer-inner">${brand}<small>© ${new Date().getFullYear()} CiviConnect</small>
  <div class="footer-links"><a href="/claim-profile.html">Διεκδίκηση προφίλ</a><a href="/admin-login.html">Διαχείριση</a><button id="contact-open">Επικοινωνία</button></div></div>
  <dialog id="contact-dialog"><div class="dialog-head"><h2>Επικοινωνία με το CiviConnect</h2><button class="circle" data-close aria-label="Κλείσιμο">${icon("close")}</button></div>
  <form class="form-stack" id="contact"><label>Όνομα<input name="name" required maxlength="160" autocomplete="name"></label><label>Email<input type="email" name="email" required maxlength="254" autocomplete="email"></label><label>Μήνυμα<textarea name="message" required maxlength="3000" rows="4"></textarea></label><button class="btn primary">Αποστολή μηνύματος</button><p class="status" role="status"></p></form></dialog>`);
$("#contact-open").onclick = () => $("#contact-dialog").showModal();
document.addEventListener("click", event => {
    if (event.target.closest("[data-close]")) event.target.closest("dialog")?.close();
});
async function api(path, method = "GET", data, cache = "default") {
    const options = {
        method,
        cache,
        headers: {}
    };
    if (data instanceof FormData) options.body = data;
    else if (data !== undefined) {
        options.headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(data);
    }
    const response = await fetch(path, options).catch(() => {
        throw Error("Η σύνδεση με το CiviConnect απέτυχε. Δοκιμάστε ξανά.");
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
        if (response.status === 401 && ["/admin", "/politician"].includes(location.pathname)) {
            location.assign(location.pathname + "-login.html");
        }
        const message = Array.isArray(body.detail) ? "Ελέγξτε τα στοιχεία που συμπληρώσατε." : body.detail;
        const error = Error(message || `Το αίτημα απέτυχε (${response.status}). Δοκιμάστε ξανά.`);
        error.status = response.status;
        throw error;
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
            await handler(new FormData(form), event.submitter);
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
    status($("#contact .status"), "Το μήνυμά σας εστάλη. Ευχαριστούμε για την επικοινωνία.");
});

function detailFields(person = {}, includeSocials = true) {
    const statements = Array.from({length: 5}, (_, i) => {
        const optional = '<span class="optional">Προαιρετικό</span>';
        return `<label>Θέση ${i+1} ${optional}
            <input name="statement" maxlength="600" value="${esc(person.statements?.[i])}"></label>`;
    }).join("");
    const socialFields = Object.entries(socialLabels).map(([key, label]) =>
        `<label>${label}<input name="${key}" type="url" maxlength="512"
            placeholder="https://" value="${esc(person.socials?.[key])}"></label>`
    ).join("");
    return `<label>Βιογραφικό <span class="optional">Προαιρετικό</span><textarea name="description" maxlength="3000" rows="4">${esc(person.description)}</textarea></label>
        <fieldset class="field-stack"><legend>Προγραμματικές θέσεις</legend>${statements}</fieldset>
        ${includeSocials ? `<fieldset><legend>Σύνδεσμοι κοινωνικών δικτύων <span class="optional">Προαιρετικό</span></legend>
        <div class="two-col">${socialFields}</div></fieldset>` : ""}`;
}

function detailData(data) {
    return {
        description: data.get("description"),
        statements: data.getAll("statement").map(value => value.trim()).filter(Boolean),
        socials: Object.fromEntries(Object.keys(socialLabels).map(key => [key, data.get(key) || ""]))
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
function stage(el, video) {
    const id = encodeURIComponent(video.youtube_id);
    const title = esc(video.title);
    const poster = video.portraitPoster || `https://i.ytimg.com/vi/${id}/mqdefault.jpg`;
    el.innerHTML = `<img class="stage-photo" src="${poster}" alt="">
      <div class="stage-caption"><h3 class="reply-title">${title}</h3></div>
      <button class="play-main" aria-label="Αναπαραγωγή: ${title}">${icon("play")}</button>`;
    $(".play-main", el).onclick = () => {
        el.innerHTML = `<div class="stage-player">
          <iframe src="https://www.youtube-nocookie.com/embed/${id}?autoplay=1" title="${title}" allow="autoplay; fullscreen" allowfullscreen></iframe>
          <button class="circle stop" aria-label="Κλείσιμο αναπαραγωγής">${icon("close")}</button></div>`;
        $(".stop", el).onclick = () => {
            stage(el, video);
            $(".play-main", el).focus();
        };
        $(".stop", el).focus();
    };
}
const empty = message => `<p class="empty">${esc(message)}</p>`;
const dateText = value => new Date(value).toLocaleDateString("el-GR", {
    month: "short",
    day: "numeric",
    year: "numeric"
});

const newsDate = new Intl.DateTimeFormat("el-GR", { dateStyle: "medium", timeZone: "UTC" });

function newsItems(articles) {
    return articles.map(article => `<li>
        <a href="${esc(article.source)}" target="_blank" rel="noopener noreferrer">${esc(article.title)}</a>
        <small>${article.publisher ? esc(article.publisher) + " · " : ""}<time datetime="${esc(article.date)}">${newsDate.format(new Date(article.date))}</time></small>
    </li>`).join("");
}

async function loadProfileNews(section, id, isRelevant = () => true) {
    const output = $(".profile-news-status", section);
    const url = "/api/politicians/" + encodeURIComponent(id) + "/news?limit=5";
    try {
        const articles = await api(url).catch(async () => {
            await new Promise(resolve => setTimeout(resolve, 750));
            return api(url);
        });
        const relevant = articles.filter(isRelevant);
        if (!relevant.length) {
            output.textContent = "Δεν βρέθηκαν πρόσφατα δημοσιεύματα για αυτό το προφίλ.";
            return;
        }
        section.insertAdjacentHTML("beforeend", `<ul class="news-links">${newsItems(relevant)}</ul>`);
        output.remove();
    } catch {
        output.textContent = "Τα δημοσιεύματα δεν είναι προσωρινά διαθέσιμα.";
    }
}

export {
    $,
    $$,
    esc,
    icon,
    socialLabels,
    profileURL,
    avatar,
    api,
    status,
    bindForm,
    detailFields,
    detailData,
    login,
    bindLogout,
    stage,
    empty,
    dateText,
    newsItems,
    loadProfileNews
};
