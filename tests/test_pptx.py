"""The built-in PowerPoint writer.

python-pptx (a test-only dependency, never shipped) reopens what SlideCatch
writes, the way PowerPoint would.
"""

import posixpath
import re
import zipfile

import pytest

from slidecatch.core.pptx import WIDE_16_9, PptxWriter, esc, fit, slide_size_for

# smallest valid PNG: 1 x 1 white pixel
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c63f8ffff3f0005fe02fea7d6a4b0000000"
    "0049454e44ae426082")


def write_deck(path, title="Weekly design review", notes=True):
    with PptxWriter(str(path), title=title) as deck:
        deck.add_title(title, "13/11/2026 · 2 slides")
        deck.add_picture(PNG, 1600, 900, notes="Captured at 14:02" if notes else "")
        deck.add_picture(PNG, 1024, 768, notes="Captured at 14:05" if notes else "",
                         name="Slide 2")
    return path


def test_zip_parts_and_links_are_complete(tmp_path):
    path = write_deck(tmp_path / "deck.pptx")
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        names = set(z.namelist())
        for part in ("[Content_Types].xml", "_rels/.rels", "ppt/presentation.xml",
                     "ppt/slides/slide1.xml", "ppt/slides/slide3.xml",
                     "ppt/notesSlides/notesSlide2.xml", "docProps/core.xml"):
            assert part in names
        types = z.read("[Content_Types].xml").decode()
        assert 'Extension="png"' in types
        # every relationship points to a part that exists
        for rels in (n for n in names if n.endswith(".rels")):
            base = posixpath.dirname(posixpath.dirname(rels))
            for target, mode in re.findall(r'Target="([^"]+)"(\s+TargetMode="External")?',
                                           z.read(rels).decode()):
                if mode:
                    continue
                full = posixpath.normpath(posixpath.join(base, target)).lstrip("/")
                assert full in names, "%s -> %s" % (rels, target)


def test_python_pptx_reads_the_deck(tmp_path):
    pptx = pytest.importorskip("pptx")
    path = write_deck(tmp_path / "deck.pptx")
    deck = pptx.Presentation(str(path))
    assert len(deck.slides) == 3
    assert deck.slide_width == WIDE_16_9[0]
    title_texts = [s.text_frame.text for s in deck.slides[0].shapes if s.has_text_frame]
    assert "Weekly design review" in title_texts
    picture = deck.slides[1].shapes[0]
    assert picture.shape_type == 13                      # MSO_SHAPE_TYPE.PICTURE
    assert picture.left >= 0 and picture.left + picture.width <= deck.slide_width
    assert deck.slides[1].notes_slide.notes_text_frame.text == "Captured at 14:02"
    assert deck.core_properties.title == "Weekly design review"


def test_without_notes_no_notes_parts(tmp_path):
    path = write_deck(tmp_path / "deck.pptx", notes=False)
    with zipfile.ZipFile(path) as z:
        assert not any("notesSlide" in n for n in z.namelist())


def test_arabic_title_is_right_to_left(tmp_path):
    path = write_deck(tmp_path / "deck.pptx", title="مراجعة التصميم الأسبوعية")
    with zipfile.ZipFile(path) as z:
        xml = z.read("ppt/slides/slide1.xml").decode("utf-8")
    assert 'rtl="1"' in xml and "مراجعة" in xml


def test_text_is_escaped(tmp_path):
    assert esc('a<b & "c">\x01') == "a&lt;b &amp; &quot;c&quot;&gt;"
    path = write_deck(tmp_path / "deck.pptx", title='R&D <draft> "v2"')
    pptx = pytest.importorskip("pptx")
    texts = [s.text_frame.text for s in pptx.Presentation(str(path)).slides[0].shapes
             if s.has_text_frame]
    assert 'R&D <draft> "v2"' in texts


def test_slide_size_follows_the_pictures():
    assert slide_size_for(16 / 9) == WIDE_16_9
    width, height = slide_size_for(4 / 3)
    assert width == WIDE_16_9[0] and abs(width / height - 4 / 3) < 0.01
    assert slide_size_for(0) == WIDE_16_9


def test_fit_keeps_proportions_and_centres():
    x, y, w, h = fit(1000, 500, 1600, 900)
    assert (w, h) == (1600, 800) and x == 0 and y == 50
    assert fit(0, 0, 10, 10) == (0, 0, 10, 10)


def test_failed_writing_leaves_a_closed_file(tmp_path):
    path = tmp_path / "deck.pptx"
    with pytest.raises(RuntimeError):
        with PptxWriter(str(path)) as deck:
            deck.add_picture(PNG, 10, 10)
            raise RuntimeError("stop")
    assert path.exists()        # the exporter removes such partial files (see test_export)
