"""SSDP/UPnP discovery for Samsung and Philips Smart TVs on the local network."""

import socket
import re
import time
import logging
from dataclasses import dataclass, field
from typing import Optional
from xml.etree import ElementTree

import requests

logger = logging.getLogger(__name__)

SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900
SSDP_TIMEOUT = 5

# Samsung TVs respond to these search targets
SEARCH_TARGETS = [
    "urn:samsung.com:device:RemoteControlReceiver:1",
    "urn:dial-multiscreen-org:service:dial:1",
    "urn:schemas-upnp-org:device:MediaRenderer:1",
]

SSDP_MSEARCH = (
    "M-SEARCH * HTTP/1.1\r\n"
    "HOST: {addr}:{port}\r\n"
    "MAN: \"ssdp:discover\"\r\n"
    "MX: {mx}\r\n"
    "ST: {st}\r\n"
    "\r\n"
)


@dataclass
class SamsungTV:
    """Represents a discovered Samsung TV."""

    ip: str
    port: int
    name: str
    model: str
    location: str
    usn: str
    brand: str = "samsung"

    def __str__(self) -> str:
        return f"{self.name} ({self.model}) at {self.ip}:{self.port}"

    @property
    def ws_endpoint(self) -> str:
        """WebSocket endpoint for the Samsung remote API."""
        return f"ws://{self.ip}:8001/api/v2/channels/samsung.remote.control"

    @property
    def wss_endpoint(self) -> str:
        """Secure WebSocket endpoint (newer TVs, port 8002)."""
        return f"wss://{self.ip}:8002/api/v2/channels/samsung.remote.control"

    @property
    def info_url(self) -> str:
        """REST API info endpoint."""
        return f"http://{self.ip}:8001/api/v2/"


@dataclass
class PhilipsTV:
    """Represents a discovered Philips TV."""

    ip: str
    port: int
    name: str
    model: str
    location: str
    usn: str
    brand: str = "philips"

    def __str__(self) -> str:
        return f"{self.name} ({self.model}) at {self.ip}:{self.port}"

    @property
    def api_url(self) -> str:
        """JointSpace API endpoint (HTTPS)."""
        return f"https://{self.ip}:1926/6"

    @property
    def api_url_http(self) -> str:
        """JointSpace API endpoint (HTTP, older models)."""
        return f"http://{self.ip}:1925/6"

    @property
    def info_url(self) -> str:
        """System info endpoint."""
        return f"https://{self.ip}:1926/6/system"


