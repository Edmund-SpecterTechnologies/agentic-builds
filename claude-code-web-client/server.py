"""Claude Code Web Client: a local web server bridging a browser chat UI and the Claude Agent SDK."""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ToolUseBlock,
    UserMessage,
    ToolResultBlock,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Claude Code Web Client")

# ── Paths ────────────────────────────────────────────────────────────────────
GUI_DIR = Path(__file__).resolve().parent
# The folder Claude Code works in. Point this at a project you are happy for the
# agent to read and write: it runs with bypassPermissions (see README).
WORKSPACE_ROOT = Path(os.environ.get("CLAUDE_WORKSPACE", GUI_DIR.parent)).resolve()
COMMANDS_DIR = WORKSPACE_ROOT / ".claude" / "commands"

# marked.js / highlight.js are vendored locally (static/) rather than loaded
# from a CDN, so the GUI works fully offline on a client machine with no internet.
app.mount("/static", StaticFiles(directory=str(GUI_DIR / "static")), name="static")

# ── Session state (persists for server lifetime) ──────────────────────────────
_client: ClaudeSDKClient | None = None
_receive_task: asyncio.Task | None = None    # background task currently reading _client's messages
_history: list[dict[str, Any]] = []          # display-ready message history
_subscribers: list[asyncio.Queue] = []        # one Queue per connected WebSocket
_current_text: str = ""                       # accumulates streaming text for current turn
_current_tools: list[dict] = []              # tool uses in current turn
_is_processing: bool = False                  # true while Claude is mid-turn
_last_event_time: float = 0.0                # timestamp of last SDK event (for receive_loop internal use)
_last_visible_event_time: float = 0.0        # timestamp of last user-visible event (for watchdog)

CLAUDE_OPTIONS_KWARGS = dict(
    cwd=str(WORKSPACE_ROOT),
    permission_mode="bypassPermissions",
    system_prompt={"type": "preset", "preset": "claude_code"},
    include_partial_messages=True,
)
# Recent Agent SDK versions refuse to launch Claude Code through a Windows
# .cmd shim (the npm install), because cmd.exe can't safely escape arguments.
# Point this at a native claude.exe instead. See README.
if os.environ.get("CLAUDE_CLI_PATH"):
    CLAUDE_OPTIONS_KWARGS["cli_path"] = os.environ["CLAUDE_CLI_PATH"]

WATCHDOG_TIMEOUT = 180.0  # seconds with no user-visible output before declaring a hang

# Browsers don't enforce same-origin policy on WebSocket handshakes, so any page
# open in the browser could otherwise connect to this socket and drive Claude Code
# with bypassPermissions. Restrict connections to pages actually served by us.
PORT = int(os.environ.get("CLAUDE_WEB_PORT", "8765"))
ALLOWED_WS_ORIGINS = {f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}"}

# DNS rebinding defence: an attacker domain that re-resolves to 127.0.0.1 would
# otherwise be served as if it were localhost.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])


# ── Startup / Shutdown ────────────────────────────────────────────────────────

async def _start_client_and_loop() -> None:
    """(Re)create the ClaudeSDKClient and start a receive_loop bound to it."""
    global _client, _receive_task
    logger.info(f"Starting Claude Code session in: {WORKSPACE_ROOT}")
    options = ClaudeAgentOptions(**CLAUDE_OPTIONS_KWARGS)
    _client = ClaudeSDKClient(options=options)
    await _client.connect()
    _receive_task = asyncio.create_task(receive_loop())
    logger.info("Claude Code session ready.")


async def reset_session() -> bool:
    """Discard the current Claude session and start a brand-new one.

    Used by the "clear conversation" action — wiping only the display history
    would leave Claude still remembering everything that was "cleared," so the
    underlying SDK client is torn down and replaced rather than just the UI state.
    Returns False (no-op) if a turn is currently in progress.
    """
    global _client, _receive_task, _history, _current_text, _current_tools, _last_visible_event_time
    if _is_processing:
        return False

    old_client, old_task = _client, _receive_task
    if old_task:
        old_task.cancel()
        try:
            await old_task
        except (asyncio.CancelledError, Exception):
            pass
    if old_client:
        await old_client.disconnect()

    _history = []
    _current_text = ""
    _current_tools = []
    _last_visible_event_time = 0.0
    await _start_client_and_loop()
    return True


