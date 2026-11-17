# Disaster recovery: rebuilding GameMetrix from nothing

Target: the site is back within one hour of losing the VM, with at most one day of data
lost (the nightly dump). Everything below is copy-pasteable; read it once now, not during
the outage.

## What lives where (and what is NOT in Git)

| Thing | Where it lives | If the VM dies |
|---|---|---|
| Code, compose files, ops scripts | GitHub | fine |
| Application images | `ghcr.io/alparslansemiz/gamemetrix-{backend,frontend}:sha-<commit>` | fine, pulled again |
| Database | Docker volume `pgdata` + nightly dump in `/var/backups/gamemetrix/` | **lost unless the dump was copied off the VM** |
| `/home/ubuntu/gamemetrix/Gamemetrix/.env` and `backend/.env` | VM only | **lost: keep an encrypted copy in the password manager** |
| Origin TLS certificate and key | `/etc/gamemetrix/origin-tls/` | certificate can be re-issued (see step 5) |
| Notification settings | `/etc/gamemetrix/notify.env` | recreate (step 9) |
| DNS, Cloudflare settings | Cloudflare | fine |

Before you ever need this: set `BACKUP_REMOTE` for `ops/backup-db.sh` so a dump leaves the VM
every night, and store both `.env` files (age/gpg-encrypted or in the password manager) off
the VM. Run `ops/restore-test.sh` monthly so you know the dumps actually restore.

## 1. New VM

- bwCloud (Karlsruhe) `p1.nano` or bigger, Ubuntu LTS, your SSH key. The current host is
  IPv6 only; Cloudflare proxies IPv4 visitors to it.
