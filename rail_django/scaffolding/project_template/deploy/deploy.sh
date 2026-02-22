#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

note() {
  echo "[deploy] $*"
}

warn() {
  echo "[deploy] Warning: $*" >&2
}

die() {
  echo "[deploy] Error: $*" >&2
  exit 1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker/docker-compose.yml"
ENV_FILE="$PROJECT_ROOT/.env"
ENV_EXAMPLE="$PROJECT_ROOT/.env.example"
CERTS_DIR="$SCRIPT_DIR/nginx/certs"
CERT_CRT="$CERTS_DIR/server.crt"
CERT_KEY="$CERTS_DIR/server.key"

CREATE_SUPERUSER=0
FOLLOW_LOGS=0
SKIP_MIGRATE=0
SKIP_COLLECTSTATIC=0
REFRESH_DEPS=0

usage() {
  cat <<'EOF'
Usage: deploy.sh [options]

Options:
  --create-superuser   Run Django createsuperuser (interactive).
  --follow-logs        Follow docker logs after deployment.
  --refresh-deps       Rebuild dependency layer (useful for git-based deps).
  --skip-migrate       Skip running migrations after containers start.
  --skip-collectstatic Skip collectstatic after containers start.
  -h, --help           Show this help message.

Environment:
  DEPLOY_DOMAIN        Domain for self-signed certs when none exist.
  DEPLOY_CREATE_SUPERUSER=1
                       Create a superuser non-interactively from .env values.
                       Requires DJANGO_SUPERUSER_USERNAME and DJANGO_SUPERUSER_PASSWORD.
  DEPLOY_REFRESH_DEPS=1
                       Force dependency layer rebuild on deploy.
EOF
}

for arg in "$@"; do
  case "$arg" in
    --create-superuser) CREATE_SUPERUSER=1 ;;
    --follow-logs) FOLLOW_LOGS=1 ;;
    --refresh-deps) REFRESH_DEPS=1 ;;
    --skip-migrate) SKIP_MIGRATE=1 ;;
    --skip-collectstatic) SKIP_COLLECTSTATIC=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $arg" ;;
  esac
done

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

ensure_tls_not_tracked() {
  if ! command -v git >/dev/null 2>&1; then
    return 0
  fi
  if ! git -C "$PROJECT_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    return 0
  fi

  local rel_cert="${CERT_CRT#$PROJECT_ROOT/}"
  local rel_key="${CERT_KEY#$PROJECT_ROOT/}"

  if git -C "$PROJECT_ROOT" ls-files --error-unmatch -- "$rel_cert" >/dev/null 2>&1 \
    || git -C "$PROJECT_ROOT" ls-files --error-unmatch -- "$rel_key" >/dev/null 2>&1; then
    die "TLS cert/key must not be tracked by git. Remove deploy/nginx/certs/server.{crt,key} from version control."
  fi
}

ensure_dir() {
  local path="$1"
  if [ -d "$path" ]; then
    return 0
  fi
  if [ -e "$path" ]; then
    die "Path exists but is not a directory: $path"
  fi
  mkdir -p "$path"
}

ensure_runtime_mount_writable() {
  local check_cmd='set -e; for dir in /home/app/web/mediafiles /home/app/web/logs /home/app/web/cache; do mkdir -p "$dir"; probe="$dir/.rail_write_probe"; : > "$probe"; rm -f "$probe"; done'
  local repair_cmd='set -e; APP_UID=$(id -u app 2>/dev/null || echo 1000); APP_GID=$(id -g app 2>/dev/null || echo 1000); for dir in /home/app/web/mediafiles /home/app/web/logs /home/app/web/cache; do mkdir -p "$dir"; chown -R "$APP_UID:$APP_GID" "$dir" || true; chmod -R u+rwX,g+rwX "$dir" || true; done'

  if "${COMPOSE[@]}" -f "$COMPOSE_FILE" run --rm --entrypoint sh web -c "$check_cmd" >/dev/null 2>&1; then
    return 0
  fi

  warn "Runtime storage is not writable by the container user; attempting permission repair."
  "${COMPOSE[@]}" -f "$COMPOSE_FILE" run --rm --entrypoint sh --user root web -c "$repair_cmd" >/dev/null 2>&1 || true

  if ! "${COMPOSE[@]}" -f "$COMPOSE_FILE" run --rm --entrypoint sh web -c "$check_cmd" >/dev/null 2>&1; then
    die "Runtime storage is not writable by the app user. Verify MEDIA_PATH/LOG_PATH/CACHE_PATH permissions on the host."
  fi
}

