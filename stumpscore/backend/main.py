from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import os
import requests
import asyncio
import json
from typing import Set
from dotenv import load_dotenv

load_dotenv()
local_matches = {}
profiles = {}

app = FastAPI(title="StumpScore API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CRIC_API_KEY = os.getenv("CRIC_API_KEY")
CRIC_API_BASE = "https://api.cricapi.com/v1"

# =========================
# REALTIME STATE
# =========================
live_clients: Set[WebSocket] = set()
latest_live_matches = []
latest_live_hash = ""


# =========================
# HELPERS
# =========================
def fetch_current_matches():
    if not CRIC_API_KEY:
        raise HTTPException(status_code=500, detail="CRIC_API_KEY not set")

    url = f"{CRIC_API_BASE}/currentMatches"
    params = {"apikey": CRIC_API_KEY, "offset": 0}

    try:
        res = requests.get(url, params=params, timeout=20)
        res.raise_for_status()
        return res.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"CricAPI request failed: {str(e)}")


def normalize_live_matches(raw_data):
    matches = []
    for m in raw_data.get("data", []):
        matches.append({
            "id": str(m.get("id")),
            "name": m.get("name"),
            "matchType": m.get("matchType"),
            "status": m.get("status"),
            "venue": m.get("venue"),
            "date": m.get("date"),
            "dateTimeGMT": m.get("dateTimeGMT"),
            "teams": m.get("teams", []),
            "teamInfo": m.get("teamInfo", []),
            "score": m.get("score", []),
            "series_id": m.get("series_id"),
            "fantasyEnabled": m.get("fantasyEnabled"),
            "bbbEnabled": m.get("bbbEnabled"),
            "hasSquad": m.get("hasSquad"),
            "matchStarted": m.get("matchStarted"),
            "matchEnded": m.get("matchEnded"),
        })
    return matches


def get_match_from_live(match_id: str):
    # First check cached live data
    for match in latest_live_matches:
        if str(match["id"]) == str(match_id):
            return match

    # Fallback to fresh fetch
    raw = fetch_current_matches()
    matches = normalize_live_matches(raw)
    for match in matches:
        if str(match["id"]) == str(match_id):
            return match

    raise HTTPException(status_code=404, detail="Match not found in current live/current match feed")


def sample_players():
    return [
        {
            "id": "p1",
            "name": "Virat Kohli",
            "country": "India",
            "role": "Batter",
            "battingStyle": "Right-hand bat",
            "bowlingStyle": "Right-arm medium",
        },
        {
            "id": "p2",
            "name": "Jasprit Bumrah",
            "country": "India",
            "role": "Bowler",
            "battingStyle": "Right-hand bat",
            "bowlingStyle": "Right-arm fast",
        },
        {
            "id": "p3",
            "name": "Babar Azam",
            "country": "Pakistan",
            "role": "Batter",
            "battingStyle": "Right-hand bat",
            "bowlingStyle": "Right-arm off break",
        },
        {
            "id": "p4",
            "name": "Pat Cummins",
            "country": "Australia",
            "role": "Bowler",
            "battingStyle": "Right-hand bat",
            "bowlingStyle": "Right-arm fast",
        },
    ]


def sample_teams():
    return [
        {"id": "t1", "name": "India", "shortName": "IND", "format": ["T20I", "ODI", "TEST"]},
        {"id": "t2", "name": "Australia", "shortName": "AUS", "format": ["T20I", "ODI", "TEST"]},
        {"id": "t3", "name": "Pakistan", "shortName": "PAK", "format": ["T20I", "ODI", "TEST"]},
        {"id": "t4", "name": "RCB", "shortName": "RCB", "format": ["IPL"]},
    ]


def sample_series():
    return [
        {"id": "s1", "name": "ICC T20 World Cup", "format": "T20I"},
        {"id": "s2", "name": "World Test Championship", "format": "TEST"},
        {"id": "s3", "name": "Asia Cup", "format": "ODI"},
        {"id": "s4", "name": "IPL 2026", "format": "T20"},
    ]


