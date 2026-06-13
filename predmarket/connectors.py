"""Real-data connector contracts for research ingestion.

Connectors return raw payloads or timestamped SourceDocument objects and never
silently substitute fake live data. If credentials or endpoints are missing,
they raise ConnectorUnavailable so callers can skip the source explicitly.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from predmarket.contracts import SourceDocument, stable_hash


class ConnectorUnavailable(RuntimeError):
    pass


@dataclass
class ConnectorResponse:
    source: str
    retrieved_ts: float
    raw_payload: Dict[str, Any]


class HTTPConnector:
    source_name = "http"

    def __init__(self, session: Any = None, timeout_seconds: float = 10.0):
        self.session = session
        self.timeout_seconds = timeout_seconds

    async def _get_json(
        self, url: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if self.session is None:
            raise ConnectorUnavailable(f"{self.source_name} session is not initialized")
        async with self.session.get(url, params=params, timeout=self.timeout_seconds) as resp:
            if resp.status >= 400:
                raise ConnectorUnavailable(
                    f"{self.source_name} returned HTTP {resp.status} for {url}"
                )
            return await resp.json()


class PolymarketCLOBConnector(HTTPConnector):
    source_name = "polymarket_clob"

    def __init__(self, session: Any = None, base_url: str = "https://clob.polymarket.com"):
        super().__init__(session=session)
        self.base_url = base_url.rstrip("/")

    async def fetch_book(self, token_id: str) -> ConnectorResponse:
        payload = await self._get_json(f"{self.base_url}/book", {"token_id": token_id})
        return ConnectorResponse(self.source_name, time.time(), payload)

    async def fetch_markets(self) -> ConnectorResponse:
        payload = await self._get_json(f"{self.base_url}/markets")
        return ConnectorResponse(self.source_name, time.time(), payload)


class KalshiConnector(HTTPConnector):
    source_name = "kalshi"

    def __init__(self, session: Any = None, base_url: str = "https://api.elections.kalshi.com/trade-api/v2"):
        super().__init__(session=session)
        self.base_url = base_url.rstrip("/")

    async def fetch_markets(self, limit: int = 200) -> ConnectorResponse:
        payload = await self._get_json(f"{self.base_url}/markets", {"limit": limit})
        return ConnectorResponse(self.source_name, time.time(), payload)

    async def fetch_orderbook(self, ticker: str) -> ConnectorResponse:
        payload = await self._get_json(f"{self.base_url}/markets/{ticker}/orderbook")
        return ConnectorResponse(self.source_name, time.time(), payload)


class MetaculusConnector(HTTPConnector):
    source_name = "metaculus"

    def __init__(self, session: Any = None, base_url: str = "https://www.metaculus.com/api2"):
        super().__init__(session=session)
        self.base_url = base_url.rstrip("/")

    async def fetch_question(self, question_id: str) -> ConnectorResponse:
        payload = await self._get_json(f"{self.base_url}/questions/{question_id}/")
        return ConnectorResponse(self.source_name, time.time(), payload)


class ManifoldConnector(HTTPConnector):
    source_name = "manifold"

    def __init__(self, session: Any = None, base_url: str = "https://api.manifold.markets/v0"):
        super().__init__(session=session)
        self.base_url = base_url.rstrip("/")

    async def fetch_market(self, market_id: str) -> ConnectorResponse:
        payload = await self._get_json(f"{self.base_url}/market/{market_id}")
        return ConnectorResponse(self.source_name, time.time(), payload)


class GDELTConnector(HTTPConnector):
    source_name = "gdelt"

    def __init__(self, session: Any = None, base_url: str = "https://api.gdeltproject.org/api/v2/doc/doc"):
        super().__init__(session=session)
        self.base_url = base_url

    async def search_documents(self, query: str, max_records: int = 25) -> List[SourceDocument]:
        payload = await self._get_json(
            self.base_url,
            {
                "query": query,
                "mode": "artlist",
                "format": "json",
                "maxrecords": max_records,
                "sort": "hybridrel",
            },
        )
        docs: List[SourceDocument] = []
        retrieved_ts = time.time()
        for article in payload.get("articles", []):
            url = article.get("url", "")
            title = article.get("title", "")
            published_ts = _parse_gdelt_ts(article.get("seendate")) or retrieved_ts
            docs.append(
                SourceDocument(
                    source_id=stable_hash({"source": self.source_name, "url": url, "title": title}),
                    source=self.source_name,
                    title=title,
                    url=url,
                    published_ts=published_ts,
                    retrieved_ts=retrieved_ts,
                    text=article.get("domain", ""),
                    metadata=article,
                )
            )
        return docs


class FederalRegisterConnector(HTTPConnector):
    source_name = "federal_register"

    def __init__(self, session: Any = None, base_url: str = "https://www.federalregister.gov/api/v1"):
        super().__init__(session=session)
        self.base_url = base_url.rstrip("/")

    async def search_documents(self, query: str, per_page: int = 20) -> List[SourceDocument]:
        payload = await self._get_json(
            f"{self.base_url}/documents.json",
            {"conditions[term]": query, "per_page": per_page, "order": "newest"},
        )
        retrieved_ts = time.time()
        docs = []
        for item in payload.get("results", []):
            published_ts = _parse_date(item.get("publication_date")) or retrieved_ts
            docs.append(
                SourceDocument(
                    source_id=stable_hash({"source": self.source_name, "id": item.get("document_number")}),
                    source=self.source_name,
                    title=item.get("title", ""),
                    url=item.get("html_url", item.get("pdf_url", "")),
                    published_ts=published_ts,
                    retrieved_ts=retrieved_ts,
                    text=item.get("abstract", ""),
                    metadata=item,
                )
            )
        return docs


class WikipediaPageviewsConnector(HTTPConnector):
    source_name = "wikipedia_pageviews"

    def __init__(self, session: Any = None, base_url: str = "https://wikimedia.org/api/rest_v1"):
        super().__init__(session=session)
        self.base_url = base_url.rstrip("/")

    async def fetch_pageviews(
        self, article: str, start_yyyymmdd: str, end_yyyymmdd: str
    ) -> ConnectorResponse:
        safe_article = article.replace(" ", "_")
        url = (
            f"{self.base_url}/metrics/pageviews/per-article/en.wikipedia/all-access/"
            f"all-agents/{safe_article}/daily/{start_yyyymmdd}/{end_yyyymmdd}"
        )
        payload = await self._get_json(url)
        return ConnectorResponse(self.source_name, time.time(), payload)


class FREDConnector(HTTPConnector):
    source_name = "fred"

    def __init__(self, session: Any = None, api_key: str = "", base_url: str = "https://api.stlouisfed.org/fred"):
        super().__init__(session=session)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    async def fetch_series(self, series_id: str) -> ConnectorResponse:
        if not self.api_key:
            raise ConnectorUnavailable("FRED_API_KEY is not configured")
        payload = await self._get_json(
            f"{self.base_url}/series/observations",
            {"series_id": series_id, "api_key": self.api_key, "file_type": "json"},
        )
        return ConnectorResponse(self.source_name, time.time(), payload)


class BLSSeriesConnector(HTTPConnector):
    source_name = "bls"

    def __init__(self, session: Any = None, api_key: str = "", base_url: str = "https://api.bls.gov/publicAPI/v2/timeseries/data"):
        super().__init__(session=session)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    async def fetch_series(self, series_id: str, start_year: int, end_year: int) -> ConnectorResponse:
        if self.session is None:
            raise ConnectorUnavailable("BLS session is not initialized")
        payload = {
            "seriesid": [series_id],
            "startyear": str(start_year),
            "endyear": str(end_year),
        }
        if self.api_key:
            payload["registrationkey"] = self.api_key
        async with self.session.post(self.base_url, json=payload, timeout=self.timeout_seconds) as resp:
            if resp.status >= 400:
                raise ConnectorUnavailable(f"BLS returned HTTP {resp.status}")
            raw = await resp.json()
        return ConnectorResponse(self.source_name, time.time(), raw)


class BEAConnector(HTTPConnector):
    source_name = "bea"

    def __init__(self, session: Any = None, api_key: str = "", base_url: str = "https://apps.bea.gov/api/data"):
        super().__init__(session=session)
        self.api_key = api_key
        self.base_url = base_url

    async def fetch_nipa_table(
        self,
        table_name: str,
        line_number: str,
        frequency: str = "Q",
        year: str = "X",
    ) -> ConnectorResponse:
        if not self.api_key:
            raise ConnectorUnavailable("BEA_API_KEY is not configured")
        payload = await self._get_json(
            self.base_url,
            {
                "UserID": self.api_key,
                "method": "GetData",
                "datasetname": "NIPA",
                "TableName": table_name,
                "LineNumber": line_number,
                "Frequency": frequency,
                "Year": year,
                "ResultFormat": "JSON",
            },
        )
        return ConnectorResponse(self.source_name, time.time(), payload)


def _parse_date(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    from datetime import datetime, timezone

    try:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def _parse_gdelt_ts(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    from datetime import datetime, timezone

    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    return None
