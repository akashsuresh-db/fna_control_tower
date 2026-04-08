"""Finance AI Chat — routed through the MAS supervisor agent endpoint.

The supervisor (mas-3744e932-endpoint) routes every question to the
Finance & Accounting Genie Space and answers with full SQL + data context.
Conversation history is replayed as messages on each turn.
Session history is persisted to Lakebase (falls back to in-memory).
"""
import json
import aiohttp
from backend.config import get_workspace_host, get_token

MAS_ENDPOINT = "mas-3744e932-endpoint"

# Keep AGENT_ENDPOINT / FMAPI_MODEL for backwards-compat with main.py import
AGENT_ENDPOINT = MAS_ENDPOINT
FMAPI_MODEL = MAS_ENDPOINT


def _token(user_token: str | None = None) -> str:
    sp_token = get_token()
    if sp_token:
        return sp_token
    if user_token:
        return user_token
    return ""


async def stream_mas_agent(
    messages: list[dict],
    user_token: str | None = None,
    previous_response_id: str | None = None,
):
    """Stream response from the MAS supervisor endpoint, yielding tokens.

    Yields dicts:
      {"type": "chunk",  "text": "..."}
      {"type": "done",   "response_id": None, "tool": None}
      {"type": "error",  "message": "..."}
    """
    token = _token(user_token)
    host = get_workspace_host()
    url = f"{host}/serving-endpoints/{MAS_ENDPOINT}/invocations"

    payload = {
        "messages": list(messages),
        "stream": True,
        "max_tokens": 2048,
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    yield {"type": "error", "message": f"HTTP {resp.status}: {error_text[:300]}"}
                    return

                async for line_bytes in resp.content:
                    line = line_bytes.decode("utf-8").strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        # Handle both chat-completions SSE and responses API formats
                        delta = (
                            chunk.get("choices", [{}])[0]
                            .get("delta", {})
                            .get("content", "")
                        )
                        if not delta:
                            # responses API format
                            delta = chunk.get("delta", {}).get("text", "") or chunk.get("text", "")
                        if delta:
                            yield {"type": "chunk", "text": delta}
                    except json.JSONDecodeError:
                        pass

        yield {"type": "done", "response_id": None, "tool": None}

    except Exception as e:
        yield {"type": "error", "message": str(e)}


async def handle_chat(
    question: str,
    active_tab: str = "P2P",
    user_token: str | None = None,
    history: list[dict] | None = None,
    previous_response_id: str | None = None,
) -> dict:
    """Send a question to the MAS supervisor and return a structured result."""
    result = {
        "question": question,
        "domain": active_tab,
        "routing": {
            "domain": "MAS Supervisor",
            "explanation": f"Routed via {MAS_ENDPOINT}",
        },
        "genie_response": None,
        "sql": None,
        "data": None,
        "answer": None,
        "error": None,
        "agent": MAS_ENDPOINT,
        "previous_response_id": None,
    }

    messages = list(history[-20:]) if history else []
    messages.append({"role": "user", "content": question})

    full_answer = ""
    async for event in stream_mas_agent(messages, user_token=user_token):
        if event["type"] == "chunk":
            full_answer += event["text"]
        elif event["type"] == "error":
            result["error"] = event["message"]
            return result

    result["answer"] = full_answer.strip() or "No answer returned. Please try again."
    return result
