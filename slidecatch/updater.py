"""Updates: find a newer release, unpack it, and swap the program's files.

This module has no Qt and no network code, so it is easy to test. The part
that talks to the internet and shows the dialogs is slidecatch/ui/updates.py.

How an update works (portable program, no installer, no administrator):

1. The release list of the project on GitHub is asked for its latest release
   (one small request; GitHub gets the program name and version, nothing else).
2. The zip of the release and its checksum file are downloaded to a folder in
   %APPDATA%\\SlideCatch\\updates, and the checksum (SHA-256) is verified.
3. The zip is unpacked next to the download.
4. A small helper script is started, SlideCatch quits, and the script (which
   cannot be locked by the running program) waits until SlideCatch.exe is free,
   moves the old files aside, copies the new ones and starts the new version.
   If anything fails, the old files are put back and the old version restarts.

Settings and sessions are never touched: they live outside the program folder
(except in portable mode, where the script only adds and replaces files, it
never deletes the "settings", "sessions" and "exports" folders).
"""

import json
import os
import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from typing import Optional

from . import APP_VERSION

# The project whose releases are checked. If the project moves, change it here.
RELEASES_REPO = "abdelhaouari-AE/SlideCatch"
API_URL = "https://api.github.com/repos/%s/releases/latest" % RELEASES_REPO
DOWNLOAD_PREFIX = "https://github.com/%s/releases/download/" % RELEASES_REPO
PAGE_URL = "https://github.com/%s/releases/latest" % RELEASES_REPO

EXE_NAME = "SlideCatch.exe"
ASSET_PATTERN = re.compile(r"^SlideCatch-[\w.\-]+-portable\.zip$")
CHECK_EVERY_HOURS = 20          # the automatic check at start-up runs at most this often


class UpdateError(Exception):
    """A problem the person can be told about (the message is shown as is)."""


@dataclass
class Release:
    version: str                # "0.2.0"
    tag: str                    # "v0.2.0"
    notes: str                  # release notes (markdown)
    page_url: str               # the release page, for people who prefer to download by hand
    zip_url: str = ""
    zip_size: int = 0
    sha_url: str = ""

    @property
    def can_download(self) -> bool:
        return bool(self.zip_url and self.sha_url)


# ------------------------------------------------------------- versions
def parse_version(text: str) -> tuple:
    """"v0.10.2" -> (0, 10, 2). Anything that is not numbers is ignored."""
    numbers = [int(n) for n in re.findall(r"\d+", str(text).split("-")[0])[:3]]
    return tuple(numbers + [0] * (3 - len(numbers)))


def is_newer(candidate: str, current: str = APP_VERSION) -> bool:
    return parse_version(candidate) > parse_version(current)


# -------------------------------------------------------- release data
def parse_release(data: dict) -> Release:
    """Read the answer of GitHub's "latest release" request."""
    if not isinstance(data, dict) or not data.get("tag_name"):
        raise UpdateError("unexpected answer")
    tag = str(data["tag_name"])
    release = Release(
        version=".".join(str(n) for n in parse_version(tag)),
        tag=tag,
        notes=str(data.get("body") or "").strip(),
        page_url=str(data.get("html_url") or PAGE_URL),
    )
    assets = {a.get("name"): a for a in data.get("assets", []) if isinstance(a, dict)}
    for name, asset in assets.items():
        url = str(asset.get("browser_download_url") or "")
        # only ever download from this project's own release area
        if name and ASSET_PATTERN.match(name) and url.startswith(DOWNLOAD_PREFIX):
            sha = assets.get(name + ".sha256")
            sha_url = str((sha or {}).get("browser_download_url") or "")
            if sha_url.startswith(DOWNLOAD_PREFIX):
                release.zip_url, release.sha_url = url, sha_url
                release.zip_size = int(asset.get("size") or 0)
                break
    return release


def parse_release_json(raw: bytes) -> Release:
    try:
        return parse_release(json.loads(raw.decode("utf-8")))
    except (ValueError, UnicodeDecodeError):
        raise UpdateError("unexpected answer") from None


def expected_checksum(text: str) -> str:
    """The SHA-256 written in the .sha256 file ("<hash>  <file name>")."""
    match = re.search(r"\b([0-9a-fA-F]{64})\b", text)
    if not match:
        raise UpdateError("checksum file not understood")
    return match.group(1).lower()


# ---------------------------------------------------- where things are
def updates_dir() -> str:
    from . import config
    return os.path.join(config.config_dir(), "updates")


def result_file() -> str:
    return os.path.join(updates_dir(), "result.txt")


