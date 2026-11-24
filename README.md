# Home agent

This repository is the workspace for the local Telegram bot. ZeroClaw reads `IDENTITY.md` and `SOUL.md` from this directory. The sauna tools and the sauna skill stay in `~/code/solara`.

ZeroClaw runs as a user service. The agent uses Claude Haiku 5.5 over the Anthropic API. Ollama is installed, but no agent uses it. The live config is `~/.zeroclaw/config.toml`. An example with no secrets is in `deploy/zeroclaw.config.example.toml`.

## Layout

| Part | Role | Location |
| --- | --- | --- |
| This repo | Bot identity, rules, and tool catalog | `~/code/home-agent` |
| Sauna tools | Heater commands | `~/code/solara/src/sauna_mcp.py` |
| Sauna skill | Heater rules for the model | `~/code/solara/skills/sauna` |
| Skill link | The path ZeroClaw loads | `~/.zeroclaw/shared/skills` |
| Speech replies | Voice notes for Telegram | `speak/server.py` |
| Voice-reply tool | On and off setting | `audio/mcp.py` |
| Voice-reply skill | Rules for that tool | `skills/audio` |
| Wi-Fi tools | Router radio on and off | `router/mcp.py` |
| Wi-Fi skill | Rules for those tools | `skills/router` |
| Claude Haiku 5.5 | Agent model (Anthropic API) | `providers.models.anthropic.home` |
| Ollama | Local model server, not used | `127.0.0.1:11434` |
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

## Audio replies

The speech reply service builds WAV audio on this computer. It listens on `127.0.0.1:8179`. The laptop speakers stay quiet. ZeroClaw converts the WAV to Opus with `ffmpeg` and uploads a voice note to the same chat. The service uses `SPEAK_VOICE` from `deploy/speak.service`. Change that line, then run `systemctl --user daemon-reload` and restart `speak.service`.

Voice replies start off. Say or type `turn voice replies on` or `turn voice replies off`. The speech service stores that setting. Later answers do not repeat it.

A typed message gets text. A typed message that says `answer via voice` gets a voice note. A voice message gets text while voice replies are off. The service refuses the voice note. A voice message gets text and a voice note while voice replies are on. The voice note follows the text by about 10 seconds. A reply of 40 characters or fewer stays text, so a voice answer uses two sentences.

The service file is `deploy/speak.service`. The program is `speak/server.py`. The voice is `en_US-libritts-high`. The first start downloads the voice into `~/.cache/home-agent/piper`.

```bash
systemctl --user enable --now speak.service
systemctl --user status speak.service
```

## Wi-Fi

The Wi-Fi tools talk to the Xfinity gateway at `10.0.0.1` over HTTP. No browser runs. Each call logs in, reads the current settings from the wireless edit page, and posts them back with only `radio_enable` changed. The network name, password, and channel stay the same.

Say or type `is the wifi on`, `turn off the 5GHz wifi`, or `turn the wifi on`. A request with no band uses both bands.

This computer reaches the internet over Wi-Fi. The tool refuses to turn off every band while that is true, because the bot could not turn the Wi-Fi back on. With an Ethernet cable plugged in, the tool allows it.

The router password lives in the ZeroClaw config, encrypted. It is not in this repo.

```bash
zeroclaw config set mcp.servers.router.env.ROUTER_PASSWORD
cd ~/code/home-agent/router && python3 -m unittest test_client
```

## Service

```bash
zeroclaw service restart
zeroclaw doctor
zeroclaw security status --agent home
```

Heater setup, Bluetooth checks, and the sauna tests are documented in `~/code/solara/README.md`.
