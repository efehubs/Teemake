#!/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
WHITE='\033[1;37m'
GREY='\033[90m'
BOLD='\033[1m'
NC='\033[0m' 

TAG_OK="${GREEN}[  OK  ]${NC}"
TAG_FAIL="${RED}[ FAIL ]${NC}"
TAG_WAIT="${YELLOW}[ WAIT ]${NC}"
TAG_INFO="${CYAN}[ INFO ]${NC}"
TAG_KEY="${PURPLE}[ KEY  ]${NC}"

draw_header() {
    clear
    echo -e "${CYAN}  ████████╗███████╗███████╗███╗    ███╗ █████╗ ██╗  ██╗███████╗${NC}"
    echo -e "${CYAN}  ╚══██╔══╝██╔════╝██╔════╝████╗ ████║██╔══██╗██║ ██╔╝██╔════╝${NC}"
    echo -e "${CYAN}     ██║   █████╗  █████╗  ██╔████╔██║███████║█████╔╝ █████╗  ${NC}"
    echo -e "${CYAN}     ██║   ██╔══╝  ██╔══╝  ██║╚██╔╝██║██╔══██║██╔═██╗ ██╔══╝  ${NC}"
    echo -e "${CYAN}     ██║   ███████╗███████╗██║ ╚═╝ ██║██║  ██║██║  ██╗███████╗${NC}"
    echo -e "${CYAN}     ╚═╝   ╚══════╝╚══════╝╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝${NC}"
    
    echo -e "  ${PURPLE}────────────────────────────────────────────────────────────${NC}"
    echo -e "  ${WHITE}    TEEMAKE v8.2${NC}    | ${GREY}   Created by Efe Pasha${NC}"
    echo -e "  ${PURPLE}────────────────────────────────────────────────────────────${NC}"
    echo ""
}

grey_output() {
    while IFS= read -r line; do
        echo -e "${GREY}  │ ${line}${NC}"
    done
}

ensure_sudo() {
    if [ "$EUID" -eq 0 ]; then return; fi
    if sudo -n true 2>/dev/null; then
        echo -e "  ${TAG_OK} Sudo privileges detected (cached)."
    else
        echo -e "  ${TAG_KEY} ${YELLOW}Sudo privileges are required for dependencies.${NC}"
        if sudo -v -p "$(echo -e "  ${TAG_KEY} ${YELLOW}Enter Password: ${NC}")"; then
            echo -e "  ${TAG_OK} Sudo access granted."
        else
            echo -e "  ${TAG_FAIL} Authentication failed. Exiting."
            exit 1
        fi
    fi
}

