from __future__ import annotations

import httpx

from evidencemesh.config import Settings
from evidencemesh.providers.arxiv import ArxivProvider
from evidencemesh.providers.base import SearchProvider
from evidencemesh.providers.brave import BraveProvider
from evidencemesh.providers.crossref import CrossrefProvider
from evidencemesh.providers.ddgs import DDGSProvider
from evidencemesh.providers.exa import ExaProvider
from evidencemesh.providers.firecrawl import FirecrawlProvider
from evidencemesh.providers.github import GitHubProvider
from evidencemesh.providers.openalex import OpenAlexProvider
from evidencemesh.providers.searxng import SearxngProvider
from evidencemesh.providers.tavily import TavilyProvider
from evidencemesh.providers.wikipedia import WikipediaProvider


def build_providers(
    settings: Settings,
    client: httpx.AsyncClient,
) -> tuple[list[SearchProvider], list[str]]:
    providers: list[SearchProvider] = []
    warnings: list[str] = []
    for name in settings.enabled_providers:
        if name == "arxiv":
            providers.append(ArxivProvider(settings.arxiv_url, client))
        elif name == "searxng":
            urls = list(
                dict.fromkeys(
                    [
                        settings.searxng_url.rstrip("/"),
                        *settings.searxng_fallback_urls,
                    ]
                )
            )
            providers.extend(
                SearxngProvider(
                    url,
                    client,
                    name="searxng" if index == 1 else f"searxng-{index}",
                )
                for index, url in enumerate(urls, start=1)
            )
        elif name == "ddgs":
            providers.append(DDGSProvider())
        elif name == "wikipedia":
            providers.append(WikipediaProvider(settings.wikipedia_url_template, client))
        elif name == "crossref":
            providers.append(
                CrossrefProvider(settings.crossref_url, client, settings.crossref_mailto)
            )
        elif name == "github":
            providers.append(
                GitHubProvider(
                    settings.github_search_url,
                    client,
                    settings.github_token,
                )
            )
        elif name == "openalex":
            if settings.openalex_api_key:
                providers.append(
                    OpenAlexProvider(
                        settings.openalex_url,
                        settings.openalex_api_key,
                        client,
                    )
                )
            else:
                warnings.append("openalex disabled: OPENALEX_API_KEY is not configured")
        elif name == "brave":
            if settings.brave_api_key:
                providers.append(BraveProvider(settings.brave_api_key, client))
            else:
                warnings.append("brave disabled: BRAVE_API_KEY is not configured")
        elif name == "tavily":
            if settings.tavily_api_key:
                providers.append(TavilyProvider(settings.tavily_api_key, client))
            else:
                warnings.append("tavily disabled: TAVILY_API_KEY is not configured")
        elif name == "exa":
            if settings.exa_api_key:
                providers.append(ExaProvider(settings.exa_api_key, client))
            else:
                warnings.append("exa disabled: EXA_API_KEY is not configured")
        elif name == "firecrawl":
            cloud_url = settings.firecrawl_url.rstrip("/") == "https://api.firecrawl.dev"
            if cloud_url and not settings.firecrawl_api_key:
                warnings.append("firecrawl disabled: FIRECRAWL_API_KEY is not configured")
            else:
                providers.append(
                    FirecrawlProvider(
                        settings.firecrawl_url,
                        client,
                        settings.firecrawl_api_key,
                    )
                )
    return providers, warnings
