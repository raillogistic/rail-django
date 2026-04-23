import os
import django
import cProfile
import pstats
import io

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rail_django.config.framework_settings")
django.setup()

from rail_django.core.registry import schema_registry

def profile_registry():
    pr = cProfile.Profile()
    pr.enable()
    
    schema_registry.discover_schemas()
    names = schema_registry.get_schema_names()
    if not names:
        print("No schemas found")
        return
    builder = schema_registry.get_schema_builder(names[0])
    schema = builder.get_schema()
    
    pr.disable()
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats('tottime')
    ps.print_stats(30)
    print(s.getvalue())

profile_registry()
