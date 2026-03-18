from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """
    ?????API ?????????
    
    ???????????API ?????????????????????????????????????
    
    Attributes:
        code: ????????? "NOT_FOUND", "VALIDATION_ERROR", "INTERNAL_ERROR"
        message: ??????????????
        details: ????????????????????????????
    """
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class TaskRequest(BaseModel):
    project_root: Optional[str] = None
    chapter: Optional[int] = None
    chapter_range: Optional[str] = None
    volume: Optional[str] = None
    mode: str = "standard"
    require_manual_approval: bool = True
    options: Dict[str, Any] = Field(default_factory=dict)


class BootstrapProjectRequest(BaseModel):
    project_root: Optional[str] = None
    title: str = ""
    genre: str = "\u7384\u5e7b"


class PlanningProfileRequest(BaseModel):
    story_logline: str = ""
    protagonist_name: str = ""
    protagonist_identity: str = ""
    protagonist_initial_state: str = ""
    protagonist_desire: str = ""
    protagonist_flaw: str = ""
    core_setting: str = ""
    ability_cost: str = ""
    volume_1_title: str = ""
    volume_1_conflict: str = ""
    volume_1_climax: str = ""
    major_characters_text: str = ""
    factions_text: str = ""
    rules_outline: str = ""
    foreshadowing_text: str = ""


class RetryRequest(BaseModel):
    resume_from_step: Optional[str] = None


class CancelTaskRequest(BaseModel):
    reason: str = ""


class ReviewDecisionRequest(BaseModel):
    task_id: str
    reason: str = ""


class InvalidFactDecisionRequest(BaseModel):
    ids: List[int] = Field(default_factory=list)
    action: str = "confirm"


class LLMSettingsRequest(BaseModel):
    provider: str = "openai-compatible"
    base_url: str = ""
    model: str = ""
    api_key: str = ""


class RAGSettingsRequest(BaseModel):
    base_url: str = ""
    embed_model: str = ""
    rerank_model: str = ""
    api_key: str = ""
