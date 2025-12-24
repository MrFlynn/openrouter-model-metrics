#!/usr/bin/env python3
# /// script
# dependencies = ["crawlee[playwright]"]
# ///

import asyncio
import re
from collections.abc import AsyncIterator, Awaitable, Callable

from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext
from playwright.async_api import Locator, Page


async def extract_provider_statistics(
    page: Page,
) -> AsyncIterator[dict[str, str | None]]:
    async def get_sibling_text(el: Locator) -> str | None:
        return await el.locator("xpath=following-sibling::*").first.text_content()

    for article in await page.locator("article").all():
        yield {
            "provider": await article.locator("a[href^='/provider']").text_content(),
            "latency": await get_sibling_text(
                article.locator("div.text-xs", has_text="Latency")
            ),
            "throughput": await get_sibling_text(
                article.locator("div.text-xs", has_text="Throughput")
            ),
        }


# This is a function decorator that allows us to patch over issues parsing the computed
# height of elements on a page. Due to the fact that the target page dynamically loads
# elements into the list on scroll, their computed style attributes may not have been
# computed by the browser yet. This allows to intercept those instances (height = "") and
# return an average value that we store from cases where the styles have been properly computed.
def always_return_value(
    func: Callable[[Locator], Awaitable[int]],
) -> Callable[[Locator], Awaitable[int]]:
    sum, count = 0, 0

    async def wrapper(locator: Locator) -> int:
        nonlocal sum, count

        try:
            result = await func(locator)

            sum += result
            count += 1

            return result
        except ValueError:
            return sum // count if count > 0 else 0

    # Allow bypass of decorator.
    wrapper.__wrapped__ = func  # type: ignore
    return wrapper


@always_return_value
async def get_element_height(locator: Locator) -> int:
    return int(
        str(
            await locator.evaluate("el => window.getComputedStyle(el).height")
        ).removesuffix("px")
    )


async def wait_until_scroll_stabilizes(
    page: Page, max_stable_frames: int = 10, timeout_seconds: float = 5
) -> None:
    async def wait_until_list_stabilizes():
        prev_hrefs: list[str] | None = None
        stable_frame_count = 0

        while stable_frame_count < max_stable_frames:
            current_hrefs = await page.eval_on_selector_all(
                "li.group a[href]", "els => els.map(e => e.getAttribute('href'))"
            )

            if current_hrefs == prev_hrefs:
                stable_frame_count += 1
            else:
                stable_frame_count = 0

            prev_hrefs = current_hrefs
            await page.evaluate("() => new Promise(r => requestAnimationFrame(r))")

    task = asyncio.create_task(wait_until_list_stabilizes())

    try:
        await asyncio.wait_for(task, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        task.cancel()
        raise


async def main() -> None:
    crawler = PlaywrightCrawler(
        respect_robots_txt_file=True,
        browser_launch_options={"chromium_sandbox": False},
    )

    @crawler.router.handler(label="model")
    async def model_page_handler(context: PlaywrightCrawlingContext) -> None:
        page = context.page
        await page.wait_for_load_state("domcontentloaded")

        # Click button to unfold more content and wait for load to complete.
        if (
            await (
                button := page.locator("button", has_text=re.compile(r"Show \d+ more"))
            ).count()
            > 1
        ):
            await button.first.click()
            await page.wait_for_load_state()

        statistics = {
            "model": await page.locator(
                "h3[title='Model identifier for use in the API']"
            ).text_content(),
            "providers": [item async for item in extract_provider_statistics(page)],
        }

        context.log.info(
            f"Collected {len(statistics['providers'])} "
            + f"provider{'s' if len(statistics['providers']) > 1 else ''} "
            + f"for {statistics['model']}"
        )

        await context.push_data(statistics)

    @crawler.router.default_handler
    async def entrypoint_handler(context: PlaywrightCrawlingContext) -> None:
        page = context.page
        await page.wait_for_load_state("domcontentloaded")

        list_container = page.locator("ul").first

        # Get total height of function without influencing the average stored in the decorator.
        # We only want to keep the average for list items.
        total_height = await get_element_height.__wrapped__(list_container)  # type: ignore
        current_position = 0

        context.log.info(f"Collecting links from {page.url}")

        while current_position <= total_height:
            # Enqueue links for models that have seen non-zero activity in the past week.
            await context.enqueue_links(
                selector="ul li:not(:has(div[title='Tokens this week']:empty)) a:not(:is(span a))",
                label="model",
            )

            dy = sum(
                await asyncio.gather(
                    *[
                        get_element_height(li)
                        for li in await page.locator("ul li").all()
                    ]
                )
            )

            await page.mouse.wheel(0, dy)
            await wait_until_scroll_stabilizes(page)

            current_position += dy

        context.log.info("Finished enqueueing model page links")

    await crawler.run(["https://openrouter.ai/models"])
    await crawler.export_data("model-metrics.json")


if __name__ == "__main__":
    result = asyncio.run(main())
