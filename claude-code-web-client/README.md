# Claude Code Web Client

A browser chat interface for Claude Code, built for people who will never open a terminal. It gives
them the full agent (tool use, slash commands, file edits) in a familiar chat window, with
responses that stream as they're written.

I built it so non-technical business owners could use a Claude Code workspace day to day.

## What it does

- **Streams responses** token by token, and shows each tool call as a readable line
  ("Read `reports/q3.md`", "Bash `python collect.py`") instead of raw JSON.
- **Slash-command autocomplete** from the workspace's `.claude/commands/` folder.
- **Survives a page refresh.** The session lives in the server, not the tab, so reopening the page
  replays the history and shows whether Claude is mid-turn.
- **"Clear conversation" really clears.** It tears down and replaces the agent session. Wiping only
  the display would leave Claude remembering everything that was "cleared."
- **Watchdog.** If no visible output arrives for three minutes, the user gets a plain-English message
  instead of a spinner that never stops.
- **Works offline.** The markdown and syntax-highlighting libraries are vendored in `static/`, not
  loaded from a CDN.

## How it works

```
browser  <--WebSocket-->  FastAPI server  <--Claude Agent SDK-->  Claude Code session
(index.html)               (server.py)                            (cwd = CLAUDE_WORKSPACE)
```

One long-lived `ClaudeSDKClient` session is shared by all open tabs. A background task reads SDK
events and fans them out to one `asyncio.Queue` per connected WebSocket. Text arrives as streaming
deltas; complete assistant messages are used only as a fallback when a block arrives without
having streamed, checked by whether that text is already at the tail of the current turn.

## Run it

Requires Python 3.11+ and Claude Code installed and signed in (the Agent SDK drives it).

```bash
cd claude-code-web-client
pip install -r requirements.txt
export CLAUDE_WORKSPACE=/path/to/your/project   # Windows cmd: set CLAUDE_WORKSPACE=C:\path\to\project
python -m uvicorn server:app --host 127.0.0.1 --port 8765
```

Open http://localhost:8765. `launch.bat` / `launch.sh` do the same and open the browser for you.

**Windows with Claude Code installed through npm:** recent Agent SDK versions refuse to start Claude
Code through npm's `claude.cmd` shim, because `cmd.exe` can't safely escape arguments. Startup fails
with `Refusing to execute batch script`. Install Claude Code natively, or point the client at an
existing `claude.exe` (the VS Code extension ships one under `resources/native-binary/`):

```bat
set CLAUDE_CLI_PATH=C:\path\to\claude.exe
```

**Cost:** every turn carries Claude Code's full system prompt, so even a one-word exchange costs
money. A test reply of "pong" cost about $0.11. The server receives each turn's cost from the SDK
and sends it to the browser, but the page doesn't display it yet.

Tested end to end on a clean install: streaming reply, history replayed after reconnecting, and a
connection from a foreign origin refused.

## Security model: read this before running it

**The agent runs with `permission_mode="bypassPermissions"`.** It can read, write, and run commands
in `CLAUDE_WORKSPACE` without asking. That was the right trade for its original users, who would not
understand a permission prompt. It also means **anyone who can reach this server can run commands
on your machine.** So:

- It binds to `127.0.0.1` only. **Never expose it on a network or put it behind a public URL.**
- **WebSocket Origin check.** Browsers do not apply the same-origin policy to WebSocket handshakes,
  so without this, any web page open in your browser could connect to `ws://localhost:8765` and
  drive Claude Code: a drive-by remote-code-execution path. A security review of the first version
  found exactly that. Connections from any origin other than this server are now closed with 1008.
- **Host check.** Requests whose `Host` isn't `localhost`/`127.0.0.1` are refused, which blocks DNS
  rebinding.
- Point `CLAUDE_WORKSPACE` at a project folder, not your home directory.

## A bug worth describing

The watchdog originally measured silence from a timestamp that the message handler assigned without
declaring it `global`. Python quietly made it a local variable, so the watchdog kept the previous
turn's clock. A message sent more than three minutes after the last reply could be declared "timed
out" before Claude had produced anything. There was no error and no crash, and the code read
correctly at a glance. It is fixed, with a comment explaining why the `global` is there.

## Third-party code

`static/marked.min.js` is marked v9.1.6 (MIT, © Christopher Jeffrey), and `static/highlight.min.js`
is highlight.js v11.9.0 (BSD-3-Clause). Both are vendored unmodified.
