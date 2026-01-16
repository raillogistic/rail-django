# Déploiement Production

## Vue d'Ensemble

Ce guide couvre le déploiement d'une application Rail Django en production, incluant la configuration Docker, la checklist de sécurité et le guide de déploiement manuel.

---

## Table des Matières

1. [Configuration Docker](#configuration-docker)
2. [Variables d'Environnement](#variables-denvironnement)
3. [Checklist de Production](#checklist-de-production)
4. [Déploiement Manuel](#déploiement-manuel)
5. [HTTPS et Certificats](#https-et-certificats)
6. [Maintenance](#maintenance)
7. [Dépannage](#dépannage)

---

## Configuration Docker

### Structure des Fichiers

```
project/
├── Dockerfile
├── deploy/
│   ├── docker/
│   │   └── docker-compose.yml
│   └── nginx/
│       ├── default.conf
│       └── certs/
│           ├── server.crt
│           └── server.key
└── .env
```

### Dockerfile Multi-Stage

Le Dockerfile inclus utilise un build multi-stage :

```dockerfile
# Stage 1 : Builder
FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements/ requirements/
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements/prod.txt

# Stage 2 : Final
FROM python:3.11-slim

WORKDIR /app

# Copier les wheels et installer
COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache /wheels/*

# Copier le code
COPY . .

# Collectstatic
RUN python manage.py collectstatic --no-input

# Utilisateur non-root
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "root.wsgi:application"]
```

### Docker Compose

```yaml
# deploy/docker/docker-compose.yml
version: "3.8"

services:
  web:
    build:
      context: ../..
      dockerfile: Dockerfile
    environment:
      - DJANGO_SETTINGS_MODULE=root.settings.production
    env_file:
      - ../../.env
    volumes:
      - static_volume:/app/staticfiles
      - media_volume:/app/media
    networks:
      - app-network
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ../nginx/default.conf:/etc/nginx/conf.d/default.conf:ro
      - ../nginx/certs:/etc/nginx/certs:ro
      - static_volume:/app/staticfiles:ro
      - media_volume:/app/media:ro
    depends_on:
      - web
    networks:
      - app-network
    restart: unless-stopped

  backup:
    image: postgres:15-alpine
    volumes:
      - ../../backups:/backups
    env_file:
      - ../../.env
    entrypoint: /bin/sh -c "while true; do pg_dump $$DATABASE_URL > /backups/backup_$$(date +%Y%m%d_%H%M%S).sql; sleep 86400; done"
    networks:
      - app-network
    restart: unless-stopped

volumes:
  static_volume:
  media_volume:

networks:
  app-network:
    driver: bridge
```

---

## Variables d'Environnement

### Fichier .env.example

```bash
# ─── Django ───
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=votre_cle_secrete_tres_longue_et_aleatoire
DJANGO_ALLOWED_HOSTS=example.com,www.example.com
DJANGO_SETTINGS_MODULE=root.settings.production

# ─── Base de Données ───
DATABASE_URL=postgres://user:password@db-host:5432/dbname

# ─── Cache ───
REDIS_URL=redis://redis-host:6379/0
CACHE_PATH=/app/cache

# ─── JWT ───
JWT_SECRET_KEY=${DJANGO_SECRET_KEY}
JWT_ACCESS_TOKEN_LIFETIME=30  # minutes
JWT_REFRESH_TOKEN_LIFETIME=7  # jours

# ─── Auth Cookies (optionnel) ───
JWT_ALLOW_COOKIE_AUTH=False
JWT_ENFORCE_CSRF=True

# ─── Performance ───
GRAPHQL_PERFORMANCE_ENABLED=True
GRAPHQL_PERFORMANCE_HEADERS=False

# ─── Export ───
EXPORT_MAX_ROWS=10000
EXPORT_STREAM_CSV=True

# ─── Email ───
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=noreply@example.com
EMAIL_HOST_PASSWORD=email_password
EMAIL_USE_TLS=True

# ─── Sentry (optionnel) ───
SENTRY_DSN=https://xxx@sentry.io/yyy
```

### Variables Critiques

| Variable               | Importance  | Description                      |
| ---------------------- | ----------- | -------------------------------- |
| `DJANGO_SECRET_KEY`    | 🔴 Critique | Clé cryptographique (> 50 chars) |
| `DJANGO_DEBUG`         | 🔴 Critique | **DOIT** être `False`            |
| `DATABASE_URL`         | 🔴 Critique | Connexion PostgreSQL             |
| `DJANGO_ALLOWED_HOSTS` | 🔴 Critique | Domaines autorisés               |

---

## Checklist de Production

### Sécurité

- [ ] `DJANGO_DEBUG=False`
- [ ] `DJANGO_SECRET_KEY` unique et aléatoire
- [ ] `DJANGO_ALLOWED_HOSTS` configuré
- [ ] HTTPS activé avec certificats valides
- [ ] CORS configuré (`allowed_origins`)
- [ ] CSRF protection activée
- [ ] Rate limiting activé
- [ ] Introspection GraphQL désactivée :
  ```python
  "enable_introspection": False,
  "enable_graphiql": False,
  ```

### Base de Données

- [ ] Utilisateur DB avec privilèges minimaux
- [ ] Connexion SSL si DB distante
- [ ] Backups automatiques configurés
- [ ] Migrations appliquées

### Fichiers

- [ ] `collectstatic` exécuté
- [ ] Nginx sert les fichiers statiques
- [ ] Permissions correctes sur les dossiers

### Monitoring

- [ ] Sentry ou équivalent configuré
- [ ] Health checks actifs
- [ ] Logs centralisés
- [ ] Alertes configurées

### MFA

- [ ] MFA obligatoire pour staff
- [ ] MFA obligatoire pour superusers

---

## Déploiement Manuel

### Prérequis

1. **Docker & Docker Compose** installés
2. **Base de données** PostgreSQL accessible
3. **Domaine/DNS** configuré

### Étapes

#### 1. Configuration Environnement

```bash
cp .env.example .env
nano .env  # Éditer les valeurs
```

#### 2. Build et Démarrage

```bash
docker-compose -f deploy/docker/docker-compose.yml up -d --build
```

#### 3. Migrations

```bash
docker-compose -f deploy/docker/docker-compose.yml exec web python manage.py migrate
```

#### 4. Collectstatic

```bash
docker-compose -f deploy/docker/docker-compose.yml exec web python manage.py collectstatic --no-input
```

#### 5. Superuser

```bash
docker-compose -f deploy/docker/docker-compose.yml exec web python manage.py createsuperuser
```

### Vérification

```bash
# Logs
docker-compose -f deploy/docker/docker-compose.yml logs -f

# Health check
curl -s http://localhost/health/ping/
```

---

## HTTPS et Certificats

### Certificat Officiel (Recommandé)

Demandez à votre équipe IT un certificat pour votre domaine :

```
deploy/nginx/certs/server.crt
deploy/nginx/certs/server.key
```

### Certificat Auto-Signé (Test)

```bash
mkdir -p deploy/nginx/certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout deploy/nginx/certs/server.key \
  -out deploy/nginx/certs/server.crt \
  -subj "/CN=app.example.com"
```

### Configuration Nginx

```nginx
# deploy/nginx/default.conf
server {
    listen 80;
    server_name _;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name app.example.com;

    ssl_certificate /etc/nginx/certs/server.crt;
    ssl_certificate_key /etc/nginx/certs/server.key;
    ssl_protocols TLSv1.2 TLSv1.3;

    location /static/ {
        alias /app/staticfiles/;
    }

    location /media/ {
        alias /app/media/;
    }

    location / {
        proxy_pass http://web:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket pour subscriptions
    location /graphql/ {
        proxy_pass http://web:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }
}
```

---

## Maintenance

### Logs

```bash
# Tous les services
docker-compose -f deploy/docker/docker-compose.yml logs -f

# Service spécifique
docker-compose -f deploy/docker/docker-compose.yml logs -f web
```

### Arrêt

```bash
docker-compose -f deploy/docker/docker-compose.yml down
```

### Mise à Jour

```bash
# Pull du code
git pull origin main

# Rebuild et redémarrage
docker-compose -f deploy/docker/docker-compose.yml up -d --build

# Migrations
docker-compose -f deploy/docker/docker-compose.yml exec web python manage.py migrate
```

### Backups

Les backups sont automatiques (tous les 24h) dans `./backups/`.

Restauration :

```bash
psql $DATABASE_URL < backups/backup_20260116_120000.sql
```

### Nettoyage

```bash
# Supprimer les anciennes images
docker image prune -a

# Supprimer les volumes orphelins
docker volume prune
```

---

## Dépannage

### Container ne démarre pas

```bash
# Voir les logs
docker-compose -f deploy/docker/docker-compose.yml logs web

# Vérifier le status
docker-compose -f deploy/docker/docker-compose.yml ps
```

### Erreur 502 Bad Gateway

**Causes possibles :**

- Le service web n'est pas démarré
- Erreur dans l'application Python

**Solution :**

```bash
docker-compose -f deploy/docker/docker-compose.yml restart web
docker-compose -f deploy/docker/docker-compose.yml logs -f web
```

### Erreur de connexion DB

**Causes possibles :**

- `DATABASE_URL` incorrecte
- DB non accessible depuis le container

**Solution :**

```bash
# Test de connexion
docker-compose -f deploy/docker/docker-compose.yml exec web python manage.py dbshell
```

### Fichiers statiques 404

**Causes possibles :**

- `collectstatic` non exécuté
- Volume non monté correctement

**Solution :**

```bash
docker-compose -f deploy/docker/docker-compose.yml exec web python manage.py collectstatic --no-input
```

### Performances dégradées

**Vérifications :**

1. Activer les logs de performance :
   ```python
   GRAPHQL_PERFORMANCE_ENABLED=True
   ```
2. Vérifier les requêtes lentes :
   ```bash
   docker-compose -f deploy/docker/docker-compose.yml logs web | grep "SLOW"
   ```
3. Vérifier l'utilisation mémoire :
   ```bash
   docker stats
   ```

---

## Sécurité Réseau

### Firewall (UFW)

```bash
# Autoriser uniquement le trafic interne
ufw allow from 10.0.0.0/8 to any port 443
ufw allow ssh
ufw enable
```

### Headers de Sécurité

Ajoutez dans Nginx :

```nginx
add_header X-Frame-Options "DENY" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Content-Security-Policy "default-src 'self'" always;
```

---

## Voir Aussi

- [Configuration](../graphql/configuration.md) - Paramètres de production
- [Health Monitoring](../extensions/health.md) - Vérifications de santé
- [Sécurité](../security/authentication.md) - Authentification et sécurité
