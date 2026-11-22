import { $, api, bindForm, status, stage, empty, esc, profileURL, icon, avatar, newsItems, loadProfileNews } from "./common.js?v=profile-networks";
import { directoryNameWords, findProfileQuery, nameToken, nameWord, nameWords, surnameKey } from "./names.js?v=demo-search";

const form = $("#citizen-form");
const message = form.elements.content;
function updateCount() {
    $("#char-count").textContent = message.value.length.toLocaleString("el-GR") + " / 3.000";
}
message.addEventListener("input", updateCount);
message.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        if (!form.querySelector("button").disabled && message.value.trim()) form.requestSubmit();
    }
});

const track = $("#reply-track");
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");
function author(person, id, className) {
    return `<a class="${className}" href="${profileURL(id)}">${avatar(person)}
        <span><strong>${esc(person.name)} ${person.status === "verified" ? icon("badge","verified") : ""}</strong><small>${person.status === "demo" ? "Φανταστικό πρόσωπο" : esc(person.party)}</small></span></a>`;
}

function detectPoster(video) {
    return new Promise(resolve => {
        const image = new Image();
        const url = `https://i.ytimg.com/vi/${video.youtube_id}/oardefault.jpg`;
        const timeout = setTimeout(() => resolve(video), 2500);
        image.onload = () => {
            clearTimeout(timeout);
            resolve(image.naturalHeight > image.naturalWidth ? {...video, portraitPoster: url} : video);
        };
        image.onerror = () => {
            clearTimeout(timeout);
            resolve(video);
        };
        image.src = url;
    });
}

async function loadVideos() {
    const rows = (await api("/api/video-replies")).filter(video => /^[A-Za-z0-9_-]{11}$/.test(video.youtube_id));
    $("#position").textContent = rows.length + " βίντεο";
    if (rows.length < 2) {
        $("#prev").disabled = $("#next").disabled = true;
    }
    // Matching runs on both sides allow swipes and animated steps across the seam.
    // Repeat short runs so that each one can fill the carousel viewport.
    const videos = await Promise.all(rows.map(detectPoster));
    const run = [...videos];
    const widthUnits = run.reduce((total, video) => total + (video.portraitPoster ? 1 : 3), 0);
    if (videos.length > 1) {
        for (let units = widthUnits; units < 12; units += widthUnits) run.push(...videos);
    }
    const sequence = rows.length > 1 ? [...run, ...run, ...run] : videos;
    for (const video of sequence) {
        const card = document.createElement("article");
        card.className = video.portraitPoster ? "reply-card portrait" : "reply-card";
        card.innerHTML = '<div class="stage"></div>';
        stage($(".stage",card), video);
        track.append(card);
    }
    if (!rows.length) track.innerHTML = empty("Τα βίντεο του καναλιού μας θα εμφανίζονται εδώ.");
    if (rows.length < 2) return;
    const cards = Array.from(track.children);
    const dwellMs = 2900;
    const glideMs = 1750;
    let frame = 0;
    let touching = false;
    let lastActivity = performance.now();
    function position(index) {
        return cards[index].getBoundingClientRect().left - cards[0].getBoundingClientRect().left;
    }

    function nearestCard() {
        const x = track.scrollLeft;
        let closest = 0;
        for (let i = 1; i < cards.length; i++) {
            const offset = position(i);
            if (offset > x && offset - x > x - position(closest)) break;
            closest = i;
        }
        return closest;
    }

    function centerRun() {
        const x = track.scrollLeft;
        if (x < position(run.length) - 1 || x >= position(2 * run.length) - 1) {
            const index = nearestCard();
            track.scrollTo({left: position(run.length + index % run.length), behavior: "instant"});
        }
    }
    track.scrollTo({left: position(run.length), behavior: "instant"});

    function stopGlide() {
        cancelAnimationFrame(frame);
        frame = 0;
        track.classList.remove("gliding");
        lastActivity = performance.now();
    }

    function step(direction) {
        stopGlide();
        centerRun();
        const start = track.scrollLeft;
        const target = position(nearestCard() + direction);
        if (reduceMotion.matches) {
            track.scrollTo({left: target, behavior: "instant"});
            return;
        }
        // Temporarily suspend native snapping so it doesn't round each frame to a card.
        track.classList.add("gliding");
        const began = performance.now();
        function glide(now) {
            const progress = Math.min(1, (now - began) / glideMs);
            const eased = (1 - Math.cos(Math.PI * progress)) / 2;
            track.scrollTo({left: start + (target - start) * eased, behavior: "instant"});
            if (progress < 1) frame = requestAnimationFrame(glide);
            else {
                stopGlide();
                centerRun();
            }
        }
        frame = requestAnimationFrame(glide);
    }
    reduceMotion.addEventListener("change", stopGlide);
    document.addEventListener("visibilitychange", stopGlide);
    track.addEventListener("wheel", stopGlide, {passive:true});
    track.addEventListener("focusin", stopGlide);
    $("#prev").onclick = () => step(-1);
    $("#next").onclick = () => step(1);
    track.addEventListener("scroll", () => { lastActivity = performance.now(); }, {passive:true});
    track.addEventListener("scrollend", () => {
        if (!frame && !track.querySelector(":focus-visible, .stage-player")) centerRun();
    });
    track.addEventListener("pointerdown", () => { stopGlide(); touching = true; });
    function release() { touching = false; }
    window.addEventListener("pointerup", release);
    window.addEventListener("pointercancel", release);
    setInterval(() => {
        if (!frame && !reduceMotion.matches && !document.hidden && !touching && !track.querySelector(".stage-player")
            && !track.matches(":focus-visible") && !track.querySelector(":focus-visible")
            && performance.now() - lastActivity >= dwellMs) step(1);
    }, 100);
}
track.addEventListener("click", event => {
    if (event.target.closest(".play-main")) track.querySelector(".stop")?.click();
}, true);
loadVideos().catch(error => {
    track.innerHTML = empty(error.message);
    $("#prev").disabled = $("#next").disabled = true;
});

