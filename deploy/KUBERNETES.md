# Развёртывание в k3s

Бот работает в namespace `findinfobot` одним экземпляром Long Polling. Индекс SQLite
хранится в PVC `findinfobot-data`. CronJob `findinfobot-index` обновляет индекс ежедневно
в 03:15 по часовому поясу `Asia/Yekaterinburg`.

Образ собирается без `.env`, SQLite, истории чатов и содержимого документов:
В него включён публичный `Russian Trusted Root CA`, необходимый для проверки TLS
`platform-api2.max.ru`; проверка сертификатов не отключается.

```bash
docker build -t findinfobot:20261111-2 .
docker save -o /tmp/findinfobot-20261111-2.tar findinfobot:20261111-2
```

На узле k3s образ импортируется командой:

```bash
k3s ctr images import /opt/find_bot/findinfobot-20261111-2.tar
```

Secret создаётся отдельно из защищённого файла окружения и не хранится в Git:

```bash
kubectl -n findinfobot create secret generic findinfobot-env \
  --from-env-file=/root/findinfobot.env
```

Применение и проверка:

```bash
kubectl apply -f deploy/kubernetes.yaml
kubectl -n findinfobot rollout status deployment/findinfobot
kubectl -n findinfobot logs deployment/findinfobot --tail=100
```
