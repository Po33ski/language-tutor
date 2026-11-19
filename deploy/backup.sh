#!/usr/bin/env bash
# Back up the SQLite databases to $BACKUP_DIR (default ~/backups), keeping $KEEP_DAYS days.
# Uses SQLite's online backup API, so it is safe while the backend is running.
# Daily at 03:00 via cron (crontab -e):
#   0 3 * * * /home/ubuntu/language-tutor/deploy/backup.sh >> /home/ubuntu/backups/backup.log 2>&1
set -euo pipefail

main() {
    cd "$(dirname "$0")"
    local backup_dir="${BACKUP_DIR:-$HOME/backups}"
    local keep_days="${KEEP_DAYS:-14}"
    local name
    name="tutor-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$backup_dir"

    docker compose exec -T backend python - "$name" <<'PY'
import sqlite3
import sys
from pathlib import Path

target = Path("/data/backups") / sys.argv[1]
target.mkdir(parents=True)
for db in ("checkpoints.db", "memory.db", "users.db"):
    source = sqlite3.connect(f"/data/{db}")
    copy = sqlite3.connect(target / db)
    source.backup(copy)
    copy.close()
    source.close()
PY
    docker compose cp "backend:/data/backups/$name" "$backup_dir/$name"
    docker compose exec -T backend rm -rf "/data/backups/$name"
    tar -czf "$backup_dir/$name.tar.gz" -C "$backup_dir" "$name"
    rm -rf "${backup_dir:?}/$name"
    find "$backup_dir" -name 'tutor-*.tar.gz' -mtime "+$keep_days" -delete
    echo "Saved $backup_dir/$name.tar.gz"
}

main "$@"
