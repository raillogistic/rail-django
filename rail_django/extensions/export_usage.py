"""
Django Model Export Usage Examples

This module demonstrates how to use the Django model export functionality
with the enhanced field format and GraphQL filter integration.

Field Format Options:
1. String format: "field_name" - Uses field name as accessor and verbose_name as title
2. Dict format: {"accessor": "field_name", "title": "Custom Title"} - Custom accessor and title

Filter Integration:
- Uses the same GraphQL filter classes as queries
- Supports quick filters, date filters, custom filters, and complex filtering
- Fallback to basic Django filtering if GraphQL filters are not available
"""

import json

import requests

from rail_django.extensions.exporting import (
    ModelExporter,
    export_model_to_csv,
    export_model_to_excel,
)


def example_csv_export():
    """Example: Export model data to CSV with mixed field formats."""

    # Mixed field format example
    fields = [
        "title",  # String format - uses verbose_name as title
        "author.username",  # Nested field access
        {"accessor": "slug", "title": "URL Slug"},  # Dict format with custom title
        {"accessor": "created_at"},  # Dict format without title (uses verbose_name)
        "is_published",
        {"accessor": "tags.count", "title": "Tag Count"},  # Method/property access
    ]

    # GraphQL-style filtering
    filters = {
        "status": "published",
        "quick": "django tutorial",  # Quick search filter
        "created_date_this_month": True,  # Date filter
        "has_tags": True,  # Custom filter
        "author__is_active": True,  # Nested field filter
    }

    ordering = ["-created_at", "title"]

    # Export to CSV
    csv_content = export_model_to_csv(
        app_name="blog",
        model_name="Post",
        fields=fields,
        filters=filters,
        ordering=ordering,
    )

    # Save to file
    with open("posts_export.csv", "wb") as f:
        f.write(csv_content)

    print("CSV export completed: posts_export.csv")


def example_excel_export():
    """Example: Export model data to Excel with advanced filtering."""

    fields = [
        "title",
        {"accessor": "author.username", "title": "Author Name"},
        {"accessor": "author.email", "title": "Author Email"},
        "category.name",
        {"accessor": "created_at", "title": "Publication Date"},
        {"accessor": "updated_at", "title": "Last Modified"},
        "view_count",
        {"accessor": "is_featured", "title": "Featured Post"},
    ]

    # Advanced GraphQL filtering
    filters = {
        "category__name__in": ["Technology", "Programming"],
        "view_count__gte": 100,
        "published_date_last_week": True,
        "author__profile__verified": True,
        "quick": "python django",
    }

    ordering = ["-view_count", "-created_at"]

    # Export to Excel
    excel_content = export_model_to_excel(
        app_name="blog",
        model_name="Post",
        fields=fields,
        filters=filters,
        ordering=ordering,
    )

    # Save to file
    with open("featured_posts_export.xlsx", "wb") as f:
        f.write(excel_content)

    print("Excel export completed: featured_posts_export.xlsx")


def example_model_exporter_usage():
    """Example: Direct ModelExporter class usage with enhanced features."""

    # Initialize exporter
    exporter = ModelExporter("blog", "Post")

    # Define fields with mixed formats
    fields = [
        "title",  # String format
        {"accessor": "slug", "title": "URL Slug"},  # Dict with custom title
        {"accessor": "author.username"},  # Dict without title (uses verbose_name)
        "content_preview",  # Method or property
        {"accessor": "tags.all", "title": "All Tags"},  # Many-to-many field
        {"accessor": "comment_count", "title": "Comments"},  # Computed field
    ]

    # GraphQL-style filters
    filters = {
        "status": "published",
        "is_featured": True,
        "created_date_today": True,
        "author__is_staff": False,
        "tags__name__icontains": "python",
    }

    ordering = ["-created_at"]

    # Export to CSV
    csv_data = exporter.export_to_csv(fields, filters, ordering)
    with open("direct_export.csv", "wb") as f:
        f.write(csv_data)

    # Export to Excel
    excel_data = exporter.export_to_excel(fields, filters, ordering)
    with open("direct_export.xlsx", "wb") as f:
        f.write(excel_data)

    print("Direct exporter usage completed")


def example_http_api_excel():
    """Example: HTTP API usage for Excel export with enhanced field format."""

    payload = {
        "app_name": "blog",
        "model_name": "Post",
        "file_extension": "xlsx",
        "filename": "blog_posts_export",
        "fields": [
            "title",  # String format
            "author.username",  # Nested field
            {"accessor": "slug", "title": "URL Slug"},  # Dict with custom title
            {"accessor": "created_at", "title": "Created Date"},
            {"accessor": "is_published", "title": "Published Status"},
            {"accessor": "category.name", "title": "Category"},
        ],
        "ordering": ["-created_at", "title"],
        "variables": {
            "status": "published",
            "quick": "django tutorial",
            "created_date_this_week": True,
            "author__is_active": True,
            "category__slug__in": ["tech", "programming"],
        },
    }

    # Make HTTP request
    response = requests.post(
        "http://localhost:8000/api/export/",
        json=payload,
        headers={"Content-Type": "application/json"},
    )

    if response.status_code == 200:
        # Save the Excel file
        with open("api_export.xlsx", "wb") as f:
            f.write(response.content)
        print("HTTP API Excel export completed: api_export.xlsx")
    else:
        print(f"Export failed: {response.status_code} - {response.text}")


