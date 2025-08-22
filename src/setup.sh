#!/bin/bash
clear

set -e

update_termux_packages() {
    echo "Updating Termux packages and installing Proot-Distro..."
    yes | pkg up > /dev/null 2>&1
    pkg install proot-distro -y > /dev/null 2>&1
}

install_debian() {
    echo "Installing Debian Trixie using Proot-Distro..."
    proot-distro install debian > /dev/null 2>&1
}

setup_debian_env() {
    echo "Configuring Debian environment and installing dependencies..."

    proot-distro login debian -- bash -c '
        set -e
        apt-get update > /dev/null 2>&1
        apt-get upgrade -y > /dev/null 2>&1
        apt-get install -y fzf curl nano > /dev/null 2>&1

        arch=$(uname -m)
        if [[ "$arch" == "aarch64" ]]; then
            echo "Installing Box64 for ARM64 architecture..."
            apt-get install -y box64 > /dev/null 2>&1
        elif [[ "$arch" == "x86_64" || "$arch" == "amd64" ]]; then
            echo "Skipping Box64 installation. CPU architecture is $arch."
        else
            echo "Unsupported CPU architecture: $arch. Exiting..."
            exit 1
        fi

        echo "Downloading Bedrux Server Manager (svm)..."
        curl -s -O https://raw.githubusercontent.com/euphoriys/bedrux/main/src/svm
        chmod +x svm
        mv svm /usr/bin/svm
    '
}

main() {
    update_termux_packages
    install_debian
    setup_debian_env
    echo "Environment setup completed!"
    echo "To enter Debian, run: pd sh debian"
    echo "Then use the Bedrux Server Manager: svm"
}

main
