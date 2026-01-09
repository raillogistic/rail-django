"""
Système de validation et sanitisation des entrées pour Django GraphQL.

Ce module fournit :
- Validation des entrées GraphQL
- Sanitisation contre les injections
- Protection contre les attaques XSS
- Validation des types de données
"""

import html
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

import bleach
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator, validate_email
from django.utils.html import strip_tags
from graphql import GraphQLError

logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Niveaux de sévérité pour les violations de validation."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ValidationResult:
    """Résultat d'une validation d'entrée."""
    is_valid: bool
    sanitized_value: Any
    violations: List[str]
    severity: ValidationSeverity
    original_value: Any


class InputValidator:
    """
    Validateur d'entrées avec sanitisation automatique.
    """

    # Patterns dangereux à détecter
    DANGEROUS_PATTERNS = [
        r'<script[^>]*>.*?</script>',  # Scripts JavaScript
        r'javascript:',  # URLs JavaScript
        r'on\w+\s*=',  # Gestionnaires d'événements
        r'expression\s*\(',  # CSS expressions
        r'@import',  # CSS imports
        r'<iframe[^>]*>',  # iframes
        r'<object[^>]*>',  # objects
        r'<embed[^>]*>',  # embeds
        r'<link[^>]*>',  # links externes
        r'<meta[^>]*>',  # meta tags
    ]

    # Tags HTML autorisés pour le contenu riche
    ALLOWED_HTML_TAGS = [
        'p', 'br', 'strong', 'em', 'u', 'ol', 'ul', 'li',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote'
    ]

    # Attributs HTML autorisés
    ALLOWED_HTML_ATTRIBUTES = {
        '*': ['class'],
        'a': ['href', 'title'],
        'img': ['src', 'alt', 'width', 'height'],
    }

    def __init__(self):
        """Initialise le validateur."""
        self.url_validator = URLValidator()

    def validate_string(self, value: str, max_length: int = None,
                        allow_html: bool = False,
                        strip_dangerous: bool = True) -> ValidationResult:
        """
        Valide et sanitise une chaîne de caractères.

        Args:
            value: Valeur à valider
            max_length: Longueur maximale autorisée
            allow_html: Autoriser le HTML sécurisé
            strip_dangerous: Supprimer les patterns dangereux

        Returns:
            Résultat de la validation
        """
        violations = []
        severity = ValidationSeverity.LOW
        sanitized_value = value

        if not isinstance(value, str):
            return ValidationResult(
                is_valid=False,
                sanitized_value="",
                violations=["La valeur doit être une chaîne de caractères"],
                severity=ValidationSeverity.HIGH,
                original_value=value
            )

        # Vérification de la longueur
        if max_length and len(value) > max_length:
            violations.append(f"Longueur maximale dépassée ({len(value)} > {max_length})")
            severity = ValidationSeverity.MEDIUM
            sanitized_value = value[:max_length]

        # Détection de patterns dangereux
        if strip_dangerous:
            for pattern in self.DANGEROUS_PATTERNS:
                if re.search(pattern, value, re.IGNORECASE):
                    violations.append(f"Pattern dangereux détecté: {pattern}")
                    severity = ValidationSeverity.CRITICAL
                    sanitized_value = re.sub(pattern, '', sanitized_value, flags=re.IGNORECASE)

        # Sanitisation HTML
        if allow_html:
            sanitized_value = bleach.clean(
                sanitized_value,
                tags=self.ALLOWED_HTML_TAGS,
                attributes=self.ALLOWED_HTML_ATTRIBUTES,
                strip=True
            )
        else:
            # Échapper le HTML
            sanitized_value = html.escape(sanitized_value)

        return ValidationResult(
            is_valid=len(violations) == 0 or severity.value in ['low', 'medium'],
            sanitized_value=sanitized_value,
            violations=violations,
            severity=severity,
            original_value=value
        )

    def validate_email(self, email: str) -> ValidationResult:
        """
        Valide une adresse email.

        Args:
            email: Adresse email à valider

        Returns:
            Résultat de la validation
        """
        violations = []

        try:
            validate_email(email)
            sanitized_email = email.lower().strip()

            return ValidationResult(
                is_valid=True,
                sanitized_value=sanitized_email,
                violations=[],
                severity=ValidationSeverity.LOW,
                original_value=email
            )
        except ValidationError as e:
            violations.extend(e.messages)

        return ValidationResult(
            is_valid=False,
            sanitized_value="",
            violations=violations,
            severity=ValidationSeverity.HIGH,
            original_value=email
        )

    def validate_url(self, url: str) -> ValidationResult:
        """
        Valide une URL.

        Args:
            url: URL à valider

        Returns:
            Résultat de la validation
        """
        violations = []

        try:
            self.url_validator(url)

            # Vérifications de sécurité supplémentaires
            if url.startswith('javascript:'):
                violations.append("URLs JavaScript non autorisées")
                return ValidationResult(
                    is_valid=False,
                    sanitized_value="",
                    violations=violations,
                    severity=ValidationSeverity.CRITICAL,
                    original_value=url
                )

            return ValidationResult(
                is_valid=True,
                sanitized_value=url,
                violations=[],
                severity=ValidationSeverity.LOW,
                original_value=url
            )
        except ValidationError as e:
            violations.extend(e.messages)

        return ValidationResult(
            is_valid=False,
            sanitized_value="",
            violations=violations,
            severity=ValidationSeverity.HIGH,
            original_value=url
        )

    def validate_graphql_input(self, input_data: Dict[str, Any],
                               schema_definition: Dict[str, Any] = None) -> Dict[str, ValidationResult]:
        """
        Valide les données d'entrée GraphQL.

        Args:
            input_data: Données d'entrée à valider
            schema_definition: Définition du schéma pour la validation

        Returns:
            Dictionnaire des résultats de validation par champ
        """
        results = {}

        for field_name, value in input_data.items():
            if isinstance(value, str):
                results[field_name] = self.validate_string(value)
            elif isinstance(value, dict):
                # Validation récursive pour les objets imbriqués
                results[field_name] = self.validate_graphql_input(value, schema_definition)
            elif isinstance(value, list):
                # Validation des listes
                list_results = []
                for item in value:
                    if isinstance(item, str):
                        list_results.append(self.validate_string(item))
                    elif isinstance(item, dict):
                        list_results.append(self.validate_graphql_input(item, schema_definition))
                results[field_name] = list_results

        return results


