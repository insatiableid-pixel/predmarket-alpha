"""Authenticated Kalshi REST V2 trading client.

This module is intentionally small and transport-injectable.  Production uses
``urllib`` from the standard library; tests pass a fake requester so no network
or credentials are needed.
"""

from __future__ import annotations

import base64
import json
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from predmarket.config import Config
from predmarket.resilience import TokenBucket

JsonPayload = dict[str, Any]
Requester = Callable[[str, str, Mapping[str, str], bytes | None, float], tuple[int, JsonPayload]]


class KalshiAPIError(RuntimeError):
    """Raised when the Kalshi API returns an HTTP error or malformed response."""

    def __init__(self, status_code: int, message: str, payload: Mapping[str, Any] | None = None):
        super().__init__(f"Kalshi API error {status_code}: {message}")
        self.status_code = int(status_code)
        self.payload = dict(payload or {})


class KalshiAuthError(KalshiAPIError):
    """Raised when Kalshi authentication fails (key loading, signing, or credentials).

    The message is actionable, indicating whether the issue is a missing file,
    invalid PEM, non-RSA key, or signing failure.
    """

    def __init__(self, message: str, *, detail: str = ""):
        super().__init__(status_code=0, message=message)
        self.detail = detail


@dataclass(frozen=True, slots=True)
class KalshiTradingClientConfig:
    base_url: str
    api_key: str
    private_key_pem_or_path: str
    timeout_seconds: float = 10.0

    @property
    def api_prefix(self) -> str:
        parsed = urlparse(self.base_url)
        return parsed.path.rstrip("/")


class KalshiTradingClient:
    """Minimal current Kalshi V2 client for event-contract order automation."""

    def __init__(
        self,
        config: KalshiTradingClientConfig,
        *,
        requester: Requester | None = None,
        clock_ms: Callable[[], int] | None = None,
        public_bucket: TokenBucket | None = None,
        auth_bucket: TokenBucket | None = None,
    ):
        self.config = config
        self.requester = requester or default_requester
        self.clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self._private_key = load_private_key(config.private_key_pem_or_path)
        # Rate-limiting buckets: public 30 req/s, auth 10 req/s by default.
        self._public_bucket = public_bucket or TokenBucket(rate=30.0, burst=60.0, name="public")
        self._auth_bucket = auth_bucket or TokenBucket(rate=10.0, burst=20.0, name="auth")

    def auth_headers(self, method: str, endpoint_path: str) -> dict[str, str]:
        timestamp = str(self.clock_ms())
        message = signing_message(
            timestamp=timestamp,
            method=method,
            api_prefix=self.config.api_prefix,
            endpoint_path=endpoint_path,
        )
        return {
            "KALSHI-ACCESS-KEY": self.config.api_key,
            "KALSHI-ACCESS-SIGNATURE": sign_pss_text(self._private_key, message),
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
        }

    def get_balance(self) -> JsonPayload:
        return self._request("GET", "/portfolio/balance")

    def get_positions(self, *, cursor: str | None = None) -> JsonPayload:
        return self._request("GET", "/portfolio/positions", params={"cursor": cursor})

    def list_orders(
        self,
        *,
        status: str | None = None,
        ticker: str | None = None,
        cursor: str | None = None,
    ) -> JsonPayload:
        return self._request(
            "GET",
            "/portfolio/orders",
            params={"status": status, "ticker": ticker, "cursor": cursor},
        )

    def get_order(self, order_id: str) -> JsonPayload:
        return self._request("GET", f"/portfolio/orders/{order_id}")

    def cancel_order(self, order_id: str) -> JsonPayload:
        return self._request("DELETE", f"/portfolio/events/orders/{order_id}")

    def get_market(self, ticker: str) -> JsonPayload:
        return self._request("GET", f"/markets/{ticker}", auth=False)

    def get_orderbook(self, ticker: str, *, depth: int = 10) -> JsonPayload:
        return self._request(
            "GET",
            f"/markets/{ticker}/orderbook",
            params={"depth": int(depth)},
            auth=False,
        )

    def get_endpoint_costs(self) -> JsonPayload:
        return self._request("GET", "/account/endpoint_costs", auth=False)

    def create_order(
        self,
        *,
        ticker: str,
        outcome_side: str,
        count: float,
        price: float,
        client_order_id: str,
        time_in_force: str = "good_till_canceled",
        post_only: bool = True,
        expiration_time: int | None = None,
    ) -> JsonPayload:
        payload = build_create_order_payload(
            ticker=ticker,
            outcome_side=outcome_side,
            count=count,
            price=price,
            client_order_id=client_order_id,
            time_in_force=time_in_force,
            post_only=post_only,
            expiration_time=expiration_time,
        )
        return self._request("POST", "/portfolio/events/orders", json_body=payload)

    def _request(
        self,
        method: str,
        endpoint_path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Mapping[str, Any] | None = None,
        auth: bool = True,
    ) -> JsonPayload:
        # Rate-limit: consume a token before making the request.
        bucket = self._auth_bucket if auth else self._public_bucket
        bucket.consume_sync(1.0, wait=True)

        path = with_query(endpoint_path, params)
        url = f"{self.config.base_url.rstrip('/')}{path}"
        body = None if json_body is None else json.dumps(json_body).encode("utf-8")
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if auth:
            headers.update(self.auth_headers(method, endpoint_path))
        status, payload = self.requester(method, url, headers, body, self.config.timeout_seconds)
        if status >= 400:
            raise KalshiAPIError(status, str(payload.get("error") or payload), payload)
        return payload


