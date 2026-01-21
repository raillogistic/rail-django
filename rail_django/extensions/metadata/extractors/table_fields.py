"""Table field extraction methods.

This module provides mixin classes for extracting table field and filter
metadata from Django models for data grid displays.
"""

import logging
from typing import Any, Optional

from django.db import models
from django.utils.encoding import force_str

from ..types import TableFieldMetadata
from .base import _build_field_permission_snapshot

logger = logging.getLogger(__name__)


class TableFieldExtractionMixin:
    """
    Mixin providing table field extraction functionality.

    This mixin should be used with BaseMetadataExtractor to provide
    table field extraction capabilities.
    """

    def _build_table_field_from_django_field(
        self, field, user=None
    ) -> Optional[TableFieldMetadata]:
        """
        Build table field metadata from a Django model field.

        Args:
            field: Django model field instance.
            user: Optional user for permission checking.

        Returns:
            TableFieldMetadata or None if user lacks permission.
        """
        field_type = field.__class__.__name__
        title = str(getattr(field, "verbose_name", field.name))
        help_text = str(getattr(field, "help_text", ""))
        is_related = isinstance(
            field, (models.ForeignKey, models.OneToOneField, models.ManyToManyField)
        )

        permission_snapshot = (
            _build_field_permission_snapshot(user, field.model, field.name)
            if user is not None
            else None
        )
        if permission_snapshot and not permission_snapshot.can_read:
            return None

        editable_flag = getattr(field, "editable", True)
        if permission_snapshot and not permission_snapshot.can_write:
            editable_flag = False

        return TableFieldMetadata(
            name=field.name,
            accessor=field.name,
            display=f"{field.name}.desc" if is_related else field.name,
            editable=editable_flag,
            field_type=field_type,
            filterable=True,
            sortable=True,
            title=title,
            help_text=help_text,
            is_property=False,
            is_related=is_related,
            permissions=permission_snapshot,
        )

    def _build_table_field_for_property(
        self,
        prop_name: str,
        return_type,
        verbose_name: Optional[str] = None,
    ) -> TableFieldMetadata:
        """
        Build table field metadata for a model property.

        Args:
            prop_name: Property name.
            return_type: Property return type annotation.
            verbose_name: Optional verbose name for display.

        Returns:
            TableFieldMetadata for the property.
        """
        import inspect
        from datetime import date, datetime, time
        from typing import Any, List, Union, get_args, get_origin

        def _to_graphql_str(py_type: Any) -> str:
            if py_type is Any or py_type is None or py_type is inspect._empty:
                return "String"

            base_map = {
                str: "String",
                int: "Int",
                float: "Float",
                bool: "Boolean",
                date: "Date",
                datetime: "DateTime",
                time: "Time",
            }

            if py_type in (dict,):
                return "JSON"

            origin = get_origin(py_type)
            if origin is Union:
                args = [arg for arg in get_args(py_type) if arg is not type(None)]
                return _to_graphql_str(args[0]) if args else "String"

            if origin is list:
                args = get_args(py_type)
                inner = _to_graphql_str(args[0]) if args else "String"
                return f"List[{inner}]"

            if origin in (dict,):
                return "JSON"

            return base_map.get(py_type, "String")

        field_type_str = _to_graphql_str(return_type)
        return TableFieldMetadata(
            name=prop_name,
            accessor=prop_name,
            display=prop_name,
            editable=False,
            field_type=field_type_str,
            filterable=True,
            sortable=True,
            title=str(verbose_name or prop_name),
            help_text=f"Computed property ({field_type_str})",
            is_property=True,
            is_related=False,
        )

    def _build_table_field_for_reverse_count(
        self, introspector, model
    ) -> list[TableFieldMetadata]:
        """
        Build count fields for reverse relationships.

        Args:
            introspector: Model introspector instance.
            model: Django model class.

        Returns:
            List of TableFieldMetadata for count fields.
        """
        counts = []
        reverse_relations = introspector.get_manytoone_relations()

        for rel_name, related_model in reverse_relations.items():
            counts.append(
                TableFieldMetadata(
                    name=f"{rel_name}_count",
                    accessor=f"{rel_name}_count",
                    display=f"{rel_name}_count",
                    editable=False,
                    field_type="Count",
                    filterable=True,
                    sortable=True,
                    title=f"Related items count ({rel_name})",
                    help_text=f"Number of related reverse objects ({rel_name})",
                    is_property=False,
                    is_related=False,
                )
            )

        for field in model._meta.get_fields():
            if isinstance(field, models.ManyToManyField):
                counts.append(
                    TableFieldMetadata(
                        name=f"{field.name}_count",
                        accessor=f"{field.name}_count",
                        display=f"{field.name}_count",
                        editable=False,
                        field_type="Count",
                        filterable=True,
                        sortable=True,
                        title=f"Related items count ({field.verbose_name})",
                        help_text=f"Number of related reverse objects ({field.verbose_name})",
                        is_property=False,
                        is_related=False,
                    )
                )

        return counts


