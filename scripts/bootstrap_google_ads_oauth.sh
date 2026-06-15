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

echo "Opening Google OAuth in your browser. Sign into the account that manages the target Google Ads account."
gcloud auth application-default login \
  --client-id-file="$CLIENT_FILE" \
  --scopes="$SCOPES"

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

gads auth-check
