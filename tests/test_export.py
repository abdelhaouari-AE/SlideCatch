"""Exporting a session to PowerPoint, PDF and pictures."""

import os
import zipfile

import pytest

from slidecatch import export


def test_pptx_export(make_session, tmp_path):
    pptx = pytest.importorskip("pptx")
    session = make_session([1, 2, 3])
    first = session.visible()[0]
    session.slides[session.visible()[1].id].deleted = True        # deleted: left out
    first.crop = [0.0, 0.0, 0.5, 0.5]                              # cropped at export
    path = str(tmp_path / "deck.pptx")
    done = []
    assert export.export(session, "pptx", path, progress=lambda a, b: done.append((a, b))) == path
    deck = pptx.Presentation(path)
    assert len(deck.slides) == 3                                   # title + 2 slides
    notes = deck.slides[1].notes_slide.notes_text_frame.text
    assert notes.startswith("Captured at ")
    with zipfile.ZipFile(path) as z:
        sizes = sorted(z.getinfo(n).file_size for n in z.namelist() if n.startswith("ppt/media/"))
    assert len(sizes) == 2
    assert done[-1] == (2, 2)
    assert session.state == "exported" and session.exported_to == path
    assert not os.path.exists(path + ".part")


def test_pptx_without_title_and_notes(make_session, tmp_path):
    pptx = pytest.importorskip("pptx")
    session = make_session([1, 2])
    path = str(tmp_path / "plain.pptx")
    export.export(session, "pptx", path, title_slide=False, notes=False)
    deck = pptx.Presentation(path)
    assert len(deck.slides) == 2
    assert not deck.slides[0].has_notes_slide


def test_pdf_export(make_session, tmp_path):
    session = make_session([1, 2, 3])
    path = str(tmp_path / "deck.pdf")
    export.export(session, "pdf", path)
    with open(path, "rb") as fh:
        data = fh.read()
    assert data.startswith(b"%PDF")
    assert data.count(b"/Type /Page\n") + data.count(b"/Type /Page\r") + \
        data.count(b"/Type /Page ") + data.count(b"/Type /Page/") + \
        data.count(b"/Type /Page>") >= 4                        # title page + 3 slides


def test_png_export(make_session, tmp_path):
    session = make_session([1, 2, 3])
    folder = str(tmp_path / "pictures")
    export.export(session, "png", folder)
    assert sorted(os.listdir(folder)) == ["Slide 01.png", "Slide 02.png", "Slide 03.png"]


def test_cancelled_export_leaves_nothing(make_session, tmp_path):
    session = make_session([1, 2, 3])
    path = str(tmp_path / "deck.pptx")
    assert export.export(session, "pptx", path, cancelled=lambda: True) == ""
    assert not os.path.exists(path) and not os.path.exists(path + ".part")
    assert session.state != "exported"


def test_nothing_to_export(make_session, tmp_path):
    session = make_session([])
    with pytest.raises(ValueError):
        export.export(session, "pdf", str(tmp_path / "x.pdf"))


def test_unknown_format(make_session, tmp_path):
    with pytest.raises(ValueError):
        export.export(make_session([1]), "docx", str(tmp_path / "x.docx"))


def test_default_file_name(make_session):
    session = make_session([1], name="Design review: rev B")
    name = export.default_file_name(session, "pptx")
    assert name.startswith("Design review rev B") and name.endswith(".pptx")
    assert ":" not in name
