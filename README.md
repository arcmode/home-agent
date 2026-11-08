# Home agent

This repository is the workspace for the local Telegram bot. ZeroClaw reads `IDENTITY.md` and `SOUL.md` from this directory. The sauna tools and the sauna skill stay in `~/code/solara`.

Ollama and ZeroClaw run as user services. The live config is `~/.zeroclaw/config.toml`. An example with no secrets is in `deploy/zeroclaw.config.example.toml`.

## Layout

| Part | Role | Location |
| --- | --- | --- |
| This repo | Bot identity, rules, and tool catalog | `~/code/home-agent` |
| Sauna tools | Heater commands | `~/code/solara/src/sauna_mcp.py` |
| Sauna skill | Heater rules for the model | `~/code/solara/skills/sauna` |
| Skill link | The path ZeroClaw loads | `~/.zeroclaw/shared/skills/sauna` |
| Ollama | Local model server | `127.0.0.1:11434` |
| ZeroClaw | Agent and Telegram channel | `127.0.0.1:42617` |

The skill link points at the solara skill directory. This repo does not keep a second copy.

## Link the skills

```bash
python3 ~/code/home-agent/scripts/link-tools.py
```

The script reads `tools.toml`. For each tool with a `skill` path, it creates a symlink under `~/.zeroclaw/shared/skills`.

## Add a tool

1. Add one block to `tools.toml`. Set `repo` to a directory under `~/code`, or set `command` to an MCP program.
2. Run `scripts/link-tools.py`.
3. Add the MCP server and the bundle with `zeroclaw config set`.
4. Add the tool names to `allowed_tools` on the `home` risk profile.
5. Run `zeroclaw service restart`.

A skill file tells the model when to use a tool. The risk profile grants the tool.

## Shell

The shell can run `ls` and `cat`. The autonomy level is `supervised`, so the workspace boundary stays on. The five sauna tools are in `auto_approve`, so a heater command does not wait for a second approval. Every shell command asks for approval in the Telegram chat, because `shell` is in `always_ask`. A missing answer denies the command after 120 seconds.

The example config requests Landlock. `deploy/zeroclaw.config.example.toml` sets `sandbox_backend` to `landlock`.

Sauna commands do not use that approval. The sauna program checks the heater limits.

To add a command later, add its executable name to `allowed_commands` and restart the service. The list holds names such as `ls`. It does not hold a script path. Add one directory to `allowed_roots` when a command must read that repository.

Leave `python`, `bash`, `curl`, and `ssh` off the command list. A repository script that needs one of those programs gets its own MCP command. Start that process with `bwrap` and put the directory in `tools.toml`.

## Voice messages

The speech service turns audio into text. It listens on `127.0.0.1:8178`. ZeroClaw sends each Telegram voice message to that service. The model then answers the transcript as text.

The service file is `deploy/transcribe.service`. The program is `transcribe/server.py`. The model is `small`. The first start downloads the model into `~/.cache/home-agent/whisper`.

```bash
systemctl --user enable --now transcribe.service
systemctl --user status transcribe.service
```

A voice message longer than 120 seconds is skipped. Send a new voice message after you enable the service. ZeroClaw does not retry a voice message it already skipped.

## Service

```bash
zeroclaw service restart
zeroclaw doctor
zeroclaw security status --agent home
```

Heater setup, Bluetooth checks, and the sauna tests are documented in `~/code/solara/README.md`.
