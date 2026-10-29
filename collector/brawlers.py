"""
Скачивает актуальный список бойцов:
  * официальный Brawl Stars API (/brawlers) — все бойцы, которые есть в игре;
  * Brawlify API — класс бойца (Damage Dealer, Tank, Marksman, ...).
Результат: data/brawlers.json. Ошибки не фатальны — сборщик игр работает и без этого файла.
"""
import json
import os
import urllib.request
from pathlib import Path

BASE = os.getenv("BS_API_BASE", "https://bsproxy.royaleapi.dev/v1")
KEY = os.getenv("BS_API_KEY")
OUT = Path(__file__).resolve().parent.parent / "data" / "brawlers.json"


def get(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "brawl-draft-helper/1.0", **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    out = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    try:
        data = get(BASE + "/brawlers?limit=300", {"Authorization": f"Bearer {KEY}"})
        for b in data.get("items", []):
            e = out.setdefault(b["name"], {})
            e["id"] = b["id"]
            # гаджеты и пассивки по порядку ID — по ним приложение расшифровывает прокачку аккаунта
            e["gadgets"] = sorted(([g["id"], g["name"]] for g in b.get("gadgets", [])))
            e["starPowers"] = sorted(([g["id"], g["name"]] for g in b.get("starPowers", [])))
        print("Официальный API: бойцов", len(data.get("items", [])))
    except Exception as e:
        print("Официальный список не загрузился:", repr(e))
    try:
        data = get("https://api.brawlify.com/v1/brawlers")
        items = data.get("list", data if isinstance(data, list) else [])
        n = 0
        for b in items:
            nm = (b.get("name") or "").upper()
            match = next((k for k in out if k.upper() == nm), None) or nm
            cls = (b.get("class") or {}).get("name")
            rar = (b.get("rarity") or {}).get("name")
            entry = out.setdefault(match, {})
            if cls:
                entry["class"] = cls
                n += 1
            if rar:
                entry["rarity"] = rar
        print("Brawlify: классов", n)
    except Exception as e:
        print("Классы с Brawlify не загрузились:", repr(e))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print("Всего бойцов в brawlers.json:", len(out))


if __name__ == "__main__":
    main()
