#!/usr/bin/env python3

import os
import sys
import subprocess
import shutil
import logging
import time
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Union
from dataclasses import dataclass
from enum import Enum

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    from rich.text import Text
    from rich import box
except ImportError:
    print("Error: Required package 'rich' not found.")
    print("Install it with: pip3 install rich")
    sys.exit(1)

console = Console()


# Constants for console styling
class Style:
    """Console style constants"""
    SUCCESS = "green"
    ERROR = "red"
    WARNING = "yellow"
    INFO = "cyan"
    DIM = "dim"
    BOLD = "bold"


class PackageManager(Enum):
    """Supported package managers"""
    APT = "apt-get"
    DNF = "dnf"
    YUM = "yum"
    PACMAN = "pacman"
    ZYPPER = "zypper"
    UNKNOWN = "unknown"


@dataclass
class GameMode:
    """Represents a Teeworlds game mode configuration"""
    name: str
    url: str
    dependencies: Dict[str, str]  # Package manager -> dependencies mapping
    build_opts: List[str]  # Default build options


@dataclass
class BuildOption:
    """Represents a CMake build option"""
    name: str
    description: str
    current_value: str
    option_type: str  # "boolean", "string", "generator"
    

@dataclass
class ConfigSetting:
    # Represents a configuration setting
    key: str
    prompt: str
    default: str
    description: str = ""


