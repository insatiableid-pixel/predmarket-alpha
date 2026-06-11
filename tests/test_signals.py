import pytest
from predmarket.signals import NLPEventSignalExtractor, BaseRateModel

def test_nlp_extraction_semantic_fallback():
    extractor = NLPEventSignalExtractor()
    extractor.initialized = False
    
    # Positive headlines should yield high probability
    p1, w1 = extractor.get_event_probability("Congress passes new historical budget bill", "Tax reform passes")
    assert p1 > 0.50
    
    # Negative headlines should yield low probability
    p2, w2 = extractor.get_event_probability("President vetoes legislative proposal", "Bill passes")
    assert p2 < 0.50

def test_base_rate_reference():
    model = BaseRateModel()
    rate, name, count = model.get_base_rate("political")
    assert rate == 0.28
    assert "US Legislative" in name
    assert count == 450
