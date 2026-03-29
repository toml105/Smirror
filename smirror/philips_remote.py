"""Philips TV JointSpace API remote control and pairing client.

Uses Philips' JointSpace REST API (port 1925/1926) to pair with the TV
and send remote control commands. This works with Philips Smart TVs
running Android TV or Saphi (2014 and newer).
"""

import hashlib
import hmac
import json
import logging
import string
import secrets
from typing import Optional

import requests
from requests.auth import HTTPDigestAuth

logger = logging.getLogger(__name__)

# Philips TV API base paths
API_VERSION = 6

# Key mapping from Samsung-style KEY_* names to Philips key names
SAMSUNG_TO_PHILIPS_KEYS = {
    "KEY_POWER": "Standby",
    "KEY_POWEROFF": "Standby",
    "KEY_VOLUP": "VolumeUp",
    "KEY_VOLDOWN": "VolumeDown",
    "KEY_MUTE": "Mute",
    "KEY_CHUP": "ChannelStepUp",
    "KEY_CHDOWN": "ChannelStepDown",
    "KEY_UP": "CursorUp",
    "KEY_DOWN": "CursorDown",
    "KEY_LEFT": "CursorLeft",
    "KEY_RIGHT": "CursorRight",
    "KEY_ENTER": "Confirm",
    "KEY_RETURN": "Back",
    "KEY_HOME": "Home",
    "KEY_SOURCE": "Source",
    "KEY_MENU": "Options",
    "KEY_TOOLS": "Options",
    "KEY_INFO": "Info",
    "KEY_PLAY": "Play",
    "KEY_PAUSE": "Pause",
    "KEY_STOP": "Stop",
    "KEY_FF": "FastForward",
    "KEY_REWIND": "Rewind",
    "KEY_0": "Digit0",
    "KEY_1": "Digit1",
    "KEY_2": "Digit2",
    "KEY_3": "Digit3",
    "KEY_4": "Digit4",
    "KEY_5": "Digit5",
    "KEY_6": "Digit6",
    "KEY_7": "Digit7",
    "KEY_8": "Digit8",
    "KEY_9": "Digit9",
    "KEY_RED": "RedColour",
    "KEY_GREEN": "GreenColour",
    "KEY_YELLOW": "YellowColour",
    "KEY_BLUE": "BlueColour",
}


def _generate_device_id() -> str:
    """Generate a random device ID for pairing."""
    return "smirror_" + "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(12))


