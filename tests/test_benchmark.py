from marketplace.benchmark import run_parser_benchmark


def test_parser_benchmark_counts_events():
    result = run_parser_benchmark("examples/manifest.json", events=10)
    assert result["events"] == 10
    assert result["succeeded"] == 10
    assert result["failed"] == 0
    assert result["events_per_second"] > 0