def sample_news():
    return [
        {
            "id": "n1",
            "title": "India prepare for a crucial clash with balanced XI",
            "source": "StumpScore Desk",
            "summary": "Team balance and death bowling remain the talking points ahead of the big game.",
        },
        {
            "id": "n2",
            "title": "IPL teams eye stronger finishing combinations",
            "source": "StumpScore Desk",
            "summary": "Franchises continue to optimize batting depth and death-over matchups.",
        },
    ]


def stable_hash(data):
    return json.dumps(data, sort_keys=True, default=str)


async def broadcast_live(payload):
    dead = []

    for ws in live_clients:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)

    for ws in dead:
        live_clients.discard(ws)


async def live_poll_loop():
    global latest_live_matches, latest_live_hash

    while True:
        try:
            raw = fetch_current_matches()
            matches = normalize_live_matches(raw)

            if not matches:
                matches = [
                    {
                        "id": "demo1",
                        "name": "No live matches right now",
                        "status": "Stay tuned for upcoming action",
                        "matchType": "CRICKET",
                        "venue": "Global Feed",
                        "score": [],
                        "teams": [],
                        "teamInfo": [],
                        "matchStarted": False,
                        "matchEnded": False,
                    }
                ]

            new_hash = stable_hash(matches)

            if new_hash != latest_live_hash:
                latest_live_matches = matches
                latest_live_hash = new_hash

                await broadcast_live({
                    "type": "live_update",
                    "matches": latest_live_matches
                })

        except Exception as e:
            await broadcast_live({
                "type": "error",
                "message": str(e)
            })

        await asyncio.sleep(8)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(live_poll_loop())


