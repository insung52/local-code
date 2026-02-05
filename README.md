# LLMCode

A local LLM-powered code assistant CLI, similar to Claude Code but running on your own hardware.

## Architecture

```
[ Client PC ]                              [ Server (MacBook/Linux) ]
┌─────────────────────┐                   ┌─────────────────────┐
│  CLI (Python)       │                   │  FastAPI Server     │
│  ├─ Agent Loop      │   Tailscale/VPN   │  ├─ Auth Middleware │
│  ├─ Tool Executor   │ ───────────────►  │  ├─ Ollama Client   │
│  │   ├─ list_files  │ ◄─────────────────│  └─ SSE Streaming   │
│  │   ├─ read_file   │                   │                     │
│  │   ├─ search_code │                   └─────────────────────┘
│  │   ├─ write_file  │                            │
│  │   ├─ git_status  │                            ▼
│  │   ├─ git_diff    │                        Ollama
│  │   └─ run_command │                   (qwen2.5-coder:14b)
│  └─ Context Manager │
└─────────────────────┘
```

## Features

- **Agent Loop**: Autonomous tool calling and execution
- **Code Tools**: List, read, search, and write files
- **Git Integration**: Check status and view diffs
- **Command Execution**: Run terminal commands with confirmation
- **Conversation History**: Continue previous conversations with `-c`
- **Project Scanning**: Index and summarize your codebase
- **SSE Streaming**: Real-time response streaming
- **Secure**: API key authentication, Tailscale VPN support

## Installation

### Option 1: Windows Installer (Recommended)

1. Download `llmcode-setup.exe` from [Releases](https://github.com/YOUR_USERNAME/local-code/releases)
2. Run the installer
   - **Note**: Your browser/Windows may show a security warning because the exe is not code-signed. Click "Keep" → "More info" → "Run anyway" to proceed.
3. Open a **new** terminal and run `llmcode`

### Option 2: From Source

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/local-code.git
cd local-code

# Install client
cd client
pip install -r requirements.txt

# Run installer script (Windows)
cd ..
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

## Server Setup

The server runs on a machine with Ollama installed (e.g., MacBook with M-series chip).

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull the model
ollama pull qwen2.5-coder:14b

# Setup server
cd server
pip install -r requirements.txt

# Create .env file
echo "API_KEY=your-secret-key" > .env

# Run server
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Network Setup (Tailscale)

For secure remote access:

1. Install [Tailscale](https://tailscale.com/) on both machines
2. Note the server's Tailscale IP (e.g., `100.x.x.x`)
3. Configure client: `llmcode --config`

## Usage

```bash
# Start new conversation
llmcode

# Continue previous conversation
llmcode -c

# Quick question
llmcode "explain this function"

# Scan project first
llmcode -s

# Reconfigure
llmcode --config
```

### In-chat Commands

| Command | Description |
|---------|-------------|
| `/scan` | Scan and index project files |
| `/include <path>` | Add file to context |
| `/clear` | Clear conversation history |
| `/quit` | Exit |
| `ESC` | Stop generation |

### Available Tools

The AI can use these tools autonomously:

| Tool | Description |
|------|-------------|
| `list_files` | List directory contents |
| `read_file` | Read file content |
| `search_code` | Search for text in code |
| `write_file` | Write/edit files (requires confirmation) |
| `git_status` | Check git status |
| `git_diff` | View git diff |
| `run_command` | Run terminal commands (requires confirmation) |

## Configuration

Config file location: `~/.llmcode/config.json`

```json
{
  "server_url": "http://100.x.x.x:8000",
  "api_key": "your-api-key",
  "default_model": "qwen2.5-coder:14b"
}
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| Server | FastAPI, Uvicorn, SSE |
| Client | Click, httpx, Rich |
| Vector DB | ChromaDB |
| LLM | Ollama (qwen2.5-coder:14b) |
| Network | Tailscale VPN |

## Project Structure

```
local-code/
├── server/
│   ├── main.py           # FastAPI app
│   ├── config.py         # Server config
│   ├── auth.py           # API key auth
│   ├── ollama_client.py  # Ollama integration
│   └── routes/           # API endpoints
├── client/
│   ├── cli.py            # Main CLI
│   ├── agent.py          # Agent loop
│   ├── tools.py          # Tool definitions
│   ├── api_client.py     # Server API client
│   ├── storage.py        # SQLite & ChromaDB
│   └── scanner.py        # File scanner
├── installer/
│   ├── installer.py      # Windows installer
│   ├── uninstaller.py    # Uninstaller
│   └── build.py          # PyInstaller build
└── docs/
    ├── macbook-deploy.md # Server deployment guide
    └── client-setup.md   # Client setup guide
```

## License

MIT
