const API_BASE = "http://127.0.0.1:9966";
const WS_BASE = "ws://127.0.0.1:9966";

let currentFilter = "all";
let cachedMatches = [];
let cachedPlayers = [];
let liveSocket = null;

async function api(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`Request failed: ${path}`);
  return res.json();
}

function getFavorites() {
  return JSON.parse(localStorage.getItem("stumpscore_favorites") || "[]");
}

function saveFavorites(favs) {
  localStorage.setItem("stumpscore_favorites", JSON.stringify(favs));
}

function toggleFavorite(item) {
  const favs = getFavorites();
  const exists = favs.find(f => f.id === item.id && f.type === item.type);

  const updated = exists
    ? favs.filter(f => !(f.id === item.id && f.type === item.type))
    : [...favs, item];

  saveFavorites(updated);
  return updated;
}

function isFavorite(id, type) {
  return getFavorites().some(f => f.id === id && f.type === type);
}

function toggleFavCard(id, type, name) {
  toggleFavorite({ id, type, name });
  location.reload();
}

function classifyMatch(match) {
  const name = (match.name || "").toLowerCase();

  if (
    name.includes("ipl") ||
    name.includes("league") ||
    name.includes("super kings") ||
    name.includes("royal challengers") ||
    name.includes("indians")
  ) {
    return "league";
  }

  return "international";
}

function setSocketStatus(text, kind = "neutral") {
  const el = document.getElementById("socketStatus");
  if (!el) return;

  el.textContent = text;
  el.className = "connection-badge";

  if (kind === "connected") el.classList.add("connected");
  if (kind === "reconnecting") el.classList.add("reconnecting");
  if (kind === "error") el.classList.add("error");
}

function showMatchSkeleton() {
  const root = document.getElementById("liveMatches");
  if (!root) return;

  root.innerHTML = Array(6).fill("").map(() => `
    <div class="match-card skeleton-card">
      <div class="skeleton skeleton-title"></div>
      <div class="skeleton skeleton-text"></div>
      <div class="skeleton skeleton-text"></div>
    </div>
  `).join("");
}

function showNewsSkeleton() {
  const root = document.getElementById("newsList");
  if (!root) return;

  root.innerHTML = Array(5).fill("").map(() => `
    <div class="news-card skeleton-card">
      <div class="skeleton skeleton-title"></div>
      <div class="skeleton skeleton-text"></div>
    </div>
  `).join("");
}

function showPlayerSkeleton() {
  const root = document.getElementById("playersList");
  if (!root) return;

  root.innerHTML = Array(6).fill("").map(() => `
    <div class="player-card skeleton-card">
      <div class="skeleton skeleton-title"></div>
      <div class="skeleton skeleton-text"></div>
    </div>
  `).join("");
}

function renderLiveStrip(matches) {
  const root = document.getElementById("liveStrip");
  if (!root) return;

  root.innerHTML = "";

  const items = matches.length ? matches : [{
    id: "demo1",
    name: "No live matches right now",
    status: "Stay tuned for upcoming action",
    matchType: "CRICKET"
  }];

  items.forEach((m) => {
    const el = document.createElement("div");
    el.className = "strip-card";
    el.innerHTML = `
      <div class="strip-top">
        <span class="live-chip"><span class="live-dot"></span> Live</span>
        <span class="strip-type">${m.matchType || "CRICKET"}</span>
      </div>
      <div class="strip-title">${m.name || "Match"}</div>
      <div class="strip-status">${m.status || ""}</div>
    `;
    root.appendChild(el);
  });
}

