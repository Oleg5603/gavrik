from ledovskikh_agent.core import Message, StateStore, extract_urls, is_public_http_url, relevance

def test_extract_and_relevance():
    assert extract_urls("Codex agents: https://example.com/x.") == ["https://example.com/x"]
    assert "codex" in relevance("Codex agents")

def test_vibe_coding_relevance_variants():
    for text in ("вайбкодинг", "вайб-кодинг", "вайб кодинг", "vibe coding", "vibecoding"):
        assert relevance(text), text

def test_ssrf_guard():
    assert not is_public_http_url("http://127.0.0.1/a", lambda _: ["127.0.0.1"])
    assert not is_public_http_url("http://example.com:3000/a", lambda _: ["93.184.216.34"])
    assert is_public_http_url("https://example.com/a", lambda _: ["93.184.216.34"])

def test_checkpoint_and_dedup(tmp_path):
    store = StateStore(tmp_path / "state.json")
    msg = Message(1, 5, "2026-01-01", "Про Codex: https://example.com", "Нейрозавод")
    assert len(store.process([msg])) == 1
    assert store.process([msg]) == []
    assert store.checkpoint(1) == 5
