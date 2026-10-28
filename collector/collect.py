"""
Сборщик ранговых игр Brawl Stars через официальный API (прокси RoyaleAPI).

Что делает за один запуск:
  1. Берёт игроков: топы рейтингов, теги про-игроков (pro_tags.txt), очередь найденных ранее.
  2. Читает их историю боёв, оставляет только ранкед (и дружеские игры про-игроков).
  3. Пропускает уже учтённые бои и игры ниже MIN_RANK.
  4. Складывает счётчики (игры/победы по картам, контрпики, пары) в data/daily/ГГГГ-ММ-ДД.json.

Только стандартная библиотека Python — ставить ничего не нужно.
Ключ берётся из переменной окружения BS_API_KEY.
"""
import hashlib
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = os.getenv("BS_API_BASE", "https://bsproxy.royaleapi.dev/v1")
KEY = os.getenv("BS_API_KEY")
RUN_SECONDS = int(os.getenv("RUN_SECONDS", "720"))       # сколько работать за запуск
WORKERS = int(os.getenv("WORKERS", "6"))                  # параллельных запросов
# Ранг в ранкеде: 1-3 Бронза, 4-6 Серебро, 7-9 Золото, 10-12 Алмаз,
# 13-15 Мифик, 16-18 Легенда, 19-21 Мастер, 22 Про. Проверяется по data/rank_names.json.
MIN_RANK = int(os.getenv("MIN_RANK", "16"))
RANKED_TYPES = {"soloRanked", "teamRanked"}
SEEN_KEEP_DAYS = 4

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DAILY = DATA / "daily"
PLAYERS_FILE = DATA / "players.json"      # очередь игроков: тег -> время последней проверки
SEEN_FILE = DATA / "seen.json"            # id уже учтённых боёв: день -> [id]
RANK_NAMES_FILE = DATA / "rank_names.json"
PRO_TAGS_FILE = ROOT / "collector" / "pro_tags.txt"

SEED_COUNTRIES = ["global", "ru", "us", "br", "kr", "jp", "de", "fr", "es", "tr", "mx", "pl", "ua", "kz"]


# ---------------- API ----------------
class Api:
    def __init__(self, key):
        self.key = key
        self.calls = 0
        self.errors = 0

    def get(self, path, retries=3):
        url = BASE + path
        for attempt in range(retries):
            req = urllib.request.Request(url, headers={
                "Authorization": f"Bearer {self.key}", "Accept": "application/json",
                "User-Agent": "brawl-draft-helper/1.0"})
            try:
                with urllib.request.urlopen(req, timeout=20) as r:
                    self.calls += 1
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                if e.code == 403:
                    raise SystemExit("403: ключ не подходит. Проверь, что в ключе указан IP 45.79.218.79 "
                                     "и что секрет BS_API_KEY вставлен целиком.")
                if e.code in (429, 500, 502, 503, 504):
                    time.sleep(1.5 * (attempt + 1) + random.random())
                    continue
                self.errors += 1
                return None
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                time.sleep(1 + attempt)
        self.errors += 1
        return None


def tag_path(tag):
    return urllib.parse.quote(tag if tag.startswith("#") else "#" + tag)


# ---------------- хранилище ----------------
def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, obj, compact=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":") if compact else None,
                      indent=None if compact else 1, sort_keys=True)
    path.write_text(text, encoding="utf-8")


