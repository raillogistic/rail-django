"""Root schema configuration for Django GraphQL Auto-Generation."""
from .core.schema import SchemaBuilder
from .core.settings import SchemaSettings

# Initialize schema settings
settings = SchemaSettings()

# Create schema builder instance
builder = SchemaBuilder(settings)

# Get the auto-generated schema
schema = builder.get_schema()
