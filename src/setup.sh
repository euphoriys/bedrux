#!/bin/bash

echo "Setting up Bedrock server environment..."

# Step 1: Update packages and install necessary tools
yes | pkg up > /dev/null 2>&1
pkg ins proot-distro -y > /dev/null 2>&1

# Step 2: Install Ubuntu distro in proot and set up the environment
pd i ubuntu > /dev/null 2>&1
pd sh ubuntu -- << 'OUTER_EOF' 2>/dev/null
    apt update > /dev/null 2>&1 && apt upgrade -y > /dev/null 2>&1 && apt install curl nano gpg -y > /dev/null 2>&1
    
    case "$(uname -m)" in
        aarch64)
            echo "Installing Box64 for ARM64 architecture..."
            curl -s -O https://raw.githubusercontent.com/euphoriys/bedrux/main/src/box64.sh > /dev/null 2>&1
            bash box64.sh > /dev/null 2>&1
            rm -rf box64.sh
            ;;
        x86_64|amd64)
            echo "Skipping Box64 installation. CPU architecture is x86_64 or amd64."
            ;;
        *)
            echo "Unsupported CPU architecture: $(uname -m). Exiting."
            exit 1
            ;;
    esac

    # Step 3: Prepare the server version downloader
    curl -s -O https://raw.githubusercontent.com/euphoriys/bedrux/main/src/minecraft_version.sh > /dev/null 2>&1
    chmod +x minecraft_version.sh > /dev/null 2>&1
OUTER_EOF

echo "Environment setup completed. Run 'pd sh ubuntu' to enter the Ubuntu environment."
echo "You can install the Bedrock server by running './minecraft_version.sh'."
