async function loadNav() {
  try {
    const res = await fetch("nav.html");
    const html = await res.text();

    document.body.insertAdjacentHTML("afterbegin", html);
    highlightActive();
  } catch (err) {
    console.error("Navbar failed to load:", err);
  }
}

function highlightActive() {
  const current = location.pathname.split("/").pop() || "index.html";

  document.querySelectorAll(".site-nav a").forEach(link => {
    if (link.getAttribute("href") === current) {
      link.classList.add("active");
    }
  });
}

window.addEventListener("DOMContentLoaded", loadNav);

