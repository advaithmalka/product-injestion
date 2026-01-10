from marketplace.evaluation import evaluate_gold_set


def test_gold_set_reports_per_field_accuracy():
    result = evaluate_gold_set("examples/gold_extractions.json")
    assert result["pages"] == 2
    assert result["overall_accuracy"] == 1.0
    assert result["field_accuracy"]["price"] == 1.0
