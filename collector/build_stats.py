"""
Собирает data/stats.json из дневных файлов за последние WINDOW_DAYS дней.
Этот файл читает бот.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DAILY = ROOT / "data" / "daily"
OUT = ROOT / "data" / "stats.json"
WINDOW_DAYS = int(os.getenv("WINDOW_DAYS", "21"))
RECENT_DAYS = 7
MIN_PAIR_GAMES = 8   # пары/контры с меньшим числом игр не сохраняем


def add(dst, src):
    for k, (g, w) in src.items():
        cell = dst.setdefault(k, [0, 0])
        cell[0] += g
        cell[1] += w


def main():
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    recent = (now - timedelta(days=RECENT_DAYS)).strftime("%Y-%m-%d")
    out = {"updated": now.strftime("%Y-%m-%d %H:%M UTC"), "window_days": WINDOW_DAYS,
           "games": 0, "pro_games": 0, "maps": {}, "brawlers": {}, "pro": {},
           "mode_brawlers": {}, "vs": {}, "with": {}}
    for f in sorted(DAILY.glob("*.json")):
        if f.stem < start:
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        out["games"] += d["games"]
        out["pro_games"] += d.get("pro_games", 0)
        for map_, mode in d["modes"].items():
            m = out["maps"].setdefault(map_, {"mode": mode, "games": 0, "recent_games": 0})
            g = sum(v[0] for v in d["brawlers"].get(map_, {}).values()) // 6
            m["games"] += g
            if f.stem >= recent:
                m["recent_games"] += g
            add(out["brawlers"].setdefault(map_, {}), d["brawlers"].get(map_, {}))
            add(out["pro"].setdefault(map_, {}), d.get("pro_brawlers", {}).get(map_, {}))
            add(out["mode_brawlers"].setdefault(mode, {}), d["brawlers"].get(map_, {}))
        for mode in d["vs"]:
            add(out["vs"].setdefault(mode, {}), d["vs"][mode])
        for mode in d["with"]:
            add(out["with"].setdefault(mode, {}), d["with"][mode])
    bl = ROOT / "data" / "brawlers.json"
    if bl.exists():  # полный список бойцов с классами — бот берёт его отсюда
        out["brawler_list"] = json.loads(bl.read_text(encoding="utf-8"))
    for key in ("vs", "with"):
        for mode, pairs in out[key].items():
            out[key][mode] = {k: v for k, v in pairs.items() if v[0] >= MIN_PAIR_GAMES}
    out["pro"] = {m: v for m, v in out["pro"].items() if v}
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"stats.json: {out['games']} игр, {out['pro_games']} с про-игроками, "
          f"{len(out['maps'])} карт, {OUT.stat().st_size // 1024} КБ")


if __name__ == "__main__":
    main()
