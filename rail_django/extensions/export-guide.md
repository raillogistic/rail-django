# Django Model Export Guide

This guide covers the enhanced Django model export functionality that allows you to generate Excel and CSV files from Django models with flexible field configurations and advanced GraphQL filter integration.

## Table of Contents

1. [Overview](#overview)
2. [Field Format Options](#field-format-options)
3. [Field Formatters and Masking](#field-formatters-and-masking)
4. [GraphQL Filter Integration](#graphql-filter-integration)
5. [HTTP API Usage](#http-api-usage)
6. [Python API Usage](#python-api-usage)
7. [Advanced Examples](#advanced-examples)
8. [Integration Setup](#integration-setup)
9. [Error Handling](#error-handling)
10. [Performance Considerations](#performance-considerations)

## Overview

The Django model export functionality provides:

- **Flexible Field Configuration**: Support for both string and dictionary field formats
- **GraphQL Filter Integration**: Uses the same advanced filtering as GraphQL queries
- **Multiple Export Formats**: Excel (.xlsx) and CSV support
- **HTTP API Endpoint**: RESTful API for generating exports
- **Python API**: Direct programmatic access to export functionality
- **Advanced Field Access**: Support for nested fields and allowlisted properties

## Field Format Options

### String Format

The simplest way to specify fields is using strings. The field name serves as both the accessor and the title (using the model field's `verbose_name`).

```python
fields = [
    "title",           # Uses field's verbose_name as title
    "author.username", # Nested field access
    "created_at",      # Date field
    "is_published"     # Boolean field
]
```

### Dictionary Format

For more control over field titles and complex accessors, use dictionary format:

```python
fields = [
    {"accessor": "title", "title": "Post Title"},
    {"accessor": "author.username", "title": "Author Name"},
    {"accessor": "slug"},  # Uses verbose_name as title
    {"accessor": "tags", "title": "Tags"}
]
```

Accessors must be explicitly allowlisted in `export_fields` and use dot notation.

### Mixed Format

You can combine both formats in the same export:

```python
fields = [
    "title",  # String format
    {"accessor": "author.username", "title": "Author"},  # Dict format
    "created_at",  # String format
    {"accessor": "view_count", "title": "Views"}  # Dict format
]
```

Callable accessors (methods) are disabled by default. If you need method-based
values, allowlist them explicitly and enable `allow_callables`.

## Field Formatters and Masking

Use `field_formatters` to apply PII masking or locale-aware formatting.

```python
RAIL_DJANGO_EXPORT = {
    "field_formatters": {
        "blog.Post": {
            "author.email": {"type": "mask", "show_last": 4},
            "created_at": {"type": "datetime", "format": "Y-m-d H:i"},
            "price": {"type": "number", "decimal_pos": 2},
        }
    }
}
```

## GraphQL Filter Integration

The export functionality integrates with the same GraphQL filter classes used in queries, providing advanced filtering capabilities beyond basic Django ORM filters.

Filters and ordering are allowlisted per model (`filterable_fields` / `orderable_fields`),
and guardrails enforce max filter count and OR depth.
Add special filter keys (like `quick`) to `filterable_special_fields` when needed.

### Basic Filters

```python
filters = {
    "status": "published",
    "is_featured": True,
    "author__is_active": True
}
```

### Quick Search Filters

```python
filters = {
    "quick": "django tutorial",  # Searches across configured quick_filter_fields
    "status": "published"
}
```

### Date Filters

```python
filters = {
    "created_date_today": True,
    "updated_date_this_week": True,
    "published_date_last_month": True,
    "archived_date_between": ["2024-01-01", "2024-12-31"]
}
```

### Custom Filters

```python
filters = {
    "has_tags": True,           # Custom filter defined in GraphQLMeta
    "content_length": "medium", # Custom filter with choices
    "reading_time_range": "5-10" # Custom filter with range
}
```

### Complex Filters

```python
filters = {
    "category__name__in": ["Technology", "Programming"],
    "view_count__gte": 100,
    "tags__name__icontains": "python",
    "author__profile__verified": True,
    "comments__created_at__range": ["2024-01-01", "2024-12-31"]
}
```

## HTTP API Usage

### Endpoint

```
POST /api/export/
```

### Request Format

```json
{
    "app_name": "blog",
    "model_name": "Post",
    "file_extension": "xlsx",  // or "csv"
    "filename": "blog_posts_export",
    "fields": [
        "title",
        "author.username",
        {"accessor": "slug", "title": "URL Slug"},
        {"accessor": "created_at", "title": "Publication Date"}
    ],
    "ordering": ["-created_at", "title"],
    "variables": {
        "status": "published",
        "quick": "django tutorial",
        "created_date_this_month": True,
        "author__is_active": True
    }
}
```

### Template + Async Example

```json
{
    "template": "recent_posts",
    "async": true,
    "variables": {
        "status": "published"
    }
}
```

### Response

The API returns the file as a downloadable attachment with appropriate headers:

- **Content-Type**: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` (Excel) or `text/csv` (CSV)
- **Content-Disposition**: `attachment; filename="blog_posts_export.xlsx"`

Async exports return a JSON payload with `job_id`, `status_url`, and `download_url`.

### Error Responses

```json
{
  "error": "Validation error",
  "details": "Invalid field configuration at index 2: field must be string or dict with accessor/title"
}
```

### API Documentation Endpoint

```
GET /api/export/
```

Returns API documentation and examples.

## Python API Usage

### Direct Functions

```python
from rail_django.extensions.exporting import export_model_to_csv, export_model_to_excel

# Export to CSV
csv_content = export_model_to_csv(
    app_name="blog",
    model_name="Post",
    fields=["title", {"accessor": "author.username", "title": "Author"}],
    filters={"status": "published", "quick": "django"},
    ordering=["-created_at"]
)

# Save to file
with open("posts.csv", "wb") as f:
    f.write(csv_content)

# Export to Excel
excel_content = export_model_to_excel(
    app_name="blog",
    model_name="Post",
    fields=["title", "author.username", "created_at"],
    filters={"is_featured": True},
    ordering=["-view_count"]
)

with open("featured_posts.xlsx", "wb") as f:
    f.write(excel_content)
```

### ModelExporter Class

```python
from rail_django.extensions.exporting import ModelExporter

# Initialize exporter
exporter = ModelExporter("blog", "Post")

# Define fields and filters
fields = [
    "title",
    {"accessor": "author.username", "title": "Author"},
    {"accessor": "category.name", "title": "Category"},
    "created_at"
]

filters = {
    "status": "published",
    "created_date_this_week": True,
    "author__is_staff": False
}

ordering = ["-created_at", "title"]

# Export to both formats
csv_data = exporter.export_to_csv(fields, filters, ordering)
excel_data = exporter.export_to_excel(fields, filters, ordering)

# Save files
with open("posts.csv", "wb") as f:
    f.write(csv_data)

with open("posts.xlsx", "wb") as f:
    f.write(excel_data)
```

## Advanced Examples

### Complex Nested Field Access

```python
fields = [
    "title",
    {"accessor": "author.profile.full_name", "title": "Author Full Name"},
    {"accessor": "author.profile.bio", "title": "Author Bio"},
    {"accessor": "category.parent.name", "title": "Parent Category"},
    {"accessor": "tags", "title": "Tags"},
    {"accessor": "word_count", "title": "Word Count"}  # Allowlisted property
]
```

### Advanced Filtering

```python
filters = {
    # Basic filters
    "status": "published",
    "is_featured": True,

    # Quick search
    "quick": "python django tutorial",

    # Date filters
    "created_date_this_month": True,
    "updated_date_last_week": True,

    # Range filters
    "view_count__range": [100, 10000],
    "word_count__gte": 500,

    # Nested relationship filters
    "author__profile__verified": True,
    "category__parent__slug": "technology",
    "tags__name__in": ["python", "django", "web-development"],

    # Custom filters (defined in GraphQLMeta)
    "has_tags": True,
    "content_length": "medium",
    "reading_difficulty": "intermediate"
}
```

### E-commerce Product Export

```python
# Product export with complex relationships
fields = [
    "name",
    {"accessor": "sku", "title": "Product SKU"},
    {"accessor": "price", "title": "Price ($)"},
    {"accessor": "category.name", "title": "Category"},
    {"accessor": "category.parent.name", "title": "Parent Category"},
    {"accessor": "supplier.company_name", "title": "Supplier"},
    {"accessor": "supplier.contact_email", "title": "Supplier Email"},
    {"accessor": "stock_quantity", "title": "Stock"},
    {"accessor": "variants", "title": "Variants"},
    {"accessor": "reviews", "title": "Reviews"},
    {"accessor": "average_rating", "title": "Rating"},  # Allowlisted property
    {"accessor": "is_active", "title": "Active"}
]

filters = {
    "is_active": True,
    "stock_quantity__gt": 0,
    "price__range": [10, 1000],
    "category__is_featured": True,
    "supplier__is_verified": True,
    "quick": "electronics smartphone",
    "created_date_last_month": True
}

ordering = ["category.name", "-created_at"]
```

## Integration Setup

### 1. Add to URLs

```python
# urls.py
from django.urls import path, include

urlpatterns = [
    # ... other patterns
    path('api/', include('rail_django.extensions.urls')),
]
```

The export URLs require JWT auth. If JWT decorators are unavailable,
`get_export_urls()` raises `ImproperlyConfigured`.

### 2. Import in Your Code

```python
# views.py or services.py
from rail_django.extensions.exporting import (
    ModelExporter,
    export_model_to_csv,
    export_model_to_excel
)
```

### 3. Configure GraphQL Meta (Optional)

To use advanced filters, ensure your models have proper GraphQL configuration:

```python
# models.py
class Post(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField()
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class GraphQLMeta:
        filter_fields = ['title', 'author', 'created_at']
        quick_filter_fields = ['title', 'content']
        custom_filters = {
            'has_tags': 'tags__isnull',
            'content_length': {
                'short': 'content__length__lt',
                'medium': 'content__length__range',
                'long': 'content__length__gt'
            }
        }
```

## Error Handling

### Common Errors

1. **Invalid Field Configuration**

   ```json
   {
     "error": "Invalid field configuration at index 2",
     "details": "Field must be string or dict with accessor/title"
   }
   ```

2. **Model Not Found**

   ```json
   {
     "error": "Model not found",
     "details": "Model 'InvalidModel' not found in app 'blog'"
   }
   ```

3. **Field Access Error**
   - Fields that don't exist or can't be accessed are logged as warnings
   - Empty string is used as fallback value

### Error Logging

The system logs errors for debugging:

```python
import logging

# Configure logging to see export errors
logging.getLogger('rail_django.extensions.exporting').setLevel(logging.WARNING)
```

## Performance Considerations

### Optimization Tips

1. **Limit Result Sets**: Use appropriate filters to limit the number of records
2. **Select Related**: The system automatically optimizes queries for foreign key fields
3. **Prefetch Related**: Many-to-many and reverse foreign key relationships are optimized
4. **Field Selection**: Only include necessary fields to reduce processing time
5. **Ordering**: Use database-level ordering instead of Python sorting

### Large Dataset Handling

For very large datasets, consider:

```python
# Use pagination or chunking for large exports
filters = {
    "created_at__gte": "2024-01-01",
    "created_at__lt": "2024-02-01"  # Monthly chunks
}

# Limit fields to essential data only
fields = ["id", "title", "created_at"]  # Minimal field set
```

### Memory Usage

- CSV exports are more memory-efficient than Excel
- Excel exports use write-only mode by default to reduce memory
- Consider CSV for very large datasets (>100k records)

## Security Considerations

1. **Authentication**: Implement proper authentication for the export endpoint
2. **Authorization**: Ensure users can only export data they have permission to view
3. **Rate Limiting**: Implement rate limiting to prevent abuse
4. **Allowlists**: Use `export_fields`, `filterable_fields`, and `orderable_fields`
5. **Formula Sanitization**: Enable CSV/Excel formula escaping for untrusted data

### Built-in Guardrails

The export endpoint supports server-side guardrails with `RAIL_DJANGO_EXPORT`
(or `RAIL_DJANGO_GRAPHQL["export_settings"]`):

```python
RAIL_DJANGO_EXPORT = {
    "max_rows": 5000,
    "stream_csv": True,
    "csv_chunk_size": 1000,
    "enforce_streaming_csv": True,
    "excel_write_only": True,
    "rate_limit": {
        "enable": True,
        "window_seconds": 60,
        "max_requests": 30,
    },
    "allowed_models": ["blog.Post"],
    "export_fields": {
        "blog.Post": ["id", "title", "author.username", "created_at"],
    },
    "export_exclude": {
        "blog.Post": ["author.password"],
    },
    "require_export_fields": True,
    "require_model_permissions": True,
    "require_field_permissions": True,
    "required_permissions": ["blog.export_post"],
    "filterable_fields": {
        "blog.Post": ["status", "author.username", "created_at"],
    },
    "filterable_special_fields": ["quick"],
    "orderable_fields": {
        "blog.Post": ["created_at", "title"],
    },
    "max_filters": 50,
    "max_or_depth": 3,
    "max_prefetch_depth": 2,
    "sanitize_formulas": True,
}
```

When enabled, the endpoint:

- Caps rows (with optional request overrides via `max_rows`)
- Blocks non-allowlisted models/fields
- Enforces filter/order allowlists and query guardrails
- Enforces model and field permissions
- Applies cache-backed rate limits
- Sanitizes CSV/Excel formulas

### Async Jobs and Templates

- `export_templates` define named field sets and default filters.
- Templates can be gated via `required_permissions`, `allowed_groups`, or `allowed_users`.
- Use `allow_overrides` to permit request overrides (e.g., `variables`, `filename`).
- `async_jobs` enables job-based exports with status and download URLs.
- Async workers require a shared cache backend.
- Async exports default to the `thread` backend; use `celery` or `rq` for workers.

### Example Security Implementation

```python
# views.py - Custom secure export view
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from rail_django.extensions.exporting import ExportView

@method_decorator(login_required, name='dispatch')
class SecureExportView(ExportView):
    def post(self, request):
        # Add custom authorization logic
        if not request.user.has_perm('myapp.export_data'):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        return super().post(request)
```

## Troubleshooting

### Common Issues

1. **GraphQL Filters Not Working**

   - Ensure `AdvancedFilterGenerator` is properly configured
   - Check that your model has `GraphQLMeta` configuration
   - Verify filter field names match your model fields

2. **Nested Field Access Fails**

   - Check that all relationships exist and are properly defined
   - Ensure foreign key fields are not null
   - Use `select_related` optimization for better performance

3. **Export Takes Too Long**
   - Add appropriate filters to limit result set
   - Reduce the number of fields being exported
   - Consider using CSV instead of Excel for large datasets

### Debug Mode

Enable debug logging to troubleshoot issues:

```python
# settings.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'rail_django.extensions.exporting': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': True,
        },
    },
}
```

This comprehensive guide covers all aspects of the enhanced Django model export functionality. The system provides flexible field configuration, advanced GraphQL filter integration, and robust error handling for reliable data export operations.