function shuffle(items) {
    const result = [...items];
    for (let i=result.length-1; i>0; i--) {
        const j=Math.floor(Math.random()*(i+1));
        [result[i],result[j]]=[result[j],result[i]];
    }
    return result;
}

const publicPeople = api("/api/politicians");

async function loadPeople() {
    const people = await publicPeople;
    const grid = $("#featured-grid");
    let shown = [];
    function rotate() {
        const previous = new Set(shown.map(p => p.id));
        const fresh = shuffle(people.filter(p => !previous.has(p.id)));
        shown = [...fresh, ...shuffle(shown)].slice(0,6);
        shown = shuffle(shown);
        grid.innerHTML = shown.map(p => author(p,p.id,"featured-person")).join("") || empty("Τα μέλη του Δημοτικού Συμβουλίου θα εμφανίζονται εδώ.");
    }
    rotate();
    if (people.length < 2) return;

    const timer = $("#people-rotation");
    const countdown = $("#people-remaining");
    const rotationMs = 12000;
    let remaining = rotationMs;
    let previousTick = performance.now();
    let rotating = false;
    const isPaused = () => document.hidden || grid.contains(document.activeElement);

    function displayTimer() {
        const label = isPaused() ? "Η αλλαγή έχει παγώσει" : `Αλλαγή σε ${Math.ceil(remaining / 1000)} δευτ.`;
        if (countdown.textContent !== label) countdown.textContent = label;
    }
    timer.hidden = false;
    displayTimer();
    document.addEventListener("visibilitychange", () => { previousTick = performance.now(); });
    setInterval(async () => {
        const now = performance.now();
        const elapsed = now - previousTick;
        previousTick = now;
        if (rotating) return;
        if (!isPaused()) remaining = Math.max(0, remaining - elapsed);
        displayTimer();
        if (isPaused() || remaining > 0) return;

        rotating = true;
        if (!reduceMotion.matches) await grid.animate([{opacity:1},{opacity:0}], {duration:250}).finished;
        if (!isPaused()) {
            rotate();
            remaining = rotationMs;
            if (!reduceMotion.matches) grid.animate([{opacity:0},{opacity:1}], {duration:300});
        }
        previousTick = performance.now();
        rotating = false;
        displayTimer();
    }, 100);
}
loadPeople().catch(error => { $("#featured-grid").innerHTML = empty(error.message); });


