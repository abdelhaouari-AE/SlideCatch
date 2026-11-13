"""Sessions: every slide is on disk the moment it is caught."""

import json
import os

from slidecatch.core import session as session_mod
from slidecatch.core.session import Session, atomic_write, find_unfinished, safe_name


def add(session, n=1, **kwargs):
    return session.add_slide(b"PNG%d" % n, b"THUMB%d" % n, bytes([n]) * 16, 1600, 900, **kwargs)


def test_create_makes_a_named_folder(sessions_root):
    s = Session.create(sessions_root, "Weekly review: rev B / final?")
    assert os.path.isdir(os.path.join(s.folder, session_mod.SLIDES_DIR))
    assert os.path.isfile(os.path.join(s.folder, session_mod.SESSION_FILE))
    name = os.path.basename(s.folder)
    assert "Weekly review" in name and not any(c in name for c in '<>:"/\\|?*')


def test_same_name_twice_gets_a_new_folder(sessions_root):
    a = Session.create(sessions_root, "Review")
    b = Session.create(sessions_root, "Review")
    assert a.folder != b.folder


def test_slides_survive_reloading(sessions_root):
    s = Session.create(sessions_root, "Review")
    first = add(s, 1)
    second = add(s, 2, manual=True, build_of=first.id)
    loaded = Session.load(s.folder)
    assert [r.id for r in loaded.visible()] == [first.id, second.id]
    assert loaded.slides[second.id].manual and loaded.slides[second.id].build_of == first.id
    with open(loaded.path(loaded.slides[first.id].file), "rb") as fh:
        assert fh.read() == b"PNG1"
    assert loaded.read_small(first.id) == bytes([1]) * 16


def test_picture_saved_before_a_crash_is_recovered(sessions_root):
    """The picture reached the disk but session.json was not updated."""
    s = Session.create(sessions_root, "Review")
    add(s, 1)
    orphan = os.path.join(s.folder, session_mod.SLIDES_DIR, "0002.png")
    with open(orphan, "wb") as fh:
        fh.write(b"PNG2")
    loaded = Session.load(s.folder)
    assert [r.id for r in loaded.visible()] == [1, 2]
    assert loaded.next_id == 3
    with open(os.path.join(s.folder, session_mod.SESSION_FILE), encoding="utf-8") as fh:
        assert "2" in json.load(fh)["slides"]         # written back


def test_atomic_write_leaves_no_temporary_file(tmp_path):
    target = tmp_path / "a.bin"
    atomic_write(str(target), b"one")
    atomic_write(str(target), b"two")
    assert target.read_bytes() == b"two"
    assert os.listdir(tmp_path) == ["a.bin"]


def test_safe_name():
    assert safe_name('a<b>c:d"e/f\\g|h?i*j') == "a b c d e f g h i j"
    assert safe_name("   ") == "Session"
    assert safe_name("", fallback="Slides") == "Slides"
    assert len(safe_name("x" * 200)) <= 60
    assert safe_name("CON") != "CON"                 # reserved name on Windows


def test_delete_merge_and_undo(sessions_root):
    s = Session.create(sessions_root, "Review")
    ids = [add(s, n).id for n in range(1, 5)]
    before = s.snapshot()
    s.slides[ids[1]].deleted = True
    s.order.reverse()
    s.merge_build(ids[2], ids[3])
    assert [r.id for r in s.visible()] == [ids[3], ids[0]]
    s.restore(before)
    assert [r.id for r in s.visible()] == ids


def test_build_groups(sessions_root):
    s = Session.create(sessions_root, "Review")
    a = add(s, 1)
    b = add(s, 2, build_of=a.id)
    c = add(s, 3, build_of=b.id)
    add(s, 4)
    assert s.build_groups() == [[a.id, b.id, c.id]]
    s.merge_build(a.id, b.id)
    assert s.build_groups() == [[b.id, c.id]]


def test_find_unfinished(sessions_root):
    done = Session.create(sessions_root, "Exported")
    add(done)
    done.set_state("exported")
    empty = Session.create(sessions_root, "Nothing caught")
    left = Session.create(sessions_root, "Left open")
    add(left)
    found = find_unfinished(sessions_root)
    assert [s.folder for s in found] == [left.folder]
    assert empty.visible_count() == 0
    assert find_unfinished(os.path.join(sessions_root, "missing")) == []


def test_broken_session_file_is_skipped(sessions_root):
    s = Session.create(sessions_root, "Broken")
    add(s)
    with open(os.path.join(s.folder, session_mod.SESSION_FILE), "w") as fh:
        fh.write("{ not json")
    assert find_unfinished(sessions_root) == []
