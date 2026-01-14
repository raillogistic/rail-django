from django.db import models


class Category(models.Model):
    nom_categorie = models.CharField(max_length=120)

    class Meta:
        app_label = "examples"
        verbose_name_plural = "categories"


class Post(models.Model):
    titre_article = models.CharField(max_length=200)
    categorie_article = models.ForeignKey(Category, on_delete=models.CASCADE)

    class Meta:
        app_label = "examples"
        verbose_name_plural = "posts"
