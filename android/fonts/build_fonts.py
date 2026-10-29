"""Build the app's bundled fonts: Noto Sans (Latin) and Noto Sans Bengali.

Each output file holds both scripts for one weight, so a single Compose
``FontFamily`` renders Bangla and Latin text in Noto. Without that, Compose
falls back to whatever Bengali font the phone's maker ships for Bangla, and
to Roboto for Latin.

Noto Sans is subset to Latin, Latin-1 and common punctuation first. The
full font also carries Greek and Cyrillic, which the app never shows, and
costs about 600 KB per weight.

Inputs are the hinted static TTFs from
https://github.com/notofonts/notofonts.github.io (fonts/NotoSans and
fonts/NotoSansBengali), licensed under the SIL Open Font License 1.1
(OFL.txt beside this file). Outputs go to android/src/main/res/font.

Usage::

    python3 -m venv /tmp/ft && /tmp/ft/bin/pip install fonttools==4.54.1
    /tmp/ft/bin/python android/fonts/build_fonts.py SOURCE_DIR
"""

from __future__ import annotations

import sys
from pathlib import Path

from fontTools.merge import Merger
from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont

LATIN_RANGES: tuple[tuple[int, int], ...] = (
    (0x0000, 0x00FF),
    (0x0131, 0x0131),
    (0x0152, 0x0153),
    (0x02BB, 0x02BC),
    (0x02C6, 0x02C6),
    (0x02DA, 0x02DA),
    (0x02DC, 0x02DC),
    (0x2000, 0x206F),
    (0x20AC, 0x20AC),
    (0x2122, 0x2122),
    (0x2190, 0x2193),
    (0x2212, 0x2212),
    (0x2215, 0x2215),
    (0xFEFF, 0xFEFF),
    (0xFFFD, 0xFFFD),
)

WEIGHTS: dict[str, str] = {
    "Regular": "Regular",
    "Medium": "Medium",
    "SemiBold": "SemiBold",
    "Bold": "Bold",
    "ExtraBold": "Bold",
}

OUTPUT = Path(__file__).resolve().parent.parent / "src/main/res/font"


class FontBuild:
    """Builds one merged Latin and Bengali font per weight.

    :ivar source: Directory holding the downloaded Noto TTFs
    """

    def __init__(self, source: Path) -> None:
        """Initialize the build.

        :param source: Directory holding the downloaded Noto TTFs
        """
        self.source = source

    def latin_subset(self, weight: str, scratch: Path) -> Path:
        """Subset one Noto Sans weight to the Latin ranges.

        :param weight: The weight name, e.g. ``SemiBold``
        :param scratch: Where to write the subset
        :return: The subset font's path
        """
        font = TTFont(self.source / f"NotoSans-{weight}.ttf")
        options = Options()
        options.layout_features = ["*"]
        subsetter = Subsetter(options)
        codepoints = {
            code for low, high in LATIN_RANGES for code in range(low, high + 1)
        }
        subsetter.populate(unicodes=codepoints)
        subsetter.subset(font)
        path = scratch / f"latin-{weight}.ttf"
        font.save(path)
        return path

    def merged(self, weight: str, bengali: str, scratch: Path) -> TTFont:
        """Merge the Latin subset with the matching Bengali weight.

        Vertical metrics take the larger of the two, so Bengali
        descenders are not clipped. Noto Sans Bengali has no ExtraBold;
        the wordmark that uses it is Latin only, so Bold is merged in.

        :param weight: The Latin weight name
        :param bengali: The Bengali weight name to merge with it
        :param scratch: Where intermediate files go
        :return: The merged font
        """
        latin = self.latin_subset(weight, scratch)
        font = Merger().merge(
            [str(latin), str(self.source / f"NotoSansBengali-{bengali}.ttf")]
        )
        bengali_font = TTFont(self.source / f"NotoSansBengali-{bengali}.ttf")
        font["hhea"].ascent = max(
            font["hhea"].ascent, bengali_font["hhea"].ascent
        )
        font["hhea"].descent = min(
            font["hhea"].descent, bengali_font["hhea"].descent
        )
        font["OS/2"].usWinDescent = max(
            font["OS/2"].usWinDescent, bengali_font["OS/2"].usWinDescent
        )
        return font

    def run(self) -> list[Path]:
        """Build every weight into the app's font resources.

        :return: The written font paths
        """
        scratch = OUTPUT.parent / "font-build"
        scratch.mkdir(exist_ok=True)
        written: list[Path] = []
        for weight, bengali in WEIGHTS.items():
            path = OUTPUT / f"noto_{weight.lower()}.ttf"
            self.merged(weight, bengali, scratch).save(path)
            written.append(path)
        for leftover in scratch.iterdir():
            leftover.unlink()
        scratch.rmdir()
        return written


if __name__ == "__main__":
    for built in FontBuild(Path(sys.argv[1])).run():
        print(built)
