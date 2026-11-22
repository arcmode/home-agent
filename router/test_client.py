import json
import unittest

from client import parse_edit_page

# A trimmed copy of the gateway page layout, with a fake password.
PAGE = """
<script>
	$("#wireless_network_switch").radioswitch({
		id: "wireless-network-switch",
		state: false ? "on" : "off"
	});
var token = "abc123token";
function click_save() {
	var rf = "1";
	var jsConfig = '{"radio_enable":"'+radio_enable
	+'", "thisUser":"'+"admin"
	+'"}';
	document.getElementById("password_field").innerHTML =
		'<input type="text" id="network_password" value="" />';
}
</script>
<input type="text" size="34" value="My &amp; Net" id="network_name" name="network_name" class="text" />
<select name="wireless_mode" id="wireless_mode">
<option value="n" >802.11 n</option><option value="a,n,ac" selected>802.11 a/n/ac</option>
</select>
<select name="encryption_method" id="security">
<option value="None" >Open</option>
<option value="WPA2_PSK_AES" selected >WPA2-PSK (AES)</option
</select>
<input type="radio"  name="channel" value="auto" id="channel_automatic" checked="checked" />
<select name="channel_number" id="channel_number">
<!--option value="36" selected="selected">36</option-->
<option value="36" >36</option><option value="157" selected="selected">157</option>
</select>
<input type="radio" name="channel_bandwidth1" value="20MHz" id="channel_bandwidth201" checked="checked" />
<input type="radio" name="channel_bandwidth1" value="80MHz" id="channel_bandwidth2" checked="checked" />
<span id="password_field"><input type="password" id="network_password" name="network_password" value="fake-pass" </span>
<input type="checkbox" id="broadcastSSID" name="broadcastSSID" checked="checked" />
<input type="checkbox" id="enableWMM" name="enableWMM" />
"""


class ParseTest(unittest.TestCase):
    def test_reads_current_settings(self):
        radio = parse_edit_page(PAGE, "2")
        self.assertFalse(radio.enabled)
        self.assertEqual(radio.token, "abc123token")
        config = json.loads(radio.config_info(True))
        self.assertEqual(
            config,
            {
                "radio_enable": "true",
                "network_name": "My & Net",
                "wireless_mode": "a,n,ac",
                "security": "WPA2_PSK_AES",
                "channel_automatic": "true",
                "channel_number": "157",
                "network_password": "fake-pass",
                "broadcastSSID": "true",
                "channel_bandwidth": "80MHz",
                "enableWMM": "false",
                "ssid_number": "2",
                "password_update": "false",
                "thisUser": "admin",
            },
        )

    def test_browser_format(self):
        text = parse_edit_page(PAGE, "2").config_info(False)
        self.assertTrue(text.startswith('{"radio_enable":"false", "network_name":'))


if __name__ == "__main__":
    unittest.main()
