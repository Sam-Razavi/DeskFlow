from typing import Annotated

from pydantic import BaseModel, Field


class AssistantSource(BaseModel):
    id: int
    title: str


class AssistantReply(BaseModel):
    # None when the knowledge base has nothing to ground an answer on; the model is then not asked.
    answer: Annotated[str, Field(max_length=6000)] | None
    sources: list[AssistantSource]
    # Why there is no answer, for the UI to explain: "no_articles" or "not_covered".
    reason: str | None = None
