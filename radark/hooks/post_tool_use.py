"""PostToolUse hook (owner-wrap-up-on-demand D4): once the dispatcher lists this session in its wrap-up request, add
the wrap-up text to the session's context right after the tool call that was running, once; subagent calls (input
with `agent_id`) are skipped. Without a request it only reads its input and exits."""
import hookcommon as hc


def decide(data: dict, e: dict) -> tuple[dict | None, dict | None]:
    """(marker fields or None, hook output or None)."""
    if data.get("agent_id"):  # a subagent's tool call: the main agent gets the text
        return None, None
    text = hc.wrap_up_text(e)
    if text is None or hc.wrap_up_delivered(e):
        return None, None
    fields = {"source": "tool", "tool_name": data.get("tool_name")}
    return fields, {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}


def main() -> None:
    data = hc.read_input()  # read always, so the writer never meets a closed pipe
    e = hc.env()
    fields, output = decide(data, e)
    if fields is not None:
        hc.write_marker(e, hc.DELIVERED, **fields)
    if output is not None:
        hc.emit(output)


if __name__ == "__main__":
    main()
