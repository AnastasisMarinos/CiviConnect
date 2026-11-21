import {
    $,
    api,
    bindForm,
    status,
    queueItem,
    stage,
    empty
} from "./common.js";
let records = [],
    index = 0;

function select(value) {
    index = (value + records.length) % records.length || 0;
    const count = records.length;
    $("#position").textContent = count ?
        `${String(index+1).padStart(2,"0")} / ${String(count).padStart(2,"0")}` : "0 replies";
    $("#prev").disabled = $("#next").disabled = count < 2;
    $("#all-replies").disabled = count === 0;
    if (!count) {
        $("#featured").innerHTML = empty("Candidate video replies will appear here when published.");
        $("#up-next").innerHTML = empty("No replies in the queue yet.");
        return;
    }
    stage($("#featured"), records[index], records[index].aspect_ratio === "vertical" ? "9:16" : "16:9");
    const queued = Array.from({
        length: Math.min(count - 1, 3)
    }, (_, i) => (index + i + 1) % count);
    $("#up-next").innerHTML = queued.length ? queued.map(i => queueItem(records[i], i)).join("") : empty(
        "You’re watching the latest reply.");
}
$("#next").onclick = () => select(index + 1);
$("#prev").onclick = () => select(index - 1);
$("#all-replies").onclick = () => {
    $("#reply-list").innerHTML = records.map(queueItem).join("");
    $("#reply-dialog").showModal();
};
for (const root of [$("#reply-list"), $("#up-next")]) root.onclick = event => {
    const item = event.target.closest("[data-index]");
    if (!item) return;
    $("#reply-dialog").close();
    select(Number(item.dataset.index));
    if (root.id === "reply-list") $(".play-main", $("#featured")).focus();
};
api("/api/video-replies").then(rows => {
    records = rows;
    select(0);
}).catch(e => {
    select(0);
    $("#featured").innerHTML = empty(e.message);
});
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
        if (Date.now() >= +target) $(".election-info h2").textContent = "Election day has arrived";
    }
    tick();
    setInterval(tick, 1000);
}).catch(e => {
    $("#election-date").textContent = e.message;
});
bindForm($("#citizen-form"), async data => {
    await api("/api/submissions", "POST", Object.fromEntries(data));
    $("#citizen-form").reset();
    status($("#citizen-form .status"),
        "Submission received. Verified candidates can now read your message.");
});
