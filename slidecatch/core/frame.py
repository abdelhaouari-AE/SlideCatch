"""The picture returned by every capture method."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Frame:
    """One captured picture.

    ``data`` holds ``height`` rows of ``stride`` bytes, top row first. Each
    pixel is 4 bytes in the order blue, green, red, unused (the 32-bit layout
    Windows and Qt both use). The fourth byte is not meaningful: GDI leaves it
    at 0, so code that reads the picture must ignore it.
    """

    data: bytes
    width: int
    height: int
    stride: int
    source: str  # "wgc", "printwindow" or "screen" - for logs and diagnostics

    def looks_blank(self) -> bool:
        """True when the picture is (almost) completely black.

        Some windows answer a background capture with a black picture. Reading
        about two thousand bytes spread over the picture is enough to notice it
        and costs nothing (slicing and ``max`` run in C).
        """
        if not self.data:
            return True
        step = max(1, len(self.data) // 2048) | 1  # odd step: visits B, G and R bytes
        return max(self.data[::step]) < 12
