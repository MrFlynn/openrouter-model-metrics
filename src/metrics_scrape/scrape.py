import argparse
import functools
import itertools
import json
import os
import re
import sys
from collections.abc import Iterator
from enum import StrEnum, auto
from typing import Required, TypedDict, cast

import requests
from loguru import logger


class ModelResponse(TypedDict):
    data: Required[list[Model]]
    links: Required[Links]


class Links(TypedDict):
    next: str | None


class Model(TypedDict):
    canonical_slug: Required[str]


class Modality(StrEnum):
    TEXT = auto()
    IMAGE = auto()
    AUDIO = auto()
    EMBEDDINGS = auto()
    ALL = auto()


def get_models(token: str, modality: Modality = Modality.ALL) -> Iterator[Model]:
    next_url: str | None = (
        f"https://openrouter.ai/api/v1/models?output_modalities={modality}"
    )

    while next_url:
        try:
            response = requests.get(
                next_url, headers={"Authorization": f"Bearer {token}"}
            )
            if not response.ok:
                logger.error(
                    "Model list query returned non-ok status code",
                    url=next_url,
                    status_code=response.status_code,
                )

                break

            data = cast(ModelResponse, json.loads(response.content))
            yield from data.get("data", [])

            next_url = data.get("links", {}).get("next")
        except json.JSONDecodeError:
            logger.exception("Openrouter sent malformed JSON response")
        except requests.ConnectionError, requests.ConnectTimeout:
            logger.exception("Could not connect to Openrouter API")


class ModelProviderInfo(TypedDict):
    id: Required[str]
    provider_slug: Required[str]


@functools.cache
def get_provider_ids(slug: str) -> list[ModelProviderInfo]:
    try:
        response = requests.get(
            "https://openrouter.ai/api/frontend/v1/stats/endpoint",
            params={"permaslug": slug},
        )

        if not response.ok:
            logger.error(
                "Model to provider ID query returned non-200 status code",
                url=response.request.url,
                status_code=response.status_code,
            )
            return []

        return cast(
            list[ModelProviderInfo], json.loads(response.content).get("data", [])
        )
    except json.JSONDecodeError:
        logger.exception("Openrouter return malformed JSON")
    except requests.ConnectionError, requests.ConnectTimeout:
        logger.exception("Failed to connect to Openrouter API")

    return []


def provider_id_to_name(provider_id: str, model_slug: str) -> str | None:
    trimmed_provider_id = next(iter(provider_id.split("::", 1)), "")

    return next(
        (
            provider["provider_slug"]
            for provider in get_provider_ids(model_slug)
            if provider["id"] == trimmed_provider_id
        ),
        None,
    )


class ModelStatisticType(StrEnum):
    THROUGHPUT = "throughput-comparison"
    LATENCY = "latency-comparison"
    LATENCY_E2E = "latency-e2e-comparison"
    TOOL_CALL_ERROR_RATE = "tool-call-error-rate"
    STRUCTURED_OUTPUT_ERROR_RATE = "structured-output-error-rate"
    CACHE_HIT_ERROR_RATE = "cache-hit-error-rate"

    @property
    def json_value(self) -> str:
        return self.value.removesuffix("-comparison").replace("-", "_")


class TimeBlock(TypedDict):
    x: Required[str]
    y: Required[dict[str, int]]


class ModelSingleStatistic(TypedDict):
    model: Required[str]
    provider: Required[str]
    statistic_type: Required[ModelStatisticType]
    timestamp: Required[str]
    value: Required[int | None]


def get_statistics(
    model_slug: str, statistic_type: ModelStatisticType
) -> Iterator[ModelSingleStatistic]:
    try:
        response = requests.get(
            f"https://openrouter.ai/api/frontend/v1/stats/{statistic_type}",
            params={
                "permaslug": model_slug,
                "timeRange": "3d",  # Only parameter that returns hourly stats
            },
        )

        if not response.ok:
            logger.error(
                "Model to provider ID query returned non-200 status code",
                url=response.request.url,
                status_code=response.status_code,
            )
            return

        for datum in json.loads(response.content).get("data", []):
            time_block = cast(TimeBlock, datum)

            for provider_id, value in time_block.get("y", {}).items():
                if provider_name := provider_id_to_name(provider_id, model_slug):
                    yield ModelSingleStatistic(
                        model=model_slug,
                        provider=provider_name,
                        statistic_type=statistic_type,
                        timestamp=time_block.get("x", ""),
                        value=value,
                    )

    except json.JSONDecodeError:
        logger.exception("Openrouter return malformed JSON")
    except requests.ConnectionError, requests.ConnectTimeout:
        logger.exception("Failed to connect to Openrouter API")


class ModelAllStatistics(TypedDict):
    model: Required[str]
    providers: Required[dict[str, list[dict[str, str | int | None]]]]


def collect_statistics(models: Iterator[Model]) -> Iterator[ModelAllStatistics]:
    for model in itertools.filterfalse(
        lambda m: re.fullmatch(r"^~.*-latest$", m.get("canonical_slug")), models
    ):

        def grouping(stat: ModelSingleStatistic) -> tuple[str, str]:
            return (stat.get("provider"), stat.get("timestamp"))

        statistics = list(
            itertools.chain.from_iterable(
                [
                    get_statistics(
                        model_slug=model.get("canonical_slug"), statistic_type=t
                    )
                    for t in list(ModelStatisticType)
                ]
            )
        )

        all_statistics = ModelAllStatistics(
            model=model.get("canonical_slug"), providers={}
        )

        for _, group in itertools.groupby(
            sorted(statistics, key=grouping), key=grouping
        ):
            if len(grouped_statistics := list(group)) > 0:
                all_statistics["providers"].setdefault(
                    grouped_statistics[0].get("provider"), []
                ).append(
                    {
                        "timestamp": grouped_statistics[0].get("timestamp"),
                        **{
                            s.get("statistic_type").json_value: s.get("value")
                            for s in grouped_statistics
                        },
                    }
                )

        yield all_statistics


def main() -> None:
    parser = argparse.ArgumentParser()
    _ = parser.add_argument(
        "-m",
        "--modality",
        type=Modality,
        choices=list(Modality),
        default=Modality.ALL,
        help="Output modality to query statistics for",
    )
    args = parser.parse_args()

    openrouter_token = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_token:
        logger.error("An Openrouter API key is required")
        sys.exit(1)

    print(
        json.dumps(
            list(
                collect_statistics(
                    get_models(token=openrouter_token, modality=args.modality)
                )
            )
        )
    )


if __name__ == "__main__":
    main()
