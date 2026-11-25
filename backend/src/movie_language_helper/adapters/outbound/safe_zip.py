"""Bounded in-memory reading of an untrusted subtitle ZIP archive."""

from __future__ import annotations

import io
import stat
import zipfile
from pathlib import PurePosixPath

from movie_language_helper.ports.catalog import ProviderFailure, ProviderFailureCode


def read_srt_member(
    archive: bytes,
    *,
    max_members: int,
    max_uncompressed_bytes: int,
    max_ratio: int,
) -> tuple[str, bytes]:
    """Validate an archive and return one deterministically selected SRT member."""
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            members = bundle.infolist()
            if not members or len(members) > max_members:
                raise _invalid("Subtitle archive has an unsafe member count.")
            candidates: list[zipfile.ZipInfo] = []
            for member in members:
                path = PurePosixPath(member.filename.replace("\\", "/"))
                mode = member.external_attr >> 16
                if (
                    member.is_dir()
                    or path.is_absolute()
                    or ".." in path.parts
                    or member.flag_bits & 0x1
                    or stat.S_ISLNK(mode)
                ):
                    raise _invalid("Subtitle archive contains an unsafe member.")
                if member.file_size > max_uncompressed_bytes:
                    raise _invalid("Subtitle archive expands beyond the size limit.")
                compressed = max(1, member.compress_size)
                if member.file_size / compressed > max_ratio:
                    raise _invalid("Subtitle archive compression ratio is unsafe.")
                if path.suffix.casefold() == ".srt":
                    candidates.append(member)
            if not candidates:
                raise _invalid("Subtitle archive does not contain an SRT file.")
            ranked = sorted(
                candidates,
                key=lambda item: (
                    len(PurePosixPath(item.filename).parts),
                    len(item.filename),
                    item.filename.casefold(),
                ),
            )
            selected = ranked[0]
            selected_rank = (
                len(PurePosixPath(selected.filename).parts),
                len(selected.filename),
            )
            if (
                sum(
                    (
                        len(PurePosixPath(item.filename).parts),
                        len(item.filename),
                    )
                    == selected_rank
                    for item in ranked
                )
                > 1
            ):
                raise _invalid("Subtitle archive contains ambiguous SRT files.")
            content = bundle.read(selected)
            if len(content) > max_uncompressed_bytes:
                raise _invalid("Subtitle member exceeds the size limit.")
            return PurePosixPath(selected.filename).name, content
    except (zipfile.BadZipFile, OSError) as error:
        raise _invalid("Subtitle provider returned an invalid archive.") from error


def _invalid(message: str) -> ProviderFailure:
    return ProviderFailure(ProviderFailureCode.INVALID_ARCHIVE, message)
