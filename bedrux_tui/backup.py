from __future__ import annotations

import datetime
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from .downloader import get_bedrux_home


@dataclass(frozen=True, slots=True)
class BackupResult:
    archive_path: Path
    instance_name: str


@dataclass(frozen=True, slots=True)
class BackupInfo:
    """Information about an existing backup."""
    path: Path
    instance_name: str
    timestamp: str
    size_mb: float

    @property
    def display_name(self) -> str:
        return f"{self.instance_name} ({self.timestamp}) - {self.size_mb:.1f} MB"


def get_bedrux_backup_dir() -> Path:
    """Get the global bedrux backup directory."""
    return get_bedrux_home() / "backups"


def list_backups() -> list[BackupInfo]:
    """List all available backups in the Bedrux backup directory.

    Default location is /opt/bedrux/.bedrux/backups unless overridden
    by the `BEDRUX_HOME` environment variable.
    """
    backup_dir = get_bedrux_backup_dir()
    if not backup_dir.exists():
        return []

    backups: list[BackupInfo] = []
    for file in backup_dir.glob("*.zip"):
        try:
            # Parse filename: instancename_YYYYMMDD_HHMMSS.zip
            stem = file.stem
            parts = stem.rsplit("_", 2)
            if len(parts) >= 3:
                instance_name = parts[0]
                date_part = parts[1]
                time_part = parts[2]
                timestamp = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]} {time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"
            else:
                instance_name = stem
                timestamp = "unknown"

            size_mb = file.stat().st_size / (1024 * 1024)
            backups.append(BackupInfo(
                path=file,
                instance_name=instance_name,
                timestamp=timestamp,
                size_mb=size_mb,
            ))
        except Exception:
            continue

    # Sort by modification time, newest first
    backups.sort(key=lambda b: b.path.stat().st_mtime, reverse=True)
    return backups


def make_backup(
    installation_path: Path,
    instance_name: str,
    *,
    backup_dir: Path | None = None,
) -> BackupResult:
    """
    Create a backup of the entire server instance as a zip file.

    Args:
        installation_path: Path to the server instance
        instance_name: Name of the instance (used in filename)
        backup_dir: Optional custom backup directory (defaults to ~/.bedrux/backups)

    Returns:
        BackupResult with the archive path
    """
    installation_path = installation_path.expanduser().resolve()
    backup_dir = (backup_dir or get_bedrux_backup_dir()).expanduser().resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    # Sanitize instance name for filename
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in instance_name)
    archive = backup_dir / f"{safe_name}_{timestamp}.zip"

    # Create zip of entire instance directory
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in installation_path.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(installation_path)
                zf.write(file_path, arcname)

    return BackupResult(archive_path=archive, instance_name=instance_name)


def restore_backup(
    backup_path: Path,
    target_path: Path,
    *,
    new_name: Optional[str] = None,
) -> Path:
    """
    Restore a backup to a target directory.

    Args:
        backup_path: Path to the backup zip file
        target_path: Base directory for instances (~/.bedrux/instances)
        new_name: Optional new name for the restored instance

    Returns:
        Path to the restored instance directory
    """
    import shutil
    import stat

    backup_path = backup_path.expanduser().resolve()
    target_path = target_path.expanduser().resolve()

    if not backup_path.exists():
        raise FileNotFoundError(f"Backup not found: {backup_path}")

    # Determine instance name from backup filename or use new_name
    if new_name:
        instance_name = new_name
    else:
        # Parse from filename: instancename_YYYYMMDD_HHMMSS.zip
        stem = backup_path.stem
        parts = stem.rsplit("_", 2)
        if len(parts) >= 3:
            instance_name = parts[0]
        else:
            instance_name = stem

    # Create target directory
    instance_dir = target_path / instance_name

    # If exists, add timestamp suffix
    if instance_dir.exists():
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        instance_name = f"{instance_name}_restored_{timestamp}"
        instance_dir = target_path / instance_name

    # Create a temp dir to extract to first
    temp_extract_dir = target_path / f".tmp_restore_{instance_name}"
    if temp_extract_dir.exists():
        shutil.rmtree(temp_extract_dir)
    temp_extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Extract backup to temp dir
        with zipfile.ZipFile(backup_path, "r") as zf:
            zf.extractall(temp_extract_dir)

        # Check if files are in a subdirectory (old backup format)
        contents = list(temp_extract_dir.iterdir())
        if len(contents) == 1 and contents[0].is_dir():
            # Files are in a subdirectory, move them up
            extracted_subdir = contents[0]
            # Move the subdirectory to final location
            shutil.move(str(extracted_subdir), str(instance_dir))
        else:
            # Files are directly in temp dir, move the whole thing
            shutil.move(str(temp_extract_dir), str(instance_dir))
            temp_extract_dir = None  # Already moved

        # Set execute permissions on bedrock_server
        server_binary = instance_dir / "bedrock_server"
        if server_binary.exists():
            # Make it executable (rwxr-xr-x = 0o755)
            server_binary.chmod(stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

        return instance_dir
    finally:
        # Clean up temp dir if it still exists
        if temp_extract_dir and temp_extract_dir.exists():
            shutil.rmtree(temp_extract_dir, ignore_errors=True)


def delete_backup(backup_path: Path) -> bool:
    """Delete a backup file."""
    try:
        backup_path = backup_path.expanduser().resolve()
        if backup_path.exists():
            backup_path.unlink()
            return True
        return False
    except Exception:
        return False
