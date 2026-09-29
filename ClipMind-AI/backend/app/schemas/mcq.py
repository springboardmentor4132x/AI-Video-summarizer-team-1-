"""MCQ API schemas."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class McqQuestionResponse(BaseModel):
    question: str
    options: list[str]
    correct_answer: str
    explanation: str
    difficulty: Literal["Easy", "Medium", "Hard"]
    topic: str
    source: Literal["Transcript", "Summary", "Key Moment"]
    timestamp: str | None = None
