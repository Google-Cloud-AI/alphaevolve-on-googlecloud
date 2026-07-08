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
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class AlphaEvolveModelConfig(BaseModel):
    """Per-model configuration for the ``models`` mixture field.

    At most two models may be specified. Weights are *relative* and normalized
    server-side, so they need not sum to 1.0.
    """

    name: str = Field(
        ...,
        description="Required. Model name (e.g. `gemini-2.5-flash`, `gemini-3.1-pro-preview`). See `model_mixture` for the list of allowed models.",
    )
    weight: Optional[float] = Field(
        default=None,
        description=(
            "Optional. Relative weight for this model in the mixture. Must be a finite, "
            "strictly positive value. Weights across all entries are normalized server-side, "
            "so they need not sum to 1.0. Defaults to 1.0 when unset, which is convenient "
            "when configuring a single model or an even mixture. Some Pro-tier models are "
            "capped at most 50% of the total weight; requests violating that cap are rejected "
            "with INVALID_ARGUMENT."
        ),
    )


class AlphaEvolveGenerationSettings(BaseModel):
    """Generation settings for the experiment."""

    context: Optional[str] = Field(
        default=None,
        description="Optional. Additional user-provided context to be used during generation.",
    )
    models: Optional[List[AlphaEvolveModelConfig]] = Field(
        default=None,
        description="Optional. Per-model configuration. See `ModelConfig` for details.",
    )
    include_full_program_in_prompt: Optional[bool] = Field(
        default=None,
        description=(
            "Optional. When true, the LLM prompt includes the full program text (both mutable "
            "EVOLVE-BLOCK regions and immutable boilerplate). When false (default), only the "
            "mutable EVOLVE-BLOCK regions are shown, saving context window."
        ),
    )



class AlphaEvolveRunSettings(BaseModel):
    """Run settings for the experiment."""

    max_programs: Optional[int] = Field(
        default=None,
        description="Optional. Maximum number of programs to generate during the experiment run.",
    )
    concurrency: Optional[int] = Field(
        default=None,
        description="Optional. Maximum number of programs that can be generated in parallel.",
    )
    max_duration: Optional[str] = Field(
        default=None,
        description="Optional. Maximum duration of the experiment.",
    )


class AlphaEvolveParetoSamplingConfig(BaseModel):
    """Configuration for Pareto sampling."""

    pareto_sampling_probability: Optional[float] = Field(
        default=None,
        description="Optional. Probability [0.0, 1.0] of sampling parent programs from the Pareto frontier instead of normal fitness-based sampling during candidate generation. Useful when optimizing multiple metrics simultaneously. Default 0.0 (disabled). Only effective when evaluation returns multiple metrics in scores_to_optimize.",
    )


class AlphaEvolveParentSamplingConfig(BaseModel):
    """Configuration for parent sampling."""

    pareto_sampling_config: Optional[AlphaEvolveParetoSamplingConfig] = Field(
        default=None,
        description="Optional. Pareto sampling configuration.",
    )


class AlphaEvolveEvolutionSettings(BaseModel):
    """Evolution settings for the experiment."""

    parent_sampling_config: Optional[AlphaEvolveParentSamplingConfig] = Field(
        default=None,
        description="Optional. Parent sampling configuration.",
    )


class AlphaEvolveExperimentConfig(BaseModel):
    """Configuration of an experiment."""

    title: str = Field(
        ...,
        description="Required. Title of the experiment.",
    )
    problem_description: str = Field(
        ...,
        description="Required. Description of the problem to be solved by the experiment.",
    )
    program_language: str = Field(
        ...,
        description="Required. Primary programming language of the code being optimized.",
    )
    run_settings: Optional[AlphaEvolveRunSettings] = Field(
        default=None,
        description="Optional. Run settings for the experiment, controlling the overall behavior of the experiment run.",
    )
    generation_settings: Optional[AlphaEvolveGenerationSettings] = Field(
        default=None,
        description="Optional. Generation settings for the experiment, controlling how new program candidates are generated, including things LLM parameters and user-provided context and prompts.",
    )
    evolution_settings: Optional[AlphaEvolveEvolutionSettings] = Field(
        default=None,
        description="Optional. Evolution settings for the experiment.",
    )


