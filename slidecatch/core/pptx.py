"""A small PowerPoint (.pptx) writer using only the Python standard library.

A .pptx file is a zip of XML files. SlideCatch only needs pictures on blank
slides, an optional title slide and speaker notes, so it writes those parts
itself instead of shipping python-pptx with lxml and Pillow (about 10 MB).

The structure follows what PowerPoint itself writes: one slide master, one
blank layout, a theme, and a notes master when there are notes. The tests
open the result with python-pptx (a test-only dependency) to check it.

Usage::

    with PptxWriter("deck.pptx", width_emu, height_emu) as deck:
        deck.add_title("Weekly design review", "13 Nov 2026 - 24 slides")
        deck.add_picture(png_bytes, pixel_width, pixel_height, notes="Captured at 14:02")
"""

import re
import zipfile
from datetime import datetime, timezone

EMU_PER_INCH = 914400
WIDE_16_9 = (12192000, 6858000)          # 13.333 x 7.5 inches, PowerPoint's default

NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
CT = "application/vnd.openxmlformats-officedocument.presentationml."
XML_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'

_BAD_XML_CHARS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_RTL_CHARS = re.compile("[֐-ࣿיִ-﷿ﹰ-﻿]")


def esc(text: str) -> str:
    """Text made safe for XML content and attribute values."""
    text = _BAD_XML_CHARS.sub("", str(text))
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def slide_size_for(aspect: float):
    """Slide size (EMU) for pictures of this width/height ratio, 13.333 in wide."""
    if not aspect or aspect <= 0:
        return WIDE_16_9
    width = WIDE_16_9[0]
    height = int(round(width / aspect / 12700.0)) * 12700      # whole points
    return width, max(914400, min(height, 51206400))


def fit(pic_w: int, pic_h: int, box_w: int, box_h: int):
    """(x, y, w, h) of a picture scaled to fit a box and centred in it."""
    if pic_w <= 0 or pic_h <= 0:
        return 0, 0, box_w, box_h
    scale = min(box_w / pic_w, box_h / pic_h)
    w, h = int(pic_w * scale), int(pic_h * scale)
    return (box_w - w) // 2, (box_h - h) // 2, w, h


def _theme(name: str) -> str:
    fonts = ('<a:latin typeface="Segoe UI"/><a:ea typeface=""/><a:cs typeface=""/>'
             '<a:font script="Arab" typeface="Segoe UI"/>')
    plain_fill = '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    line = '<a:ln w="%d"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
    return (
        XML_HEAD + '<a:theme xmlns:a="%s" name="%s"><a:themeElements>' % (NS_A, esc(name))
        + '<a:clrScheme name="SlideCatch">'
        '<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>'
        '<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>'
        '<a:dk2><a:srgbClr val="242424"/></a:dk2><a:lt2><a:srgbClr val="F5F5F5"/></a:lt2>'
        '<a:accent1><a:srgbClr val="5B5FC7"/></a:accent1>'
        '<a:accent2><a:srgbClr val="444791"/></a:accent2>'
        '<a:accent3><a:srgbClr val="7F85F5"/></a:accent3>'
        '<a:accent4><a:srgbClr val="C4314B"/></a:accent4>'
        '<a:accent5><a:srgbClr val="237B4B"/></a:accent5>'
        '<a:accent6><a:srgbClr val="E97548"/></a:accent6>'
        '<a:hlink><a:srgbClr val="5B5FC7"/></a:hlink>'
        '<a:folHlink><a:srgbClr val="444791"/></a:folHlink></a:clrScheme>'
        '<a:fontScheme name="SlideCatch"><a:majorFont>' + fonts + '</a:majorFont>'
        '<a:minorFont>' + fonts + '</a:minorFont></a:fontScheme>'
        '<a:fmtScheme name="SlideCatch"><a:fillStyleLst>' + plain_fill * 3 + '</a:fillStyleLst>'
        '<a:lnStyleLst>' + line % 9525 + line % 25400 + line % 38100 + '</a:lnStyleLst>'
        '<a:effectStyleLst>' + '<a:effectStyle><a:effectLst/></a:effectStyle>' * 3
        + '</a:effectStyleLst><a:bgFillStyleLst>' + plain_fill * 3 + '</a:bgFillStyleLst>'
        '</a:fmtScheme></a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/></a:theme>')


