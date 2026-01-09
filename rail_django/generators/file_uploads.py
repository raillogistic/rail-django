"""
Générateur de mutations pour les téléchargements de fichiers et la gestion des médias.

Ce module fournit des fonctionnalités automatiques pour :
- Génération de mutations de téléchargement de fichiers
- Validation des types et tailles de fichiers
- Intégration avec les systèmes de stockage
- Traitement et optimisation des médias
"""

import hashlib
import mimetypes
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, Union

import graphene
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile
from django.db import models
from django.utils.text import slugify
from graphene import Boolean, Field, Int
from graphene import List as GrapheneList
from graphene import Mutation, ObjectType, String
from graphene_file_upload.scalars import Upload

from ..core.settings import GraphQLAutoConfig


class ThreatDetected(Exception):
    """Exception levée quand une menace est détectée dans un fichier."""
    pass


class ScanResult:
    """Résultat d'un scan antivirus."""

    def __init__(self, is_clean: bool = True, threat_name: str = None):
        """
        Initialise le résultat du scan.

        Args:
            is_clean: Indique si le fichier est propre
            threat_name: Nom de la menace détectée (si applicable)
        """
        self.is_clean = is_clean
        self.threat_name = threat_name


class FileValidationError(Exception):
    """Exception levée lors de la validation des fichiers."""
    pass


class FileInfo(graphene.ObjectType):
    """Informations sur un fichier téléchargé."""

    id = graphene.String(description="Identifiant unique du fichier")
    name = graphene.String(description="Nom original du fichier")
    size = graphene.Int(description="Taille du fichier en octets")
    content_type = graphene.String(description="Type MIME du fichier")
    url = graphene.String(description="URL d'accès au fichier")
    path = graphene.String(description="Chemin de stockage du fichier")
    checksum = graphene.String(description="Somme de contrôle MD5 du fichier")
    uploaded_at = graphene.DateTime(description="Date et heure de téléchargement")
    extension = graphene.String(description="Extension du fichier")

    def __init__(self, name=None, size=None, content_type=None, extension=None,
                 url=None, path=None, checksum=None, uploaded_at=None, id=None, **kwargs):
        """Initialise un objet FileInfo."""
        super().__init__(**kwargs)
        self.name = name
        self.size = size
        self.content_type = content_type
        self.extension = extension
        self.url = url
        self.path = path
        self.checksum = checksum
        self.uploaded_at = uploaded_at
        self.id = id or str(uuid.uuid4())

    @classmethod
    def from_uploaded_file(cls, uploaded_file: Union[InMemoryUploadedFile, TemporaryUploadedFile]):
        """
        Crée un FileInfo à partir d'un fichier téléchargé.

        Args:
            uploaded_file: Fichier téléchargé Django

        Returns:
            FileInfo: Instance avec les informations du fichier
        """
        # Extraire l'extension du nom de fichier
        extension = Path(uploaded_file.name).suffix if uploaded_file.name else ""

        return cls(
            name=uploaded_file.name,
            size=uploaded_file.size,
            content_type=uploaded_file.content_type,
            extension=extension,
            uploaded_at=datetime.now()
        )


class FileUploadResult(graphene.ObjectType):
    """Résultat d'un téléchargement de fichier."""

    success = graphene.Boolean(description="Indique si le téléchargement a réussi")
    file_info = graphene.Field(FileInfo, description="Informations sur le fichier téléchargé")
    error_message = graphene.String(description="Message d'erreur en cas d'échec")

    # Compatibilité avec l'ancienne interface
    ok = graphene.Boolean(description="Indique si le téléchargement a réussi")
    file = graphene.Field(FileInfo, description="Informations sur le fichier téléchargé")
    errors = graphene.List(graphene.String, description="Liste des erreurs rencontrées")

    def __init__(self, success=None, file_info=None, error_message=None,
                 ok=None, file=None, errors=None, **kwargs):
        """
        Initialise le résultat du téléchargement.

        Args:
            success: Indique si le téléchargement a réussi (nouvelle interface)
            file_info: Informations sur le fichier (nouvelle interface)
            error_message: Message d'erreur (nouvelle interface)
            ok: Indique si le téléchargement a réussi (ancienne interface)
            file: Informations sur le fichier (ancienne interface)
            errors: Liste des erreurs (ancienne interface)
        """
        super().__init__(**kwargs)
        # Nouvelle interface
        self.success = success if success is not None else ok
        self.file_info = file_info if file_info is not None else file
        self.error_message = error_message

        # Ancienne interface pour compatibilité
        self.ok = ok if ok is not None else success
        self.file = file if file is not None else file_info
        self.errors = errors or ([error_message] if error_message else [])


