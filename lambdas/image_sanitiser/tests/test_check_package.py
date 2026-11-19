"""The package check refuses a zip the arm64 function could not run."""

from __future__ import annotations

import pathlib
import struct
import zipfile

import pytest

from image_sanitiser import check_package

HANDLER = pathlib.Path(check_package.__file__).resolve().parent / "handler.py"


def _elf(machine: int) -> bytes:
    """Build a 64-bit little-endian ELF header naming ``machine``."""
    ident = b"\x7fELF" + bytes([2, 1, 1]) + b"\x00" * 9
    return ident + struct.pack("<HH", 3, machine) + b"\x00" * 44


def _package(tmp_path: pathlib.Path, entries: dict[str, bytes]) -> pathlib.Path:
    path = tmp_path / "image_sanitiser.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name, body in entries.items():
            archive.writestr(name, body)
    return path


def _good() -> dict[str, bytes]:
    return {
        "handler.py": HANDLER.read_bytes(),
        "PIL/__init__.py": b"",
        check_package.CORE_EXTENSION: _elf(check_package.EM_AARCH64),
        "pillow.libs/libwebp-1.so.7": _elf(check_package.EM_AARCH64),
        "pillow-13.0.0.dist-info/RECORD": b"",
    }


def test_an_aarch64_package_passes(tmp_path: pathlib.Path) -> None:
    package = _package(tmp_path, _good())

    assert check_package.problems(package, HANDLER) == []
    assert check_package.main([str(package)]) == 0


@pytest.mark.parametrize(
    ("change", "complaint"),
    [
        # This host's Pillow: an x86-64 (62) core extension.
        ({check_package.CORE_EXTENSION: _elf(62)}, "not a 64-bit AArch64"),
        # A bundled library for the wrong machine.
        ({"pillow.libs/libwebp-1.so.7": _elf(62)}, "libwebp"),
        # Not an ELF at all, and too short to be one.
        ({"pillow.libs/libwebp-1.so.7": b"\x7fEL"}, "libwebp"),
        ({"PIL/_imaging.cpython-312-x86_64-linux-gnu.so": _elf(62)}, "x86_64"),
        ({"handler.py": b"def handler(event, context): pass\n"}, "differs"),
        ({"boto3/__init__.py": b""}, "unexpected entry"),
        ({"app/main.py": b""}, "unexpected entry"),
    ],
)
def test_a_package_the_function_cannot_run_is_refused(
    tmp_path: pathlib.Path, change: dict[str, bytes], complaint: str
) -> None:
    package = _package(tmp_path, {**_good(), **change})

    found = check_package.problems(package, HANDLER)

    assert any(complaint in problem for problem in found), found
    assert check_package.main([str(package)]) == 1


@pytest.mark.parametrize("missing", ["handler.py", check_package.CORE_EXTENSION])
def test_a_package_missing_its_handler_or_pillow_is_refused(
    tmp_path: pathlib.Path, missing: str
) -> None:
    entries = _good()
    del entries[missing]

    assert check_package.problems(_package(tmp_path, entries), HANDLER) != []
