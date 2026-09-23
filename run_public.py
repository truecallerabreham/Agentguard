"""AgentGuard Public Server & Tunnel Launcher.

Launches the AgentGuard SaaS Web Server and optionally opens a secure public HTTPS
tunnel via localtunnel or cloudflared so anyone on the internet can test the platform.

Usage:
    python run_public.py [--port 8080] [--no-tunnel]
"""

from __future__ import annotations
import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
import uvicorn

from agentguard.config import get_settings
from agentguard.server import build_http_app


def start_server(host: str, port: int):
    """Run the Uvicorn ASGI server."""
    app = build_http_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


def main():
    parser = argparse.ArgumentParser(description="Run AgentGuard public SaaS platform.")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind (default: 8080)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--no-tunnel", action="store_true", help="Disable public HTTPS tunnel")
    args = parser.parse_args()

    port = int(os.getenv("PORT", args.port))
    host = os.getenv("HOST", args.host)

    print("=" * 78)
    print("  🛡️  AGENTGUARD — AUTONOMOUS E-COMMERCE CUSTOMER SUPPORT PLATFORM")
    print("=" * 78)
    print(f"\n  [LOCAL ACCESS]")
    print(f"  • SaaS Landing Page:     http://localhost:{port}/")
    print(f"  • Merchant Dashboard:    http://localhost:{port}/dashboard")
    print(f"  • Customer Store Demo:   http://localhost:{port}/store?store_id=demo-store")
    print(f"  • Embed Widget Script:   http://localhost:{port}/widget.js")
    print(f"  • API Health Probe:      http://localhost:{port}/healthz\n")

    # Start Uvicorn in background thread
    server_thread = threading.Thread(target=start_server, args=(host, port), daemon=True)
    server_thread.start()

    # Give server a moment to bind
    time.sleep(1.5)

    # Launch tunnel if requested and available
    tunnel_proc = None
    if not args.no_tunnel:
        npx_bin = shutil.which("npx") or shutil.which("npx.cmd")
        cloudflared_bin = shutil.which("cloudflared") or shutil.which("cloudflared.exe")

        if cloudflared_bin:
            print("  [PUBLIC INTERNET ACCESS] Starting Cloudflare Tunnel...")
            try:
                tunnel_proc = subprocess.Popen(
                    [cloudflared_bin, "tunnel", "--url", f"http://127.0.0.1:{port}"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                print("  Tunnel launching... check console for public https://*.trycloudflare.com link.")
            except Exception as e:
                print(f"  Failed to start cloudflared: {e}")
        elif npx_bin:
            print("  [PUBLIC INTERNET ACCESS] Starting Localtunnel via npx...")
            print("  Generating instant public HTTPS URL for sharing with testers...\n")
            try:
                tunnel_proc = subprocess.Popen(
                    [npx_bin, "--yes", "localtunnel", "--port", str(port)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )

                def log_tunnel(proc):
                    for line in iter(proc.stdout.readline, ""):
                        if not line:
                            break
                        if "url is:" in line.lower() or "https://" in line:
                            print(f"\n  🎉 SHAREABLE PUBLIC URL: {line.strip()}")
                            print(f"  Share with anyone: {line.strip().replace('your url is: ', '')}\n")
                        else:
                            print(f"  [tunnel] {line.strip()}")

                t = threading.Thread(target=log_tunnel, args=(tunnel_proc,), daemon=True)
                t.start()
            except Exception as e:
                print(f"  Failed to start localtunnel: {e}")
        else:
            print("  [NOTE] Neither 'cloudflared' nor 'npx' found for automatic tunneling.")
            print(f"  You can use ngrok: ngrok http {port}")

    print("-" * 78)
    print("  Server is RUNNING. Press Ctrl+C to terminate.")
    print("-" * 78)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping AgentGuard server and tunnels...")
        if tunnel_proc:
            tunnel_proc.terminate()
        sys.exit(0)


if __name__ == "__main__":
    main()
