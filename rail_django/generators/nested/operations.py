"""
Unified relation operation processor.
"""

from dataclasses import dataclass
from typing import Any, Type, Optional, List
from django.db import models
import logging

logger = logging.getLogger(__name__)

@dataclass
class RelationOperation:
    operation: str  # "connect", "create", "update", "disconnect", "set"
    data: Any
    field_name: str
    related_model: Type[models.Model]

class RelationOperationProcessor:
    """
    Processes unified relation operations (connect/create/update/etc)
    by delegating to the handler's specific implementation methods.
    """
    
    def __init__(self, handler):
        self.handler = handler

    def process_relation(
        self, 
        instance: models.Model, 
        field_name: str, 
        operations_data: dict, 
        info=None,
        is_m2m: bool = False,
        is_reverse: bool = False
    ):
        """
        Process all operations for a relation field uniformly.
        Expected operations_data: { "connect": [...], "create": [...] }
        """
        model = type(instance)
        # Determine relation model if not passed? 
        # We rely on handler to pass correct context or we introspect.
        # But iterating operations is standard.
        
        # Order: set -> disconnect -> connect -> create -> update
        order = ["set", "disconnect", "connect", "create", "update"]
        
        for op in order:
            if op in operations_data:
                data = operations_data[op]
                if data is None: 
                    continue
                    
                self._dispatch(instance, field_name, op, data, info, is_m2m, is_reverse)

    def _dispatch(self, instance, field_name, operation, data, info, is_m2m, is_reverse):
        # Dispatch to specific handler methods based on operation
        # The handler (NestedUpdateMixin/CreateMixin) should expose these methods.
        # We will assume they are available on self.handler
        try:
            if hasattr(self.handler, "_assert_relation_operation_allowed"):
                self.handler._assert_relation_operation_allowed(
                    type(instance), field_name, operation
                )
        except Exception:
            # Let handler raise the appropriate error when operation is disallowed
            raise
        
        if operation == "connect":
            self.handler.handle_connect(instance, field_name, data, info, is_m2m, is_reverse)
        elif operation == "create":
            self.handler.handle_create(instance, field_name, data, info, is_m2m, is_reverse)
        elif operation == "update":
            self.handler.handle_update(instance, field_name, data, info, is_m2m, is_reverse)
        elif operation == "disconnect":
            self.handler.handle_disconnect(instance, field_name, data, info, is_m2m, is_reverse)
        elif operation == "set":
            self.handler.handle_set(instance, field_name, data, info, is_m2m, is_reverse)
