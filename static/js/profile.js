import {
    $,
    $$,
    api,
    esc,
    icon,
    stage,
    empty
} from "./common.js";
try {
    const id = new URLSearchParams(location.search).get("id");
    if (!id) throw Error("Choose a candidate from the directory to see their profile.");
    const [p, all] = await Promise.all([api("/api/politicians/" + encodeURIComponent(id)), api(
        "/api/video-replies")]);
    const replies = all.filter(r => r.politician_id === id);
    document.title = p.name + " · CiviConnect";
    const links = Object.entries(p.socials).filter(([, url]) => /^https?:\/\//i.test(url)).map(([k, url]) =>
        `<a href="${esc(url)}" rel="noopener noreferrer" target="_blank">${esc({x:"X",instagram:"Instagram",tiktok:"TikTok",website:"Website"}[k])}</a>`
        ).join("");
    $("#profile").innerHTML =
        `<div class="profile-hero"><img class="avatar" src="${esc(p.photo_url)}" alt="${esc(p.name)}"><div><div class="eyebrow">${icon("badge","verified")} Verified candidate</div><h1>${esc(p.name)}</h1><p>${esc(p.party)}</p></div></div>
      <div class="profile-info"><article class="panel"><h2>About ${esc(p.name.split(" ")[0])}</h2><p>${esc(p.description)}</p><div class="socials">${links}</div></article>
      <article class="panel"><h2>Policy statements</h2><ul>${p.statements.map(s=>`<li>${esc(s)}</li>`).join("")}</ul></article></div>
      <section class="profile-replies"><h2>Video replies</h2><div class="video-grid">${replies.map(()=>'<div class="stage"></div>').join("")||empty("No video replies published yet.")}</div></section>`;
    $$(".video-grid .stage").forEach((el, i) => stage(el, replies[i]));
} catch (e) {
    $("#profile").innerHTML = empty(e.message);
}