class TeemakeBuilder:
    # Main class for building and managing Teeworlds servers
    
    # Game mode configurations
    GAME_MODES: List[GameMode] = [
        GameMode(
            name="Teeworlds",
            url="https://github.com/teeworlds/teeworlds.git",
            dependencies={
                "apt-get": "libpnglite-dev libwavpack-dev",
                "dnf": "libpng-devel wavpack-devel",
                "yum": "libpng-devel wavpack-devel",
                "pacman": "libpng wavpack",
                "zypper": "libpng16-devel wavpack-devel",
            },
            build_opts=["cmake", "../source/", "-DCLIENT=OFF", "-DSERVER=ON"]
        ),
        GameMode(
            name="DDNet",
            url="https://github.com/ddnet/ddnet.git",
            dependencies={
                "apt-get": "libvulkan-dev libsqlite3-dev libcurl4-openssl-dev",
                "dnf": "vulkan-devel sqlite-devel libcurl-devel",
                "yum": "vulkan-devel sqlite-devel libcurl-devel",
                "pacman": "vulkan-icd-loader sqlite curl",
                "zypper": "vulkan-devel sqlite3-devel libcurl-devel",
            },
            build_opts=["cmake", "../source/", "-DCLIENT=OFF", "-DSERVER=ON"]
        ),
        GameMode(
            name="zCatch",
            url="https://github.com/jxsl13/zcatch.git",
            dependencies={
                "apt-get": "libcurl4-openssl-dev",
                "dnf": "libcurl-devel",
                "yum": "libcurl-devel",
                "pacman": "curl",
                "zypper": "libcurl-devel",
            },
            build_opts=["cmake", "../source/", "-DCLIENT=OFF", "-DSERVER=ON"]
        ),
    ]
    
    # Available build options for each game mode
    AVAILABLE_BUILD_OPTIONS: Dict[str, List[BuildOption]] = {
        "Teeworlds": [
            BuildOption("-DCLIENT", "Build client", "OFF", "boolean"),
            BuildOption("-DSERVER", "Build server", "ON", "boolean"),
            BuildOption("-DMASTERSERVER", "Build masterserver", "OFF", "boolean"),
            BuildOption("-DTOOLS", "Build tools", "OFF", "boolean"),
            BuildOption("-DDEV", "Development mode", "OFF", "boolean"),
            BuildOption("-GNinja", "Use Ninja build system (faster)", "OFF", "generator"),
        ],
        "DDNet": [
            BuildOption("-DCLIENT", "Build client", "OFF", "boolean"),
            BuildOption("-DSERVER", "Build server", "ON", "boolean"),
            BuildOption("-DTOOLS", "Build tools", "OFF", "boolean"),
            BuildOption("-DMYSQL", "Enable MySQL support", "OFF", "boolean"),
            BuildOption("-DWEBSOCKETS", "Enable WebSocket support", "OFF", "boolean"),
            BuildOption("-DVIDEORECORDER", "Enable video recorder", "OFF", "boolean"),
            BuildOption("-DUPNP", "Enable UPnP support", "OFF", "boolean"),
            BuildOption("-DSTEAM", "Enable Steam integration", "OFF", "boolean"),
            BuildOption("-DPREFER_BUNDLED_LIBS", "Use bundled libraries", "OFF", "boolean"),
            BuildOption("-GNinja", "Use Ninja build system (faster)", "OFF", "generator"),
        ],
        "zCatch": [
            BuildOption("-DCLIENT", "Build client", "OFF", "boolean"),
            BuildOption("-DSERVER", "Build server", "ON", "boolean"),
            BuildOption("-DTOOLS", "Build tools", "OFF", "boolean"),
            BuildOption("-DDEV", "Development mode", "OFF", "boolean"),
            BuildOption("-GNinja", "Use Ninja build system (faster)", "OFF", "generator"),
        ],
    }
    
    # Base dependencies for different package managers
    BASE_DEPS: Dict[str, str] = {
        "apt-get": "build-essential cmake git python3 libfreetype6-dev libsdl2-dev",
        "dnf": "gcc gcc-c++ make cmake git python3 freetype-devel SDL2-devel",
        "yum": "gcc gcc-c++ make cmake git python3 freetype-devel SDL2-devel",
        "pacman": "base-devel cmake git python freetype2 sdl2",
        "zypper": "gcc gcc-c++ make cmake git python3 freetype2-devel libSDL2-devel",
    }
    
    # Minimum required disk space in MegaByte
    MIN_DISK_SPACE_MB = 2000
    
    # Basic configuration settings for each game mode
    BASIC_CONFIG_SETTINGS: Dict[str, List[ConfigSetting]] = {
        "Teeworlds": [
            ConfigSetting("sv_name", "Server Name", "My Teeworlds Server", "The name of your server"),
            ConfigSetting("sv_port", "Server Port", "8303", "Port number (default: 8303)"),
            ConfigSetting("sv_max_clients", "Maximum Players", "16", "Maximum number of players"),
            ConfigSetting("sv_gametype", "Game Type", "dm", "Game type (dm, tdm, ctf)"),
        ],
        "DDNet": [
            ConfigSetting("sv_name", "Server Name", "My DDNet Server", "The name of your server"),
            ConfigSetting("sv_port", "Server Port", "8303", "Port number (default: 8303)"),
            ConfigSetting("sv_max_clients", "Maximum Players", "64", "Maximum number of players"),
            ConfigSetting("sv_gametype", "Game Type", "DDraceNetwork", "Game type"),
        ],
        "zCatch": [
            ConfigSetting("sv_name", "Server Name", "My zCatch Server", "The name of your server"),
            ConfigSetting("sv_port", "Server Port", "8303", "Port number (default: 8303)"),
            ConfigSetting("sv_max_clients", "Maximum Players", "16", "Maximum number of players"),
            ConfigSetting("sv_gametype", "Game Type", "zCatch", "Game type"),
        ],
    }
    
    # Advanced configuration settings (to be implemented later)
    ADVANCED_CONFIG_SETTINGS: Dict[str, List[ConfigSetting]] = {
        "Teeworlds": [],
        "DDNet": [],
        "zCatch": [],
    }
    
    def __init__(self, verbose: bool = False):
        """
        Initialize the TeemakeBuilder
        
        Args:
            verbose: Enable verbose logging
        """
        self.server_name: Optional[str] = None
        self.selected_mode: Optional[GameMode] = None
        self.verbose: bool = verbose
        self.is_root: bool = os.geteuid() == 0
        self._setup_logging()  # Setup logging FIRST
        self.package_manager: PackageManager = self._detect_package_manager()
        
    def _setup_logging(self) -> None:
        """Setup logging configuration"""
        log_format = '%(asctime)s - %(levelname)s - %(message)s'
        logging.basicConfig(
            level=logging.DEBUG if self.verbose else logging.INFO,
            format=log_format,
            handlers=[
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def _detect_package_manager(self) -> PackageManager:
        """
        Detect the system's package manager
        
        Returns:
            PackageManager enum value
        """
        package_managers = {
            'apt-get': PackageManager.APT,
            'dnf': PackageManager.DNF,
            'yum': PackageManager.YUM,
            'pacman': PackageManager.PACMAN,
            'zypper': PackageManager.ZYPPER,
        }
        
        for cmd, pm in package_managers.items():
            if shutil.which(cmd):
                self.logger.debug(f"Detected package manager: {pm.value}")
                return pm
        
        self.logger.warning("Could not detect package manager")
        return PackageManager.UNKNOWN
        
    def show_header(self, clear: bool = True) -> None:
        """Display the application header"""
        if clear:
            # Use os.system for proper clearing across all terminals
            os.system('clear' if os.name != 'nt' else 'cls')
        
        header_art = """
  ████████╗███████╗███████╗███╗   ███╗ █████╗ ██╗  ██╗███████╗
  ╚══██╔══╝██╔════╝██╔════╝████╗ ████║██╔══██╗██║ ██╔╝██╔════╝
     ██║   █████╗  █████╗  ██╔████╔██║███████║█████╔╝ █████╗  
     ██║   ██╔══╝  ██╔══╝  ██║╚██╔╝██║██╔══██║██╔═██╗ ██╔══╝  
     ██║   ███████╗███████╗██║ ╚═╝ ██║██║  ██║██║  ██╗███████╗
     ╚═╝   ╚══════╝╚══════╝╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝
        """
        
        console.print(Panel(
            Text(header_art, style=f"{Style.INFO} {Style.BOLD}") + "\n" +
            Text("Teemake - v2.0", style=f"white {Style.BOLD}") + 
            Text(" | Created by efe", style="bright_black"),
            box=box.DOUBLE,
            border_style=Style.INFO,
            padding=(0, 2)
        ))
        console.print()
    
    def clear_screen(self) -> None:
        """Clear the screen and show header"""
        # Use os.system for proper clearing across all terminals
        os.system('clear' if os.name != 'nt' else 'cls')
        self.show_header(clear=False)
    
    def check_disk_space(self, path: Path = Path.cwd()) -> bool:
        """
        Check if there's enough disk space for build
        
        Args:
            path: Path to check disk space on
            
        Returns:
            True if enough space available
        """
        try:
            stat = shutil.disk_usage(path)
            available_mb = stat.free / (1024 * 1024)
            
            if available_mb < self.MIN_DISK_SPACE_MB:
                console.print(
                    f"[{Style.ERROR}]✗ Insufficient disk space[/{Style.ERROR}]"
                )
                console.print(
                    f"  Required: {self.MIN_DISK_SPACE_MB}MB, "
                    f"Available: {available_mb:.0f}MB"
                )
                return False
            
            console.print(
                f"[{Style.SUCCESS}]✓ Disk space check passed "
                f"({available_mb:.0f}MB available)[/{Style.SUCCESS}]"
            )
            return True
            
        except Exception as e:
            self.logger.warning(f"Could not check disk space: {e}")
            return True  # Continue anyway
    
    def ensure_sudo(self) -> bool:
        """
        Check and request sudo privileges if needed
        
        Returns:
            True if sudo is available or running as root
        """
        # If already root, no sudo needed
        if self.is_root:
            console.print(f"[{Style.SUCCESS}]✓ Running as root[/{Style.SUCCESS}]")
            return True
        
        # Check if sudo is cached
        try:
            result = subprocess.run(
                ["sudo", "-n", "true"],
                capture_output=True,
                timeout=1
            )
            if result.returncode == 0:
                console.print(
                    f"[{Style.SUCCESS}]✓ Sudo privileges detected (cached)[/{Style.SUCCESS}]"
                )
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        console.print(
            f"[{Style.WARNING}]Sudo privileges required for dependencies[/{Style.WARNING}]"
        )
        
        try:
            result = subprocess.run(["sudo", "-v"], timeout=30)
            if result.returncode == 0:
                console.print(f"[{Style.SUCCESS}]✓ Sudo access granted[/{Style.SUCCESS}]")
                return True
            else:
                console.print(f"[{Style.ERROR}]✗ Authentication failed[/{Style.ERROR}]")
                return False
        except subprocess.TimeoutExpired:
            console.print(f"[{Style.ERROR}]✗ Authentication timeout[/{Style.ERROR}]")
            return False
        except KeyboardInterrupt:
            console.print(f"\n[{Style.ERROR}]✗ Authentication cancelled[/{Style.ERROR}]")
            return False
    
    def run_command(
        self, 
        description: str, 
        command: Union[List[str], str],
        shell: bool = False,
        cwd: Optional[Path] = None
    ) -> Tuple[bool, str, str]:
        """
        Run a command with progress indication
        
        Args:
            description: Human-readable description of the command
            command: Command to run (list preferred for safety)
            shell: Whether to use shell (avoid if possible)
            cwd: Working directory for command
            
        Returns:
            Tuple of (success, stdout, stderr)
        """
        self.logger.debug(f"Running command: {command}")
        
        if self.verbose:
            console.print(f"\n[{Style.INFO}]ℹ[/{Style.INFO}] {description}")
            console.print(f"[{Style.DIM}]Running: {command}[/{Style.DIM}]\n")
            
            result = subprocess.run(
                command,
                shell=shell,
                text=True,
                cwd=cwd,
                capture_output=True,
                errors='replace'
            )
            
            if result.stdout:
                console.print(result.stdout)
            if result.stderr:
                console.print(f"[{Style.WARNING}]{result.stderr}[/{Style.WARNING}]")
            
            return result.returncode == 0, result.stdout, result.stderr
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            task = progress.add_task(description, total=None)
            
            try:
                result = subprocess.run(
                    command,
                    shell=shell,
                    capture_output=True,
                    text=True,
                    cwd=cwd,
                    timeout=3600,  # 1 hour timeout
                    errors='replace'
                )
                
                progress.update(task, completed=True)
                
                if result.returncode == 0:
                    console.print(f"[{Style.SUCCESS}]✓ {description}[/{Style.SUCCESS}]")
                    return True, result.stdout, result.stderr
                else:
                    console.print(f"[{Style.ERROR}]✗ {description}[/{Style.ERROR}]")
                    console.print(f"\n[{Style.ERROR}]Error output:[/{Style.ERROR}]")
                    
                    # Show relevant error lines
                    error_lines = result.stderr.split('\n') if result.stderr else []
                    for line in error_lines[-15:]:  # Last 15 lines
                        if line.strip():
                            console.print(f"  [{Style.DIM}]{line}[/{Style.DIM}]")
                    
                    return False, result.stdout, result.stderr
                    
            except subprocess.TimeoutExpired:
                progress.update(task, completed=True)
                console.print(
                    f"[{Style.ERROR}]✗ {description} (timeout)[/{Style.ERROR}]"
                )
                return False, "", "Command timed out after 1 hour"
            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"[{Style.ERROR}]✗ {description}[/{Style.ERROR}]")
                console.print(f"[{Style.ERROR}]Exception: {str(e)}[/{Style.ERROR}]")
                return False, "", str(e)
    
    def validate_server_name(self, name: str) -> bool:
        """
        Validate server name for security and compatibility
        
        Args:
            name: Server name to validate
            
        Returns:
            True if valid
        """
        import re
        
        # Check for path traversal attempts
        if '..' in name or '/' in name or '\\' in name:
            return False
        
        # Check alphanumeric with dash and underscore
        if not re.match(r'^[a-zA-Z0-9_-]+$', name):
            return False
        
        # Check length (reasonable limits)
        if len(name) < 1 or len(name) > 64:
            return False
            
        return True
    
    def get_server_name(self) -> str:
        """
        Prompt user for server name with validation
        
        Returns:
            Validated server name
        """
        while True:
            self.clear_screen()
            console.print(f"[{Style.INFO} {Style.BOLD}]Step 1/5: Folder Name[/{Style.INFO} {Style.BOLD}]\n")
            
            name = Prompt.ask(
                f"[{Style.WARNING} {Style.BOLD}]Enter Folder Name[/{Style.WARNING} {Style.BOLD}]",
            )
            
            if self.validate_server_name(name):
                return name
            
            console.print(
                f"\n[{Style.ERROR}]Invalid name. Use alphanumeric characters, - or _ only "
                f"(1-64 chars, no path separators).[/{Style.ERROR}]"
            )
            console.print(f"\n[{Style.INFO}]Press Enter to try again...[/{Style.INFO}]")
            input()
    
    def select_game_mode(self) -> GameMode:
        """
        Display game modes and let user select one
        
        Returns:
            Selected GameMode
        """
        while True:
            self.clear_screen()
            console.print(f"[{Style.INFO} {Style.BOLD}]Step 2/5: Game Mode Selection[/{Style.INFO} {Style.BOLD}]\n")
            console.print(f"[white {Style.BOLD}]Available Game Modes:[/white {Style.BOLD}]\n")
            
            table = Table(show_header=True, header_style=f"{Style.INFO} {Style.BOLD}", box=box.ROUNDED)
            table.add_column("#", style=Style.INFO, width=4)
            table.add_column("Mode", style=f"white {Style.BOLD}")
            table.add_column("Description", style=Style.DIM)
            
            descriptions: Dict[str, str] = {
                "Teeworlds": "Classic Teeworlds",
                "DDNet": "Advanced race mode ",
                "zCatch": "Pvp catch mode"
            }
            
            for idx, mode in enumerate(self.GAME_MODES, 1):
                table.add_row(
                    str(idx),
                    mode.name,
                    descriptions.get(mode.name, "")
                )
            
            console.print(table)
            console.print()
            
            choice = Prompt.ask(
                f"[{Style.WARNING}]Select a mode (1-{len(self.GAME_MODES)})[/{Style.WARNING}]",
            )
            
            try:
                idx = int(choice)
                if 1 <= idx <= len(self.GAME_MODES):
                    return self.GAME_MODES[idx - 1]
            except ValueError:
                pass
            
            console.print(f"\n[{Style.ERROR}]Invalid choice. Please try again.[/{Style.ERROR}]")
            console.print(f"\n[{Style.INFO}]Press Enter to continue...[/{Style.INFO}]")
            input()
    
    def customize_build_options(self) -> Tuple[List[str], bool]:
        """
        Allow user to customize build options for selected game mode
        
        Returns:
            Tuple of (build command arguments, use_ninja flag)
        """
        self.clear_screen()
        console.print(f"[{Style.INFO} {Style.BOLD}]Step 3/5: Build Options[/{Style.INFO} {Style.BOLD}]\n")
        
        # Ask if user wants to customize
        if not Confirm.ask(
            f"[{Style.WARNING}]Do you want to customize build options?[/{Style.WARNING}]",
            default=False
        ):
            console.print(f"\n[{Style.INFO}]✓ Using default build options[/{Style.INFO}]")
            return self.selected_mode.build_opts.copy(), False
        
        # Get available options for this game mode
        available_options = self.AVAILABLE_BUILD_OPTIONS.get(self.selected_mode.name, [])
        
        if not available_options:
            console.print(
                f"\n[{Style.WARNING}]No customizable options available for {self.selected_mode.name}[/{Style.WARNING}]"
            )
            console.print(f"\n[{Style.INFO}]Press Enter to continue...[/{Style.INFO}]")
            input()
            return self.selected_mode.build_opts.copy(), False
        
        # Create a copy of options to track current values
        current_options = {opt.name: opt.current_value for opt in available_options}
        use_ninja = False
        
        while True:
            self.clear_screen()
            console.print(f"[{Style.INFO} {Style.BOLD}]Step 3/5: Build Options Customization[/{Style.INFO} {Style.BOLD}]\n")
            
            # Display available options with current values
            console.print(f"[white {Style.BOLD}]Available Build Options:[/white {Style.BOLD}]\n")
            
            table = Table(show_header=True, header_style=f"{Style.INFO} {Style.BOLD}", box=box.ROUNDED)
            table.add_column("#", style=Style.INFO, width=4)
            table.add_column("Option", style=f"white {Style.BOLD}", width=20)
            table.add_column("Description", style=Style.DIM, width=35)
            table.add_column("Current", style=Style.SUCCESS, width=10)
            
            for idx, opt in enumerate(available_options, 1):
                # Get current value (may have been changed)
                current_val = current_options.get(opt.name, opt.current_value)
                
                # Highlight changed values
                if current_val != opt.current_value:
                    value_display = f"[{Style.SUCCESS} {Style.BOLD}]{current_val}[/{Style.SUCCESS} {Style.BOLD}]"
                else:
                    value_display = current_val
                
                table.add_row(str(idx), opt.name, opt.description, value_display)
            
            console.print(table)
            console.print()
            
            # Instructions
            console.print(f"[{Style.INFO}]Instructions:[/{Style.INFO}]")
            console.print(f"  • Use number: [white {Style.BOLD}]<#>=<value>[/white {Style.BOLD}] → Example: [white]1=ON[/white]")
            console.print(f"  • Use name: [white {Style.BOLD}]<option>=<value>[/white {Style.BOLD}] → Example: [white]-DMYSQL=ON[/white]")
            console.print(f"  • For Ninja: [white {Style.BOLD}]<#>=ON/OFF[/white {Style.BOLD}] or [white]-GNinja[/white]")
            console.print(f"  • Type [white {Style.BOLD}]done[/white {Style.BOLD}] when finished\n")
            
            # Collect custom options
            user_input = Prompt.ask(
                f"[{Style.WARNING}]Enter option (number or name) or 'done'[/{Style.WARNING}]",
                default=""
            ).strip()
            
            if not user_input or user_input.lower() == 'done':
                # User is done customizing
                break
            
            # Parse the input
            if '=' in user_input:
                option_part, value = user_input.split('=', 1)
                option_part = option_part.strip()
                value = value.strip()
                
                # Check if it's a number
                if option_part.isdigit():
                    idx = int(option_part)
                    if 1 <= idx <= len(available_options):
                        opt = available_options[idx - 1]
                        
                        if opt.option_type == "generator":
                            # Handle generator options (like -GNinja)
                            if value.upper() in ["ON", "YES", "TRUE", "1"]:
                                current_options[opt.name] = "ON"
                                if opt.name == "-GNinja":
                                    use_ninja = True
                                console.print(f"[{Style.SUCCESS}]✓ Set {opt.name} = ON[/{Style.SUCCESS}]")
                            else:
                                current_options[opt.name] = "OFF"
                                if opt.name == "-GNinja":
                                    use_ninja = False
                                console.print(f"[{Style.SUCCESS}]✓ Set {opt.name} = OFF[/{Style.SUCCESS}]")
                        
                        elif opt.option_type == "boolean":
                            # Validate boolean values
                            if value.upper() not in ["ON", "OFF", "YES", "NO", "TRUE", "FALSE", "1", "0"]:
                                console.print(
                                    f"[{Style.ERROR}]Invalid boolean value. Use ON/OFF, YES/NO, TRUE/FALSE, or 1/0[/{Style.ERROR}]"
                                )
                                console.print(f"[{Style.INFO}]Press Enter to continue...[/{Style.INFO}]")
                                input()
                                continue
                            
                            # Normalize to ON/OFF
                            normalized = "ON" if value.upper() in ["ON", "YES", "TRUE", "1"] else "OFF"
                            current_options[opt.name] = normalized
                            console.print(f"[{Style.SUCCESS}]✓ Set {opt.name} = {normalized}[/{Style.SUCCESS}]")
                        
                        else:
                            # String type
                            current_options[opt.name] = value
                            console.print(f"[{Style.SUCCESS}]✓ Set {opt.name} = {value}[/{Style.SUCCESS}]")
                        
                        # Brief pause to show message
                        import time
                        time.sleep(0.5)
                    else:
                        console.print(f"[{Style.ERROR}]Invalid option number. Must be 1-{len(available_options)}[/{Style.ERROR}]")
                        console.print(f"[{Style.INFO}]Press Enter to continue...[/{Style.INFO}]")
                        input()
                
                else:
                    # It's an option name (like -DMYSQL)
                    option_exists = False
                    for opt in available_options:
                        if opt.name == option_part:
                            option_exists = True
                            
                            if opt.option_type == "generator":
                                # Handle generator options
                                if value.upper() in ["ON", "YES", "TRUE", "1"]:
                                    current_options[opt.name] = "ON"
                                    if opt.name == "-GNinja":
                                        use_ninja = True
                                    console.print(f"[{Style.SUCCESS}]✓ Set {opt.name} = ON[/{Style.SUCCESS}]")
                                else:
                                    current_options[opt.name] = "OFF"
                                    if opt.name == "-GNinja":
                                        use_ninja = False
                                    console.print(f"[{Style.SUCCESS}]✓ Set {opt.name} = OFF[/{Style.SUCCESS}]")
                            
                            elif opt.option_type == "boolean":
                                if value.upper() not in ["ON", "OFF", "YES", "NO", "TRUE", "FALSE", "1", "0"]:
                                    console.print(
                                        f"[{Style.ERROR}]Invalid boolean value. Use ON/OFF[/{Style.ERROR}]"
                                    )
                                    console.print(f"[{Style.INFO}]Press Enter to continue...[/{Style.INFO}]")
                                    input()
                                    continue
                                
                                normalized = "ON" if value.upper() in ["ON", "YES", "TRUE", "1"] else "OFF"
                                current_options[opt.name] = normalized
                                console.print(f"[{Style.SUCCESS}]✓ Set {opt.name} = {normalized}[/{Style.SUCCESS}]")
                            
                            else:
                                current_options[opt.name] = value
                                console.print(f"[{Style.SUCCESS}]✓ Set {opt.name} = {value}[/{Style.SUCCESS}]")
                            
                            import time
                            time.sleep(0.5)
                            break
                    
                    if not option_exists:
                        console.print(
                            f"[{Style.WARNING}]Warning: {option_part} is not in the standard options list[/{Style.WARNING}]"
                        )
                        console.print(f"[{Style.INFO}]Press Enter to continue...[/{Style.INFO}]")
                        input()
            
            elif user_input == "-GNinja":
                # Toggle Ninja on
                current_options["-GNinja"] = "ON"
                use_ninja = True
                console.print(f"[{Style.SUCCESS}]✓ Enabled Ninja generator[/{Style.SUCCESS}]")
                import time
                time.sleep(0.5)
            
            else:
                console.print(
                    f"[{Style.ERROR}]Invalid format. Use <#>=<value>, <option>=<value>, or 'done'[/{Style.ERROR}]"
                )
                console.print(f"[{Style.INFO}]Examples: 1=ON, -DMYSQL=ON, -GNinja, done[/{Style.INFO}]")
                console.print(f"\n[{Style.INFO}]Press Enter to continue...[/{Style.INFO}]")
                input()
        
        # Build final command with changed options only
        custom_options: List[str] = []
        
        for opt in available_options:
            current_val = current_options.get(opt.name, opt.current_value)
            
            # Only add if changed from default OR if it's a critical option
            if current_val != opt.current_value:
                if opt.option_type == "generator":
                    if current_val == "ON":
                        custom_options.append(opt.name)
                else:
                    custom_options.append(f"{opt.name}={current_val}")
        
        if custom_options:
            # Build command: cmake ../source/ [custom_options]
            build_command = ["cmake", "../source/"] + custom_options
            
            # Always add -DCLIENT=OFF and -DSERVER=ON if not already set
            has_client = any('-DCLIENT' in opt for opt in custom_options)
            has_server = any('-DSERVER' in opt for opt in custom_options)
            
            if not has_client:
                build_command.append("-DCLIENT=OFF")
            if not has_server:
                build_command.append("-DSERVER=ON")
            
            return build_command, use_ninja
        else:
            console.print(f"\n[{Style.INFO}]No changes made, using defaults[/{Style.INFO}]")
            console.print(f"\n[{Style.INFO}]Press Enter to continue...[/{Style.INFO}]")
            input()
            return self.selected_mode.build_opts.copy(), False
    
    def _get_install_command(self, dependencies: str) -> Optional[List[str]]:
        """
        Get the appropriate install command for detected package manager
        
        Args:
            dependencies: Space-separated list of dependencies
            
        Returns:
            Command list or None if unsupported
        """
        if self.package_manager == PackageManager.APT:
            cmd_prefix = ["sudo", "apt-get", "install", "-y"] if not self.is_root else ["apt-get", "install", "-y"]
            return cmd_prefix + dependencies.split()
        
        elif self.package_manager == PackageManager.DNF:
            cmd_prefix = ["sudo", "dnf", "install", "-y"] if not self.is_root else ["dnf", "install", "-y"]
            return cmd_prefix + dependencies.split()
        
        elif self.package_manager == PackageManager.YUM:
            cmd_prefix = ["sudo", "yum", "install", "-y"] if not self.is_root else ["yum", "install", "-y"]
            return cmd_prefix + dependencies.split()
        
        elif self.package_manager == PackageManager.PACMAN:
            cmd_prefix = ["sudo", "pacman", "-S", "--noconfirm"] if not self.is_root else ["pacman", "-S", "--noconfirm"]
            return cmd_prefix + dependencies.split()
        
        elif self.package_manager == PackageManager.ZYPPER:
            cmd_prefix = ["sudo", "zypper", "install", "-y"] if not self.is_root else ["zypper", "install", "-y"]
            return cmd_prefix + dependencies.split()
        
        return None
    
    def install_dependencies(self, use_ninja: bool = False) -> bool:
        """
        Install required dependencies
        
        Args:
            use_ninja: Whether to install ninja-build package
        
        Returns:
            True if successful
        """
        pm_value = self.package_manager.value
        
        if self.package_manager == PackageManager.UNKNOWN:
            console.print(
                f"[{Style.ERROR}]✗ Unsupported package manager. "
                f"Please install dependencies manually:[/{Style.ERROR}]"
            )
            # Show APT dependencies as example
            deps_to_show = f"{self.BASE_DEPS.get('apt-get', '')} {self.selected_mode.dependencies.get('apt-get', '')}"
            if use_ninja:
                deps_to_show += " ninja-build"
            console.print(f"  Example (APT): {deps_to_show}")
            
            if not Confirm.ask(
                f"\n[{Style.WARNING}]Continue anyway? (dependencies must be installed)[/{Style.WARNING}]"
            ):
                return False
            return True
        
        # Get base dependencies for this package manager
        base_deps = self.BASE_DEPS.get(pm_value, self.BASE_DEPS.get("apt-get", ""))
        
        # Get game mode dependencies for this package manager
        mode_deps = self.selected_mode.dependencies.get(pm_value, 
                                                        self.selected_mode.dependencies.get("apt-get", ""))
        
        # Combine dependencies
        all_deps = f"{base_deps} {mode_deps}"
        
        # Add ninja if needed
        if use_ninja:
            ninja_packages = {
                "apt-get": "ninja-build",
                "dnf": "ninja-build",
                "yum": "ninja-build",
                "pacman": "ninja",
                "zypper": "ninja",
            }
            ninja_pkg = ninja_packages.get(pm_value, "ninja-build")
            all_deps += f" {ninja_pkg}"
        
        install_cmd = self._get_install_command(all_deps)
        
        if not install_cmd:
            console.print(f"[{Style.ERROR}]Failed to create install command[/{Style.ERROR}]")
            return False
        
        success, _, _ = self.run_command(
            f"Installing dependencies for {self.selected_mode.name}" + (" with Ninja" if use_ninja else ""),
            install_cmd,
            shell=False
        )
        
        return success
    
    def clone_repository(self, source_path: Path) -> bool:
        """
        Clone git repository
        
        Args:
            source_path: Path to clone repository into
            
        Returns:
            True if successful
        """
        success, _, _ = self.run_command(
            f"Downloading {self.selected_mode.name}",
            ["git", "clone", "--recursive", self.selected_mode.url, "."],
            shell=False,
            cwd=source_path
        )
        
        if not success:
            return False
        
        # Validate git clone success
        if not (source_path / ".git").exists():
            console.print(
                f"[{Style.ERROR}]✗ Git repository not properly cloned[/{Style.ERROR}]"
            )
            return False
        
        console.print(
            f"[{Style.SUCCESS}]✓ Repository validated[/{Style.SUCCESS}]"
        )
        return True
    
    def configure_build(self, build_path: Path, build_opts: List[str]) -> bool:
        """
        Configure the build system
        
        Args:
            build_path: Build directory path
            build_opts: Build options to use
            
        Returns:
            True if successful
        """
        success, _, _ = self.run_command(
            "Initializing build system",
            build_opts,
            shell=False,
            cwd=build_path
        )
        
        return success
    
    def compile_server(self, build_path: Path, use_ninja: bool = False) -> bool:
        """
        Compile the server binary
        
        Args:
            build_path: Build directory path
            use_ninja: Whether to use Ninja build system
            
        Returns:
            True if successful
        """
        if use_ninja:
            # Use ninja instead of make
            success, _, _ = self.run_command(
                "Compiling binary with Ninja",
                ["ninja"],
                shell=False,
                cwd=build_path
            )
        else:
            # Limit cores to reasonable max for make
            cores = min(os.cpu_count() or 2, 16)
            
            success, _, _ = self.run_command(
                f"Compiling binary (using {cores} cores)",
                ["make", f"-j{cores}"],
                shell=False,
                cwd=build_path
            )
        
        return success
    
    def configure_server(self, build_path: Path) -> bool:
        """
        Configure the server after successful build
        
        Args:
            build_path: Build directory path
            
        Returns:
            True if configuration completed (or skipped)
        """
        self.clear_screen()
        console.print(f"[{Style.INFO} {Style.BOLD}]Server Configuration[/{Style.INFO} {Style.BOLD}]\n")
        
        # Ask user for configuration type
        console.print(f"[white {Style.BOLD}]Choose Configuration Type:[/white {Style.BOLD}]\n")
        
        table = Table(show_header=True, header_style=f"{Style.INFO} {Style.BOLD}", box=box.ROUNDED)
        table.add_column("#", style=Style.INFO, width=4)
        table.add_column("Type", style=f"white {Style.BOLD}")
        table.add_column("Description", style=Style.DIM)
        
        config_options = [
            ("Basic Configuration", "Configure essential settings (name, port, players, gametype)"),
            ("Advanced Configuration", "Configure all available settings (coming soon)"),
            ("No Configuration", "Skip configuration - use default settings")
        ]
        
        for idx, (name, desc) in enumerate(config_options, 1):
            table.add_row(str(idx), name, desc)
        
        console.print(table)
        console.print()
        
        while True:
            choice = Prompt.ask(
                f"[{Style.WARNING}]Select configuration type (1-3)[/{Style.WARNING}]",
                default="1"
            )
            
            try:
                idx = int(choice)
                if idx == 1:
                    return self._basic_configuration(build_path)
                elif idx == 2:
                    console.print(
                        f"[{Style.WARNING}]Advanced configuration is not yet implemented.[/{Style.WARNING}]"
                    )
                    console.print(
                        f"[{Style.INFO}]Falling back to basic configuration...[/{Style.INFO}]\n"
                    )
                    return self._basic_configuration(build_path)
                elif idx == 3:
                    console.print(
                        f"[{Style.INFO}]Skipping configuration - server will use default settings.[/{Style.INFO}]"
                    )
                    return True
                else:
                    console.print(f"[{Style.ERROR}]Invalid choice. Please select 1-3.[/{Style.ERROR}]")
            except ValueError:
                console.print(f"[{Style.ERROR}]Invalid input. Please enter a number.[/{Style.ERROR}]")
    
    def _basic_configuration(self, build_path: Path) -> bool:
        """
        Handle basic configuration
        
        Args:
            build_path: Build directory path
            
        Returns:
            True if configuration saved successfully
        """
        # Get settings for current game mode
        settings = self.BASIC_CONFIG_SETTINGS.get(self.selected_mode.name, [])
        
        if not settings:
            console.print(
                f"[{Style.ERROR}]No configuration settings found for {self.selected_mode.name}[/{Style.ERROR}]"
            )
            return False
        
        config_values: Dict[str, str] = {}
        
        while True:
            self.clear_screen()
            console.print(f"[{Style.INFO} {Style.BOLD}]Basic Configuration[/{Style.INFO} {Style.BOLD}]\n")
            
            # Collect configuration values
            console.print(f"[{Style.INFO}]Enter configuration values:[/{Style.INFO}]\n")
            
            for setting in settings:
                while True:
                    prompt_text = f"[{Style.WARNING}]{setting.prompt}[/{Style.WARNING}]"
                    if setting.description:
                        console.print(f"  [{Style.DIM}]{setting.description}[/{Style.DIM}]")
                    
                    value = Prompt.ask(
                        prompt_text,
                        default=setting.default
                    )
                    
                    # Basic validation for port
                    if setting.key == "sv_port":
                        try:
                            port = int(value)
                            if port < 1024 or port > 65535:
                                console.print(
                                    f"[{Style.ERROR}]Port must be between 1024 and 65535[/{Style.ERROR}]"
                                )
                                continue
                        except ValueError:
                            console.print(
                                f"[{Style.ERROR}]Port must be a valid number[/{Style.ERROR}]"
                            )
                            continue
                    
                    # Basic validation for max_clients
                    if setting.key == "sv_max_clients":
                        try:
                            clients = int(value)
                            if clients < 1 or clients > 256:
                                console.print(
                                    f"[{Style.ERROR}]Max clients must be between 1 and 256[/{Style.ERROR}]"
                                )
                                continue
                        except ValueError:
                            console.print(
                                f"[{Style.ERROR}]Max clients must be a valid number[/{Style.ERROR}]"
                            )
                            continue
                    
                    config_values[setting.key] = value
                    break
                
                console.print()
            
            # Display entered configuration
            console.print(f"[{Style.INFO} {Style.BOLD}]Configuration Summary:[/{Style.INFO} {Style.BOLD}]\n")
            
            summary_table = Table(show_header=True, header_style=f"{Style.INFO} {Style.BOLD}", box=box.ROUNDED)
            summary_table.add_column("Setting", style=f"white {Style.BOLD}")
            summary_table.add_column("Value", style=Style.INFO)
            
            for setting in settings:
                summary_table.add_row(setting.prompt, config_values[setting.key])
            
            console.print(summary_table)
            console.print()
            
            # Confirm values
            if Confirm.ask(
                f"[{Style.WARNING}]Are these values correct?[/{Style.WARNING}]",
                default=True
            ):
                break
            else:
                console.print(
                    f"\n[{Style.INFO}]Let's re-enter the configuration...[/{Style.INFO}]\n"
                )
                config_values.clear()
        
        # Save configuration to file
        return self._save_config_file(build_path, config_values, "basic_config.cfg")
    
    def _save_config_file(self, build_path: Path, config_values: Dict[str, str], filename: str) -> bool:
        """
        Save configuration to a file
        
        Args:
            build_path: Build directory path
            config_values: Dictionary of configuration key-value pairs
            filename: Name of the configuration file
            
        Returns:
            True if file saved successfully
        """
        config_path = build_path / filename
        
        try:
            with open(config_path, 'w') as f:
                f.write("// Teeworlds Server Configuration\n")
                f.write(f"// Generated by TEEMAKE v3.0\n")
                f.write(f"// Game Mode: {self.selected_mode.name}\n")
                f.write("\n")
                
                for key, value in config_values.items():
                    # Add quotes for string values, keep numbers unquoted
                    if key in ["sv_port", "sv_max_clients"]:
                        f.write(f"{key} {value}\n")
                    else:
                        f.write(f'{key} "{value}"\n')
            
            console.print()
            console.print(
                f"[{Style.SUCCESS}]✓ Configuration saved to: {config_path}[/{Style.SUCCESS}]"
            )
            self.logger.info(f"Configuration saved to {config_path}")
            return True
            
        except Exception as e:
            console.print(
                f"[{Style.ERROR}]✗ Failed to save configuration: {e}[/{Style.ERROR}]"
            )
            self.logger.error(f"Failed to save configuration: {e}")
            return False
    
    def build_server(self) -> Optional[Path]:
        """
        Main build process
        
        Returns:
            Path to build directory if successful, None otherwise
        """
        # Get server name
        self.server_name = self.get_server_name()
        
        # Select game mode
        self.selected_mode = self.select_game_mode()
        
        # Customize build options
        custom_build_opts, use_ninja = self.customize_build_options()
        
        # Ask about verbose logging
        self.clear_screen()
        console.print(f"[{Style.INFO} {Style.BOLD}]Step 4/5: Build Configuration[/{Style.INFO} {Style.BOLD}]\n")
        
        self.verbose = Confirm.ask(
            f"[{Style.WARNING}]Show detailed build logs?[/{Style.WARNING}]",
        )
        
        # Update logging level if changed
        if self.verbose:
            logging.getLogger().setLevel(logging.DEBUG)
        
        # Display build configuration summary
        self.clear_screen()
        console.print(f"[{Style.INFO} {Style.BOLD}]Step 4/5: Configuration Summary[/{Style.INFO} {Style.BOLD}]\n")
        console.print(Panel(
            f"[white {Style.BOLD}]Server Name:[/white {Style.BOLD}] {self.server_name}\n"
            f"[white {Style.BOLD}]Game Mode:[/white {Style.BOLD}] {self.selected_mode.name}\n"
            f"[white {Style.BOLD}]Build System:[/white {Style.BOLD}] {'Ninja' if use_ninja else 'Make'}\n"
            f"[white {Style.BOLD}]Package Manager:[/white {Style.BOLD}] {self.package_manager.value}\n"
            f"[white {Style.BOLD}]Verbose Logs:[/white {Style.BOLD}] {'Yes' if self.verbose else 'No'}",
            title=f"[{Style.INFO}]Build Configuration[/{Style.INFO}]",
            border_style="purple"
        ))
        console.print()
        
        # Check disk space
        if not self.check_disk_space():
            console.print(f"\n[{Style.INFO}]Press Enter to exit...[/{Style.INFO}]")
            input()
            return None
        
        # Ensure sudo privileges (if not root)
        if not self.ensure_sudo():
            console.print(f"\n[{Style.INFO}]Press Enter to exit...[/{Style.INFO}]")
            input()
            return None
        
        console.print()
        console.print(f"[{Style.INFO}]Press Enter to start building...[/{Style.INFO}]")
        input()
        
        # Clear screen for build process
        self.clear_screen()
        console.print(f"[{Style.INFO} {Style.BOLD}]Step 5/5: Building Server[/{Style.INFO} {Style.BOLD}]\n")
        
        # Install dependencies (including ninja if needed)
        if not self.install_dependencies(use_ninja):
            console.print(f"[{Style.ERROR}]Failed to install dependencies[/{Style.ERROR}]")
            console.print(f"\n[{Style.INFO}]Press Enter to exit...[/{Style.INFO}]")
            input()
            return None
        
        # Create directory structure
        server_path = Path(self.server_name)
        source_path = server_path / "source"
        build_path = server_path / "server"
        
        try:
            source_path.mkdir(parents=True, exist_ok=True)
            build_path.mkdir(parents=True, exist_ok=True)
            
            # Convert to absolute paths
            source_path = source_path.absolute()
            build_path = build_path.absolute()
            start_dir = Path.cwd().absolute()
            
            self.logger.debug(f"Source path: {source_path}")
            self.logger.debug(f"Build path: {build_path}")
            
        except Exception as e:
            console.print(f"[{Style.ERROR}]Failed to create directories: {e}[/{Style.ERROR}]")
            return None
        
        # Use try/finally to ensure we return to original directory
        try:
            # Clone repository
            if not self.clone_repository(source_path):
                console.print(f"[{Style.ERROR}]Failed to download source code[/{Style.ERROR}]")
                return None
            
            # Configure build with custom options
            if not self.configure_build(build_path, custom_build_opts):
                console.print(f"[{Style.ERROR}]Failed to initialize build[/{Style.ERROR}]")
                return None
            
            # Compile with use_ninja flag
            if not self.compile_server(build_path, use_ninja):
                console.print(f"[{Style.ERROR}]Failed to compile[/{Style.ERROR}]")
                return None
            
            # Return build_path for configuration
            return build_path
            
        finally:
            # Always return to starting directory
            os.chdir(start_dir)
            self.logger.debug(f"Returned to directory: {start_dir}")
    
    def run(self) -> int:
        """
        Main entry point
        
        Returns:
            Exit code (0 for success)
        """
        self.show_header()
        
        try:
            build_path = self.build_server()
            
            if build_path:
                self.clear_screen()
                console.print(f"[{Style.SUCCESS} {Style.BOLD}]✓ BUILD COMPLETE![/{Style.SUCCESS} {Style.BOLD}]\n")
                console.print(Panel(
                    f"Server build finished in: [white {Style.BOLD}]./{self.server_name}[/white {Style.BOLD}]",
                    border_style=Style.SUCCESS,
                    box=box.ROUNDED
                ))
                console.print()
                console.print(f"[{Style.INFO}]Press Enter to configure server...[/{Style.INFO}]")
                input()
                
                # Configure server
                self.configure_server(build_path)
                
                # Final completion screen
                self.clear_screen()
                console.print(f"[{Style.SUCCESS} {Style.BOLD}]✓ Installation Complete![/{Style.SUCCESS} {Style.BOLD}]\n")
                console.print(Panel(
                    f"[white]Server:[/white] [white {Style.BOLD}]{self.server_name}[/white {Style.BOLD}]\n"
                    f"[white]Location:[/white] [white {Style.BOLD}]./{self.server_name}/server/[/white {Style.BOLD}]\n"
                    f"[white]Config:[/white] [white {Style.BOLD}]basic_config.cfg[/white {Style.BOLD}]\n\n"
                    f"[{Style.INFO}]To start your server:[/{Style.INFO}]\n"
                    f"  [white {Style.BOLD}]cd {self.server_name}/server[/white {Style.BOLD}]\n"
                    f"  [white {Style.BOLD}]./server_binary -f your_config.cfg[/white {Style.BOLD}]",
                    title=f"[{Style.SUCCESS}]Ready to Launch[/{Style.SUCCESS}]",
                    border_style=Style.SUCCESS,
                    box=box.DOUBLE
                ))
                console.print(f"\n[{Style.INFO}]Enjoy your Teeworlds server![/{Style.INFO}]\n")
                return 0
            else:
                console.print()
                console.print(
                    f"[{Style.ERROR} {Style.BOLD}]Build failed. "
                    f"Please check the errors above.[/{Style.ERROR} {Style.BOLD}]\n"
                )
                return 1
                
        except KeyboardInterrupt:
            console.print(
                f"\n\n[{Style.WARNING}]⚠  Build cancelled by user[/{Style.WARNING}]\n"
            )
            return 130
        except Exception as e:
            console.print(
                f"\n[{Style.ERROR} {Style.BOLD}]Unexpected error: {e}[/{Style.ERROR} {Style.BOLD}]\n"
            )
            self.logger.exception("Unexpected error occurred")
            return 1


def main() -> None:
    """Application entry point"""
    builder = TeemakeBuilder()
    sys.exit(builder.run())


if __name__ == "__main__":
    main()
