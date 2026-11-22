"""HTTP client for the Xfinity gateway Wi-Fi radios.

The gateway web UI has no API. This module logs in like the browser,
reads the current settings from the edit page, and posts them back with
only radio_enable changed. Every other setting keeps its current value.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from pathlib import Path

BANDS = {"2.4GHz": "1", "5GHz": "2"}
USER_AGENT = "home-agent-router/1.0"
SET_PATH = "/actionHandler/ajaxSet_wireless_network_configuration_edit.jst"


class RouterError(RuntimeError):
    pass


@dataclass
class Radio:
    ssid_number: str
    enabled: bool
    token: str
    form: dict[str, str]

    def config_info(self, enabled: bool) -> str:
        """Build configInfo in the same key order and format as the browser."""
        f = self.form
        config = {
            "radio_enable": _flag(enabled),
            "network_name": f["network_name"],
            "wireless_mode": f["wireless_mode"],
            "security": f["security"],
            "channel_automatic": f["channel_automatic"],
            "channel_number": f["channel_number"],
            "network_password": f["network_password"],
            "broadcastSSID": f["broadcastSSID"],
            "channel_bandwidth": f["channel_bandwidth"],
            "enableWMM": f["enableWMM"],
            "ssid_number": self.ssid_number,
            "password_update": "false",
            "thisUser": f["thisUser"],
        }
        return json.dumps(config, separators=(", ", ":"), ensure_ascii=False)


def _flag(value: bool) -> str:
    return "true" if value else "false"


class _FormParser(HTMLParser):
    """Collect the values the browser reads in click_save()."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.inputs: dict[str, dict[str, str | None]] = {}
        self.radios: dict[str, str] = {}
        self.selects: dict[str, str] = {}
        self._select: str | None = None
        self._first_option: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "input":
            element_id = a.get("id")
            if element_id and element_id not in self.inputs:
                self.inputs[element_id] = a
            if a.get("type") == "radio" and "checked" in a and a.get("name"):
                # A later checked radio in the same group wins, as in a browser.
                self.radios[a["name"]] = a.get("value") or ""
        elif tag == "select":
            self._select = a.get("id")
            self._first_option = None
        elif tag == "option" and self._select:
            value = a.get("value") or ""
            if self._first_option is None:
                self._first_option = value
            if "selected" in a:
                self.selects[self._select] = value

    def handle_endtag(self, tag: str) -> None:
        if tag == "select" and self._select:
            if self._select not in self.selects and self._first_option is not None:
                self.selects[self._select] = self._first_option
            self._select = None


def parse_edit_page(page: str, ssid_number: str) -> Radio:
    token = re.search(r'var token = "([^"]+)"', page)
    state = re.search(
        r'#wireless_network_switch"\)\.radioswitch\(\{.*?state:\s*(true|false)\s*\?',
        page,
        re.S,
    )
    rf = re.search(r'var rf\s*=\s*"([^"]*)"', page)
    user = re.search(r'"thisUser":"\'?\s*\+\s*"([^"]+)"', page)
    if not token or not state or rf is None:
        raise RouterError("the Wi-Fi edit page did not have the expected layout")

    parser = _FormParser()
    parser.feed(page)
    inputs = parser.inputs

    def checked(element_id: str) -> str:
        element = inputs.get(element_id)
        if element is None:
            raise RouterError(f"missing field {element_id}")
        return _flag("checked" in element)

    def value(element_id: str) -> str:
        element = inputs.get(element_id)
        if element is None or element.get("value") is None:
            raise RouterError(f"missing field {element_id}")
        return element["value"] or ""

    def selected(element_id: str) -> str:
        if element_id not in parser.selects:
            raise RouterError(f"missing field {element_id}")
        return parser.selects[element_id]

    bandwidth = parser.radios.get("channel_bandwidth" + rf.group(1))
    if bandwidth is None:
        raise RouterError("missing field channel_bandwidth")

    form = {
        "network_name": value("network_name"),
        "wireless_mode": selected("wireless_mode"),
        "security": selected("security"),
        "channel_automatic": checked("channel_automatic"),
        "channel_number": selected("channel_number"),
        "network_password": value("network_password"),
        "broadcastSSID": checked("broadcastSSID"),
        "channel_bandwidth": bandwidth,
        "enableWMM": checked("enableWMM"),
        "thisUser": user.group(1) if user else "admin",
    }
    return Radio(ssid_number, state.group(1) == "true", token.group(1), form)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return None


