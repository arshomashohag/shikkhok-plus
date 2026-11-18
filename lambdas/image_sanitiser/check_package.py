"""Prove a built sanitiser package is the one the function can run.

Usage::

    python lambdas/image_sanitiser/check_package.py dist/image_sanitiser.zip

The function is arm64 on CPython 3.12. A package built with this host's
Pillow (x86_64) or with no compiled Pillow at all would upload cleanly and
fail at its first invocation, after the release had shipped. So the last
step of ``make lambda-image`` reads the zip back and refuses it unless:

* ``handler.py`` sits at its root and is byte-for-byte this directory's;
* Pillow's core extension, ``PIL/_imaging.cpython-312-aarch64-linux-gnu.so``,
  is present;
* every shared object in it is a 64-bit ELF for AArch64 (``e_machine``
  183), the bundled libraries in ``pillow.libs/`` included; and
* nothing else is at the root: only the handler, ``PIL/``, Pillow's
  ``.dist-info`` and its ``pillow.libs/``.

Standard library only.
"""

from __future__ import annotations

import pathlib
import re
import sys
import zipfile
from typing import Literal

HERE = pathlib.Path(__file__).resolve().parent

CORE_EXTENSION = "PIL/_imaging.cpython-312-aarch64-linux-gnu.so"
EM_AARCH64 = 183
ELFCLASS64 = 2

#: What may sit at the zip's root, by first path component.
ROOT_ENTRY = re.compile(r"handler\.py|PIL|pillow\.libs|pillow-[\w.]+\.dist-info")


def _elf_machine(header: bytes) -> int | None:
    """Return an ELF header's machine, or None when it is not 64-bit ELF.

    :param header: The file's first 20 bytes at least
    :return: ``e_machine``, or None
    """
    if len(header) < 20 or header[:4] != b"\x7fELF" or header[4] != ELFCLASS64:
        return None
    order: Literal["little", "big"] = "little" if header[5] == 1 else "big"
    return int.from_bytes(header[18:20], order)


def problems(package: pathlib.Path, handler: pathlib.Path) -> list[str]:
    """Return every reason the package must not ship.

    :param package: The built zip
    :param handler: The handler source it must carry
    :return: Empty when it may ship
    """
    found: list[str] = []
    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()
        files = [name for name in names if not name.endswith("/")]
        if "handler.py" not in names:
            found.append("no handler.py at the root")
        elif archive.read("handler.py") != handler.read_bytes():
            found.append("handler.py differs from the source it was built from")
        if CORE_EXTENSION not in names:
            found.append(f"no {CORE_EXTENSION}: Pillow is missing or not aarch64")
        for name in files:
            if not ROOT_ENTRY.fullmatch(name.split("/", 1)[0]):
                found.append(f"unexpected entry at the root: {name}")
            if re.search(r"\.so(\.|$)", name):
                machine = _elf_machine(archive.read(name)[:20])
                if machine != EM_AARCH64:
                    found.append(f"{name} is not a 64-bit AArch64 ELF ({machine})")
    return found


def main(argv: list[str]) -> int:
    """Check one package.

    :param argv: ``[package.zip]``
    :return: The process exit code
    """
    package = pathlib.Path(argv[0])
    found = problems(package, HERE / "handler.py")
    for problem in found:
        print(f"::error::{package}: {problem}")
    if found:
        return 1
    with zipfile.ZipFile(package) as archive:
        count = len(archive.namelist())
    size = package.stat().st_size
    print(f"{package}: {count} entries, {size} bytes; {CORE_EXTENSION} is AArch64.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
