"""
Subscriptions extension package.
"""

from .consumer import get_subscription_consumer
from .broadcaster import ensure_broadcast_signals
from .registry import clear_subscription_registry, iter_subscriptions_for_model
from ...generators.subscriptions.utils import RailSubscription

# Alias for convenience
broadcast = RailSubscription.broadcast

__all__ = [
    "get_subscription_consumer",
    "ensure_broadcast_signals",
    "clear_subscription_registry",
    "iter_subscriptions_for_model",
    "RailSubscription",
    "broadcast",
]