# Brawl Draft — помощник драфта ранкеда Brawl Stars (проект Никиты)

Отвечать по-русски, коротко. Пользователь не программист: давать простые шаги, делать самому всё, что можно.

## Из чего состоит
1. **Сборщик статистики** — `collector/` в этом репо, GitHub Actions `.github/workflows/collect.yml`
   (каждые 3 ч, ручной запуск: REST `POST /repos/dlayabotarankedsobr/brawl-ranked-stats/actions/workflows/collect.yml/dispatches`
   с `ref=main`, `inputs[run_seconds]=600`; `gh workflow run` не работает — GraphQL закрыт).
   - Пишет в ветку `state`: `data/daily/ГГГГ-ММ-ДД.json` (бои, пары, контры, точные сборки из боёв, **сборки из профилей**),
     `data/stats.json` (агрегат за **10 дней**, `WINDOW_DAYS`), players/seen/profiled/rank_names/brawlers.json.
   - Окно 10 дней: старые daily удаляются; общего builds.json больше нет (сборки — по дням).
   - Ключ Brawl Stars API (секрет `BS_API_KEY`) привязан к IP прокси RoyaleAPI 45.79.218.79; API = https://bsproxy.royaleapi.dev/v1.
   - Учитываются игры Легенды+ (rank ≥ 16; rank = brawler.trophies в soloRanked; 22 = Про).
2. **Мини-приложение** — `docs/` (GitHub Pages): https://dlayabotarankedsobr.github.io/brawl-ranked-stats/
   - Один файл `docs/index.html` (чистый JS), данные: stats.json с ветки state, `docs/app-data.json` (108 бойцов, классы, RU-имена),
     `docs/map-terrain.json` (доля кустов), `docs/ranked-season.json` (**3 бойца сезона на 11 силе — менять каждый сезон**,
     сезон начинается в 3-й четверг месяца; источник — вики Brawl Stars → Ranked → Trial Brawlers).
   - Картинки: Brawlify CDN (cdn.brawlify.com), баффи-версии значков — BSInfo (raw.githubusercontent.com/lot-xq/BSInfo-CDN/HEAD/{gadgets|starpowers|hypercharges}/buffies/{id}.png),
     капли силы `docs/img/hc*.png`.
   - Логика: brawlerScore (сглаживание K=100), pairDelta (Вильсон), vsEdge = статистика пары + классовые контры (CLASS_VS, ANTI_THROWER),
     counterThreat (кого ещё может взять соперник), composition (открытость карты), accountPenalty / canPick (в пики — только 11 сила или бойцы сезона),
     banPlan (баны зависят от того, кто пикает первым), gearPick (доля у Легенды+ + точные сборки + правила кустов/открытости/соперников).
   - Аккаунт: прокачка кодируется в ссылке `#acc=` (версия 2 = raw deflate) или приходит с сервера бота; хранится в Telegram CloudStorage.
   - Сервер бота: адрес в `?api=` ссылки (запоминается в CloudStorage). Если 502 — «сервер игры не отвечает», иначе фолбэк в чат.
   - Проверка: после пуша Pages обновляется ~1–15 мин; тестировать во встроенном браузере (fetch работает) — в контейнере данные не грузятся.
3. **Telegram-бот** @brawl_draft_helper_bot — на ПК пользователя: `C:\Users\Nameless\PycharmProjects\brawl_draft_bot` (копия: /home/claude/brawl_draft_bot).
   - `bot.py`: /start, поиск по тегу, картинка профиля, aiohttp-сервер 127.0.0.1:8787+ (`/api/profile`, `/api/card`, проверка подписи initData),
     туннель: cloudflared (у пользователя не работает — DPI/VPN рвёт TLS к edge) → запасной **localhost.run через ssh** (работает; адрес меняется при перезапуске).
     Журналы: `bot.log`, `tunnel_output.log`, `api_url.txt`.
   - `profile_html.py` — картинка профиля (HTML → PNG через Playwright, один общий браузер, семафор 3, кэш 10 мин); `profile_card.py` — загрузка ассетов + запасной Pillow.
   - `assets/` — пустые рамки (gadget/sp/hc/gear), шарик баффи, значки режимов; `buffie_icons.json`, `hypercharge_icons.json`.
   - `start.bat` — venv, pip, `playwright install chromium`, запуск. `.env` (BOT_TOKEN, BS_API_KEY) — защищён, **ключи никогда не вводить самому**.

## Как доставлять файлы на ПК пользователя
- `device_commit_files` молча НЕ перезаписывает существующие файлы → класть в `_update\` и делать `cat _update/x > x` через device_bash, сверять md5.
- Файлы > 30 МБ или без расширения не проходят — резать на куски ~9 МБ `.bin` и склеивать `cat`.
- Папка на устройстве: `$HOME/mnt/PycharmProjects/brawl_draft_bot`. У VM нет интернета.
- Перезапуск бота самому: computer-use (Проводник и cmd — только клики): закрыть крестиком окно cmd бота, выделить start.bat, лента «Открыть».
  Telegram — tier full (можно открыть приложение и проверить). После рестарта отправить боту /start (обновляет кнопку меню с новым адресом).

## Предпочтения пользователя по картинке профиля (не ломать)
Синий стиль SLT; сила — цифра внутри капли гиперзаряда (фиолетовая/баффи/серая); у пассивок/гаджетов/снаряжения — цифра внутри пустой рамки;
баффи — игровые значки с белой рамкой; сортировка: сила ↓, баффи ↓, кубки ↓; ранкед — только значок + эло (без названия лиги);
в шапке: 9 плиток (сила 11, бойцы, пассивки, гаджеты, гиперзаряды, баффи X/81 с шариком, снаряжение, победы 3×3, победы в столкновении).
