---
name: audio
description: Turn voice replies on or off for later voice messages.
---

# Voice replies

Voice replies start off. The speech service stores the setting. Do not store it in the reply text.

When the user turns voice replies on, call `audio__audio_replies` with `enabled` true. Then say `Voice replies are on.`

When the user turns voice replies off, call `audio__audio_replies` with `enabled` false. Then say `Voice replies are off.`

A later voice message does not need this tool. Answer the person. Do not mention the setting.

A typed message gets text. When the typed message says `answer via voice`, call `audio__audio_replies` with `speak_next` true, then call `send_via` with modality `voice`, then answer in two sentences.
