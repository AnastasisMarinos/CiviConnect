import { $, api, bindForm, status, stage, empty, esc, profileURL, icon } from "./common.js";

const form = $("#citizen-form");
const message = form.elements.content;
function updateCount() {
    $("#char-count").textContent = message.value.length.toLocaleString() + " / 3,000";
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
    return `<a class="${className}" href="${profileURL(id)}"><img class="avatar" src="${esc(person.photo_url)}" alt="">
        <span><strong>${esc(person.name)} ${icon("badge","verified")}</strong><small>${esc(person.party)}</small></span></a>`;
}

async function loadReplies() {
    const rows = await api("/api/video-replies");
    $("#position").textContent = rows.length + (rows.length === 1 ? " reply" : " replies");
    if (rows.length < 2) {
        $("#prev").disabled = $("#next").disabled = true;
    }
    // Matching runs on both sides allow swipes and animated steps across the seam.
    // A run must be wider than the largest (three-card) viewport.
    const run = rows.length > 1 && rows.length < 4 ? rows.concat(rows) : rows;
    const sequence = rows.length > 1 ? [...run, ...run, ...run] : rows;
    for (const reply of sequence) {
        const card = document.createElement("article");
        card.className = "reply-card";
        card.innerHTML = '<div class="stage"></div>' + author(reply, reply.politician_id, "reply-author");
        stage($(".stage",card), reply);
        track.append(card);
    }
    if (!rows.length) track.innerHTML = empty("Published video replies will appear here.");
    if (rows.length < 2) return;
    const cards = Array.from(track.children);
    const dwellMs = 1500;
    const glideMs = 1200;
    let frame = 0;
    let touching = false;
    let lastActivity = performance.now();
    const stride = () => cards[1].getBoundingClientRect().left - cards[0].getBoundingClientRect().left;

    function centerRun() {
        const width = stride() * run.length;
        if (!width) return;
        const x = track.scrollLeft;
        if (x < width - 1 || x >= 2 * width - 1) {
            const index = Math.round(x / stride());
            track.scrollTo({left: (run.length + index % run.length) * stride(), behavior: "instant"});
        }
    }
    track.scrollTo({left: run.length * stride(), behavior: "instant"});

    function stopGlide() {
        cancelAnimationFrame(frame);
        frame = 0;
        track.classList.remove("gliding");
        lastActivity = performance.now();
    }

    function step(direction) {
        stopGlide();
        centerRun();
        const width = stride();
        if (!width) return;
        const start = track.scrollLeft;
        const target = (Math.round(start / width) + direction) * width;
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
// Opening a second player also stops embedded YouTube playback in the first.
track.addEventListener("click", event => {
    if (event.target.closest(".play-main")) track.querySelector(".stop")?.click();
}, true);
loadReplies().catch(error => {
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

async function loadPeople() {
    const people = await api("/api/politicians");
    const grid = $("#featured-grid");
    let shown = [];
    function rotate() {
        const previous = new Set(shown.map(p => p.id));
        const fresh = shuffle(people.filter(p => !previous.has(p.id)));
        shown = [...fresh, ...shuffle(shown)].slice(0,6);
        shown = shuffle(shown);
        grid.innerHTML = shown.map(p => author(p,p.id,"featured-person")).join("") || empty("Verified candidates will appear here.");
    }
    rotate();
    if (people.length > 1) setInterval(async () => {
        if (document.hidden || grid.contains(document.activeElement)) return;
        if (!reduceMotion.matches) await grid.animate([{opacity:1},{opacity:0}], {duration:300}).finished;
        if (grid.contains(document.activeElement)) return;
        rotate();
        if (!reduceMotion.matches) grid.animate([{opacity:0},{opacity:1}], {duration:350});
    }, 30000);
}
loadPeople().catch(error => { $("#featured-grid").innerHTML = empty(error.message); });


api("/api/config").then(config => {
    const target = new Date(config.election_datetime_iso);
    $("[data-election-area]").textContent =
        `${config.municipality_name} · ${config.election_datetime_iso.slice(0,4)} election hub`;
    $("#election-date").textContent = new Intl.DateTimeFormat("en", {
        dateStyle: "long",
        timeZone: "UTC"
    }).format(new Date(config.election_datetime_iso.slice(0, 10) + "T12:00:00Z"));

    function tick() {
        let seconds = Math.max(0, Math.floor((target - Date.now()) / 1000));
        for (const [label, divisor] of [
                ["Days", 86400],
                ["Hours", 3600],
                ["Minutes", 60],
                ["Seconds", 1]
            ]) {
            $("#time-" + label).textContent = String(Math.floor(seconds / divisor)).padStart(2,
            "0");
            seconds %= divisor;
        }
        if (Date.now() >= +target) $("#election-label").textContent = "Election day has arrived";
    }
    tick();
    setInterval(tick, 1000);
}).catch(e => {
    $("#election-date").textContent = e.message;
});
bindForm($("#citizen-form"), async data => {
    await api("/api/submissions", "POST", Object.fromEntries(data));
    $("#citizen-form").reset();
    updateCount();
    status($("#citizen-form .status"),
        "Submission received. Verified candidates can now read your message.");
});