const footerElection = $(".footer-election");
const footerRow = $(".footer-inner");
$(".footer-links", footerRow).before(footerElection);

api("/api/config").catch(() => ({})).then(config => {
    const configured = new Date(config.election_datetime_iso || "");
    const estimated = !Number.isFinite(+configured);
    const target = estimated ? new Date("2028-11-26T00:00:00+02:00") : configured;
    const athensDate = { timeZone: "Europe/Athens" };
    const year = new Intl.DateTimeFormat("el-GR", { ...athensDate, year: "numeric" }).format(target);
    const municipality = config.municipality_name || "Δήμος Αθηναίων";
    $("[data-election-area]").textContent = `${municipality} · ${estimated ? "Δημοτική συμμετοχή" : "Δημοτικές εκλογές " + year}`;

    const clock = $(".footer-clock");
    const units = [["Days", 86400], ["Hours", 3600], ["Minutes", 60], ["Seconds", 1]]
        .map(([label, divisor]) => [$("#time-" + label), divisor]);

    function tick() {
        let seconds = Math.ceil((target - Date.now()) / 1000);
        if (seconds <= 0) {
            $("#election-label").textContent = "Δημοτικές εκλογές";
            clock.hidden = true;
            return;
        }
        for (const [element, divisor] of units) {
            element.textContent = String(Math.floor(seconds / divisor)).padStart(2, "0");
            seconds %= divisor;
        }
        setTimeout(tick, 1000);
    }
    tick();
    footerRow.classList.add("has-election");
    footerElection.hidden = false;
});
const answerBox = $("#civic-answer");
const answerStatus = $(".status", form);
const dateLabel = new Intl.DateTimeFormat("el-GR", { dateStyle: "medium", timeZone: "UTC" });
const sourceTypes = {
    introduced: "Εισήγηση θέματος",
    summary: "Σύνοψη τοποθέτησης OpenCouncil",
    statement: "Απόσπασμα τοποθέτησης",
    decision: "Δημοτική πράξη · Διαύγεια",
    report: "Απόσπασμα δημοσιεύματος"
};
const claimStages = {statement: "Δήλωση", proposal: "Πρόταση", approval: "Έγκριση", implementation: "Υλοποίηση"};
const assessments = {
    supported: "Τεκμηριώνεται", partial: "Μερική τεκμηρίωση",
    conflicting: "Αντικρουόμενες πηγές", unconfirmed: "Δεν βρέθηκε επιβεβαίωση"
};

function localMessage(answer) {
    if (answer.status === "index_unavailable") {
        return "Το αρχείο των συνεδριάσεων δεν είναι ακόμη διαθέσιμο.";
    }
    if (answer.status !== "answered") {
        return "Δεν βρήκα αρκετά σχετικά στοιχεία στις συνεδριάσεις των τελευταίων 365 ημερών. Μπορείς να δοκιμάσεις ένα πιο συγκεκριμένο θέμα ή να αναφέρεις τη γειτονιά που σε ενδιαφέρει.";
    }
    const names = new Intl.ListFormat("el-GR");
    const people = names.format(answer.people.map(person => person.name));
    const groups = names.format(answer.parties.map(party => party.name));
    const subject = answer.topic ? ` για το θέμα «${answer.topic}»` : "";
    const affiliation = groups ? ` Στις σχετικές συνεδριάσεις τοποθετήθηκαν μέλη από τις εξής παρατάξεις: ${groups}.` : "";
    if (!people) {
        return "Βρήκα σχετικά δημόσια έγγραφα ή δημοσιεύματα. Μπορείς να τα ανοίξεις από τις πηγές παρακάτω.";
    }
    return `Στις συνεδριάσεις που έψαξα${subject}, βρήκα σχετικές εισηγήσεις ή τοποθετήσεις από τους εξής εκπροσώπους: ${people}.${affiliation}

Στις πηγές μπορείς να δεις τι εισηγήθηκε ή τι ανέφερε κάθε εκπρόσωπος.`;
}

