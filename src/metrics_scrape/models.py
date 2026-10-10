from enum import StrEnum, auto
from typing import NotRequired, Required, TypedDict


class Modality(StrEnum):
    TEXT = auto()
    IMAGE = auto()
    AUDIO = auto()
    EMBEDDINGS = auto()
    ALL = auto()


class ModelStatisticType(StrEnum):
    THROUGHPUT = "throughput-comparison"
    LATENCY = "latency-comparison"
    LATENCY_E2E = "latency-e2e-comparison"
    TOOL_CALL_ERROR_RATE = "tool-call-error-rate"
    STRUCTURED_OUTPUT_ERROR_RATE = "structured-output-error-rate"
    CACHE_HIT_RATE = "cache-hit-rate-comparison"

    @property
    def json_value(self) -> str:
        return self.value.removesuffix("-comparison").replace("-", "_")


# Generic API Wrappers for all API responses
class GenericAPIResponse[T](TypedDict):
    data: Required[T]
    links: Required[Links]


class Links(TypedDict):
    next: str | None


# Model API response: /api/v1/models
class Model(TypedDict):
    canonical_slug: Required[str]


# Model statistic page slug to ID: /api/frontend/v1/stats/endpoint
class ModelProviderInfo(TypedDict):
    id: Required[str]
    provider_slug: Required[str]


# Generic graphed model data: /api/frontend/v1/stats/
class TimeBlock(TypedDict):
    """
    Contains the numeric value for all providers for a given statistic at
    a specific timestamp.

    x: timestamp
    y: mapping of provider IDs to numeric values
    """

    x: Required[str]
    y: Required[dict[str, int | float]]


# Single statistic entry decoded from each time block.
class ModelSingleStatistic(TypedDict):
    model: Required[str]
    provider: Required[str]
    statistic_type: Required[ModelStatisticType]
    timestamp: Required[str]
    value: Required[int | float]


# All statistics for a given model combined into a single dictionary.
class ModelAllStatistics(TypedDict):
    model: Required[str]
    providers: Required[dict[str, list[ProviderStatistics]]]


class ProviderStatistics(TypedDict):
    timestamp: Required[str]
    throughput: NotRequired[int | float]
    latency: NotRequired[int | float]
    latency_e2e: NotRequired[int | float]
    tool_call_error_rate: NotRequired[int | float]
    structured_output_error_rate: NotRequired[int | float]
    cache_hit_rate: NotRequired[int | float]
