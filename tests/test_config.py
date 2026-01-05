from marketplace.config import Settings


def test_arc_web_host_maps_to_documented_api_host():
    config = Settings(openai_base_url="https://llm.arc.vt.edu/")
    assert config.normalized_openai_base_url == "https://llm-api.arc.vt.edu/api/v1"
