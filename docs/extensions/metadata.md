# Metadata Extension

Module: `rail_django.extensions.metadata`

- Exposes model metadata for frontends (forms, tables).
- Enable with `schema_settings.show_metadata = True`.
- Metadata is private and requires an authenticated user.
- Cache policy lives under `RAIL_DJANGO_GRAPHQL["METADATA"]` in
  [reference/configuration](../reference/configuration.md).
