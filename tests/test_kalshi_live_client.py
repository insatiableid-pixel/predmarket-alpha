from __future__ import annotations

import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from predmarket.kalshi_live_client import (
    KalshiTradingClient,
    KalshiTradingClientConfig,
    book_price_for_outcome,
    book_side_for_outcome,
    build_create_order_payload,
    signing_message,
    stable_client_order_id,
)


def private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def test_signing_message_uses_trade_api_path_without_query() -> None:
    message = signing_message(
        timestamp="123",
        method="get",
        api_prefix="/trade-api/v2",
        endpoint_path="/portfolio/orders?limit=5",
    )

    assert message == "123GET/trade-api/v2/portfolio/orders"


def test_create_order_payload_maps_outcome_to_v2_book_side() -> None:
    yes = build_create_order_payload(
        ticker="KXUNIT",
        outcome_side="yes",
        count=2,
        price=0.56,
        client_order_id="cid",
    )
    no = build_create_order_payload(
        ticker="KXUNIT",
        outcome_side="no",
        count=2,
        price=0.44,
        client_order_id="cid",
    )

    assert yes["side"] == "bid"
    assert no["side"] == "ask"
    assert no["count"] == "2.00"
    assert no["price"] == "0.5600"
    assert no["time_in_force"] == "good_till_canceled"
    assert no["post_only"] is True
    assert no["self_trade_prevention_type"] == "maker"
    assert book_side_for_outcome("yes") == "bid"
    assert book_price_for_outcome("yes", 0.44) == 0.44
    assert book_price_for_outcome("no", 0.44) == 0.56


def test_create_order_payload_can_explicitly_cross_as_ioc_taker() -> None:
    payload = build_create_order_payload(
        ticker="KXUNIT",
        outcome_side="yes",
        count=2,
        price=0.56,
        client_order_id="cid",
        time_in_force="immediate_or_cancel",
        post_only=False,
    )

    assert payload["time_in_force"] == "immediate_or_cancel"
    assert payload["post_only"] is False
    assert payload["self_trade_prevention_type"] == "taker_at_cross"


def test_create_order_payload_rejects_ioc_expiration() -> None:
    with pytest.raises(ValueError, match="immediate_or_cancel cannot include expiration_time"):
        build_create_order_payload(
            ticker="KXUNIT",
            outcome_side="yes",
            count=2,
            price=0.56,
            client_order_id="cid",
            time_in_force="immediate_or_cancel",
            post_only=False,
            expiration_time=1_783_100_000,
        )


def test_client_create_order_uses_event_order_v2_shape() -> None:
    calls = []

    def requester(method, url, headers, body, timeout):
        calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "body": json.loads((body or b"{}").decode("utf-8")),
                "timeout": timeout,
            }
        )
        return 201, {"order_id": "order-1", "fill_count": "0.00", "remaining_count": "1.00"}

    client = KalshiTradingClient(
        KalshiTradingClientConfig(
            base_url="https://external-api.demo.kalshi.co/trade-api/v2",
            api_key="key-id",
            private_key_pem_or_path=private_key_pem(),
        ),
        requester=requester,
        clock_ms=lambda: 123456789,
    )
    client.create_order(
        ticker="KXUNIT",
        outcome_side="no",
        count=1,
        price=0.42,
        client_order_id=stable_client_order_id("unit"),
    )

    call = calls[0]
    assert call["method"] == "POST"
    assert call["url"].endswith("/trade-api/v2/portfolio/events/orders")
    assert call["headers"]["KALSHI-ACCESS-KEY"] == "key-id"
    assert call["headers"]["KALSHI-ACCESS-TIMESTAMP"] == "123456789"
    assert call["body"]["side"] == "ask"
    assert call["body"]["price"] == "0.5800"
    assert call["body"]["time_in_force"] == "good_till_canceled"
    assert call["body"]["post_only"] is True
    assert call["body"]["self_trade_prevention_type"] == "maker"