function renderMatches(matches) {
  const root = document.getElementById("liveMatches");
  if (!root) return;

  root.innerHTML = "";

  let filtered = matches;
  if (currentFilter !== "all") {
    filtered = matches.filter((m) => classifyMatch(m) === currentFilter);
  }

  if (!filtered.length) {
    root.innerHTML = `<div class="empty">No matches in this section right now.</div>`;
    return;
  }

  filtered.forEach((m) => {
    const scoreHtml = (m.score || []).map(s => `
      <div class="score-row">
        <span>${s.inning || "Innings"}</span>
        <strong>${s.r || 0}/${s.w || 0} (${s.o || 0})</strong>
      </div>
    `).join("");

    const favoriteButton = m.id && m.id !== "demo1"
      ? `<button class="fav-btn" onclick="event.stopPropagation(); toggleFavCard('${m.id}','match',${JSON.stringify(m.name || "Match")})">
          ${isFavorite(m.id, "match") ? "â˜…" : "â˜†"}
        </button>`
      : "";

    const el = document.createElement("article");
    el.className = "match-card";
    el.style.cursor = m.id && m.id !== "demo1" ? "pointer" : "default";

    if (m.id && m.id !== "demo1") {
      el.onclick = () => {
        window.location.href = `match.html?id=${m.id}`;
      };
    }

    el.innerHTML = `
      <div class="card-top">
        <span class="match-status-pill"><span class="live-dot"></span> Live</span>
        <div style="display:flex; gap:8px; align-items:center;">
          <span class="match-type">${m.matchType || ""}</span>
          ${favoriteButton}
        </div>
      </div>
      <h4 class="match-title">${m.name || "Match"}</h4>
      <p class="meta">${m.venue || "Venue not available"}</p>
      <div class="score-box">
        ${scoreHtml || `<div class="score-row"><span>Status</span><strong>${m.status || "N/A"}</strong></div>`}
      </div>
      <div class="card-footer">
        <span>${m.status || ""}</span>
        <span>ID: ${m.id || "-"}</span>
      </div>
    `;
    root.appendChild(el);
  });
}

function renderNews(news) {
  const root = document.getElementById("newsList");
  if (!root) return;

  root.innerHTML = "";

  if (!news.length) {
    root.innerHTML = `<div class="empty">No news available right now.</div>`;
    return;
  }

  news.forEach((n) => {
    const el = document.createElement("article");
    el.className = "news-card";
    el.innerHTML = `
      <h4>${n.title}</h4>
      <p class="meta">${n.source}</p>
      <p class="meta">${n.summary || ""}</p>
    `;
    root.appendChild(el);
  });
}

function renderPlayers(players) {
  const root = document.getElementById("playersList");
  if (!root) return;

  root.innerHTML = "";

  if (!players.length) {
    root.innerHTML = `<div class="empty">No players found.</div>`;
    return;
  }

  players.forEach((p) => {
    const favoriteButton = `
      <button class="fav-btn" onclick="event.stopPropagation(); toggleFavCard('${p.id}','player',${JSON.stringify(p.name)})">
        ${isFavorite(p.id, "player") ? "â˜…" : "â˜†"}
      </button>
    `;

    const el = document.createElement("article");
    el.className = "player-card";
    el.onclick = () => {
      window.location.href = `player.html?id=${p.id}`;
    };

    el.innerHTML = `
      <div class="card-top">
        <span class="match-type">Profile</span>
        ${favoriteButton}
      </div>
      <h4>${p.name}</h4>
      <div class="player-country">${p.country}</div>
      <div class="player-role">${p.role}</div>
      <div class="player-style">${p.battingStyle || ""} ${p.bowlingStyle ? "â€¢ " + p.bowlingStyle : ""}</div>
    `;
    root.appendChild(el);
  });
}

function renderFavoritesPage() {
  if (pageType !== "favorites") return;

  const favs = getFavorites();
  const matches = favs.filter(f => f.type === "match");
  const players = favs.filter(f => f.type === "player");

  const matchRoot = document.getElementById("favMatches");
  const playerRoot = document.getElementById("favPlayers");

  if (matchRoot) {
    if (!matches.length) {
      matchRoot.innerHTML = `<div class="empty">No favorite matches</div>`;
    } else {
      matchRoot.innerHTML = matches.map(m => `
        <article class="match-card" onclick="window.location.href='match.html?id=${m.id}'">
          <h4 class="match-title">${m.name}</h4>
        </article>
      `).join("");
    }
  }

  if (playerRoot) {
    if (!players.length) {
      playerRoot.innerHTML = `<div class="empty">No favorite players</div>`;
    } else {
      playerRoot.innerHTML = players.map(p => `
        <article class="player-card" onclick="window.location.href='player.html?id=${p.id}'">
          <h4>${p.name}</h4>
        </article>
      `).join("");
    }
  }
}

function attachLiveFilters() {
  document.querySelectorAll(".nav-btn[data-filter]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".nav-btn[data-filter]").forEach(t => t.classList.remove("active"));
      btn.classList.add("active");
      currentFilter = btn.dataset.filter;
      renderMatches(cachedMatches);
    });
  });
}

