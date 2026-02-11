import graphene
import pytest
from django.db import models
from types import SimpleNamespace
from unittest.mock import Mock, patch

from rail_django.core.schema.query_builder import QueryBuilderMixin
from rail_django.generators.mutations.generator import MutationGenerator
from rail_django.generators.types.generator import TypeGenerator


class PublishedManager(models.Manager):
    pass


class NamingContractModel(models.Model):
    name = models.CharField(max_length=64)
    objects = models.Manager()
    published = PublishedManager()

    class Meta:
        app_label = "test_naming_contract"


class MethodNamingModel(models.Model):
    name = models.CharField(max_length=64)

    class Meta:
        app_label = "test_naming_contract"

    def approve_item(self):
        return True


class DummyMutation(graphene.Mutation):
    ok = graphene.Boolean()

    class Arguments:
        id = graphene.ID(required=False)

    @classmethod
    def mutate(cls, *args, **kwargs):
        return cls(ok=True)


class DummyQueryBuilder(QueryBuilderMixin):
    def __init__(self):
        self.settings = SimpleNamespace(enable_pagination=True)
        self.schema_name = "default"
        self.query_generator = Mock()
        self._query_fields = {}

        self.query_generator.is_history_related_manager.return_value = False
        self.query_generator.get_manager_queryset_model.return_value = None
        self.query_generator.generate_single_query.return_value = graphene.Field(
            graphene.String
        )
        self.query_generator.generate_list_query.return_value = graphene.Field(
            graphene.String
        )
        self.query_generator.generate_grouping_query.return_value = graphene.Field(
            graphene.String
        )
        self.query_generator.generate_paginated_query.return_value = graphene.Field(
            graphene.String
        )


@pytest.mark.unit
def test_query_naming_contract_uses_model_list_page_group_and_manager_suffix():
    builder = DummyQueryBuilder()
    builder._generate_query_fields([NamingContractModel])

    generated = set(builder._query_fields.keys())

    assert "namingContractModel" in generated
    assert "namingContractModelList" in generated
    assert "namingContractModelPage" in generated
    assert "namingContractModelGroup" in generated

    assert "namingContractModelByPublished" in generated
    assert "namingContractModelListByPublished" in generated
    assert "namingContractModelPageByPublished" in generated
    assert "namingContractModelGroupByPublished" in generated

    assert "namingContractModels" not in generated
    assert "namingContractModelPages" not in generated
    assert "namingContractModelGroups" not in generated


@pytest.mark.unit
def test_mutation_naming_contract_uses_camel_contract_for_crud_bulk_and_methods():
    generator = MutationGenerator(type_generator=Mock(spec=TypeGenerator))

    generator.settings.enable_create = True
    generator.settings.enable_update = True
    generator.settings.enable_delete = True
    generator.settings.enable_bulk_operations = True
    generator.settings.generate_bulk = True
    generator.settings.enable_method_mutations = True

    with patch.object(generator, "generate_create_mutation", return_value=DummyMutation):
        with patch.object(
            generator, "generate_update_mutation", return_value=DummyMutation
        ):
            with patch.object(
                generator, "generate_delete_mutation", return_value=DummyMutation
            ):
                with patch.object(
                    generator,
                    "generate_bulk_create_mutation",
                    return_value=DummyMutation,
                ):
                    with patch.object(
                        generator,
                        "generate_bulk_update_mutation",
                        return_value=DummyMutation,
                    ):
                        with patch.object(
                            generator,
                            "generate_bulk_delete_mutation",
                            return_value=DummyMutation,
                        ):
                            with patch.object(
                                generator,
                                "generate_method_mutation",
                                return_value=DummyMutation,
                            ):
                                mutations = generator.generate_all_mutations(
                                    MethodNamingModel
                                )

    assert "createMethodNamingModel" in mutations
    assert "updateMethodNamingModel" in mutations
    assert "deleteMethodNamingModel" in mutations
    assert "bulkCreateMethodNamingModel" in mutations
    assert "bulkUpdateMethodNamingModel" in mutations
    assert "bulkDeleteMethodNamingModel" in mutations
    assert "approveItemMethodNamingModel" in mutations
