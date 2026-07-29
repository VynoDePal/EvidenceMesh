# EvidenceMesh

[![CI](https://github.com/VynoDePal/EvidenceMesh/actions/workflows/ci.yml/badge.svg)](https://github.com/VynoDePal/EvidenceMesh/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB.svg)](pyproject.toml)
[![MCP](https://img.shields.io/badge/MCP-FastMCP-5B45FF.svg)](https://gofastmcp.com/)

Evidence-first, provider-neutral web search and deep-research infrastructure for
AI agents.

EvidenceMesh is a Python SDK, CLI and FastMCP server. It federates multiple
search engines, fuses their rankings, removes duplicates, extracts public
HTML/PDF content and returns compact evidence with stable `[S#]` citations.
The core works without a paid API or a bundled language model.

> **Status:** `0.1.0` alpha. The implementation is tested, but no claim of
> superior end-to-end research quality is made until comparable public
> benchmark runs are available.

## Why another search MCP?

Most search MCPs are thin wrappers around one paid API. Most deep-research
projects bundle a particular model, search service and report writer.
EvidenceMesh separates those concerns:

- **Free core:** self-hosted SearXNG plus direct Wikipedia, Crossref, arXiv and
  GitHub repository adapters; DDGS is an environment-sensitive opt-in.
- **Deterministic routing:** web, reference, academic and code sources receive
  only compatible queries, with conservative budgets for rate-limited APIs and
  profile-aware domain diversity.
- **Provider federation:** reciprocal-rank fusion across independent result lists.
- **Evidence, not hidden answers:** quotations, retrieval time, content hash,
  provenance signals and risk flags.
- **Model neutral:** the MCP client keeps control of reasoning and synthesis.
- **Defensive retrieval:** public-network URL policy, DNS-pinned connections,
  redirect revalidation, total deadlines, byte/page limits, bounded robots.txt,
  active-content removal and prompt-injection flags.
- **Reproducible evaluation:** deterministic algorithm benchmark plus a live
  retrieval harness for public QA datasets.

## Architecture

```mermaid
flowchart TD
    A["AI client / Python app"] --> B["FastMCP · SDK · CLI"]
    B --> C["Query plan"]
    C --> D["Provider federation"]
    D --> E["RRF · dedup · diversity"]
    E --> F["Safe fetch · HTML/PDF extraction"]
    F --> G["Evidence ledger · [S#] citations"]
```

The calling model receives structured evidence and a synthesis protocol. Web
pages never become model instructions.

## Quick start

Requirements: Python 3.11+ and [uv](https://docs.astral.sh/uv/). Docker is
required for the recommended free general-web path because it runs the private
default SearXNG service.

```bash
git clone https://github.com/VynoDePal/EvidenceMesh.git
cd EvidenceMesh
uv sync

# Start a private local SearXNG instance.
docker compose up -d searxng

uv run evidencemesh search "FastMCP HTTP transport" --fetch-content
uv run evidencemesh research "Compare open source deep-research systems"
```

If SearXNG is unavailable, the other configured providers still run and the
response contains an explicit partial-failure warning. After three consecutive
failures, EvidenceMesh opens that provider's process-local circuit for 60
seconds so later searches do not repeatedly inherit its full deadline. One
half-open recovery probe is allowed after the cooldown.

## MCP setup

### STDIO

Add this server to any MCP-compatible client. Replace `/absolute/path`:

```json
{
  "mcpServers": {
    "evidencemesh": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/EvidenceMesh",
        "run",
        "evidencemesh-mcp"
      ]
    }
  }
}
```

### Streamable HTTP

```bash
uv run evidencemesh serve --transport http --host 127.0.0.1 --port 8000
```

The MCP endpoint is `http://127.0.0.1:8000/mcp`. A public deployment must add
TLS, authentication and rate limiting in front of the server.

## MCP tools

| Tool | Purpose |
|---|---|
| `search_web` | Federated search, ranking, deduplication and optional extraction |
| `deep_research` | Multi-query, citation-ready evidence packet |
| `fetch_url` | Bounded extraction of one public HTML, text or PDF URL |
| `batch_search` | Up to 20 searches with bounded concurrency |
| `verify_claim` | Collect evidence and counter-searches without a truth verdict |
| `health` | Provider and safety configuration without network calls |

The `evidence_first_research` MCP prompt provides a complete client-side
research workflow.

## Providers

| Provider | Key required | `community` | `quality` | Profiles |
|---|---:|---:|---:|---|
| SearXNG | No | Yes | Yes | Web, news |
| Wikipedia | No | Yes | Yes | Web, reference, academic |
| Crossref | No | Yes | Yes | Academic |
| arXiv | No | Yes | Yes | Academic |
| GitHub repositories | No; token optional | Yes | Yes | Code |
| Tavily | Yes | No | Yes when configured | Web, news |
| OpenAlex | Free key | No | Explicit opt-in | Academic |
| Brave | Yes | No | Explicit opt-in | Web, news, academic, code |
| Exa | Yes | No | Explicit opt-in | Web, news, academic, code |
| Firecrawl | Cloud only | No | Explicit opt-in | Web, news, academic, code |
| DDGS | No | No | No | Web, news, academic, code |

The default `community` profile requires no API key and remains a best-effort
self-hosted route. The recommended `quality` profile adds Tavily when
`TAVILY_API_KEY` is configured; a missing key produces a visible configuration
warning and a degraded health status. Other keyed adapters remain available
through an explicit provider list, but are not silently added to the
recommended quality bundle.

```bash
# Named bundles.
export EVIDENCEMESH_DEPLOYMENT_PROFILE=community  # or quality

# Required by the recommended quality profile.
export TAVILY_API_KEY=...

# An explicit list overrides the selected bundle.
export EVIDENCEMESH_PROVIDERS=searxng,wikipedia,crossref,arxiv,github
export EVIDENCEMESH_SEARXNG_URL=http://127.0.0.1:8888
export EVIDENCEMESH_PROVIDER_FAILURE_THRESHOLD=3
export EVIDENCEMESH_PROVIDER_RECOVERY_SECONDS=60
```

Optional keys use `OPENALEX_API_KEY`, `GITHUB_TOKEN`, `BRAVE_API_KEY`,
`TAVILY_API_KEY`, `EXA_API_KEY` and `FIRECRAWL_API_KEY`. A self-hosted
Firecrawl endpoint can be selected with `EVIDENCEMESH_FIRECRAWL_URL` and does
not require a key.

See [provider documentation](docs/providers.md) for limitations and data flow.

## Python SDK

```python
import asyncio

from evidencemesh import EvidenceMesh, ResearchRequest


async def main() -> None:
    async with EvidenceMesh() as engine:
        packet = await engine.research(
            ResearchRequest(
                question="What changed in the latest stable FastMCP release?",
                language="en",
                max_sources=12,
            )
        )
        for item in packet.evidence:
            print(item.citation_id, item.title, item.url)


asyncio.run(main())
```

## Evaluation

```bash
# Unit, integration, MCP contract and safety tests.
uv run pytest

# Deterministic RRF/dedup regression benchmark.
uv run evidencemesh benchmark-offline

# Interleaved zero-key retrieval pilot on checksum-pinned SimpleQA.
uv run python benchmarks/run_live_retrieval.py \
  --simpleqa \
  --sample-size 30 \
  --seed 0 \
  --max-results 10 \
  --output benchmarks/results/simpleqa_retrieval_pilot_2026-07-28.json
```

The offline benchmark tests algorithms, not real-world search quality. Live
results must record provider configuration, date, dataset sample and hardware.
See the [benchmark methodology](docs/benchmarking.md), the
[Phase 2/3 protocol](docs/benchmark-protocol-v1.md), the
[locked Phase 4 protocol](docs/benchmark-protocol-v2.md), the
[locked Phase 5 protocol](docs/benchmark-protocol-v3.md), the
[locked Phase 6 protocol](docs/benchmark-protocol-v4.md), the
[locked Phase 7 protocol](docs/benchmark-protocol-v5.md), the
[locked Phase 8 protocol](docs/benchmark-protocol-v6.md), the
[end-to-end guide](docs/end-to-end-benchmark.md), the
[competitive snapshot](docs/competitive-benchmark.md) and the committed
[offline v1 result](benchmarks/results/offline_v1.md). A
[zero-key live smoke test](benchmarks/results/live_smoke_2026-07-28.md) records
connectivity and partial-failure behavior without presenting one question as a
quality score. The
[30-row SimpleQA retrieval pilot](benchmarks/results/simpleqa_retrieval_pilot_2026-07-28.md)
is the first comparative live baseline; it records a no-go for superiority and
release claims. The
[200-row Phase 3 reliability run](benchmarks/results/simpleqa_retrieval_phase3_2026-07-28.md)
shows the circuit breaker reducing sustained federated p95 latency to 888 ms,
but only 70.5% availability; the release decision therefore remains no-go.
Phase 4 replaces that measured DDGS dependency with the private SearXNG
default, adds a provenance-locked 200-case GitHub benchmark, and introduces a
controlled end-to-end generation runner. The
[Phase 4 result](benchmarks/results/simpleqa_retrieval_phase4_2026-07-28.md)
found only 71.5% federated availability and a 98.0% partial-query failure rate
because the SearXNG upstream path became unavailable. The release decision
therefore remains no-go. No answer-quality score is claimed until the separate
official evaluator is run. Phase 5 calibrates eight keyless SearXNG engines on
a separate 12-query suite. Its pre-registered gate prevents tuning and
evaluating on the same SimpleQA questions: a new 200-case run is allowed only
if at least two engines pass every reliability and relevance threshold. The
valid
[Phase 5 calibration](benchmarks/results/searxng_calibration_phase5_2026-07-28.md)
found only one eligible engine: DuckDuckGo returned results for 12/12 cases and
found the target domain for 11/12, while every other candidate failed at least
one gate. Because `1 < 2`, production configuration is unchanged and the
200-case retrieval and local-model stages were not run. Phase 6 evaluates a
different, multi-source composition: DuckDuckGo is isolated behind private
SearXNG for general web, while direct reference, academic and repository
verticals add independent coverage. Its protocol requires successful
replication on two independently administered networks; that release gate
cannot be waived when only one environment is available. The
[Phase 6 calibration](benchmarks/results/multisource_calibration_phase6_2026-07-28.md)
returned results for 24/24 cases and hit the target domain and expected source
family for 22/24, with five providers and all four families contributing.
However, SearXNG failed in 8/12 routed cases, producing a 33.3% partial-failure
rate above the locked 25% maximum. The functional gate therefore failed, the
200-case stage was not run, and the release decision remains no-go. Phase 7
adds an explicit reference route, separates raw provider degradation from
required-family satisfaction, and freezes a new 32-case quality-profile
calibration. Tavily is capped at one basic request per web case and eight
credits for the complete run. The
[Phase 7 result](benchmarks/results/quality_calibration_phase7_2026-07-29.md)
found Tavily successful and contributing in 8/8 web cases, with all eight web
targets retrieved. The complete candidate nevertheless hit only 18/32 exact
targets because academic reached 2/8 and code reached 0/8. The functional,
two-network and release gates therefore remain closed, and Stage B was not
run. Phase 8 preserves that frozen result and evaluates the identified defects
on another untouched 32-case suite. It gives single-domain verticals all ten
result slots, normalizes natural-language repository intent for GitHub, matches
canonical target identities instead of URL prefixes, and records whether an
upstream target was later removed by ranking. Tavily remains capped at eight
basic calls. The protocol is locked before the first live request; the
two-network and release gates remain closed regardless of a one-network
functional result.

The
[Phase 8 result](benchmarks/results/quality_calibration_phase8_2026-07-29.md)
returned evidence and the required source family for 32/32 cases and hit 26/32
canonical targets, clearing every overall gate. Reference reached 8/8 and
academic 7/8, but repository code reached only 4/8 against the locked 6/8
minimum. Five of the six misses were absent upstream and one web target was
dropped by ranking. The per-topic functional gate therefore failed, Stage B
was not run, and the release decision remains no-go.

## Security

EvidenceMesh blocks private, loopback, link-local and reserved fetch targets by
default. Document connections are pinned to the public addresses that passed
validation. It also limits redirects, time, bytes and PDF pages; bounds and
respects robots.txt; strips active HTML content; and labels common
prompt-injection patterns.

These controls are risk reduction, not a sandbox or a truth detector. Read the
[threat model](docs/threat-model.md) before remote deployment. The dated
[v0.1 security and release audit](docs/security-audit-v0.1.md) records the
closed findings, test methods and residual risks.

## Development

```bash
uv sync --extra dev
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

Contributions are welcome when benchmark claims are reproducible and provider
costs or quotas are stated explicitly. See [CONTRIBUTING.md](CONTRIBUTING.md).

The current suite contains 226 tests and reports over 91% branch-aware coverage
locally. CI repeats the suite on Python 3.11, 3.12 and 3.13.

## License

EvidenceMesh is released under the [Apache License 2.0](LICENSE). SearXNG is a
separate service distributed under its own AGPL-3.0 license; EvidenceMesh only
communicates with it through its documented HTTP API.
