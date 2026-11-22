import { $, api, bindForm, status, detailFields, detailData } from "./common.js?v=workspace-cleanup";

const form = $("#application");
const select = form.elements.person;
const button = form.querySelector("button");
const output = $(".status", form);
$("#detail-fields").innerHTML = detailFields({}, false);

try {
    const people = (await api("/api/politicians")).filter(person => person.status === "unclaimed");
    const requested = new URLSearchParams(location.search).get("id");
    people.sort((a, b) => a.name.localeCompare(b.name, "el"));
    for (const person of people) {
        select.add(new Option(person.name + " · " + person.party, person.id));
    }
    if (people.some(person => person.id === requested)) select.value = requested;
    button.disabled = !people.length;
    if (!people.length) status(output, "Δεν υπάρχουν διαθέσιμα προφίλ για διεκδίκηση.");
} catch (error) {
    status(output, error.message, true);
}

bindForm(form, async data => {
    const photo = data.get("photo");
    if (photo.size > 8 * 1024 ** 2) throw Error("Επιλέξτε φωτογραφία έως 8 MB.");
    const { description, statements } = detailData(data);
    const upload = new FormData();
    upload.append("application", JSON.stringify({
        description, statements, verification_email: data.get("verification_email")
    }));
    if (photo.size) upload.append("photo", photo);
    await api("/api/politicians/" + encodeURIComponent(data.get("person")) + "/claim", "POST", upload);
    form.reset();
    status(output, "Το αίτημά σας υποβλήθηκε. Θα επικοινωνήσουμε μαζί σας για την επαλήθευση.");
});