show_progress() {
    local pid=$1
    local text=$2
    local delay=0.08
    local width=15
    local start_time=$(date +%s)
    local slider="▒▓█▓▒"
    local slen=${#slider}
    local pos=0
    local dir=1

    tput civis
    while kill -0 "$pid" 2>/dev/null; do
        local elapsed=$(($(date +%s) - start_time))
        local bar=""
        for ((i=0; i<width; i++)); do
            if (( i >= pos && i < pos + slen )); then
                local char_idx=$((i - pos))
                bar+="${slider:char_idx:1}"
            else
                bar+="░"
            fi
        done
        printf "\r  ${TAG_WAIT} %-35s [%s] ${GREY}%ds${NC}" "$text" "$bar" "$elapsed"
        ((pos += dir))
        if (( pos >= width - slen || pos <= 0 )); then ((dir *= -1)); fi
        sleep $delay
    done
    tput cnorm
    printf "\r\033[K"
}

run_task() {
    local DESC="$1"
    local CMD="$2"

    if [ "$VERBOSE" = true ]; then
        echo -e "\n${TAG_INFO} ${WHITE}$DESC${NC}"
        eval "$CMD" 2>&1 | grey_output
        local EXIT_CODE=${PIPESTATUS[0]}
    else
        local LOGFILE=$(mktemp)
        eval "$CMD" > "$LOGFILE" 2>&1 &
        local PID=$!
        show_progress $PID "$DESC"
        wait $PID
        local EXIT_CODE=$?
        if [ $EXIT_CODE -eq 0 ]; then
            printf "\r  ${TAG_OK} %-35s\n" "$DESC"
            rm "$LOGFILE"
        else
            printf "\r  ${TAG_FAIL} %-35s\n" "$DESC"
            echo -e "\n${RED}[ERROR] Task failed. Last 5 lines:${NC}"
            tail -n 5 "$LOGFILE" | grey_output
            rm "$LOGFILE"
            exit 1
        fi
    fi
}

draw_header

# Server name
while true; do
    read -p "$(echo -e "  ${YELLOW}${BOLD}Enter Server Name:${NC} ")" SERVER_NAME
    if [[ -n "$SERVER_NAME" && "$SERVER_NAME" =~ ^[a-zA-Z0-9_-]+$ ]]; then break; fi
    echo -e "    ${RED}Invalid name. Use alphanumeric characters, - or _ only.${NC}"
done

# 1. Define Game Modes
declare -a MODES=(
    "Vanilla" "https://github.com/teeworlds/teeworlds.git"
    "DDNet"   "https://github.com/ddnet/ddnet.git"
    "zCatch"  "https://github.com/jxsl13/zcatch.git"
)

# 2. Define Mode-Specific Dependencies
declare -A EXTRA_DEPS_APT=(
    ["Vanilla"]="libpnglite-dev libwavpack-dev"
    ["DDNet"]="libvulkan-dev libsqlite3-dev libcurl4-openssl-dev"
    ["zCatch"]="libcurl4-openssl-dev"
)

declare -A EXTRA_DEPS_DNF=(
    ["Vanilla"]="pnglite-devel wavpack-devel"
    ["DDNet"]="vulkan-devel sqlite-devel libcurl-devel"
    ["zCatch"]="libcurl-devel"
)

declare -A EXTRA_DEPS_PACMAN=(
    ["Vanilla"]="wavpack"
    ["DDNet"]="vulkan-headers vulkan-icd-loader sqlite curl"
    ["zCatch"]="curl"
)

# 3. Define Mode-Specific Build Options
# -DCLIENT=OFF is added to all to prevent the compile error
declare -A BUILD_OPT=(
    ["Vanilla"]="cmake ../source/ -DCLIENT=OFF -DSERVER=ON"
    ["DDNet"]="cmake ../source/ -DCLIENT=OFF -DSERVER=ON"
    ["zCatch"]="cmake ../source/ -DCLIENT=OFF -DSERVER=ON"
)

# Mode selection Logic
echo ""
echo -e "  ${WHITE}${BOLD}Available Game Modes:${NC}"
NUM_MODES=$((${#MODES[@]} / 2))
for ((i=0; i<NUM_MODES; i++)); do
    echo -e "    ${CYAN}$((i+1))${NC} - ${MODES[$((i*2))]}"
done

echo ""
while true; do
    read -p "$(echo -e "  ${YELLOW}Select a mode (1-$NUM_MODES): ${NC}")" MODE_CHOICE
    if [[ "$MODE_CHOICE" =~ ^[0-9]+$ ]] && [ "$MODE_CHOICE" -ge 1 ] && [ "$MODE_CHOICE" -le "$NUM_MODES" ]; then
        SELECTED_NAME="${MODES[$(( (MODE_CHOICE-1)*2 ))]}"
        SELECTED_URL="${MODES[$(( (MODE_CHOICE-1)*2 + 1 ))]}"
        break
    fi 
done

# Detailed logs
echo ""
read -p "$(echo -e "  ${YELLOW}Show detailed build logs? (y/n): ${NC}")" VIEW_LOGS
[[ "$VIEW_LOGS" =~ ^[Yy] ]] && VERBOSE=true || VERBOSE=false

echo -e "\n  ${PURPLE} DEPLOYING SERVER: ${WHITE}${BOLD}$SERVER_NAME${NC}"
echo -e "  ${PURPLE}────────────────────────────────────────────────────────────${NC}"

# Package manager discovery
echo -e "  ${BLUE} System Discovery...${NC}"

BASE_APT="build-essential cmake git python3 libfreetype6-dev libsdl2-dev"
BASE_DNF="@development-tools cmake gcc-c++ git freetype-devel python3 SDL2-devel"
BASE_PACMAN="base-devel cmake git freetype2 sdl2"

if command -v apt-get &> /dev/null; then
    PM="apt"; INSTALL="sudo apt-get install -y"
    SPECIFIC_DEPS=${EXTRA_DEPS_APT[$SELECTED_NAME]}
    FINAL_DEPS="$BASE_APT $SPECIFIC_DEPS"
elif command -v dnf &> /dev/null; then
    PM="dnf"; INSTALL="sudo dnf install -y"
    SPECIFIC_DEPS=${EXTRA_DEPS_DNF[$SELECTED_NAME]}
    FINAL_DEPS="$BASE_DNF $SPECIFIC_DEPS"
elif command -v pacman &> /dev/null; then
    PM="pacman"; INSTALL="sudo pacman -S --noconfirm"
    SPECIFIC_DEPS=${EXTRA_DEPS_PACMAN[$SELECTED_NAME]}
    FINAL_DEPS="$BASE_PACMAN $SPECIFIC_DEPS"
else
    echo -e "  OS/Package Manager not supported." && exit 1
fi

echo -e "    ${GREY}Manager: $PM${NC}"
echo -e "    ${GREY}Installing dependencies for: $SELECTED_NAME...${NC}"

ensure_sudo
run_task "Synchronizing Dependencies for $SELECTED_NAME" "$INSTALL $FINAL_DEPS"

# BUILDING AND COMPILING
mkdir -p "$SERVER_NAME/source" "$SERVER_NAME/server"
cd "$SERVER_NAME/source" || exit

run_task "Downloading $SELECTED_NAME" "git clone --recursive $SELECTED_URL ."

cd "../server" || exit

# --- Dynamic Build Logic ---
CURRENT_BUILD_CMD=${BUILD_OPT[$SELECTED_NAME]}
run_task "Initializing Build System" "$CURRENT_BUILD_CMD"

CORES=$(nproc)
run_task "Compiling Binary (Cores: $CORES)" "make -j$CORES"

echo -e "  ${PURPLE}────────────────────────────────────────────────────────────${NC}"
echo -e "\n  ${GREEN}${BOLD}COMPLETE!${NC} Server build finished in: ${WHITE}./$SERVER_NAME${NC}\n"

while true; do
    read -p "$(echo -e "  ${YELLOW}Run configuration script? (y/n): ${NC}")" RUN_CONFIG
    case $RUN_CONFIG in
        [Yy]* ) 
            echo -e "  ${TAG_WAIT} Fetching script..."
            curl -sSL "https://gist.githubusercontent.com/efehubs/d7537913b098285e3083010dc17b7044/raw/" | bash
            sleep 1; echo -e "\r  ${TAG_OK} Configuration script executed."
            break ;;
        [Nn]* ) 
            echo -e "  ${TAG_INFO} Skipping configuration script."
            break ;;
    esac
done

echo ""
echo -e "  ${CYAN}Installation finished successfully. Enjoy your Teeworlds server!${NC}\n"
exit 0
