# Conversion script for `git-history` tool. Transforms the shape of the the
# data in mode-metrics.json to a flat row-priented model expected by SQLite.
# Loading this in your editor will result in various errors being reported.
# This is fine. This script is only meant to be used with git-history. See the
# README for more information on usage.

value_extractor = re.compile(r"((?P<value>\d+\.?\d*)|(?P<null>--))(tps|s)")


def get_metric_value(s: str) -> float | None:
    try:
        if bool(match := value_extractor.match(s)):
            if bool(value := match.groupdict().get("value")):
                return float(value)

            return None
    except ValueError:
        return None


for model in json.loads(content):
    if bool(model_name := model.get("model")):
        for provider in model.get("providers", []):
            if bool(provider_name := provider.get("provider")):
                yield {
                    "model": model_name,
                    "provider": provider_name,
                    "tokens_per_second": get_metric_value(
                        provider.get("throughput", "")
                    ),
                    "time_to_first_token": get_metric_value(
                        provider.get("latency", "")
                    ),
                }
