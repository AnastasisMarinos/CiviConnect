import {
    $,
    api,
    bindForm,
    status,
    detailFields,
    detailData
} from "./common.js";
$("#detail-fields").innerHTML = detailFields();
bindForm($("#application"), async data => {
    const photo = data.get("photo");
    if (photo.size > 8 * 1024 ** 2) throw Error("Choose a photo smaller than 8 MB.");
    const application = {
        ...detailData(data),
        name: data.get("name"),
        party: data.get("party"),
        verification_email: data.get("verification_email")
    };
    const upload = new FormData();
    upload.append("application", JSON.stringify(application));
    upload.append("photo", photo);
    await api("/api/politicians/apply", "POST", upload);
    $("#application").reset();
    status($("#application .status"),
        "Application received. The team will review your details and contact you by email.");
});