class MultipleFileUploadResult(graphene.ObjectType):
    """Résultat d'un téléchargement multiple de fichiers."""

    success = graphene.Boolean(description="Indique si tous les téléchargements ont réussi")
    file_infos = graphene.List(
        FileInfo, description="Liste des informations sur les fichiers téléchargés")
    error_message = graphene.String(description="Messages d'erreur en cas d'échec")

    # Compatibilité avec l'ancienne interface
    ok = graphene.Boolean(description="Indique si tous les téléchargements ont réussi")
    files = graphene.List(FileInfo, description="Liste des fichiers téléchargés avec succès")
    errors = graphene.List(graphene.String, description="Liste des erreurs rencontrées")

    def __init__(self, success=None, file_infos=None, error_message=None,
                 ok=None, files=None, errors=None, **kwargs):
        """
        Initialise le résultat du téléchargement multiple.

        Args:
            success: Indique si tous les téléchargements ont réussi (nouvelle interface)
            file_infos: Liste des informations sur les fichiers (nouvelle interface)
            error_message: Messages d'erreur (nouvelle interface)
            ok: Indique si tous les téléchargements ont réussi (ancienne interface)
            files: Liste des fichiers (ancienne interface)
            errors: Liste des erreurs (ancienne interface)
        """
        super().__init__(**kwargs)
        # Nouvelle interface
        self.success = success if success is not None else ok
        self.file_infos = file_infos if file_infos is not None else files
        self.error_message = error_message

        # Ancienne interface pour compatibilité
        self.ok = ok if ok is not None else success
        self.files = files if files is not None else file_infos
        self.errors = errors or ([error_message] if error_message else [])
    failed_count = graphene.Int(description="Nombre de fichiers qui ont échoué")
    success_count = graphene.Int(description="Nombre de fichiers téléchargés avec succès")


