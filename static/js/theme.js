// Apply the stored preference before the first paint. Auto follows the OS.
try {
    const preference = localStorage.getItem("civiconnect-theme");
    if (["dark", "light"].includes(preference)) document.documentElement.dataset.theme = preference;
} catch {
    /* Storage may be disabled in private browsing. */ }
