"""Samsung TV WebSocket remote control and pairing client.

Uses Samsung's WebSocket API (port 8001/8002) to pair with the TV
and send remote control commands. This is the same protocol used
by the Samsung SmartThings app.
"""

import base64
import json
import logging
import ssl
import time
from typing import Optional

import websocket

from .discovery import SamsungTV

logger = logging.getLogger(__name__)

APP_NAME = "Smirror"


def _encode_name(name: str) -> str:
    """Base64-encode a name for the Samsung API."""
    return base64.b64encode(name.encode()).decode()


class SamsungRemote:
    """WebSocket client for Samsung TV remote control API."""

    def __init__(self, tv: SamsungTV, app_name: str = APP_NAME):
        self.tv = tv
        self.app_name = app_name
        self._ws: Optional[websocket.WebSocket] = None
        self._token: Optional[str] = None

    @property
    def _ws_url(self) -> str:
        encoded_name = _encode_name(self.app_name)
        base = f"ws://{self.tv.ip}:8001/api/v2/channels/samsung.remote.control"
        url = f"{base}?name={encoded_name}"
        if self._token:
            url += f"&token={self._token}"
        return url

    @property
    def _wss_url(self) -> str:
        encoded_name = _encode_name(self.app_name)
        base = f"wss://{self.tv.ip}:8002/api/v2/channels/samsung.remote.control"
        url = f"{base}?name={encoded_name}"
        if self._token:
            url += f"&token={self._token}"
        return url

    def connect(self, use_ssl: bool = False, timeout: float = 10.0) -> bool:
        """Connect to the TV and complete pairing.

        On first connection, the TV will display a pairing prompt.
        The user must accept the connection on the TV.

        Returns True if connected successfully.
        """
        url = self._wss_url if use_ssl else self._ws_url

        ssl_opts = {}
        if use_ssl:
            ssl_opts = {
                "sslopt": {
                    "cert_reqs": ssl.CERT_NONE,
                    "check_hostname": False,
                }
            }

        logger.info("Connecting to %s ...", url)
        try:
            self._ws = websocket.create_connection(
                url, timeout=timeout, **ssl_opts
            )
        except ConnectionRefusedError:
            if not use_ssl:
                logger.info("Port 8001 refused, trying SSL on 8002...")
                return self.connect(use_ssl=True, timeout=timeout)
            logger.error("Connection refused on both ports.")
            return False
        except Exception as e:
            if not use_ssl:
                logger.info("Connection failed (%s), trying SSL on 8002...", e)
                return self.connect(use_ssl=True, timeout=timeout)
            logger.error("Failed to connect: %s", e)
            return False

        # Read the initial response - contains connection status
        try:
            response = json.loads(self._ws.recv())
            event = response.get("event", "")

            if event == "ms.channel.connect":
                # Successfully connected
                data = response.get("data", {})
                self._token = data.get("token")
                if self._token:
                    logger.info(
                        "Connected and paired! Token saved for future connections."
                    )
                else:
                    logger.info("Connected to TV.")
                return True

            elif event == "ms.channel.unauthorized":
                logger.warning(
                    "TV rejected the connection. Please accept the pairing "
                    "prompt on the TV and try again."
                )
                return False

            elif event == "ms.channel.timeOut":
                logger.warning("Connection timed out waiting for TV approval.")
                return False

            else:
                logger.warning("Unexpected response event: %s", event)
                # May still be connected
                return True

        except Exception as e:
            logger.error("Error reading connection response: %s", e)
            return False

    def disconnect(self):
        """Close the WebSocket connection."""
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

    def send_key(self, key: str):
        """Send a remote control key press to the TV.

        Common keys:
            KEY_POWEROFF, KEY_POWER, KEY_VOLUP, KEY_VOLDOWN, KEY_MUTE,
            KEY_CHUP, KEY_CHDOWN, KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT,
            KEY_ENTER, KEY_RETURN, KEY_HOME, KEY_SOURCE, KEY_MENU,
            KEY_TOOLS, KEY_INFO, KEY_HDMI, KEY_0-KEY_9
        """
        if not self._ws:
            raise RuntimeError("Not connected. Call connect() first.")

        payload = {
            "method": "ms.remote.control",
            "params": {
                "Cmd": "Click",
                "DataOfCmd": key,
                "Option": "false",
                "TypeOfRemote": "SendRemoteKey",
            },
        }
        self._ws.send(json.dumps(payload))
        logger.debug("Sent key: %s", key)

    def send_text(self, text: str):
        """Send text input to the TV (for search fields, etc.)."""
        if not self._ws:
            raise RuntimeError("Not connected. Call connect() first.")

        encoded = base64.b64encode(text.encode()).decode()
        payload = {
            "method": "ms.remote.control",
            "params": {
                "Cmd": encoded,
                "DataOfCmd": "base64",
                "TypeOfRemote": "SendInputString",
            },
        }
        self._ws.send(json.dumps(payload))
        logger.debug("Sent text input")

    def open_app(self, app_id: str):
        """Launch an app on the TV by its app ID."""
        if not self._ws:
            raise RuntimeError("Not connected. Call connect() first.")

        payload = {
            "method": "ms.channel.emit",
            "params": {
                "event": "ed.apps.launch",
                "to": "host",
                "data": {
                    "appId": app_id,
                    "action_type": "DEEP_LINK",
                },
            },
        }
        self._ws.send(json.dumps(payload))
        logger.debug("Launched app: %s", app_id)

    def open_browser(self, url: str):
        """Open a URL in the TV's built-in browser."""
        if not self._ws:
            raise RuntimeError("Not connected. Call connect() first.")

        payload = {
            "method": "ms.channel.emit",
            "params": {
                "event": "ed.apps.launch",
                "to": "host",
                "data": {
                    "appId": "org.tizen.browser",
                    "action_type": "NATIVE_LAUNCH",
                    "metaTag": url,
                },
            },
        }
        self._ws.send(json.dumps(payload))
        logger.debug("Opened browser URL")

    @property
    def token(self) -> Optional[str]:
        """The pairing token (if received). Save this for reconnection."""
        return self._token

    @token.setter
    def token(self, value: str):
        self._token = value

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()
