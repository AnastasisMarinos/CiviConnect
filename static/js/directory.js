import {
    $,
    api,
    esc,
    icon,
    profileURL,
    empty
} from "./common.js";
try {
    const [people, replies] = await Promise.all([api("/api/politicians"), api("/api/video-replies")]);
    const counts = new Map();
    replies.forEach(r => counts.set(r.politician_id, (counts.get(r.politician_id) || 0) + 1));

    function render() {
        const search = $("#search").value.trim().toLowerCase();
        const list = people.filter(p => (p.name + " " + p.party).toLowerCase().includes(search));
        $("#result-count").textContent = `${list.length} verified candidate${list.length===1?"":"s"}`;
        $("#directory").innerHTML = list.map(p =>
            `<article class="candidate-card"><img class="avatar" src="${esc(p.photo_url)}" alt="${esc(p.name)}"><h2>${esc(p.name)} ${icon("badge","verified")}</h2><p>${esc(p.party)}</p><small>${counts.get(p.id)||0} video ${counts.get(p.id)===1?"reply":"replies"}</small><a class="btn" href="${profileURL(p.id)}">Explore profile</a></article>`
            ).join("") || empty(search ? "No candidates match your search." :
            "Verified candidates will appear here.");
    }
    $("#search").oninput = render;
    render();
} catch (e) {
    $("#directory").innerHTML = empty(e.message);
}