class TableFilterExtractionMixin:
    """
    Mixin providing table filter extraction functionality.

    This mixin should be used with BaseMetadataExtractor to provide
    table filter extraction capabilities.
    """

    def _extract_table_filters(
        self,
        model,
        introspector,
        exclude: Optional[list[str]] = None,
        only: Optional[list[str]] = None,
        include_nested: bool = True,
        only_lookup: Optional[list[str]] = None,
        exclude_lookup: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """
        Extract filter metadata for table display.

        Args:
            model: Django model class.
            introspector: Model introspector instance.
            exclude: Field names to exclude from filters.
            only: Field names to exclusively include in filters.
            include_nested: Whether to include nested filter groups.
            only_lookup: Lookup expressions to include.
            exclude_lookup: Lookup expressions to exclude.

        Returns:
            List of grouped filter metadata dictionaries.
        """
        try:
            from ....generators.filter_inputs import AdvancedFilterGenerator

            filter_generator = AdvancedFilterGenerator(
                enable_nested_filters=True, schema_name=self.schema_name
            )
            filter_class = filter_generator.generate_filter_set(model)

            properties_dict = getattr(introspector, "properties", {}) or {}
            grouped_filter_dict: dict[str, dict[str, Any]] = {}
            base_filters = getattr(filter_class, "base_filters", {}) or {}

            for fname, finstance in base_filters.items():
                if (
                    "quick" in fname
                    or "_ptr" in fname
                    or "polymorphic_ctype" in fname
                    or "_id" in fname
                    or fname == "pk"
                    or fname == "id"
                ):
                    continue

                parts = fname.split("__")
                base_name = parts[0]

                if (
                    base_name == "id"
                    or base_name == "pk"
                    or "report_rows" in base_name
                    or "_snapshots" in base_name
                    or "_policies" in base_name
                ):
                    continue

                lookup_expr = "__".join(parts[1:]) or "exact"
                is_nested = (len(parts) > 2) and not fname.endswith("_count")
                group_key = base_name

                # Resolve field and labels
                field_obj = None
                verbose_name_val = group_key
                related_model_name = None

                try:
                    field_obj = model._meta.get_field(base_name)
                    if getattr(field_obj, "related_model", None):
                        related_model_name = field_obj.related_model.__name__
                        rel_meta = field_obj.related_model._meta
                        verbose_name_val = str(
                            getattr(rel_meta, "verbose_name_plural", None)
                            or getattr(rel_meta, "verbose_name", base_name)
                        )
                    else:
                        verbose_name_val = str(
                            getattr(field_obj, "verbose_name", base_name)
                        )
                except Exception:
                    prop_info = properties_dict.get(base_name)
                    if prop_info is not None:
                        verbose_name_val = (
                            getattr(
                                getattr(prop_info, "fget", None),
                                "short_description",
                                None,
                            )
                            or getattr(prop_info, "verbose_name", None)
                            or base_name
                        )

                # Compute choices for CharField choices
                option_choices = None
                try:
                    if field_obj is not None and isinstance(
                        field_obj, models.CharField
                    ):
                        raw_choices = getattr(field_obj, "choices", None)
                        if raw_choices and lookup_expr in ("exact", "in"):
                            option_choices = [
                                {
                                    "value": self._json_safe_value(val),
                                    "label": force_str(lbl),
                                }
                                for val, lbl in raw_choices
                            ]
                except Exception:
                    option_choices = None

                # Initialize group
                if group_key not in grouped_filter_dict:
                    grouped_filter_dict[group_key] = {
                        "field_name": group_key,
                        "is_nested": False,
                        "related_model": related_model_name,
                        "is_custom": False,
                        "field_label": verbose_name_val,
                        "options": [],
                        "nested": [],
                        "_seen_parent": set(),
                    }

                # Build option
                option = {
                    "name": fname if lookup_expr != "exact" else base_name,
                    "lookup_expr": lookup_expr,
                    "help_text": self._translate_help_text_to_french(
                        lookup_expr, verbose_name_val
                    ),
                    "filter_type": finstance.__class__.__name__,
                    "choices": option_choices,
                }

                if not is_nested:
                    seen_parent = grouped_filter_dict[group_key]["_seen_parent"]
                    key = lookup_expr
                    if key not in seen_parent:
                        grouped_filter_dict[group_key]["options"].append(option)
                        seen_parent.add(key)

            # Finalize
            filters = []
            for gval in grouped_filter_dict.values():
                gval.pop("_seen_parent", None)
                opts = list(gval.get("options") or [])
                if opts:
                    opts.sort(
                        key=lambda o: 0 if o.get("lookup_expr") == "exact" else 1
                    )
                    gval["options"] = opts
                filters.append(gval)

            # Apply selection filters
            filters = self._apply_filter_selection(
                filters,
                only_fields=only or [],
                exclude_fields=exclude or [],
                include_nested_val=include_nested,
                only_lk=only_lookup or [],
                exclude_lk=exclude_lookup or [],
            )

            return filters

        except Exception as e:
            logger.warning(f"Error extracting filters for {model.__name__}: {e}")
            return []

    def _apply_filter_selection(
        self,
        filters_in: list[dict[str, Any]],
        only_fields: Optional[list[str]] = None,
        exclude_fields: Optional[list[str]] = None,
        include_nested_val: bool = True,
        only_lk: Optional[list[str]] = None,
        exclude_lk: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """
        Filter the computed filters according to selection variables.

        Args:
            filters_in: List of grouped filter dicts.
            only_fields: Field names to include.
            exclude_fields: Field names to exclude.
            include_nested_val: Whether to include nested groups.
            only_lk: Lookup expressions to include.
            exclude_lk: Lookup expressions to exclude.

        Returns:
            Filter list after applying selection rules.
        """
        only_fields_set = set(only_fields or [])
        exclude_fields_set = set(exclude_fields or [])
        only_lk_set = set(only_lk or [])
        exclude_lk_set = set(exclude_lk or [])

        result: list[dict[str, Any]] = []

        for grp in filters_in:
            parent_name = grp.get("field_name")

            if parent_name in exclude_fields_set:
                continue

            include_parent = True
            if only_fields_set:
                include_parent = parent_name in only_fields_set or any(
                    (nested.get("field_name") in only_fields_set)
                    for nested in (grp.get("nested") or [])
                )
            if not include_parent:
                continue

            new_grp = dict(grp)

            # Apply lookup filters to options
            opts = list(new_grp.get("options") or [])
            if only_lk_set:
                opts = [o for o in opts if o.get("lookup_expr") in only_lk_set]
            if exclude_lk_set:
                opts = [o for o in opts if o.get("lookup_expr") not in exclude_lk_set]
            if opts:
                opts.sort(key=lambda o: 0 if o.get("lookup_expr") == "exact" else 1)
            new_grp["options"] = opts

            # Handle nested
            nested_list = list(new_grp.get("nested") or [])
            if not include_nested_val:
                if only_fields_set:
                    nested_list = [
                        n for n in nested_list
                        if n.get("field_name") in only_fields_set
                    ]
                else:
                    nested_list = []

            if only_fields_set:
                nested_list = [
                    n for n in nested_list if n.get("field_name") in only_fields_set
                ]
            if exclude_fields_set:
                nested_list = [
                    n for n in nested_list
                    if n.get("field_name") not in exclude_fields_set
                ]

            for n in nested_list:
                n_opts = list(n.get("options") or [])
                if only_lk_set:
                    n_opts = [
                        o for o in n_opts if o.get("lookup_expr") in only_lk_set
                    ]
                if exclude_lk_set:
                    n_opts = [
                        o for o in n_opts if o.get("lookup_expr") not in exclude_lk_set
                    ]
                if n_opts:
                    n_opts.sort(
                        key=lambda o: 0 if o.get("lookup_expr") == "exact" else 1
                    )
                n["options"] = n_opts

            new_grp["nested"] = nested_list
            result.append(new_grp)

        return result


__all__ = ["TableFieldExtractionMixin", "TableFilterExtractionMixin"]
