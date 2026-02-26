from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4


class Platform(Enum):
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"
    INSTAGRAM = "instagram"


class RequestStatus(Enum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    DOWNLOADING = "downloading"
    SENDING = "sending"
    COMPLETED = "completed"
    FAILED = "failed"


class ChatType(Enum):
    PRIVATE = "private"
    GROUP = "group"
    INLINE = "inline"


@dataclass
class VideoRequest:
    url: str
    platform: Platform
    user_id: int
    chat_id: int
    chat_type: ChatType
    language: str = "en"
    id: str = field(default_factory=lambda: str(uuid4()))
    message_id: int | None = None
    status: RequestStatus = RequestStatus.PENDING
    duration: int | None = None
    file_size: int | None = None
    file_path: str | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
