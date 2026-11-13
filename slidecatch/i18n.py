"""Interface languages: English (default), French and Arabic.

Texts are written in English in the code, inside ``tr("...")``. The French
and Arabic translations live in ``slidecatch/locales/fr.py`` and ``ar.py``
(one dictionary {English: translation} each). A missing translation shows the
English text, so the interface never breaks; ``tests/test_i18n.py`` checks
that every text is translated.

Placeholders such as ``{n}`` are filled after translation:
``tr("Slide {n} saved", n=12)``. Texts that count things have a singular and
a plural form: ``trn("{n} slide", "{n} slides", n)``.
"""

LANGUAGES = {"en": "English", "fr": "Français", "ar": "العربية"}
RTL_LANGUAGES = {"ar"}

_state = {"lang": "en", "table": {}}


def table(lang: str) -> dict:
    if lang == "fr":
        from .locales.fr import STRINGS
        return STRINGS
    if lang == "ar":
        from .locales.ar import STRINGS
        return STRINGS
    return {}


def set_language(lang: str):
    lang = lang if lang in LANGUAGES else "en"
    _state["lang"] = lang
    _state["table"] = table(lang)


def language() -> str:
    return _state["lang"]


def is_rtl(lang: str = None) -> bool:
    return (lang or _state["lang"]) in RTL_LANGUAGES


def _fill(template: str, english: str, values: dict) -> str:
    """Puts the values in the placeholders. A broken translation falls back to
    the English text instead of crashing the interface."""
    if not values:
        return template
    try:
        return template.format(**values)
    except (KeyError, IndexError, ValueError):
        return english.format(**values)


def tr(text: str, **values) -> str:
    return _fill(_state["table"].get(text, text), text, values)


# In Arabic, a noun after a number from 3 to 10 takes its plural form
# ("3 شرائح"); after 11 and more it takes the singular ("11 شريحة").
_ARABIC_COUNTED = (("شريحة", "شرائح"), ("صورة", "صور"))


def trn(singular: str, plural: str, n: int, **values) -> str:
    """A text with a number of things: ``trn("{n} slide", "{n} slides", n)``.

    English uses the singular for 1 only, French for 0 and 1. For Arabic, the
    noun that follows the number is adjusted as explained above.
    """
    lang = _state["lang"]
    one = n in (0, 1) if lang == "fr" else n == 1
    english = singular if one else plural
    template = _state["table"].get(english, english)
    if lang == "ar" and not one:
        for single, many in _ARABIC_COUNTED:
            word = many if 3 <= n % 100 <= 10 else single
            template = (template.replace("{n} " + single, "{n} " + word)
                        .replace("{n} " + many, "{n} " + word))
    return _fill(template, english, dict(values, n=n))


def _direction(text: str) -> str:
    """'rtl' or 'ltr' from the first letter of a text ('' when it has none).
    Written without the unicodedata module to keep the app small."""
    for char in text:
        code = ord(char)
        if 0x0590 <= code <= 0x08FF or 0xFB1D <= code <= 0xFDFF or 0xFE70 <= code <= 0xFEFF:
            return "rtl"
        if char.isalpha():
            return "ltr"
    return ""


def bidi_safe(text: str) -> str:
    """Keeps a shortened title correct in a mixed-direction interface.

    A Latin window title shown in the Arabic interface would otherwise get its
    "…" on the wrong side ("…Weekly review" instead of "Weekly review…"). An
    invisible direction mark at the end ties the "…" to the words it shortens.
    """
    direction = _direction(text)
    if direction == "ltr" and is_rtl():
        return text + "‎"          # LEFT-TO-RIGHT MARK
    if direction == "rtl" and not is_rtl():
        return text + "‏"          # RIGHT-TO-LEFT MARK
    return text


def N_(text: str) -> str:
    """Marks a text for translation where it is stored, not shown (it is passed
    to ``tr`` later). Lets the tests find every text that needs a translation."""
    return text


def resource_name(stem: str, lang: str = None) -> str:
    """File name of a long text in the current language, e.g. ``guide_fr.md``."""
    return "%s_%s.md" % (stem, lang or _state["lang"])