def trading_client_config_from_app_config(
    config: Config, *, execution_mode: str
) -> KalshiTradingClientConfig:
    mode = execution_mode.strip().lower()
    kalshi = config.venues.kalshi
    base_url = kalshi.demo_api_url if mode == "demo" else kalshi.api_url
    return KalshiTradingClientConfig(
        base_url=base_url,
        api_key=kalshi.api_key,
        private_key_pem_or_path=kalshi.api_secret,
    )


def build_create_order_payload(
    *,
    ticker: str,
    outcome_side: str,
    count: float,
    price: float,
    client_order_id: str,
    time_in_force: str = "good_till_canceled",
    post_only: bool = True,
    expiration_time: int | None = None,
) -> JsonPayload:
    side = book_side_for_outcome(outcome_side)
    book_price = book_price_for_outcome(outcome_side, price)
    if count <= 0:
        raise ValueError("count must be positive")
    if not (0.0 < price < 1.0):
        raise ValueError("price must be a probability in (0, 1)")
    if expiration_time is not None and time_in_force == "immediate_or_cancel":
        raise ValueError("immediate_or_cancel cannot include expiration_time")
    payload = {
        "ticker": ticker,
        "client_order_id": client_order_id,
        "side": side,
        "count": f"{count:.2f}",
        "price": f"{book_price:.4f}",
        "time_in_force": time_in_force,
        "self_trade_prevention_type": "maker" if post_only else "taker_at_cross",
        "post_only": bool(post_only),
        "cancel_order_on_pause": True,
        "reduce_only": False,
        "subaccount": 0,
        "exchange_index": 0,
    }
    if expiration_time is not None:
        payload["expiration_time"] = int(expiration_time)
    return payload


def book_side_for_outcome(outcome_side: str) -> str:
    normalized = outcome_side.strip().lower()
    if normalized == "yes":
        return "bid"
    if normalized == "no":
        return "ask"
    raise ValueError(f"unsupported outcome side: {outcome_side!r}")


def book_price_for_outcome(outcome_side: str, outcome_price: float) -> float:
    normalized = outcome_side.strip().lower()
    if normalized == "yes":
        return float(outcome_price)
    if normalized == "no":
        return round(1.0 - float(outcome_price), 10)
    raise ValueError(f"unsupported outcome side: {outcome_side!r}")


def stable_client_order_id(*parts: object) -> str:
    key = "|".join(str(part) for part in parts)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"predmarket-alpha:kalshi-live:{key}"))


def signing_message(
    *,
    timestamp: str,
    method: str,
    api_prefix: str,
    endpoint_path: str,
) -> str:
    endpoint_no_query = endpoint_path.split("?", maxsplit=1)[0]
    path = f"{api_prefix.rstrip('/')}/{endpoint_no_query.lstrip('/')}"
    return f"{timestamp}{method.upper()}{path}"


def sign_pss_text(private_key: rsa.RSAPrivateKey, text: str) -> str:
    signature = private_key.sign(
        text.encode("utf-8"),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def load_private_key(value: str) -> rsa.RSAPrivateKey:
    text = value.strip()
    if not text:
        raise KalshiAuthError(
            "Kalshi private key is required: set venues.kalshi.api_secret, "
            "KALSHI_PRIVATE_KEY_PATH, KALSHI_PRIVATE_KEY_PEM, or legacy KALSHI_API_SECRET"
        )

    path: Path | None = None
    path_is_file = False
    if "-----BEGIN " in text and "PRIVATE KEY-----" in text:
        raw = text.encode("utf-8")
    else:
        try:
            path = Path(text).expanduser()
            path_is_file = path.is_file()
        except OSError as exc:
            raise KalshiAuthError(
                "Kalshi private key value is not a readable file path or valid PEM text",
                detail=str(exc),
            ) from exc
        if path_is_file:
            try:
                raw = path.read_bytes()
            except OSError as exc:
                raise KalshiAuthError(
                    f"Kalshi private key file exists at {path} but could not be read: {exc}",
                    detail=str(exc),
                ) from exc
        else:
            raw = text.encode("utf-8")

    try:
        private_key = serialization.load_pem_private_key(raw, password=None)
    except ValueError as exc:
        if path_is_file:
            raise KalshiAuthError(
                f"Kalshi private key file at {path} exists but is not valid PEM",
                detail=str(exc),
            ) from exc
        raise KalshiAuthError(
            "Kalshi private key value is not valid PEM. "
            "If using an env variable, ensure it contains the full PEM including "
            "-----BEGIN RSA PRIVATE KEY----- header and footer.",
            detail=str(exc),
        ) from exc
    except TypeError as exc:
        if path_is_file:
            raise KalshiAuthError(
                f"Kalshi private key file at {path} exists but could not be deserialized",
                detail=str(exc),
            ) from exc
        raise KalshiAuthError(
            "Kalshi private key could not be deserialized from the provided value",
            detail=str(exc),
        ) from exc
    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise KalshiAuthError(
            "Kalshi private key exists and is valid PEM but is not an RSA key. "
            "Generate an RSA key pair in the Kalshi dashboard and use the downloaded private key."
        )
    return private_key


def with_query(endpoint_path: str, params: Mapping[str, Any] | None) -> str:
    clean_params = {key: value for key, value in (params or {}).items() if value is not None}
    if not clean_params:
        return endpoint_path
    return f"{endpoint_path}?{urlencode(clean_params)}"


def default_requester(
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: bytes | None,
    timeout_seconds: float,
) -> tuple[int, JsonPayload]:
    request = Request(url, data=body, headers=dict(headers), method=method.upper())
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return int(response.status), decode_json_bytes(response.read())
    except HTTPError as exc:
        return int(exc.code), decode_json_bytes(exc.read())


def decode_json_bytes(raw: bytes) -> JsonPayload:
    if not raw:
        return {}
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"raw": raw.decode("utf-8", errors="replace")}
    return decoded if isinstance(decoded, dict) else {"payload": decoded}
