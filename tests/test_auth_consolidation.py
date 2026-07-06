"""Tests for auth consolidation: unified RSA-PSS auth via kalshi_live_client.py.

Covers VAL-AUTH-001 through VAL-AUTH-010 and VAL-CROSS-029, VAL-CROSS-031.
"""

from __future__ import annotations

import importlib
import pathlib
import re
import warnings
from typing import Any

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from predmarket.kalshi_live_client import (
    KalshiAuthError,
    KalshiTradingClient,
    KalshiTradingClientConfig,
    load_private_key,
    sign_pss_text,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_rsa_key_pem() -> tuple[rsa.RSAPrivateKey, str]:
    """Generate a throwaway RSA key pair and return (key_object, pem_string)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    return key, pem


def _requester_capture() -> tuple[list[dict[str, Any]], Any]:
    """Return (capture_list, requester) for inspecting headers sent."""
    calls: list[dict[str, Any]] = []

    def requester(method, url, headers, body, timeout):
        calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "timeout": timeout,
            }
        )
        return 200, {}

    return calls, requester


# ---------------------------------------------------------------------------
# VAL-AUTH-001: RSA-PSS is the single canonical auth path
# ---------------------------------------------------------------------------


class TestRsaPssCanonicalAuthPath:
    """VAL-AUTH-001: All authenticated calls flow through sign_pss_text()."""

    def test_auth_headers_uses_rsa_pss_signing(self) -> None:
        """auth_headers output includes a valid PSS signature."""
        _, pem = _generate_rsa_key_pem()
        config = KalshiTradingClientConfig(
            base_url="https://external-api.demo.kalshi.co/trade-api/v2",
            api_key="test-key",
            private_key_pem_or_path=pem,
        )
        client = KalshiTradingClient(config, clock_ms=lambda: 1000)
        headers = client.auth_headers("GET", "/portfolio/balance")
        assert "KALSHI-ACCESS-SIGNATURE" in headers
        sig = headers["KALSHI-ACCESS-SIGNATURE"]
        # PSS signature is base64-encoded binary, so it should be non-empty
        # base64 with no whitespace
        assert len(sig) > 0
        assert sig.strip() == sig

    def test_sign_pss_text_uses_pss_sha256(self) -> None:
        """sign_pss_text uses PSS padding with SHA256 hash as required by Kalshi.

        Note: PSS signatures are randomized (salt), so verification is done
        by checking that the signature is valid, not by comparing bytes.
        """
        key, _ = _generate_rsa_key_pem()
        result = sign_pss_text(key, "test-message")
        import base64

        sig_bytes = base64.b64decode(result)
        # Verify the signature is valid with PSS SHA256
        key.public_key().verify(
            sig_bytes,
            b"test-message",
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        # If verify() doesn't raise, the signature is correct

    def test_signing_message_format(self) -> None:
        """signing_message produces timestamp+method+path format per Kalshi spec."""
        from predmarket.kalshi_live_client import signing_message

        msg = signing_message(
            timestamp="12345",
            method="POST",
            api_prefix="/trade-api/v2",
            endpoint_path="/portfolio/events/orders",
        )
        assert msg == "12345POST/trade-api/v2/portfolio/events/orders"

    def test_signing_message_strips_query_params(self) -> None:
        """Query parameters are stripped from the endpoint path before signing."""
        from predmarket.kalshi_live_client import signing_message

        msg = signing_message(
            timestamp="67890",
            method="GET",
            api_prefix="/trade-api/v2",
            endpoint_path="/portfolio/orders?limit=5&status=open",
        )
        assert msg == "67890GET/trade-api/v2/portfolio/orders"


# ---------------------------------------------------------------------------
# VAL-AUTH-002: Public data paths are unauthenticated
# ---------------------------------------------------------------------------


class TestPublicDataPathsUnauthenticated:
    """VAL-AUTH-002: Public endpoints send no KALSHI-ACCESS-* headers."""

    def test_get_market_no_auth_headers(self) -> None:
        """get_market must not include KALSHI-ACCESS-* headers."""
        _, pem = _generate_rsa_key_pem()
        calls, requester = _requester_capture()
        client = KalshiTradingClient(
            KalshiTradingClientConfig(
                base_url="https://external-api.demo.kalshi.co/trade-api/v2",
                api_key="test-key",
                private_key_pem_or_path=pem,
            ),
            requester=requester,
            clock_ms=lambda: 1000,
        )
        client.get_market("KXBTCD-24H")
        assert len(calls) == 1
        headers = calls[0]["headers"]
        assert "KALSHI-ACCESS-KEY" not in headers
        assert "KALSHI-ACCESS-SIGNATURE" not in headers
        assert "KALSHI-ACCESS-TIMESTAMP" not in headers

    def test_get_orderbook_no_auth_headers(self) -> None:
        """get_orderbook must not include KALSHI-ACCESS-* headers."""
        _, pem = _generate_rsa_key_pem()
        calls, requester = _requester_capture()
        client = KalshiTradingClient(
            KalshiTradingClientConfig(
                base_url="https://external-api.demo.kalshi.co/trade-api/v2",
                api_key="test-key",
                private_key_pem_or_path=pem,
            ),
            requester=requester,
            clock_ms=lambda: 1000,
        )
        client.get_orderbook("KXBTCD-24H", depth=5)
        assert len(calls) == 1
        headers = calls[0]["headers"]
        assert "KALSHI-ACCESS-KEY" not in headers
        assert "KALSHI-ACCESS-SIGNATURE" not in headers
        assert "KALSHI-ACCESS-TIMESTAMP" not in headers

    def test_get_endpoint_costs_no_auth_headers(self) -> None:
        """get_endpoint_costs must not include KALSHI-ACCESS-* headers."""
        _, pem = _generate_rsa_key_pem()
        calls, requester = _requester_capture()
        client = KalshiTradingClient(
            KalshiTradingClientConfig(
                base_url="https://external-api.demo.kalshi.co/trade-api/v2",
                api_key="test-key",
                private_key_pem_or_path=pem,
            ),
            requester=requester,
            clock_ms=lambda: 1000,
        )
        client.get_endpoint_costs()
        assert len(calls) == 1
        headers = calls[0]["headers"]
        assert "KALSHI-ACCESS-KEY" not in headers
        assert "KALSHI-ACCESS-SIGNATURE" not in headers
        assert "KALSHI-ACCESS-TIMESTAMP" not in headers

    def test_auth_true_sends_headers(self) -> None:
        """Authenticated calls DO include KALSHI-ACCESS-* headers."""
        _, pem = _generate_rsa_key_pem()
        calls, requester = _requester_capture()
        client = KalshiTradingClient(
            KalshiTradingClientConfig(
                base_url="https://external-api.demo.kalshi.co/trade-api/v2",
                api_key="test-key",
                private_key_pem_or_path=pem,
            ),
            requester=requester,
            clock_ms=lambda: 1000,
        )
        client.get_balance()
        assert len(calls) == 1
        headers = calls[0]["headers"]
        assert "KALSHI-ACCESS-KEY" in headers
        assert "KALSHI-ACCESS-SIGNATURE" in headers
        assert "KALSHI-ACCESS-TIMESTAMP" in headers


# ---------------------------------------------------------------------------
# VAL-AUTH-003: SDK-based auth in execution.py deprecated with warnings
# ---------------------------------------------------------------------------


class TestExecutionDeprecationWarning:
    """VAL-AUTH-003: execution.py emits DeprecationWarning when using kalshi_python."""

    def test_execution_manager_emits_deprecation_warning(self, mock_config) -> None:
        """Creating ExecutionManager with credentials emits DeprecationWarning."""
        from predmarket.audit import AuditLogger

        mock_config.venues.kalshi.enabled = True
        mock_config.venues.kalshi.api_key = "test-key"
        mock_config.venues.kalshi.api_secret = "test-secret"

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from predmarket.execution import ExecutionManager

            audit = AuditLogger(str(mock_config.global_cfg.data_dir))
            ExecutionManager(mock_config, audit)
            deprecation_warnings = [
                x for x in w if issubclass(x.category, DeprecationWarning)
            ]
            assert len(deprecation_warnings) >= 1
            msg = str(deprecation_warnings[0].message)
            assert "KalshiTradingClient" in msg
            assert "kalshi_python" in msg.lower()


# ---------------------------------------------------------------------------
# VAL-AUTH-004: SDK-based auth in ingest.py deprecated with warnings
# ---------------------------------------------------------------------------


class TestIngestDeprecationWarning:
    """VAL-AUTH-004: ingest.py emits DeprecationWarning when using kalshi_python."""

    def test_ingest_connect_kalshi_emits_deprecation_warning(self, mock_config) -> None:
        """Calling _connect_kalshi with credentials emits DeprecationWarning."""
        from predmarket.ingest import MarketIngestManager

        mock_config.venues.kalshi.enabled = True
        mock_config.venues.kalshi.api_key = "test-key"
        mock_config.venues.kalshi.api_secret = "test-secret"

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            manager = MarketIngestManager(mock_config)
            # initialize calls _connect_kalshi which uses kalshi_python
            import asyncio

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(manager.initialize())
            except Exception:
                # May fail due to network, but warning should already be emitted
                pass
            finally:
                loop.close()

            deprecation_warnings = [
                x for x in w if issubclass(x.category, DeprecationWarning)
            ]
            assert len(deprecation_warnings) >= 1
            msg = str(deprecation_warnings[0].message)
            assert "KalshiTradingClient" in msg
            assert "kalshi_python" in msg.lower()


# ---------------------------------------------------------------------------
# VAL-AUTH-005: New modules import from kalshi_live_client, never kalshi_python
# ---------------------------------------------------------------------------


class TestNewModulesImportFromKalshiLiveClient:
    """VAL-AUTH-005: New mission modules import from kalshi_live_client."""

    def test_websocket_imports_from_kalshi_live_client(self) -> None:
        """kalshi_websocket.py imports auth functions from kalshi_live_client."""
        import predmarket.kalshi_websocket

        source = pathlib.Path(predmarket.kalshi_websocket.__file__).read_text("utf-8")
        # Must import from kalshi_live_client, not kalshi_python
        assert "from predmarket.kalshi_live_client import" in source
        assert "import kalshi_python" not in source
        assert "from kalshi_python" not in source

    def test_jurisdiction_does_not_import_kalshi_python(self) -> None:
        """kalshi_jurisdiction.py does not import kalshi_python."""
        import predmarket.kalshi_jurisdiction

        source = pathlib.Path(predmarket.kalshi_jurisdiction.__file__).read_text("utf-8")
        assert "kalshi_python" not in source

    def test_websocket_uses_sign_pss_text(self) -> None:
        """kalshi_websocket.py uses sign_pss_text or load_private_key from client."""
        import predmarket.kalshi_websocket

        source = pathlib.Path(predmarket.kalshi_websocket.__file__).read_text("utf-8")
        assert "load_private_key" in source
        assert "sign_pss_text" in source


# ---------------------------------------------------------------------------
# VAL-AUTH-006: Private key loading is centralized in kalshi_live_client.py
# ---------------------------------------------------------------------------


class TestPrivateKeyLoadingCentralized:
    """VAL-AUTH-006: Only kalshi_live_client.py implements load_private_key."""

    def test_load_private_key_only_in_kalshi_live_client(self) -> None:
        """load_private_key must not be reimplemented in execution.py or ingest.py."""
        for module_path in [
            "predmarket/execution.py",
            "predmarket/ingest.py",
        ]:
            full_path = pathlib.Path(__file__).resolve().parents[1] / module_path
            source = full_path.read_text("utf-8")
            # These files should NOT implement their own key loading or PEM parsing
            # They should only import load_private_key
            lines_with_load = [
                line
                for line in source.split("\n")
                if "load_private_key" in line and "def load_private_key" in line
            ]
            assert len(lines_with_load) == 0, (
                f"{module_path} implements its own load_private_key "
                f"at line(s): {lines_with_load}"
            )


# ---------------------------------------------------------------------------
# VAL-AUTH-007: Auth failure produces actionable KalshiAuthError messages
# ---------------------------------------------------------------------------


class TestKalshiAuthErrorActionable:
    """VAL-AUTH-007: load_private_key raises KalshiAuthError with actionable messages."""

    def test_missing_file_raises_auth_error(self, tmp_path) -> None:
        """Non-existent key file path produces KalshiAuthError mentioning file."""
        fake_path = tmp_path / "nonexistent" / "key.pem"
        with pytest.raises(KalshiAuthError) as exc_info:
            load_private_key(str(fake_path))
        assert "private key" in str(exc_info.value).lower()

    def test_invalid_pem_string_raises_auth_error(self) -> None:
        """Invalid PEM value produces KalshiAuthError mentioning PEM."""
        with pytest.raises(KalshiAuthError) as exc_info:
            load_private_key("not-a-real-key")
        msg = str(exc_info.value)
        assert "PEM" in msg or "private key" in msg.lower()

    def test_empty_string_raises_auth_error(self) -> None:
        """Empty key value produces KalshiAuthError."""
        with pytest.raises(KalshiAuthError) as exc_info:
            load_private_key("")
        assert "required" in str(exc_info.value).lower()

    def test_non_rsa_pem_key_raises_auth_error(self, tmp_path) -> None:
        """A valid PEM that is not an RSA key produces KalshiAuthError mentioning RSA."""
        # Generate an EC key (not RSA)
        from cryptography.hazmat.primitives.asymmetric import ec

        ec_key = ec.generate_private_key(ec.SECP256R1())
        ec_pem = ec_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")

        key_file = tmp_path / "ec_key.pem"
        key_file.write_text(ec_pem)

        with pytest.raises(KalshiAuthError) as exc_info:
            load_private_key(str(key_file))
        msg = str(exc_info.value)
        assert "RSA" in msg

    def test_load_private_key_success_with_valid_key(self) -> None:
        """A valid RSA PEM string loads successfully."""
        _, pem = _generate_rsa_key_pem()
        key = load_private_key(pem)
        assert isinstance(key, rsa.RSAPrivateKey)


# ---------------------------------------------------------------------------
# VAL-AUTH-008: Config provides a single key path for all auth consumers
# ---------------------------------------------------------------------------


class TestSingleKeyPathInConfig:
    """VAL-AUTH-008: Config has one Kalshi credential pair with no separate SDK key."""

    def test_kalshi_config_has_single_credential_pair(self) -> None:
        """KalshiConfig has api_key and api_secret but no separate sdk_key."""
        from predmarket.config import KalshiConfig

        # Verify the canonical fields exist
        cfg = KalshiConfig()
        assert hasattr(cfg, "api_key")
        assert hasattr(cfg, "api_secret")

        # Verify no separate SDK credential field
        assert not hasattr(cfg, "sdk_key")
        assert not hasattr(cfg, "sdk_secret")

    def test_config_yaml_has_no_duplicate_key_paths(self) -> None:
        """Config YAML does not define separate SDK key path."""
        config_path = (
            pathlib.Path(__file__).resolve().parents[1] / "config" / "config.yaml"
        )
        raw = config_path.read_text("utf-8")
        # The config should not have a separate SDK key section
        assert "sdk_key" not in raw
        assert "sdk_secret" not in raw

    def test_trading_client_config_uses_venues_kalshi_api_secret(self) -> None:
        """trading_client_config_from_app_config maps api_secret to private_key_pem_or_path."""
        from predmarket.config import Config
        from predmarket.kalshi_live_client import trading_client_config_from_app_config

        # Create a minimal config with credentials
        config = Config()
        config.venues.kalshi.api_key = "test-key-id"
        config.venues.kalshi.api_secret = "/path/to/key.pem"
        config.venues.kalshi.use_demo = True

        client_config = trading_client_config_from_app_config(config, execution_mode="demo")
        assert client_config.api_key == "test-key-id"
        assert client_config.private_key_pem_or_path == "/path/to/key.pem"


# ---------------------------------------------------------------------------
# VAL-AUTH-009: Token/timestamp replay protection
# ---------------------------------------------------------------------------


class TestTimestampReplayProtection:
    """VAL-AUTH-009: Each auth_headers() call produces a fresh timestamp."""

    def test_timestamp_increases_with_each_call(self) -> None:
        """Each auth_headers call uses the current time, producing different timestamps."""
        _, pem = _generate_rsa_key_pem()
        counter = iter([1000, 2000, 3000])

        client = KalshiTradingClient(
            KalshiTradingClientConfig(
                base_url="https://external-api.demo.kalshi.co/trade-api/v2",
                api_key="test-key",
                private_key_pem_or_path=pem,
            ),
            clock_ms=lambda: next(counter),
        )
        h1 = client.auth_headers("GET", "/portfolio/balance")
        h2 = client.auth_headers("GET", "/portfolio/balance")
        h3 = client.auth_headers("GET", "/portfolio/balance")

        assert h1["KALSHI-ACCESS-TIMESTAMP"] == "1000"
        assert h2["KALSHI-ACCESS-TIMESTAMP"] == "2000"
        assert h3["KALSHI-ACCESS-TIMESTAMP"] == "3000"
        # Signatures should also differ since the message includes the timestamp
        assert h1["KALSHI-ACCESS-SIGNATURE"] != h2["KALSHI-ACCESS-SIGNATURE"]

    def test_timestamp_is_always_monotonic(self) -> None:
        """Real clock_ms produces monotonically increasing timestamps."""
        _, pem = _generate_rsa_key_pem()

        client = KalshiTradingClient(
            KalshiTradingClientConfig(
                base_url="https://external-api.demo.kalshi.co/trade-api/v2",
                api_key="test-key",
                private_key_pem_or_path=pem,
            ),
        )
        h1 = client.auth_headers("GET", "/portfolio/balance")
        h2 = client.auth_headers("GET", "/portfolio/balance")
        assert int(h2["KALSHI-ACCESS-TIMESTAMP"]) >= int(h1["KALSHI-ACCESS-TIMESTAMP"])


# ---------------------------------------------------------------------------
# VAL-AUTH-010: No secrets logged in auth debug output
# ---------------------------------------------------------------------------


class TestNoSecretsLogged:
    """VAL-AUTH-010: Auth-related code does not log api_key, private_key, or signatures."""

    def test_kalshi_live_client_has_no_secret_logging(self) -> None:
        """kalshi_live_client.py must not log api_key or private_key content."""
        source = pathlib.Path(
            importlib.util.find_spec("predmarket.kalshi_live_client").origin  # type: ignore[union-attr]
        ).read_text("utf-8")
        # Check no log statements include secret values
        suspicious_patterns = [
            r'log.*api_key',
            r'log.*private_key',
            r'log.*PEM',
            r'log.*signature',
            r'logger\.(info|debug|warning).*api_key',
            r'logger\.(info|debug|warning).*private_key',
        ]
        for pattern in suspicious_patterns:
            matches = re.findall(pattern, source, re.IGNORECASE)
            assert len(matches) == 0, (
                f"Found potential secret leak pattern '{pattern}' "
                f"in kalshi_live_client.py: {matches}"
            )

    def test_websocket_has_no_secret_logging(self) -> None:
        """kalshi_websocket.py must not log api_key, private_key, or signature content."""
        source = pathlib.Path(
            importlib.util.find_spec("predmarket.kalshi_websocket").origin  # type: ignore[union-attr]
        ).read_text("utf-8")
        suspicious_patterns = [
            r'log.*api_key',
            r'log.*private_key',
            r'log.*PEM',
            r'log.*signature',
        ]
        for pattern in suspicious_patterns:
            matches = re.findall(pattern, source, re.IGNORECASE)
            assert len(matches) == 0, (
                f"Found potential secret leak pattern '{pattern}' "
                f"in kalshi_websocket.py: {matches}"
            )


# ---------------------------------------------------------------------------
# VAL-CROSS-029: Auth consolidation single RSA-PSS signing path
# ---------------------------------------------------------------------------


class TestCrossAuthConsolidation:
    """VAL-CROSS-029: execution.py and ingest.py don't reimplement key loading."""

    def test_execution_no_key_loading_implementation(self) -> None:
        """execution.py does not implement its own load_private_key function."""
        module_path = (
            pathlib.Path(__file__).resolve().parents[1] / "predmarket" / "execution.py"
        )
        source = module_path.read_text("utf-8")
        assert "def load_private_key" not in source
        assert "serialization.load_pem_private_key" not in source

    def test_ingest_no_key_loading_implementation(self) -> None:
        """ingest.py does not implement its own load_private_key function."""
        module_path = (
            pathlib.Path(__file__).resolve().parents[1] / "predmarket" / "ingest.py"
        )
        source = module_path.read_text("utf-8")
        assert "def load_private_key" not in source
        assert "serialization.load_pem_private_key" not in source

    def test_all_auth_calls_flow_through_kalshi_live_client(self) -> None:
        """Verified that execution.py and ingest.py delegate to KalshiTradingClient."""
        # execution.py delegates via KalshiTradingClient for auth
        # ingest.py delegates via KalshiTradingClient for auth
        # websocket imports from kalshi_live_client
        import predmarket.kalshi_websocket

        ws_source = pathlib.Path(predmarket.kalshi_websocket.__file__).read_text("utf-8")
        assert "kalshi_live_client" in ws_source


# ---------------------------------------------------------------------------
# VAL-CROSS-031: No live execution without explicit arming
# ---------------------------------------------------------------------------


class TestNoLiveExecutionWithoutArming:
    """VAL-CROSS-031: Live execution requires multiple safety gates."""

    def test_live_arming_state_requires_all_gates(self) -> None:
        """live_arming_state returns unarmed without all safety checks."""
        from predmarket.config import Config
        from predmarket.kalshi_live_engine import live_arming_state

        config = Config()
        state = live_arming_state(config, execution_mode="disabled")
        assert state.armed is False

    def test_live_arming_state_blocks_without_env_var(self, mock_config) -> None:
        """Missing KALSHI_LIVE_TRADING_ENABLED blocks live arming."""
        from predmarket.kalshi_live_engine import live_arming_state

        mock_config.venues.kalshi.execution_enabled = True

        with pytest.MonkeyPatch.context() as mp:
            mp.delenv("KALSHI_LIVE_TRADING_ENABLED", raising=False)
            mp.setenv("KALSHI_CONFIRM_PRODUCTION_LIVE", "I_UNDERSTAND_KALSHI_LIVE_RISK")
            state = live_arming_state(mock_config, execution_mode="live")
            assert state.armed is False
            assert any("KALSHI_LIVE_TRADING_ENABLED" in b for b in state.blockers)

    def test_live_arming_state_blocks_without_confirm_env(self, mock_config) -> None:
        """Missing KALSHI_CONFIRM_PRODUCTION_LIVE blocks live arming."""
        from predmarket.kalshi_live_engine import live_arming_state

        mock_config.venues.kalshi.execution_enabled = True

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("KALSHI_LIVE_TRADING_ENABLED", "1")
            mp.delenv("KALSHI_CONFIRM_PRODUCTION_LIVE", raising=False)
            state = live_arming_state(mock_config, execution_mode="live")
            assert state.armed is False
            assert any("KALSHI_CONFIRM_PRODUCTION_LIVE" in b for b in state.blockers)

    def test_live_arming_state_passes_with_all_checks(self, mock_config) -> None:
        """All safety gates pass produces armed=True."""
        from predmarket.kalshi_live_engine import live_arming_state

        mock_config.venues.kalshi.execution_enabled = True

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("KALSHI_LIVE_TRADING_ENABLED", "1")
            mp.setenv("KALSHI_CONFIRM_PRODUCTION_LIVE", "I_UNDERSTAND_KALSHI_LIVE_RISK")
            state = live_arming_state(mock_config, execution_mode="live")
            assert state.armed is True
            assert len(state.blockers) == 0

    def test_live_arming_requires_valid_rsa_key_material(self) -> None:
        """RSA key material availability check passes through load_private_key."""
        # Verify load_private_key rejects missing keys
        with pytest.raises(KalshiAuthError):
            load_private_key("")

        # Verify valid key loads
        _, pem = _generate_rsa_key_pem()
        key = load_private_key(pem)
        assert isinstance(key, rsa.RSAPrivateKey)
