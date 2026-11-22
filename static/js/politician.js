import {
    $,
    api,
    status,
    bindForm,
    detailFields,
    detailData,
    login,
    bindLogout,
    profileURL
} from "./common.js?v=workspace-cleanup";
if ($("#login")) login("politician");
else startDashboard();
async function startDashboard() {
    const root = $("#workspace");
    bindLogout("politician");
    try {
        const {profile} = await api("/api/politician/workspace");
        $("#workspace-name").textContent = profile.name + " · " + profile.party;
        root.innerHTML = `<form id="edit-profile" class="panel form-stack wide-form"><div class="section-head"><h2>Επεξεργασία προφίλ</h2><a href="${profileURL(profile.id)}">Προβολή προφίλ</a></div>${detailFields(profile)}<label>Νέα φωτογραφία <span class="optional">Προαιρετικό</span><input name="photo" type="file" accept="image/jpeg,image/png,image/webp"></label><button class="btn primary">Αποθήκευση προφίλ</button><p class="status" role="status"></p></form>`;
        bindForm($("#edit-profile"), async fields => {
            const body = detailData(fields);
            const upload = new FormData();
            upload.append("profile", JSON.stringify(body));
            const photo = fields.get("photo");
            if (photo.size) upload.append("photo", photo);
            await api("/api/politician/profile", "PUT", upload);
            status($("#edit-profile .status"), "Το προφίλ ενημερώθηκε.");
        });
    } catch (e) {
        status($("#dashboard-status"), e.message, true);
    }
}
