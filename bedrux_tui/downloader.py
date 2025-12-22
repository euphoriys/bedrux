"""Bedrux Downloader - Fetches and installs Bedrock Dedicated Server."""

from __future__ import annotations

import asyncio
import os
import platform
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import aiohttp


WIKI_URL = "https://minecraft.wiki/w/Bedrock_Dedicated_Server"
WIKI_API_URL = "https://minecraft.wiki/api.php?action=parse&page=Bedrock_Dedicated_Server&prop=text&format=json"
VERSION_PATTERN = re.compile(r"<b>(Release|Preview):</b>.*?>([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)")


@dataclass
class VersionInfo:
    """Represents a Bedrock server version."""
    version: str
    is_preview: bool

    @property
    def download_url(self) -> str:
        """Generate download URL for this version."""
        suffix = "-preview" if self.is_preview else ""
        return f"https://www.minecraft.net/bedrockdedicatedserver/bin-linux{suffix}/bedrock-server-{self.version}.zip"

    @property
    def display_name(self) -> str:
        """Display name for UI."""
        prefix = "Preview" if self.is_preview else "Release"
        return f"{prefix}: {self.version}"


LogCallback = Callable[[str], None]
ProgressCallback = Callable[[int, int], None]


def get_system_arch() -> str:
    """Get system architecture."""
    return platform.machine()


def get_server_command() -> str:
    """Get the appropriate server command based on system architecture."""
    arch = get_system_arch()
    if arch == "aarch64":
        return "box64 bedrock_server"
    elif arch == "x86_64":
        return "./bedrock_server"
    else:
        # Fallback for unknown architectures
        return "./bedrock_server"


async def fetch_versions(log: Optional[LogCallback] = None) -> list[VersionInfo]:
    """Fetch available versions from Minecraft wiki using curl (like svm does)."""
    versions: list[VersionInfo] = []

    if log:
        log("Fetching versions from Minecraft Wiki...")

    try:
        # Use curl like the original svm script - this works reliably
        proc = await asyncio.create_subprocess_exec(
            "curl", "-s", WIKI_URL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

        if proc.returncode != 0:
            if log:
                log("Failed to fetch versions: curl error")
            return versions

        html = stdout.decode("utf-8", errors="replace")
    except asyncio.TimeoutError:
        if log:
            log("Timeout while fetching versions.")
        return versions
    except FileNotFoundError:
        if log:
            log("curl not found. Please install curl.")
        return versions
    except Exception as e:
        if log:
            log(f"Error fetching versions: {e}")
        return versions

    # Parse versions from HTML
    release_match = re.search(r'<b>Release:</b>.*?>(\d+\.\d+\.\d+\.\d+)', html)
    preview_match = re.search(r'<b>Preview:</b>.*?>(\d+\.\d+\.\d+\.\d+)', html)

    if release_match:
        versions.append(VersionInfo(version=release_match.group(1), is_preview=False))
        if log:
            log(f"Found Release: {release_match.group(1)}")

    if preview_match:
        versions.append(VersionInfo(version=preview_match.group(1), is_preview=True))
        if log:
            log(f"Found Preview: {preview_match.group(1)}")

    if not versions and log:
        log("No versions found on wiki page.")

    return versions


async def check_url_exists(url: str) -> bool:
    """Check if a URL exists (returns 200)."""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "Mozilla/5.0 (compatible; BedruxClient/1.0)"}
            async with session.head(url, headers=headers, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=10)) as response:
                return response.status == 200
    except Exception:
        return False


async def make_version_url(version: str, log: Optional[LogCallback] = None) -> Optional[str]:
    """Create download URL for a version, checking both release and preview."""
    release_url = f"https://www.minecraft.net/bedrockdedicatedserver/bin-linux/bedrock-server-{version}.zip"
    preview_url = f"https://www.minecraft.net/bedrockdedicatedserver/bin-linux-preview/bedrock-server-{version}.zip"

    if log:
        log(f"Checking release URL for version {version}...")

    if await check_url_exists(release_url):
        if log:
            log("Release version found.")
        return release_url

    if log:
        log("Checking preview URL...")

    if await check_url_exists(preview_url):
        if log:
            log("Preview version found.")
        return preview_url

    if log:
        log(f"Version {version} not found.")
    return None