function displayProfileResult(matches) {
    const person = matches.length === 1 ? matches[0] : null;
    const notice = matches.length ? "Βρέθηκαν περισσότερα προφίλ με αυτό το όνομα. Γράψτε το πλήρες όνομα." :
        "Δεν βρέθηκε δημόσιο προφίλ με αυτό το όνομα.";
    const card = person ? `
        <div class="profile-match">
            ${avatar(person)}<div>
                <h2 id="profile-result-title" tabindex="-1"><a class="chat-profile-link" href="${profileURL(person.id)}">${esc(person.name)}</a></h2>
                ${person.status === "demo" ? "<small>Φανταστικό πρόσωπο</small>" : ""}
                <p>${esc([person.role, person.party].filter(Boolean).join(" · "))}</p>
            </div>
        </div>
        <section class="person-news" aria-labelledby="profile-result-news-title">
            <h3 id="profile-result-news-title">Πρόσφατα δημοσιεύματα από το Google News</h3>
            <p class="profile-news-status" role="status">Αναζήτηση δημοσιευμάτων…</p>
        </section>` : `<h2 id="profile-result-title" tabindex="-1">Αναζήτηση προφίλ</h2><p>${esc(notice)}</p>`;
    answerBox.innerHTML = `<section class="chat-reply" aria-labelledby="profile-result-title">${card}</section>`;
    answerBox.hidden = false;
    $("#profile-result-title").focus();
    if (person) {
        const surname = surnameKey(person);
        loadProfileNews($(".person-news", answerBox), person.id, article =>
            (" " + nameWords(article.title).join(" ") + " ").includes(" " + surname + " "));
    }
}

function profileLinker(people, onMention) {
    const nameSeparator = /^[\p{Zs}\p{Pd}\t]+$/u;
    const profiles = new Map();
    let longestName = 0;
    for (const person of people) {
        const words = directoryNameWords(person);
        if (words.length < 2) continue;
        const name = words.join(" ");
        profiles.set(name, profiles.has(name) ? null : person);
        longestName = Math.max(longestName, words.length);
    }

    return message => {
        const words = Array.from(message.matchAll(nameToken));
        const normalized = words.map(word => nameWord(word[0]));
        let html = "";
        let cursor = 0;
        for (let i = 0; i < words.length; i++) {
            let name = normalized[i];
            let match;
            for (let j = i + 1; j < Math.min(words.length, i + longestName); j++) {
                const previousEnd = words[j - 1].index + words[j - 1][0].length;
                if (!nameSeparator.test(message.slice(previousEnd, words[j].index))) break;
                name += " " + normalized[j];
                if (profiles.has(name)) match = {index: j, person: profiles.get(name)};
            }
            if (!match?.person) continue;
            const start = words[i].index;
            const end = words[match.index].index + words[match.index][0].length;
            html += esc(message.slice(cursor, start));
            html += `<a class="chat-profile-link" href="${profileURL(match.person.id)}">${esc(message.slice(start, end))}</a>`;
            onMention(match.person);
            cursor = end;
            i = match.index;
        }
        return html + esc(message.slice(cursor));
    };
}

async function loadPersonNews(section, people) {
    for (let i = 0; i < people.length; i += 3) {
        const batch = people.slice(i, i + 3);
        const results = await Promise.all(batch.map(async person => {
            const articles = await api("/api/politicians/" + encodeURIComponent(person.id) + "/news")
                .catch(() => []);
            if (!articles.length) return "";
            return `<div class="person-news-group">
                <h4><a class="chat-profile-link" href="${profileURL(person.id)}">${esc(person.name)}</a></h4>
                <ul class="news-links">${newsItems(articles)}</ul>
            </div>`;
        }));
        if (!section.isConnected || answerBox.hidden) return;
        const groups = results.join("");
        if (groups) {
            section.insertAdjacentHTML("beforeend", groups);
            section.hidden = false;
        }
    }
}

