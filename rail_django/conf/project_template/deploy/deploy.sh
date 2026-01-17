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

usage() {
  cat <<'EOF'
Usage: deploy.sh [options]

Options:
  --create-superuser   Run Django createsuperuser (interactive).
  --follow-logs        Follow docker logs after deployment.
  --skip-migrate       Skip running migrations after containers start.
  --skip-collectstatic Skip collectstatic after containers start.
  -h, --help           Show this help message.

Environment:
  DEPLOY_DOMAIN        Domain for self-signed certs when none exist.
  DEPLOY_CREATE_SUPERUSER=1
                       Create a superuser non-interactively from .env values.
                       Requires DJANGO_SUPERUSER_USERNAME and DJANGO_SUPERUSER_PASSWORD.
EOF
}

for arg in "$@"; do
  case "$arg" in
    --create-superuser) CREATE_SUPERUSER=1 ;;
    --follow-logs) FOLLOW_LOGS=1 ;;
    --skip-migrate) SKIP_MIGRATE=1 ;;
    --skip-collectstatic) SKIP_COLLECTSTATIC=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $arg" ;;
  esac
done

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
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

is_truthy() {
  case "$(echo "$1" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|y|on) return 0 ;;
    *) return 1 ;;
  esac
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

missing=()
for key in DJANGO_SECRET_KEY DATABASE_URL DJANGO_ALLOWED_HOSTS; do
  if [ -z "$(read_env "$key")" ]; then
    missing+=("$key")
  fi
done

if [ ${#missing[@]} -gt 0 ]; then
  die "Missing required .env values: ${missing[*]}"
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

note "Building and starting containers..."
"${COMPOSE[@]}" -f "$COMPOSE_FILE" up -d --build

note "Waiting for web container..."
attempts=30
until "${COMPOSE[@]}" -f "$COMPOSE_FILE" exec -T web python -c "print('ready')" >/dev/null 2>&1; do
  attempts=$((attempts - 1))
  if [ "$attempts" -le 0 ]; then
    die "Web container did not become ready."
  fi
  sleep 1
done

if [ "$SKIP_MIGRATE" -eq 0 ]; then
  note "Running migrations..."
  "${COMPOSE[@]}" -f "$COMPOSE_FILE" exec -T web python manage.py migrate
fi

if [ "$SKIP_COLLECTSTATIC" -eq 0 ]; then
  note "Collecting static files..."
  "${COMPOSE[@]}" -f "$COMPOSE_FILE" exec -T web python manage.py collectstatic --noinput
fi

if [ "$CREATE_SUPERUSER" -eq 1 ]; then
  note "Creating superuser (interactive)..."
  "${COMPOSE[@]}" -f "$COMPOSE_FILE" exec web python manage.py createsuperuser
elif is_truthy "$(read_env DEPLOY_CREATE_SUPERUSER)"; then
  note "Creating superuser (non-interactive)..."
  su_username="$(read_env DJANGO_SUPERUSER_USERNAME)"
  su_email="$(read_env DJANGO_SUPERUSER_EMAIL)"
  su_password="$(read_env DJANGO_SUPERUSER_PASSWORD)"

  if [ -z "$su_username" ] || [ -z "$su_password" ]; then
    die "DEPLOY_CREATE_SUPERUSER=1 requires DJANGO_SUPERUSER_USERNAME and DJANGO_SUPERUSER_PASSWORD."
  fi

  if [ -n "$su_email" ]; then
    "${COMPOSE[@]}" -f "$COMPOSE_FILE" exec -T web \
      python manage.py createsuperuser --noinput --username "$su_username" --email "$su_email"
  else
    warn "DJANGO_SUPERUSER_EMAIL not set; createsuperuser may fail if email is required."
    "${COMPOSE[@]}" -f "$COMPOSE_FILE" exec -T web \
      python manage.py createsuperuser --noinput --username "$su_username"
  fi
fi

note "Deployment complete."

if [ "$FOLLOW_LOGS" -eq 1 ]; then
  "${COMPOSE[@]}" -f "$COMPOSE_FILE" logs -f
fi
