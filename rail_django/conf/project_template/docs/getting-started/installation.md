# Installation

## Prérequis

- **Python** 3.11 ou supérieur
- **pip** (Python Package Installer)
- **PostgreSQL** (recommandé pour la production)
- **Redis** (optionnel, pour le cache et rate limiting)
- **Docker & Docker Compose** (optionnel, pour le développement containerisé)

---

## Installation du Package

### Depuis PyPI

```bash
pip install rail-django
```

### Depuis GitHub

```bash
pip install git+https://github.com/raillogistic/rail-django.git
```

### Installation en Mode Développement

Pour contribuer au framework :

```bash
git clone https://github.com/raillogistic/rail-django.git
cd rail-django
pip install -e .
```

---

## Création d'un Nouveau Projet

### Utiliser rail-admin

Le CLI `rail-admin` crée automatiquement la structure de projet recommandée :

```bash
rail-admin startproject mon_projet
cd mon_projet
```

### Structure Créée

```
mon_projet/
├── manage.py           # Point d'entrée Django
├── root/               # Configuration principale
│   ├── __init__.py
│   ├── settings/       # Paramètres (base, dev, prod)
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── dev.py
│   │   └── production.py
│   ├── urls.py         # Routage global
│   ├── wsgi.py         # WSGI (production)
│   ├── asgi.py         # ASGI (WebSocket)
│   └── webhooks.py     # Configuration webhooks
├── apps/               # Vos applications Django
├── requirements/       # Dépendances
│   ├── base.txt
│   ├── dev.txt
│   └── prod.txt
├── docs/               # Documentation
├── deploy/             # Configuration déploiement
├── .env.example        # Variables d'environnement
└── Dockerfile          # Build Docker
```

---

## Installation des Dépendances

### Développement

```bash
pip install -r requirements/dev.txt
```

### Production

```bash
pip install -r requirements/prod.txt
```

---

## Configuration de la Base de Données

### SQLite (Développement)

Par défaut, le projet utilise SQLite (aucune configuration nécessaire).

### PostgreSQL (Production)

1. Créez la base de données :

```bash
createdb mon_projet_db
```

2. Configurez la variable d'environnement :

```bash
export DATABASE_URL=postgres://user:password@localhost:5432/mon_projet_db
```

3. Ou modifiez `.env` :

```ini
DATABASE_URL=postgres://user:password@localhost:5432/mon_projet_db
```

---

## Initialisation

### Appliquer les Migrations

```bash
python manage.py migrate
```

### Créer un Superutilisateur

```bash
python manage.py createsuperuser
```

### Démarrer le Serveur

```bash
python manage.py runserver
```

Accédez à :

- **GraphiQL** : http://localhost:8000/graphql/graphiql/
- **Admin Django** : http://localhost:8000/admin/

---

## Vérification de l'Installation

### Test GraphQL

Ouvrez GraphiQL et exécutez :

```graphql
query {
  __schema {
    types {
      name
    }
  }
}
```

### Test d'Authentification

```graphql
mutation {
  login(username: "admin", password: "votre_mot_de_passe") {
    ok
    token
    user {
      username
    }
  }
}
```

---

## Prochaines Étapes

- [Démarrage Rapide](./quickstart.md) - Créer votre première API
- [Configuration](../graphql/configuration.md) - Personnaliser le framework

---

## Dépannage

### Erreur : "rail-admin command not found"

Assurez-vous que le package est installé et que le répertoire Scripts/bin est dans votre PATH.

```bash
pip show rail-django
# Vérifiez "Location" et ajoutez bin/ à votre PATH
```

### Erreur : "No module named 'rail_django'"

Vérifiez l'installation :

```bash
pip list | grep rail
```

Si absent, réinstallez :

```bash
pip install rail-django
```

### Erreur de migration

Assurez-vous que la base de données est accessible et que `DATABASE_URL` est correcte.

```bash
python manage.py dbshell
```
