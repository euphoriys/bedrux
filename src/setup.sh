#!/bin/bash

set -e

update_termux_packages() {
    echo "Updating Termux packages and installing proot-distro..."
    yes | pkg up > /dev/null
    pkg install proot-distro -y > /dev/null
}

install_ubuntu() {
    echo "Installing Ubuntu distribution in proot-distro..."
    proot-distro install ubuntu > /dev/null
}

setup_ubuntu_env() {
    echo "Configuring Ubuntu environment and installing dependencies..."

    proot-distro login ubuntu -- bash -c '
        set -e
        apt update > /dev/null
        apt upgrade -y > /dev/null
        apt install -y fzf curl nano gpg > /dev/null 

        arch=$(uname -m)
        if [[ "$arch" == "aarch64" ]]; then
            echo "Installing Box64 for ARM64 architecture..."
            curl -s -O https://raw.githubusercontent.com/euphoriys/bedrux/main/src/box64.sh
            bash box64.sh > /dev/null 2>&1
            rm -f box64.sh
        elif [[ "$arch" == "x86_64" || "$arch" == "amd64" ]]; then
            echo "Skipping Box64 installation. CPU architecture is $arch."
        else
            echo "Unsupported CPU architecture: $arch. Exiting."
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
    install_ubuntu
    setup_ubuntu_env
    echo "Environment setup completed!"
    echo "To enter Ubuntu, run: pd sh ubuntu"
    echo "To use the Bedrux Server Manager, run: svm"
}

main