def parse_time(s):  # "20261028T201530.000Z"
    return datetime.strptime(s[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)


def new_day():
    # brawlers: map -> brawler -> [games, wins]
    # vs:       mode -> "A|B" -> [games, wins of A]   (A против B)
    # with:     mode -> "A|B" -> [games, wins]        (A и B в одной команде, A<B)
    # modes:    map -> mode,  pro: те же счётчики только для про-игроков
    return {"games": 0, "modes": {}, "brawlers": {}, "vs": {}, "with": {},
            "pro_games": 0, "pro_brawlers": {}}


def bump(d, k1, k2, win):
    cell = d.setdefault(k1, {}).setdefault(k2, [0, 0])
    cell[0] += 1
    cell[1] += 1 if win else 0


# ---------------- разбор боя ----------------
def battle_id(item, tags):
    raw = item["battleTime"] + "|" + "|".join(sorted(tags))
    return hashlib.blake2b(raw.encode(), digest_size=6).hexdigest()


def extract(item, owner_tag):
    """Возвращает (id, день, режим, карта, команды[[имена]], победившая_команда, ранги, теги, тип) или None."""
    b, ev = item.get("battle") or {}, item.get("event") or {}
    teams = b.get("teams")
    if not teams or len(teams) != 2 or any(len(t) != 3 for t in teams):
        return None
    result = b.get("result")
    if result not in ("victory", "defeat"):
        return None
    mode, map_ = ev.get("mode") or b.get("mode"), ev.get("map")
    if not mode or not map_:
        return None
    tags = [p.get("tag") for t in teams for p in t]
    names = [[(p.get("brawler") or {}).get("name") for p in t] for t in teams]
    if any(n is None for t in names for n in t):
        return None
    my_team = next((i for i, t in enumerate(teams) if any(p.get("tag") == owner_tag for p in t)), None)
    if my_team is None:
        return None
    winner = my_team if result == "victory" else 1 - my_team
    ranks = [(p.get("brawler") or {}).get("trophies") for t in teams for p in t]
    day = parse_time(item["battleTime"]).strftime("%Y-%m-%d")
    return battle_id(item, tags), day, mode, map_, names, winner, ranks, tags, b.get("type")


def add_battle(day_data, mode, map_, names, winner, pro=False):
    day_data["games"] += 1
    day_data["modes"][map_] = mode
    for ti, team in enumerate(names):
        win = ti == winner
        enemy = names[1 - ti]
        for a in team:
            bump(day_data["brawlers"], map_, a, win)
            if pro:
                bump(day_data["pro_brawlers"], map_, a, win)
            for e in enemy:
                bump(day_data["vs"], mode, f"{a}|{e}", win)
        for i in range(3):
            for j in range(i + 1, 3):
                x, y = sorted((team[i], team[j]))
                bump(day_data["with"], mode, f"{x}|{y}", win)
    if pro:
        day_data["pro_games"] += 1


# ---------------- основной цикл ----------------
def main():
    if not KEY:
        raise SystemExit("Нет ключа BS_API_KEY")
    api = Api(KEY)
    start = time.time()
    now = datetime.now(timezone.utc)

    players = load_json(PLAYERS_FILE, {})                  # tag -> unix time последней проверки
    seen = load_json(SEEN_FILE, {})                        # day -> [ids]
    rank_names = load_json(RANK_NAMES_FILE, {})
    cutoff = (now - timedelta(days=SEEN_KEEP_DAYS)).strftime("%Y-%m-%d")
    seen = {d: ids for d, ids in seen.items() if d >= cutoff}
    seen_set = {i for ids in seen.values() for i in ids}
    days: dict[str, dict] = {}

    pro_tags = set()
    if PRO_TAGS_FILE.exists():
        for line in PRO_TAGS_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("//"):
                tag = line.split()[0].upper()
                pro_tags.add(tag if tag.startswith("#") else "#" + tag)

    # 1) Сиды: топ-рейтинги стран
    for c in SEED_COUNTRIES:
        data = api.get(f"/rankings/{c}/players?limit=200")
        for p in (data or {}).get("items", []):
            players.setdefault(p["tag"], 0)
    for t in pro_tags:
        players.setdefault(t, 0)

    # 2) Очередь: про-игроки всегда первыми, дальше — давно не проверенные
    def queue():
        order = sorted(players, key=lambda t: (t not in pro_tags, players[t]))
        return order

    stats = {"ranked": 0, "pro": 0, "low_rank": 0, "dup": 0, "players": 0}
    rank_hist: dict[int, int] = {}

    def fetch(tag):
        return tag, api.get(f"/players/{tag_path(tag)}/battlelog")

    def handle(tag, data):
        stats["players"] += 1
        players[tag] = int(time.time())
        for item in (data or {}).get("items", []):
            b = item.get("battle") or {}
            is_pro = tag in pro_tags
            btype = b.get("type")
            if btype not in RANKED_TYPES and not (is_pro and btype == "friendly"):
                continue
            ex = extract(item, tag)
            if not ex:
                continue
            bid, day, mode, map_, names, winner, ranks, tags, btype = ex
            if day < cutoff:
                continue
            if bid in seen_set:
                stats["dup"] += 1
                continue
            for t in tags:  # расширяем очередь игроками из ранкеда
                if btype in RANKED_TYPES and t not in players:
                    players[t] = 0
            pro_game = any(t in pro_tags for t in tags)
            if btype in RANKED_TYPES:
                valid = [r for r in ranks if isinstance(r, int)]
                avg = sum(valid) / len(valid) if valid else 0
                if valid:
                    rank_hist[round(avg)] = rank_hist.get(round(avg), 0) + 1
                if avg < MIN_RANK and not pro_game:
                    stats["low_rank"] += 1
                    seen_set.add(bid)
                    seen.setdefault(day, []).append(bid)
                    continue
            seen_set.add(bid)
            seen.setdefault(day, []).append(bid)
            if day not in days:
                days[day] = load_json(DAILY / f"{day}.json", None) or new_day()
            add_battle(days[day], mode, map_, names, winner, pro=pro_game)
            stats["ranked"] += 1
            stats["pro"] += 1 if pro_game else 0

    # 3) Иногда смотрим профили — узнаём, какие номера рангов соответствуют названиям
    def learn_ranks(sample):
        for tag in sample:
            p = api.get(f"/players/{tag_path(tag)}")
            if p and p.get("rankedRank") is not None and p.get("rankedRankName"):
                rank_names[str(p["rankedRank"])] = p["rankedRankName"]

    learn_ranks(random.sample(list(players), min(15, len(players))))

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        q = queue()
        i = 0
        while i < len(q) and time.time() - start < RUN_SECONDS:
            batch = q[i:i + WORKERS * 4]
            i += len(batch)
            for tag, data in pool.map(fetch, batch):
                handle(tag, data)
            if len(players) > len(q) and i >= len(q):
                q = queue()
                i = 0

    # 4) Чистим очередь, чтобы файл не рос бесконечно: оставляем 60 000 самых свежих
    if len(players) > 60000:
        keep = sorted(players, key=lambda t: (t not in pro_tags, -players[t]))[:60000]
        players = {t: players[t] for t in keep}

    for day, d in days.items():
        save_json(DAILY / f"{day}.json", d)
    # чистим старые дневные файлы (старше 35 дней)
    old = (now - timedelta(days=35)).strftime("%Y-%m-%d")
    for f in DAILY.glob("*.json"):
        if f.stem < old:
            f.unlink()
    save_json(PLAYERS_FILE, players)
    save_json(SEEN_FILE, seen)
    save_json(RANK_NAMES_FILE, rank_names, compact=False)

    print(f"Запросов: {api.calls}, ошибок: {api.errors}, игроков проверено: {stats['players']}")
    print(f"Новых игр учтено: {stats['ranked']} (с про-игроками: {stats['pro']}), "
          f"ниже ранга {MIN_RANK}: {stats['low_rank']}, повторов: {stats['dup']}")
    print("Средний ранг в найденных играх:", dict(sorted(rank_hist.items())))
    print("Названия рангов:", rank_names)


if __name__ == "__main__":
    sys.exit(main())
