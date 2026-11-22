---
name: router
description: Turn the home Wi-Fi networks on or off, or say whether they are on.
---

# Home Wi-Fi

The home Wi-Fi has two bands: `2.4GHz` and `5GHz`. Both use the same network name.

When the user asks whether the Wi-Fi is on, call `router__wifi_status`. Say the state of each band.

When the user turns a band on or off, call `router__wifi_set` with `band` and `enabled`. A band named `2.4`, `2.4 GHz`, or `slow` is `2.4GHz`. A band named `5`, `5 GHz`, or `fast` is `5GHz`. When the user does not name a band, use `both`.

The tool refuses to turn off every band, because this bot uses the Wi-Fi. Say the error. Offer to turn off one band.

A change takes up to a minute. Report the result only after the tool returns.