function attachPlayerSearch() {
  const input = document.getElementById("playerSearchInput");
  const btn = document.getElementById("playerSearchBtn");
  if (!input || !btn) return;

  const run = () => {
    const q = input.value.trim().toLowerCase();
    if (!q) {
      renderPlayers(cachedPlayers);
      return;
    }

    const filtered = cachedPlayers.filter(p =>
      (p.name || "").toLowerCase().includes(q)
    );
    renderPlayers(filtered);
  };

  btn.addEventListener("click", run);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") run();
  });
}

function connectLiveSocket() {
  if (pageType !== "live") return;

  showMatchSkeleton();
  setSocketStatus("Connecting...", "neutral");

  liveSocket = new WebSocket(`${WS_BASE}/ws/live`);

  liveSocket.onopen = () => {
    setSocketStatus("Live connected", "connected");
  };

  liveSocket.onmessage = (event) => {
    const msg = JSON.parse(event.data);

    if (msg.type === "live_update") {
      cachedMatches = msg.matches || [];
      renderLiveStrip(cachedMatches);
      renderMatches(cachedMatches);
    }

    if (msg.type === "error") {
      setSocketStatus("Feed error", "error");
      console.error(msg.message);
    }
  };

  liveSocket.onclose = () => {
    setSocketStatus("Reconnecting...", "reconnecting");
    setTimeout(connectLiveSocket, 3000);
  };

  liveSocket.onerror = () => {
    liveSocket.close();
  };
}

async function loadNewsPage() {
  showNewsSkeleton();
  const news = await api("/news/latest");
  renderNews(news);
}

async function loadPlayersPage() {
  showPlayerSkeleton();
  const players = await api("/players");
  cachedPlayers = players;
  renderPlayers(players);
}
function renderMatchesList(matches) {
  const root = document.getElementById("matchesList");
  if (!root) return;

  if (!matches.length) {
    root.innerHTML = `<div class="empty">No created matches yet.</div>`;
    return;
  }

  root.innerHTML = matches.map(m => `
    <article class="news-card">
      <div class="card-top">
        <span class="match-type">${m.id}</span>
        <button onclick="selectMatch('${m.id}')">Select</button>
      </div>
      <h4>${m.team1} vs ${m.team2}</h4>
      <p class="meta">Status: ${m.status}</p>
      <p class="meta">Created by: ${m.created_by}</p>
    </article>
  `).join("");
}

async function loadAllMatches() {
  try {
    const matches = await api("/local-match");
    renderMatchesList(matches);
  } catch (err) {
    console.error(err);
  }
}

function selectMatch(matchId) {
  currentMatchId = matchId;
  loadMatch();
}
loadAllMatches();

document.getElementById("findProfileBtn").onclick = async () => {
  try {
    const profileId = document.getElementById("lookupProfileId").value.trim();
    const phone = document.getElementById("lookupPhone").value.trim();

    const q = new URLSearchParams();
    if (profileId) q.append("profile_id", profileId);
    if (phone) q.append("phone", phone);

    const profile = await api(`/profiles/find?${q.toString()}`);

    document.getElementById("lookupResult").innerHTML = `
      <article class="news-card">
        <h4>${profile.name}</h4>
        <p class="meta">ID: ${profile.id}</p>
        <p class="meta">Phone: ${profile.phone || "-"}</p>
        <p class="meta">Role: ${profile.role || "-"}</p>
      </article>
    `;
  } catch (err) {
    document.getElementById("lookupResult").innerHTML =
      `<div class="empty">${err.message}</div>`;
  }
};


(function init() {
  const run = async () => {
    try {
      if (pageType === "live") {
        attachLiveFilters();
        connectLiveSocket();
      }

      if (pageType === "news") {
        await loadNewsPage();
      }

      if (pageType === "players") {
        await loadPlayersPage();
        attachPlayerSearch();
      }

      if (pageType === "favorites") {
        renderFavoritesPage();
      }
    } catch (e) {
      console.error(e);

      const container =
        document.getElementById("liveMatches") ||
        document.getElementById("newsList") ||
        document.getElementById("playersList");

      if (container) {
        container.innerHTML = `
          <div class="empty">
            Failed to load data. Please check backend or API.
          </div>
        `;
      }
    }
  };

  run();
})();
