#!/usr/bin/env python3
"""
chop_monitor.py — Live ASCII bar display for a TouchDesigner CHOP.

Polls GET /chop?path=<chop> on the MCP WebServer DAT.
"Full" on each bar = highest observed absolute value for that channel.

Usage:
    python chop_monitor.py
    python chop_monitor.py --chop /path/to/chop --rate 20 --port 9980
"""

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

BAR_WIDTH  = 36
FULL_CHAR  = '\u2588'   # █
EMPTY_CHAR = '\u2591'   # ░
PEAK_CHAR  = '\u258a'   # ▊  (marks the peak position)


def fetch_chop(host: str, port: int, chop_path: str) -> dict:
    url = f"http://{host}:{port}/chop?path={urllib.parse.quote(chop_path)}"
    with urllib.request.urlopen(url, timeout=2) as resp:
        return json.loads(resp.read().decode())


def render_bar(value: float, max_val: float, width: int = BAR_WIDTH) -> tuple[str, float]:
    ratio = max(0.0, min(1.0, abs(value) / max_val)) if max_val != 0 else 0.0
    filled = round(ratio * width)
    bar = FULL_CHAR * filled + EMPTY_CHAR * (width - filled)
    return bar, ratio


def clear():
    os.system('cls' if os.name == 'nt' else 'clear')


def main():
    parser = argparse.ArgumentParser(description='Live ASCII bar display for a TD CHOP')
    parser.add_argument('--host',  default='localhost')
    parser.add_argument('--port',  type=int,   default=9980)
    parser.add_argument('--chop',  default='/ascii_UI', help='Operator path in TD')
    parser.add_argument('--rate',  type=float, default=10.0, help='Poll rate in Hz')
    parser.add_argument('--reset', action='store_true',  help='Reset peak tracking each run')
    args = parser.parse_args()

    interval = 1.0 / max(args.rate, 0.1)
    maximums: dict[str, float] = defaultdict(float)
    last_error = ''
    frame = 0

    while True:
        t0 = time.monotonic()
        frame += 1

        try:
            data     = fetch_chop(args.host, args.port, args.chop)
            channels = data.get('channels', {})
            td_rate  = data.get('rate', '?')
            n_samp   = data.get('numSamples', '?')
            last_error = ''

            for name, val in channels.items():
                if abs(val) > maximums[name]:
                    maximums[name] = abs(val)

            clear()

            ruler = '\u2500' * (BAR_WIDTH + 38)
            name_w = max((len(n) for n in channels), default=6)
            name_w = max(name_w, 6)

            print(f" CHOP Monitor  \u2502  {args.chop}  \u2502  {td_rate} Hz  {n_samp} samples")
            print(f" {ruler}")
            print(f"  {'CHANNEL':<{name_w}}  {'VALUE':>10}  {'BAR':<{BAR_WIDTH+2}}  {'%':>5}  PEAK")
            print(f" {ruler}")

            if not channels:
                print("  (no channels — CHOP may be empty or cooking)")
            else:
                for name, val in sorted(channels.items()):
                    mx  = maximums[name]
                    bar, ratio = render_bar(val, mx)
                    peak_str = f"{mx:.4f}"
                    sign = '+' if val >= 0 else '-'
                    print(f"  {name:<{name_w}}  {sign}{abs(val):>9.4f}  [{bar}]  {ratio*100:>4.1f}%  {peak_str}")

            print(f" {ruler}")
            spinner = '|/-\\'[frame % 4]
            print(f"  {spinner}  poll {args.rate:.0f} Hz  \u2502  {len(channels)} ch  \u2502  peak resets on --reset flag")

        except urllib.error.URLError as e:
            last_error = f"Connection error: {e.reason}"
            clear()
            print(f" CHOP Monitor  \u2502  {args.chop}")
            print(f"  {last_error}")
            print("  Waiting for WebServer DAT on port 9980...")
        except Exception as e:
            last_error = str(e)
            clear()
            print(f" CHOP Monitor  \u2502  {args.chop}")
            print(f"  Error: {last_error}")

        elapsed = time.monotonic() - t0
        wait = interval - elapsed
        if wait > 0:
            time.sleep(wait)


if __name__ == '__main__':
    main()
