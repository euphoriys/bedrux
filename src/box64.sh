#!/bin/bash

# Ensure the script runs in its own directory
cd "$(dirname "$0")" || exit 1

# Function to remove existing Box64 sources and keyring
remove_existing_sources() {
    if [ -f /etc/apt/sources.list.d/box64.list ]; then
        rm -f /etc/apt/sources.list.d/box64.list || exit 1
    fi
    if [ -f /etc/apt/sources.list.d/box64.sources ]; then
        rm -f /etc/apt/sources.list.d/box64.sources || exit 1
    fi
    if [ -f /usr/share/keyrings/box64-archive-keyring.gpg ]; then
        rm -f /usr/share/keyrings/box64-archive-keyring.gpg
    fi
}

# Function to add Box64 sources and keyring
add_box64_sources() {
    mkdir -p /usr/share/keyrings
    curl -s "https://pi-apps-coders.github.io/box64-debs/KEY.gpg" | gpg --dearmor -o /usr/share/keyrings/box64-archive-keyring.gpg
    echo "Types: deb
URIs: https://Pi-Apps-Coders.github.io/box64-debs/debian
Suites: ./
Signed-By: /usr/share/keyrings/box64-archive-keyring.gpg" | tee /etc/apt/sources.list.d/box64.sources >/dev/null
}

# Function to install Box64
install_box64() {
    apt update
    apt install box64-android -y
}

# Main script execution
remove_existing_sources
add_box64_sources
install_box64
