# Документация: запуск и проверка голосового ассистента поликлиники

## 1. Состав стека

| Сервис | Назначение | Порт |
|---|---|---|
| `app` | FastAPI + диалоговый движок + TTS (Silero) | 8000 |
| `asterisk` | Телефония (AGI, SIP) | 5060/udp, 10000-10099/udp |
| `db` | PostgreSQL | 5432 |
| `redis` | Кэш и локи слотов | 6379 |

---

## 2. Запуск

### 2.1. Поднять все контейнеры

```bash
cd /mnt/c/hack_clinic/voice_assistant_for_a_clinic
docker compose up -d
```

### 2.2. Проверить статус

```bash
docker compose ps
```

Все 4 сервиса должны быть `Up`. Для `asterisk` — статус `Up ... (healthy)`.

---

## 3. Проверка FastAPI

### 3.1. Health

```bash
curl http://localhost:8000/health
```

Ожидаемо: `{"status":"healthy"}`.

### 3.2. Диалоговый движок

```bash
curl -X POST http://localhost:8000/demo/dialog \
  -H "Content-Type: application/json" \
  -d '{"call_id":"t1","text":"Хочу записаться к терапевту"}'
```

Ожидаемо: JSON с полем `reply` и `step: "ask_name"`.

Продолжение диалога (тот же `call_id`):

```bash
curl -X POST http://localhost:8000/demo/dialog \
  -H "Content-Type: application/json" \
  -d '{"call_id":"t1","text":"Иванов Пётр 17.03.1985"}'
```

```bash
curl -X POST http://localhost:8000/demo/dialog \
  -H "Content-Type: application/json" \
  -d '{"call_id":"t1","text":"к терапевту"}'
```

### 3.3. TTS (синтез речи)

```bash
curl -X POST http://localhost:8000/synthesize \
  -H "Content-Type: application/json" \
  -d '{"text":"Здравствуйте, это поликлиника"}' \
  -o /tmp/test_tts.wav
```

Проверка файла:

```bash
ls -la /tmp/test_tts.wav
file /tmp/test_tts.wav
```

Ожидаемо: файл >30 КБ, формат `WAVE audio, Microsoft PCM, 16 bit, mono 8000 Hz`.

---

## 4. Проверка контейнера Asterisk

### 4.1. Контейнер запущен и здоров

```bash
docker ps --filter name=clinic-asterisk
```

### 4.2. Логи Asterisk

```bash
docker logs clinic-asterisk --tail 40
```

Ищи `Asterisk Ready.` — сигнал, что всё поднялось.

### 4.3. Проверка модулей

```bash
docker exec -it clinic-asterisk asterisk -rx "module show like pjsip"
docker exec -it clinic-asterisk asterisk -rx "pjsip show endpoints"
docker exec -it clinic-asterisk asterisk -rx "pjsip show transports"
```

---

## 5. Проверка связки Asterisk ↔ FastAPI

### 5.1. Резолв имени сервиса

```bash
docker exec -it clinic-asterisk sh -c "getent hosts app"
```

Ожидаемо: `172.18.0.x   app`.

### 5.2. HTTP-запрос из контейнера Asterisk

```bash
docker exec -it clinic-asterisk python3 -c "import urllib.request; print(urllib.request.urlopen('http://app:8000/health', timeout=5).read())"
```

Ожидаемо: `b'{"status":"healthy"}'`.

---

## 6. Проверка AGI-скрипта

### 6.1. Файл на месте

```bash
docker exec -it clinic-asterisk ls -la /var/lib/asterisk/agi-bin/ga_bridge.py
```

### 6.2. Shebang правильный

```bash
docker exec -i clinic-asterisk bash <<'EOF'
head -c 30 /var/lib/asterisk/agi-bin/ga_bridge.py | od -c
EOF
```

Ожидаемо: `# ! / u s r / b i n / e n v   p y t h o n 3 \n` — без `\r`, без лишних `#`.

### 6.3. Права на исполнение

```bash
docker exec -i clinic-asterisk bash <<'EOF'
chmod +x /var/lib/asterisk/agi-bin/ga_bridge.py
ls -la /var/lib/asterisk/agi-bin/ga_bridge.py
EOF
```

### 6.4. Запуск вручную (без звонка)

```bash
docker exec -i clinic-asterisk bash <<'EOF'
/var/lib/asterisk/agi-bin/ga_bridge.py < /dev/null
echo "EXIT=$?"
EOF
```

Ожидаемо: серия строк `VERBOSE ...`, `STREAM FILE ...`, `HANGUP`, затем `EXIT=0`. Если `Exec format error` — shebang неверный, вернуться к 6.2.

---

## 7. Права на папку звуков

```bash
docker exec -it clinic-asterisk sh -c "chown -R asterisk:asterisk /var/lib/asterisk/sounds/ga && chmod -R 755 /var/lib/asterisk/sounds/ga"
docker exec -it clinic-asterisk ls -la /var/lib/asterisk/sounds/ga/
```

Ожидаемо: владелец `asterisk:asterisk`.

---

## 8. Перезагрузка dialplan

```bash
docker exec -it clinic-asterisk asterisk -rx "dialplan reload"
docker exec -it clinic-asterisk asterisk -rx "dialplan show from-internal"
```

