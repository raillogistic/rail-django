"""
Registre de hooks enfichables pour le SchemaManager.

Ce module fournit un registre de hooks centralisé et typé pour le cycle
de vie des schémas GraphQL. Il remplace la gestion ad hoc des hooks
pré/post opération par un système plus formel et extensible.

Utilisation:

    from rail_django.management.schema.hooks import hook_registry

    @hook_registry.on(SchemaOperation.REGISTER, when="post")
    def log_registration(context: dict) -> None:
        print(f"Schéma enregistré : {context['name']}")

    # Ou programmatiquement :
    hook_registry.register(SchemaOperation.DELETE, my_hook, when="pre")
    hook_registry.unregister(SchemaOperation.DELETE, my_hook, when="pre")
    hook_registry.clear()
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Callable

from .lifecycle import SchemaOperation

logger = logging.getLogger(__name__)

HookCallable = Callable[[dict[str, Any]], None]


class SchemaHookRegistry:
    """Registre centralisé de hooks pour les opérations de schéma.

    Ce registre remplace les dictionnaires internes ``_pre_operation_hooks``
    et ``_post_operation_hooks`` du ``SchemaManager`` par un système
    enfichable, testable et réutilisable.

    Attributes:
        _pre_hooks: Hooks exécutés avant chaque opération.
        _post_hooks: Hooks exécutés après chaque opération.
    """

    def __init__(self) -> None:
        self._pre_hooks: dict[SchemaOperation, list[HookCallable]] = defaultdict(list)
        self._post_hooks: dict[SchemaOperation, list[HookCallable]] = defaultdict(list)

    def _select_registry(self, when: str) -> dict[SchemaOperation, list[HookCallable]]:
        """Sélectionne le registre de hooks en fonction du timing.

        Args:
            when: Timing du hook, ``'pre'`` ou ``'post'``.

        Returns:
            Le dictionnaire de hooks correspondant.

        Raises:
            ValueError: Si ``when`` n'est ni ``'pre'`` ni ``'post'``.
        """
        if when == "pre":
            return self._pre_hooks
        if when == "post":
            return self._post_hooks
        raise ValueError(f"'when' doit être 'pre' ou 'post', reçu : {when!r}")

    def register(
        self,
        operation: SchemaOperation,
        hook: HookCallable,
        *,
        when: str = "post",
    ) -> None:
        """Enregistre un hook pour une opération de schéma.

        Args:
            operation: L'opération de schéma à écouter.
            hook: Le callable à exécuter.
            when: Timing du hook (``'pre'`` ou ``'post'``).
        """
        registry = self._select_registry(when)
        if hook not in registry[operation]:
            registry[operation].append(hook)
            logger.debug(
                "Hook enregistré pour %s-%s : %s",
                when,
                operation.value,
                getattr(hook, "__name__", repr(hook)),
            )

    def unregister(
        self,
        operation: SchemaOperation,
        hook: HookCallable,
        *,
        when: str = "post",
    ) -> bool:
        """Supprime un hook enregistré.

        Args:
            operation: L'opération de schéma ciblée.
            hook: Le callable à retirer.
            when: Timing du hook (``'pre'`` ou ``'post'``).

        Returns:
            ``True`` si le hook a été retiré, ``False`` s'il n'existait pas.
        """
        registry = self._select_registry(when)
        hooks = registry.get(operation, [])
        try:
            hooks.remove(hook)
            return True
        except ValueError:
            return False

    def on(
        self,
        operation: SchemaOperation,
        *,
        when: str = "post",
    ) -> Callable[[HookCallable], HookCallable]:
        """Décorateur pour enregistrer un hook.

        Exemple::

            @hook_registry.on(SchemaOperation.REGISTER, when="post")
            def on_register(context: dict) -> None:
                ...

        Args:
            operation: L'opération de schéma à écouter.
            when: Timing du hook (``'pre'`` ou ``'post'``).

        Returns:
            Le décorateur qui enregistre la fonction.
        """
        def decorator(func: HookCallable) -> HookCallable:
            self.register(operation, func, when=when)
            return func
        return decorator

    def execute(
        self,
        operation: SchemaOperation,
        when: str,
        context: dict[str, Any],
    ) -> None:
        """Exécute tous les hooks enregistrés pour une opération.

        Les erreurs dans les hooks individuels sont loguées mais ne bloquent
        pas l'exécution des hooks suivants.

        Args:
            operation: L'opération de schéma en cours.
            when: Timing du hook (``'pre'`` ou ``'post'``).
            context: Dictionnaire de contexte passé à chaque hook.
        """
        registry = self._select_registry(when)
        hooks = registry.get(operation, [])
        for hook in hooks:
            try:
                hook(context)
            except Exception as exc:
                logger.error(
                    "Erreur dans le hook %s-%s (%s) : %s",
                    when,
                    operation.value,
                    getattr(hook, "__name__", repr(hook)),
                    exc,
                )

    def get_hooks(
        self,
        operation: SchemaOperation,
        when: str,
    ) -> list[HookCallable]:
        """Retourne les hooks enregistrés pour une opération et un timing.

        Args:
            operation: L'opération de schéma ciblée.
            when: Timing du hook (``'pre'`` ou ``'post'``).

        Returns:
            Liste des hooks enregistrés (copie).
        """
        registry = self._select_registry(when)
        return list(registry.get(operation, []))

    def clear(self, operation: SchemaOperation | None = None) -> None:
        """Supprime tous les hooks enregistrés.

        Args:
            operation: Si fourni, ne supprime que les hooks de cette opération.
                Si ``None``, supprime tous les hooks.
        """
        if operation is None:
            self._pre_hooks.clear()
            self._post_hooks.clear()
            logger.debug("Tous les hooks ont été supprimés")
        else:
            self._pre_hooks.pop(operation, None)
            self._post_hooks.pop(operation, None)
            logger.debug(
                "Hooks supprimés pour l'opération %s", operation.value
            )


# Instance globale du registre de hooks, partagée par le SchemaManager.
hook_registry = SchemaHookRegistry()
