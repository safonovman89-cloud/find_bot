# Поисковый бот для MAX

Пользовательская инструкция и готовое описание для карточки MAX находятся в `BOT_DESCRIPTION.md`.

Бот ищет инструкции и документы по ключевым словам в четырёх базах:

- РСЭД ЯНАО: `https://instructions.yanao.ru/shelves/rsed-yanao`
- ГИС ЕСКУ: `http://apbook.yanao.int/books/gis-esku`
- База знаний ЯНАО: `https://kb.yanao.ru/`
- Публичные документы ЯНАО: `https://files.yanao.ru/s/7MKQp8Xqm9NDQT9`

Пользователь отправляет ключевые слова и получает до пяти наиболее релевантных результатов сразу из всех источников со ссылками. Страницы заранее сохраняются в SQLite, поэтому ответы быстрые и продолжают работать при временной недоступности исходных сайтов.

Бот распознаёт упомянутую информационную систему и хранит контекст диалога 24 часа. Поэтому после запроса «РСЭД — как подписать документ?» уточнение «а как проверить подпись?» ищется только в материалах РСЭД. Команда `/reset` или сообщение «искать везде» очищает историю и контекст. История ограничена 40 сообщениями на диалог и автоматически удаляется через 7 дней.

Если настроен AI Gateway ЯНАО, модель определяет контекст, преобразует уточняющие сообщения в самостоятельный поисковый запрос и составляет краткий ответ по найденным фрагментам. Ссылки и результаты всегда выбираются локальным поисковым индексом, а модель получает только выдержки из уже найденных материалов. При ошибке модели бот автоматически использует локальный алгоритм.

## Мини-приложение MAX

Адаптивный веб-интерфейс находится в `miniapp/`. Он ищет по всем четырём источникам, запоминает контекст выбранной системы и историю запросов на устройстве, показывает краткое описание результата и открывает оригиналы через MAX Bridge.

Публичный адрес: `https://yanao-knowledge-search.safonovman.chatgpt.site`

Для публикации копии на GitHub Pages предусмотрена статическая сборка `npm run build:pages` и workflow `.github/workflows/deploy-miniapp-pages.yml`.

Полные тексты документов в мини-приложение и репозиторий не выгружаются. Скрипт `scripts/export_miniapp_index.py` создаёт только заголовки, ссылки и необратимые поисковые сигнатуры:

```bash
python3 scripts/export_miniapp_index.py
cd miniapp
npm install
npm test
```

В настройках бота MAX укажите опубликованный HTTPS-адрес в разделе «Мини-приложение» и выберите подпись кнопки «Открыть».

## Быстрый запуск

Требуется Python 3.11+ и бот, прошедший модерацию MAX.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Загрузите переменные из `.env` удобным для вашей ОС способом и создайте индекс:

```bash
set -a; source .env; set +a
python -m bot.cli index
```

Запустите webhook-сервис:

```bash
uvicorn bot.app:app --host 0.0.0.0 --port 8000
```

Снаружи endpoint должен быть доступен как `https://ваш-домен/webhook` на порту 443 с доверенным TLS-сертификатом. После настройки reverse proxy зарегистрируйте подписку:

```bash
python -m bot.cli set-webhook
```

Зарегистрируйте команды, которые MAX показывает при вводе `/`:

```bash
python -m bot.cli set-commands
```

Проверка состояния: `GET /health`. В production запускайте один процесс Uvicorn либо вынесите обработку событий в очередь. База SQLite защищает от повторной обработки одинаковых событий MAX.

## Запуск без домена для проверки

Пока публичного HTTPS-домена нет, бот можно проверить через Long Polling:

```bash
set -a; source .env; set +a
python -m bot.cli polling
```

Откройте `https://max.ru/findinfobot`, нажмите «Начать» и отправьте запрос. Long Polling предназначен только для разработки и тестирования; для production MAX рекомендует webhook.

## Автозапуск через systemd

Готовый unit-файл находится в `deploy/findinfobot.service`. Установите и включите его:

```bash
sudo install -m 0644 deploy/findinfobot.service /etc/systemd/system/findinfobot.service
sudo systemctl daemon-reload
sudo systemctl enable --now findinfobot.service
systemctl status findinfobot.service
```

Просмотр журнала: `journalctl -u findinfobot.service -f`.

Если для пользователя включён systemd linger, можно установить службу без `sudo` из файла `deploy/findinfobot-user.service`:

```bash
install -Dm644 deploy/findinfobot-user.service ~/.config/systemd/user/findinfobot.service
systemctl --user daemon-reload
systemctl --user enable --now findinfobot.service
```

## Обновление инструкций

Запускайте ежедневно через cron или systemd timer:

```bash
python -m bot.cli index
```

Индекс каждого источника заменяется только после успешной загрузки непустого набора страниц.
Для извлечения текста из старых файлов `.doc` требуется системная утилита `antiword`.

## Переменные окружения

- `MAX_BOT_TOKEN` — токен из платформы MAX для бизнеса;
- `MAX_WEBHOOK_SECRET` — секрет проверки заголовка `X-Max-Bot-Api-Secret`;
- `MAX_WEBHOOK_URL` — публичный HTTPS URL, заканчивающийся на `/webhook`;
- `DATABASE_PATH` — путь к SQLite, по умолчанию `data/bot.sqlite3`.
- `AI_GATEWAY_API_KEY` — ключ AI Gateway ЯНАО, необязателен;
- `AI_GATEWAY_BASE_URL` — OpenAI-совместимый endpoint, по умолчанию `https://ai-gw.yanao.ru/v1`;
- `AI_GATEWAY_MODEL` — модель анализа запросов, по умолчанию `yanao/large`.

Не коммитьте `.env` и токен бота.