def _parse_ssdp_response(data: str) -> Optional[dict]:
    """Parse an SSDP response into a header dictionary."""
    headers = {}
    for line in data.split("\r\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            headers[key.strip().upper()] = value.strip()
    return headers if headers else None


def _fetch_device_description(location: str) -> Optional[dict]:
    """Fetch and parse the UPnP device description XML."""
    try:
        resp = requests.get(location, timeout=3)
        resp.raise_for_status()
        root = ElementTree.fromstring(resp.text)

        ns = {"upnp": "urn:schemas-upnp-org:device-1-0"}
        device = root.find(".//upnp:device", ns)
        if device is None:
            return None

        friendly_name = device.findtext("upnp:friendlyName", "", ns)
        model_name = device.findtext("upnp:modelName", "", ns)
        manufacturer = device.findtext("upnp:manufacturer", "", ns)

        return {
            "name": friendly_name,
            "model": model_name,
            "manufacturer": manufacturer,
        }
    except Exception as e:
        logger.debug("Failed to fetch device description from %s: %s", location, e)
        return None


def _get_tv_info_rest(ip: str) -> Optional[dict]:
    """Try the Samsung REST API to get TV info directly."""
    try:
        resp = requests.get(f"http://{ip}:8001/api/v2/", timeout=3)
        resp.raise_for_status()
        data = resp.json()
        device = data.get("device", {})
        return {
            "name": device.get("name", "Samsung TV"),
            "model": device.get("modelName", "Unknown"),
            "ip": device.get("ip", ip),
        }
    except Exception as e:
        logger.debug("REST API not available on %s: %s", ip, e)
        return None


def discover_tvs(timeout: float = SSDP_TIMEOUT) -> list[SamsungTV]:
    """Discover Samsung TVs on the local network via SSDP.

    Sends M-SEARCH multicast messages and collects responses
    from Samsung TV devices.
    """
    found = {}  # keyed by IP to deduplicate

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(timeout)

    for st in SEARCH_TARGETS:
        msg = SSDP_MSEARCH.format(
            addr=SSDP_ADDR, port=SSDP_PORT, mx=3, st=st
        ).encode()
        sock.sendto(msg, (SSDP_ADDR, SSDP_PORT))

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            sock.settimeout(remaining)
            data, addr = sock.recvfrom(4096)
            response = data.decode("utf-8", errors="replace")
            headers = _parse_ssdp_response(response)
            if not headers:
                continue

            ip = addr[0]
            if ip in found:
                continue

            # Check if it's a Samsung device
            server = headers.get("SERVER", "")
            usn = headers.get("USN", "")
            location = headers.get("LOCATION", "")

            is_samsung = "samsung" in server.lower() or "samsung" in usn.lower()

            if location and not is_samsung:
                desc = _fetch_device_description(location)
                if desc and "samsung" in desc.get("manufacturer", "").lower():
                    is_samsung = True

            if not is_samsung:
                continue

            # Get detailed TV info
            info = _get_tv_info_rest(ip)
            if info:
                name = info["name"]
                model = info["model"]
            else:
                desc = _fetch_device_description(location) if location else None
                name = desc.get("name", "Samsung TV") if desc else "Samsung TV"
                model = desc.get("model", "Unknown") if desc else "Unknown"

            # Extract port from location URL
            port_match = re.search(r":(\d+)", location)
            port = int(port_match.group(1)) if port_match else 8001

            tv = SamsungTV(
                ip=ip,
                port=port,
                name=name,
                model=model,
                location=location,
                usn=usn,
            )
            found[ip] = tv
            logger.info("Discovered: %s", tv)

        except socket.timeout:
            break
        except Exception as e:
            logger.debug("Error processing SSDP response: %s", e)

    sock.close()
    return list(found.values())


def find_tv_by_ip(ip: str) -> Optional[SamsungTV]:
    """Try to connect to a Samsung TV at a known IP address."""
    info = _get_tv_info_rest(ip)
    if info:
        return SamsungTV(
            ip=ip,
            port=8001,
            name=info["name"],
            model=info["model"],
            location=f"http://{ip}:8001/",
            usn="",
        )
    return None


def _get_philips_tv_info(ip: str) -> Optional[dict]:
    """Try the Philips JointSpace API to get TV info."""
    # Try HTTPS on 1926 first, then HTTP on 1925
    for scheme, port in [("https", 1926), ("http", 1925)]:
        try:
            resp = requests.get(
                f"{scheme}://{ip}:{port}/6/system",
                timeout=3,
                verify=False,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "name": data.get("name", "Philips TV"),
                "model": data.get("model", data.get("modelname", "Unknown")),
                "ip": ip,
                "port": port,
                "use_ssl": scheme == "https",
            }
        except Exception as e:
            logger.debug("Philips API not available on %s:%d: %s", ip, port, e)
    return None


def find_philips_tv_by_ip(ip: str) -> Optional[PhilipsTV]:
    """Try to connect to a Philips TV at a known IP address."""
    info = _get_philips_tv_info(ip)
    if info:
        return PhilipsTV(
            ip=ip,
            port=info["port"],
            name=info["name"],
            model=info["model"],
            location=f"https://{ip}:{info['port']}/",
            usn="",
        )
    return None


def find_any_tv_by_ip(ip: str):
    """Try to find any supported TV (Samsung or Philips) at a given IP.

    Returns a SamsungTV, PhilipsTV, or None.
    """
    # Try Samsung first (faster check)
    tv = find_tv_by_ip(ip)
    if tv:
        return tv
    # Try Philips
    tv = find_philips_tv_by_ip(ip)
    if tv:
        return tv
    return None


def discover_all_tvs(timeout: float = SSDP_TIMEOUT) -> list:
    """Discover all supported TVs (Samsung and Philips) on the local network.

    Returns a mixed list of SamsungTV and PhilipsTV objects.
    """
    found = {}

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(timeout)

    # Send SSDP searches for all device types
    all_targets = SEARCH_TARGETS + [
        "urn:schemas-upnp-org:device:Basic:1",
        "ssdp:all",
    ]

    for st in all_targets:
        msg = SSDP_MSEARCH.format(
            addr=SSDP_ADDR, port=SSDP_PORT, mx=3, st=st
        ).encode()
        sock.sendto(msg, (SSDP_ADDR, SSDP_PORT))

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            sock.settimeout(remaining)
            data, addr = sock.recvfrom(4096)
            response = data.decode("utf-8", errors="replace")
            headers = _parse_ssdp_response(response)
            if not headers:
                continue

            ip = addr[0]
            if ip in found:
                continue

            server = headers.get("SERVER", "")
            usn = headers.get("USN", "")
            location = headers.get("LOCATION", "")

            # Check Samsung
            is_samsung = "samsung" in server.lower() or "samsung" in usn.lower()
            if location and not is_samsung:
                desc = _fetch_device_description(location)
                if desc and "samsung" in desc.get("manufacturer", "").lower():
                    is_samsung = True

            if is_samsung:
                info = _get_tv_info_rest(ip)
                if info:
                    name = info["name"]
                    model = info["model"]
                else:
                    desc = _fetch_device_description(location) if location else None
                    name = desc.get("name", "Samsung TV") if desc else "Samsung TV"
                    model = desc.get("model", "Unknown") if desc else "Unknown"

                port_match = re.search(r":(\d+)", location)
                port = int(port_match.group(1)) if port_match else 8001

                tv = SamsungTV(
                    ip=ip, port=port, name=name, model=model,
                    location=location, usn=usn,
                )
                found[ip] = tv
                logger.info("Discovered Samsung: %s", tv)
                continue

            # Check Philips
            is_philips = "philips" in server.lower() or "philips" in usn.lower()
            if location and not is_philips:
                desc = _fetch_device_description(location)
                if desc and "philips" in desc.get("manufacturer", "").lower():
                    is_philips = True

            if is_philips:
                info = _get_philips_tv_info(ip)
                if info:
                    tv = PhilipsTV(
                        ip=ip, port=info["port"], name=info["name"],
                        model=info["model"], location=location, usn=usn,
                    )
                    found[ip] = tv
                    logger.info("Discovered Philips: %s", tv)

        except socket.timeout:
            break
        except Exception as e:
            logger.debug("Error processing SSDP response: %s", e)

    sock.close()
    return list(found.values())
