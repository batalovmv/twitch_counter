
# 🎥 Twitch Stream Stats Bot

Бот для Twitch, который:

- 📊 считает **минуты присутствия** зрителей по сообщениям в чате  
- 🕹️ работает только **когда стрим в онлайне** (через Twitch Helix API)  
- 💾 хранит статистику в **Yandex YDB Serverless**  
- 📢 отправляет красивые уведомления в **Telegram-канал**:  
  - при старте стрима создаёт пост  
  - обновляет его каждую минуту (игра / зрители / заголовок)  
  - при завершении стрима удаляет пост  
- ⚡ команды: `!top`, `!watchtime`, `!settopn`, `!help`  

---

## 📂 Структура проекта

```

twitch\_counter/
├─ README.md
├─ .gitignore
├─ .env.example
├─ requirements.txt
├─ Dockerfile
├─ run.sh          # запуск на Linux/macOS
├─ run.ps1         # запуск на Windows PowerShell
└─ src/
└─ bot/
├─ main.py
├─ config.py
├─ util/time.py
├─ data/store\_ydb.py
└─ services/
├─ accrual.py
├─ twitch\_bot.py
├─ live\_state.py
└─ telegram\_notifier.py

````

---

## ⚙️ Настройка `.env`

Скопируй `.env.example` → `.env` и укажи свои данные:

```env
# Twitch
TWITCH_BOT_USERNAME=имя_бота
TWITCH_OAUTH_TOKEN=oauth:xxxxxxxxxxxxxxxxx
TWITCH_CHANNEL=имя_канала
TWITCH_CLIENT_ID=your_twitch_app_id
TWITCH_CLIENT_SECRET=your_twitch_app_secret

# Бот
BOT_DEFAULT_TOPN=3
TICK_INTERVAL_MINUTES=1
ACTIVE_WINDOW_MINUTES=5
LIVE_POLL_SECONDS=60

# YDB
DB_PROVIDER=ydb
YDB_ENDPOINT=grpcs://ydb.serverless.yandexcloud.net:2135
YDB_DATABASE=/ru-central1/.../...

# Для локального запуска
YDB_METADATA_CREDENTIALS=0
YDB_SERVICE_ACCOUNT_KEY_FILE_CREDENTIALS=/abs/path/to/key.json

# Для облака (ВМ с сервисным аккаунтом)
# YDB_METADATA_CREDENTIALS=1

# Telegram
TG_BOT_TOKEN=1234567:AA...
TG_CHAT_ID=@my_channel
TG_PARSE_MODE=HTML
TG_DISABLE_WEB_PAGE_PREVIEW=1
````

---

## 🚀 Запуск

### Локально

Linux/macOS:

```bash
python3 -m pip install -r requirements.txt
chmod +x run.sh
./run.sh
```

Windows PowerShell:

```powershell
py -3 -m pip install -r requirements.txt
.\run.ps1
```

---

### Docker

Сборка:

```bash
docker build -t twitch-counter .
```

Запуск:

```bash
docker run -d --name twitch-counter --restart unless-stopped \
  -e TWITCH_BOT_USERNAME=... \
  -e TWITCH_OAUTH_TOKEN=oauth:... \
  -e TWITCH_CHANNEL=... \
  -e TWITCH_CLIENT_ID=... \
  -e TWITCH_CLIENT_SECRET=... \
  -e DB_PROVIDER=ydb \
  -e YDB_ENDPOINT=grpcs://ydb.serverless.yandexcloud.net:2135 \
  -e YDB_DATABASE=/ru-central1/... \
  -e YDB_METADATA_CREDENTIALS=1 \
  -e TG_BOT_TOKEN=... \
  -e TG_CHAT_ID=@my_channel \
  cr.yandex/<registry_id>/twitch-counter:latest
```

---

## ☁️ Деплой в Yandex Cloud

1. Создай **Container Registry** и запушь туда образ
2. Создай сервисный аккаунт с ролями:

   * `ydb.editor`
   * `container-registry.images.puller`
3. Подними **минимальную ВМ** в Compute Cloud (2 vCPU, 2 GB RAM)
4. На ВМ установи Docker и запусти контейнер как выше (`--restart unless-stopped`)

> Почему не Serverless Containers?
> Потому что Twitch-бот работает через постоянное WebSocket-соединение, а серверлесс подходит только для запрос-ответ (HTTP).

---

## 📜 Команды

* `!top [N]` — топ N зрителей за месяц (по умолчанию 3). Стример и бот не выводятся.
* `!watchtime [ник]` — минуты зрителя за месяц.
* `!settopn N` — меняет значение по умолчанию (только для стримера/модеров).
* `!help` — список команд.

---

## ⏱️ Как работает подсчёт минут

1. Зритель пишет сообщение → бот помечает его активным
2. Каждую минуту бот добавляет +1 всем, кто был активен в последние `ACTIVE_WINDOW_MINUTES`
3. Если стрима нет — минуты не считаются
4. Данные пишутся помесячно (`YYYY-MM`)

---

## 📢 Telegram

* При старте стрима бот создаёт пост в канале
* Каждую минуту обновляет (игра, зрители, заголовок)
* При завершении — удаляет пост
* Новый стрим → новое сообщение

---

## 🛠️ Типичные ошибки

* ❌ `YDB_METADATA_CREDENTIALS=1` локально
  ✔ Используй `=0` и ключ JSON

* ❌ В `YDB_ENDPOINT` добавлен `?database=...`
  ✔ Endpoint и database должны быть **раздельно**

* ❌ `TWITCH_OAUTH_TOKEN` без `oauth:`
  ✔ Токен обязательно с префиксом



