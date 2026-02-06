"""GraphQL error output types for table extension."""

import graphene


class TableErrorType(graphene.ObjectType):
    field = graphene.String()
    message = graphene.String(required=True)
    code = graphene.String(required=True)
    severity = graphene.String()
    details = graphene.JSONString()
    retryable = graphene.Boolean()
    retryAfter = graphene.Int()
    traceId = graphene.String()