def _text_style(size: int) -> str:
    return ('<a:lvl1pPr marL="0" algn="l" defTabSz="914400" rtl="0" eaLnBrk="1" '
            'latinLnBrk="0" hangingPunct="1"><a:defRPr sz="%d" kern="1200">'
            '<a:solidFill><a:schemeClr val="tx1"/></a:solidFill><a:latin typeface="+mn-lt"/>'
            '<a:ea typeface="+mn-ea"/><a:cs typeface="+mn-cs"/></a:defRPr></a:lvl1pPr>' % size)


_EMPTY_TREE = ('<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/>'
               '</p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
               '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>')
_CLR_MAP = ('bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" '
            'accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" '
            'hlink="hlink" folHlink="folHlink"')
_NS_DECL = 'xmlns:a="%s" xmlns:r="%s" xmlns:p="%s"' % (NS_A, NS_R, NS_P)


def _rels(items) -> str:
    body = "".join('<Relationship Id="%s" Type="%s" Target="%s"/>' % (rid, kind, target)
                   for rid, kind, target in items)
    return XML_HEAD + '<Relationships xmlns="%s">%s</Relationships>' % (NS_REL, body)


def _paragraph(text: str, size: int, bold: bool = False, color: str = "242424",
               align: str = "ctr") -> str:
    rtl = bool(_RTL_CHARS.search(text))
    lang = "ar-MA" if rtl else "en-US"
    return ('<a:p><a:pPr algn="%s"%s/><a:r><a:rPr lang="%s" sz="%d" b="%d" dirty="0">'
            '<a:solidFill><a:srgbClr val="%s"/></a:solidFill></a:rPr><a:t>%s</a:t></a:r></a:p>'
            % (align, ' rtl="1"' if rtl else "", lang, size, 1 if bold else 0, color, esc(text)))


