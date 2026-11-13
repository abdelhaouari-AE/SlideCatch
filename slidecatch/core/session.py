"""Crash-safe session folder: every slide is on disk the moment it is caught.

A session is one capture (one meeting). Its folder holds::

    session.json          name, times, slide order and edits
    slides/0001.png       full-size picture of slide 1
    slides/0001.thumb.png small picture for the review screen
    slides/0001.small     128 x 72 grey copy used to recognise the slide

Files are written to a temporary name and then renamed, so a crash or a
power cut never leaves a half-written file. If SlideCatch stops before the
session was exported, the next start offers to restore it; pictures saved
just before a crash but missing from session.json are found and added back.
"""

import json
import os
import re
import shutil
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

SESSION_FILE = "session.json"
SLIDES_DIR = "slides"
FORMAT_VERSION = 1

STATE_CAPTURING = "capturing"
STATE_STOPPED = "stopped"
STATE_EXPORTED = "exported"


def atomic_write(path: str, data: bytes):
    """Write ``data`` to ``path`` without ever leaving a partial file."""
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def safe_name(text: str, fallback: str = "Session", limit: int = 60) -> str:
    """A name usable as a Windows file or folder name."""
    name = _UNSAFE.sub(" ", text or "").strip()
    name = re.sub(r"\s+", " ", name).strip(" .")
    if name.upper() in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"(COM|LPT)\d", name.upper()):
        name = "_" + name
    return (name[:limit].rstrip(" .") or fallback)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class SlideRecord:
    id: int
    file: str                       # relative to the session folder
    thumb: str
    small_file: str
    time: str                       # when the slide was first caught (local ISO time)
    width: int = 0
    height: int = 0
    manual: bool = False            # captured with "Capture this slide now"
    deleted: bool = False
    merged_into: Optional[int] = None   # earlier step of an animation, kept out
    build_of: Optional[int] = None      # this slide adds content to slide build_of
    crop: Optional[List[float]] = None  # [x, y, w, h] fractions, applied at export
    refined: int = 0

    @staticmethod
    def from_dict(data: dict) -> "SlideRecord":
        known = SlideRecord.__dataclass_fields__
        return SlideRecord(**{k: v for k, v in data.items() if k in known})