Ожидаемо: виден экстеншен `999` → `AGI(ga_bridge.py)`.

---

## 9. Запуск CLI Asterisk для наблюдения

В отдельном окне WSL:

```bash
docker exec -it clinic-asterisk asterisk -rvvv
```

Оставь окно открытым. Выход — `exit` или `Ctrl+C`.

---

## 10. Звонок из MicroSIP

### 10.1. Настройки аккаунта MicroSIP

| Поле | Значение |
|---|---|
| SIP-сервер | IP WSL (получить: `hostname -I`) |
| SIP-прокси | (пусто) |
| Имя пользователя | `1001` |
| Домен | IP WSL |
| Логин | `1001` |
| Пароль | `secret1001` |
| Транспорт | UDP |
| Публичный адрес | Авто |

### 10.2. IP WSL

```bash
hostname -I
```

Пример: `172.25.105.119`.

### 10.3. Звонок

В MicroSIP набрать `999` → нажать **Вызов**.

Ожидаемая последовательность:

1. ~1–3 сек пауза
2. Голос: «Здравствуйте! Это голосовой ассистент поликлиники…»
3. Нажать `1` — движок отвечает
4. Нажать `0` — выход

---

## 11. Диагностика проблем

### 11.1. `Exec format error`

Причина: неправильный shebang или CRLF в первой строке.

```bash
docker exec -i clinic-asterisk bash <<'EOF'
sed -i '1s|^.*$|#!/usr/bin/env python3|' /var/lib/asterisk/agi-bin/ga_bridge.py
sed -i 's/\r$//' /var/lib/asterisk/agi-bin/ga_bridge.py
chmod +x /var/lib/asterisk/agi-bin/ga_bridge.py
head -c 30 /var/lib/asterisk/agi-bin/ga_bridge.py | od -c
EOF
```

### 11.2. AGI падает на записи WAV

Причина: у пользователя `asterisk` нет прав на `/var/lib/asterisk/sounds/ga/`.

```bash
docker exec -it clinic-asterisk sh -c "chown -R asterisk:asterisk /var/lib/asterisk/sounds/ga && chmod -R 755 /var/lib/asterisk/sounds/ga"
```

### 11.3. Тишина в трубке, но скрипт отработал

Проверить, что WAV создан:

```bash
docker exec -it clinic-asterisk ls -la /var/lib/asterisk/sounds/ga/
```

### 11.4. `STREAM FILE` не находит файл

Asterisk ищет файлы в `/var/lib/asterisk/sounds/<язык>/`. В AGI указывать путь без расширения. Команда:

```text
STREAM FILE ga/call_hello ""
```

означает `/var/lib/asterisk/sounds/ga/call_hello.wav`.

### 11.5. Логи FastAPI

```bash
docker logs voice_assistant_for_a_clinic-app-1 --tail 50
```

### 11.6. Полные логи Asterisk

```bash
docker exec -it clinic-asterisk tail -100 /var/log/asterisk/full
```

---

## 12. Пересборка контейнера app

После правок `requirements.txt` или `Dockerfile`:

```bash
cd /mnt/c/hack_clinic/voice_assistant_for_a_clinic
docker compose build app
docker compose up -d app
```

---

## 13. Полный перезапуск

```bash
cd /mnt/c/hack_clinic/voice_assistant_for_a_clinic
docker compose down
docker compose up -d
docker compose ps
```

После `down` — повторить разделы 6.3 и 7 (права слетают, потому что контейнер создаётся заново).

---

## 14. Чек-лист «всё работает»

1. `docker compose ps` — 4 сервиса `Up`
2. `curl http://localhost:8000/health` → `{"status":"healthy"}`
3. `curl -X POST http://localhost:8000/synthesize ...` → WAV 8000 Hz mono PCM16
4. `docker exec ... python3 -c "import urllib.request; ... urlopen('http://app:8000/health')"` → `healthy`
5. `docker exec ... head -c 30 ga_bridge.py | od -c` → `#!...python3\n`
6. `docker exec ... ga_bridge.py < /dev/null` → `EXIT=0`
7. `docker exec ... ls /var/lib/asterisk/sounds/ga/` → владелец `asterisk:asterisk`
8. MicroSIP зарегистрирован (`1001`, зелёный статус)
9. Звонок на `999` → слышен голос ассистента

---

## Приложение: исправления, которые уже сделаны в проекте

| Что | Где | Зачем |
|---|---|---|
| Замена `requests` на `urllib` | `asterisk-agi/ga_bridge.py` | В контейнере Asterisk нет pip и пакета `requests` |
| Shebang `#!/usr/bin/env python3` | первая строка `ga_bridge.py` | Без него `Exec format error` |
| Удаление CRLF (`sed 's/\r$//'`) | `ga_bridge.py` | Windows-переносы ломают shebang |
| `chown asterisk:asterisk` | `/var/lib/asterisk/sounds/ga/` | AGI работает от `asterisk`, не от `root` |
| Правильный `requirements.txt` | корень проекта | `silero-tts==1.0.0` не существует; заменено на `silero` + CPU-torch |
| `--extra-index-url .../whl/cpu` | `requirements.txt` | CPU-версия torch ~200 МБ вместо 2 ГБ CUDA |
| Подключение `voice_routes.py` в `main.py` | `app/main.py` | Без этого `/synthesize` недоступен |