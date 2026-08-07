#!/usr/bin/env bash
set -euo pipefail

PYTHON_VERSION="3.14.0"
UA_DIR="${HOME}/tools/ua"
SKIP_PYENV_INSTALL=0
FORCE_UPDATE=0
PYENV_ROOT_DEFAULT="${HOME}/.pyenv"
PYENV_GIT_REF="v2.6.7"
PYENV_REPO_URL="https://github.com/pyenv/pyenv.git"

usage() {
    cat <<'EOF'
Usage: install-seedbox.sh [options]

Install or update Upload Assistant on a Linux box without requiring root.

Options:
  --ua-dir PATH           Installation directory (default: ~/tools/ua)
  --python VERSION        Python version for pyenv (default: 3.14.0)
  --skip-pyenv-install    Fail instead of installing pyenv automatically
  --force-update          Recreate .venv and reinstall packages
  -h, --help              Show this help
EOF
}

log() {
    printf '==> %s\n' "$1"
}

fail() {
    printf 'Error: %s\n' "$1" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

append_pyenv_init() {
    local rc_file="$1"
    if [ ! -f "$rc_file" ]; then
        touch "$rc_file"
    fi

    if ! grep -q 'PYENV_ROOT' "$rc_file"; then
        cat >>"$rc_file" <<'EOF'

export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
EOF
    fi
}

setup_pyenv_env() {
    export PYENV_ROOT="${PYENV_ROOT_DEFAULT}"
    export PATH="${PYENV_ROOT}/bin:${PATH}"
    eval "$(pyenv init -)"
}

install_pyenv_if_needed() {
    if command -v pyenv >/dev/null 2>&1; then
        setup_pyenv_env
        return
    fi

    if [ "$SKIP_PYENV_INSTALL" -eq 1 ]; then
        fail "pyenv is not installed and --skip-pyenv-install was requested"
    fi

    require_command git

    log "Installing pyenv"
    if [ -e "${PYENV_ROOT_DEFAULT}" ] && [ ! -d "${PYENV_ROOT_DEFAULT}/.git" ]; then
        fail "Refusing to install pyenv because ${PYENV_ROOT_DEFAULT} exists and is not a git checkout"
    fi

    git clone --branch "$PYENV_GIT_REF" --depth 1 "$PYENV_REPO_URL" "${PYENV_ROOT_DEFAULT}"
    setup_pyenv_env
    append_pyenv_init "${HOME}/.bashrc"
    append_pyenv_init "${HOME}/.profile"
}

install_python_if_needed() {
    if ! pyenv versions --bare | grep -qx "$PYTHON_VERSION"; then
        log "Installing Python ${PYTHON_VERSION} via pyenv"
        pyenv install "$PYTHON_VERSION"
    fi
}

clone_or_update_repo() {
    mkdir -p "$(dirname "$UA_DIR")"

    if [ ! -d "${UA_DIR}/.git" ]; then
        log "Cloning Upload Assistant into ${UA_DIR}"
        git clone https://github.com/wastaken7/Upload-Assistant.git "$UA_DIR"
        return
    fi

    log "Updating existing Upload Assistant checkout"
    git -C "$UA_DIR" pull --ff-only
}

install_dependencies() {
    cd -- "$UA_DIR"
    UA_DIR="$PWD"

    log "Selecting Python ${PYTHON_VERSION} for this checkout"
    pyenv local "$PYTHON_VERSION"

    if [ "$FORCE_UPDATE" -eq 1 ] && [ -d ".venv" ]; then
        log "Removing existing virtual environment"
        rm -rf "${UA_DIR}/.venv"
    fi

    if [ ! -d ".venv" ]; then
        log "Creating virtual environment"
        python -m venv .venv
    elif [ -x ".venv/bin/python" ]; then
        local venv_python_version
        venv_python_version="$("./.venv/bin/python" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
        if [ "$venv_python_version" != "$PYTHON_VERSION" ]; then
            if [ "$FORCE_UPDATE" -eq 1 ]; then
                log "Recreating virtual environment for Python ${PYTHON_VERSION}"
                rm -rf "${UA_DIR}/.venv"
                python -m venv .venv
            else
                fail "Existing .venv uses Python ${venv_python_version}; rerun with --force-update to recreate it for ${PYTHON_VERSION}"
            fi
        fi
    fi

    # shellcheck disable=SC1091
    source .venv/bin/activate

    log "Upgrading pip"
    python -m pip install -U pip

    log "Installing Upload Assistant dependencies"
    pip install -r requirements.txt

}

write_runner() {
    cat >"${UA_DIR}/run-ua.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# shellcheck disable=SC1091
source .venv/bin/activate
exec python upload.py "$@"
EOF
    chmod +x "${UA_DIR}/run-ua.sh"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --ua-dir)
            [ "$#" -ge 2 ] || fail "--ua-dir requires a path"
            UA_DIR="$2"
            shift 2
            ;;
        --python)
            [ "$#" -ge 2 ] || fail "--python requires a version"
            PYTHON_VERSION="$2"
            shift 2
            ;;
        --skip-pyenv-install)
            SKIP_PYENV_INSTALL=1
            shift
            ;;
        --force-update)
            FORCE_UPDATE=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            fail "Unknown option: $1"
            ;;
    esac
done

require_command git
require_command bash

install_pyenv_if_needed
require_command pyenv

install_python_if_needed
clone_or_update_repo
install_dependencies
write_runner

cat <<EOF

Installation complete.

Location:
  ${UA_DIR}

Run:
  cd -- "${UA_DIR}"
  ./run-ua.sh "/path/to/content" --trackers yourtracker

Optional next steps:
  - Start the Web UI: ./run-ua.sh --webui 0.0.0.0:5000
EOF
