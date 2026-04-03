#!/usr/bin/env python3
"""Tiny HTTP server that records audio via pw-record on the RPi.

Chromium on RPi can't access the EMEET mic through getUserMedia,
but pw-record (PipeWire native) works perfectly. This server
bridges the gap: the browser JS POSTs to localhost:9099/record,
this server runs pw-record, and returns the WAV bytes.

Usage: python3 mic_server.py [--port 9099]
"""

import subprocess
import tempfile
import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


def find_emeet_target():
    """Find the EMEET PipeWire source node ID."""
    try:
        result = subprocess.run(
            ["pactl", "list", "sources", "short"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.strip().split("\n"):
            parts = line.split("\t")
            if len(parts) >= 2 and "emeet" in line.lower() and "monitor" not in line.lower():
                return parts[0].strip()  # node ID
    except Exception as e:
        print(f"[mic] Error finding EMEET: {e}")
    return None


EMEET_TARGET = None


class MicHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def do_POST(self):
        global EMEET_TARGET
        path = urlparse(self.path).path

        if path == "/record":
            # Read duration from query or body
            query = parse_qs(urlparse(self.path).query)
            duration = int(query.get("duration", [5])[0])
            duration = min(max(duration, 1), 30)  # clamp 1-30s

            # Find EMEET target if not cached
            if not EMEET_TARGET:
                EMEET_TARGET = find_emeet_target()

            if not EMEET_TARGET:
                self.send_response(500)
                self._cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "EMEET mic not found"}).encode())
                return

            # Record via pw-record
            try:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    tmp_path = f.name

                print(f"[mic] Recording {duration}s from target {EMEET_TARGET}...")
                proc = subprocess.run(
                    ["pw-record", f"--target={EMEET_TARGET}", tmp_path],
                    timeout=duration + 2,
                    capture_output=True,
                )
            except subprocess.TimeoutExpired:
                pass  # Expected — pw-record runs until killed
            except Exception as e:
                self.send_response(500)
                self._cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
                return

            # Read and return the WAV file
            try:
                with open(tmp_path, "rb") as f:
                    wav_data = f.read()
                os.unlink(tmp_path)

                if len(wav_data) <= 44:
                    self.send_response(500)
                    self._cors_headers()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "No audio captured"}).encode())
                    return

                print(f"[mic] Captured {len(wav_data)} bytes")
                self.send_response(200)
                self._cors_headers()
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(wav_data)))
                self.end_headers()
                self.wfile.write(wav_data)

            except Exception as e:
                self.send_response(500)
                self._cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(404)
            self._cors_headers()
            self.end_headers()

    def do_GET(self):
        """Health check."""
        if urlparse(self.path).path == "/health":
            global EMEET_TARGET
            if not EMEET_TARGET:
                EMEET_TARGET = find_emeet_target()
            status = {"ok": EMEET_TARGET is not None, "target": EMEET_TARGET}
            self.send_response(200)
            self._cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(status).encode())
        else:
            self.send_response(404)
            self._cors_headers()
            self.end_headers()

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, format, *args):
        print(f"[mic] {args[0]}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9099)
    args = parser.parse_args()

    EMEET_TARGET = find_emeet_target()
    if EMEET_TARGET:
        print(f"[mic] EMEET found: target={EMEET_TARGET}")
    else:
        print("[mic] WARNING: EMEET not found, will retry on first request")

    server = HTTPServer(("0.0.0.0", args.port), MicHandler)
    print(f"[mic] Mic server listening on port {args.port}")
    server.serve_forever()