@dataclass
class Session:
    folder: str
    name: str = ""
    created: str = field(default_factory=now_iso)
    state: str = STATE_CAPTURING
    order: List[int] = field(default_factory=list)
    slides: Dict[int, SlideRecord] = field(default_factory=dict)
    target: dict = field(default_factory=dict)
    next_id: int = 1
    exported_to: str = ""
    ended: str = ""

    def __post_init__(self):
        self._lock = threading.RLock()

    # ------------------------------------------------------------ create
    @staticmethod
    def create(root: str, name: str, target: Optional[dict] = None) -> "Session":
        os.makedirs(root, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        base = "%s %s" % (stamp, safe_name(name, fallback="Session"))
        folder = os.path.join(root, base)
        suffix = 2
        while os.path.exists(folder):
            folder = os.path.join(root, "%s (%d)" % (base, suffix))
            suffix += 1
        os.makedirs(os.path.join(folder, SLIDES_DIR))
        session = Session(folder=folder, name=(name or "").strip(), target=dict(target or {}))
        session.save()
        return session

    @staticmethod
    def load(folder: str) -> "Session":
        with open(os.path.join(folder, SESSION_FILE), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        slides = {int(k): SlideRecord.from_dict(v) for k, v in data.get("slides", {}).items()}
        session = Session(
            folder=folder,
            name=data.get("name", ""),
            created=data.get("created", now_iso()),
            state=data.get("state", STATE_STOPPED),
            order=[int(i) for i in data.get("order", []) if int(i) in slides],
            slides=slides,
            target=data.get("target", {}),
            next_id=int(data.get("next_id", max(slides, default=0) + 1)),
            exported_to=data.get("exported_to", ""),
            ended=data.get("ended", ""),
        )
        session._recover_orphans()
        return session

    def _recover_orphans(self):
        """Add pictures that reached the disk but not session.json (crash)."""
        slides_dir = os.path.join(self.folder, SLIDES_DIR)
        if not os.path.isdir(slides_dir):
            return
        known_files = {rec.file for rec in self.slides.values()}
        added = False
        for name in sorted(os.listdir(slides_dir)):
            match = re.fullmatch(r"(\d{4,})\.png", name)
            rel = SLIDES_DIR + "/" + name
            if not match or rel in known_files:
                continue
            number = int(match.group(1))
            if number in self.slides:
                continue
            stamp = datetime.fromtimestamp(os.path.getmtime(os.path.join(slides_dir, name)))
            self.slides[number] = SlideRecord(
                id=number, file=rel, thumb=SLIDES_DIR + "/%04d.thumb.png" % number,
                small_file=SLIDES_DIR + "/%04d.small" % number,
                time=stamp.isoformat(timespec="seconds"))
            self.order.append(number)
            self.next_id = max(self.next_id, number + 1)
            added = True
        if added:
            self.save()

    # -------------------------------------------------------------- save
    def to_dict(self) -> dict:
        return {
            "app": "SlideCatch",
            "format": FORMAT_VERSION,
            "name": self.name,
            "created": self.created,
            "ended": self.ended,
            "state": self.state,
            "order": list(self.order),
            "next_id": self.next_id,
            "target": self.target,
            "exported_to": self.exported_to,
            "slides": {str(k): asdict(v) for k, v in self.slides.items()},
        }

    def save(self):
        with self._lock:
            data = json.dumps(self.to_dict(), ensure_ascii=False, indent=1).encode("utf-8")
            atomic_write(os.path.join(self.folder, SESSION_FILE), data)

    # ------------------------------------------------------------ slides
    def path(self, relative: str) -> str:
        return os.path.join(self.folder, *relative.split("/"))

    def add_slide(self, png: bytes, thumb_png: bytes, small: bytes, width: int, height: int,
                  manual: bool = False, build_of: Optional[int] = None,
                  when: Optional[str] = None) -> SlideRecord:
        with self._lock:
            number = self.next_id
            self.next_id += 1
            record = SlideRecord(
                id=number,
                file=SLIDES_DIR + "/%04d.png" % number,
                thumb=SLIDES_DIR + "/%04d.thumb.png" % number,
                small_file=SLIDES_DIR + "/%04d.small" % number,
                time=when or now_iso(),
                width=width, height=height, manual=manual, build_of=build_of)
            atomic_write(self.path(record.small_file), small)
            atomic_write(self.path(record.thumb), thumb_png)
            atomic_write(self.path(record.file), png)       # the picture last: it marks the slide
            self.slides[number] = record
            self.order.append(number)
            self.save()
            return record

    def replace_image(self, slide_id: int, png: bytes, thumb_png: bytes, small: bytes,
                      width: int, height: int):
        with self._lock:
            record = self.slides[slide_id]
            atomic_write(self.path(record.small_file), small)
            atomic_write(self.path(record.thumb), thumb_png)
            atomic_write(self.path(record.file), png)
            record.width, record.height = width, height
            record.refined += 1
            self.save()

    def read_small(self, slide_id: int) -> Optional[bytes]:
        try:
            with open(self.path(self.slides[slide_id].small_file), "rb") as fh:
                return fh.read()
        except (OSError, KeyError):
            return None

    def visible(self) -> List[SlideRecord]:
        """Slides kept, in presentation order."""
        with self._lock:
            return [self.slides[i] for i in self.order
                    if i in self.slides and not self.slides[i].deleted]

    def visible_count(self) -> int:
        return len(self.visible())

    def merge_build(self, earlier_id: int, final_id: int):
        """Keep only the final step of an animation (the earlier step is hidden)."""
        with self._lock:
            record = self.slides[earlier_id]
            record.deleted = True
            record.merged_into = final_id
            self.save()

    def build_groups(self) -> List[List[int]]:
        """Runs of visible slides where each one adds content to the previous one."""
        groups, run = [], []
        for record in self.visible():
            if run and record.build_of == run[-1]:
                run.append(record.id)
            else:
                if len(run) > 1:
                    groups.append(run)
                run = [record.id]
        if len(run) > 1:
            groups.append(run)
        return groups

    # ------------------------------------------------------- undo support
    def snapshot(self) -> dict:
        with self._lock:
            return {
                "order": list(self.order),
                "slides": {k: (v.deleted, v.merged_into, list(v.crop) if v.crop else None)
                           for k, v in self.slides.items()},
                "name": self.name,
            }

    def restore(self, snap: dict):
        with self._lock:
            self.order = [i for i in snap["order"] if i in self.slides]
            for key, (deleted, merged_into, crop) in snap["slides"].items():
                if key in self.slides:
                    record = self.slides[key]
                    record.deleted, record.merged_into = deleted, merged_into
                    record.crop = list(crop) if crop else None
            self.name = snap.get("name", self.name)
            self.save()

    # ------------------------------------------------------------- state
    def set_state(self, state: str):
        with self._lock:
            self.state = state
            if state != STATE_CAPTURING:
                self.ended = now_iso()
            self.save()

    def delete_files(self):
        shutil.rmtree(self.folder, ignore_errors=True)


def find_unfinished(root: str) -> List[Session]:
    """Sessions with slides that were never exported, newest first."""
    found = []
    if not root or not os.path.isdir(root):
        return found
    for name in os.listdir(root):
        folder = os.path.join(root, name)
        if not os.path.isfile(os.path.join(folder, SESSION_FILE)):
            continue
        try:
            session = Session.load(folder)
        except (OSError, ValueError, TypeError, KeyError):
            continue
        if session.state != STATE_EXPORTED and session.visible_count() > 0:
            found.append(session)
    found.sort(key=lambda s: s.created, reverse=True)
    return found
