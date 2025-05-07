#!/bin/bash

# Ensure the script always runs from its own directory
cd "$(dirname "$0")" || exit 1

# Base directories for instances and backups
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTANCES_DIR="$BASE_DIR/../instances"
BACKUP_DIR="$BASE_DIR/../backups"

# Function to fetch the latest release or preview version
# This function scrapes the Minecraft wiki to find the latest version
fetch_version() {
    local pattern=$1
    curl -s https://minecraft.wiki/w/Bedrock_Dedicated_Server | grep -oP "(?<=$pattern)[^\"]+" || { echo "Error: Unable to fetch version."; exit 1; }
}

# Function to determine the download URL based on the user's choice
# Supports release, preview, or manual version input
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
# Ensures the downloaded file is a valid zip archive
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

# Function to replace the bedrock_server executable in an existing instance
# Updates the server executable while preserving configuration and world data
replace_version() {
    local instance_dir="$INSTANCES_DIR/$1"
    if [ -d "$instance_dir" ]; then
        echo "Updating instance: ${1}..."
        unzip -o -j "bedrockserver_tmp.zip" "bedrock_server" -d "$instance_dir" > /dev/null || {
            echo "Error: Failed to update the instance."
            exit 1
        }
        rm "bedrockserver_tmp.zip"
        echo "Instance ${1} updated successfully."
    else
        echo "Error: Instance ${1} does not exist."
        exit 1
    fi
}

# Function to overwrite an existing instance
# Deletes the existing instance directory and sets up a new server instance
overwrite_instance() {
    local instance_dir="$INSTANCES_DIR/$1"
    if [ -d "$instance_dir" ]; then
        echo "Overwriting instance: ${1}..."
        rm -rf "$instance_dir" || { echo "Error: Failed to delete the existing instance."; exit 1; }
        setup_server "$1"
        echo "Instance ${1} overwritten successfully."
    else
        echo "Error: Instance ${1} does not exist."
        exit 1
    fi
}

# Function to create a start script for the server
# Uses Box64 if available, otherwise runs the server directly
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

# Function to create an autostart script for the server
# Restarts the server automatically if it crashes
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

# Function to set up a new server instance
# Unzips the downloaded server files and creates management scripts
setup_server() {
    local instance_name="$1"
    local path="$INSTANCES_DIR/$instance_name"
    local zip_path="$PWD/bedrockserver_tmp.zip"

    echo "Unzipping the downloaded file..."
    mkdir -p "$path"
    cd "$path" || exit
    unzip -q "$zip_path" && rm "$zip_path"
    echo "$version" > "$path/version.txt"
    create_start_script
    create_autostart_script
    echo "Unzipping completed."
    echo "Setup completed. To start the server, navigate to '$path' and run './start.sh'."
}

