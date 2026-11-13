"""Languages: every text translated, placeholders intact, plurals right."""

import os
import re

import pytest

from scripts.list_texts import texts
from slidecatch import APP_AUTHOR, i18n

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLACEHOLDER = re.compile(r"\{(\w+)\}")
CODE_TEXTS = texts()


@pytest.mark.parametrize("lang", ["fr", "ar"])
def test_every_text_is_translated(lang):
    table = i18n.table(lang)
    missing = [t for t in CODE_TEXTS if t not in table]
    assert not missing, "%d texts without %s translation: %s" % (len(missing), lang, missing[:5])


@pytest.mark.parametrize("lang", ["fr", "ar"])
def test_translations_keep_valid_placeholders(lang):
    """A translation may leave a value out ("شريحة واحدة") but never invent one."""
    for english, translated in i18n.table(lang).items():
        assert translated.strip(), english
        assert set(PLACEHOLDER.findall(translated)) <= set(PLACEHOLDER.findall(english)), english


@pytest.mark.parametrize("lang", ["fr", "ar"])
def test_no_unused_translations(lang):
    unused = [t for t in i18n.table(lang) if t not in CODE_TEXTS]
    assert not unused, unused[:5]


def test_plural_forms():
    i18n.set_language("en")
    assert i18n.trn("{n} slide", "{n} slides", 1) == "1 slide"
    assert i18n.trn("{n} slide", "{n} slides", 0) == "0 slides"
    i18n.set_language("fr")
    assert i18n.trn("{n} slide", "{n} slides", 0) == "0 diapositive"
    assert i18n.trn("{n} slide", "{n} slides", 2) == "2 diapositives"
    i18n.set_language("ar")
    assert i18n.trn("{n} slide", "{n} slides", 1) == "شريحة واحدة"
    assert i18n.trn("{n} slide", "{n} slides", 5) == "5 شرائح"
    assert i18n.trn("{n} slide", "{n} slides", 11) == "11 شريحة"
    assert i18n.trn("{n} slide", "{n} slides", 103) == "103 شرائح"
    assert i18n.trn("Save {n} picture", "Save {n} pictures", 4) == "حفظ 4 صور"


def test_missing_translation_shows_english():
    i18n.set_language("fr")
    assert i18n.tr("A text nobody translated") == "A text nobody translated"
    assert i18n.tr("Slide {n} saved", n=3) == "Diapositive 3 enregistrée"


def test_direction():
    assert i18n.is_rtl("ar") and not i18n.is_rtl("fr")
    i18n.set_language("ar")
    assert i18n.bidi_safe("Weekly review…").endswith("‎")
    assert i18n.bidi_safe("مراجعة") == "مراجعة"
    i18n.set_language("en")
    assert i18n.bidi_safe("مراجعة…").endswith("‏")
    assert i18n.bidi_safe("Weekly review") == "Weekly review"


@pytest.mark.parametrize("lang", sorted(i18n.LANGUAGES))
@pytest.mark.parametrize("stem", ["guide", "terms"])
def test_long_texts_exist_in_every_language(lang, stem):
    path = os.path.join(ROOT, "slidecatch", "resources", i18n.resource_name(stem, lang))
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    assert "{APP_VERSION}" in text and "{APP_AUTHOR}" in text


def test_dialogs_fill_in_the_author(qapp):
    from slidecatch.ui.dialogs import read_text
    assert APP_AUTHOR in read_text("terms")
    assert "{APP_" not in read_text("guide")
