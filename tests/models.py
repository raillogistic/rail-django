from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class TestCompany(models.Model):
    nom_entreprise = models.CharField(max_length=200)
    secteur_activite = models.CharField(max_length=120)
    adresse_entreprise = models.CharField(max_length=255)
    email_entreprise = models.EmailField()
    nombre_employes = models.PositiveIntegerField(default=0)
    est_active = models.BooleanField(default=True)

    class Meta:
        app_label = "tests"
        verbose_name_plural = "companies"


class TestEmployee(models.Model):
    utilisateur_employe = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="test_employees"
    )
    entreprise_employe = models.ForeignKey(
        TestCompany, on_delete=models.CASCADE, related_name="employes"
    )
    poste_employe = models.CharField(max_length=120)
    salaire_employe = models.DecimalField(max_digits=10, decimal_places=2)
    date_embauche = models.DateField()
    est_manager = models.BooleanField(default=False)

    class Meta:
        app_label = "tests"
        verbose_name_plural = "employees"


class TestSkillCategory(models.Model):
    nom_categorie = models.CharField(max_length=120)
    description_categorie = models.TextField(blank=True)

    class Meta:
        app_label = "tests"
        verbose_name_plural = "skill categories"


class TestSkill(models.Model):
    nom_competence = models.CharField(max_length=120)
    description_competence = models.TextField(blank=True)
    niveau_requis = models.CharField(max_length=40)
    categorie_competence = models.ForeignKey(
        TestSkillCategory, on_delete=models.CASCADE, related_name="competences"
    )

    class Meta:
        app_label = "tests"
        verbose_name_plural = "skills"


class TestProject(models.Model):
    nom_projet = models.CharField(max_length=120)
    description_projet = models.TextField(blank=True)
    entreprise_projet = models.ForeignKey(
        TestCompany, on_delete=models.CASCADE, related_name="projects", null=True, blank=True
    )

    class Meta:
        app_label = "tests"
        verbose_name_plural = "projects"


class TestProjectAssignment(models.Model):
    projet = models.ForeignKey(
        TestProject, on_delete=models.CASCADE, related_name="assignments"
    )
    employe = models.ForeignKey(
        TestEmployee, on_delete=models.CASCADE, related_name="assignments"
    )
    role = models.CharField(max_length=120, blank=True)

    class Meta:
        app_label = "tests"
        verbose_name_plural = "project assignments"


class TestCustomer(models.Model):
    nom_client = models.CharField(max_length=120)
    prenom_client = models.CharField(max_length=120)
    email_client = models.EmailField(unique=True)
    telephone_client = models.CharField(max_length=50, blank=True)
    adresse_client = models.CharField(max_length=255, blank=True)
    ville_client = models.CharField(max_length=120, blank=True)
    code_postal = models.CharField(max_length=20, blank=True)
    pays_client = models.CharField(max_length=120, blank=True)
    solde_compte = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    est_actif = models.BooleanField(default=True)

    class Meta:
        app_label = "tests"
        verbose_name_plural = "customers"


class TestAccount(models.Model):
    numero_compte = models.CharField(max_length=50, unique=True)
    client_compte = models.ForeignKey(
        TestCustomer, on_delete=models.CASCADE, related_name="comptes_client"
    )
    type_compte = models.CharField(max_length=30)
    solde_compte = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    taux_interet = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    class Meta:
        app_label = "tests"
        verbose_name_plural = "accounts"

    def effectuer_virement(self, destination, montant):
        if montant < 0:
            raise ValueError("Transfer amount must be positive")
        if self.solde_compte < montant:
            raise ValueError("Insufficient balance")
        self.solde_compte -= montant
        destination.solde_compte += montant
        self.save()
        destination.save()
