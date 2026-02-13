from django.db import models
from django.test import TestCase
from types import SimpleNamespace

from rail_django.extensions.form.extractors.base import FormConfigExtractor
from rail_django.extensions.metadata.extractor import ModelSchemaExtractor


class LabelProduct(models.Model):
    class Meta:
        app_label = "test_relation_labels"
        verbose_name = "Produit"
        verbose_name_plural = "Produits"


class LabelOrderItem(models.Model):
    product = models.ForeignKey(
        LabelProduct,
        on_delete=models.CASCADE,
        related_name="order_items",
        verbose_name="Produit/Ordres",
    )

    class Meta:
        app_label = "test_relation_labels"
        verbose_name = "Ordre"
        verbose_name_plural = "Ordres"


class FallbackCustomer(models.Model):
    class Meta:
        app_label = "test_relation_labels"
        verbose_name = "Client"
        verbose_name_plural = "Clients"


class FallbackPurchase(models.Model):
    customer = models.ForeignKey(
        FallbackCustomer,
        on_delete=models.CASCADE,
        related_name="purchase_rows",
        verbose_name="Client",
    )

    class Meta:
        app_label = "test_relation_labels"
        verbose_name = "Achat"
        verbose_name_plural = "Achats"


class FallbackAccount(models.Model):
    class Meta:
        app_label = "test_relation_labels"
        verbose_name = "Compte"
        verbose_name_plural = "Comptes"


class FallbackAccountProfile(models.Model):
    account = models.OneToOneField(
        FallbackAccount,
        on_delete=models.CASCADE,
        related_name="profile_data",
        verbose_name="Compte",
    )

    class Meta:
        app_label = "test_relation_labels"
        verbose_name = "Profil"
        verbose_name_plural = "Profils"


class TestRelationLabels(TestCase):
    @staticmethod
    def _build_reverse_field(
        *,
        accessor_name: str,
        source_verbose_name: str,
        many_to_many: bool = False,
        one_to_many: bool = True,
        one_to_one: bool = False,
    ):
        return SimpleNamespace(
            name=accessor_name,
            auto_created=True,
            many_to_many=many_to_many,
            one_to_many=one_to_many,
            one_to_one=one_to_one,
            verbose_name=accessor_name,
            field=SimpleNamespace(verbose_name=source_verbose_name),
            get_accessor_name=lambda: accessor_name,
        )

    def test_form_forward_relation_uses_left_side_of_split_verbose_name(self):
        extractor = FormConfigExtractor()
        relations = extractor._extract_relations(LabelOrderItem, user=None)

        product_relation = next(
            rel for rel in relations if rel["field_name"] == "product"
        )
        self.assertEqual(product_relation["label"], "Produit")

    def test_form_reverse_relation_uses_right_side_of_split_verbose_name(self):
        extractor = FormConfigExtractor()
        reverse_field = self._build_reverse_field(
            accessor_name="order_items",
            source_verbose_name="Produit/Ordres",
        )

        label = extractor._get_relation_label(
            field=reverse_field,
            related_model=LabelOrderItem,
            is_reverse=True,
        )
        self.assertEqual(label, "Ordres")

    def test_form_reverse_relation_falls_back_to_related_plural_for_many(self):
        extractor = FormConfigExtractor()
        reverse_field = self._build_reverse_field(
            accessor_name="purchase_rows",
            source_verbose_name="Client",
            one_to_many=True,
        )

        label = extractor._get_relation_label(
            field=reverse_field,
            related_model=FallbackPurchase,
            is_reverse=True,
        )
        self.assertEqual(label, "Achats")

    def test_form_reverse_relation_falls_back_to_related_verbose_for_one_to_one(self):
        extractor = FormConfigExtractor()
        reverse_field = self._build_reverse_field(
            accessor_name="profile_data",
            source_verbose_name="Compte",
            one_to_many=False,
            one_to_one=True,
        )

        label = extractor._get_relation_label(
            field=reverse_field,
            related_model=FallbackAccountProfile,
            is_reverse=True,
        )
        self.assertEqual(label, "Profil")

    def test_form_reverse_relation_last_fallback_removes_underscores(self):
        extractor = FormConfigExtractor()
        reverse_field = self._build_reverse_field(
            accessor_name="order_items",
            source_verbose_name="Order items",
            one_to_many=False,
            one_to_one=False,
        )

        label = extractor._get_relation_label(
            field=reverse_field,
            related_model=FallbackPurchase,
            is_reverse=True,
        )
        self.assertEqual(label, "orderitems")

    def test_metadata_forward_relation_uses_left_side_of_split_verbose_name(self):
        extractor = ModelSchemaExtractor()
        relations = extractor._extract_relationships(LabelOrderItem, user=None)

        product_relation = next(
            rel for rel in relations if rel["field_name"] == "product"
        )
        self.assertEqual(product_relation["verbose_name"], "Produit")

    def test_metadata_reverse_relation_uses_right_side_of_split_verbose_name(self):
        extractor = ModelSchemaExtractor()
        reverse_field = self._build_reverse_field(
            accessor_name="order_items",
            source_verbose_name="Produit/Ordres",
        )

        label = extractor._get_relationship_label(
            field=reverse_field,
            related_model=LabelOrderItem,
            is_reverse=True,
        )
        self.assertEqual(label, "Ordres")
