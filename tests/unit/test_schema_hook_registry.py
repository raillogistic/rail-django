"""
Tests pour le registre de hooks enfichables du SchemaManager.

Ce module valide:
- L'enregistrement et l'exécution des hooks pré/post opération.
- Le décorateur ``@hook_registry.on()``.
- Le désenregistrement et le nettoyage des hooks.
- La gestion d'erreur dans les hooks (isolation).
"""

import pytest
from unittest.mock import MagicMock

from rail_django.management.schema.hooks import SchemaHookRegistry
from rail_django.management.schema.lifecycle import SchemaOperation


@pytest.mark.unit
class TestSchemaHookRegistry:
    """Tests pour la classe SchemaHookRegistry."""

    def setup_method(self):
        """Crée un registre neuf pour chaque test."""
        self.registry = SchemaHookRegistry()

    def test_register_and_execute_post_hook(self):
        """Un hook post enregistré doit être appelé avec le contexte."""
        callback = MagicMock()
        self.registry.register(SchemaOperation.REGISTER, callback, when="post")

        context = {"name": "test_schema"}
        self.registry.execute(SchemaOperation.REGISTER, "post", context)

        callback.assert_called_once_with(context)

    def test_register_and_execute_pre_hook(self):
        """Un hook pre enregistré doit être appelé avec le contexte."""
        callback = MagicMock()
        self.registry.register(SchemaOperation.DELETE, callback, when="pre")

        context = {"name": "to_delete"}
        self.registry.execute(SchemaOperation.DELETE, "pre", context)

        callback.assert_called_once_with(context)

    def test_decorator_registration(self):
        """Le décorateur @on() doit enregistrer le hook."""
        called_with = {}

        @self.registry.on(SchemaOperation.UPDATE, when="post")
        def on_update(ctx):
            called_with.update(ctx)

        self.registry.execute(SchemaOperation.UPDATE, "post", {"version": "2.0"})

        assert called_with == {"version": "2.0"}

    def test_unregister_hook(self):
        """Un hook désenregistré ne doit plus être appelé."""
        callback = MagicMock()
        self.registry.register(SchemaOperation.REGISTER, callback, when="post")

        removed = self.registry.unregister(SchemaOperation.REGISTER, callback, when="post")
        assert removed is True

        self.registry.execute(SchemaOperation.REGISTER, "post", {})
        callback.assert_not_called()

    def test_unregister_nonexistent_hook_returns_false(self):
        """Désenregistrer un hook non existant retourne False."""
        callback = MagicMock()
        result = self.registry.unregister(SchemaOperation.REGISTER, callback, when="post")
        assert result is False

    def test_clear_all_hooks(self):
        """clear() sans argument supprime tous les hooks."""
        callback = MagicMock()
        self.registry.register(SchemaOperation.REGISTER, callback, when="post")
        self.registry.register(SchemaOperation.DELETE, callback, when="pre")

        self.registry.clear()

        self.registry.execute(SchemaOperation.REGISTER, "post", {})
        self.registry.execute(SchemaOperation.DELETE, "pre", {})
        callback.assert_not_called()

    def test_clear_specific_operation(self):
        """clear(operation) ne supprime que les hooks de cette opération."""
        register_hook = MagicMock()
        delete_hook = MagicMock()
        self.registry.register(SchemaOperation.REGISTER, register_hook, when="post")
        self.registry.register(SchemaOperation.DELETE, delete_hook, when="post")

        self.registry.clear(SchemaOperation.REGISTER)

        self.registry.execute(SchemaOperation.REGISTER, "post", {})
        self.registry.execute(SchemaOperation.DELETE, "post", {})

        register_hook.assert_not_called()
        delete_hook.assert_called_once()

    def test_hook_error_isolation(self):
        """Une erreur dans un hook ne bloque pas les hooks suivants."""
        failing_hook = MagicMock(side_effect=RuntimeError("boom"))
        surviving_hook = MagicMock()

        self.registry.register(SchemaOperation.REGISTER, failing_hook, when="post")
        self.registry.register(SchemaOperation.REGISTER, surviving_hook, when="post")

        self.registry.execute(SchemaOperation.REGISTER, "post", {"name": "test"})

        failing_hook.assert_called_once()
        surviving_hook.assert_called_once()

    def test_get_hooks_returns_copy(self):
        """get_hooks() retourne une copie de la liste."""
        callback = MagicMock()
        self.registry.register(SchemaOperation.REGISTER, callback, when="post")

        hooks = self.registry.get_hooks(SchemaOperation.REGISTER, "post")
        assert len(hooks) == 1
        assert hooks[0] is callback

        # Modifier la copie ne doit pas affecter le registre
        hooks.clear()
        assert len(self.registry.get_hooks(SchemaOperation.REGISTER, "post")) == 1

    def test_invalid_when_raises_value_error(self):
        """Un timing invalide doit lever ValueError."""
        with pytest.raises(ValueError, match="'pre' ou 'post'"):
            self.registry.register(SchemaOperation.REGISTER, lambda ctx: None, when="invalid")

    def test_duplicate_registration_is_idempotent(self):
        """Enregistrer le même hook deux fois ne crée qu'une seule entrée."""
        callback = MagicMock()
        self.registry.register(SchemaOperation.REGISTER, callback, when="post")
        self.registry.register(SchemaOperation.REGISTER, callback, when="post")

        hooks = self.registry.get_hooks(SchemaOperation.REGISTER, "post")
        assert len(hooks) == 1
