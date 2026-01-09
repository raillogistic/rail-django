"""
Hook registry system for GraphQL schema registry.
"""

import logging
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class HookRegistry:
    """
    Registry for managing hooks in the GraphQL schema system.

    This provides a centralized way to register and execute hooks
    for various events in the schema lifecycle.
    """

    def __init__(self):
        self._hooks: Dict[str, List[Callable]] = defaultdict(list)
        self._hook_metadata: Dict[str, Dict[str, Any]] = {}

    def register_hook(self,
                      event: str,
                      hook: Callable,
                      priority: int = 100,
                      name: Optional[str] = None,
                      description: Optional[str] = None) -> None:
        """
        Register a hook for a specific event.

        Args:
            event: Event name (e.g., 'pre_registration', 'post_registration')
            hook: Hook function to register
            priority: Hook priority (lower numbers run first)
            name: Optional hook name for identification
            description: Optional hook description
        """
        hook_name = name or f"{hook.__module__}.{hook.__name__}"

        # Store hook with metadata
        hook_info = {
            'hook': hook,
            'priority': priority,
            'name': hook_name,
            'description': description or '',
            'event': event
        }

        # Insert hook in priority order
        hooks_list = self._hooks[event]
        inserted = False

        for i, existing_hook_info in enumerate(hooks_list):
            if priority < existing_hook_info.get('priority', 100):
                hooks_list.insert(i, hook_info)
                inserted = True
                break

        if not inserted:
            hooks_list.append(hook_info)

        self._hook_metadata[hook_name] = hook_info
        logger.debug(f"Registered hook '{hook_name}' for event '{event}' with priority {priority}")

    def unregister_hook(self, event: str, hook: Callable) -> bool:
        """
        Unregister a hook for a specific event.

        Args:
            event: Event name
            hook: Hook function to unregister

        Returns:
            True if hook was found and removed, False otherwise
        """
        hooks_list = self._hooks[event]

        for i, hook_info in enumerate(hooks_list):
            if hook_info['hook'] == hook:
                removed_hook = hooks_list.pop(i)
                hook_name = removed_hook['name']
                if hook_name in self._hook_metadata:
                    del self._hook_metadata[hook_name]
                logger.debug(f"Unregistered hook '{hook_name}' for event '{event}'")
                return True

        return False

    def unregister_hook_by_name(self, hook_name: str) -> bool:
        """
        Unregister a hook by its name.

        Args:
            hook_name: Name of hook to unregister

        Returns:
            True if hook was found and removed, False otherwise
        """
        if hook_name not in self._hook_metadata:
            return False

        hook_info = self._hook_metadata[hook_name]
        event = hook_info['event']
        hook = hook_info['hook']

        return self.unregister_hook(event, hook)

    def get_hooks(self, event: str) -> List[Dict[str, Any]]:
        """
        Get all hooks for a specific event.

        Args:
            event: Event name

        Returns:
            List of hook information dictionaries
        """
        return self._hooks[event].copy()

    def get_hook_functions(self, event: str) -> List[Callable]:
        """
        Get hook functions for a specific event.

        Args:
            event: Event name

        Returns:
            List of hook functions in priority order
        """
        return [hook_info['hook'] for hook_info in self._hooks[event]]

    def execute_hooks(self, event: str, *args, **kwargs) -> List[Any]:
        """
        Execute all hooks for a specific event.

        Args:
            event: Event name
            *args: Positional arguments to pass to hooks
            **kwargs: Keyword arguments to pass to hooks

        Returns:
            List of hook results
        """
        results = []
        hooks = self._hooks[event]

        logger.debug(f"Executing {len(hooks)} hooks for event '{event}'")

        for hook_info in hooks:
            hook = hook_info['hook']
            hook_name = hook_info['name']

            try:
                result = hook(*args, **kwargs)
                results.append(result)
                logger.debug(f"Hook '{hook_name}' executed successfully")
            except Exception as e:
                logger.error(f"Error executing hook '{hook_name}' for event '{event}': {e}")
                results.append(None)

        return results

    def execute_hooks_with_modification(self, event: str, initial_data: Dict[str, Any], *args, **kwargs) -> Dict[str, Any]:
        """
        Execute hooks that can modify data.

        Args:
            event: Event name
            initial_data: Initial data dictionary
            *args: Additional positional arguments
            **kwargs: Additional keyword arguments

        Returns:
            Modified data dictionary
        """
        modified_data = initial_data.copy()
        hooks = self._hooks[event]

        logger.debug(f"Executing {len(hooks)} modification hooks for event '{event}'")

        for hook_info in hooks:
            hook = hook_info['hook']
            hook_name = hook_info['name']

            try:
                result = hook(modified_data, *args, **kwargs)
                if isinstance(result, dict):
                    modified_data.update(result)
                logger.debug(f"Modification hook '{hook_name}' executed successfully")
            except Exception as e:
                logger.error(
                    f"Error executing modification hook '{hook_name}' for event '{event}': {e}")

        return modified_data

    def clear_hooks(self, event: Optional[str] = None) -> None:
        """
        Clear hooks for a specific event or all events.

        Args:
            event: Event name to clear, or None to clear all
        """
        if event:
            if event in self._hooks:
                # Remove metadata for hooks being cleared
                for hook_info in self._hooks[event]:
                    hook_name = hook_info['name']
                    if hook_name in self._hook_metadata:
                        del self._hook_metadata[hook_name]

                del self._hooks[event]
                logger.debug(f"Cleared all hooks for event '{event}'")
        else:
            self._hooks.clear()
            self._hook_metadata.clear()
            logger.debug("Cleared all hooks for all events")

    def get_events(self) -> List[str]:
        """Get list of all events that have registered hooks."""
        return list(self._hooks.keys())

    def get_hook_count(self, event: Optional[str] = None) -> int:
        """
        Get count of hooks for an event or total hooks.

        Args:
            event: Event name, or None for total count

        Returns:
            Number of hooks
        """
        if event:
            return len(self._hooks[event])
        else:
            return sum(len(hooks) for hooks in self._hooks.values())

    def get_hook_info(self, hook_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific hook.

        Args:
            hook_name: Name of hook

        Returns:
            Hook information dictionary or None if not found
        """
        return self._hook_metadata.get(hook_name)

    def list_hooks(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        List all registered hooks organized by event.

        Returns:
            Dictionary mapping event names to lists of hook info
        """
        result = {}
        for event, hooks in self._hooks.items():
            result[event] = [
                {
                    'name': hook_info['name'],
                    'priority': hook_info['priority'],
                    'description': hook_info['description']
                }
                for hook_info in hooks
            ]
        return result


# Global hook registry instance
hook_registry = HookRegistry()
