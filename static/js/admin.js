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
    icon
} from "./common.js";
if ($("#login")) login("admin");
else startDashboard();
async function startDashboard() {
    const root = $("#workspace"),
        output = $("#dashboard-status");
    let data, credential = null;
    const reload = async () => {
        data = await api("/api/admin/workspace");
    };
    bindLogout("admin");

    function showTab(index) {
        $$("[data-tab]").forEach((b, i) => {
            b.classList.toggle("active", index === i);
            b.setAttribute("aria-pressed", String(index === i));
        });
        status(output);
        [verification, manage, submissions, contacts][index]();
    }
    $$("[data-tab]").forEach(b => b.onclick = () => showTab(Number(b.dataset.tab)));

    function personCard(p, actions, details = false) {
        return `<article class="record"><div class="person-line"><img class="avatar" src="${esc(p.photo_url)}" alt=""><div><h3>${esc(p.name)}</h3><span>${esc(p.party)}</span></div></div>
          ${details?`<p>${esc(p.description)}</p><p>${esc(p.verification_email)}</p><ul>${p.statements.map(s=>`<li>${esc(s)}</li>`).join("")}</ul>`:""}
          <div class="actions">${actions}</div></article>`;
    }

    function verification() {
        const pending = data.people.filter(p => p.status === "pending");
        const approved = data.people.filter(p => p.status === "verified");
        root.innerHTML =
            `<div id="issued"></div><h2>Pending verification (${pending.length})</h2>${pending.map(p=>personCard(p,`<button class="btn primary" data-issue="approve" data-id="${esc(p.id)}">Approve &amp; generate credentials</button>`,true)).join("")||empty("No applications awaiting verification.")}
          <h2>Verified candidate credentials</h2>${approved.map(p=>personCard(p,`<button class="btn" data-issue="regenerate" data-id="${esc(p.id)}">Regenerate credentials</button>`)).join("")||empty("No verified candidates yet.")}`;
        if (credential) {
            const {
                person,
                account
            } = credential;
            const message =
                `Username: ${account.login_username}\nTemporary password: ${account.temporary_password}`;
            $("#issued").innerHTML =
                `<div class="credentials"><strong>Credentials for ${esc(person.name)}</strong><pre>${esc(message)}</pre><div class="actions"><button id="copy" class="btn">Copy credentials</button><a class="btn" href="mailto:${encodeURIComponent(person.verification_email)}?subject=${encodeURIComponent("Your CiviConnect candidate credentials")}&body=${encodeURIComponent(message)}">Draft email</a><button class="btn" id="dismiss">Dismiss</button></div><p class="status" role="status"></p></div>`;
            $("#copy").onclick = async () => {
                try {
                    await navigator.clipboard.writeText(message);
                    status($("#issued .status"), "Credentials copied.");
                } catch {
                    status($("#issued .status"),
                        "Select the username and password above to copy them.");
                }
            };
            $("#dismiss").onclick = () => {
                credential = null;
                $("#issued").replaceChildren();
            };
        }
        $$("[data-issue]").forEach(b => b.onclick = async () => {
            if (b.dataset.issue === "regenerate" && !confirm(
                    "Replace this candidate’s password and end their current sessions?"))
                return;
            b.disabled = true;
            try {
                const account = await api(
                    `/api/admin/politicians/${b.dataset.id}/${b.dataset.issue}`, "POST");
                credential = {
                    person: data.people.find(p => p.id === b.dataset.id),
                    account
                };
                await reload();
                verification();
                $("#issued").scrollIntoView({
                    block: "center"
                });
            } catch (e) {
                status(output, e.message, true);
                b.disabled = false;
            }
        });
    }

    function manage() {
        const people = data.people.filter(p => p.status === "verified");
        root.innerHTML =
            `<h2>Verified candidates</h2>${people.map(p=>personCard(p,`<button class="btn" data-edit="${esc(p.id)}">Edit candidate</button><button class="btn danger" data-delete="politicians" data-id="${esc(p.id)}">Delete candidate</button>`)).join("")||empty("No verified candidates yet.")}
        <h2>Published replies</h2>${data.replies.map(r=>`<article class="record"><small>${esc(r.name)} · ${dateText(r.created_at)}</small><h3>${esc(r.question_prompt)}</h3><a href="/profile.html?id=${encodeURIComponent(r.politician_id)}">View on profile</a><div class="actions"><button class="btn danger" data-delete="replies" data-id="${esc(r.id)}">Remove reply</button></div></article>`).join("")||empty("No video replies published.")}
        <dialog id="editor"><div class="dialog-head"><h2>Edit candidate</h2><button data-close class="circle" aria-label="Close">${icon("close")}</button></div><div id="edit-body"></div></dialog>`;
        $$("[data-edit]").forEach(b => b.onclick = () => {
            const p = data.people.find(p => p.id === b.dataset.edit);
            $("#edit-body").innerHTML =
                `<form id="admin-edit" class="form-stack"><label>Name<input name="name" required maxlength="160" value="${esc(p.name)}"></label><label>Party<input name="party" required maxlength="160" value="${esc(p.party)}"></label>${detailFields(p)}<button class="btn primary">Save candidate</button><p class="status" role="status"></p></form>`;
            bindForm($("#admin-edit"), async fields => {
                await api("/api/admin/politicians/" + p.id, "PUT", {
                    ...detailData(fields),
                    name: fields.get("name"),
                    party: fields.get("party")
                });
                await reload();
                $("#editor").close();
                manage();
                status(output, "Candidate updated.");
            });
            $("#editor").showModal();
        });
        $$("[data-delete]").forEach(b => b.onclick = async () => {
            const candidates = b.dataset.delete === "politicians";
            if (!confirm(candidates ?
                    "Delete this candidate, their planner notes, and all their replies?" :
                    "Remove this video reply from the homepage and profile?")) return;
            b.disabled = true;
            try {
                await api(`/api/admin/${b.dataset.delete}/${b.dataset.id}`, "DELETE");
                await reload();
                manage();
                status(output, "Removed.");
            } catch (e) {
                status(output, e.message, true);
                b.disabled = false;
            }
        });
    }

    function submissions() {
        root.innerHTML =
            `<h2>Citizen submissions</h2><p class="subtle">The JSONL feed preserves the original submissions. The JSON bundle includes current planning flags.</p><div class="toolbar"><a class="btn primary" href="/api/admin/export/llm-dataset?format=jsonl" download>Download JSONL</a><a class="btn" href="/api/admin/export/llm-dataset" download>Download JSON bundle</a></div>${data.submissions.map(s=>`<article class="record"><small>${s.topic ? esc(s.topic) + " · " : ""}${dateText(s.submitted_at)}</small><p>${esc(s.content)}</p></article>`).join("")||empty("No citizen submissions yet.")}`;
    }

    function contacts() {
        root.innerHTML =
            `<h2>Contact messages</h2>${data.contacts.map(c=>`<article class="record"><small>${dateText(c.submitted_at)}</small><h3>${esc(c.name)}</h3><a href="mailto:${encodeURIComponent(c.email)}">${esc(c.email)}</a><p>${esc(c.message)}</p></article>`).join("")||empty("No contact messages yet.")}`;
    }
    try {
        await reload();
        showTab(0);
    } catch (e) {
        status(output, e.message, true);
    }
}