def example_http_api_csv():
    """Example: HTTP API usage for CSV export with GraphQL filters."""

    payload = {
        "app_name": "ecommerce",
        "model_name": "Product",
        "file_extension": "csv",
        "filename": "products_report",
        "fields": [
            "name",
            {"accessor": "sku", "title": "Product SKU"},
            "price",
            {"accessor": "category.name", "title": "Category"},
            {"accessor": "supplier.company_name", "title": "Supplier"},
            {"accessor": "stock_quantity", "title": "Stock"},
            {"accessor": "is_active", "title": "Active Status"},
        ],
        "ordering": ["category.name", "-price"],
        "variables": {
            "is_active": True,
            "stock_quantity__gt": 0,
            "price__range": [10, 1000],
            "category__is_featured": True,
            "quick": "electronics",
            "created_date_last_month": True,
        },
    }

    # Make HTTP request
    response = requests.post(
        "http://localhost:8000/api/export/",
        json=payload,
        headers={"Content-Type": "application/json"},
    )

    if response.status_code == 200:
        # Save the CSV file
        with open("products_report.csv", "wb") as f:
            f.write(response.content)
        print("HTTP API CSV export completed: products_report.csv")
    else:
        print(f"Export failed: {response.status_code} - {response.text}")


def example_complex_nested_fields():
    """Example: Complex nested field access and method calls."""

    fields = [
        "title",
        {"accessor": "author.profile.full_name", "title": "Author Full Name"},
        {"accessor": "author.profile.bio", "title": "Author Bio"},
        {"accessor": "category.parent.name", "title": "Parent Category"},
        {"accessor": "tags.count", "title": "Tag Count"},
        {
            "accessor": "comments.filter(is_approved=True).count",
            "title": "Approved Comments",
        },
        {"accessor": "get_absolute_url", "title": "URL"},
        {"accessor": "word_count", "title": "Word Count"},  # Custom property
        {"accessor": "reading_time", "title": "Reading Time"},  # Custom method
    ]

    # Advanced filtering with nested relationships
    filters = {
        "author__profile__is_verified": True,
        "category__parent__slug": "technology",
        "tags__name__in": ["python", "django", "web-development"],
        "comments__count__gte": 5,
        "word_count__range": [500, 2000],
        "published_date_between": ["2024-01-01", "2024-12-31"],
        "quick": "advanced tutorial",
    }

    ordering = ["-published_at", "author.profile.full_name"]

    # Export using ModelExporter
    exporter = ModelExporter("blog", "Article")

    csv_content = exporter.export_to_csv(fields, filters, ordering)
    with open("complex_export.csv", "wb") as f:
        f.write(csv_content)

    excel_content = exporter.export_to_excel(fields, filters, ordering)
    with open("complex_export.xlsx", "wb") as f:
        f.write(excel_content)

    print("Complex nested fields export completed")


# Commented out Django management command example
"""
# Example Django Management Command
# File: management/commands/export_data.py

from django.core.management.base import BaseCommand
from rail_django.extensions.exporting import ModelExporter


class Command(BaseCommand):
    help = 'Export model data to CSV or Excel'
    
    def add_arguments(self, parser):
        parser.add_argument('app_name', type=str, help='Django app name')
        parser.add_argument('model_name', type=str, help='Model name')
        parser.add_argument('--format', choices=['csv', 'excel'], default='csv')
        parser.add_argument('--output', type=str, help='Output filename')
        parser.add_argument('--fields', type=str, help='JSON string of field configurations')
        parser.add_argument('--filters', type=str, help='JSON string of filter parameters')
        parser.add_argument('--ordering', type=str, help='JSON string of ordering fields')
    
    def handle(self, *args, **options):
        import json
        
        app_name = options['app_name']
        model_name = options['model_name']
        format_type = options['format']
        output_file = options.get('output') or f"{model_name.lower()}_export"
        
        # Parse JSON arguments
        fields = json.loads(options.get('fields', '["id"]'))
        filters = json.loads(options.get('filters', '{}'))
        ordering = json.loads(options.get('ordering', '[]'))
        
        # Create exporter
        exporter = ModelExporter(app_name, model_name)
        
        # Export data
        if format_type == 'csv':
            content = exporter.export_to_csv(fields, filters, ordering)
            filename = f"{output_file}.csv"
        else:
            content = exporter.export_to_excel(fields, filters, ordering)
            filename = f"{output_file}.xlsx"
        
        # Save file
        with open(filename, 'wb') as f:
            f.write(content)
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully exported data to {filename}')
        )

# Usage examples:
# python manage.py export_data blog Post --format=csv --fields='["title", {"accessor": "author.username", "title": "Author"}]'
# python manage.py export_data blog Post --format=excel --filters='{"status": "published", "quick": "django"}'
"""


if __name__ == "__main__":
    print("Running Django Model Export Examples...")

    # Run examples (comment out as needed)
    example_csv_export()
    example_excel_export()
    example_model_exporter_usage()
    example_complex_nested_fields()

    # HTTP API examples (requires running Django server)
    # example_http_api_excel()
    # example_http_api_csv()

    print("All examples completed!")
