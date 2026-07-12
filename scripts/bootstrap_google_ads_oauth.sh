#!/usr/bin/env bash
set -euo pipefail

SCOPES="openid,https://www.googleapis.com/auth/userinfo.email,https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/adwords"
ADS_SCOPE="https://www.googleapis.com/auth/adwords"
CONFIG_DIR="${GOOGLE_ADS_CLI_CONFIG_DIR:-${GOOGLE_ADS_CLI_HOME:-$HOME/.google-ads-cli}}"
DEFAULT_CLIENT_FILE="$CONFIG_DIR/google-ads-oauth-client.json"
CLIENT_FILE="${GOOGLE_ADS_OAUTH_CLIENT_FILE:-$DEFAULT_CLIENT_FILE}"

if [ ! -f "$CLIENT_FILE" ]; then
  cat >&2 <<MSG
Missing OAuth client JSON:
  $CLIENT_FILE

Create it in Google Cloud Console:
  APIs & Services -> Credentials -> Create Credentials -> OAuth client ID -> Desktop app

If the OAuth consent screen is in Testing, add your Google account as a test user.
Then download the JSON and save it at the path above.
MSG
  exit 64
fi

store_adc_credentials() {
  export GOOGLE_ADS_NEW_ACCESS_TOKEN
  GOOGLE_ADS_NEW_ACCESS_TOKEN="$(gcloud auth application-default print-access-token --scopes="$ADS_SCOPE")"

  python3 - <<'PY'
import json
import os
from pathlib import Path

adc_path = Path.home() / ".config/gcloud/application_default_credentials.json"
adc = json.loads(adc_path.read_text())

values = {
    "GOOGLE_ADS_ACCESS_TOKEN": os.environ["GOOGLE_ADS_NEW_ACCESS_TOKEN"],
    "GOOGLE_ADS_CLIENT_ID": adc.get("client_id", ""),
    "GOOGLE_ADS_CLIENT_SECRET": adc.get("client_secret", ""),
    "GOOGLE_ADS_REFRESH_TOKEN": adc.get("refresh_token", ""),
}

config_dir = Path(os.environ.get("GOOGLE_ADS_CLI_CONFIG_DIR") or os.environ.get("GOOGLE_ADS_CLI_HOME") or Path.home() / ".google-ads-cli")

for env_path in [config_dir / ".env"]:
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    seen = set()
    out = []
    for line in lines:
        key = line.split("=", 1)[0].replace("export ", "").strip() if "=" in line else ""
        if key in values:
            out.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in values.items():
        if key not in seen:
            out.append(f"{key}={value}")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(out).rstrip() + "\n")
    env_path.chmod(0o600)

print("Stored Google Ads OAuth access and refresh credentials.")
PY
}

run_python_loopback_oauth() {
  export GOOGLE_ADS_OAUTH_CLIENT_FILE="$CLIENT_FILE"
  export GOOGLE_ADS_OAUTH_SCOPES="$SCOPES"
  export GOOGLE_ADS_OAUTH_TIMEOUT_SECONDS="${GOOGLE_ADS_OAUTH_TIMEOUT_SECONDS:-300}"

  python3 - <<'PY'
import json
import os
import secrets
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

client_path = Path(os.environ["GOOGLE_ADS_OAUTH_CLIENT_FILE"])
client_doc = json.loads(client_path.read_text())
client_type = "web" if "web" in client_doc else "installed" if "installed" in client_doc else "unknown"
client_cfg = client_doc.get("installed") or client_doc.get("web") or client_doc
client_id = client_cfg.get("client_id")
client_secret = client_cfg.get("client_secret")
if not client_id or not client_secret:
    raise SystemExit(f"{client_path}: expected OAuth client_id and client_secret")

timeout = int(os.environ.get("GOOGLE_ADS_OAUTH_TIMEOUT_SECONDS") or "300")
port = int(os.environ.get("GOOGLE_ADS_OAUTH_PORT") or "0")
bind_host = os.environ.get("GOOGLE_ADS_OAUTH_BIND_HOST") or "127.0.0.1"
redirect_uri_override = os.environ.get("GOOGLE_ADS_OAUTH_REDIRECT_URI")
if redirect_uri_override and "localhost" not in redirect_uri_override and "127.0.0.1" not in redirect_uri_override and client_type != "web":
    raise SystemExit(
        "Tailscale/non-localhost OAuth redirect requires a Web OAuth client JSON. "
        f"{client_path} is {client_type}. Create a Web client with authorized redirect URI "
        f"{redirect_uri_override}, then set GOOGLE_ADS_OAUTH_CLIENT_FILE to that JSON."
    )
open_browser = os.environ.get("GOOGLE_ADS_OAUTH_OPEN_BROWSER", "auto").lower()
headless_session = bool(os.environ.get("SSH_CONNECTION")) and not (
    os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
)
state = secrets.token_urlsafe(24)
result: dict[str, str] = {}

class OAuthHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if query.get("state", [""])[0] != state:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"State mismatch. Return to the terminal and retry.")
            result["error"] = "state mismatch"
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if "error" in query:
            result["error"] = query["error"][0]
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Google OAuth returned an error. Return to the terminal.")
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        code = query.get("code", [""])[0]
        if not code:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing authorization code. Return to the terminal and retry.")
            result["error"] = "missing code"
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        result["code"] = code
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Google Ads OAuth complete. You can close this tab.")
        threading.Thread(target=self.server.shutdown, daemon=True).start()