class FileValidator:
    """Validateur pour les fichiers téléchargés."""

    def __init__(self, settings: GraphQLAutoConfig):
        self.settings = settings
        self.allowed_types = getattr(settings, 'ALLOWED_FILE_TYPES', [
            'image/jpeg', 'image/png', 'image/gif', 'image/webp',
            'application/pdf', 'text/plain', 'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        ])
        self.max_file_size = getattr(settings, 'MAX_FILE_SIZE', 10 * 1024 * 1024)  # 10MB par défaut
        self.max_total_size = getattr(settings, 'MAX_TOTAL_UPLOAD_SIZE',
                                      100 * 1024 * 1024)  # 100MB par défaut

    def validate_file_type(self, file_info: FileInfo, allowed_types: List[str]) -> None:
        """
        Valide le type MIME d'un fichier.

        Args:
            file_info: Informations sur le fichier
            allowed_types: Liste des types MIME autorisés

        Raises:
            FileValidationError: Si le type de fichier n'est pas autorisé
        """
        if file_info.content_type not in allowed_types:
            raise FileValidationError(
                f"Type de fichier non autorisé: {file_info.content_type}. "
                f"Types autorisés: {', '.join(allowed_types)}"
            )

    def validate_file_extension(self, file_info: FileInfo, allowed_extensions: List[str]) -> None:
        """
        Valide l'extension d'un fichier.

        Args:
            file_info: Informations sur le fichier
            allowed_extensions: Liste des extensions autorisées

        Raises:
            FileValidationError: Si l'extension n'est pas autorisée
        """
        if file_info.extension not in allowed_extensions:
            raise FileValidationError(
                f"Extension de fichier non autorisée: {file_info.extension}. "
                f"Extensions autorisées: {', '.join(allowed_extensions)}"
            )

    def validate_file(self, file: Union[InMemoryUploadedFile, TemporaryUploadedFile]) -> None:
        """
        Valide un fichier téléchargé.

        Args:
            file: Fichier à valider

        Raises:
            FileValidationError: Si le fichier ne respecte pas les critères de validation
        """
        # Validation de la taille
        if file.size > self.max_file_size:
            raise FileValidationError(
                f"Le fichier '{file.name}' est trop volumineux. "
                f"Taille maximale autorisée : {self.max_file_size / (1024*1024):.1f}MB"
            )

        # Validation du type MIME
        content_type = file.content_type or mimetypes.guess_type(file.name)[0]
        if content_type not in self.allowed_types:
            raise FileValidationError(
                f"Type de fichier non autorisé : {content_type}. "
                f"Types autorisés : {', '.join(self.allowed_types)}"
            )

        # Validation du nom de fichier
        if not file.name or len(file.name) > 255:
            raise FileValidationError("Nom de fichier invalide ou trop long")

        # Vérification des caractères dangereux dans le nom
        dangerous_chars = ['..', '/', '\\', '<', '>', ':', '"', '|', '?', '*']
        if any(char in file.name for char in dangerous_chars):
            raise FileValidationError("Le nom de fichier contient des caractères non autorisés")

    def validate_multiple_files(self, files: List[Union[InMemoryUploadedFile, TemporaryUploadedFile]]) -> None:
        """
        Valide une liste de fichiers téléchargés.

        Args:
            files: Liste des fichiers à valider

        Raises:
            FileValidationError: Si les fichiers ne respectent pas les critères de validation
        """
        if not files:
            raise FileValidationError("Aucun fichier fourni")

        total_size = sum(file.size for file in files)
        if total_size > self.max_total_size:
            raise FileValidationError(
                f"Taille totale des fichiers trop importante. "
                f"Taille maximale autorisée : {self.max_total_size / (1024*1024):.1f}MB"
            )

        for file in files:
            self.validate_file(file)

    def validate_file_size(self, file: Union[InMemoryUploadedFile, TemporaryUploadedFile], max_size: int = None) -> bool:
        """
        Valide uniquement la taille d'un fichier.

        Args:
            file: Fichier à valider
            max_size: Taille maximale personnalisée (optionnelle)

        Returns:
            bool: True si la taille est valide

        Raises:
            FileValidationError: Si le fichier est trop volumineux
        """
        size_limit = max_size if max_size is not None else self.max_file_size
        if file.size > size_limit:
            raise FileValidationError(
                f"fichier de taille trop importante: {file.size} bytes (limite: {size_limit} bytes)")
        return True


class FileProcessor:
    """Processeur pour les fichiers téléchargés."""

    def __init__(self, settings: GraphQLAutoConfig):
        self.settings = settings
        self.upload_path = getattr(settings, 'UPLOAD_PATH', 'uploads/')

    def generate_file_path(self, file: Union[InMemoryUploadedFile, TemporaryUploadedFile]) -> str:
        """
        Génère un chemin unique pour le fichier.

        Args:
            file: Fichier téléchargé

        Returns:
            str: Chemin unique pour le fichier
        """
        # Génération d'un nom unique
        file_extension = Path(file.name).suffix.lower()
        unique_name = f"{uuid.uuid4().hex}{file_extension}"

        # Organisation par date
        now = datetime.now()
        date_path = f"{now.year}/{now.month:02d}/{now.day:02d}"

        return f"{self.upload_path}{date_path}/{unique_name}"

    def calculate_checksum(self, file: Union[InMemoryUploadedFile, TemporaryUploadedFile]) -> str:
        """
        Calcule la somme de contrôle MD5 du fichier.

        Args:
            file: Fichier téléchargé

        Returns:
            str: Somme de contrôle MD5
        """
        md5_hash = hashlib.md5()

        # Lecture du fichier par chunks pour économiser la mémoire
        file.seek(0)
        for chunk in iter(lambda: file.read(4096), b""):
            md5_hash.update(chunk)
        file.seek(0)

        return md5_hash.hexdigest()

    def save_file(self, file: Union[InMemoryUploadedFile, TemporaryUploadedFile]) -> FileInfo:
        """
        Sauvegarde un fichier et retourne ses informations.

        Args:
            file: Fichier à sauvegarder

        Returns:
            FileInfo: Informations sur le fichier sauvegardé
        """
        file_path = self.generate_file_path(file)
        checksum = self.calculate_checksum(file)

        # Sauvegarde du fichier
        saved_path = default_storage.save(file_path, file)
        file_url = default_storage.url(saved_path)

        return FileInfo(
            id=str(uuid.uuid4()),
            name=file.name,
            size=file.size,
            content_type=file.content_type,
            url=file_url,
            path=saved_path,
            checksum=checksum,
            uploaded_at=datetime.now()
        )

    def process_uploaded_file(self, uploaded_file: Union[InMemoryUploadedFile, TemporaryUploadedFile]) -> FileInfo:
        """
        Traite un fichier téléchargé et retourne ses informations.

        Args:
            uploaded_file: Fichier téléchargé

        Returns:
            FileInfo: Informations sur le fichier traité
        """
        return self.save_file(uploaded_file)


class FileUploadGenerator:
    """Générateur de mutations pour les téléchargements de fichiers."""

    def __init__(self, settings: GraphQLAutoConfig):
        self.settings = settings
        self.validator = FileValidator(settings)
        self.processor = FileProcessor(settings)

    def generate_single_upload_mutation(self) -> Type[Mutation]:
        """
        Génère une mutation pour télécharger un seul fichier.

        Returns:
            Type[Mutation]: Classe de mutation pour téléchargement simple
        """
        validator = self.validator
        processor = self.processor

        class SingleFileUpload(Mutation):
            """Mutation pour télécharger un seul fichier."""

            class Arguments:
                file = Upload(required=True, description="Fichier à télécharger")
                description = String(description="Description optionnelle du fichier")

            Output = FileUploadResult

            @staticmethod
            def mutate(root, info, file, description=None):
                """
                Exécute le téléchargement d'un fichier.

                Args:
                    root: Objet racine GraphQL
                    info: Informations de contexte GraphQL
                    file: Fichier téléchargé
                    description: Description optionnelle

                Returns:
                    FileUploadResult: Résultat du téléchargement
                """
                try:
                    # Validation du fichier
                    validator.validate_file(file)

                    # Traitement et sauvegarde
                    file_info = processor.save_file(file)

                    return FileUploadResult(
                        ok=True,
                        file=file_info,
                        errors=[]
                    )

                except FileValidationError as e:
                    return FileUploadResult(
                        ok=False,
                        file=None,
                        errors=[str(e)]
                    )
                except Exception as e:
                    return FileUploadResult(
                        ok=False,
                        file=None,
                        errors=[f"Erreur lors du téléchargement : {str(e)}"]
                    )

        return SingleFileUpload

    def generate_multiple_upload_mutation(self) -> Type[Mutation]:
        """
        Génère une mutation pour télécharger plusieurs fichiers.

        Returns:
            Type[Mutation]: Classe de mutation pour téléchargement multiple
        """
        validator = self.validator
        processor = self.processor

        class MultipleFileUpload(Mutation):
            """Mutation pour télécharger plusieurs fichiers."""

            class Arguments:
                files = GrapheneList(Upload, required=True,
                                     description="Liste des fichiers à télécharger")
                description = String(description="Description optionnelle des fichiers")

            Output = MultipleFileUploadResult

            @staticmethod
            def mutate(root, info, files, description=None):
                """
                Exécute le téléchargement de plusieurs fichiers.

                Args:
                    root: Objet racine GraphQL
                    info: Informations de contexte GraphQL
                    files: Liste des fichiers téléchargés
                    description: Description optionnelle

                Returns:
                    MultipleFileUploadResult: Résultat du téléchargement multiple
                """
                uploaded_files = []
                errors = []

                try:
                    # Validation globale
                    validator.validate_multiple_files(files)

                    # Traitement de chaque fichier
                    for file in files:
                        try:
                            file_info = processor.save_file(file)
                            uploaded_files.append(file_info)
                        except Exception as e:
                            errors.append(f"Erreur pour le fichier '{file.name}': {str(e)}")

                    success_count = len(uploaded_files)
                    failed_count = len(files) - success_count

                    return MultipleFileUploadResult(
                        ok=failed_count == 0,
                        files=uploaded_files,
                        errors=errors,
                        success_count=success_count,
                        failed_count=failed_count
                    )

                except FileValidationError as e:
                    return MultipleFileUploadResult(
                        ok=False,
                        files=[],
                        errors=[str(e)],
                        success_count=0,
                        failed_count=len(files) if files else 0
                    )
                except Exception as e:
                    return MultipleFileUploadResult(
                        ok=False,
                        files=[],
                        errors=[f"Erreur lors du téléchargement multiple : {str(e)}"],
                        success_count=0,
                        failed_count=len(files) if files else 0
                    )

        return MultipleFileUpload

    def generate_file_mutations(self) -> Dict[str, Type[Mutation]]:
        """
        Génère toutes les mutations de fichiers.

        Returns:
            Dict[str, Type[Mutation]]: Dictionnaire des mutations générées
        """
        mutations = {}

        # Mutation de téléchargement simple
        mutations['upload_file'] = self.generate_single_upload_mutation()

        # Mutation de téléchargement multiple
        mutations['upload_files'] = self.generate_multiple_upload_mutation()

        return mutations

    def process_single_file_upload(self, file: Union[InMemoryUploadedFile, TemporaryUploadedFile], model_class, user, additional_fields: dict = None, max_file_size: int = None) -> FileUploadResult:
        """
        Traite le téléchargement d'un seul fichier.

        Args:
            file: Fichier téléchargé
            model_class: Classe du modèle Django pour sauvegarder le fichier
            user: Utilisateur effectuant le téléchargement
            additional_fields: Champs additionnels pour le traitement

        Returns:
            FileUploadResult: Résultat du téléchargement
        """
        try:
            # Scan antivirus
            scanner = VirusScanner()
            scanner.scan_uploaded_file(file)

            # Validation du fichier avec taille personnalisée si fournie
            if max_file_size:
                self.validator.validate_file_size(file, max_file_size)
            else:
                self.validator.validate_file(file)

            # Création de FileInfo à partir du fichier téléchargé
            file_info = FileInfo.from_uploaded_file(file)

            # Traitement et sauvegarde
            processed_file = self.processor.save_file(file)

            return FileUploadResult(
                success=True,
                file_info=file_info,
                error_message=None
            )

        except ThreatDetected as e:
            return FileUploadResult(
                success=False,
                file_info=None,
                error_message=str(e)
            )
        except FileValidationError as e:
            return FileUploadResult(
                success=False,
                file_info=None,
                error_message=str(e)
            )
        except Exception as e:
            return FileUploadResult(
                success=False,
                file_info=None,
                error_message=f"Erreur lors du téléchargement : {str(e)}"
            )

    def generate_single_file_upload_mutation(self, model_class=None) -> str:
        """
        Génère le code d'une mutation pour téléchargement simple.

        Args:
            model_class: Classe de modèle (pour compatibilité avec les tests)

        Returns:
            str: Code de la mutation générée
        """
        model_name = model_class.__name__.replace('Model', '') if model_class else "File"

        return f"""
class Upload{model_name}File(graphene.Mutation):
    \"\"\"Mutation pour télécharger un fichier {model_name}.\"\"\"
    
    class Arguments:
        file = Upload()
        description = String()
    
    Output = FileUploadResult
    
    @staticmethod
    def mutate(root, info, file, description=None):
        \"\"\"Exécute le téléchargement d'un fichier.\"\"\"
        try:
            # Validation et traitement du fichier
            validator = FileValidator(settings)
            validator.validate_file(file)
            
            processor = FileProcessor(settings)
            file_info = processor.save_file(file)
            
            return FileUploadResult(
                success=True,
                file_info=file_info,
                error_message=None
            )
            
        except FileValidationError as e:
            return FileUploadResult(
                success=False,
                file_info=None,
                error_message=str(e)
            )
"""

    def process_multiple_file_upload(self, files: List[Union[InMemoryUploadedFile, TemporaryUploadedFile]], model_class, user, additional_fields: dict = None) -> MultipleFileUploadResult:
        """
        Traite le téléchargement de plusieurs fichiers.

        Args:
            files: Liste des fichiers téléchargés
            model_class: Classe du modèle Django pour sauvegarder les fichiers
            user: Utilisateur effectuant le téléchargement
            additional_fields: Champs additionnels pour le traitement

        Returns:
            MultipleFileUploadResult: Résultat du téléchargement multiple
        """
        file_infos = []
        errors = []

        for file in files:
            try:
                # Scan antivirus
                scanner = VirusScanner()
                scanner.scan_uploaded_file(file)

                # Validation du fichier
                self.validator.validate_file(file)

                # Création de FileInfo à partir du fichier téléchargé
                file_info = FileInfo.from_uploaded_file(file)
                file_infos.append(file_info)

                # Traitement et sauvegarde
                processed_file = self.processor.save_file(file)

            except (ThreatDetected, FileValidationError) as e:
                errors.append(f"Erreur pour le fichier '{file.name}': {str(e)}")
            except Exception as e:
                errors.append(f"Erreur inattendue pour le fichier '{file.name}': {str(e)}")

        return MultipleFileUploadResult(
            success=len(errors) == 0,
            file_infos=file_infos,
            error_message="; ".join(errors) if errors else None
        )

    def process_uploaded_file(self, uploaded_file: Union[InMemoryUploadedFile, TemporaryUploadedFile]) -> FileInfo:
        """
        Traite un fichier téléchargé et retourne ses informations.

        Args:
            uploaded_file: Fichier téléchargé

        Returns:
            FileInfo: Informations sur le fichier traité
        """
        return FileInfo.from_uploaded_file(uploaded_file)

    def generate_multiple_file_upload_mutation(self, model_class=None) -> str:
        """
        Génère le code d'une mutation pour téléchargement multiple.

        Args:
            model_class: Classe de modèle (pour compatibilité avec les tests)

        Returns:
            str: Code de la mutation générée
        """
        model_name = model_class.__name__.replace('Model', '') if model_class else "File"

        return f"""
class UploadMultiple{model_name}Files(graphene.Mutation):
    \"\"\"Mutation pour télécharger plusieurs fichiers {model_name}.\"\"\"
    
    class Arguments:
        files = List(Upload)
        description = String()
    
    Output = MultipleFileUploadResult
    
    @staticmethod
    def mutate(root, info, files, description=None):
        \"\"\"Exécute le téléchargement de plusieurs fichiers.\"\"\"
        try:
            # Validation et traitement des fichiers
            validator = FileValidator(settings)
            processor = FileProcessor(settings)
            
            file_infos = []
            for file in files:
                validator.validate_file(file)
                file_info = processor.save_file(file)
                file_infos.append(file_info)
            
            return MultipleFileUploadResult(
                success=True,
                file_infos=file_infos,
                error_message=None
            )
            
        except FileValidationError as e:
            return MultipleFileUploadResult(
                success=False,
                file_infos=[],
                error_message=str(e)
            )
"""

    def generate_file_upload_types(self) -> str:
        """
        Génère les types GraphQL pour les téléchargements de fichiers.

        Returns:
            str: Code des types générés
        """
        return """
class FileInfoType(graphene.ObjectType):
    name = graphene.String(description="Nom du fichier")
    size = graphene.Int(description="Taille du fichier en octets")
    content_type = graphene.String(description="Type MIME du fichier")
    extension = graphene.String(description="Extension du fichier")

class FileUploadResultType(graphene.ObjectType):
    success = graphene.Boolean(description="Indique si le téléchargement a réussi")
    file_info = graphene.Field(FileInfoType, description="Informations sur le fichier téléchargé")
    error_message = graphene.String(description="Message d'erreur en cas d'échec")

class MultipleFileUploadResultType(graphene.ObjectType):
    success = graphene.Boolean(description="Indique si tous les téléchargements ont réussi")
    file_infos = graphene.List(FileInfoType, description="Liste des informations sur les fichiers téléchargés")
    error_message = graphene.String(description="Messages d'erreur en cas d'échec")
"""


class VirusScanner:
    """Scanner de virus pour les fichiers téléchargés."""

    def __init__(self, settings: GraphQLAutoConfig = None):
        self.settings = settings
        self.enabled = getattr(settings, 'VIRUS_SCAN_ENABLED', False) if settings else False

    def scan_file(self, file_path: str) -> bool:
        """
        Scanne un fichier pour détecter les virus.

        Args:
            file_path: Chemin vers le fichier à scanner

        Returns:
            bool: True si le fichier est sûr, False si un virus est détecté
        """
        if not self.enabled:
            # Si le scan n'est pas activé, considérer le fichier comme sûr
            return True

        # Simulation d'un scan de virus
        # Dans un vrai projet, vous utiliseriez une bibliothèque comme python-clamav
        # ou un service externe comme VirusTotal

        # Pour les tests, on peut simuler la détection basée sur le nom du fichier
        if 'virus' in Path(file_path).name.lower():
            return False

        return True

    def scan_uploaded_file(self, file: Union[InMemoryUploadedFile, TemporaryUploadedFile]) -> bool:
        """
        Scanne un fichier téléchargé pour détecter les virus.

        Args:
            file: Fichier téléchargé

        Returns:
            bool: True si le fichier est sûr, False si un virus est détecté
        """
        if not self.enabled:
            return True

        # Simulation basée sur le nom du fichier
        if 'virus' in file.name.lower():
            return False

        return True
