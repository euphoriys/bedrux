#!/bin/bash

set -e

update_termux_packages() {
    echo "Updating Termux packages and installing proot-distro..."
    yes | pkg up > /dev/null 2>&1
    pkg install proot-distro -y > /dev/null 2>&1
}

install_ubuntu() {
    echo "Installing Ubuntu distribution in proot-distro..."
    proot-distro install ubuntu > /dev/null 2>&1
}

setup_ubuntu_env() {
    echo "Configuring Ubuntu environment and installing dependencies..."

    cat > /tmp/ubuntu_setup_inner.sh <<'EOF'
#!/bin/bash
set -e
apt update > /dev/null 2>&1
apt upgrade -y > /dev/null 2>&1
apt install -y curl nano gpg > /dev/null 2>&1

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

echo "Downloading Minecraft version helper script..."
curl -s -O https://raw.githubusercontent.com/euphoriys/bedrux/main/src/minecraft_version.sh
chmod +x minecraft_version.sh

echo "Downloading Bedrux Server Manager (svm)..."
curl -s -O https://raw.githubusercontent.com/euphoriys/bedrux/main/src/svm
chmod +x svm
mv svm /usr/bin/svm

echo "svm installed to /usr/bin and made executable."
EOF

    proot-distro login ubuntu -- bash /tmp/ubuntu_setup_inner.sh
    rm -f /tmp/ubuntu_setup_inner.sh
}

main() {
    update_termux_packages
    install_ubuntu
    setup_ubuntu_env
    echo "Environment setup completed!"
    echo "To enter Ubuntu, run: proot-distro login ubuntu"
    echo "To install the Bedrock server, run: ./bedrock_server_manager.sh"
}

main