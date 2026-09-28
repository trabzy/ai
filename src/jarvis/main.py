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

    if args.voice:
        config.voice_enabled = True

    jarvis = Jarvis(config)

    if args.once:
        print(jarvis.handle_message(args.once))
        return

    if config.voice_enabled:
        jarvis.run_voice_loop()
    else:
        jarvis.run_text_loop()


if __name__ == "__main__":
    main()
