"""Upload, preview, and delete transcript-session endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status

from movie_language_helper.adapters.inbound.http.dependencies import get_services
from movie_language_helper.adapters.inbound.http.schemas import (
    PreviewCueResponse,
    TranscriptPreviewResponse,
    TranscriptSessionCreatedResponse,
)
from movie_language_helper.application.errors import ApplicationError
from movie_language_helper.application.transcripts import warning_codes
from movie_language_helper.domain.subtitle import TranscriptSourceKind
from movie_language_helper.domain.time import SyncOffset, Timestamp
from movie_language_helper.infrastructure.container import AppServices
from movie_language_helper.ports.subtitle import SubtitlePayload

router = APIRouter(prefix="/api/v1/transcript-sessions", tags=["transcripts"])
ALLOWED_UPLOAD_CONTENT_TYPES = {
    "application/octet-stream",
    "application/x-subrip",
    "text/plain",
}
UPLOAD_CHUNK_BYTES = 64 * 1024


@router.post(
    "/upload",
    response_model=TranscriptSessionCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_transcript(
    file: Annotated[UploadFile, File(description="English SRT subtitle")],
    rights_acknowledged: Annotated[bool, Form()],
    services: Annotated[AppServices, Depends(get_services)],
) -> TranscriptSessionCreatedResponse:
    """Create a transient session from a rights-acknowledged SRT upload."""
    if not rights_acknowledged:
        raise ApplicationError(
            "invalid_request",
            "Subtitle-use rights must be acknowledged.",
        )
    filename = file.filename
    if filename is None or not filename.casefold().endswith(".srt"):
        raise ApplicationError("unsupported_subtitle", "Only .srt files are supported.")
    if file.content_type not in ALLOWED_UPLOAD_CONTENT_TYPES:
        raise ApplicationError(
            "unsupported_subtitle",
            "Uploaded subtitle content type is unsupported.",
        )
    content = await _read_bounded(file, services.settings.upload_max_bytes)
    session = await services.create_uploaded_session.execute(
        SubtitlePayload(
            content=content,
            source_kind=TranscriptSourceKind.UPLOAD,
            filename=filename,
            declared_format="srt",
            content_type=file.content_type,
        )
    )
    return TranscriptSessionCreatedResponse(
        id=session.id,
        created_at=session.created_at,
        expires_at=session.expires_at,
        cue_count=len(session.transcript.cues),
        duration_ms=session.transcript.duration.milliseconds,
        warnings=warning_codes(session.transcript.warnings),
    )


@router.get("/{session_id}/preview", response_model=TranscriptPreviewResponse)
async def preview_transcript(
    session_id: str,
    services: Annotated[AppServices, Depends(get_services)],
    at_ms: Annotated[int, Query(ge=0)],
    sync_offset_ms: int = 0,
) -> TranscriptPreviewResponse:
    """Return only a bounded offset-adjusted preview near one timestamp."""
    preview = await services.preview_session.execute(
        session_id,
        Timestamp(at_ms),
        SyncOffset(sync_offset_ms),
    )
    return TranscriptPreviewResponse(
        session_id=preview.session_id,
        at_ms=preview.at.milliseconds,
        sync_offset_ms=preview.sync_offset.milliseconds,
        cues=tuple(
            PreviewCueResponse(
                id=cue.id,
                start_ms=cue.display_range.start.milliseconds,
                end_ms=cue.display_range.end.milliseconds,
                text=cue.text,
                flags=tuple(sorted(flag.value for flag in cue.flags)),
            )
            for cue in preview.cues
        ),
    )


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transcript(
    session_id: str,
    services: Annotated[AppServices, Depends(get_services)],
) -> Response:
    """Delete a transient transcript session."""
    await services.delete_session.execute(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _read_bounded(file: UploadFile, limit: int) -> bytes:
    content = bytearray()
    try:
        while chunk := await file.read(UPLOAD_CHUNK_BYTES):
            content.extend(chunk)
            if len(content) > limit:
                raise ApplicationError(
                    "resource_limit_exceeded",
                    "Uploaded subtitle exceeds the configured byte limit.",
                )
    finally:
        await file.close()
    return bytes(content)
