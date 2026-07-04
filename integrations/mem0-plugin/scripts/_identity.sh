# Source this file. Sets MEM0_API_KEY, MEM0_RESOLVED_USER_ID, and settings.
#
# API key resolution (first non-empty wins):
#   1. MEM0_API_KEY env var (explicit / shell profile)
#   2. CLAUDE_PLUGIN_OPTION_API_KEY (injected by Claude Code userConfig)
#   3. CLAUDE_PLUGIN_OPTION_MEM0_API_KEY (legacy userConfig)
#   4. Extract from shell profile files (~/.zshrc, ~/.bashrc, etc.)
#      Desktop app doesn't inherit shell env — this fallback covers users
#      who set MEM0_API_KEY in their profile but use the Desktop app.
#
# Settings: ~/.mem0/settings.json (user-editable, falls back to defaults)

_SCRIPT_DIR="$( cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd )"

_mem0_extract_profile_var() {
  _mem0_var_name="$1"
  for _profile in "$HOME/.zshrc" "$HOME/.bashrc" "$HOME/.zprofile" "$HOME/.bash_profile" "$HOME/.profile"; do
    if [ -f "$_profile" ]; then
      _extracted=$(grep -E "^\s*(export\s+)?${_mem0_var_name}=" "$_profile" 2>/dev/null \
        | tail -1 \
        | sed 's/^[^=]*=//' \
        | sed 's/[[:space:]]#.*//' \
        | sed "s/^[\"']//;s/[\"']$//" \
        | tr -d '[:space:]')
      # Only use literal values — skip variable references like ${OTHER_VAR}
      if [ -n "$_extracted" ] && [ "${_extracted#\$}" = "$_extracted" ]; then
        printf '%s' "$_extracted"
        return
      fi
    fi
  done
}

# Resolve API key: env var > userConfig > shell profile extraction
if [ -z "${MEM0_API_KEY:-}" ] && [ -n "${CLAUDE_PLUGIN_OPTION_API_KEY:-}" ]; then
  MEM0_API_KEY="$CLAUDE_PLUGIN_OPTION_API_KEY"
  export MEM0_API_KEY
fi
if [ -z "${MEM0_API_KEY:-}" ] && [ -n "${CLAUDE_PLUGIN_OPTION_MEM0_API_KEY:-}" ]; then
  MEM0_API_KEY="$CLAUDE_PLUGIN_OPTION_MEM0_API_KEY"
  export MEM0_API_KEY
fi
# Fallback: extract MEM0_API_KEY from shell profile files.
# The Desktop app only reads PATH from shell profiles — env vars like
# MEM0_API_KEY are not inherited. This grep-based extraction handles
# the common `export MEM0_API_KEY=...` pattern without sourcing the
# full profile (which could have side effects).
if [ -z "${MEM0_API_KEY:-}" ]; then
  _extracted="$(_mem0_extract_profile_var MEM0_API_KEY)"
  if [ -n "$_extracted" ]; then
    MEM0_API_KEY="$_extracted"
    export MEM0_API_KEY
  fi
fi

for _mem0_endpoint_var in MEM0_API_HOST MEM0_API_URL MEM0_MCP_URL; do
  eval "_mem0_current_value=\"\${${_mem0_endpoint_var}:-}\""
  if [ -z "$_mem0_current_value" ]; then
    _extracted="$(_mem0_extract_profile_var "$_mem0_endpoint_var")"
    if [ -n "$_extracted" ]; then
      export "${_mem0_endpoint_var}=$_extracted"
    fi
  fi
done
unset _mem0_endpoint_var _mem0_current_value _extracted

_mem0_resolve_identity() {
  if [ -n "${MEM0_USER_ID:-}" ]; then
    printf '%s' "$MEM0_USER_ID"
    return
  fi
  printf '%s' "${USER:-default}"
}

MEM0_RESOLVED_USER_ID="$(_mem0_resolve_identity)"
export MEM0_RESOLVED_USER_ID

_MEM0_IDENTITY_ANNOTATION=""
if [ -n "${MEM0_USER_ID:-}" ] && [ "$MEM0_USER_ID" != "${USER:-default}" ]; then
  _MEM0_IDENTITY_ANNOTATION=" (override; default: ${USER:-default})"
fi
export _MEM0_IDENTITY_ANNOTATION

# Load settings from ~/.mem0/settings.json
if command -v python3 >/dev/null 2>&1; then
  _SETTINGS_JSON=$(PYTHONPATH="$_SCRIPT_DIR" python3 -c "from load_settings import load_settings; import json; print(json.dumps(load_settings()))" 2>/dev/null || echo "{}")
  MEM0_AUTO_SAVE=$(echo "$_SETTINGS_JSON" | python3 -c "import sys,json; print(str(json.load(sys.stdin).get('auto_save',True)).lower())" 2>/dev/null || echo "true")
  MEM0_AUTO_SEARCH=$(echo "$_SETTINGS_JSON" | python3 -c "import sys,json; print(str(json.load(sys.stdin).get('auto_search',True)).lower())" 2>/dev/null || echo "true")
  MEM0_SEARCH_LIMIT=$(echo "$_SETTINGS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('search_limit',10))" 2>/dev/null || echo "10")
  MEM0_RETENTION_SESSION_DAYS=$(echo "$_SETTINGS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('retention_session_days',90))" 2>/dev/null || echo "90")
  MEM0_CONFIDENCE_THRESHOLD=$(echo "$_SETTINGS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('confidence_threshold',0.3))" 2>/dev/null || echo "0.3")
  MEM0_GLOBAL_SEARCH=$(echo "$_SETTINGS_JSON" | python3 -c "import sys,json; print(str(json.load(sys.stdin).get('global_search',False)).lower())" 2>/dev/null || echo "false")
  MEM0_DEBUG=$(echo "$_SETTINGS_JSON" | python3 -c "import sys,json; print(str(json.load(sys.stdin).get('debug',False)).lower())" 2>/dev/null || echo "false")
else
  MEM0_AUTO_SAVE="true"
  MEM0_AUTO_SEARCH="true"
  MEM0_SEARCH_LIMIT="10"
  MEM0_RETENTION_SESSION_DAYS="90"
  MEM0_CONFIDENCE_THRESHOLD="0.3"
  MEM0_GLOBAL_SEARCH="false"
  MEM0_DEBUG="false"
fi
export MEM0_AUTO_SAVE MEM0_AUTO_SEARCH MEM0_SEARCH_LIMIT MEM0_RETENTION_SESSION_DAYS MEM0_CONFIDENCE_THRESHOLD MEM0_GLOBAL_SEARCH MEM0_DEBUG

# Also resolve project context
. "$_SCRIPT_DIR/_project.sh"
