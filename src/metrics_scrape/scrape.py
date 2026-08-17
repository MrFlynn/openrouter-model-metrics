import argparse
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
                logger.warning(
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
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

    for model in itertools.filterfalse(
        lambda m: re.fullmatch(r"^~.*-latest$", m.get("canonical_slug")),
        get_models(token=openrouter_token, modality=args.modality),
    ):
        print(model.get("canonical_slug"))


if __name__ == "__main__":
    main()