class AlphaEvolveExperimentStats(BaseModel):
    """Stats about the experiment."""

    candidates_count: int = Field(
        default=0,
        description="Output only. Number of candidates generated.",
    )
    evaluated_candidates_count: int = Field(
        default=0,
        description="Output only. Number of candidates evaluated.",
    )
    input_token_count: Optional[str] = Field(
        default=None,
        description="Output only. Number of billed input tokens consumed by the experiment.",
    )
    output_token_count: Optional[str] = Field(
        default=None,
        description="Output only. Number of billed output tokens consumed by the experiment.",
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

    name: str = Field(
        ...,
        description="Identifier. The full resource name of the experiment. Format: `projects/{project}/locations/{location}/collections/{collection}/engines/{engine}/sessions/{session}/alphaEvolveExperiments/{alpha_evolve_experiment}`",
    )
    create_time: Optional[datetime] = Field(
        default=None,
        description="Output only. Time when the experiment was created.",
    )
    config: AlphaEvolveExperimentConfig = Field(
        ...,
        description="Required. Experiment configuration.",
    )
    stats: Optional[AlphaEvolveExperimentStats] = Field(
        default=None,
        description="Output only. Experiment stats.",
    )
    state: AlphaEvolveExperimentState = Field(
        default=AlphaEvolveExperimentState.STATE_UNSPECIFIED,
        description="Output only. The state of the experiment.",
    )
    initial_alpha_evolve_program: Optional[str] = Field(
        default=None,
        description="Output only. Specifies the name of the seed program used to start the experiment.",
    )


class AlphaEvolveSourceFile(BaseModel):
    """A single source file with its path, content and metadata."""

    path: str = Field(
        ...,
        description='Required. The relative path of the file, including the filename. e.g., "src/main.py", "utils/helpers.js", "README.md"',
    )
    content: str = Field(
        ...,
        description="Required. The raw content of the file. This is a string and not bytes, because it should be ultimately processed by the LLM as text.",
    )
    program_language: Optional[str] = Field(
        default=None,
        description="Optional. The programming language of the file.",
    )
    description: Optional[str] = Field(
        default=None,
        description="Optional. Additional description of the file.",
    )


class AlphaEvolveProgramContent(BaseModel):
    """A self-contained message containing the content of a program. Can represent a collection of files."""

    description: Optional[str] = Field(
        default=None,
        description="Optional. Description of the program.",
    )
    files: List[AlphaEvolveSourceFile] = Field(
        ...,
        description="Required. A list of source files that make up the overall program.",
    )


class AlphaEvolveEvaluationScore(BaseModel):
    """An evaluation score for a metric."""

    metric: str = Field(
        ...,
        description="Required. Name of the metric.",
    )
    score: Optional[float] = Field(
        default=None,
        description="Required. Score of a program for this metric.",
    )


class AlphaEvolveEvaluationScores(BaseModel):
    """Contains the evaluation scores for the target metrics to optimize."""

    scores: List[AlphaEvolveEvaluationScore] = Field(
        ...,
        description="Required. List of evaluation scores.",
    )


class AlphaEvolveEvaluationInsight(BaseModel):
    """An evaluation insight."""

    label: str = Field(
        ...,
        description="Optional. Label of the insight.",
    )
    text: str = Field(
        ...,
        description="Optional. Text of the insight.",
    )


class AlphaEvolveEvaluationInsights(BaseModel):
    """Represents various insights about the candidate."""

    insights: List[AlphaEvolveEvaluationInsight] = Field(
        ...,
        description="Optional. List of evaluation insights.",
    )


class AlphaEvolveProgramEvaluation(BaseModel):
    """Evaluation results for the program."""

    scores: AlphaEvolveEvaluationScores = Field(
        ...,
        description="Optional. Contains the evaluation scores for the target metrics to optimize.",
    )
    insights: Optional[AlphaEvolveEvaluationInsights] = Field(
        default=None,
        description="Optional. Represents various insights about the candidate, which are not directly used as optimization target, but that can be used to improve subsequent generations, and as such can be used to construct the evolution prompt.",
    )


class AlphaEvolveProgramEvaluationSubmission(BaseModel):
    """Evaluation submission for a program candidate."""

    program: str = Field(
        ...,
        description="Required. Unique identifier for the program. Format: `projects/{project}/locations/{location}/collections/{collection}/engines/{engine}/sessions/{session}/alphaEvolveExperiments/{alpha_evolve_experiment}/alphaEvolvePrograms/{alpha_evolve_program}`",
    )
    evaluation: AlphaEvolveProgramEvaluation = Field(
        ...,
        description="Required. Evaluation results for the program candidate.",
    )
    lock_token: str = Field(
        ...,
        description="Required. Lock token for the program obtained in the AcquireAlphaEvolvePrograms call.",
    )


class AlphaEvolveProgram(BaseModel):
    """Represents a single program to be used within the context of an AlphaEvolve experiment."""

    name: str = Field(
        ...,
        description="Identifier. Unique identifier for the program. Format: `projects/{project}/locations/{location}/collections/{collection}/engines/{engine}/sessions/{session}/alphaEvolveExperiments/{alpha_evolve_experiment}/alphaEvolvePrograms/{alpha_evolve_program}`",
    )
    create_time: Optional[datetime] = Field(
        default=None,
        description="Output only. Time when the program was created.",
    )
    content: Optional[AlphaEvolveProgramContent] = Field(
        default=None,
        description="Optional. Content of the program.",
    )
    evaluation: Optional[AlphaEvolveProgramEvaluation] = Field(
        default=None,
        description="Optional. Evaluation results for the program.",
    )
    lock_token: Optional[str] = Field(
        default=None,
        description="Optional. Lock token for the program.",
    )
    parent_programs: Optional[List[str]] = Field(
        default=None,
        description="Output only. Optionally specifies which parent programs this program was evolved from. Format: `projects/{project}/locations/{location}/collections/{collection}/engines/{engine}/sessions/{session}/alphaEvolveExperiments/{alpha_evolve_experiment}/alphaEvolvePrograms/{alpha_evolve_program}`",
    )
    state: Optional[str] = Field(
        default=None,
        description="Output only. State of the program.",
    )


class AlphaEvolveListExperimentsResponse(BaseModel):
    """Response message for AlphaEvolveService.ListAlphaEvolveExperiments."""

    alpha_evolve_experiments: List[AlphaEvolveExperiment] = Field(
        default=[],
        description="Output only. List of experiments.",
    )
    next_page_token: Optional[str] = Field(
        default=None,
        description="Output only. A token, which can be sent as `page_token` to retrieve the next page. If this field is omitted, there are no subsequent pages.",
    )


class AlphaEvolveListProgramsResponse(BaseModel):
    """Response message for AlphaEvolveService.ListAlphaEvolvePrograms."""

    alpha_evolve_programs: List[AlphaEvolveProgram] = Field(
        default=[],
        description="Output only. List of programs matching the criteria provided in the request.",
    )
    next_page_token: Optional[str] = Field(
        default=None,
        description="Output only. A token, which can be sent as `page_token` to retrieve the next page. If this field is omitted, there are no subsequent pages.",
    )