# =========================
# ROOT
# =========================
@app.get("/")
def root():
    return {"message": "StumpScore API running", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok"}


# =========================
# MATCHES
# =========================
@app.get("/matches/live")
def matches_live():
    return latest_live_matches


@app.get("/matches/upcoming")
def matches_upcoming():
    raw = fetch_current_matches()
    matches = normalize_live_matches(raw)
    return [m for m in matches if not m.get("matchStarted")]


@app.get("/matches/recent")
def matches_recent():
    raw = fetch_current_matches()
    matches = normalize_live_matches(raw)
    return [m for m in matches if m.get("matchEnded")]


@app.get("/matches/{match_id}")
def match_details(match_id: str):
    match = get_match_from_live(match_id)
    return {
        "match": match,
        "info": {
            "weather": "Not available in current provider feed",
            "pitchReport": "Can be added later with another source",
            "toss": "Not available in current provider feed",
        }
    }


@app.get("/matches/{match_id}/scorecard")
def match_scorecard(match_id: str):
    match = get_match_from_live(match_id)
    return {
        "match_id": match_id,
        "teams": match.get("teams", []),
        "score": match.get("score", []),
        "summary": match.get("status"),
    }


@app.get("/matches/{match_id}/commentary")
def match_commentary(match_id: str):
    match = get_match_from_live(match_id)
    return {
        "match_id": match_id,
        "available": False,
        "message": "Ball-by-ball commentary is not available from the current CricAPI route used here.",
        "status": match.get("status"),
        "commentary": []
    }


@app.get("/matches/{match_id}/stats")
def match_stats(match_id: str):
    match = get_match_from_live(match_id)
    return {
        "match_id": match_id,
        "teamComparison": {
            "teams": match.get("teams", []),
            "status": match.get("status"),
        },
        "advanced": {
            "runRate": "Can be derived later",
            "requiredRate": "Can be derived later",
            "partnerships": [],
        }
    }


@app.get("/matches/{match_id}/squads")
def match_squads(match_id: str):
    match = get_match_from_live(match_id)
    teams = match.get("teams", [])
    return {
        "match_id": match_id,
        "squads": [
            {"team": teams[0] if len(teams) > 0 else "Team 1", "players": sample_players()[:2]},
            {"team": teams[1] if len(teams) > 1 else "Team 2", "players": sample_players()[2:]},
        ]
    }


@app.get("/matches/{match_id}/overs")
def match_overs(match_id: str):
    match = get_match_from_live(match_id)
    return {
        "match_id": match_id,
        "status": match.get("status"),
        "overs": [],
        "message": "Over-by-over feed is not yet wired from the current live provider."
    }


# =========================
# REALTIME WEBSOCKET
# =========================
@app.websocket("/ws/live")
async def websocket_live(ws: WebSocket):
    await ws.accept()
    live_clients.add(ws)

    try:
        await ws.send_json({
            "type": "live_update",
            "matches": latest_live_matches
        })

        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        live_clients.discard(ws)
    except Exception:
        live_clients.discard(ws)


# =========================
# PLAYERS
# =========================
@app.get("/players")
def players(
    q: str | None = Query(default=None),
    country: str | None = Query(default=None),
    role: str | None = Query(default=None),
):
    data = sample_players()

    if q:
        data = [p for p in data if q.lower() in p["name"].lower()]
    if country:
        data = [p for p in data if country.lower() in p["country"].lower()]
    if role:
        data = [p for p in data if role.lower() in p["role"].lower()]

    return data


@app.get("/players/{player_id}")
def player_details(player_id: str):
    for player in sample_players():
        if player["id"] == player_id:
            return player
    raise HTTPException(status_code=404, detail="Player not found")


@app.get("/players/{player_id}/stats")
def player_stats(player_id: str):
    return {
        "player_id": player_id,
        "t20": {"matches": 125, "runs": 4188, "wickets": 4},
        "odi": {"matches": 295, "runs": 13906, "wickets": 5},
        "test": {"matches": 113, "runs": 8848, "wickets": 0},
    }


@app.get("/players/{player_id}/matches")
def player_matches(player_id: str):
    return {
        "player_id": player_id,
        "recentMatches": [
            {"match_id": "m1", "opponent": "Australia", "format": "T20I"},
            {"match_id": "m2", "opponent": "England", "format": "ODI"},
        ]
    }


@app.get("/players/{player_id}/career")
def player_career(player_id: str):
    return {
        "player_id": player_id,
        "career": {
            "debut": "Sample data",
            "bestPerformance": "Sample data",
            "awards": [],
            "milestones": [],
        }
    }


# =========================
# TEAMS
# =========================
@app.get("/teams")
def teams():
    return sample_teams()


@app.get("/teams/{team_id}")
def team_details(team_id: str):
    for team in sample_teams():
        if team["id"] == team_id:
            return team
    raise HTTPException(status_code=404, detail="Team not found")


@app.get("/teams/{team_id}/players")
def team_players(team_id: str):
    team_map = {
        "t1": sample_players()[:2],
        "t2": sample_players()[2:],
        "t3": [sample_players()[2]],
        "t4": [sample_players()[0]],
    }
    return {"team_id": team_id, "players": team_map.get(team_id, [])}


@app.get("/teams/{team_id}/matches")
def team_matches(team_id: str):
    return {
        "team_id": team_id,
        "matches": [
            {"match_id": "m11", "opponent": "Sample Opponent", "status": "Completed"},
            {"match_id": "m12", "opponent": "Sample Opponent 2", "status": "Upcoming"},
        ]
    }


# =========================
# SERIES
# =========================
@app.get("/series")
def series():
    return sample_series()


@app.get("/series/{series_id}")
def series_details(series_id: str):
    for s in sample_series():
        if s["id"] == series_id:
            return s
    raise HTTPException(status_code=404, detail="Series not found")


@app.get("/series/{series_id}/matches")
def series_matches(series_id: str):
    raw = fetch_current_matches()
    matches = normalize_live_matches(raw)
    filtered = [m for m in matches if str(m.get("series_id")) == str(series_id)]
    return {"series_id": series_id, "matches": filtered}


# =========================
# NEWS
# =========================
@app.get("/news")
def news():
    return sample_news()


@app.get("/news/latest")
def news_latest():
    return sample_news()[:2]


@app.get("/news/trending")
def news_trending():
    return sample_news()


@app.get("/news/search")
def news_search(q: str):
    return [n for n in sample_news() if q.lower() in n["title"].lower()]


@app.get("/news/player/{name}")
def news_by_player(name: str):
    return [n for n in sample_news() if name.lower() in n["title"].lower()]


@app.get("/news/team/{name}")
def news_by_team(name: str):
    return [n for n in sample_news() if name.lower() in n["title"].lower()]


@app.get("/news/series/{name}")
def news_by_series(name: str):
    return [n for n in sample_news() if name.lower() in n["title"].lower()]


# =========================
# SEARCH + PREDICTIONS
# =========================
@app.get("/search")
def search(q: str = Query(..., min_length=1)):
    players_found = [p for p in sample_players() if q.lower() in p["name"].lower()]
    teams_found = [t for t in sample_teams() if q.lower() in t["name"].lower()]
    series_found = [s for s in sample_series() if q.lower() in s["name"].lower()]

    raw = fetch_current_matches()
    matches = normalize_live_matches(raw)
    matches_found = [
        m for m in matches
        if q.lower() in (m.get("name") or "").lower()
        or any(q.lower() in team.lower() for team in m.get("teams", []))
    ]

    return {
        "query": q,
        "players": players_found,
        "teams": teams_found,
        "series": series_found,
        "matches": matches_found,
    }


@app.get("/predictions/{match_id}")
def predictions(match_id: str):
    match = get_match_from_live(match_id)
    teams = match.get("teams", [])
    favorite = teams[0] if teams else "Unknown"

    return {
        "match_id": match_id,
        "favorite": favorite,
        "winProbability": {
            favorite: 58,
            teams[1] if len(teams) > 1 else "Opponent": 42
        },
        "reason": "Basic placeholder prediction. Later connect Kaggle/ML or stronger live stats model."
    }
@app.post("/local-match/create")
def create_local_match(payload: dict):
    match_id = f"local_{len(local_matches) + 1}"

    local_matches[match_id] = {
        "id": match_id,
        "team1": payload.get("team1", "Team A"),
        "team2": payload.get("team2", "Team B"),
        "score": 0,
        "wickets": 0,
        "overs": 0.0,
        "balls": [],
        "striker": payload.get("striker", "Batter 1"),
        "non_striker": payload.get("non_striker", "Batter 2"),
        "bowler": payload.get("bowler", "Bowler 1"),
    }

    return local_matches[match_id]


@app.get("/local-match/{match_id}")
def get_local_match(match_id: str):
    if match_id not in local_matches:
        raise HTTPException(status_code=404, detail="Local match not found")
    return local_matches[match_id]


@app.post("/local-match/{match_id}/ball")
def add_ball(match_id: str, payload: dict):
    if match_id not in local_matches:
        raise HTTPException(status_code=404, detail="Local match not found")

    match = local_matches[match_id]

    runs = int(payload.get("runs", 0))
    wicket = bool(payload.get("wicket", False))

    match["score"] += runs
    if wicket:
        match["wickets"] += 1

    balls_bowled = len(match["balls"]) + 1
    overs = balls_bowled // 6
    balls = balls_bowled % 6
    match["overs"] = float(f"{overs}.{balls}")

    match["balls"].append({
        "ball_no": balls_bowled,
        "runs": runs,
        "wicket": wicket
    })

    return match


@app.get("/local-match/{match_id}/scorecard")
def local_scorecard(match_id: str):
    if match_id not in local_matches:
        raise HTTPException(status_code=404, detail="Local match not found")

    match = local_matches[match_id]

    return {
        "id": match["id"],
        "team1": match["team1"],
        "team2": match["team2"],
        "score": f'{match["score"]}/{match["wickets"]}',
        "overs": match["overs"],
        "balls": match["balls"],
        "striker": match["striker"],
        "non_striker": match["non_striker"],
        "bowler": match["bowler"],
    }
@app.post("/profiles/create")
def create_profile(payload: dict):
    profile_id = f"profile_{len(profiles) + 1}"

    profile = {
        "id": profile_id,
        "name": payload.get("name", "Unknown Player"),
        "phone": payload.get("phone", ""),
        "role": payload.get("role", "Player"),
        "batting_style": payload.get("batting_style", ""),
        "bowling_style": payload.get("bowling_style", ""),
    }

    profiles[profile_id] = profile
    return profile

@app.get("/profiles")
def get_profiles():
    return list(profiles.values())

@app.get("/profiles/find")
def find_profile(profile_id: str = Query(default=""), phone: str = Query(default="")):
    if profile_id and profile_id in profiles:
        return profiles[profile_id]

    if phone:
        for profile in profiles.values():
            if profile.get("phone") == phone:
                return profile

    raise HTTPException(status_code=404, detail="Profile not found")

@app.post("/local-match/create")
def create_local_match(payload: dict):
    match_id = f"local_{len(local_matches) + 1}"

    local_matches[match_id] = {
        "id": match_id,
        "created_by": payload.get("created_by", "creator_1"),
        "team1": payload.get("team1", "Team A"),
        "team2": payload.get("team2", "Team B"),
        "team1_players": [],
        "team2_players": [],
        "score": 0,
        "wickets": 0,
        "overs": 0.0,
        "balls": [],
        "striker": None,
        "non_striker": None,
        "bowler": None,
        "status": "setup"
    }

    return local_matches[match_id]

@app.post("/local-match/{match_id}/add-player")
def add_player_to_match(match_id: str, payload: dict):
    if match_id not in local_matches:
        raise HTTPException(status_code=404, detail="Local match not found")

    match = local_matches[match_id]
    team = payload.get("team")
    profile_id = payload.get("profile_id")
    phone = payload.get("phone")

    player = None

    if profile_id and profile_id in profiles:
        player = profiles[profile_id]

    if not player and phone:
        for p in profiles.values():
            if p.get("phone") == phone:
                player = p
                break

    if not player:
        raise HTTPException(status_code=404, detail="Player profile not found")

    if team == "team1":
        if player not in match["team1_players"]:
            match["team1_players"].append(player)
    elif team == "team2":
        if player not in match["team2_players"]:
            match["team2_players"].append(player)
    else:
        raise HTTPException(status_code=400, detail="Team must be team1 or team2")

    return match

   
@app.post("/local-match/{match_id}/set-lineup")
def set_match_lineup(match_id: str, payload: dict):
    if match_id not in local_matches:
        raise HTTPException(status_code=404, detail="Local match not found")

    match = local_matches[match_id]

    match["striker"] = payload.get("striker")
    match["non_striker"] = payload.get("non_striker")
    match["bowler"] = payload.get("bowler")
    match["status"] = "live"

    return match

@app.get("/local-match/{match_id}")
def get_local_match(match_id: str):
    if match_id not in local_matches:
        raise HTTPException(status_code=404, detail="Local match not found")
    return local_matches[match_id]

@app.get("/local-match")
def list_local_matches():
    return list(local_matches.values())

@app.post("/local-match/create")
def create_local_match(payload: dict):
    match_id = f"local_{len(local_matches) + 1}"

    local_matches[match_id] = {
        "id": match_id,
        "created_by": payload.get("created_by", "creator_1"),
        "team1_name": payload.get("team1_name", "Team 1"),
        "team2_name": payload.get("team2_name", "Team 2"),
        "team1_data": None,
        "team2_data": None,
        "toss_winner": None,
        "decision": None,
        "striker": None,
        "non_striker": None,
        "bowler": None,
        "score": 0,
        "wickets": 0,
        "overs": 0.0,
        "balls": [],
        "status": "setup"
    }

    return local_matches[match_id]

@app.get("/local-match")
def list_local_matches():
    return list(local_matches.values())

@app.get("/local-match/{match_id}")
def get_local_match(match_id: str):
    if match_id not in local_matches:
        raise HTTPException(status_code=404, detail="Local match not found")
    return local_matches[match_id]