class PptxWriter:
    """Writes a presentation slide by slide (pictures stay on disk, not in memory)."""

    def __init__(self, path: str, width_emu: int = WIDE_16_9[0], height_emu: int = WIDE_16_9[1],
                 title: str = "", author: str = "SlideCatch"):
        self.path = path
        self.width, self.height = int(width_emu), int(height_emu)
        self.title, self.author = title, author
        self._zip = zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, allowZip64=True)
        self._slides = []          # (number, has_notes)
        self._images = 0
        self._closed = False

    # ---------------------------------------------------------------- api
    def add_picture(self, png: bytes, pixel_width: int, pixel_height: int, notes: str = "",
                    name: str = "") -> int:
        self._images += 1
        image_name = "image%d.png" % self._images
        self._zip.writestr("ppt/media/" + image_name, png, compress_type=zipfile.ZIP_STORED)
        x, y, w, h = fit(pixel_width, pixel_height, self.width, self.height)
        number = len(self._slides) + 1
        label = name or "Slide %d" % number
        shapes = ('<p:pic><p:nvPicPr><p:cNvPr id="2" name="%s" descr="%s"/><p:cNvPicPr>'
                  '<a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
                  '<p:blipFill><a:blip r:embed="rId2"/><a:stretch><a:fillRect/></a:stretch>'
                  '</p:blipFill><p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/>'
                  '</a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>'
                  % (esc(label), esc(label), x, y, w, h))
        extra = [("rId2", REL + "image", "../media/" + image_name)]
        self._write_slide(number, shapes, extra, notes)
        return number

    def add_title(self, title: str, subtitle: str = "", notes: str = "") -> int:
        number = len(self._slides) + 1
        margin = self.width // 12
        box_w = self.width - 2 * margin
        title_h = self.height // 4
        title_y = self.height // 2 - title_h
        sub_h = self.height // 6
        sub_y = self.height // 2 + self.height // 40
        shapes = (self._text_box(2, "Title", margin, title_y, box_w, title_h,
                                 _paragraph(title or " ", 4000, bold=True), anchor="b")
                  + self._text_box(3, "Subtitle", margin, sub_y, box_w, sub_h,
                                   _paragraph(subtitle or " ", 2000, color="616161"), anchor="t"))
        self._write_slide(number, shapes, [], notes)
        return number

    def close(self):
        if self._closed:
            return
        try:
            self._write_package()
        finally:
            self._zip.close()
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.close()
        else:
            self._zip.close()
            self._closed = True

    # ------------------------------------------------------------ slides
    @staticmethod
    def _text_box(shape_id, name, x, y, w, h, paragraphs, anchor="ctr"):
        return ('<p:sp><p:nvSpPr><p:cNvPr id="%d" name="%s"/><p:cNvSpPr txBox="1"/><p:nvPr/>'
                '</p:nvSpPr><p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/>'
                '</a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>'
                '<p:txBody><a:bodyPr wrap="square" lIns="91440" tIns="45720" rIns="91440" '
                'bIns="45720" anchor="%s"><a:normAutofit/></a:bodyPr><a:lstStyle/>%s'
                '</p:txBody></p:sp>' % (shape_id, name, x, y, w, h, anchor, paragraphs))

    def _write_slide(self, number, shapes, extra_rels, notes):
        xml = (XML_HEAD + '<p:sld %s><p:cSld>' % _NS_DECL + _EMPTY_TREE + shapes
               + '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>')
        self._zip.writestr("ppt/slides/slide%d.xml" % number, xml)
        rels = [("rId1", REL + "slideLayout", "../slideLayouts/slideLayout1.xml")] + extra_rels
        has_notes = bool(notes and notes.strip())
        if has_notes:
            rels.append(("rId9", REL + "notesSlide", "../notesSlides/notesSlide%d.xml" % number))
            self._write_notes(number, notes)
        self._zip.writestr("ppt/slides/_rels/slide%d.xml.rels" % number, _rels(rels))
        self._slides.append((number, has_notes))

    def _write_notes(self, number, notes):
        paragraphs = "".join(_paragraph(line, 1200, align="l") for line in notes.splitlines()
                             if line.strip()) or _paragraph(" ", 1200, align="l")
        xml = (XML_HEAD + '<p:notes %s><p:cSld>' % _NS_DECL + _EMPTY_TREE
               + '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Slide Image Placeholder 1"/><p:cNvSpPr>'
               '<a:spLocks noGrp="1" noRot="1" noChangeAspect="1"/></p:cNvSpPr><p:nvPr>'
               '<p:ph type="sldImg" idx="2"/></p:nvPr></p:nvSpPr><p:spPr/></p:sp>'
               '<p:sp><p:nvSpPr><p:cNvPr id="3" name="Notes Placeholder 2"/><p:cNvSpPr>'
               '<a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph type="body" idx="1"/></p:nvPr>'
               '</p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/>' + paragraphs
               + '</p:txBody></p:sp></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/>'
               '</p:clrMapOvr></p:notes>')
        self._zip.writestr("ppt/notesSlides/notesSlide%d.xml" % number, xml)
        self._zip.writestr("ppt/notesSlides/_rels/notesSlide%d.xml.rels" % number, _rels([
            ("rId1", REL + "notesMaster", "../notesMasters/notesMaster1.xml"),
            ("rId2", REL + "slide", "../slides/slide%d.xml" % number)]))

    # ----------------------------------------------------------- package
    def _write_package(self):
        z = self._zip
        any_notes = any(has for _, has in self._slides)
        slide_ids = "".join('<p:sldId id="%d" r:id="rIdS%d"/>' % (255 + n, n)
                            for n, _ in self._slides)
        notes_list = ('<p:notesMasterIdLst><p:notesMasterId r:id="rIdN"/></p:notesMasterIdLst>'
                      if any_notes else "")
        presentation = (
            XML_HEAD + '<p:presentation %s saveSubsetFonts="1">' % _NS_DECL
            + '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rIdM"/></p:sldMasterIdLst>'
            + notes_list
            + ('<p:sldIdLst>%s</p:sldIdLst>' % slide_ids if slide_ids else "")
            + '<p:sldSz cx="%d" cy="%d"/><p:notesSz cx="6858000" cy="9144000"/>'
            % (self.width, self.height)
            + '<p:defaultTextStyle>' + _text_style(1800) + '</p:defaultTextStyle>'
            + '</p:presentation>')
        z.writestr("ppt/presentation.xml", presentation)

        rels = [("rIdM", REL + "slideMaster", "slideMasters/slideMaster1.xml"),
                ("rIdT", REL + "theme", "theme/theme1.xml"),
                ("rIdP", REL + "presProps", "presProps.xml"),
                ("rIdV", REL + "viewProps", "viewProps.xml"),
                ("rIdY", REL + "tableStyles", "tableStyles.xml")]
        rels += [("rIdS%d" % n, REL + "slide", "slides/slide%d.xml" % n) for n, _ in self._slides]
        if any_notes:
            rels.append(("rIdN", REL + "notesMaster", "notesMasters/notesMaster1.xml"))
        z.writestr("ppt/_rels/presentation.xml.rels", _rels(rels))

        master = (XML_HEAD + '<p:sldMaster %s><p:cSld><p:bg><p:bgRef idx="1001">'
                  '<a:schemeClr val="bg1"/></p:bgRef></p:bg>' % _NS_DECL + _EMPTY_TREE
                  + '</p:spTree></p:cSld><p:clrMap %s/>' % _CLR_MAP
                  + '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/>'
                  '</p:sldLayoutIdLst><p:txStyles><p:titleStyle>' + _text_style(4400)
                  + '</p:titleStyle><p:bodyStyle>' + _text_style(2800)
                  + '</p:bodyStyle><p:otherStyle>' + _text_style(1800)
                  + '</p:otherStyle></p:txStyles></p:sldMaster>')
        z.writestr("ppt/slideMasters/slideMaster1.xml", master)
        z.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", _rels([
            ("rId1", REL + "slideLayout", "../slideLayouts/slideLayout1.xml"),
            ("rId2", REL + "theme", "../theme/theme1.xml")]))

        layout = (XML_HEAD + '<p:sldLayout %s type="blank" preserve="1"><p:cSld name="Blank">'
                  % _NS_DECL + _EMPTY_TREE + '</p:spTree></p:cSld><p:clrMapOvr>'
                  '<a:masterClrMapping/></p:clrMapOvr></p:sldLayout>')
        z.writestr("ppt/slideLayouts/slideLayout1.xml", layout)
        z.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", _rels([
            ("rId1", REL + "slideMaster", "../slideMasters/slideMaster1.xml")]))
        z.writestr("ppt/theme/theme1.xml", _theme("SlideCatch"))

        if any_notes:
            notes_master = (
                XML_HEAD + '<p:notesMaster %s><p:cSld><p:bg><p:bgRef idx="1001">'
                '<a:schemeClr val="bg1"/></p:bgRef></p:bg>' % _NS_DECL + _EMPTY_TREE
                + '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Slide Image Placeholder 1"/>'
                '<p:cNvSpPr><a:spLocks noGrp="1" noRot="1" noChangeAspect="1"/></p:cNvSpPr>'
                '<p:nvPr><p:ph type="sldImg" idx="2"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm>'
                '<a:off x="381000" y="685800"/><a:ext cx="6096000" cy="3429000"/></a:xfrm>'
                '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr></p:sp>'
                '<p:sp><p:nvSpPr><p:cNvPr id="3" name="Notes Placeholder 2"/><p:cNvSpPr>'
                '<a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph type="body" sz="quarter" '
                'idx="1"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x="685800" y="4343400"/>'
                '<a:ext cx="5486400" cy="4114800"/></a:xfrm><a:prstGeom prst="rect">'
                '<a:avLst/></a:prstGeom></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/>'
                '<a:p><a:endParaRPr lang="en-US"/></a:p></p:txBody></p:sp>'
                '</p:spTree></p:cSld><p:clrMap %s/><p:notesStyle>' % _CLR_MAP
                + _text_style(1200) + '</p:notesStyle></p:notesMaster>')
            z.writestr("ppt/notesMasters/notesMaster1.xml", notes_master)
            z.writestr("ppt/notesMasters/_rels/notesMaster1.xml.rels", _rels([
                ("rId1", REL + "theme", "../theme/theme2.xml")]))
            z.writestr("ppt/theme/theme2.xml", _theme("SlideCatch Notes"))

        z.writestr("ppt/presProps.xml", XML_HEAD + '<p:presentationPr %s/>' % _NS_DECL)
        z.writestr("ppt/viewProps.xml", XML_HEAD + '<p:viewPr %s><p:normalViewPr>'
                   '<p:restoredLeft sz="15620"/><p:restoredTop sz="94660"/></p:normalViewPr>'
                   '<p:gridSpacing cx="76200" cy="76200"/></p:viewPr>' % _NS_DECL)
        z.writestr("ppt/tableStyles.xml", XML_HEAD + '<a:tblStyleLst xmlns:a="%s" '
                   'def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>' % NS_A)

        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        z.writestr("docProps/core.xml", XML_HEAD + (
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/'
            'metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/'
            'dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            '<dc:title>%s</dc:title><dc:creator>%s</dc:creator><cp:lastModifiedBy>%s'
            '</cp:lastModifiedBy><cp:revision>1</cp:revision>'
            '<dcterms:created xsi:type="dcterms:W3CDTF">%s</dcterms:created>'
            '<dcterms:modified xsi:type="dcterms:W3CDTF">%s</dcterms:modified>'
            '</cp:coreProperties>' % (esc(self.title), esc(self.author), esc(self.author),
                                      stamp, stamp)))
        notes_count = sum(1 for _, has in self._slides if has)
        z.writestr("docProps/app.xml", XML_HEAD + (
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/'
            'extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/'
            '2006/docPropsVTypes"><Application>SlideCatch</Application>'
            '<PresentationFormat>Custom</PresentationFormat><Slides>%d</Slides>'
            '<Notes>%d</Notes><HiddenSlides>0</HiddenSlides></Properties>'
            % (len(self._slides), notes_count)))

        z.writestr("_rels/.rels", _rels([
            ("rId1", REL + "officeDocument", "ppt/presentation.xml"),
            ("rId2", "http://schemas.openxmlformats.org/package/2006/relationships/metadata/"
                     "core-properties", "docProps/core.xml"),
            ("rId3", REL + "extended-properties", "docProps/app.xml")]))

        overrides = [
            ("/ppt/presentation.xml", CT + "presentation.main+xml"),
            ("/ppt/slideMasters/slideMaster1.xml", CT + "slideMaster+xml"),
            ("/ppt/slideLayouts/slideLayout1.xml", CT + "slideLayout+xml"),
            ("/ppt/theme/theme1.xml", "application/vnd.openxmlformats-officedocument.theme+xml"),
            ("/ppt/presProps.xml", CT + "presProps+xml"),
            ("/ppt/viewProps.xml", CT + "viewProps+xml"),
            ("/ppt/tableStyles.xml", CT + "tableStyles+xml"),
            ("/docProps/core.xml", "application/vnd.openxmlformats-package.core-properties+xml"),
            ("/docProps/app.xml",
             "application/vnd.openxmlformats-officedocument.extended-properties+xml"),
        ]
        overrides += [("/ppt/slides/slide%d.xml" % n, CT + "slide+xml") for n, _ in self._slides]
        if any_notes:
            overrides += [("/ppt/notesMasters/notesMaster1.xml", CT + "notesMaster+xml"),
                          ("/ppt/theme/theme2.xml",
                           "application/vnd.openxmlformats-officedocument.theme+xml")]
            overrides += [("/ppt/notesSlides/notesSlide%d.xml" % n, CT + "notesSlide+xml")
                          for n, has in self._slides if has]
        types = ('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                 '<Default Extension="png" ContentType="image/png"/>'
                 '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
                 'relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                 + "".join('<Override PartName="%s" ContentType="%s"/>' % item
                           for item in overrides) + '</Types>')
        z.writestr("[Content_Types].xml", XML_HEAD + types)
