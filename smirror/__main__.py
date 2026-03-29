"""CLI entry point for Smirror - Smart TV Screen Mirror.

Usage:
    python -m smirror discover          # Find Samsung/Philips TVs on the network
    python -m smirror mirror            # Mirror screen to first TV found
    python -m smirror mirror --ip X     # Mirror to a specific TV
    python -m smirror remote --ip X     # Send remote key commands
    python -m smirror pair --ip X       # Pair with a Philips TV (PIN-based)
"""

import argparse
import logging
import sys

from . import __version__


def cmd_discover(args):
    """Discover Samsung and Philips TVs on the local network."""
    from .discovery import discover_tvs, discover_all_tvs

    print(f"Scanning for Smart TVs (timeout: {args.timeout}s)...")
    tvs = discover_all_tvs(timeout=args.timeout)

    if not tvs:
        print("\nNo Smart TVs found on the network.")
        print("Tips:")
        print("  - Make sure your computer and TV are on the same WiFi")
        print("  - Hotel WiFi may have device isolation enabled")
        print("  - Try connecting directly with: smirror mirror --ip <TV_IP>")
        print("  - For Philips TVs, try: smirror remote --ip <TV_IP> --type philips")
        return 1

    print(f"\nFound {len(tvs)} TV(s):\n")
    for i, tv in enumerate(tvs, 1):
        brand = getattr(tv, 'brand', 'unknown').capitalize()
        print(f"  {i}. [{brand}] {tv.name}")
        print(f"     Model: {tv.model}")
        print(f"     IP:    {tv.ip}")
        if hasattr(tv, 'ws_endpoint'):
            print(f"     WS:    {tv.ws_endpoint}")
        if hasattr(tv, 'api_url'):
            print(f"     API:   {tv.api_url}")
        print()

    return 0


def cmd_mirror(args):
    """Start screen mirroring to a Smart TV."""
    from .discovery import discover_all_tvs, find_any_tv_by_ip, find_tv_by_ip, find_philips_tv_by_ip
    from .mirror import ScreenMirrorSession

    tv = None

    if args.ip:
        print(f"Connecting to TV at {args.ip}...")
        if args.type == "philips":
            tv = find_philips_tv_by_ip(args.ip)
            if not tv:
                print(f"Could not reach a Philips TV at {args.ip}")
                return 1
        elif args.type == "samsung":
            tv = find_tv_by_ip(args.ip)
            if not tv:
                print(f"Could not reach a Samsung TV at {args.ip}")
                return 1
        else:
            tv = find_any_tv_by_ip(args.ip)
            if not tv:
                print(f"Could not reach a Smart TV at {args.ip}")
                print("Try specifying --type samsung or --type philips")
                return 1
        print(f"Found: {tv}")
    else:
        print("Scanning for Smart TVs...")
        tvs = discover_all_tvs(timeout=args.timeout)
        if not tvs:
            print("No Smart TVs found. Use --ip to specify the TV's IP address.")
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
    """Send remote control commands to a Smart TV."""
    from .discovery import find_tv_by_ip, find_philips_tv_by_ip, find_any_tv_by_ip, PhilipsTV

    if not args.ip:
        print("Error: --ip is required for remote commands.")
        return 1

    # Determine TV type
    if args.type == "philips":
        tv = find_philips_tv_by_ip(args.ip)
        if not tv:
            print(f"Could not reach a Philips TV at {args.ip}")
            return 1
    elif args.type == "samsung":
        tv = find_tv_by_ip(args.ip)
        if not tv:
            print(f"Could not reach a Samsung TV at {args.ip}")
            return 1
    else:
        tv = find_any_tv_by_ip(args.ip)
        if not tv:
            print(f"Could not reach a Smart TV at {args.ip}")
            print("Try specifying --type samsung or --type philips")
            return 1

    is_philips = isinstance(tv, PhilipsTV)

    if is_philips:
        from .philips_remote import PhilipsRemote
        remote = PhilipsRemote(tv.ip, port=tv.port)
        if not remote.connect():
            print("Failed to connect to Philips TV.")
            print("You may need to pair first: smirror pair --ip " + args.ip)
            return 1
    else:
        from .remote import SamsungRemote
        remote = SamsungRemote(tv)
        if not remote.connect():
            print("Failed to connect. Check if the TV accepted the pairing request.")
            return 1

    brand = "Philips" if is_philips else "Samsung"
    print(f"Connected to {brand} TV: {tv}")

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
        if is_philips:
            print("Interactive remote mode. Type key names (e.g., VolumeUp, CursorUp) or 'quit'.")
            print("Philips keys: VolumeUp, VolumeDown, Mute, CursorUp, CursorDown,")
            print("  CursorLeft, CursorRight, Confirm, Back, Home, Standby,")
            print("  ChannelStepUp, ChannelStepDown, Play, Pause, Stop")
        else:
            print("Interactive remote mode. Type key names (e.g., KEY_VOLUP) or 'quit'.")

        while True:
            try:
                cmd = input("> ").strip()
                if cmd.lower() in ("quit", "exit", "q"):
                    break
                if is_philips:
                    # Accept both Philips and Samsung-style keys
                    remote.send_key(cmd)
                    print(f"  Sent: {cmd}")
                elif cmd.startswith("KEY_"):
                    remote.send_key(cmd)
                    print(f"  Sent: {cmd}")
                else:
                    print(f"  Unknown command. Use KEY_* format (e.g., KEY_VOLUP)")
            except (KeyboardInterrupt, EOFError):
                break

    remote.disconnect()
    return 0