function displayAnswer(question, answer, people) {
    const mentioned = new Map();
    const linkProfiles = profileLinker(people, person => mentioned.set(person.id, person));
    const reply = linkProfiles(answer.message || localMessage(answer));
    const sourceById = new Map(answer.sources.map(source => [source.id, source]));
    const sources = answer.sources.map(source => `<li class="evidence-card">
        <span class="evidence-meta">${esc(sourceTypes[source.kind])} · ${dateLabel.format(new Date(source.date))}</span>
        <strong>${esc(source.speaker || source.publisher)}${source.party ? " · " + esc(source.party) : ""}</strong>
        ${source.ada ? `<small>ΑΔΑ ${esc(source.ada)}${source.scope === "metadata" ? " · Τίτλος πράξης" : ""}</small>` : ""}
        <p>${esc(source.text)}</p>
        <a href="${esc(source.source)}" target="_blank" rel="noopener noreferrer">${esc(source.title || "Συνεδρίαση στο OpenCouncil")}</a>
    </li>`).join("");
    const checks = (answer.checks || []).map(check => {
        const links = check.evidence_ids.map(id => sourceById.get(id)).filter(Boolean);
        return `<li class="claim-check">
            <div class="claim-meta"><span>${esc(claimStages[check.stage])}</span>
                <strong>${esc(assessments[check.assessment])}</strong></div>
            <p>${linkProfiles(check.claim)}</p>
            ${links.length ? `<ul class="claim-links">${links.map(source =>
                `<li><a href="${esc(source.source)}" target="_blank" rel="noopener noreferrer">${esc(source.ada || source.title || "Πρακτικά OpenCouncil")}</a></li>`
            ).join("")}</ul>` : ""}
        </li>`;
    }).join("");
    const headlines = newsItems(answer.headlines || []);
    const coverage = answer.source_coverage || {};
    const unavailable = Object.entries({decision: "Διαύγεια", headlines: "Google News", report: "ΕΡΤ"})
        .filter(([kind]) => coverage[kind] === "unavailable").map(([, name]) => name);
    answerBox.innerHTML = `<div class="chat-question">${esc(question)}</div>
        <section class="chat-reply" aria-labelledby="evidence-title">
            <h2 id="evidence-title" tabindex="-1">${icon("mark")} CiviConnect</h2>
            <p class="chat-message">${reply}</p>
            ${checks ? `<h3 class="claim-heading">Έλεγχος ισχυρισμών</h3><ul class="claim-list">${checks}</ul>` : ""}
            ${sources ? `<details class="chat-sources"><summary>Πηγές τεκμηρίωσης (${answer.sources.length})</summary><ul class="evidence-sources">${sources}</ul></details>` : ""}
            ${headlines ? `<details class="chat-sources"><summary>Σχετικοί τίτλοι από το Google News</summary><ul class="news-links">${headlines}</ul></details>` : ""}
            ${mentioned.size ? `<section class="person-news" aria-labelledby="person-news-title" hidden><h3 id="person-news-title">Πρόσφατα δημοσιεύματα για τους εκπροσώπους</h3></section>` : ""}
            ${unavailable.length ? `<p class="evidence-meta source-availability">Προσωρινά μη διαθέσιμες πηγές: ${esc(unavailable.join(", "))}</p>` : ""}
        </section>`;
    answerBox.hidden = false;
    $("#evidence-title").focus();
    if (mentioned.size) loadPersonNews($(".person-news", answerBox), [...mentioned.values()]);
}

bindForm(form, async data => {
    const content = data.get("content").trim();
    if (!content) throw Error("Γράψτε πρώτα μια ερώτηση ή ένα μήνυμα.");
    answerBox.hidden = true;
    status(answerStatus, "Αναζητώ προφίλ ή σχετικές πηγές…");
    const people = await api("/api/politicians", "GET", undefined, "no-store").catch(() => []);
    const profiles = findProfileQuery(content, people);
    if (profiles) {
        status(answerStatus);
        displayProfileResult(profiles);
        return;
    }
    status(answerStatus, "Ελέγχω τις διαθέσιμες πηγές…");
    const answer = await api("/api/athens/answer", "POST", {question: content});
    status(answerStatus);
    displayAnswer(content, answer, people);
});
