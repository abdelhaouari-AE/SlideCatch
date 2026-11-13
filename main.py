"""Start SlideCatch: ``python main.py`` (also the entry point of SlideCatch.exe)."""

import sys

if __name__ == "__main__":
    from slidecatch.app import main
    sys.exit(main())
