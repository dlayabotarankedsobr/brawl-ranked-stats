# Brawl Stars ranked stats

Сборщик статистики ранкеда (Легенда и выше + игры про-игроков) через официальный Brawl Stars API.
Запускается в GitHub Actions каждые 3 часа, результат — `data/stats.json` в ветке `state`.

Настройка: Settings → Secrets and variables → Actions → New repository secret,
имя `BS_API_KEY`, значение — ключ с developer.brawlstars.com (IP `45.79.218.79`).
