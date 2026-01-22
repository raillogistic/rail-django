# Authentication

Rail Django integrates seamlessly with Django's authentication system.

## Middleware

The framework provides `GraphQLAuthenticationMiddleware`, which ensures `info.context.user` is populated correctly.

It supports:
1.  **Session Authentication**: Standard Django sessions (good for same-domain apps).
2.  **Token Authentication**: Integration with `Authorization: Bearer ...` headers (e.g., JWT).

## Configuration

In `settings.py`:

```python
MIDDLEWARE = [
    # ...
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "rail_django.middleware.performance.GraphQLPerformanceMiddleware", # Optional but recommended
    # ...
]
```

## Accessing User

In any resolver:

```python
def resolve_my_field(root, info):
    user = info.context.user
    if user.is_authenticated:
        return f"Hello, {user.username}"
    return "Hello, Guest"
```

## JWT Support

Rail Django works with standard JWT libraries like `django-graphql-jwt`.

To enable:
1.  Install `django-graphql-jwt`.
2.  Add its middleware/authentication backend.
3.  Register the mutations.

```python
# schema.py
import graphene
import graphql_jwt

class Mutation(graphene.ObjectType):
    token_auth = graphql_jwt.ObtainJSONWebToken.Field()
    verify_token = graphql_jwt.Verify.Field()
    refresh_token = graphql_jwt.Refresh.Field()
```
