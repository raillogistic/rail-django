"""
DataLoader helpers for reverse relations.
"""

from typing import Optional, Type

from django.db import models

try:
    from promise import Promise
    from promise.dataloader import DataLoader
except Exception:
    Promise = None
    DataLoader = None


if DataLoader:

    class RelatedObjectsLoader(DataLoader):
        """Batch loader for reverse foreign key relations."""

        def __init__(
            self,
            related_model: type[models.Model],
            relation_field: str,
            db_alias: Optional[str] = None,
        ):
            super().__init__()
            self.related_model = related_model
            self.relation_field = relation_field
            self.db_alias = db_alias

        def batch_load_fn(self, keys):
            if Promise is None:
                return keys

            results_map = {key: [] for key in keys}
            if not keys:
                return Promise.resolve([[] for _ in keys])

            filter_kwargs = {f"{self.relation_field}__in": keys}
            queryset = self.related_model._default_manager.using(self.db_alias).filter(
                **filter_kwargs
            )

            for obj in queryset:
                key = getattr(obj, f"{self.relation_field}_id", None)
                if key is None:
                    try:
                        key = getattr(obj, self.relation_field).pk
                    except Exception:
                        key = None
                results_map.setdefault(key, []).append(obj)

            return Promise.resolve([results_map.get(key, []) for key in keys])

else:
    RelatedObjectsLoader = None
