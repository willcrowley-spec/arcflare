from pydantic import BaseModel, Field


class AnalysisConfig(BaseModel):
    velocity_window_days: int = Field(default=30, ge=1, le=730)
    min_records_for_vectorization: int = Field(default=1, ge=0)
    embedding_provider: str = "default"
    vector_store_provider: str = "default"
    llm_provider: str = "default"
    model_overrides: dict[str, str] = Field(default_factory=dict)


class AnalysisConfigUpdate(BaseModel):
    velocity_window_days: int | None = Field(default=None, ge=1, le=730)
    min_records_for_vectorization: int | None = Field(default=None, ge=0)
    model_overrides: dict[str, str] | None = None


class ClassificationUpdate(BaseModel):
    classification: str = Field(..., pattern="^(included|excluded)$")