server = HTTPServer((bind_host, port), OAuthHandler)
redirect_uri = redirect_uri_override or f"http://127.0.0.1:{server.server_port}/"
scopes = os.environ["GOOGLE_ADS_OAUTH_SCOPES"].replace(",", " ")
auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(
    {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scopes,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
)

print("Google OAuth URL:")
print(auth_url)
print()
print(f"Waiting for OAuth callback on {redirect_uri} for up to {timeout}s.")
print(f"Local callback listener: http://{bind_host}:{server.server_port}/")
if headless_session:
    if redirect_uri_override:
        print("Remote SSH detected. Using explicit redirect URI override; make sure it routes to the local callback listener.")
    else:
        print(
            "Remote SSH detected. Open the URL in a real browser only if this port is forwarded "
            f"back to this machine, for example: ssh -L {server.server_port}:127.0.0.1:{server.server_port} <host>"
        )
should_open = open_browser in {"1", "true", "yes"} or (
    open_browser == "auto" and not headless_session
)
if should_open:
    try:
        opened = webbrowser.open(auth_url)
        if not opened and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            subprocess.run(["xdg-open", auth_url], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
thread.join(timeout)
server.server_close()
if "code" not in result:
    raise SystemExit(f"OAuth did not complete within {timeout}s: {result.get('error') or 'no callback received'}")

payload = urllib.parse.urlencode(
    {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": result["code"],
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
).encode("utf-8")
req = urllib.request.Request(
    "https://oauth2.googleapis.com/token",
    data=payload,
    method="POST",
    headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
)
with urllib.request.urlopen(req, timeout=30) as response:
    token_body = json.loads(response.read().decode("utf-8"))

refresh_token = token_body.get("refresh_token")
if not refresh_token:
    raise SystemExit("OAuth token response did not include refresh_token; revoke the prior grant or retry with prompt=consent.")

values = {
    "GOOGLE_ADS_ACCESS_TOKEN": token_body["access_token"],
    "GOOGLE_ADS_CLIENT_ID": client_id,
    "GOOGLE_ADS_CLIENT_SECRET": client_secret,
    "GOOGLE_ADS_REFRESH_TOKEN": refresh_token,
}

config_dir = Path(os.environ.get("GOOGLE_ADS_CLI_CONFIG_DIR") or os.environ.get("GOOGLE_ADS_CLI_HOME") or Path.home() / ".google-ads-cli")
env_path = config_dir / ".env"
lines = env_path.read_text().splitlines() if env_path.exists() else []
seen = set()
out = []
for line in lines:
    key = line.split("=", 1)[0].replace("export ", "").strip() if "=" in line else ""
    if key in values:
        out.append(f"{key}={values[key]}")
        seen.add(key)
    else:
        out.append(line)
for key, value in values.items():
    if key not in seen:
        out.append(f"{key}={value}")
env_path.parent.mkdir(parents=True, exist_ok=True)
env_path.write_text("\n".join(out).rstrip() + "\n")
env_path.chmod(0o600)
print("Stored Google Ads OAuth access and refresh credentials.")
PY
}

if command -v gcloud >/dev/null 2>&1; then
  echo "Opening Google OAuth in your browser. Sign into the account that manages the target Google Ads account."
  gcloud auth application-default login \
    --client-id-file="$CLIENT_FILE" \
    --scopes="$SCOPES"
  store_adc_credentials
else
  echo "gcloud not found; using local Python OAuth loopback fallback."
  run_python_loopback_oauth
fi

gads auth-check