def cmd_pair(args):
    """Pair with a Philips TV using PIN-based authentication."""
    from .philips_remote import PhilipsRemote

    if not args.ip:
        print("Error: --ip is required for pairing.")
        return 1

    print(f"Starting pairing with Philips TV at {args.ip}...")
    remote = PhilipsRemote(args.ip)

    # Step 1: Send pairing request
    result = remote.pair_request()
    if not result:
        print("Failed to send pairing request. Is the TV on and reachable?")
        return 1

    print("\nA PIN code should appear on the TV screen.")

    # Step 2: Get PIN from user
    try:
        pin = input("Enter the PIN shown on the TV: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nPairing cancelled.")
        return 1

    if not pin:
        print("No PIN entered. Pairing cancelled.")
        return 1

    # Step 3: Complete pairing
    auth_data = result.get("auth_key", "")
    timestamp = result.get("timestamp", "")

    if remote.pair_grant(pin, timestamp, auth_data):
        print(f"\nPairing successful!")
        print(f"  Device ID: {remote.device_id}")
        print(f"  Auth Key:  {remote.auth_key}")
        print(f"\nSave these for future connections:")
        print(f"  smirror remote --ip {args.ip} --type philips")
        return 0
    else:
        print("Pairing failed. Check that the PIN was correct.")
        return 1


def main():
    parser = argparse.ArgumentParser(
        prog="smirror",
        description="Smirror - Smart TV Screen Mirror (Samsung & Philips)",
    )
    parser.add_argument(
        "--version", action="version", version=f"smirror {__version__}"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # discover
    p_discover = subparsers.add_parser("discover", help="Find Smart TVs on network")
    p_discover.add_argument(
        "--timeout", type=float, default=5.0, help="Discovery timeout in seconds"
    )

    # mirror
    p_mirror = subparsers.add_parser("mirror", help="Mirror screen to a Smart TV")
    p_mirror.add_argument("--ip", help="TV IP address (skip discovery)")
    p_mirror.add_argument(
        "--type", choices=["samsung", "philips", "auto"], default="auto",
        help="TV brand (default: auto-detect)"
    )
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
    p_remote.add_argument(
        "--type", choices=["samsung", "philips", "auto"], default="auto",
        help="TV brand (default: auto-detect)"
    )
    p_remote.add_argument("--key", help="Key to send (e.g., KEY_VOLUP or VolumeUp)")
    p_remote.add_argument("--text", help="Text to type on the TV")
    p_remote.add_argument("--url", help="URL to open in TV browser")
    p_remote.add_argument("--app", help="App ID/package to launch")

    # pair (Philips)
    p_pair = subparsers.add_parser("pair", help="Pair with a Philips TV (PIN-based)")
    p_pair.add_argument("--ip", required=True, help="TV IP address")

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
        "pair": cmd_pair,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main() or 0)
