"""Table v3 subscription placeholders."""

import graphene

from ..services.subscription_manager import (
    can_emit,
    set_presence,
    subscription_health,
    subscribe,
)


class TableRowsChangedType(graphene.ObjectType):
    changeType = graphene.String(required=True)
    affectedIds = graphene.List(graphene.ID, required=True)
    updatedFields = graphene.List(graphene.String)
    invalidateCache = graphene.Boolean()


class TableUserPresenceType(graphene.ObjectType):
    userId = graphene.String(required=True)
    username = graphene.String(required=True)
    action = graphene.String(required=True)
    timestamp = graphene.String()
    subscriptionHealth = graphene.JSONString()


class TableSubscriptions(graphene.ObjectType):
    tableRowsChanged = graphene.Field(
        TableRowsChangedType,
        app=graphene.String(required=True),
        model=graphene.String(required=True),
    )
    tableUserPresence = graphene.Field(
        TableUserPresenceType,
        app=graphene.String(required=True),
        model=graphene.String(required=True),
    )

    def resolve_tableRowsChanged(self, info, app: str, model: str):
        user = getattr(info.context, "user", None)
        user_id = str(getattr(user, "id", "0"))
        subscribe(app, model, user_id)
        if not can_emit(app, model):
            return {
                "changeType": "THROTTLED",
                "affectedIds": [],
                "updatedFields": [],
                "invalidateCache": False,
            }
        return {
            "changeType": "NOOP",
            "affectedIds": [],
            "updatedFields": [],
            "invalidateCache": False,
        }

    def resolve_tableUserPresence(self, info, app: str, model: str):
        user = getattr(info.context, "user", None)
        username = getattr(user, "username", "anonymous")
        user_id = str(getattr(user, "id", "0"))
        payload = set_presence(app, model, user_id, "VIEWING")
        return {
            "userId": user_id,
            "username": username,
            "action": payload["action"],
            "timestamp": payload["timestamp"],
            "subscriptionHealth": subscription_health(app, model),
        }
