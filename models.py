from typing import Any, Literal
from pydantic import BaseModel, Field

BlockType = Literal[
    'heading', 'paragraph', 'list', 'table', 'figure', 'caption', 'equation',
    'footnote', 'header', 'footer', 'spreadsheet', 'slide', 'unknown',
]

class BoundingBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float

class Block(BaseModel):
    id: str
    type: BlockType
    page: int
    text: str = ''
    bbox: BoundingBox | None = None
    confidence: float = Field(ge=0, le=1)
    source: str = ''
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: Literal['ok', 'ambiguous', 'error'] = 'ok'

class DocumentResult(BaseModel):
    filename: str
    format: str
    pages: int
    status: Literal['success', 'partial', 'error']
    errors: list[dict[str, Any]] = Field(default_factory=list)
    blocks: list[Block] = Field(default_factory=list)
    markdown: str = ''
