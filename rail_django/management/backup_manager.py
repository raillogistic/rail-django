"""
Backup management module.

Provides minimal backup/restore interfaces for schema management to satisfy
imports during Django initialization. This stub can be extended with real
backup logic later.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class BackupStrategy(Enum):
    """Supported backup strategies."""
    FULL = "full"
    INCREMENTAL = "incremental"


@dataclass
class SchemaBackup:
    """Represents a schema backup artifact."""
    schema_name: str
    version: Optional[str]
    created_at: datetime = field(default_factory=datetime.now)
    file_path: Optional[Path] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class BackupManager:
    """
    Minimal backup manager with stubbed methods.
    Replace implementations with actual backup/restore logic when needed.
    """

    def __init__(self, backup_dir: Path = Path("backups")):
        self.backup_dir = backup_dir
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not ensure backup directory exists: {e}")

    def create_backup(self, schema_name: str, version: Optional[str] = None,
                      strategy: BackupStrategy = BackupStrategy.FULL,
                      metadata: Optional[Dict[str, Any]] = None) -> SchemaBackup:
        """
        Create a schema backup artifact (stubbed: writes no data).
        """
        backup = SchemaBackup(
            schema_name=schema_name,
            version=version,
            file_path=self.backup_dir / f"{schema_name}-{version or 'unknown'}.bak",
            metadata=metadata or {"strategy": strategy.value},
        )
        logger.info(f"Created backup metadata: {backup}")
        return backup

    def restore_backup(self, backup: SchemaBackup) -> bool:
        """
        Restore a schema from a backup (stubbed: does nothing).
        Returns True to indicate success.
        """
        logger.info(f"Restoring backup: {backup}")
        return True
