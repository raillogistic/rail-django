
import re

file_path = 'rail_django/core/schema.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update imports
if 'from graphene.utils.str_converters import to_camel_case' in content:
    content = content.replace(
        'from graphene.utils.str_converters import to_camel_case',
        'from graphene.utils.str_converters import to_camel_case, to_snake_case'
    )

# 2. Fix model_name calculation
# Current: model_name = to_camel_case(model.__name__)
# Target: model_name = to_camel_case(to_snake_case(model.__name__))

content = content.replace(
    'model_name = to_camel_case(model.__name__)',
    'model_name = to_camel_case(to_snake_case(model.__name__))'
)

# 3. Fix _get_list_alias logic?
# The previous script replaced `return f"all_{alias}"` with `return to_camel_case(f"all_{alias}")`.
# `alias` comes from `_pluralize_name` or meta.
# If alias is "Products" (from verbose_name_plural), then `f"all_{alias}"` is "all_Products".
# `to_camel_case("all_Products")` -> "allProducts". This seems safe.
# But check `_get_list_alias` implementation again.
# It does `alias = ...strip("_").lower()` in the original code.
# My previous refactor removed the `.lower()` part implicitly?
# No, I only replaced the return statement!
# `alias = _GRAPHQL_NAME_INVALID_RE.sub("", alias).strip("_").lower()` WAS there.
# So `alias` is already lowercase.
# So `all_{alias}` is `all_products`.
# `to_camel_case("all_products")` -> "allProducts".
# So `allProducts` should be correct.

# The issue was definitely the `model_name` capitalization.

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed schema casing logic")
