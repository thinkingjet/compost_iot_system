// CompostIQ public website. Optional extras only: every page works without
// this file. Code samples get language tabs and a Copy button.

document.querySelectorAll("[data-tabs]").forEach((box) => {
  const tabs = box.querySelectorAll("[data-tab]");
  const panels = box.querySelectorAll("[data-panel]");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => t.setAttribute("aria-pressed", String(t === tab)));
      panels.forEach((panel) => {
        panel.hidden = panel.dataset.panel !== tab.dataset.tab;
      });
    });
  });
});

if (navigator.clipboard) {
  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.hidden = false;
    button.addEventListener("click", async () => {
      const code = button.closest(".codebox").querySelector("pre:not([hidden])");
      // Drop the "$ " shell prompt so the command can be pasted as is.
      await navigator.clipboard.writeText(code.innerText.replace(/^\$ /gm, ""));
      button.textContent = "Copied";
      setTimeout(() => { button.textContent = "Copy"; }, 1500);
    });
  });
}