class PhilipsRemote:
    """HTTP client for Philips TV JointSpace API."""

    def __init__(self, ip: str, port: int = 1926, use_ssl: bool = True):
        self.ip = ip
        self.port = port
        self.use_ssl = use_ssl
        self._device_id: Optional[str] = None
        self._auth_key: Optional[str] = None
        self._session = requests.Session()
        self._session.verify = False  # Philips TVs use self-signed certs

        # Suppress SSL warnings for self-signed certs
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    @property
    def _base_url(self) -> str:
        scheme = "https" if self.use_ssl else "http"
        return f"{scheme}://{self.ip}:{self.port}/{API_VERSION}"

    @property
    def _auth(self) -> Optional[HTTPDigestAuth]:
        if self._device_id and self._auth_key:
            return HTTPDigestAuth(self._device_id, self._auth_key)
        return None

    def _get(self, path: str, timeout: float = 5.0) -> Optional[dict]:
        """Make an authenticated GET request to the TV API."""
        try:
            resp = self._session.get(
                f"{self._base_url}/{path}",
                auth=self._auth,
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.debug("GET %s failed: %s", path, e)
            return None

    def _post(self, path: str, data: dict, timeout: float = 5.0) -> Optional[dict]:
        """Make an authenticated POST request to the TV API."""
        try:
            resp = self._session.post(
                f"{self._base_url}/{path}",
                json=data,
                auth=self._auth,
                timeout=timeout,
            )
            if resp.status_code in (200, 201):
                try:
                    return resp.json()
                except Exception:
                    return {}
            return None
        except Exception as e:
            logger.debug("POST %s failed: %s", path, e)
            return None

    def get_system_info(self) -> Optional[dict]:
        """Get TV system information (no auth needed on some models)."""
        # Try without auth first
        try:
            resp = self._session.get(
                f"{self._base_url}/system",
                timeout=5,
            )
            if resp.ok:
                return resp.json()
        except Exception:
            pass
        # Try with auth
        return self._get("system")

    def pair_request(self) -> Optional[dict]:
        """Start the pairing process. The TV will display a PIN code.

        Returns the pairing response containing auth details needed for grant.
        """
        self._device_id = _generate_device_id()

        payload = {
            "scope": ["read", "write", "control"],
            "device": {
                "device_name": "Smirror",
                "device_os": "Linux",
                "app_id": "app.id.smirror",
                "app_name": "Smirror",
                "type": "native",
                "id": self._device_id,
            },
        }

        try:
            resp = self._session.post(
                f"{self._base_url}/pair/request",
                json=payload,
                timeout=10,
            )
            if resp.ok:
                data = resp.json()
                logger.info("Pairing request sent. Check the TV for a PIN code.")
                return data
            else:
                logger.error("Pair request failed: %s %s", resp.status_code, resp.text)
                return None
        except Exception as e:
            logger.error("Pair request failed: %s", e)
            return None

    def pair_grant(self, pin: str, auth_timestamp: str = None, auth_key: str = None) -> bool:
        """Complete pairing by submitting the PIN shown on the TV.

        Returns True if pairing succeeded. Sets self._auth_key on success.
        """
        payload = {
            "auth": {
                "auth_AppId": "1",
                "pin": pin,
                "auth_timestamp": auth_timestamp or "",
                "auth_signature": self._create_signature(pin, auth_timestamp, auth_key),
            },
            "device": {
                "device_name": "Smirror",
                "device_os": "Linux",
                "app_id": "app.id.smirror",
                "app_name": "Smirror",
                "type": "native",
                "id": self._device_id,
            },
        }

        try:
            resp = self._session.post(
                f"{self._base_url}/pair/grant",
                json=payload,
                auth=HTTPDigestAuth(self._device_id, pin),
                timeout=10,
            )
            if resp.ok:
                data = resp.json()
                self._auth_key = data.get("auth_key", pin)
                logger.info("Pairing successful!")
                return True
            else:
                logger.error("Pair grant failed: %s %s", resp.status_code, resp.text)
                return False
        except Exception as e:
            logger.error("Pair grant failed: %s", e)
            return False

    def _create_signature(self, pin: str, timestamp: str = None, secret: str = None) -> str:
        """Create HMAC signature for pairing."""
        if not secret or not timestamp:
            return ""
        msg = f"{timestamp}{pin}".encode()
        return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()

    def connect(self, device_id: str = None, auth_key: str = None) -> bool:
        """Connect to the TV using saved credentials.

        If device_id and auth_key are provided, uses them directly.
        Otherwise, tries to connect without auth (works on some older models).

        Returns True if the TV is reachable and responding.
        """
        if device_id and auth_key:
            self._device_id = device_id
            self._auth_key = auth_key

        # Test connection by fetching system info
        info = self.get_system_info()
        if info:
            name = info.get("name", "Philips TV")
            logger.info("Connected to %s", name)
            return True

        # If HTTPS on 1926 fails, try HTTP on 1925
        if self.use_ssl and self.port == 1926:
            logger.info("HTTPS on 1926 failed, trying HTTP on 1925...")
            self.use_ssl = False
            self.port = 1925
            info = self.get_system_info()
            if info:
                name = info.get("name", "Philips TV")
                logger.info("Connected to %s (HTTP mode)", name)
                return True

        logger.error("Could not connect to Philips TV at %s", self.ip)
        return False

    def disconnect(self):
        """Close the session."""
        self._session.close()

    def send_key(self, key: str):
        """Send a remote control key press to the TV.

        Accepts both Philips native keys (e.g., 'VolumeUp') and
        Samsung-style KEY_* names (e.g., 'KEY_VOLUP') for compatibility.
        """
        # Translate Samsung key names to Philips if needed
        if key.startswith("KEY_"):
            philips_key = SAMSUNG_TO_PHILIPS_KEYS.get(key)
            if not philips_key:
                logger.warning("Unknown key mapping for %s", key)
                return
            key = philips_key

        result = self._post("input/key", {"key": key})
        if result is not None:
            logger.debug("Sent key: %s", key)
        else:
            logger.error("Failed to send key: %s", key)

    def send_text(self, text: str):
        """Send text input to the TV (not directly supported by all models)."""
        # Philips doesn't have a direct text input API like Samsung.
        # We simulate it by sending individual character keys.
        logger.warning("Text input is limited on Philips TVs. Sending as individual keys.")
        for char in text:
            if char.isdigit():
                self.send_key(f"Digit{char}")

    def open_browser(self, url: str):
        """Open a URL on the TV's browser via the activities API."""
        payload = {
            "intent": {
                "action": "android.intent.action.VIEW",
                "component": {
                    "packageName": "org.chromium.webview_shell",
                    "className": "org.chromium.webview_shell.WebViewBrowserActivity",
                },
                "data": url,
            },
        }
        result = self._post("activities/launch", payload)
        if result is not None:
            logger.debug("Opened browser URL: %s", url)
        else:
            # Fallback: try alternative browser package
            payload["intent"]["component"] = {
                "packageName": "com.vewd.core.integration.dia",
                "className": "com.aspect.webbrowser.BrowserActivity",
            }
            result = self._post("activities/launch", payload)
            if result is not None:
                logger.debug("Opened browser URL (fallback): %s", url)
            else:
                logger.error("Failed to open URL. TV may not support browser launch.")

    def open_app(self, package_name: str):
        """Launch an app on the TV by package name."""
        payload = {
            "intent": {
                "action": "android.intent.action.MAIN",
                "component": {
                    "packageName": package_name,
                    "className": "",
                },
            },
        }
        result = self._post("activities/launch", payload)
        if result is not None:
            logger.debug("Launched app: %s", package_name)
        else:
            logger.error("Failed to launch app: %s", package_name)

    def get_current_channel(self) -> Optional[dict]:
        """Get the current TV channel."""
        return self._get("activities/current")

    def get_ambilight_power(self) -> Optional[dict]:
        """Get Ambilight power state."""
        return self._get("ambilight/power")

    def set_ambilight_power(self, on: bool):
        """Toggle Ambilight on/off."""
        self._post("ambilight/power", {"power": "On" if on else "Off"})

    @property
    def device_id(self) -> Optional[str]:
        return self._device_id

    @property
    def auth_key(self) -> Optional[str]:
        return self._auth_key

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()
