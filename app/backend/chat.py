"""Finance AI Chat — routed through the MAS supervisor agent endpoint.

The supervisor (mas-3744e932-endpoint) uses the Responses API format:
  - Request:  { "input": [{role, content}], "max_tokens": N }
  - Response: { "output": [ {type, role, content: [{type, text}]} ] }

The final answer is in the last "message" output item. Intermediate items
contain the Genie tool call and raw table data — we surface the final
formatted answer which includes the cleaned-up markdown table + insights.

Session history is persisted to Lakebase (falls back to in-memory).
"""
import json
import aiohttp
from backend.config import get_workspace_host, get_token

MAS_ENDPOINT = "mas-3744e932-endpoint"
AGENT_ENDPOINT = MAS_ENDPOINT  # backwards-compat
FMAPI_MODEL = MAS_ENDPOINT     # backwards-compat


def _token(user_token: str | None = None) -> str:
    sp_token = get_token()
    if sp_token:
        return sp_token
    if user_token:
        return user_token
    return ""


def _extract_answer(output: list) -> str:
    """
    Extract the final formatted answer from the MAS output array.

    The output array looks like:
      [0] message  — "I'll query the system..."
      [1] function_call — Genie tool call
      [2] message  — raw <name> routing tag (skip)
      [3] message  — raw Genie SQL result table (skip)
      [4] message  — raw <name> routing tag (skip)
      [5] message  — final formatted answer  ← this is what we want

    Strategy: take the LAST message item whose text is NOT just a <name> tag.
    """
    candidates = []
    for item in output:
        if item.get("type") != "message":
            continue
        for c in item.get("content", []):
            text = c.get("text", "").strip()
            if not text:
                continue
            # Skip bare routing tags like <name>...</name>
            if text.startswith("<name>") and text.endswith("</name>"):
                continue
            candidates.append(text)

    if not candidates:
        return ""

    # The last candidate is the final formatted answer
    return candidates[-1]


async def stream_mas_agent(
    messages: list[dict],
    user_token: str | None = None,
    previous_response_id: str | None = None,
):
    """
    Call the MAS supervisor and yield the answer as streaming chunks.

    The MAS endpoint does not support SSE streaming, so we call it once
    and yield the answer in ~50-char chunks to keep the streaming UX.

    Yields dicts:
      {"type": "chunk",  "text": "..."}
      {"type": "done",   "response_id": None, "tool": None}
      {"type": "error",  "message": "..."}
    """
    import asyncio

    token = _token(user_token)
    host = get_workspace_host()
    url = f"{host}/serving-endpoints/{MAS_ENDPOINT}/invocations"

    payload = {
        "input": list(messages),
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

                body = await resp.text()

        d = json.loads(body)
        output = d.get("output", [])
        answer = _extract_answer(output)

        if not answer:
            yield {"type": "error", "message": "No answer returned from supervisor."}
            return

        # Stream the answer in chunks to preserve the typing-effect UX
        chunk_size = 40
        for i in range(0, len(answer), chunk_size):
            yield {"type": "chunk", "text": answer[i:i + chunk_size]}
            await asyncio.sleep(0.01)

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
