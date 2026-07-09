# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class AlphaEvolveModel(str, Enum):
    """Model selection for generation."""

    GEMINI_V2P5_FLASH = "gemini-2.5-flash"
    GEMINI_V2P5_PRO = "gemini-2.5-pro"
    GEMINI_V3P0_FLASH_PREVIEW = "gemini-3-flash-preview"
    GEMINI_V3P1_PRO_PREVIEW = "gemini-3.1-pro-preview"
    GEMINI_V3P5_FLASH = "gemini-3.5-flash"

    @classmethod
    def from_str(cls, val: str) -> "AlphaEvolveModel":
        try:
            return cls[val]
        except KeyError:
            return cls(val)


def parse_models_from_env(env_val: str) -> list[dict[str, Any]]:
    """Parses models with optional weights from an env var string (delimited by comma, semicolon, plus, or slash).

    Example format: 'GEMINI_V2P5_PRO:0.7;GEMINI_V2P5_FLASH:0.3' or 'GEMINI_V2P5_FLASH'
    """
    for sep in [";", "+", "/"]:
        env_val = env_val.replace(sep, ",")
    results = []
    for item in env_val.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            name_str, weight_str = item.split(":", 1)
            model_enum = AlphaEvolveModel.from_str(name_str.strip())
            results.append({"name": model_enum, "weight": float(weight_str.strip())})
        else:
            model_enum = AlphaEvolveModel.from_str(item)
            results.append({"name": model_enum})
    return results


class AlphaEvolveModelConfig(BaseModel):
    """Per-model configuration for the ``models`` mixture field.

    At most two models may be specified. Weights are *relative* and normalized
    server-side, so they need not sum to 1.0. Note that capped models like
    'gemini-3.1-pro-preview' cannot exceed 50% share of the total mixture weight.
    """

    name: AlphaEvolveModel = Field(
        ...,
        description=(
            "Model name. One of: 'gemini-2.5-flash', 'gemini-2.5-pro', "
            "'gemini-3-flash-preview', 'gemini-3.1-pro-preview', "
            "'gemini-3.5-flash'."
        ),
    )
    weight: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Relative weight for this model in the mixture. Normalized "
            "server-side; defaults to 1.0 when unset."
        ),
    )


class AlphaEvolveGenerationSettings(BaseModel):
    """Generation settings for the experiment."""

    context: str | None = Field(
        default=None, description="Additional user-provided context."
    )
    models: list[AlphaEvolveModelConfig] | None = Field(
        default=None,
        min_length=1,
        max_length=2,
        description="Per-model configuration for code generation.",
    )

    @field_validator("models")
    @classmethod
    def validate_models_list(cls, v: list[AlphaEvolveModelConfig] | None) -> list[AlphaEvolveModelConfig] | None:
        if v is not None:
            if len(v) == 0:
                raise ValueError("If models is specified, at least one model must be provided.")
            if len(v) > 2:
                raise ValueError("At most two models may be specified in the mixture.")
        return v


class AlphaEvolveRunSettings(BaseModel):
    """Run settings for the experiment."""

    max_programs: int | None = Field(
        default=None, description="Maximum number of programs to generate."
    )
    concurrency: int | None = Field(
        default=None, description="Maximum number of programs in parallel."
    )
    max_duration: int | None = Field(
        default=None, description="Maximum experiment wall-clock duration in hours (e.g. 6)."
    )
    idle_timeout: int | None = Field(
        default=None, description="Maximum inactivity period before pausing in hours (e.g. 5)."
    )


class AlphaEvolveEvolutionSettings(BaseModel):
    """Evolution settings for the experiment."""

    reset_interval: int | None = Field(
        default=None, description="Reset interval for reseeding islands."
    )


class AlphaEvolveExperimentConfig(BaseModel):
    """Configuration of an experiment."""

    title: str = Field(..., description="Title of the experiment.")
    problem_description: str = Field(..., description="Description of the problem.")
    notes: str | None = Field(default=None, description="Additional notes.")
    program_language: str = Field(..., description="Primary programming language.")
    run_settings: AlphaEvolveRunSettings | None = Field(
        default=None, description="Run settings."
    )
    generation_settings: AlphaEvolveGenerationSettings | None = Field(
        default=None, description="Generation settings."
    )
    evolution_settings: AlphaEvolveEvolutionSettings | None = Field(
        default=None, description="Evolution settings."
    )


class AlphaEvolveExperimentStats(BaseModel):
    """Stats about the experiment."""

    candidates_count: int = Field(default=0, description="Number of candidates generated.")
    evaluated_candidates_count: int = Field(
        default=0, description="Number of candidates evaluated."
    )


