"""The AWS SDK is reachable from one file, and never from the public hub.

H3 brings boto3 into the image for the photo bucket alone [H3 deviation 1].
The container's only AWS credentials are the media role's, scoped to that
bucket, so the SDK's reach is bounded by IAM either way; what this gate
bounds is the *code*: one module, ``app/hub/media/storage.py``, talks to S3,
and everything else goes through its :class:`MediaStore` interface. A
second importer would be a second place a client is built -- without the
credential refresh and the regional endpoint the storage module pins -- and
an import under ``app/hub/public`` would put an AWS client one call away from
an anonymous page.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: The one module allowed to import the SDK.
STORAGE = "app/hub/media/storage.py"

#: An import of either SDK package, in any of the forms Python accepts,
#: including a dynamic import by name.
_IMPORT = re.compile(
    r"^\s*(?:import|from)\s+(?:boto3|botocore)\b"
    r"|import_module\(\s*[\"'](?:boto3|botocore)\b"
    r"|__import__\(\s*[\"'](?:boto3|botocore)\b",
    re.M,
)


def _importers(root: pathlib.Path) -> set[str]:
    """List every Python file under ``root/app`` that imports the SDK.

    :param root: The repository root to scan
    :return: Paths relative to ``root``
    """
    return {
        str(path.relative_to(root))
        for path in (root / "app").rglob("*.py")
        if _IMPORT.search(path.read_text())
    }


def test_boto3_imported_only_by_storage() -> None:
    assert _importers(ROOT) == {STORAGE}


def test_never_under_the_public_hub() -> None:
    assert not [p for p in _importers(ROOT) if p.startswith("app/hub/public/")]


def test_the_gate_fires(tmp_path: pathlib.Path) -> None:
    # Not vacuous: each import form is seen, and the allowed file is too.
    hub = tmp_path / "app" / "hub" / "public"
    hub.mkdir(parents=True)
    forms = {
        "a.py": "import boto3\n",
        "b.py": "from botocore.config import Config\n",
        "c.py": "import importlib\nc = importlib.import_module('boto3')\n",
        "d.py": 'x = __import__("botocore.session")\n',
        "e.py": "# boto3 is mentioned, not imported\n",
    }
    for name, text in forms.items():
        (hub / name).write_text(text)

    assert _importers(tmp_path) == {
        f"app/hub/public/{name}" for name in ("a.py", "b.py", "c.py", "d.py")
    }


def test_the_sdk_is_locked_with_hashes() -> None:
    # In the image only as the lockfile pins it: exact versions, hashes.
    lock = (ROOT / "requirements.txt").read_text()
    for package in ("boto3", "botocore", "s3transfer"):
        block = re.search(
            rf"^{package}==[0-9.]+ \\\n(\s+--hash=sha256:\w+.*\n)+", lock, re.M
        )
        assert block, package


def test_the_container_never_builds_a_cloudfront_client() -> None:
    # The invalidation outbox is still sent by the host [R8]: the media
    # role has no CloudFront permission, and no code asks for a client.
    offenders = [
        str(path.relative_to(ROOT))
        for path in (ROOT / "app").rglob("*.py")
        if re.search(r"client\(\s*[\"']cloudfront", path.read_text())
    ]
    assert offenders == []
    assert re.search(r"client\(\s*\"s3\"", (ROOT / STORAGE).read_text())
