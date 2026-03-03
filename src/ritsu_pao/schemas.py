"""データスキーマ定義 — 入力(candidates.json)と出力(publish契約)"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ─── 入力: candidates.json スキーマ ───


class Regime(str, Enum):
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"


class ReasonTop3(BaseModel):
    feature: str
    value: float
    z: float
    direction: str
    note: str


class Event(BaseModel):
    date: str
    type: str


class Candidate(BaseModel):
    ticker: str
    name: str
    sector: str
    score: float
    reasons_top3: list[ReasonTop3]
    risk_flags: list[str] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    holding_window: str = "1-5d"


class CandidatesMeta(BaseModel):
    run_id: str
    as_of: str
    timezone: str = "Asia/Tokyo"
    git_sha: str = ""
    inputs_digest: str = ""
    universe_size: int = 0
    eligible_size: int = 0
    generated_at: str = ""


class CandidatesJson(BaseModel):
    meta: CandidatesMeta
    candidates: list[Candidate]


# ─── 入力: gates結果 ───


class GatesResult(BaseModel):
    all_passed: bool
    rejection_reasons: list[str] = Field(default_factory=list)
    regime: str = "risk_on"
    wf_ic: float | None = None


# ─── 出力: script_x.json ───


class ScriptXJson(BaseModel):
    date: str
    status: str  # "trade" | "no_trade"
    body: str
    self_reply: str
    image: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    v2_experiment: dict[str, Any] | None = None


# ─── 出力: script_youtube.json ───


class ScriptYoutubeJson(BaseModel):
    date: str
    status: str
    hook: str
    body: str
    cta: str
    voicepeak: dict[str, Any] = Field(default_factory=dict)
    upload_meta: dict[str, Any] = Field(default_factory=dict)
    v2_experiment: dict[str, Any] | None = None


# ─── 出力: meta.json ───


class PublishStatus(str, Enum):
    OK = "ok"
    NO_POST = "no_post"


class MetaJson(BaseModel):
    date: str
    status: PublishStatus
    generated_at: str
    rejection_reasons: list[str] = Field(default_factory=list)
    quality_score: float | None = None
    run_id: str = ""
    git_sha: str = ""