# Function to list all existing server instances
list_instances() {
    local instances=($(find "$INSTANCES_DIR" -type f -name "bedrock_server" -exec dirname {} \; | sort -u))
    if [ ${#instances[@]} -eq 0 ]; then
        echo "No instances found."
        return 1
    fi
    echo "Existing instances:"
    for instance in "${instances[@]}"; do
        echo "${instance#$INSTANCES_DIR/}"
    done
    return 0
}

# Function to create a backup of a server instance
create_backup() {
    local instance_dir="$1"
    mkdir -p "$BACKUP_DIR"
    local timestamp=$(date +"%Y%m%d_%H%M%S")
    local backup_file="$BACKUP_DIR/${instance_dir}_backup_$timestamp.tar.gz"
    echo "Creating backup for instance: $instance_dir..."
    tar -czf "$backup_file" -C "$INSTANCES_DIR" "$instance_dir" || { echo "Error when creating the backup."; exit 1; }
    echo "Backup successfully created: $backup_file"
}

# Function to view details of an existing instance
view_instance_details() {
    local instance_dir="$INSTANCES_DIR/$1"
    if [ ! -d "$instance_dir" ]; then
        echo "Error: Instance $1 does not exist."
        exit 1
    fi

    echo "Details for instance: $1"
    echo "-------------------------"
    echo "Path: $instance_dir"
    echo "Size: $(du -sh "$instance_dir" | cut -f1)"
    echo "Server version: $(cat "$instance_dir/version.txt" 2>/dev/null || echo 'Unknown')"

    # Check for worlds or treat the instance as the world
    if [ -d "$instance_dir/worlds" ] && [ "$(ls -A "$instance_dir/worlds" 2>/dev/null)" ]; then
        echo "Worlds: $(ls "$instance_dir/worlds")"
    fi
    echo "-------------------------"
}

# Function to delete an existing instance
delete_instance() {
    local instance_dir="$INSTANCES_DIR/$1"
    if [ ! -d "$instance_dir" ]; then
        echo "Error: Instance $1 does not exist."
        exit 1
    fi

    read -p "Are you sure you want to delete the instance '$1'? This action cannot be undone. [y/N]: " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "Operation canceled."
        exit 0
    fi

    rm -rf "$instance_dir" || { echo "Error: Failed to delete the instance."; exit 1; }
    echo "Instance '$1' deleted successfully."
}

# Main menu for user interaction
echo "Choose an option:"
echo "1. Create a new instance"
echo "2. Update the server version in an existing instance"
echo "3. Delete an existing instance and create a new one with the latest or specified server version"
echo "4. Delete an existing instance"
echo "5. View details of an existing instance"
echo "6. Create a backup of an existing instance"
echo "7. Restore a backup"
read -p "Enter your choice [1-7]: " option

# Handle user input
if [[ "$option" -ne 1 && "$option" -ne 2 && "$option" -ne 3 && "$option" -ne 4 && "$option" -ne 5 && "$option" -ne 6 && "$option" -ne 7 ]]; then
    echo "Invalid option."
    exit 1
fi

if [ "$option" -eq 1 ]; then
    # Create a new instance
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

elif [ "$option" -eq 2 ]; then
    # Update the server version in an existing instance
    if ! list_instances; then
        exit 1
    fi
    read -p "Enter the instance name: " instance_dir
    if [ ! -d "$INSTANCES_DIR/$instance_dir" ] || [ ! -f "$INSTANCES_DIR/$instance_dir/bedrock_server" ]; then
        echo "Instance $instance_dir does not exist."
        exit 1
    fi
    read -p "Do you want to use the latest release, preview, or enter a version manually? [release] " choice
    determine_url "$choice"
    download_and_validate
    replace_version "$instance_dir"

elif [ "$option" -eq 3 ]; then
    # Delete an existing instance and create a new one
    if ! list_instances; then
        exit 1
    fi
    read -p "Enter the instance name: " instance_dir
    if [ ! -d "$INSTANCES_DIR/$instance_dir" ]; then
        echo "Instance $instance_dir does not exist."
        exit 1
    fi
    read -p "Do you want to use the latest release, preview, or enter a version manually? [release] " choice
    determine_url "$choice"
    download_and_validate
    overwrite_instance "$instance_dir"

elif [ "$option" -eq 4 ]; then
    # Delete an existing instance
    if ! list_instances; then
        exit 1
    fi
    read -p "Enter the name of the instance to delete: " instance_dir
    if [ ! -d "$INSTANCES_DIR/$instance_dir" ]; then
        echo "Error: Instance $instance_dir does not exist."
        exit 1
    fi
    delete_instance "$instance_dir"

elif [ "$option" -eq 5 ]; then
    # View details of an existing instance
    if ! list_instances; then
        exit 1
    fi
    read -p "Enter the name of the instance to view details: " instance_dir
    if [ ! -d "$INSTANCES_DIR/$instance_dir" ]; then
        echo "Error: Instance $instance_dir does not exist."
        exit 1
    fi
    view_instance_details "$instance_dir"

elif [ "$option" -eq 6 ]; then
    # Create a backup of an existing instance
    if ! list_instances; then
        exit 1
    fi
    read -p "Enter the name of the instance to be backed up: " instance_dir
    if [ ! -d "$INSTANCES_DIR/$instance_dir" ]; then
        echo "Instance $instance_dir does not exist."
        exit 1
    fi
    create_backup "$instance_dir"

elif [ "$option" -eq 7 ]; then
    # Restore a backup
    if [ ! -d "backups" ]; then
        echo "Error: The 'backups' folder does not exist."
        echo "Please create a backup first using Option 6."
        exit 1
    fi

    backups_count=$(ls backups/*.tar.gz 2>/dev/null | wc -l)
    if [ "$backups_count" -eq 1 ]; then
        backup_name=$(ls backups/*.tar.gz)
        backup_name=$(basename "$backup_name")
        echo "Automatically selected backup: $backup_name"
    elif [ "$backups_count" -eq 0 ]; then
        echo "Error: No backup files found in the 'backups' folder."
        echo "Please create a backup first using Option 6."
        exit 1
    else
        echo "Available backups:"
        ls backups/
        read -p "Enter the name of the backup file (e.g., your_backup.tar.gz): " backup_name
    fi

    backup_file="backups/$backup_name"
    if [ ! -f "$backup_file" ]; then
        echo "Backup file $backup_file does not exist."
        exit 1
    fi

    backup_instance_name=$(echo "$backup_name" | sed -E 's/_backup_[0-9]{8}_[0-9]{6}\.tar\.gz$//')
    if [ -z "$backup_instance_name" ]; then
        echo "Error: Could not determine the instance name from the backup file."
        exit 1
    fi

    if ! list_instances; then
        exit 1
    fi
    read -p "Enter the name of the instance to replace (or leave empty to use the backup's original name '$backup_instance_name'): " target_instance_name
    if [ -z "$target_instance_name" ]; then
        target_instance_name="$backup_instance_name"
    fi

    if [ -d "./$target_instance_name" ]; then
        echo "WARNING: The folder '$target_instance_name' will be deleted and replaced with the backup."
        read -p "Are you sure you want to continue? [y/N]: " confirm
        if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
            echo "Operation canceled."
            exit 0
        fi
        echo "Deleting existing instance folder $target_instance_name in /src..."
        rm -rf "./$target_instance_name"
    else
        echo "Warning: Target instance $target_instance_name does not exist. A new instance will be created."
    fi

    echo "Restoring backup $backup_file to /src/$target_instance_name..."
    mkdir -p "./$target_instance_name"
    tar --strip-components=1 -xzf "$backup_file" -C "./$target_instance_name" || { echo "Error when restoring the backup."; exit 1; }

    if [ "$(ls -A "./$target_instance_name")" ]; then
        echo "Backup successfully restored to /src/$target_instance_name."
    else
        echo "Error: Backup restoration failed. Target directory is empty."
        exit 1
    fi
else
    echo "Invalid option."
    exit 1
fi
