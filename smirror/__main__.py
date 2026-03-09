"""CLI entry point for Smirror - Samsung TV Screen Mirror.

Usage:
    python -m smirror discover          # Find Samsung TVs on the network
    python -m smirror mirror            # Mirror screen to first TV found
    python -m smirror mirror --ip X     # Mirror to a specific TV
    python -m smirror remote --ip X     # Send remote key commands
"""

import argparse
import logging
import sys

from . import __version__


def cmd_discover(args):
    """Discover Samsung TVs on the local network."""
    from .discovery import discover_tvs

    print(f"Scanning for Samsung TVs (timeout: {args.timeout}s)...")
    tvs = discover_tvs(timeout=args.timeout)

    if not tvs:
        print("\nNo Samsung TVs found on the network.")
        print("Tips:")
        print("  - Make sure your computer and TV are on the same WiFi")
        print("  - Hotel WiFi may have device isolation enabled")
        print("  - Try connecting to the TV directly with: smirror mirror --ip <TV_IP>")
        return 1

    print(f"\nFound {len(tvs)} Samsung TV(s):\n")
    for i, tv in enumerate(tvs, 1):
        print(f"  {i}. {tv.name}")
        print(f"     Model: {tv.model}")
        print(f"     IP:    {tv.ip}")
        print(f"     WS:    {tv.ws_endpoint}")
        print()

    return 0


def cmd_mirror(args):
    """Start screen mirroring to a Samsung TV."""
    from .discovery import discover_tvs, find_tv_by_ip
    from .mirror import ScreenMirrorSession

    tv = None

    if args.ip:
        print(f"Connecting to TV at {args.ip}...")
        tv = find_tv_by_ip(args.ip)
        if not tv:
            print(f"Could not reach a Samsung TV at {args.ip}")
            print("Make sure the TV is on and connected to the network.")
            return 1
    else:
        print("Scanning for Samsung TVs...")
        tvs = discover_tvs(timeout=args.timeout)
        if not tvs:
            print("No Samsung TVs found. Use --ip to specify the TV's IP address.")
            return 1
        tv = tvs[0]
        print(f"Found: {tv}")

    session = ScreenMirrorSession(
        tv=tv,
        fps=args.fps,
        quality=args.quality,
        scale=args.scale,
        server_port=args.port,
    )
    session.start()
    return 0


def cmd_remote(args):
    """Send remote control commands to a Samsung TV."""
    from .discovery import find_tv_by_ip
    from .remote import SamsungRemote

    if not args.ip:
        print("Error: --ip is required for remote commands.")
        return 1

    tv = find_tv_by_ip(args.ip)
    if not tv:
        print(f"Could not reach a Samsung TV at {args.ip}")
        return 1

    remote = SamsungRemote(tv)
    if not remote.connect():
        print("Failed to connect. Check if the TV accepted the pairing request.")
        return 1

    if args.key:
        remote.send_key(args.key)
        print(f"Sent key: {args.key}")
    elif args.text:
        remote.send_text(args.text)
        print(f"Sent text input")
    elif args.url:
        remote.open_browser(args.url)
        print(f"Opened URL on TV browser")
    elif args.app:
        remote.open_app(args.app)
        print(f"Launched app: {args.app}")
    else:
        # Interactive mode
        print("Interactive remote mode. Type key names (e.g., KEY_VOLUP) or 'quit'.")
        while True:
            try:
                cmd = input("> ").strip()
                if cmd.lower() in ("quit", "exit", "q"):
                    break
                if cmd.startswith("KEY_"):
                    remote.send_key(cmd)
                    print(f"  Sent: {cmd}")
                else:
                    print(f"  Unknown command. Use KEY_* format (e.g., KEY_VOLUP)")
            except (KeyboardInterrupt, EOFError):
                break

    remote.disconnect()
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="smirror",
        description="Smirror - Samsung TV Screen Mirror",
    )
    parser.add_argument(
        "--version", action="version", version=f"smirror {__version__}"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # discover
    p_discover = subparsers.add_parser("discover", help="Find Samsung TVs on network")
    p_discover.add_argument(
        "--timeout", type=float, default=5.0, help="Discovery timeout in seconds"
    )

    # mirror
    p_mirror = subparsers.add_parser("mirror", help="Mirror screen to a Samsung TV")
    p_mirror.add_argument("--ip", help="TV IP address (skip discovery)")
    p_mirror.add_argument("--fps", type=int, default=15, help="Frames per second")
    p_mirror.add_argument(
        "--quality", type=int, default=70, help="JPEG quality (1-100)"
    )
    p_mirror.add_argument(
        "--scale", type=float, default=1.0, help="Scale factor (0.1-1.0)"
    )
    p_mirror.add_argument(
        "--port", type=int, default=7878, help="Local HTTP server port"
    )
    p_mirror.add_argument(
        "--timeout", type=float, default=5.0, help="Discovery timeout in seconds"
    )

    # remote
    p_remote = subparsers.add_parser("remote", help="Send remote control commands")
    p_remote.add_argument("--ip", required=True, help="TV IP address")
    p_remote.add_argument("--key", help="Key to send (e.g., KEY_VOLUP)")
    p_remote.add_argument("--text", help="Text to type on the TV")
    p_remote.add_argument("--url", help="URL to open in TV browser")
    p_remote.add_argument("--app", help="App ID to launch")

    args = parser.parse_args()

    # Set up logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "discover": cmd_discover,
        "mirror": cmd_mirror,
        "remote": cmd_remote,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main() or 0)