- Security group: SSH (22) from your address, and **80/443 only from Cloudflare's ranges**
  (https://www.cloudflare.com/ips-v4/ and https://www.cloudflare.com/ips-v6/). This is how the
  current VM was set up on 2026-11-17; the host firewall script in step 8 is the second layer.
- Add swap (the host has 1 GB RAM, the stack is sized for 4 GB of swap):

```bash
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 2. Docker and the code

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu          # log out and in again
mkdir -p ~/gamemetrix && cd ~/gamemetrix
git clone https://github.com/AlparslanSemiz/Gamemetrix.git
cd Gamemetrix
```

## 3. Environment files

Restore both files from the encrypted copy, then lock them down. If there is no copy, start
from the examples and see `docs/production-security-runbook.md` ("Required production
environment") for every required value; provider keys must be re-issued.

```bash
sudo install -o root -g root -m 600 /path/to/root.env .env
sudo install -o root -g root -m 600 /path/to/backend.env backend/.env
```

`.env` must contain `ENV=production`, the `POSTGRES_*` and `APP_DB_*` credentials,
`ORIGIN_CERT_PATH`/`ORIGIN_KEY_PATH` and `GAMEMETRIX_IMAGE_PREFIX=ghcr.io/alparslansemiz/gamemetrix`.
Do not set `GAMEMETRIX_TAG` by hand; the deploy script writes it.

## 4. Database: start empty, then restore

```bash
sudo docker compose up -d db
# copy the newest dump onto the VM first (from the off-site copy), then:
sudo docker exec -i gamemetrix-db sh -c \
  'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' \
  < /path/to/gamemetrix-YYYYMMDD-HHMM.dump
sudo docker exec -i gamemetrix-db sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT count(*) FROM games" -c "SELECT * FROM alembic_version"'
```

Then create the application role the backend connects as (the dump was restored by the admin
user; `--no-owner` leaves ownership with it). With the root `.env` exported in a root shell:

```bash
sudo bash -c 'set -a; . ./.env; set +a
  docker exec -i gamemetrix-db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -v admin_user="$POSTGRES_USER" -v app_user="$APP_DB_USER" \
    -v app_password="$APP_DB_PASSWORD" -v database_name="$POSTGRES_DB" \
    < ops/create-app-db-role.sql'
```

No dump at all (worst case): the catalog is rebuilt by the data-fill jobs over days, accounts
and collections are gone. `alembic upgrade head` does not work on an empty database (the
baseline revision creates the current schema, so later revisions collide). Instead create the
schema from the models and stamp it:
`docker compose run --rm --no-deps backend python -c "from app.database import Base, engine; from app import models; Base.metadata.create_all(engine)"`
then `docker compose run --rm --no-deps backend alembic stamp head`.

## 5. Origin TLS (Cloudflare Origin CA)

```bash
sudo mkdir -p /etc/gamemetrix/origin-tls
```

Put the certificate and key at `/etc/gamemetrix/origin-tls/origin.crt` and `origin.key`
(owner `root`, group `101`, modes `0644` and `0640`, so the non-root nginx can read them).
If the old key is gone, issue a new one: Cloudflare dashboard, SSL/TLS, Origin Server, Create
Certificate, hostnames `gamemetrix.me` and `*.gamemetrix.me`. The key is shown once; never put
it in Git or chat. Without these files the deploy script runs the HTTP-only foundation.

## 6. First deployment

```bash
sudo bash ops/deploy-production.sh /home/ubuntu/gamemetrix/Gamemetrix
```

It pulls the CI-built images for the checked-out commit, starts db, backend, frontend and
nginx in order, waits for health and for `/health/ready` (database answers, catalog not
empty), and records `.deployed-sha`. If it says the images are not published, wait for the
`images` workflow of that commit.

## 7. DNS and Cloudflare

- Records for `gamemetrix.me`, `www` and `api` point at the new VM's address, **proxied**
  (orange cloud). An IPv6-only VM needs `AAAA` records.
- SSL/TLS mode **Full (strict)** (origin TLS from step 5 must already answer; check with
  `curl --resolve gamemetrix.me:443:127.0.0.1 https://gamemetrix.me/health` on the VM).
- Purge the Cloudflare cache after DNS changes.

## 8. Firewall

From a second SSH session:

```bash
sudo bash ops/configure-cloudflare-ufw.sh --apply
```

Check afterwards that direct connections to the VM's 80/443 from outside Cloudflare fail and
that the site still works through Cloudflare.

## 9. Cron, logs and notifications

```bash
sudo install -o root -g root -m 644 ops/logrotate-gamemetrix /etc/logrotate.d/gamemetrix
sudo mkdir -p /etc/gamemetrix
# optional but strongly recommended: failures and dead-man pings
sudo install -o root -g root -m 600 /dev/stdin /etc/gamemetrix/notify.env <<'ENV'
NOTIFY_URL=<discord or slack webhook>
NOTIFY_PING_URL=<healthchecks.io ping base, e.g. https://hc-ping.com/<ping-key>>
ENV
sudo crontab -e   # add the lines below
```

```cron
*/5 * * * * /home/ubuntu/gamemetrix/Gamemetrix/ops/auto-deploy.sh >> /var/log/gamemetrix-autodeploy.log 2>&1
* * * * * /home/ubuntu/gamemetrix/Gamemetrix/ops/health-watchdog.sh >> /var/log/gamemetrix-watchdog.log 2>&1
30 3 * * * /home/ubuntu/gamemetrix/Gamemetrix/ops/backup-db.sh >> /var/log/gamemetrix-backup.log 2>&1
0 3 * * * /home/ubuntu/gamemetrix/Gamemetrix/ops/cleanup.sh >> /var/log/gamemetrix-cleanup.log 2>&1
10 4 1-7 * 0 /home/ubuntu/gamemetrix/Gamemetrix/ops/restore-test.sh >> /var/log/gamemetrix-restore-test.log 2>&1
```

Also set `BACKUP_REMOTE` in the backup cron line for the off-site copy. With Healthchecks.io,
create checks with the slugs `watchdog`, `backup` and `restore-test`.

## 10. Verify

- `curl -fsS https://api.gamemetrix.me/health/ready` returns `{"status":"ok",...}`.
- https://gamemetrix.me loads a catalog page and a game page.
- `docker compose ps` shows four healthy containers; `docker stats --no-stream` stays under
  the limits.
- Run `sudo ops/restore-test.sh` once on the new VM after its first nightly backup.

## Restore test

`ops/restore-test.sh` loads the newest dump into a throwaway `postgres:15-alpine` container
(160 MB cap, no published port), checks that `games` has at least `RESTORE_TEST_MIN_GAMES`
rows (default 1000) and that `alembic_version` is present, prints row counts for the main
tables, and deletes the container. A failure sends a message through `ops/notify.sh`.