class Router:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.cookies = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies), _NoRedirect()
        )

    @classmethod
    def from_env(cls) -> "Router":
        password = os.environ.get("ROUTER_PASSWORD")
        if not password:
            raise RouterError("ROUTER_PASSWORD is not set")
        return cls(
            os.environ.get("ROUTER_URL", "http://10.0.0.1"),
            os.environ.get("ROUTER_USER", "admin"),
            password,
        )

    def _request(
        self,
        path: str,
        data: dict[str, str] | None = None,
        referer: str = "/index.jst",
        timeout: float = 15,
        ajax: bool = False,
    ) -> tuple[int, dict[str, str], str]:
        headers = {
            "User-Agent": USER_AGENT,
            "Origin": self.base,
            "Referer": self.base + referer,
        }
        body = None
        if data is not None:
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        if ajax:
            headers["X-Requested-With"] = "XMLHttpRequest"
        request = urllib.request.Request(self.base + path, data=body, headers=headers)
        try:
            with self.opener.open(request, timeout=timeout) as response:
                return response.status, dict(response.headers), response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            if 300 <= exc.code < 400:
                return exc.code, dict(exc.headers), ""
            raise RouterError(f"router returned HTTP {exc.code} for {path}") from exc

    def login(self) -> None:
        status, headers, _ = self._request(
            "/check.jst", {"username": self.username, "password": self.password}
        )
        location = headers.get("location") or headers.get("Location") or ""
        if status != 302 or "at_a_glance" not in location:
            raise RouterError("router login failed")

    def logout(self) -> None:
        try:
            self._request("/home_loggedout.jst", timeout=5)
        except (RouterError, OSError):
            pass

    def radio(self, band: str) -> Radio:
        ssid_number = BANDS[band]
        status, _, page = self._request(
            f"/wireless_network_configuration_edit.jst?id={ssid_number}",
            referer="/wireless_network_configuration.jst",
        )
        if status != 200:
            raise RouterError("router session expired")
        return parse_edit_page(page, ssid_number)

    def set_radio(self, band: str, enabled: bool) -> None:
        radio = self.radio(band)
        if radio.enabled == enabled:
            return
        data = {"configInfo": radio.config_info(enabled), "csrfp_token": radio.token}
        try:
            _, _, body = self._request(
                SET_PATH,
                data,
                referer=f"/wireless_network_configuration_edit.jst?id={radio.ssid_number}",
                timeout=90,
                ajax=True,
            )
        except (OSError, urllib.error.URLError):
            # This computer may be on the radio that just went down. The
            # caller checks the result after the link comes back.
            return
        try:
            result = json.loads(body)
        except json.JSONDecodeError:
            result = body.strip()
        if result != "success":
            raise RouterError(f"router refused the change: {str(result)[:200]}")


def host_uses_wifi() -> bool:
    """True when the default route of this computer goes over Wi-Fi."""
    try:
        lines = Path("/proc/net/route").read_text().splitlines()[1:]
    except OSError:
        return True
    for line in lines:
        fields = line.split()
        if len(fields) > 1 and fields[1] == "00000000":
            return Path(f"/sys/class/net/{fields[0]}/wireless").exists()
    return True


def status() -> dict:
    router = Router.from_env()
    router.login()
    try:
        radios = {band: router.radio(band) for band in BANDS}
    finally:
        router.logout()
    return {
        "confirmed": True,
        "network_name": radios["2.4GHz"].form["network_name"],
        **{band: ("on" if r.enabled else "off") for band, r in radios.items()},
    }


def set_wifi(band: str, enabled: bool, wait_secs: float = 60) -> dict:
    targets = list(BANDS) if band == "both" else [band]
    if any(t not in BANDS for t in targets):
        return {"confirmed": False, "error": "band must be 2.4GHz, 5GHz, or both"}

    router = Router.from_env()
    router.login()
    try:
        current = {b: router.radio(b).enabled for b in BANDS}
        planned = {**current, **{t: enabled for t in targets}}
        if not any(planned.values()) and host_uses_wifi():
            return {
                "confirmed": False,
                "error": (
                    "Refused: this would turn off every Wi-Fi band, and this bot "
                    "reaches the internet over Wi-Fi. Nobody could turn it back on "
                    "from Telegram."
                ),
            }
        for target in targets:
            router.set_radio(target, enabled)
    finally:
        router.logout()

    # Read the state back. Retry while this computer reconnects.
    deadline = time.monotonic() + wait_secs
    last_error = ""
    while True:
        try:
            result = status()
            if all(result[t] == ("on" if enabled else "off") for t in targets):
                return result
            last_error = "the router still reports the old state"
        except (RouterError, OSError) as exc:
            last_error = str(exc)
        if time.monotonic() >= deadline:
            return {"confirmed": False, "error": f"could not confirm the change: {last_error}"}
        time.sleep(5)
