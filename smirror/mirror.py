"""Screen capture and streaming to Samsung TV.

Captures the local screen, encodes frames as JPEG, and streams
them to the TV via its media rendering capabilities.
"""

import base64
import io
import json
import logging
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

from PIL import ImageGrab, Image

from .discovery import SamsungTV
from .remote import SamsungRemote

logger = logging.getLogger(__name__)

# Default settings
DEFAULT_FPS = 15
DEFAULT_QUALITY = 70
DEFAULT_SCALE = 1.0


class FrameBuffer:
    """Thread-safe buffer holding the latest captured frame."""

    def __init__(self):
        self._frame: Optional[bytes] = None
        self._lock = threading.Lock()

    def update(self, frame: bytes):
        with self._lock:
            self._frame = frame

    def get(self) -> Optional[bytes]:
        with self._lock:
            return self._frame


class MJPEGHandler(BaseHTTPRequestHandler):
    """HTTP handler that serves an MJPEG stream from the frame buffer."""

    frame_buffer: FrameBuffer = None  # Set by the server

    def do_GET(self):
        if self.path == "/stream":
            self._serve_mjpeg()
        elif self.path == "/frame":
            self._serve_single_frame()
        elif self.path == "/":
            self._serve_player_page()
        else:
            self.send_error(404)

    def _serve_mjpeg(self):
        self.send_response(200)
        boundary = "frameboundary"
        self.send_header(
            "Content-Type", f"multipart/x-mixed-replace; boundary={boundary}"
        )
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Connection", "close")
        self.end_headers()

        try:
            while True:
                frame = self.frame_buffer.get()
                if frame:
                    self.wfile.write(f"--{boundary}\r\n".encode())
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(
                        f"Content-Length: {len(frame)}\r\n\r\n".encode()
                    )
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
                time.sleep(1 / 30)  # Cap at 30fps delivery
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _serve_single_frame(self):
        frame = self.frame_buffer.get()
        if frame:
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(frame)))
            self.end_headers()
            self.wfile.write(frame)
        else:
            self.send_error(503, "No frame available yet")

    def _serve_player_page(self):
        """Serve an HTML page with a full-screen MJPEG viewer."""
        html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Smirror - Screen Mirror</title>
    <style>
        * { margin: 0; padding: 0; }
        body { background: #000; overflow: hidden; }
        img {
            width: 100vw;
            height: 100vh;
            object-fit: contain;
        }
    </style>
</head>
<body>
    <img src="/stream" alt="Screen Mirror">
</body>
</html>"""
        encoded = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args):
        # Suppress default request logging
        pass


class ScreenCapturer:
    """Captures the screen at a target FPS and stores JPEG frames."""

    def __init__(
        self,
        frame_buffer: FrameBuffer,
        fps: int = DEFAULT_FPS,
        quality: int = DEFAULT_QUALITY,
        scale: float = DEFAULT_SCALE,
    ):
        self.frame_buffer = frame_buffer
        self.fps = fps
        self.quality = quality
        self.scale = scale
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def _capture_loop(self):
        interval = 1.0 / self.fps
        while self._running:
            start = time.monotonic()
            try:
                screenshot = ImageGrab.grab()

                if self.scale != 1.0:
                    new_size = (
                        int(screenshot.width * self.scale),
                        int(screenshot.height * self.scale),
                    )
                    screenshot = screenshot.resize(new_size, Image.LANCZOS)

                buf = io.BytesIO()
                screenshot.save(buf, format="JPEG", quality=self.quality)
                self.frame_buffer.update(buf.getvalue())

            except Exception as e:
                logger.error("Screen capture error: %s", e)

            elapsed = time.monotonic() - start
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def start(self):
        """Start capturing in a background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info(
            "Screen capture started (fps=%d, quality=%d, scale=%.1f)",
            self.fps,
            self.quality,
            self.scale,
        )

    def stop(self):
        """Stop the capture thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        logger.info("Screen capture stopped.")


def _get_local_ip() -> str:
    """Get the local IP address that's routable on the LAN."""
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


class ScreenMirrorSession:
    """Manages a complete screen mirroring session.

    1. Starts local screen capture
    2. Starts an MJPEG HTTP server
    3. Opens the TV's browser to the MJPEG stream
    """

    def __init__(
        self,
        tv: SamsungTV,
        fps: int = DEFAULT_FPS,
        quality: int = DEFAULT_QUALITY,
        scale: float = DEFAULT_SCALE,
        server_port: int = 7878,
    ):
        self.tv = tv
        self.fps = fps
        self.quality = quality
        self.scale = scale
        self.server_port = server_port

        self._frame_buffer = FrameBuffer()
        self._capturer = ScreenCapturer(
            self._frame_buffer, fps=fps, quality=quality, scale=scale
        )
        self._server: Optional[HTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None

    def _start_server(self):
        """Start the MJPEG HTTP server."""
        MJPEGHandler.frame_buffer = self._frame_buffer

        self._server = HTTPServer(("0.0.0.0", self.server_port), MJPEGHandler)
        self._server_thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )
        self._server_thread.start()

        local_ip = _get_local_ip()
        logger.info(
            "MJPEG server running at http://%s:%d/",
            local_ip,
            self.server_port,
        )
        return local_ip

    def start(self):
        """Start the screen mirror session.

        - Captures screen locally
        - Serves MJPEG stream over HTTP
        - Opens the TV browser to display the stream
        """
        # Start screen capture
        self._capturer.start()

        # Start HTTP server
        local_ip = self._start_server()

        # Wait a moment for first frame
        time.sleep(0.5)

        stream_url = f"http://{local_ip}:{self.server_port}/"

        # Connect to TV and open the browser
        remote = SamsungRemote(self.tv)
        if remote.connect():
            logger.info("Opening stream on TV browser...")
            remote.open_browser(stream_url)
            remote.disconnect()
            print(f"\nMirroring started!")
            print(f"  Stream URL: {stream_url}")
            print(f"  TV: {self.tv}")
            print(f"  FPS: {self.fps}, Quality: {self.quality}")
            print(f"\nPress Ctrl+C to stop.\n")
        else:
            print(f"\nCould not auto-open on TV. Open this URL on the TV manually:")
            print(f"  {stream_url}")
            print(f"\nThe MJPEG stream is running. Press Ctrl+C to stop.\n")

        # Block until interrupted
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        """Stop the mirror session and clean up."""
        print("\nStopping mirror session...")
        self._capturer.stop()
        if self._server:
            self._server.shutdown()
        logger.info("Mirror session ended.")
