"""Finance AI Chat — Databricks Mosaic AI Agent.

Architecture:
  User question → mas-6f799597-endpoint (Mosaic AI Agent)
               → agent-finance-accounting-analytics tool (Genie space)
               → Answer

The agent handles its own routing and Genie tool calls.
Conversation continuity is maintained via previous_response_id.
Session history is persisted to Lakebase for the history drawer.
"""
import aiohttp
import json as _json
from openai import AsyncOpenAI
from backend.config import get_workspace_host, get_token

# Mosaic AI Agent serving endpoint (configured by user in Databricks UI)
AGENT_ENDPOINT = "mas-6f799597-endpoint"


def _token(user_token: str | None = None) -> str:
    """Return the best available token.

    Prefer the app service-principal token — it has CAN_QUERY on the MAS
    endpoint via the app.yaml resource grant, and carries the full
    'all-apis' scope needed for model-serving calls.
    Fall back to the forwarded user token if no SP token is present.
    """
    sp_token = get_token()
    if sp_token:
        return sp_token
    if user_token:
        return user_token
    return ""


def _extract_answer(output: list) -> str:
    """
    Pull the final human-readable answer from the agent output array.
    The output is a list of {type, content, ...} objects.
    We want the last 'message' item whose text is not an internal tool tag.
    """
    answer_parts = []
    for item in output:
        if item.get("type") != "message":
            continue
        for c in item.get("content", []):
            text = c.get("text", "").strip()
            # Skip internal routing tags like <name>...</name>
            if text and not (text.startswith("<name>") and text.endswith("</name>")):
                answer_parts.append(text)

    # Return the last meaningful chunk (the final synthesised answer)
    return answer_parts[-1] if answer_parts else ""


async def stream_mas_agent(
    messages: list[dict],
    user_token: str | None = None,
    previous_response_id: str | None = None,
):
    """Stream MAS response, yielding only the final answer token by token.

    The MAS produces output items in sequence:
      1. Thinking/planning text — buffered until response.output_item.done fires.
      2. Tool-call items (Genie SQL, function calls) — each ends with done.
      3. Final answer text — streamed immediately after the first done event.

    Yields dicts:
      {"type": "chunk",  "text": "..."}                    — token
      {"type": "done",   "response_id": "...", "tool": "..."} — stream complete
      {"type": "error",  "message": "..."}                  — failure
    """
    token = _token(user_token)
    host = get_workspace_host()
    client = AsyncOpenAI(api_key=token, base_url=f"{host}/serving-endpoints")

    pre_done_buffer = ""
    seen_done = False
    response_id = None
    tool_name = None

    kwargs: dict = {"model": AGENT_ENDPOINT, "input": messages, "stream": True}
    if previous_response_id:
        kwargs["previous_response_id"] = previous_response_id

    try:
        stream = await client.responses.create(**kwargs)
        async for event in stream:
            etype = getattr(event, "type", "")

            if etype == "response.output_text.delta":
                chunk = getattr(event, "delta", "")
                if not chunk:
                    continue
                if seen_done:
                    yield {"type": "chunk", "text": chunk}
                else:
                    pre_done_buffer += chunk

            elif etype == "response.output_item.done":
                if not seen_done:
                    # Discard the supervisor's thinking text; start streaming real answer
                    pre_done_buffer = ""
                    seen_done = True
                # Capture tool name from completed function_call items
                item = getattr(event, "item", None)
                if item and getattr(item, "type", "") == "function_call":
                    tool_name = getattr(item, "name", None)

            elif etype == "response.completed":
                resp_obj = getattr(event, "response", None)
                if resp_obj:
                    response_id = getattr(resp_obj, "id", None)

        # No done event fired → direct response with no tool calls; emit buffer
        if not seen_done and pre_done_buffer:
            yield {"type": "chunk", "text": pre_done_buffer.strip()}

        yield {"type": "done", "response_id": response_id, "tool": tool_name}

    except Exception as e:
        yield {"type": "error", "message": str(e)}


async def handle_chat(
    question: str,
    active_tab: str = "P2P",
    user_token: str | None = None,
    history: list[dict] | None = None,
    previous_response_id: str | None = None,
) -> dict:
    """
    Send a question to the Mosaic AI Agent and return a structured result.

    previous_response_id: the agent's response ID from the prior turn.
        When provided the agent resumes the same conversation thread,
        maintaining context without us having to replay history.

    history: [{role, content}] from Lakebase — used as fallback input
        for the first turn of a resumed session when previous_response_id
        is not yet known by the frontend.
    """
    token = _token(user_token)
    host = get_workspace_host()
    url = f"{host}/serving-endpoints/{AGENT_ENDPOINT}/invocations"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    result = {
        "question": question,
        "domain": active_tab,
        "routing": {"domain": "Finance Agent", "explanation": "Routed via Mosaic AI Agent (mas-6f799597)"},
        "genie_response": None,
        "sql": None,
        "data": None,
        "answer": None,
        "error": None,
        "agent": AGENT_ENDPOINT,
        "previous_response_id": None,
    }

    # Always replay history in the input array — the MAS endpoint does not
    # reliably maintain state via previous_response_id alone, so we include
    # prior turns explicitly every turn to guarantee multi-turn context.
    if history:
        messages = list(history[-20:])  # cap at 10 Q+A pairs
        messages.append({"role": "user", "content": question})
    else:
        messages = [{"role": "user", "content": question}]
    payload: dict = {"input": messages}
    if previous_response_id:
        payload["previous_response_id"] = previous_response_id

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
                    result["error"] = f"Agent error ({resp.status}): {error_text[:300]}"
                    return result
                data = await resp.json()

    except Exception as e:
        result["error"] = f"Agent call failed: {str(e)}"
        return result

    # Extract answer text
    output = data.get("output", [])
    answer = _extract_answer(output)
    result["answer"] = answer or "The agent returned no answer. Please try rephrasing."

    # Capture the response ID for the next turn
    result["previous_response_id"] = data.get("id")

    # Extract Genie tool call details if present (for the routing display)
    for item in output:
        if item.get("type") == "function_call":
            fn_name = item.get("name", "")
            args = item.get("arguments", "{}")
            try:
                import json
                parsed = json.loads(args) if isinstance(args, str) else args
            except Exception:
                parsed = {}
            result["routing"]["tool"] = fn_name
            result["routing"]["explanation"] = f"Mosaic AI Agent → {fn_name}"
            result["genie_response"] = {"space": fn_name, "query": parsed.get("genie_query", "")}
            break

    return result
