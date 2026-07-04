"""Database backup with rotation.

Idempotent and safe to re-run (each run writes a new timestamped file):

    python manage.py backup_db                # to BACKUP_DIR (default BASE_DIR/backups)
    python manage.py backup_db --keep 60      # keep the newest 60 backups

SQLite gets a consistent file snapshot via the sqlite backup API; other
engines fall back to a gzipped `dumpdata` JSON (portable across engines).
Run it from cron/systemd-timer on the VPS; sync the backup dir offsite
(e.g. S3-compatible object storage) with a separate rclone/rsync job.
"""

import gzip
import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management import BaseCommand, call_command


class Command(BaseCommand):
    help = 'پشتیبان‌گیری از پایگاه داده با چرخش فایل‌های قدیمی'

    def add_arguments(self, parser):
        parser.add_argument('--dir', default=None, help='Backup directory (default: <BASE_DIR>/backups)')
        parser.add_argument('--keep', type=int, default=30, help='How many newest backups to keep')

    def handle(self, *args, **options):
        backup_dir = Path(options['dir'] or getattr(settings, 'BACKUP_DIR', settings.BASE_DIR / 'backups'))
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')

        engine = settings.DATABASES['default']['ENGINE']
        if engine.endswith('sqlite3'):
            target = backup_dir / f'db-{stamp}.sqlite3'
            source = sqlite3.connect(settings.DATABASES['default']['NAME'])
            try:
                dest = sqlite3.connect(target)
                with dest:
                    source.backup(dest)  # consistent even under concurrent writes
                dest.close()
            finally:
                source.close()
        else:
            target = backup_dir / f'db-{stamp}.json.gz'
            with gzip.open(target, 'wt', encoding='utf-8') as fh:
                call_command('dumpdata', '--natural-foreign', '--natural-primary',
                             exclude=['contenttypes', 'auth.permission', 'sessions', 'admin.logentry'],
                             stdout=fh)

        self.stdout.write(self.style.SUCCESS(f'backup written: {target}'))

        # Rotation: keep the newest N of each kind
        backups = sorted(backup_dir.glob('db-*'), key=lambda p: p.name, reverse=True)
        for old in backups[options['keep']:]:
            old.unlink()
            self.stdout.write(f'rotated out: {old.name}')