async def download_and_install(
    url: str,
    instance_name: str,
    bedrux_home: Path,
    log: Optional[LogCallback] = None,
    progress: Optional[ProgressCallback] = None,
    overwrite: bool = False,
) -> bool:
    """
    Download and install a Bedrock server instance.

    Args:
        url: Download URL for the server zip
        instance_name: Name for the new instance
        bedrux_home: Base directory for bedrux (~/.bedrux)
        log: Callback for logging messages
        progress: Callback for progress updates (current, total)
        overwrite: Whether to overwrite existing instance

    Returns:
        True if installation was successful, False otherwise
    """
    # Ensure directories exist
    instances_dir = bedrux_home / "instances"
    downloads_dir = bedrux_home / "downloads"
    backups_dir = bedrux_home / "backups"

    # Control downloads behavior via environment variables:
    # - BEDRUX_USE_DOWNLOADS: if set to '0' or 'false' (case-insensitive), do not create a persistent downloads folder and use a temp file instead.
    # - BEDRUX_KEEP_DOWNLOADS: if set to '1' or 'true', keep downloaded zip files in the downloads folder (if used).
    # Default to not using a persistent downloads folder (use temp files),
    # set BEDRUX_USE_DOWNLOADS=1 to enable persistent `downloads/`.
    use_downloads = os.environ.get("BEDRUX_USE_DOWNLOADS", "0").lower() not in ("0", "false")
    keep_downloads = os.environ.get("BEDRUX_KEEP_DOWNLOADS", "0").lower() in ("1", "true")

    # Always ensure instances and backups directories exist.
    instances_dir.mkdir(parents=True, exist_ok=True)
    backups_dir.mkdir(parents=True, exist_ok=True)
    if use_downloads:
        downloads_dir.mkdir(parents=True, exist_ok=True)

    instance_path = instances_dir / instance_name

    # Check if instance exists
    if instance_path.exists():
        if not overwrite:
            if log:
                log(f"Instance '{instance_name}' already exists. Use overwrite option to replace.")
            return False

        if log:
            log(f"Removing existing instance '{instance_name}'...")

        try:
            shutil.rmtree(instance_path)
        except Exception as e:
            if log:
                log(f"Failed to remove existing instance: {e}")
            return False

    # Extract filename from URL
    filename = url.split("/")[-1]

    # Download target: persistent downloads dir or a temporary file
    if use_downloads:
        download_path = downloads_dir / filename
    else:
        import tempfile
        tf = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        download_path = Path(tf.name)
        tf.close()

    if log:
        log(f"[+] Downloading {filename}...")

    # Download the file
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "Mozilla/5.0 (compatible; BedruxClient/1.0)"}
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=600)) as response:
                if response.status != 200:
                    if log:
                        log(f"Download failed: HTTP {response.status}")
                    # cleanup temp file if used
                    if not use_downloads and download_path.exists():
                        download_path.unlink()
                    return False

                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0

                with open(download_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress and total_size > 0:
                            progress(downloaded, total_size)

        if log:
            log("[+] Download complete.")

    except asyncio.TimeoutError:
        if log:
            log("Download timed out.")
        if download_path.exists():
            download_path.unlink()
        return False
    except Exception as e:
        if log:
            log(f"Download failed: {e}")
        if download_path.exists():
            download_path.unlink()
        return False

    # Extract the zip file
    if log:
        log("[+] Extracting...")

    try:
        instance_path.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(download_path, 'r') as zip_ref:
            zip_ref.extractall(instance_path)

        if log:
            log("[+] Extraction complete.")

    except zipfile.BadZipFile:
        if log:
            log("Failed: Downloaded file is not a valid zip archive.")
        if download_path.exists():
            download_path.unlink()
        if instance_path.exists():
            shutil.rmtree(instance_path)
        return False
    except Exception as e:
        if log:
            log(f"Extraction failed: {e}")
        if download_path.exists():
            download_path.unlink()
        if instance_path.exists():
            shutil.rmtree(instance_path)
        return False

    # Clean up download if using temp or if user doesn't want to keep downloads
    try:
        if (not use_downloads) or (use_downloads and not keep_downloads):
            if download_path.exists():
                download_path.unlink()
                if log:
                    log("[+] Cleaned up download file.")
    except Exception:
        pass

    # Make bedrock_server executable
    server_bin = instance_path / "bedrock_server"
    if server_bin.exists():
        try:
            os.chmod(server_bin, 0o755)
            if log:
                log("[+] Made bedrock_server executable.")
        except Exception as e:
            if log:
                log(f"Warning: Could not set executable permission: {e}")

    if log:
        log(f"[✓] Instance '{instance_name}' created successfully!")
        arch = get_system_arch()
        cmd = get_server_command()
        log(f"[i] System architecture: {arch}")
        log(f"[i] Server command: {cmd}")

    return True


def validate_version_format(version: str) -> bool:
    """Validate version string format (e.g., 1.21.0.3)."""
    pattern = r'^1\.\d{1,3}\.\d{1,3}\.\d{1,3}$'
    return bool(re.match(pattern, version))


def validate_instance_name(name: str) -> tuple[bool, str]:
    """
    Validate instance name.

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not name:
        return False, "Instance name cannot be empty."

    if len(name) > 64:
        return False, "Instance name is too long (max 64 characters)."

    # Check for invalid characters
    invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|', '\n', '\r', '\t']
    for char in invalid_chars:
        if char in name:
            return False, f"Instance name cannot contain '{char}'."

    # Check for reserved names
    reserved = ['.', '..', 'CON', 'PRN', 'AUX', 'NUL']
    if name.upper() in reserved:
        return False, f"'{name}' is a reserved name."

    return True, ""


def get_bedrux_home() -> Path:
    """Get the bedrux home directory."""
    # Allow overriding the base location via environment variable for flexibility
    env = os.environ.get("BEDRUX_HOME")
    if env:
        return Path(env).expanduser().resolve()

    # If running as root, use root's home; otherwise use the invoking user's home
    try:
        if os.geteuid() == 0:
            return Path("/root") / ".bedrux"
    except AttributeError:
        # Windows or platforms without geteuid - fall back to Path.home()
        pass

    return Path.home() / ".bedrux"


def ensure_bedrux_home(migrate_from_opt: bool = True) -> Path:
    """Ensure the Bedrux home directory exists and optionally migrate from /opt/bedrux.

    Behavior:
    - If `BEDRUX_HOME` env var is set, use that path.
    - If running as root, use `/root/.bedrux`, otherwise `~/.bedrux` of the user.
    - If `migrate_from_opt` is True and `/opt/bedrux/.bedrux` exists and differs
      from the chosen target, copy contents into the target (only if target is
      missing or empty) to avoid accidental overwrite.

    Returns the chosen Bedrux home Path.
    """
    target = get_bedrux_home()
    target.mkdir(parents=True, exist_ok=True)

    if migrate_from_opt:
        opt_path = Path("/opt/bedrux") / ".bedrux"
        try:
            if opt_path.exists() and opt_path.resolve() != target.resolve():
                # Only migrate if target is empty (to be safe)
                if not any(target.iterdir()):
                    # Copy contents from opt_path to target
                    for item in opt_path.iterdir():
                        src = item
                        dest = target / item.name
                        if src.is_dir():
                            shutil.copytree(src, dest)
                        else:
                            shutil.copy2(src, dest)
        except Exception:
            # Non-fatal: if migration fails, leave target as-is
            pass

    return target
