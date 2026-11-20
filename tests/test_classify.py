import pandas as pd

from cantill_pipeline.classify import RuntimeTaxonomyClassifier


def test_taxonomy_depth_and_fallback():
    taxonomy = pd.DataFrame([{
        "l1": "Mining", "l2": "Drilling", "l3": "Rods", "l4": "",
    }])
    classifier = RuntimeTaxonomyClassifier(taxonomy, ["l1", "l2", "l3", "l4"])
    classifier.build_taxonomy_fallback()
    parts, confidence = classifier.predict("drill rod")
    assert len(parts) == 4
    assert 0 <= confidence <= 1
