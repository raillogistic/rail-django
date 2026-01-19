# Metadata Extension

Module: `rail_django.extensions.metadata`

- Exposes model metadata for frontends (forms, tables).
- Enable with `schema_settings.show_metadata = True`.
- Metadata is private and requires an authenticated user.
- Cache policy lives under `RAIL_DJANGO_GRAPHQL["METADATA"]` in
  [reference/configuration](../reference/configuration.md).

## Filter Metadata

The metadata extension exposes filter information that reflects the configured filter style:

### Filter Styles

Rail Django supports two filter input styles:

| Style | Argument | Type Pattern | Example |
|-------|----------|--------------|---------|
| Nested (default) | `where` | `{Model}WhereInput` | `where: { name: { icontains: "x" } }` |
| Flat (legacy/relay) | `filters` | `{Model}ComplexFilter` | `filters: { name__icontains: "x" }` |

Configure in settings:

```python
RAIL_DJANGO_GRAPHQL = {
    "query_settings": {
        # "nested" (default) or "flat"
        "filter_input_style": "nested",
        # Or enable both styles
        "enable_dual_filter_styles": True,
    }
}
```

### Nested Filter Operators

When using nested style, each field type exposes typed operators:

- **String**: `eq`, `neq`, `contains`, `icontains`, `starts_with`, `ends_with`, `in`, `not_in`, `is_null`, `regex`
- **Numeric**: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`, `between`, `is_null`
- **Date/DateTime**: All numeric operators plus `year`, `month`, `day`, `today`, `this_week`, `this_month`, `past_year`
- **Boolean**: `eq`, `is_null`
- **JSON**: `eq`, `is_null`, `has_key`, `has_keys`, `has_any_keys`

### Relation Filters

Nested style includes relation quantifiers for M2M and reverse relations:

- `{relation}_some`: At least one related object matches
- `{relation}_every`: All related objects match
- `{relation}_none`: No related objects match
- `{relation}_count`: Filter by count of related objects

See the [Filtering Guide](../guides/filtering.md) for complete documentation.