@app.on_event("startup")
async def startup_event() -> None:
    await _start_client_and_loop()
    asyncio.create_task(watchdog_loop())


@app.on_event("shutdown")
async def shutdown_event() -> None:
    global _client
    if _client:
        await _client.disconnect()


# ── Background receive loop ───────────────────────────────────────────────────

async def receive_loop() -> None:
    """Read messages from Claude SDK and broadcast to all WebSocket subscribers."""
    global _current_text, _current_tools, _history, _is_processing, _last_event_time, _last_visible_event_time

    async for message in _client.receive_messages():
        _last_event_time = time.monotonic()
        events_to_broadcast: list[dict] = []

        # ── Streaming text chunks ──
        if isinstance(message, StreamEvent):
            raw = message.event
            ev_type = raw.get("type")
            if ev_type == "content_block_start":
                # A new content block is starting. If it's text and we already have
                # prior text in this turn (narration from an earlier block, or a
                # previous tool call's lead-in), insert a paragraph break before it.
                if raw.get("content_block", {}).get("type") == "text" and _current_text:
                    _current_text += "\n\n"
                    _last_visible_event_time = time.monotonic()
                    events_to_broadcast.append({"type": "text_chunk", "content": "\n\n"})
            elif ev_type == "content_block_delta":
                delta = raw.get("delta", {})
                if delta.get("type") == "text_delta":
                    chunk = delta.get("text", "")
                    if chunk:
                        _current_text += chunk
                        _last_visible_event_time = time.monotonic()
                        events_to_broadcast.append({"type": "text_chunk", "content": chunk})

        # ── Complete assistant message (tool uses + fallback text) ──
        elif isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    # With include_partial_messages=True, StreamEvent already delivered
                    # this exact text via content_block_delta chunks above — this branch
                    # is a fallback for the rare case where a block arrives complete
                    # without having streamed (e.g. a very short block). Detect "already
                    # streamed" by checking whether it's already sitting at the tail of
                    # _current_text, rather than assuming streaming always precedes it.
                    if block.text and not _current_text.endswith(block.text):
                        chunk = ("\n\n" + block.text) if _current_text else block.text
                        _current_text += chunk
                        _last_visible_event_time = time.monotonic()
                        events_to_broadcast.append({"type": "text_chunk", "content": chunk})
                elif isinstance(block, ToolUseBlock):
                    summary = _summarize_input(block.name, block.input)
                    tool_event = {
                        "type": "tool_use",
                        "name": block.name,
                        "input": summary,
                    }
                    _current_tools.append({"name": block.name, "input_summary": summary})
                    _last_visible_event_time = time.monotonic()
                    events_to_broadcast.append(tool_event)

        # ── User message with tool results ──
        elif isinstance(message, UserMessage):
            if isinstance(message.content, list):
                for block in message.content:
                    if isinstance(block, ToolResultBlock):
                        events_to_broadcast.append({"type": "tool_result"})

        # ── Turn complete ──
        elif isinstance(message, ResultMessage):
            ts = time.time()
            if _current_text or _current_tools:
                _history.append({
                    "role": "assistant",
                    "content": _current_text,
                    "tools": _current_tools,
                    "timestamp": ts,
                })
            _current_text = ""
            _current_tools = []
            _is_processing = False
            _last_visible_event_time = time.monotonic()
            events_to_broadcast.append({
                "type": "done",
                "cost": message.total_cost_usd,
                "is_error": message.is_error,
                "timestamp": ts,
            })

        # Broadcast all events to subscribers
        _broadcast(events_to_broadcast)


