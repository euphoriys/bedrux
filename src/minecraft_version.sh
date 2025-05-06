#!/bin/bash

# Function to fetch the latest release or preview version
fetch_version() {
    local pattern=$1
    curl -s https://minecraft.wiki/w/Bedrock_Dedicated_Server | grep -oP "(?<=$pattern)[^\"]+" || { echo "Error: Unable to fetch version."; exit 1; }
}

# Function to determine the download URL based on the user's choice
determine_url() {
    local choice=$1
    case "$choice" in
        preview)
            version=$(fetch_version "Preview:</b> <a href=\"/w/Bedrock_Edition_Preview_")
            url="https://www.minecraft.net/bedrockdedicatedserver/bin-linux-preview/bedrock-server-$version.zip"
            ;;
        manual)
            read -p "Enter the Minecraft Bedrock server version: " version
            url="https://www.minecraft.net/bedrockdedicatedserver/bin-linux/bedrock-server-$version.zip"
            ;;
        *)
            if [[ "$choice" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
                version=$choice
                url="https://www.minecraft.net/bedrockdedicatedserver/bin-linux/bedrock-server-$version.zip"
            else
                version=$(fetch_version "Release:</b> <a href=\"/w/Bedrock_Edition_")
                url="https://www.minecraft.net/bedrockdedicatedserver/bin-linux/bedrock-server-$version.zip"
            fi
            ;;
    esac
}

# Function to download and validate the Bedrock server
download_and_validate() {
    local temp_zip="bedrockserver_tmp.zip"
    echo "Downloading version: $version"
    curl -s -A "Mozilla/5.0 (Linux)" -o "$temp_zip" $url || { echo "Error: Unable to download the specified version."; exit 1; }

    if ! unzip -tq "$temp_zip" > /dev/null 2>&1; then
        echo "Error: The specified version does not exist or the downloaded file is not a valid zip file."
        rm "$temp_zip"
        exit 1
    fi

    echo "Download and validation successful."
}

# Function to create start script
create_start_script() {
    if command -v box64 > /dev/null 2>&1; then
        echo "#!/bin/bash
export BOX64_LOG=0
box64 bedrock_server | grep -v 'Box64 with Dynarec'" > start.sh
    else
        echo "#!/bin/bash
./bedrock_server" > start.sh
    fi
    chmod +x start.sh
}

# Function to create autostart script
create_autostart_script() {
    if command -v box64 > /dev/null 2>&1; then
        echo '#!/bin/bash
while true; do
    if ! pgrep -x "bedrock_server" > /dev/null; then
        echo "Starting Minecraft Bedrock Server..."
        cd ~/bedrockserver || exit
        export BOX64_LOG=0
        box64 bedrock_server | grep -v 'Box64 with Dynarec'
        echo "Minecraft Bedrock Server stopped! Restarting in 5 seconds."
        sleep 5
    else
        echo "Server is running."
        sleep 5
    fi
done' > autostart.sh
    else
        echo '#!/bin/bash
while true; do
    if ! pgrep -x "bedrock_server" > /dev/null; then
        echo "Starting Minecraft Bedrock Server..."
        cd ~/bedrockserver || exit
        ./bedrock_server
        echo "Minecraft Bedrock Server stopped! Restarting in 5 seconds."
        sleep 5
    else
        echo "Server is running."
        sleep 5
    fi
done' > autostart.sh
    fi
    chmod +x autostart.sh
}

# Function to set up the server
setup_server() {
    local instance_name=$1
    echo "Unzipping the downloaded file..."
    mkdir -p "$instance_name"
    cd "$instance_name"
    unzip -q "../bedrockserver_tmp.zip" && rm "../bedrockserver_tmp.zip"
    create_start_script
    create_autostart_script
    echo "Unzipping completed."
    echo "Setup completed. To start the server, navigate to the '$instance_name' directory and run './start.sh'."
}

# Function to list existing instances
list_instances() {
    local instances=($(find . -type f -name "bedrock_server" -exec dirname {} \; | sort -u))
    if [ ${#instances[@]} -eq 0 ]; then
        echo "No instances found."
        return 1
    fi
    echo "Existing instances:"
    for instance in "${instances[@]}"; do
        echo "${instance#./}"
    done
    return 0
}

# Function to replace the bedrock_server executable in an existing instance
replace_version() {
    local instance_dir=$1
    if [ -d "$instance_dir" ]; then
        unzip -o -j "bedrockserver_tmp.zip" "bedrock_server" -d "$instance_dir" > /dev/null
        rm "bedrockserver_tmp.zip"
        echo "Instance ${instance_dir#./} updated successfully."
    else
        echo "Instance ${instance_dir#./} does not exist."
        exit 1
    fi
}

# Function to overwrite an existing instance
overwrite_instance() {
    local instance_dir=$1
    if [ -d "$instance_dir" ]; then
        rm -rf "$instance_dir"
        setup_server "$instance_dir"
        echo "Instance ${instance_dir#./} overwritten successfully."
    else
        echo "Instance ${instance_dir#./} does not exist."
        exit 1
    fi
}

echo "Choose an option:"
echo "1. Create a new instance"
echo "2. Replace the server version in an existing instance"
echo "3. Overwrite an existing instance"
read -p "Enter your choice [1-3]: " option

if [[ "$option" -ne 1 && "$option" -ne 2 && "$option" -ne 3 ]]; then
    echo "Invalid option."
    exit 1
fi

if [ "$option" -eq 1 ]; then
    read -p "Enter a name for the new instance (leave empty for default naming): " instance_name
    if [ -z "$instance_name" ]; then
        instance_name="bedrockserver"
        instance_number=2
        while [ -d "$instance_name" ]; do
            instance_name="bedrockserver$instance_number"
            instance_number=$((instance_number + 1))
        done
    fi
    read -p "Do you want to use the latest release, preview, or enter a version manually? [release] " choice
    determine_url "$choice"
    download_and_validate
    setup_server "$instance_name"
else
    if ! list_instances; then
        exit 1
    fi
    read -p "Enter the instance name: " instance_dir
    if [ ! -d "$instance_dir" ] || [ ! -f "$instance_dir/bedrock_server" ]; then
        echo "Instance $instance_dir does not exist."
        exit 1
    fi
    read -p "Do you want to use the latest release, preview, or enter a version manually? [release] " choice
    determine_url "$choice"
    download_and_validate
    if [ "$option" -eq 2 ]; then
        replace_version "$instance_dir"
    elif [ "$option" -eq 3 ]; then
        overwrite_instance "$instance_dir"
    else
        echo "Invalid option."
        exit 1
    fi
fi
