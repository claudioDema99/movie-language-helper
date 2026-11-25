"""Security limits for provider subtitle archives."""

import io
import zipfile
from unittest.mock import patch

import pytest

from movie_language_helper.adapters.outbound.safe_zip import read_srt_member
from movie_language_helper.ports.catalog import ProviderFailure, ProviderFailureCode


def _archive(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, content in entries.items():
            bundle.writestr(name, content)
    return buffer.getvalue()


def _read(archive: bytes) -> tuple[str, bytes]:
    return read_srt_member(
        archive,
        max_members=3,
        max_uncompressed_bytes=1_000,
        max_ratio=100,
    )


def test_selects_shallowest_srt_without_extracting() -> None:
    filename, content = _read(
        _archive(
            {
                "nested/alternate.srt": b"alternate",
                "movie.srt": b"synthetic",
                "readme.txt": b"metadata",
            }
        )
    )
    assert filename == "movie.srt"
    assert content == b"synthetic"


@pytest.mark.parametrize(
    ("archive", "message"),
    [
        (_archive({}), "member count"),
        (_archive({"a": b"1", "b": b"2", "c": b"3", "d": b"4"}), "member count"),
        (_archive({"folder/": b""}), "unsafe member"),
        (_archive({"/absolute.srt": b"x"}), "unsafe member"),
        (_archive({"../escape.srt": b"x"}), "unsafe member"),
        (_archive({"large.srt": b"x" * 1_001}), "size limit"),
        (_archive({"readme.txt": b"x"}), "does not contain"),
        (_archive({"one.srt": b"1", "two.srt": b"2"}), "ambiguous"),
        (b"not a zip", "invalid archive"),
    ],
)
def test_rejects_unsafe_archives(archive: bytes, message: str) -> None:
    with pytest.raises(ProviderFailure, match=message) as caught:
        _read(archive)
    assert caught.value.code is ProviderFailureCode.INVALID_ARCHIVE


def test_rejects_symlinks_encryption_ratio_and_lying_member_size() -> None:
    symlink = zipfile.ZipInfo("link.srt")
    symlink.external_attr = 0o120777 << 16
    encrypted = zipfile.ZipInfo("secret.srt")
    encrypted.flag_bits = 1
    ratio = zipfile.ZipInfo("ratio.srt")
    ratio.file_size = 500
    ratio.compress_size = 1
    oversized_read = zipfile.ZipInfo("movie.srt")
    oversized_read.file_size = 1
    oversized_read.compress_size = 1

    class _Bundle:
        def __init__(self, member: zipfile.ZipInfo, content: bytes = b"x") -> None:
            self.member = member
            self.content = content

        def __enter__(self) -> "_Bundle":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def infolist(self) -> list[zipfile.ZipInfo]:
            return [self.member]

        def read(self, _member: zipfile.ZipInfo) -> bytes:
            return self.content

    for member, message, content in (
        (symlink, "unsafe member", b"x"),
        (encrypted, "unsafe member", b"x"),
        (ratio, "ratio", b"x"),
        (oversized_read, "size limit", b"x" * 1_001),
    ):
        with (
            patch(
                "movie_language_helper.adapters.outbound.safe_zip.zipfile.ZipFile",
                return_value=_Bundle(member, content),
            ),
            pytest.raises(ProviderFailure, match=message),
        ):
            _read(b"fixture")


def test_maps_archive_open_os_error() -> None:
    with (
        patch(
            "movie_language_helper.adapters.outbound.safe_zip.zipfile.ZipFile",
            side_effect=OSError("synthetic"),
        ),
        pytest.raises(ProviderFailure, match="invalid archive"),
    ):
        _read(b"fixture")
