from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Kind = Literal["publish", "download", "processing", "login", "check", "preview"]
Status = Literal[
    "queued", "running", "succeeded", "failed", "cancelled", "interrupted", "unknown"
]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AccountInput(Input):
    platform: Literal[1, 2, 3, 4]
    name: str = Field(min_length=1, max_length=80)


class LoginInput(Input):
    headed: bool = False


class PublishItem(Input):
    material_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, value):
        return list(
            dict.fromkeys(
                tag.strip().lstrip("#") for tag in value if tag.strip().lstrip("#")
            )
        )


class PublishBatch(Input):
    request_key: str = Field(min_length=8, max_length=100)
    items: list[PublishItem] = Field(min_length=1, max_length=100)
    account_ids: list[int] = Field(min_length=1, max_length=100)


class DownloadInput(Input):
    url: str = Field(min_length=1, max_length=2000)
    subtitles: bool = True


class YouTubeDownloadInput(DownloadInput):
    request_key: str = Field(min_length=8, max_length=100)
    title: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    account_ids: list[int] = Field(default_factory=list, max_length=100)


class BrowserAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["navigate", "back", "forward", "reload", "click", "scroll", "key", "text", "show"]
    text: str = Field(default="", max_length=4000)
    x: float = Field(default=0, ge=0, le=1280)
    y: float = Field(default=0, ge=0, le=800)
    dx: float = Field(default=0, ge=-5000, le=5000)
    dy: float = Field(default=0, ge=-5000, le=5000)
    clicks: int = Field(default=1, ge=1, le=2)


class BrowserState(BaseModel):
    active: bool
    url: str
    title: str
    video_url: str | None
    image: str
    width: int
    height: int
    message: str


class ProcessingInput(Input):
    material_id: int = Field(gt=0)


class SettingsInput(Input):
    downloadProxy: str = ""
    videoProcessing: dict[str, Any] | None = None
    publishTopicPresets: dict[str, list[str]] | None = None


class BrowserCookie(BaseModel):
    # Cookie values must retain whitespace exactly as exported by the browser.
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=256)
    value: str = Field(max_length=32768)
    domain: str = Field(min_length=1, max_length=253)
    path: str = Field(default="/", min_length=1, max_length=2048)
    secure: bool = True
    httpOnly: bool = False
    expires: float | None = Field(default=None, allow_inf_nan=False)


class BrowserCookieImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cookies: list[BrowserCookie] = Field(max_length=500)


class Task(BaseModel):
    id: str
    kind: Kind
    title: str
    status: Status
    phase: str
    progress: float | None
    payload: dict[str, Any]
    result: dict[str, Any]
    error: str | None
    detail: str | None
    parent_id: str | None
    account_id: int | None
    material_id: int | None
    created_at: str
    updated_at: str


class TaskCreated(BaseModel):
    id: str


class BatchResult(BaseModel):
    id: str
    tasks: list[Task]


class Account(BaseModel):
    id: int
    type: int
    userName: str
    status: int
    platform: str


class Material(BaseModel):
    id: int
    filename: str
    filesize: float | None = None
    upload_time: str | None = None
    source_url: str | None = None
    source_type: str | None = None
    video_title: str | None = None
    video_title_zh: str | None = None
    video_description: str | None = None
    material_type: str = "original"
    parent_file_id: int | None = None
    display_tags: list[str] = Field(default_factory=list)
    video_resolution: str | None = None
    duration: float | None = None
    has_subtitle: bool = False
    has_thumbnail: bool = False


class MaterialPage(BaseModel):
    items: list[Material]
    total: int
    page: int
    page_size: int


class TaskEvent(BaseModel):
    id: int
    task_id: str | None
    event: str
    data: dict[str, Any]
    created_at: str
