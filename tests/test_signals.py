from predmarket.signals import BaseRateModel, MacroSignalExtractor, NLPEventSignalExtractor


def test_nlp_extraction_semantic_fallback():
    extractor = NLPEventSignalExtractor()
    extractor.initialized = False

    # Positive headlines should yield high probability
    p1, w1 = extractor.get_event_probability(
        "Congress passes new historical budget bill", "Tax reform passes"
    )
    assert p1 > 0.50

    # Negative headlines should yield low probability
    p2, w2 = extractor.get_event_probability("President vetoes legislative proposal", "Bill passes")
    assert p2 < 0.50

    # Empty headline returns neutral
    p3, w3 = extractor.get_event_probability("", "Question")
    assert p3 == 0.50
    assert w3 == 0.0


def test_base_rate_reference():
    model = BaseRateModel()
    rate, name, count = model.get_base_rate("political")
    assert rate == 0.28
    assert "US Legislative" in name
    assert count == 450

    # Unknown category falls back to "other"
    rate2, name2, count2 = model.get_base_rate("nonexistent")
    assert rate2 == 0.38
    assert count2 == 1200


def test_nlp_recency_anchor():
    """Test that breaking news keywords trigger higher NLP weight."""
    extractor = NLPEventSignalExtractor()
    extractor.initialized = False

    # Breaking news should get high weight (> 0.60 triggers RECENCY-ANCHOR)
    p1, w1 = extractor.get_event_probability(
        "BREAKING: Congress announces agreement on bill", "Bill passes"
    )
    assert w1 == 0.65  # Breaking news weight

    # Regular news gets lower weight
    p2, w2 = extractor.get_event_probability("Congress debates bill", "Bill passes")
    assert w2 == 0.30  # Standard weight


def test_fred_key_missing_returns_default(monkeypatch):
    """Test that missing FRED_API_KEY returns hardcoded default without HTTP call."""
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    extractor = MacroSignalExtractor()

    # Should return default without making HTTP request
    rate = extractor.fetch_fred_rate("CPIAUCSNS")
    assert rate == 3.1  # Hardcoded CPI default

    rate2 = extractor.fetch_fred_rate("FEDFUNDS")
    assert rate2 == 5.25

    rate3 = extractor.fetch_fred_rate("UNKNOWN_SERIES")
    assert rate3 == 0.0


def test_nlp_negative_sentiment_detection():
    """Test various negative sentiment keywords — no positive keywords present."""
    extractor = NLPEventSignalExtractor()
    extractor.initialized = False

    negatives = [
        "President vetoes the bill outright",
        "Senate blocks the nomination completely",
        "Negotiations stall amid gridlock in Congress",
        "Opposition rejects the proposal decisively",
        "Bill unlikely to advance, delay expected",
    ]

    for headline in negatives:
        p, w = extractor.get_event_probability(headline, "Will it pass?")
        assert p < 0.50, f"Headline '{headline}' should yield p < 0.50, got {p}"


def test_nlp_positive_sentiment_detection():
    """Test various positive sentiment keywords — no negative keywords present."""
    extractor = NLPEventSignalExtractor()
    extractor.initialized = False

    positives = [
        "Congress passes landmark legislation successfully",
        "Senate approves nomination unanimously",
        "FOMC cuts interest rates decisively",
        "Presidential support surges for reform bill",
        "Economic growth surpasses all expectations",
    ]

    for headline in positives:
        p, w = extractor.get_event_probability(headline, "Will it pass?")
        assert p > 0.50, f"Headline '{headline}' should yield p > 0.50, got {p}"
