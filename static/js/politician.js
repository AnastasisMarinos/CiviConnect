import {
    $,
    $$,
    api,
    esc,
    status,
    bindForm,
    detailFields,
    detailData,
    login,
    bindLogout,
    empty,
    dateText,
    profileURL
} from "./common.js";
if ($("#login")) login("politician");
else startDashboard();
async function startDashboard() {
    const root = $("#workspace");
    let data, selected = 0,
        sourceQuestion = null,
        query = "";
    bindLogout("politician");
    const reload = async () => {
        data = await api("/api/politician/workspace");
    };

    function showTab(i) {
        selected = i;
        $$("[data-tab]").forEach((b, j) => {
            b.classList.toggle("active", j === i);
            b.setAttribute("aria-pressed", String(j === i));
        });
        status($("#dashboard-status"));
        [planner, publisher, myProfile][i]();
    }
    $$("[data-tab]").forEach(b => b.onclick = () => showTab(Number(b.dataset.tab)));

    function planner() {
        root.innerHTML =
            `<h2>Citizen submissions</h2><div class="toolbar"><input id="plan-search" type="search" aria-label="Search submissions" placeholder="Search questions or topics" value="${esc(query)}"></div><div id="plans"></div>`;

        function list() {
            const items = data.submissions.filter(s => (s
                .content + " " + s.topic).toLowerCase().includes(query.toLowerCase()));
            $("#plans").innerHTML = items.map(s =>
                `<article class="record"><small>${s.topic ? esc(s.topic) + " · " : ""}${dateText(s.submitted_at)}</small>
              <h3>${esc(s.content)}</h3><form class="form-stack" data-plan="${esc(s.id)}"><div class="two-col"><label>Planning status<select name="flag">${[["","Unmarked"],["planned","Planned"],["answered","Answered"]].map(([v,t])=>`<option value="${v}" ${s.politician_flags[data.profile.id]===v?"selected":""}>${t}</option>`).join("")}</select></label><label>Private campaign note<textarea name="note" rows="2" maxlength="3000">${esc(data.notes[s.id])}</textarea></label></div>
              <div class="actions"><button class="btn">Save plan</button><button class="btn primary" type="button" data-reply="${esc(s.id)}">Reply with video</button></div><p class="status" role="status"></p></form></article>`
                ).join("") || empty("No submissions match these filters.");
            $$("[data-plan]").forEach(form => bindForm(form, async fields => {
                const sid = form.dataset.plan;
                const body = Object.fromEntries(fields);
                await api("/api/politician/planner/" + sid, "PUT", body);
                data.notes[sid] = body.note;
                data.submissions.find(s => s.id === sid).politician_flags[data.profile
                    .id] = body.flag;
                status($(".status", form), "Plan saved.");
            }));
            $$("[data-reply]").forEach(b => b.onclick = () => {
                sourceQuestion = data.submissions.find(s => s.id === b.dataset.reply);
                showTab(1);
                root.scrollIntoView({
                    block: "start"
                });
            });
        }
        $("#plan-search").oninput = e => {
            query = e.target.value;
            list();
        };
        list();
    }

    function publisher() {
        root.innerHTML = `<form id="publish" class="panel form-stack wide-form"><h2>Publish a video reply</h2>
          <label>Reply to<select name="question_id" id="question-id"><option value="">Custom question or topic</option>${data.submissions.map(s=>`<option value="${esc(s.id)}">${esc(s.content)}</option>`).join("")}</select></label>
          <label>Question or topic<textarea name="question_prompt" required maxlength="3000" rows="3"></textarea></label>
          <fieldset><legend>Video source</legend><div class="pills"><label><input type="radio" name="source" value="youtube" checked><span>YouTube link</span></label><label><input type="radio" name="source" value="upload"><span>Upload video</span></label></div></fieldset>
          <label id="youtube-field">YouTube or Shorts URL<input name="youtube_url" type="url" required placeholder="https://www.youtube.com/watch?v=…"></label>
          <label id="upload-field" hidden>Video file<input name="video" type="file" accept="video/mp4,video/webm" disabled><small>MP4 or WebM, up to 64 MB.</small></label>
          <label>Aspect ratio<select name="aspect_ratio"><option value="auto">Automatic (vertical for Shorts)</option><option value="vertical">Vertical (9:16)</option><option value="horizontal">Horizontal (16:9)</option></select></label>
          <button class="btn primary">Publish reply</button><p class="status" role="status"></p></form>`;
        const form = $("#publish"),
            prompt = form.elements.question_prompt;

        function linkQuestion() {
            sourceQuestion = data.submissions.find(s => s.id === form.elements.question_id.value) ||
                null;
            prompt.value = sourceQuestion?.content || "";
            prompt.readOnly = !!sourceQuestion;
        }
        form.elements.question_id.value = sourceQuestion?.id || "";
        linkQuestion();
        form.elements.question_id.onchange = linkQuestion;
        $$("[name=source]", form).forEach(b => b.onchange = () => {
            const upload = form.elements.source.value === "upload";
            $("#youtube-field").hidden = upload;
            $("#upload-field").hidden = !upload;
            form.elements.video.disabled = !upload;
            form.elements.video.required = upload;
            form.elements.youtube_url.required = !upload;
            form.elements.youtube_url.disabled = upload;
        });
        bindForm(form, async fields => {
            fields.delete("source");
            if (fields.get("video")?.size > 64 * 1024 ** 2) throw Error(
                "Choose a video smaller than 64 MB.");
            await api("/api/politician/replies", "POST", fields);
            sourceQuestion = null;
            await reload();
            showTab(2);
            status($("#dashboard-status"),
                "Video published to the public square and your profile.");
        });
    }

    function myProfile() {
        root.innerHTML =
            `<h2>My video replies</h2>${data.replies.map(r=>`<article class="record"><small>${dateText(r.created_at)}</small><h3>${esc(r.question_prompt)}</h3><button class="btn danger" data-remove="${esc(r.id)}">Delete reply</button></article>`).join("")||empty("You haven’t published a reply yet.")}
          <form id="edit-profile" class="panel form-stack wide-form"><div class="section-head"><h2>Edit my profile</h2><a href="${profileURL(data.profile.id)}">View profile</a></div>${detailFields(data.profile)}<button class="btn primary">Save profile</button><p class="status" role="status"></p></form>`;
        $$("[data-remove]").forEach(b => b.onclick = async () => {
            if (!confirm("Delete this video reply from your profile and the homepage?"))
                return;
            b.disabled = true;
            try {
                await api("/api/politician/replies/" + b.dataset.remove, "DELETE");
                await reload();
                showTab(2);
            } catch (e) {
                status($("#dashboard-status"), e.message, true);
                b.disabled = false;
            }
        });
        bindForm($("#edit-profile"), async fields => {
            const body = detailData(fields);
            await api("/api/politician/profile", "PUT", body);
            Object.assign(data.profile, body);
            status($("#edit-profile .status"), "Profile updated.");
        });
    }
    try {
        await reload();
        $("#workspace-name").textContent = data.profile.name + " · " + data.profile.party;
        showTab(selected);
    } catch (e) {
        status($("#dashboard-status"), e.message, true);
    }
}
