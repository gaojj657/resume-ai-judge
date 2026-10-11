import json
import httpx
import openai
from app.ai import structured_call, Profile


def test_real_sdk_stream_request_without_network(app, monkeypatch):
    """Exercise official SDK request/event parsing; no real API call or key."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key-for-tests")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    result = {"name": "测试", "phone": "", "email": "", "education": "本科", "major": "",
              "relevant_information": {"skills": [], "internships": [], "projects": []}}
    response = {"id": "resp_test", "object": "response", "created_at": 1, "status": "completed",
                "model": "test-model", "output": [{"type": "message", "id": "msg_test", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(result), "annotations": []}]}],
                "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30,
                          "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}},
                "parallel_tool_calls": True, "tools": [], "tool_choice": "auto", "metadata": {}}

    def transport(request):
        data = json.loads(request.content)
        assert request.url.path == "/v1/responses"
        assert data["stream"] is True and data["store"] is False
        assert data["text"]["format"]["strict"] is True
        assert data["text"]["format"]["type"] == "json_schema"
        assert data["text"]["format"]["schema"]["additionalProperties"] is False
        created = {"type": "response.created", "sequence_number": 0, "response": {**response, "status": "in_progress", "output": []}}
        completed = {"type": "response.completed", "sequence_number": 1, "response": response}
        stream = "".join(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in [created, completed])
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=stream)

    actual_client = openai.OpenAI
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: actual_client(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(transport))))
    profile, meta = structured_call(app, Profile, "提取资料", {"markdown": "合成测试"})
    assert profile == result
    assert meta["usage"]["total_tokens"] == 30
    assert meta["response_id"] == "resp_test"