is_truthy() {
  case "$(echo "$1" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|y|on) return 0 ;;
    *) return 1 ;;
  esac
}

is_insecure_secret() {
  local value
  value="$(echo "$1" | tr '[:upper:]' '[:lower:]' | xargs)"
  case "$value" in
    ""|change_me|changeme|replace_me|replace-with-secure-value|default|password|secret)
      return 0
      ;;
    change_me_in_production_with_a_long_random_string|replace_with_long_random_secret_key|replace_with_strong_password)
      return 0
      ;;
  esac
  if [[ "$value" == *"change_me"* ]] || [[ "$value" == *"replace_with_"* ]]; then
    return 0
  fi
  return 1
}

read_env() {
  local key="$1"
  local line
  line="$(grep -E "^[[:space:]]*${key}=" "$ENV_FILE" | tail -n 1 || true)"
  if [ -z "$line" ]; then
    echo ""
    return 0
  fi
  local value="${line#*=}"
  value="${value%$'\r'}"
  echo "$value"
}

require_cmd docker

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  die "Docker Compose not found. Install docker-compose or Docker with compose plugin."
fi

if [ ! -f "$COMPOSE_FILE" ]; then
  die "Compose file not found: $COMPOSE_FILE"
fi

if [ ! -f "$ENV_FILE" ]; then
  if [ -f "$ENV_EXAMPLE" ]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    die "Created .env from .env.example. Edit .env and re-run deploy.sh."
  fi
  die ".env not found and .env.example missing."
fi

ensure_tls_not_tracked

missing=()
for key in DJANGO_SECRET_KEY DATABASE_URL DJANGO_ALLOWED_HOSTS; do
  if [ -z "$(read_env "$key")" ]; then
    missing+=("$key")
  fi
done

