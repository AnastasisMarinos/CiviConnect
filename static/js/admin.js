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
    icon,
    avatar
} from "./common.js?v=workspace-cleanup";
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
        [verification, manage, contacts][index]();
    }
    $$("[data-tab]").forEach(b => b.onclick = () => showTab(Number(b.dataset.tab)));

    function personCard(p, actions, details = false) {
        return `<article class="record"><div class="person-line">${p.claim?.photo ? `<img class="avatar" src="/api/admin/politicians/${encodeURIComponent(p.id)}/claim-photo" alt="">` : avatar(p)}<div><h3>${esc(p.name)}</h3><span>${esc(p.party)}</span></div></div>
          ${details?`<p>${esc(p.claim?.description ?? p.description)}</p><p>${esc(p.claim?.verification_email ?? p.verification_email)}</p><ul>${(p.claim?.statements ?? p.statements).map(s=>`<li>${esc(s)}</li>`).join("")}</ul>`:""}
          <div class="actions">${actions}</div></article>`;
    }

    function verification() {
        const pending = data.people.filter(p => p.status === "pending" || p.claim);
        const approved = data.people.filter(p => p.status === "verified");
        root.innerHTML =
            `<div id="issued"></div><p>Επιβεβαιώστε την ταυτότητα του αιτούντος μέσω επίσημου στοιχείου επικοινωνίας του Δήμου πριν εγκρίνετε τη διεκδίκηση.</p><h2>Αιτήσεις προς επαλήθευση (${pending.length})</h2>${pending.map(p=>personCard(p,`<button class="btn primary" data-issue="approve" data-id="${esc(p.id)}">Έγκριση και έκδοση στοιχείων σύνδεσης</button>${p.claim ? `<button class="btn danger" data-issue="reject" data-id="${esc(p.id)}">Απόρριψη αιτήματος</button>` : ""}`,true)).join("")||empty("Δεν υπάρχουν αιτήσεις προς επαλήθευση.")}
          <h2>Στοιχεία σύνδεσης επαληθευμένων εκπροσώπων</h2>${approved.map(p=>personCard(p,`<button class="btn" data-issue="regenerate" data-id="${esc(p.id)}">Έκδοση νέων στοιχείων σύνδεσης</button>`)).join("")||empty("Δεν υπάρχουν ακόμη επαληθευμένοι εκπρόσωποι.")}`;
        if (credential) {
            const {
                person,
                account
            } = credential;
            const message =
                `Όνομα χρήστη: ${account.login_username}\nΠροσωρινός κωδικός πρόσβασης: ${account.temporary_password}`;
            $("#issued").innerHTML =
                `<div class="credentials"><strong>Στοιχεία σύνδεσης για ${esc(person.name)}</strong><pre>${esc(message)}</pre><div class="actions"><button id="copy" class="btn">Αντιγραφή στοιχείων σύνδεσης</button><a class="btn" href="mailto:${encodeURIComponent(person.verification_email)}?subject=${encodeURIComponent("Στοιχεία σύνδεσης στο CiviConnect")}&body=${encodeURIComponent(message)}">Σύνταξη email</a><button class="btn" id="dismiss">Απόκρυψη</button></div><p class="status" role="status"></p></div>`;
            $("#copy").onclick = async () => {
                try {
                    await navigator.clipboard.writeText(message);
                    status($("#issued .status"), "Τα στοιχεία σύνδεσης αντιγράφηκαν.");
                } catch {
                    status($("#issued .status"),
                        "Επιλέξτε το όνομα χρήστη και τον κωδικό παραπάνω για να τα αντιγράψετε.");
                }
            };
            $("#dismiss").onclick = () => {
                credential = null;
                $("#issued").replaceChildren();
            };
        }
        $$("[data-issue]").forEach(b => b.onclick = async () => {
            if (b.dataset.issue === "regenerate" && !confirm(
                    "Να αντικατασταθεί ο κωδικός πρόσβασης και να τερματιστούν οι ενεργές συνδέσεις του εκπροσώπου;"))
                return;
            b.disabled = true;
            try {
                const account = await api(
                    `/api/admin/politicians/${b.dataset.id}/${b.dataset.issue}`, "POST");
                await reload();
                credential = b.dataset.issue === "reject" ? null : {
                    person: data.people.find(p => p.id === b.dataset.id),
                    account
                };
                verification();
                if (credential) $("#issued").scrollIntoView({
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
            `<h2>Επαληθευμένοι εκπρόσωποι</h2>${people.map(p=>personCard(p,`<button class="btn" data-edit="${esc(p.id)}">Επεξεργασία εκπροσώπου</button><button class="btn danger" data-delete data-id="${esc(p.id)}">Διαγραφή εκπροσώπου</button>`)).join("")||empty("Δεν υπάρχουν ακόμη επαληθευμένοι εκπρόσωποι.")}
        <dialog id="editor"><div class="dialog-head"><h2>Επεξεργασία εκπροσώπου</h2><button data-close class="circle" aria-label="Κλείσιμο">${icon("close")}</button></div><div id="edit-body"></div></dialog>`;
        $$("[data-edit]").forEach(b => b.onclick = () => {
            const p = data.people.find(p => p.id === b.dataset.edit);
            $("#edit-body").innerHTML =
                `<form id="admin-edit" class="form-stack"><label>Όνομα<input name="name" required maxlength="160" value="${esc(p.name)}"></label><label>Παράταξη<input name="party" required maxlength="160" value="${esc(p.party)}"></label>${detailFields(p)}<button class="btn primary">Αποθήκευση εκπροσώπου</button><p class="status" role="status"></p></form>`;
            bindForm($("#admin-edit"), async fields => {
                await api("/api/admin/politicians/" + p.id, "PUT", {
                    ...detailData(fields),
                    name: fields.get("name"),
                    party: fields.get("party")
                });
                await reload();
                $("#editor").close();
                manage();
                status(output, "Τα στοιχεία του εκπροσώπου ενημερώθηκαν.");
            });
            $("#editor").showModal();
        });
        $$("[data-delete]").forEach(b => b.onclick = async () => {
            if (!confirm("Να διαγραφεί αυτό το προφίλ;")) return;
            b.disabled = true;
            try {
                await api(`/api/admin/politicians/${b.dataset.id}`, "DELETE");
                await reload();
                manage();
                status(output, "Η αφαίρεση ολοκληρώθηκε.");
            } catch (e) {
                status(output, e.message, true);
                b.disabled = false;
            }
        });
    }

    function contacts() {
        root.innerHTML =
            `<h2>Μηνύματα επικοινωνίας</h2>${data.contacts.map(c=>`<article class="record"><small>${dateText(c.submitted_at)}</small><h3>${esc(c.name)}</h3><a href="mailto:${encodeURIComponent(c.email)}">${esc(c.email)}</a><p>${esc(c.message)}</p></article>`).join("")||empty("Δεν υπάρχουν ακόμη μηνύματα επικοινωνίας.")}`;
    }
    try {
        await reload();
        showTab(0);
    } catch (e) {
        status(output, e.message, true);
    }
}
