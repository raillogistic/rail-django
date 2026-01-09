"""
Système de scan antivirus pour les fichiers téléchargés.

Ce module fournit des fonctionnalités de sécurité avancées pour :
- Scan antivirus des fichiers téléchargés
- Intégration avec ClamAV
- Quarantaine des fichiers suspects
- Logging des menaces détectées
"""

import hashlib
import logging
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile

from ..core.settings import GraphQLAutoConfig

logger = logging.getLogger(__name__)


class VirusScanError(Exception):
    """Exception levée lors d'erreurs de scan antivirus."""
    pass


class ThreatDetected(Exception):
    """Exception levée lorsqu'une menace est détectée."""
    pass


class ScanResult:
    """Résultat d'un scan antivirus."""

    def __init__(self, is_clean: bool, threat_name: Optional[str] = None,
                 scan_time: Optional[datetime] = None, scanner_version: Optional[str] = None):
        self.is_clean = is_clean
        self.threat_name = threat_name
        self.scan_time = scan_time or datetime.now()
        self.scanner_version = scanner_version

    def __str__(self):
        if self.is_clean:
            return f"Fichier propre (scanné le {self.scan_time})"
        else:
            return f"Menace détectée: {self.threat_name} (scanné le {self.scan_time})"


class ClamAVScanner:
    """Scanner antivirus utilisant ClamAV."""

    def __init__(self, settings: GraphQLAutoConfig):
        self.settings = settings
        self.clamav_path = getattr(settings, 'CLAMAV_PATH', 'clamscan')
        self.clamd_socket = getattr(settings, 'CLAMD_SOCKET', None)
        self.use_clamd = getattr(settings, 'USE_CLAMD', True)
        self.timeout = getattr(settings, 'VIRUS_SCAN_TIMEOUT', 30)

        # Vérification de la disponibilité de ClamAV
        if not self._check_clamav_available():
            logger.warning("ClamAV n'est pas disponible sur ce système")

    def _check_clamav_available(self) -> bool:
        """
        Vérifie si ClamAV est disponible sur le système.

        Returns:
            bool: True si ClamAV est disponible
        """
        try:
            if self.use_clamd:
                # Test de connexion à clamd
                result = subprocess.run(
                    ['clamdscan', '--version'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                return result.returncode == 0
            else:
                # Test de clamscan
                result = subprocess.run(
                    [self.clamav_path, '--version'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            return False

    def _get_scanner_version(self) -> Optional[str]:
        """
        Récupère la version du scanner ClamAV.

        Returns:
            Optional[str]: Version du scanner ou None
        """
        try:
            cmd = ['clamdscan', '--version'] if self.use_clamd else [self.clamav_path, '--version']
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip().split('\n')[0]
        except Exception:
            pass
        return None

    def scan_file(self, file_path: str) -> ScanResult:
        """
        Scanne un fichier avec ClamAV.

        Args:
            file_path: Chemin vers le fichier à scanner

        Returns:
            ScanResult: Résultat du scan

        Raises:
            VirusScanError: Si le scan échoue
            ThreatDetected: Si une menace est détectée
        """
        if not os.path.exists(file_path):
            raise VirusScanError(f"Le fichier {file_path} n'existe pas")

        try:
            if self.use_clamd:
                cmd = ['clamdscan', '--no-summary', file_path]
            else:
                cmd = [self.clamav_path, '--no-summary', file_path]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )

            scanner_version = self._get_scanner_version()

            # Code de retour 0 = fichier propre
            if result.returncode == 0:
                logger.info(f"Fichier {file_path} scanné: propre")
                return ScanResult(
                    is_clean=True,
                    scanner_version=scanner_version
                )

            # Code de retour 1 = menace détectée
            elif result.returncode == 1:
                # Extraction du nom de la menace depuis la sortie
                threat_name = "Menace inconnue"
                if result.stdout:
                    lines = result.stdout.strip().split('\n')
                    for line in lines:
                        if 'FOUND' in line:
                            parts = line.split(':')
                            if len(parts) >= 2:
                                threat_name = parts[1].strip().replace(' FOUND', '')
                            break

                logger.warning(f"Menace détectée dans {file_path}: {threat_name}")
                return ScanResult(
                    is_clean=False,
                    threat_name=threat_name,
                    scanner_version=scanner_version
                )

            # Autres codes de retour = erreur
            else:
                error_msg = f"Erreur lors du scan ClamAV (code {result.returncode}): {result.stderr}"
                logger.error(error_msg)
                raise VirusScanError(error_msg)

        except subprocess.TimeoutExpired:
            raise VirusScanError(f"Timeout lors du scan du fichier {file_path}")
        except Exception as e:
            raise VirusScanError(f"Erreur lors du scan: {e}")

    def scan_uploaded_file(self, file: Union[InMemoryUploadedFile, TemporaryUploadedFile]) -> ScanResult:
        """
        Scanne un fichier téléchargé.

        Args:
            file: Fichier téléchargé à scanner

        Returns:
            ScanResult: Résultat du scan
        """
        # Création d'un fichier temporaire pour le scan
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            try:
                # Écriture du contenu dans le fichier temporaire
                file.seek(0)
                for chunk in file.chunks():
                    temp_file.write(chunk)
                file.seek(0)

                temp_file.flush()

                # Scan du fichier temporaire
                return self.scan_file(temp_file.name)

            finally:
                # Nettoyage du fichier temporaire
                try:
                    os.unlink(temp_file.name)
                except OSError:
                    pass


class MockScanner:
    """Scanner factice pour les environnements de développement."""

    def __init__(self, settings: GraphQLAutoConfig):
        self.settings = settings
        self.simulate_threats = getattr(settings, 'MOCK_SCANNER_SIMULATE_THREATS', False)
        self.threat_patterns = getattr(settings, 'MOCK_SCANNER_THREAT_PATTERNS', [
            'virus', 'malware', 'trojan', 'test'
        ])

    def scan_file(self, file_path: str) -> ScanResult:
        """
        Simule un scan de fichier.

        Args:
            file_path: Chemin vers le fichier

        Returns:
            ScanResult: Résultat simulé
        """
        filename = os.path.basename(file_path).lower()

        # Simulation de détection de menace basée sur le nom de fichier
        if self.simulate_threats:
            for pattern in self.threat_patterns:
                if pattern in filename:
                    return ScanResult(
                        is_clean=False,
                        threat_name=f"Test.{pattern.capitalize()}.MOCK",
                        scanner_version="MockScanner 1.0"
                    )

        return ScanResult(
            is_clean=True,
            scanner_version="MockScanner 1.0"
        )

    def scan_uploaded_file(self, file: Union[InMemoryUploadedFile, TemporaryUploadedFile]) -> ScanResult:
        """
        Simule un scan de fichier téléchargé.

        Args:
            file: Fichier téléchargé

        Returns:
            ScanResult: Résultat simulé
        """
        filename = file.name.lower() if file.name else "unknown"

        if self.simulate_threats:
            for pattern in self.threat_patterns:
                if pattern in filename:
                    return ScanResult(
                        is_clean=False,
                        threat_name=f"Test.{pattern.capitalize()}.MOCK",
                        scanner_version="MockScanner 1.0"
                    )

        return ScanResult(
            is_clean=True,
            scanner_version="MockScanner 1.0"
        )


class VirusScanner:
    """Gestionnaire principal de scan antivirus."""

    def __init__(self, settings: GraphQLAutoConfig):
        self.settings = settings
        self.enabled = getattr(settings, 'VIRUS_SCANNING_ENABLED', True)
        self.scanner_type = getattr(settings, 'VIRUS_SCANNER_TYPE', 'clamav')
        self.quarantine_path = getattr(settings, 'QUARANTINE_PATH', None)

        # Initialisation du scanner approprié
        if not self.enabled:
            self.scanner = None
        elif self.scanner_type == 'clamav':
            self.scanner = ClamAVScanner(settings)
        elif self.scanner_type == 'mock':
            self.scanner = MockScanner(settings)
        else:
            raise VirusScanError(f"Type de scanner non supporté: {self.scanner_type}")

    def scan_file(self, file_path: str) -> ScanResult:
        """
        Scanne un fichier.

        Args:
            file_path: Chemin vers le fichier à scanner

        Returns:
            ScanResult: Résultat du scan
        """
        if not self.enabled or not self.scanner:
            return ScanResult(is_clean=True, scanner_version="Disabled")

        return self.scanner.scan_file(file_path)

    def scan_uploaded_file(self, file: Union[InMemoryUploadedFile, TemporaryUploadedFile]) -> ScanResult:
        """
        Scanne un fichier téléchargé.

        Args:
            file: Fichier téléchargé à scanner

        Returns:
            ScanResult: Résultat du scan

        Raises:
            ThreatDetected: Si une menace est détectée
        """
        if not self.enabled or not self.scanner:
            return ScanResult(is_clean=True, scanner_version="Disabled")

        result = self.scanner.scan_uploaded_file(file)

        # Logging du résultat
        if result.is_clean:
            logger.info(f"Fichier {file.name} scanné: propre")
        else:
            logger.warning(f"Menace détectée dans {file.name}: {result.threat_name}")

            # Quarantaine si configurée
            if self.quarantine_path and not result.is_clean:
                self._quarantine_file(file, result)

            # Lever une exception pour bloquer le téléchargement
            raise ThreatDetected(f"Menace détectée: {result.threat_name}")

        return result

    def _quarantine_file(self, file: Union[InMemoryUploadedFile, TemporaryUploadedFile],
                         scan_result: ScanResult) -> None:
        """
        Met un fichier en quarantaine.

        Args:
            file: Fichier à mettre en quarantaine
            scan_result: Résultat du scan
        """
        if not self.quarantine_path:
            return

        try:
            # Création du répertoire de quarantaine si nécessaire
            quarantine_dir = Path(self.quarantine_path)
            quarantine_dir.mkdir(parents=True, exist_ok=True)

            # Génération d'un nom unique pour le fichier en quarantaine
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_hash = hashlib.md5(file.read()).hexdigest()[:8]
            file.seek(0)

            quarantine_filename = f"{timestamp}_{file_hash}_{file.name}"
            quarantine_path = quarantine_dir / quarantine_filename

            # Sauvegarde du fichier en quarantaine
            with open(quarantine_path, 'wb') as qf:
                file.seek(0)
                for chunk in file.chunks():
                    qf.write(chunk)
                file.seek(0)

            # Création d'un fichier de métadonnées
            metadata_path = quarantine_path.with_suffix('.metadata')
            with open(metadata_path, 'w') as mf:
                mf.write(f"Original filename: {file.name}\n")
                mf.write(f"Threat detected: {scan_result.threat_name}\n")
                mf.write(f"Scan time: {scan_result.scan_time}\n")
                mf.write(f"Scanner version: {scan_result.scanner_version}\n")
                mf.write(f"File size: {file.size}\n")
                mf.write(f"Content type: {file.content_type}\n")

            logger.info(f"Fichier {file.name} mis en quarantaine: {quarantine_path}")

        except Exception as e:
            logger.error(f"Erreur lors de la mise en quarantaine de {file.name}: {e}")

    def get_quarantine_files(self) -> List[Dict[str, str]]:
        """
        Récupère la liste des fichiers en quarantaine.

        Returns:
            List[Dict[str, str]]: Liste des fichiers en quarantaine avec leurs métadonnées
        """
        if not self.quarantine_path:
            return []

        quarantine_dir = Path(self.quarantine_path)
        if not quarantine_dir.exists():
            return []

        quarantine_files = []

        for file_path in quarantine_dir.glob("*"):
            if file_path.suffix == '.metadata':
                continue

            metadata_path = file_path.with_suffix('.metadata')
            metadata = {}

            if metadata_path.exists():
                try:
                    with open(metadata_path, 'r') as mf:
                        for line in mf:
                            if ':' in line:
                                key, value = line.strip().split(':', 1)
                                metadata[key.strip()] = value.strip()
                except Exception:
                    pass

            quarantine_files.append({
                'quarantine_path': str(file_path),
                'quarantine_time': datetime.fromtimestamp(file_path.stat().st_ctime).isoformat(),
                **metadata
            })

        return sorted(quarantine_files, key=lambda x: x.get('quarantine_time', ''), reverse=True)

    def delete_quarantine_file(self, quarantine_path: str) -> bool:
        """
        Supprime un fichier de la quarantaine.

        Args:
            quarantine_path: Chemin vers le fichier en quarantaine

        Returns:
            bool: True si la suppression a réussi
        """
        try:
            file_path = Path(quarantine_path)
            metadata_path = file_path.with_suffix('.metadata')

            # Suppression du fichier et de ses métadonnées
            if file_path.exists():
                file_path.unlink()
            if metadata_path.exists():
                metadata_path.unlink()

            logger.info(f"Fichier en quarantaine supprimé: {quarantine_path}")
            return True

        except Exception as e:
            logger.error(
                f"Erreur lors de la suppression du fichier en quarantaine {quarantine_path}: {e}")
            return False
