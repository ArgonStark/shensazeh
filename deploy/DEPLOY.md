# Sazandeh — VPS Deploy Guide (fast path for the deadline)

Target: Ubuntu 22.04 VPS. App runs as **gunicorn** behind **nginx**, using **SQLite**.
Estimated time: ~30–45 min.

Throughout, replace `YOUR_DOMAIN_OR_IP` with your domain (e.g. `sazandeh.ir`) or the server's public IP.

---

## 0. Connect to the server
```bash
ssh root@YOUR_SERVER_IP
```

## 1. System packages
```bash
apt update && apt upgrade -y
apt install -y python3-venv python3-pip nginx git \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev libjpeg-dev   # last line: for WeasyPrint/Pillow
mkdir -p /var/log/sazandeh
```

## 2. Get the code onto the server
**Option A — git (recommended):** push your project to a git remote, then:
```bash
cd /var/www && git clone YOUR_REPO_URL sazandeh
```
**Option B — copy from your machine** (run on your LOCAL machine):
```bash
# exclude venv/cache; include db.sqlite3 and media so your data/images come along
rsync -avz --exclude venv --exclude '__pycache__' --exclude staticfiles \
    /Users/argon/Projects/sazandeh/ root@YOUR_SERVER_IP:/var/www/sazandeh/
```

## 3. Python environment
```bash
cd /var/www/sazandeh
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Environment file
```bash
cp deploy/.env.production.example .env
nano .env        # set ALLOWED_HOSTS and SITE_URL to YOUR_DOMAIN_OR_IP (SECRET_KEY is pre-filled)
```

## 5. Django prep
```bash
source venv/bin/activate
python manage.py migrate
python manage.py collectstatic --noinput
# create an admin login if you need the panel (login field is the mobile number):
python manage.py createsuperuser
```

## 6. Permissions
```bash
chown -R www-data:www-data /var/www/sazandeh /var/log/sazandeh
```

## 7. gunicorn service
```bash
cp /var/www/sazandeh/deploy/gunicorn.service /etc/systemd/system/sazandeh.service
systemctl daemon-reload
systemctl enable --now sazandeh
systemctl status sazandeh        # should be "active (running)"
```

## 8. nginx
```bash
cp /var/www/sazandeh/deploy/nginx_sazandeh.conf /etc/nginx/sites-available/sazandeh
# (already set to shensazeh.ir / www.shensazeh.ir — edit only if testing by raw IP)
ln -sf /etc/nginx/sites-available/sazandeh /etc/nginx/sites-enabled/sazandeh
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx
```

> DNS: point an **A record** for `shensazeh.ir` (and `www`) at the server's public IP before this resolves publicly.

## 9. Open the firewall (if ufw is on)
```bash
ufw allow 'Nginx Full' && ufw allow OpenSSH
```

## 10. Visit it 🎉
Open `http://YOUR_DOMAIN_OR_IP/` — the landing page should load with full styling.

---

## HTTPS (optional, do if you have a domain pointed at the server)
```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d shensazeh.ir -d www.shensazeh.ir
```
Then in `.env` set `SITE_URL=https://shensazeh.ir` and `SECURE_SSL=True`, and `systemctl restart sazandeh`.

---

## Nightly database backup
```bash
mkdir -p /var/backups/sazandeh && chown www-data:www-data /var/backups/sazandeh
cp /var/www/sazandeh/deploy/sazandeh-backup.service /etc/systemd/system/
cp /var/www/sazandeh/deploy/sazandeh-backup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sazandeh-backup.timer
systemctl list-timers | grep sazandeh    # verify it's scheduled
```
Backups rotate automatically (newest 30 kept). Copy `/var/backups/sazandeh/`
offsite (rclone to S3-compatible storage, or a nightly rsync to another host) —
a backup on the same disk is not a real backup.

---

## Updating after a code change
```bash
cd /var/www/sazandeh && git pull          # or rsync again
source venv/bin/activate
pip install -r requirements.txt           # if deps changed
python manage.py migrate
python manage.py collectstatic --noinput
systemctl restart sazandeh
```

---

## Troubleshooting
- **502 Bad Gateway** → gunicorn isn't running: `systemctl status sazandeh`, `journalctl -u sazandeh -n 50`.
- **Unstyled page / CSS 404** → run `collectstatic`; check nginx `/static/` alias path and that `staticfiles/` exists.
- **DisallowedHost** → add the domain/IP to `ALLOWED_HOSTS` in `.env`, then `systemctl restart sazandeh`.
- **Images (media) 404** → confirm `media/` was copied and the nginx `/media/` alias is correct.
- **Logs** → `/var/log/sazandeh/error.log` (app) and `/var/log/nginx/error.log` (proxy).

> Note: CDN assets (Bootstrap, Tailwind, Vazirmatn, Quill, etc.) load from jsDelivr. If judges access from inside Iran without a VPN and the CDN is slow/blocked, self-host those files. Not required for tomorrow, but keep it in mind — see ROADMAP §15.
