"""Probe: MoneyPuck shot-level data. Downloads one season's zip, prints the columns and a few rows."""
import io, sys, zipfile
import requests

season = sys.argv[1] if len(sys.argv) > 1 else "2025"
url = f"https://peter-tanner.com/moneypuck/downloads/shots_{season}.zip"
alt = f"https://moneypuck.com/moneypuck/playerData/shots/shots_{season}.zip"
for u in (url, alt):
    try:
        r = requests.get(u, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
        print("GET", u, r.status_code, len(r.content), "bytes")
        if r.ok and len(r.content) > 1000:
            break
    except Exception as e:
        print("GET", u, "failed:", e)
else:
    sys.exit(0)
z = zipfile.ZipFile(io.BytesIO(r.content))
print("members:", z.namelist())
name = [n for n in z.namelist() if n.endswith(".csv")][0]
with z.open(name) as f:
    head = [next(f).decode("utf-8", "replace").rstrip("\n") for _ in range(4)]
cols = head[0].split(",")
print("columns (%d):" % len(cols))
for i in range(0, len(cols), 8):
    print("  ", ", ".join(cols[i:i + 8]))
for row in head[1:]:
    vals = row.split(",")
    print("row:", {c: v for c, v in zip(cols, vals) if c in ("game_id","homeTeamCode","awayTeamCode","period","time","event","xGoal","shotType","teamCode","isHomeTeam","goal","shotDistance","arenaAdjustedShotDistance","xCordAdjusted","yCordAdjusted","goalieNameForShot","shooterName","homeSkatersOnIce","awaySkatersOnIce","isPlayoffGame","season","shotOnEmptyNet","shotRebound","shotRush","shotGeneratedRebound","playerPositionThatDidEvent")})
