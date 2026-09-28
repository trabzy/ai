"""CLI entry point for Jarvis."""

from __future__ import annotations

import argparse
import sys

from .assistant import Jarvis
from .config import ConfigError, JarvisConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Jarvis - a Claude-powered voice/text assistant")
    parser.add_argument(
        "--voice",
        action="store_true",
        help="Run in voice mode (requires a microphone and the 'voice' extra)",
    )
    parser.add_argument(
        "--hud",
        action="store_true",
        help="Launch the holographic web HUD in your browser",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HUD host to bind (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="HUD port (default 8765)")
    parser.add_argument("--no-browser", action="store_true", help="Don't open a browser tab for the HUD")
    parser.add_argument(
        "--protocol",
        help="Working protocol for text/voice mode: jarvis, strategist, solver, engineer, ideas, redteam",
    )
    parser.add_argument(
        "--once",
        metavar="MESSAGE",
        help="Send a single message and print the reply, then exit (useful for scripting)",
    )
    args = parser.parse_args()

    try:
        config = JarvisConfig.from_env()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.hud:
        from .server import serve

        serve(config, host=args.host, port=args.port, open_browser=not args.no_browser)
        return

    if args.voice:
        config.voice_enabled = True

    jarvis = Jarvis(config)
    jarvis.protocol = args.protocol

    if args.once:
        print(jarvis.handle_message(args.once))
        return

    if config.voice_enabled:
        jarvis.run_voice_loop()
    else:
        jarvis.run_text_loop()


if __name__ == "__main__":
    main()


def hud() -> None:
    """Entry point for the ``jarvis-hud`` command."""
    import sys as _sys

    _sys.argv.insert(1, "--hud")
    main()
