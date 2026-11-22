import {
    $,
    api,
    esc,
    icon,
    avatar,
    profileURL,
    empty
} from "./common.js?v=workspace-cleanup";
import { searchDirectory } from "./names.js?v=workspace-cleanup";
try {
    const [people, groups] = await Promise.all([api("/api/politicians"), api("/api/parties")]);
    const group = $("#party-filter");
    for (const party of groups.sort((a, b) => a.name.localeCompare(b.name, "el"))) {
        group.add(new Option(party.name, party.id));
    }
    group.hidden = !groups.length;

    function render() {
        const search = $("#search").value.trim();
        const list = searchDirectory(people, search).filter(p => !group.value || p.party_id === group.value);
        $("#result-count").textContent = `${list.length} προφίλ`;
        $("#directory").innerHTML = list.map(p =>
            `<article class="candidate-card">${avatar(p)}<h2>${esc(p.name)} ${p.status === "verified" ? icon("badge","verified") : ""}</h2><p>${esc(p.party)}</p>${p.status === "demo" ? "<small>Φανταστικό πρόσωπο</small>" : p.role ? `<small>${esc(p.role)}</small>` : ""}<a class="btn" href="${profileURL(p.id)}">Προβολή προφίλ</a></article>`
            ).join("") || empty(search || group.value ? "Δεν βρέθηκαν εκπρόσωποι με αυτά τα κριτήρια." :
            "Ο κατάλογος εκπροσώπων δεν έχει ακόμη διαθέσιμα προφίλ.");
    }
    $("#search").oninput = render;
    group.onchange = render;
    render();
} catch (e) {
    $("#directory").innerHTML = empty(e.message);
}