def can_self_update() -> bool:
    """True for the built Windows program in a folder that can be written to."""
    if not (getattr(sys, "frozen", False) and sys.platform == "win32"):
        return False
    from . import config
    folder = config.program_dir()
    probe = os.path.join(folder, ".write-test-%d" % os.getpid())
    try:
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("x")
        os.remove(probe)
        return True
    except OSError:
        return False


def read_previous_result() -> str:
    """What the helper script of the last update said ("" if nothing to report).

    The file is removed once read. "ok" means the update worked; any other
    text is the reason why the old version was put back."""
    path = result_file()
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read().strip()
        os.remove(path)
        return text
    except OSError:
        return ""


# ------------------------------------------------------------ unpacking
def stage(zip_path: str, destination: str) -> str:
    """Unpack the downloaded zip and return the folder that holds SlideCatch.exe.

    Refuses a zip whose entries would land outside ``destination`` (a
    damaged or malicious file) or that does not look like SlideCatch."""
    os.makedirs(destination, exist_ok=True)
    root = os.path.realpath(destination)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.infolist():
                target = os.path.realpath(os.path.join(root, member.filename))
                if target != root and not target.startswith(root + os.sep):
                    raise UpdateError("the zip file is not safe")
            if archive.testzip() is not None:
                raise UpdateError("the zip file is damaged")
            archive.extractall(root)
    except zipfile.BadZipFile:
        raise UpdateError("the zip file is damaged") from None
    for folder, _dirs, files in os.walk(root):
        if EXE_NAME in files and os.path.isdir(os.path.join(folder, "_internal")):
            return folder
    raise UpdateError("the zip file does not contain SlideCatch")


# ---------------------------------------------------------- the helper
SCRIPT = r"""@echo off
rem SlideCatch update helper. Arguments: 1 = program folder, 2 = new files folder,
rem 3 = program name, 4 = result file. Written by SlideCatch itself.
setlocal enableextensions
set "APP=%~1"
set "NEW=%~2"
set "EXE=%~3"
set "RESULT=%~4"
set /a tries=0

:wait
rem the program file cannot be renamed while SlideCatch is still running
ren "%APP%\%EXE%" "%EXE%.old" 2>nul
if exist "%APP%\%EXE%.old" goto swap
set /a tries+=1
if %tries% GEQ 90 goto timeout
ping -n 2 127.0.0.1 >nul
goto wait

:swap
if exist "%APP%\_internal.old" rd /s /q "%APP%\_internal.old"
ren "%APP%\_internal" "_internal.old" 2>nul
if exist "%APP%\_internal" goto locked
rem copies new files over, never deletes other folders (portable settings, sessions...)
robocopy "%NEW%" "%APP%" /E /NFL /NDL /NJH /NJS /NP /R:2 /W:1 >nul
if errorlevel 8 goto copyfailed
if not exist "%APP%\%EXE%" goto copyfailed
echo ok>"%RESULT%"
start "" "%APP%\%EXE%"
rd /s /q "%APP%\_internal.old" 2>nul
del /q "%APP%\%EXE%.old" 2>nul
rd /s /q "%NEW%" 2>nul
exit /b 0

:timeout
echo SlideCatch did not close in time>"%RESULT%"
start "" "%APP%\%EXE%"
exit /b 1

:locked
echo some files are in use (antivirus or file explorer?)>"%RESULT%"
goto rollback

:copyfailed
echo the new files could not be copied>"%RESULT%"

:rollback
rem put the old version back
if exist "%APP%\_internal.old" (
  if exist "%APP%\_internal" rd /s /q "%APP%\_internal"
  ren "%APP%\_internal.old" "_internal"
)
if exist "%APP%\%EXE%.old" (
  del /q "%APP%\%EXE%" 2>nul
  ren "%APP%\%EXE%.old" "%EXE%"
)
start "" "%APP%\%EXE%"
exit /b 1
"""


def write_script(folder: str) -> str:
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "apply-update.bat")
    with open(path, "w", encoding="ascii", newline="\r\n") as fh:
        fh.write(SCRIPT)
    return path


def start_script(program_dir: str, new_dir: str, folder: Optional[str] = None) -> subprocess.Popen:
    """Start the helper script, detached from this program. SlideCatch must
    quit right after: the script waits for that."""
    folder = folder or updates_dir()
    script = write_script(folder)
    os.makedirs(folder, exist_ok=True)
    os.makedirs(os.path.dirname(result_file()), exist_ok=True)     # the script writes its answer there
    flags = 0
    if sys.platform == "win32":
        flags = (subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
                 | subprocess.CREATE_NEW_PROCESS_GROUP)
    return subprocess.Popen([script, program_dir, new_dir, EXE_NAME, result_file()],
                            creationflags=flags, close_fds=True, cwd=folder)