class GraphQLInputSanitizer:
    """
    Sanitiseur spécialisé pour les entrées GraphQL.
    """

    def __init__(self):
        """Initialise le sanitiseur."""
        self.validator = InputValidator()

    def sanitize_mutation_input(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitise les données d'entrée d'une mutation GraphQL.

        Args:
            input_data: Données d'entrée à sanitiser

        Returns:
            Données sanitisées
        """
        sanitized_data = {}

        for field_name, value in input_data.items():
            if isinstance(value, str):
                result = self.validator.validate_string(value, strip_dangerous=True)
                if result.severity == ValidationSeverity.CRITICAL:
                    logger.warning(
                        f"Entrée dangereuse détectée pour le champ {field_name}: {result.violations}")
                    raise GraphQLError(f"Données d'entrée non valides pour le champ {field_name}")
                sanitized_data[field_name] = result.sanitized_value
            elif isinstance(value, dict):
                sanitized_data[field_name] = self.sanitize_mutation_input(value)
            elif isinstance(value, list):
                sanitized_list = []
                for item in value:
                    if isinstance(item, str):
                        result = self.validator.validate_string(item, strip_dangerous=True)
                        sanitized_list.append(result.sanitized_value)
                    elif isinstance(item, dict):
                        sanitized_list.append(self.sanitize_mutation_input(item))
                    else:
                        sanitized_list.append(item)
                sanitized_data[field_name] = sanitized_list
            else:
                sanitized_data[field_name] = value

        return sanitized_data


def validate_input(validator_func: Callable = None):
    """
    Décorateur pour valider automatiquement les entrées GraphQL.

    Args:
        validator_func: Fonction de validation personnalisée

    Returns:
        Décorateur de validation
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Extraire les données d'entrée
            if 'input' in kwargs:
                sanitizer = GraphQLInputSanitizer()
                kwargs['input'] = sanitizer.sanitize_mutation_input(kwargs['input'])

            # Validation personnalisée si fournie
            if validator_func:
                validator_func(*args, **kwargs)

            return func(*args, **kwargs)
        return wrapper
    return decorator


# Instance globale du validateur
input_validator = InputValidator()
graphql_sanitizer = GraphQLInputSanitizer()