async def watchdog_loop() -> None:
    """Broadcast a timeout error if no user-visible event arrives within WATCHDOG_TIMEOUT seconds."""
    global _is_processing, _current_text, _current_tools, _last_visible_event_time
    while True:
        await asyncio.sleep(15)
        if _is_processing and _last_visible_event_time > 0:
            elapsed = time.monotonic() - _last_visible_event_time
            if elapsed > WATCHDOG_TIMEOUT:
                logger.warning(f"Watchdog: no visible output for {elapsed:.0f}s — declaring timeout")
                _is_processing = False
                _current_text = ""
                _current_tools = []
                _last_visible_event_time = 0.0
                mins = int(WATCHDOG_TIMEOUT // 60)
                _broadcast([{
                    "type": "error",
                    "message": f"No response for {mins} minutes. Claude may be processing a very large file. Restart the server to reset.",
                }])


def _broadcast(events: list[dict]) -> None:
    """Put events into all subscriber queues, removing dead ones."""
    dead = []
    for event in events:
        for q in _subscribers:
            try:
                q.put_nowait(event)
            except Exception:
                if q not in dead:
                    dead.append(q)
    for q in dead:
        if q in _subscribers:
            _subscribers.remove(q)


def _make_relative(path_str: str) -> str:
    """Convert an absolute path to a relative path from WORKSPACE_ROOT."""
    if not path_str:
        return ""
    try:
        return str(Path(path_str).relative_to(WORKSPACE_ROOT))
    except ValueError:
        return Path(path_str).name  # fallback: just the filename


def _summarize_input(tool_name: str, tool_input: dict) -> str:
    """Return a human-readable summary of what a tool is doing."""
    if tool_name in ("Read", "Write", "Edit", "MultiEdit"):
        return _make_relative(tool_input.get("file_path", ""))
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        return cmd[:80] + ("…" if len(cmd) > 80 else "")
    if tool_name == "Glob":
        return tool_input.get("pattern", "")
    if tool_name == "Grep":
        return tool_input.get("pattern", "")
    if tool_name in ("WebFetch", "WebSearch"):
        return tool_input.get("url", tool_input.get("query", ""))
    return ""


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
async def root() -> HTMLResponse:
    html = (GUI_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@app.get("/api/commands")
async def get_commands() -> dict:
    """Return all available slash commands for autocomplete."""
    commands = []
    if COMMANDS_DIR.exists():
        # Sort by command name, not filename — "prime.md" vs "prime-telegram.md"
        # sort in the opposite order if compared with the .md suffix attached
        # ('-' < '.' in ASCII), which put the wrong command first for autocomplete.
        for f in sorted(COMMANDS_DIR.glob("*.md"), key=lambda p: p.stem):
            commands.append(f.stem)
    return {"commands": commands}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    if ws.headers.get("origin") not in ALLOWED_WS_ORIGINS:
        await ws.close(code=1008)
        return
    await ws.accept()

    queue: asyncio.Queue = asyncio.Queue()
    _subscribers.append(queue)

    # Send full history on connect
    await ws.send_json({"type": "history", "messages": _history})

    # If Claude is mid-turn, tell the browser so it shows waiting state
    if _is_processing:
        await ws.send_json({"type": "waiting", "value": True})

    async def receive_from_browser() -> None:
        """Listen for user messages from the browser."""
        # _last_visible_event_time must be declared global here: without it the
        # assignment below creates a local, the watchdog keeps the previous turn's
        # timestamp, and a new message sent >3 min after the last reply can be
        # declared "timed out" before Claude has produced any output.
        global _is_processing, _last_event_time, _last_visible_event_time
        try:
            while True:
                raw = await ws.receive_text()
                data = json.loads(raw)
                if data.get("type") == "user_message":
                    text = data["content"].strip()
                    if not text:
                        continue
                    if _is_processing:
                        # Reject while mid-turn — browser should prevent this but just in case
                        await ws.send_json({
                            "type": "error",
                            "message": "Still processing previous message. Please wait.",
                        })
                        continue
                    ts = time.time()
                    _history.append({"role": "user", "content": text, "timestamp": ts})
                    await ws.send_json({"type": "user_echo", "content": text, "timestamp": ts})
                    _is_processing = True
                    _last_event_time = time.monotonic()
                    _last_visible_event_time = time.monotonic()
                    await _client.query(text)
                elif data.get("type") == "clear_conversation":
                    if _is_processing:
                        await ws.send_json({
                            "type": "error",
                            "message": "Still processing. Please wait before clearing.",
                        })
                        continue
                    ok = await reset_session()
                    if ok:
                        _broadcast([{"type": "history", "messages": []}])
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error(f"Browser receive error: {e}")

    async def send_to_browser() -> None:
        """Forward SDK events from queue to browser."""
        try:
            while True:
                event = await queue.get()
                await ws.send_json(event)
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error(f"Browser send error: {e}")

    try:
        await asyncio.gather(receive_from_browser(), send_to_browser())
    finally:
        if queue in _subscribers:
            _subscribers.remove(queue)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=PORT, reload=False)