class AlphaEvolveExperimentState(Enum):
    """Experiment state values.

    Values:
        STATE_UNSPECIFIED (0):
            Default value. This value is unused.
        CREATED (1):
            The experiment is created.
        RUNNING (2):
            The experiment is running.
        PAUSED (3):
            The experiment is paused.
        COMPLETED (4):
            The experiment is completed.
        FAILED (5):
            The experiment has failed.
    """

    STATE_UNSPECIFIED = 0
    CREATED = 1
    RUNNING = 2
    PAUSED = 3
    COMPLETED = 4
    FAILED = 5


class AlphaEvolveExperiment(BaseModel):
    """An experiment is a single run of the AlphaEvolve agent."""

    name: str = Field(..., description="The full resource name of the experiment.")
    create_time: datetime | None = Field(
        default=None, description="Time when the experiment was created."
    )
    config: AlphaEvolveExperimentConfig = Field(..., description="Experiment configuration.")
    stats: AlphaEvolveExperimentStats | None = Field(
        default=None, description="Experiment stats."
    )
    state: AlphaEvolveExperimentState = Field(
        default=AlphaEvolveExperimentState.STATE_UNSPECIFIED,
        description="The state of the experiment.",
    )


class AlphaEvolveSourceFile(BaseModel):
    """A single source file with its path, content and metadata."""

    path: str = Field(
        ...,
        description="The relative path of the file, including the filename. e.g., 'src/main.py', 'utils/helpers.js', 'README.md'.",
    )
    content: str = Field(
        ...,
        description="The raw content of the file. This is a string and not bytes, because it should be ultimately processed by the LLM as text.",
    )
    program_language: str | None = Field(
        default=None, description="The programming language of the file."
    )
    description: str | None = Field(
        default=None, description="Additional description of the file."
    )


class AlphaEvolveProgramContent(BaseModel):
    """A self-contained message containing the content of a program. Can represent a collection of files."""

    description: str | None = Field(default=None, description="Description of the program.")
    files: list[AlphaEvolveSourceFile] = Field(
        ..., description="A list of source files that make up the overall program."
    )


class AlphaEvolveProgram(BaseModel):
    """Represents a single program to be used within the context of an AlphaEvolve experiment."""

    name: str = Field(
        ...,
        description="Identifier. Unique identifier for the program. Format: projects/{project}/locations/{location}/collections/{collection}/engines/{engine}/sessions/{session}/alphaEvolveExperiments/{alpha_evolve_experiment}/alphaEvolvePrograms/{alpha_evolve_program}",
    )
    create_time: datetime | None = Field(
        default=None, description="Time when the program was created."
    )
    content: AlphaEvolveProgramContent | None = Field(
        default=None, description="Content of the program."
    )
    evaluation: AlphaEvolveProgramEvaluation | None = Field(
        default=None, description="Evaluation results for the program."
    )
    lock_token: str | None = Field(default=None, description="Lock token for the program.")


class AlphaEvolveEvaluationScore(BaseModel):
    """An evaluation score for a metric."""

    metric: str = Field(..., description="Name of the metric.")
    score: float | None = Field(
        default=None, description="Score of a program for this metric."
    )


class AlphaEvolveEvaluationScores(BaseModel):
    """Contains the evaluation scores for the target metrics to optimize."""

    scores: list[AlphaEvolveEvaluationScore] = Field(
        ..., description="List of evaluation scores."
    )


class AlphaEvolveEvaluationInsight(BaseModel):
    """An evaluation insight."""

    label: str = Field(..., description="Label of the insight.")
    text: str = Field(..., description="Text of the insight.")


class AlphaEvolveEvaluationInsights(BaseModel):
    """Represents various insights about the candidate."""

    insights: list[AlphaEvolveEvaluationInsight] = Field(
        ..., description="List of evaluation insights."
    )


class AlphaEvolveProgramEvaluation(BaseModel):
    """Evaluation results for the program."""

    scores: AlphaEvolveEvaluationScores = Field(
        ...,
        description="Contains the evaluation scores for the target metrics to optimize.",
    )
    insights: AlphaEvolveEvaluationInsights | None = Field(
        default=None,
        description="Represents various insights about the candidate, which are not directly used as optimization target, but that can be used to improve subsequent generations, and as such can be used to construct the evolution prompt.",
    )


class AlphaEvolveProgramEvaluationSubmission(BaseModel):
    """Evaluation submission for a program candidate."""

    program: str = Field(
        ...,
        description="Required. Unique identifier for the program. Format: projects/{project}/locations/{location}/collections/{collection}/engines/{engine}/sessions/{session}/alphaEvolveExperiments/{alpha_evolve_experiment}/alphaEvolvePrograms/{alpha_evolve_program}",
    )
    evaluation: AlphaEvolveProgramEvaluation = Field(
        ..., description="Required. Evaluation results for the program candidate."
    )
    lock_token: str = Field(
        ...,
        description="Required. Lock token for the program obtained in the AcquireAlphaEvolvePrograms call.",
    )
