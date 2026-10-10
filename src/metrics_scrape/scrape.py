import argparse
import functools
import itertools
import json
import os
import re
import sys
from collections.abc import Iterator
from typing import cast

import requests
from loguru import logger

from .models import (
    GenericAPIResponse,
    Modality,
    Model,
    ModelAllStatistics,
    ModelProviderInfo,
    ModelSingleStatistic,
    ModelStatisticType,
    ProviderStatistics,
    TimeBlock,
)


def send_request[T](
    request: requests.Request, session: requests.Session | None, *, _hint: type[T]
) -> T | None:
    with logger.contextualize(
        method=request.method, url=request.url, model=request.params.get("permaslug")
    ):
        try:
            if not session:
                session = requests.Session()

            response = session.send(request.prepare())
            if not response.ok:
                logger.bind(status_code=response.status_code).error(
                    "Query returned non-ok status code"
                )

            return cast(T, json.loads(response.content))
        except json.JSONDecodeError:
            logger.exception("Openrouter return malformed JSON")
        except requests.ConnectionError, requests.ConnectTimeout:
            logger.exception("Failed to open connection to Openrouter API")


def get_models(token: str, modality: Modality = Modality.ALL) -> Iterator[Model]:
    session = requests.Session()

    prefix = "https://openrouter.ai"
    next_url: str | None = (
        f"/api/v1/models?output_modalities={modality}"
    )

    while next_url:
        if data := send_request(
            requests.Request(
                "GET", prefix + next_url, headers={"Authorization": f"Bearer {token}"}
            ),
            session,
            _hint=GenericAPIResponse[list[Model]],
        ):
            yield from data.get("data", [])
            next_url = data.get("links", {}).get("next")


@functools.cache
def get_provider_ids(slug: str) -> list[ModelProviderInfo]:
    if data := send_request(
        requests.Request(
            "GET",
            "https://openrouter.ai/api/frontend/v1/stats/endpoint",
            params={"permaslug": slug},
        ),
        None,
        _hint=GenericAPIResponse[list[ModelProviderInfo]],
    ):
        return data.get("data", [])

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


def get_statistics(
    model_slug: str, statistic_type: ModelStatisticType
) -> Iterator[ModelSingleStatistic]:
    if data := send_request(
        requests.Request(
            "GET",
            f"https://openrouter.ai/api/frontend/v1/stats/{statistic_type}",
            params={"permaslug": model_slug, "timeRange": "3d"},
        ),
        None,
        _hint=GenericAPIResponse[list[TimeBlock]],
    ):
        for time_block in data.get("data", []):
            for provider_id, value in time_block.get("y", {}).items():
                if provider_name := provider_id_to_name(provider_id, model_slug):
                    yield ModelSingleStatistic(
                        model=model_slug,
                        provider=provider_name,
                        statistic_type=statistic_type,
                        timestamp=time_block.get("x", ""),
                        value=value,
                    )


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
                    ProviderStatistics(
                        timestamp=grouped_statistics[0].get("timestamp"),
                        **{
                            s.get("statistic_type").json_value: s.get("value")
                            for s in grouped_statistics
                        },
                    )
                )

        yield all_statistics


def main() -> None:
    logger.remove()
    _ = logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
        + "| <level>{level: <8}</level> "
        + "| <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level> "
        + "| {extra}",
    )

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