if [ ${#missing[@]} -gt 0 ]; then
  die "Missing required .env values: ${missing[*]}"
fi

secret_key="$(read_env DJANGO_SECRET_KEY)"
if is_insecure_secret "$secret_key"; then
  die "DJANGO_SECRET_KEY appears to use a placeholder or weak default value."
fi

if [ ! -f "$CERT_CRT" ] || [ ! -f "$CERT_KEY" ]; then
  require_cmd openssl
  ensure_dir "$CERTS_DIR"

  allowed_hosts="$(read_env DJANGO_ALLOWED_HOSTS)"
  allowed_hosts="${allowed_hosts// /}"
  domain="${DEPLOY_DOMAIN:-${allowed_hosts%%,*}}"
  if [ -z "$domain" ]; then
    domain="localhost"
  fi

  note "Generating self-signed TLS certs for ${domain}..."
  if ! openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$CERT_KEY" \
    -out "$CERT_CRT" \
    -subj "/CN=${domain}" \
    -addext "subjectAltName=DNS:${domain}" >/dev/null 2>&1; then
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
      -keyout "$CERT_KEY" \
      -out "$CERT_CRT" \
      -subj "/CN=${domain}" >/dev/null
  fi
  chmod 600 "$CERT_KEY"
fi

media_path="$(read_env MEDIA_PATH)"
if [ -z "$media_path" ]; then
  media_path="../../media"
fi
if [[ "$media_path" = /* ]]; then
  ensure_dir "$media_path"
else
  ensure_dir "$SCRIPT_DIR/docker/$media_path"
fi

backup_path="$(read_env BACKUP_PATH)"
if [ -z "$backup_path" ]; then
  backup_path="../../backups"
fi
if [[ "$backup_path" = /* ]]; then
  ensure_dir "$backup_path"
else
  ensure_dir "$SCRIPT_DIR/docker/$backup_path"
fi

log_path="$(read_env LOG_PATH)"
if [ -z "$log_path" ]; then
  log_path="../../logs"
fi
if [[ "$log_path" = /* ]]; then
  ensure_dir "$log_path"
else
  ensure_dir "$SCRIPT_DIR/docker/$log_path"
fi

cache_path="$(read_env CACHE_PATH)"
if [ -z "$cache_path" ]; then
  cache_path="../../cache"
fi
if [[ "$cache_path" = /* ]]; then
  ensure_dir "$cache_path"
else
  ensure_dir "$SCRIPT_DIR/docker/$cache_path"
fi

note "Building web image..."
build_args=()
build_args+=(--build-arg "RAIL_GIT_CACHE_BUST=$(date +%s)")
if [ "$REFRESH_DEPS" -eq 1 ] || is_truthy "$(read_env DEPLOY_REFRESH_DEPS)"; then
  build_args+=(--build-arg "RAIL_DEP_CACHE_BUST=$(date +%s)")
fi

"${COMPOSE[@]}" -f "$COMPOSE_FILE" build "${build_args[@]}" web

note "Validating runtime storage permissions..."
ensure_runtime_mount_writable

if [ "$SKIP_MIGRATE" -eq 0 ]; then
  note "Running migrations..."
  "${COMPOSE[@]}" -f "$COMPOSE_FILE" run --rm --entrypoint python web manage.py migrate
fi

if [ "$SKIP_COLLECTSTATIC" -eq 0 ]; then
  note "Collecting static files..."
  "${COMPOSE[@]}" -f "$COMPOSE_FILE" run --rm --entrypoint python web manage.py collectstatic --noinput
fi

note "Starting containers..."
"${COMPOSE[@]}" -f "$COMPOSE_FILE" up -d

note "Waiting for web readiness endpoint..."
attempts=30
readiness_cmd="import sys, urllib.request; resp = urllib.request.urlopen('http://127.0.0.1:8000/health/ready/', timeout=3); sys.exit(0 if 200 <= getattr(resp, 'status', 200) < 400 else 1)"
until "${COMPOSE[@]}" -f "$COMPOSE_FILE" exec -T web python -c "$readiness_cmd" >/dev/null 2>&1; do
  attempts=$((attempts - 1))
  if [ "$attempts" -le 0 ]; then
    die "Web readiness probe did not pass."
  fi
  sleep 1
done

if [ "$CREATE_SUPERUSER" -eq 1 ]; then
  note "Creating superuser (interactive)..."
  "${COMPOSE[@]}" -f "$COMPOSE_FILE" exec web python manage.py createsuperuser
elif is_truthy "$(read_env DEPLOY_CREATE_SUPERUSER)"; then
  note "Ensuring superuser exists (non-interactive)..."
  su_username="$(read_env DJANGO_SUPERUSER_USERNAME)"
  su_email="$(read_env DJANGO_SUPERUSER_EMAIL)"
  su_password="$(read_env DJANGO_SUPERUSER_PASSWORD)"

  if [ -z "$su_username" ] || [ -z "$su_password" ]; then
    die "DEPLOY_CREATE_SUPERUSER=1 requires DJANGO_SUPERUSER_USERNAME and DJANGO_SUPERUSER_PASSWORD."
  fi
  if is_insecure_secret "$su_password"; then
    die "DJANGO_SUPERUSER_PASSWORD appears to use a placeholder or weak default value."
  fi

  "${COMPOSE[@]}" -f "$COMPOSE_FILE" exec -T web python manage.py shell <<'PY'
import os

from django.contrib.auth import get_user_model

username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "").strip()
email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "").strip()
password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")

if not username or not password:
    raise SystemExit(
        "DJANGO_SUPERUSER_USERNAME and DJANGO_SUPERUSER_PASSWORD are required."
    )

User = get_user_model()
lookup = {User.USERNAME_FIELD: username}
defaults = {
    "is_staff": True,
    "is_superuser": True,
    "is_active": True,
}
if hasattr(User, "email") and User.USERNAME_FIELD != "email" and email:
    defaults["email"] = email

user, created = User.objects.get_or_create(defaults=defaults, **lookup)
changed = created

if not getattr(user, "is_staff", False):
    user.is_staff = True
    changed = True
if not getattr(user, "is_superuser", False):
    user.is_superuser = True
    changed = True
if not getattr(user, "is_active", True):
    user.is_active = True
    changed = True

if hasattr(user, "email") and email and getattr(user, "email", "") != email:
    user.email = email
    changed = True

if not user.check_password(password):
    user.set_password(password)
    changed = True

if changed:
    user.save()

if created:
    print("Superuser created.")
elif changed:
    print("Superuser updated.")
else:
    print("Superuser already up to date.")
PY
fi

note "Deployment complete."

if [ "$FOLLOW_LOGS" -eq 1 ]; then
  "${COMPOSE[@]}" -f "$COMPOSE_FILE" logs -f
fi
