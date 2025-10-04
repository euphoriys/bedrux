#!/bin/bash
clear

run_silent() {
    local output
    if ! output=$("$@" 2>&1); then
        echo "Command failed: $*" >&2
        echo "$output" >&2
        return 1
    fi
}

implement_function() {
    local func_name="$1"; shift
    local define_only=0
    if [[ "$1" == "--define-only" ]]; then
        define_only=1
        shift
    fi
    if [[ -z "$func_name" ]]; then
        echo "Usage: implement_function <function_name> [--define-only] [args...]" >&2
        return 2
    fi
    if ! declare -f "$func_name" >/dev/null; then
        echo "Error: function '$func_name' is not defined." >&2
        return 1
    fi
    if [[ $define_only -eq 1 ]]; then
        ( declare -f run_silent 2>/dev/null || true
          declare -f "$func_name" ) | pd sh debian -- bash -s
    else
        ( declare -f run_silent 2>/dev/null || true
          declare -f "$func_name"
          printf '\n%s' "$func_name"
          for a in "$@"; do printf ' %q' "$a"; done
          printf '\n' ) | pd sh debian -- bash -s
    fi
}

main() {
    update_termux
    install_proot_distro
    install_debian
    implement_function run_silent --define-only
    implement_function setup_debian
}

update_termux() {
    echo "Updating Termux packages..."
    run_silent bash -c "yes | pkg up"
}

install_proot_distro() {
    echo "Installing PRoot Distro..."
    run_silent pkg ins -y proot-distro
}

install_debian() {
    echo "Installing Debian Trixie..."
    run_silent pd i debian
}

setup_debian() {
    echo "Configuring Debian environment..."
    run_silent apt-get update
    run_silent apt-get upgrade -y
    run_silent apt-get install -y fzf curl nano

    ARCH=$(uname -m)
    echo "Detected architecture: $ARCH"

    case "$ARCH" in
        aarch64)
            echo "Installing Box64 for '$ARCH' architecture..."
            run_silent apt-get install -y box64
            echo "Configuring environment variables in order to increase performance..."
            curl -s -O https://raw.githubusercontent.com/euphoriys/bedrux/main/src/.box64rc
            ;;
        x86_64|amd64)
            echo "Skipping Box64 installation. CPU architecture: '$ARCH'"
            run_silent apt-get install -y libcurl4t64
            ;;
        *)
            echo "Unsupported CPU architecture: '$ARCH'. Exiting..." >&2
            exit 1
            ;;
    esac

    echo "Downloading Bedrux Server Manager (svm)..."
    curl -s -O https://raw.githubusercontent.com/euphoriys/bedrux/main/src/svm
    chmod +x svm
    mv svm /usr/bin/svm
}

main