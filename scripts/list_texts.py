"""List every interface text (``tr``, ``trn`` and ``N_``) found in the code.

    python scripts/list_texts.py            all texts
    python scripts/list_texts.py fr         texts missing a French translation
"""

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def texts():
    found = {}
    package = os.path.join(ROOT, "slidecatch")
    for folder, _dirs, files in os.walk(package):
        if "locales" in folder:
            continue
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(folder, name)
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), path)
            for node in ast.walk(tree):
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None) \
                    if isinstance(node, ast.Call) else None
                if not isinstance(node, ast.Call) or name not in ("tr", "trn", "N_"):
                    continue
                # tr("text") and N_("text"): one text; trn("singular", "plural", n): two
                for arg in node.args[:2 if name == "trn" else 1]:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        found.setdefault(arg.value, os.path.relpath(path, ROOT))
    return found


if __name__ == "__main__":
    sys.path.insert(0, ROOT)
    all_texts = texts()
    if len(sys.argv) > 1:
        from slidecatch.i18n import table
        known = table(sys.argv[1])
        missing = [t for t in all_texts if t not in known]
        for text in missing:
            print(repr(text))
        print(len(missing), "missing of", len(all_texts), file=sys.stderr)
    else:
        for text, where in sorted(all_texts.items(), key=lambda x: x[1]):
            print("%-40s %r" % (where, text))
        print(len(all_texts), "texts", file=sys.stderr)
