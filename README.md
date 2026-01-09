# Rail Django

> **Cadre de travail GraphQL pour Django (Entreprise-grade)**
> *Accélérez le développement de vos API GraphQL sécurisées et performantes.*

**Rail Django** est une surcouche spécialisée pour `Graphene-Django` conçue pour éliminer le code répétitif (boilerplate) et imposer des standards de sécurité et d'architecture de niveau production dès le premier jour.

---

## 🚀 Fonctionnalités Clés (Caractéristiques principales)

*   **Génération Automatique (Auto-génération):** Crée instantanément des Types, Requêtes (Queries) et Mutations CRUD à partir de vos modèles Django.
*   **Sécurité Native (Sécurité intégrée):** RBAC (Contrôle d'accès basé sur les rôles), limitation de profondeur des requêtes, et validation des entrées activés par défaut.
*   **Audit & Traçabilité (Journalisation d'audit):** Système complet de logs pour les actions sensibles et les tentatives d'authentification.
*   **Extensions "Batteries Incluses" (Extensions intégrées):** Monitoring de santé (Health checks), export Excel/CSV, MFA, et génération de PDF.
*   **Optimisation de Performance (Optimisation des requêtes):** Résolution automatique du problème N+1 via l'injection intelligente de `select_related` et `prefetch_related`.

---

## 🛠️ Installation et Démarrage Rapide

### Installation (Installation du paquet)

```bash
pip install rail-django
```

### Initialisation d'un projet (Scaffolding)

Utilisez l'outil CLI `rail-admin` pour créer une structure de projet propre et conforme :

```bash
rail-admin startproject mon_projet_api
cd mon_projet_api
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Accédez à l'interface GraphiQL sur `http://localhost:8000/graphql`.

---

## 🏗️ Architecture du Code (Structure interne)

Le framework est structuré en modules découplés pour assurer une maintenance aisée :

*   **`rail_django.core`**: Gère le registre des schémas (`SchemaRegistry`) et le moteur de construction (`SchemaBuilder`).
*   **`rail_django.generators`**: Contient l'intelligence de conversion ORM vers GraphQL (`TypeGenerator`, `MutationGenerator`).
*   **`rail_django.security`**: Implémente le moteur de permissions fines et le RBAC.
*   **`rail_django.extensions`**: Regroupe les fonctionnalités pluggables (Santé, Audit, Export).

Pour une analyse détaillée du fonctionnement interne, consultez le dossier [**docs/**](docs/README.md).

---

## 🔒 Sécurité et RBAC (Gestion des accès)

Rail Django utilise une approche hybride pour la gestion des droits :

```python
# Exemple de configuration de métadonnées (Metadata)
class Document(models.Model):
    titre = models.CharField(max_length=200, verbose_name="Titre du document")
    contenu = models.TextField(verbose_name="Contenu privé")

    graphql_meta = GraphQLMeta(
        exclude=["secret_key"],
        field_permissions={
            "contenu": {
                "roles": ["manager", "admin"],
                "visibility": "hidden"
            }
        }
    )
```

---

## 📖 Documentation Complète (Guide technique)

Une documentation technique détaillée axée sur le fonctionnement du code est disponible dans le répertoire `docs/` :

*   [**Architecture Internals**](docs/architecture.md) : Pipeline de construction et design patterns.
*   [**Modules & Classes**](docs/modules.md) : Référence technique des composants.
*   [**Security Internals**](docs/security.md) : Détails de l'implémentation RBAC et Audit.
*   [**Configuration system**](docs/configuration.md) : Fonctionnement du `SettingsProxy`.

---

## 🤝 Contribution (Contribuer au projet)

Les contributions sont les bienvenues ! Merci de consulter nos directives de contribution avant de soumettre une Pull Request.

**Licence :** MIT
