# Config
DB_USER="root"
DB_HOST="localhost"
DATABASES="replaygenie"
BACKUP_DIR="/backups/mysql"
LOCAL_RETENTION_DAYS=3
REMOTE_ENABLED=true
REMOTE_PATH="gdrive:mysql-backups"

set -euo pipefail

TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

log()  { echo "$LOG_PREFIX INFO  $*"; }
warn() { echo "$LOG_PREFIX WARN  $*"; }
fail() { echo "$LOG_PREFIX ERROR $*" >&2; exit 1; }

# Validate dependencies

command -v mysqldump &>/dev/null || fail "mysqldump not found. Is MySQL client installed?"
command -v gzip      &>/dev/null || fail "gzip not found."

if [ "$REMOTE_ENABLED" = true ]; then
  command -v rclone &>/dev/null || fail "rclone not found. See https://rclone.org/install/"
fi

# Prepare backup dir
mkdir -p "$BACKUP_DIR"
log "Backup directory: $BACKUP_DIR"

# Build mysqldump credentials
MYSQL_OPTS="-h $DB_HOST -u $DB_USER"
if [ -n "$DB_PASSWORD" ]; then
  MYSQL_OPTS="$MYSQL_OPTS -p$DB_PASSWORD"
fi

# mysql dump
run_dump() {
  local db="$1"
  local filename

  if [ "$db" = "ALL" ]; then
    filename="all-databases_${TIMESTAMP}.sql.gz"
    log "Dumping ALL databases → $filename"
    mysqldump $MYSQL_OPTS \
      --all-databases \
      --single-transaction \
      --routines \
      --triggers \
      --events \
    | gzip > "$BACKUP_DIR/$filename"
  else
    filename="${db}_${TIMESTAMP}.sql.gz"
    log "Dumping database '$db' → $filename"
    mysqldump $MYSQL_OPTS \
      --databases "$db" \
      --single-transaction \
      --routines \
      --triggers \
      --events \
    | gzip > "$BACKUP_DIR/$filename"
  fi

  local size
  size=$(du -sh "$BACKUP_DIR/$filename" | cut -f1)
  log "Saved: $BACKUP_DIR/$filename ($size)"
}

if [ "$DATABASES" = "ALL" ]; then
  run_dump "ALL"
else
  for db in $DATABASES; do
    run_dump "$db"
  done
fi

# Sync to google drive remote storage
if [ "$REMOTE_ENABLED" = true ]; then
  log "Syncing backups to remote: $REMOTE_PATH"
  rclone copy "$BACKUP_DIR" "$REMOTE_PATH" \
    --transfers 4 \
    --no-traverse \
    --log-level INFO
  log "Remote sync complete."
else
  warn "Remote sync is disabled (REMOTE_ENABLED=false). Backups are local only."
fi

# Clean up old local backups
log "Removing local backups older than $LOCAL_RETENTION_DAYS days..."
deleted=$(find "$BACKUP_DIR" -name "*.sql.gz" -mtime +"$LOCAL_RETENTION_DAYS" -print -delete)
if [ -n "$deleted" ]; then
  log "Deleted:$deleted"
else
  log "Nothing to clean up."
fi

log "Backup finished successfully."