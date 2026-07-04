# Shensazeh — VPS Deploy Guide

Target: Ubuntu 22.04+ VPS. App runs as **gunicorn** behind **nginx**, using **SQLite**.
Estimated time: ~30–45 min.

Throughout, replace `YOUR_SERVER_IP` with your server's public IP. The domain is `shensazeh.ir`.

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
mkdir -p /var/log/shensazeh
```

## 2. Get the code onto the server
**Option A — git (recommended):**
```bash
cd /var/www && git clone https://github.com/ArgonStark/shensazeh.git shensazeh
```
> Note: `.gitignore` excludes `db.sqlite3` and `media/`, so a fresh clone starts with an
> empty database. Run migrations + `createsuperuser` (steps 5) for a clean start, or use
> Option B to bring existing data/images across.

**Option B — copy from your machine** (run on your LOCAL machine):
```bash
# include db.sqlite3 and media so your data/images come along
rsync -avz --exclude venv --exclude '__pycache__' --exclude staticfiles \
    /Users/argon/Projects/sazandeh/ root@YOUR_SERVER_IP:/var/www/shensazeh/
```

## 3. Python environment
```bash
cd /var/www/shensazeh
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Environment file
```bash
cp deploy/.env.production.example .env
nano .env        # ALLOWED_HOSTS and SITE_URL are pre-filled for shensazeh.ir; set a real SECRET_KEY
```

## 5. Django prep
```bash
source venv/bin/activate
python manage.py migrate
python manage.py collectstatic --noinput
# create an admin login for the panel (login is email + password):
python manage.py createsuperuser
```

## 6. Permissions
```bash
chown -R www-data:www-data /var/www/shensazeh /var/log/shensazeh
```

## 7. gunicorn service
```bash
cp /var/www/shensazeh/deploy/shensazeh.service /etc/systemd/system/shensazeh.service
systemctl daemon-reload
systemctl enable --now shensazeh
systemctl status shensazeh        # should be "active (running)"
```
The service uses `RuntimeDirectory=shensazeh`, so systemd creates `/run/shensazeh/`
(owned by `www-data`) and gunicorn binds `unix:/run/shensazeh/shensazeh.sock` there.
Binding directly in `/run` fails with `[Errno 13] Permission denied` — don't do that.

## 8. nginx
```bash
cp /var/www/shensazeh/deploy/nginx_shensazeh.conf /etc/nginx/sites-available/shensazeh
# (already set to shensazeh.ir / www.shensazeh.ir — edit only if testing by raw IP)
ln -sf /etc/nginx/sites-available/shensazeh /etc/nginx/sites-enabled/shensazeh
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx
```

> DNS: point an **A record** for `shensazeh.ir` (and `www`) at the server's public IP before this resolves publicly.

## 9. Open the firewall (if ufw is on)
```bash
ufw allow 'Nginx Full' && ufw allow OpenSSH
```

## 10. Verify
```bash
ls -l /run/shensazeh/                             # shensazeh.sock should exist (owned by www-data)
curl -I -H "Host: shensazeh.ir" http://127.0.0.1/ # should return 200 (or 301/302)
```
A plain `curl -I http://127.0.0.1/` returns **400** by design — Django rejects any Host
not in `ALLOWED_HOSTS`. Test with the `-H "Host: shensazeh.ir"` header as above.

Then open `http://shensazeh.ir/` — the landing page should load with full styling.

---

## HTTPS (do once the domain points at the server)
```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d shensazeh.ir -d www.shensazeh.ir
```
Then in `.env` set `SITE_URL=https://shensazeh.ir` and `SECURE_SSL=True`, and `systemctl restart shensazeh`.

---

## Nightly database backup
```bash
mkdir -p /var/backups/shensazeh && chown www-data:www-data /var/backups/shensazeh
cp /var/www/shensazeh/deploy/shensazeh-backup.service /etc/systemd/system/
cp /var/www/shensazeh/deploy/shensazeh-backup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now shensazeh-backup.timer
systemctl list-timers | grep shensazeh    # verify it's scheduled
```
Backups rotate automatically (newest 30 kept). Copy `/var/backups/shensazeh/`
offsite (rclone to S3-compatible storage, or a nightly rsync to another host) —
a backup on the same disk is not a real backup.

---

## Updating after a code change
```bash
cd /var/www/shensazeh && git pull          # or rsync again
source venv/bin/activate
pip install -r requirements.txt            # if deps changed
python manage.py migrate
python manage.py collectstatic --noinput
systemctl restart shensazeh
```

---

## Troubleshooting
- **502 Bad Gateway** → gunicorn isn't running or the socket is missing: `systemctl status shensazeh`, `journalctl -xeu shensazeh.service -n 40`, and confirm `/run/shensazeh/shensazeh.sock` exists.
- **`[Errno 13] Permission denied` on the socket** → the service must have `RuntimeDirectory=shensazeh` and bind under `/run/shensazeh/`, not directly in `/run`.
- **400 Bad Request** → expected for a request whose Host isn't in `ALLOWED_HOSTS`; use `-H "Host: shensazeh.ir"`. If it happens in the browser on the real domain, add the domain to `ALLOWED_HOSTS` in `.env` and `systemctl restart shensazeh`.
- **Unstyled page / CSS 404** → run `collectstatic`; check nginx `/static/` alias path and that `staticfiles/` exists.
- **DisallowedHost** → add the domain/IP to `ALLOWED_HOSTS` in `.env`, then `systemctl restart shensazeh`.
- **Images (media) 404** → confirm `media/` was copied and the nginx `/media/` alias is correct.
- **Logs** → `/var/log/shensazeh/error.log` (app) and `/var/log/nginx/error.log` (proxy).

> Note: CDN assets (Bootstrap, Tailwind, Vazirmatn, Quill, etc.) load from jsDelivr. If users access from inside Iran without a VPN and the CDN is slow/blocked, self-host those files — see ROADMAP §15.
