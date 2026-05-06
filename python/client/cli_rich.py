import re
import time
import os
import sys

# Rich Imports
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.prompt import Prompt
from rich.layout import Layout
from rich.style import Style
from rich import box

# Local Imports
try:
    from client.interface import *
    from client.core import QUARPCore
    from client.utils import ASCII_ART
except ModuleNotFoundError:
    from .interface import *
    from .core import QUARPCore
    from .utils import ASCII_ART

class QUARPConsoleRich:
    """
    Rich Console View/Controller for QUARP.
    Wraps QUARPCore with a UI using the 'rich' library.
    """
    def __init__(self, server_ip=None, server_port=None, core_instance=None):
        if core_instance:
            self.core = core_instance
        else:
            if server_ip is None or server_port is None:
                raise ValueError("If no core_instance is provided, server_ip and server_port are required.")
            self.core = QUARPCore(server_ip, server_port)
        
        # Setup Rich Console
        self.console = Console()
        self.prompt_text = "[bold cyan]QUARP[/] [bold yellow]>[/] "
        self.error_style = Style(color="red", bold=True)
        self.success_style = Style(color="green", bold=True)
        self.info_style = Style(color="cyan")
        self.warning_style = Style(color="yellow")

        # Register Core Callbacks
        self.core.on_connected = self.on_connected
        self.core.on_disconnected = self.on_disconnected
        self.core.on_message_received = self.on_message_received
        self.core.on_error = self.on_error

        # Register Logic Handlers (override default only if not already customized)
        map_cmd_printer = {
            FE_INCOMING_MSG: ("_handle_incoming_msg", self.handle_incoming_msg_print),
            FE_ONE_WAY_RANGE_CMD: ("_handle_one_way_range", self.handle_one_way_range_print),
            FE_TRACKING_CMD: ("_handle_tracking", self.handle_tracking_print),
            FE_ACK_CMD: ("_handle_ack", self.handle_ack_print),
            FE_NACK_CMD: ("_handle_nack", self.handle_nack_print)
        }

        for cmd, (start_name, print_handler) in map_cmd_printer.items():
            current_handler = self.core.handlers.get(cmd)
            # If the handler is the default one (checking by name convention), we replace it with our printer.
            # If it has been changed (e.g. by CroceClient), we prefer the custom one.
            if current_handler and current_handler.__name__ == start_name:
                self.core.register_handler(cmd, print_handler)
        
        # Command Definitions (View Logic: regex parsing)
        self.available_commands = {
            FE_SEND_CMD: ("[cmd][data] -> send data packet.",
                          rf'^{FE_SEND_CMD}\s+(.+)$',
                          self.send_command_handler),
            FE_SET_TRANSMISSION_LEVEL_CMD: ("[cmd][data] -> set transmission level. Accepted values 0-3.",
                                            rf'^{FE_SET_TRANSMISSION_LEVEL_CMD}\s+([0-3])$',
                                            self.set_transmission_level_handler),
            FE_SET_SYNCHRONIZATION_CHANNEL_CMD: ("[cmd][data] -> set the channel to use for synchronization. Accepted values 0-3.",
                                            rf'^{FE_SET_SYNCHRONIZATION_CHANNEL_CMD}\s+([0-3])$',
                                            self.set_synchronization_channel_handler),
            FE_SET_DEMOD_CHANNEL_CMD: ("[cmd][data] -> set the channel to use for demodulation. Accepted values 0-3.",
                                       rf'^{FE_SET_DEMOD_CHANNEL_CMD}\s+([0-3])$',
                                       self.set_demodulation_channel_handler),
            FE_SET_VOL_CMD: ("[cmd][data] -> set transmission volume level. Accepted values 0.0-1.0.",
                             rf'^{FE_SET_VOL_CMD}\s+(0(?:\.\d+)?|1(?:\.0+)?)$',
                             self.set_transmission_volume_handler),
            FE_SET_CORR1_CMD: ("[cmd][data] -> set correlation threshold first encounter. Accepted values 0.0-1.0.",
                               rf'^{FE_SET_CORR1_CMD}\s+(0(?:\.\d+)?|1(?:\.0+)?)$',
                               self.set_correlation_threshold1_handler),
            FE_SET_CORR2_CMD: ("[cmd][data] -> set correlation threshold second encounter. Accepted values 0.0-1.0.",
                               rf'^{FE_SET_CORR2_CMD}\s+(0(?:\.\d+)?|1(?:\.0+)?)$',
                               self.set_correlation_threshold2_handler),
            FE_SET_RECEPTION_VOLUME_CMD: ("[cmd][data] -> set reception volume level. Accepted values 0.0-1.0.",
                                          rf'^{FE_SET_RECEPTION_VOLUME_CMD}\s+(0(?:\.\d+)?|1(?:\.0+)?)$',
                                          self.set_reception_volume_handler),
            FE_GET_TRANSMISSION_LEVEL_CMD: ("[cmd] -> get transmission level.",
                                            rf'^{FE_GET_TRANSMISSION_LEVEL_CMD}$',
                                            self.get_transmission_level_handler),
            FE_GET_SYNCHRONIZATION_CHANNEL_CMD: ("[cmd] -> get the index of the channel in use for synchronization.",
                                                 rf'^{FE_GET_SYNCHRONIZATION_CHANNEL_CMD}$',
                                                 self.get_synchronization_channel_handler),
            FE_GET_DEMOD_CHANNEL_CMD: ("[cmd] -> get the index of the channel in use for demodulation.",
                                       rf'^{FE_GET_DEMOD_CHANNEL_CMD}$',
                                       self.get_demodulation_channel_handler),
            FE_GET_RECEPTION_VOLUME_CMD: ("[cmd] -> get transmission level.",
                                          rf'^{FE_GET_RECEPTION_VOLUME_CMD}$',
                                          self.get_reception_volume_handler),
            FE_GET_VOL_CMD: ("[cmd] -> get volume level.",
                             rf'^{FE_GET_VOL_CMD}$',
                             self.get_transmission_volume_handler),
            FE_GET_CORR1_CMD: ("[cmd] -> get correlation threshold first encounter.",
                               rf'^{FE_GET_CORR1_CMD}$',
                               self.get_correlation_threshold1_handler),
            FE_GET_CORR2_CMD: ("[cmd] -> get correlation threshold second encounter.",
                               rf'^{FE_GET_CORR2_CMD}$',
                               self.get_correlation_threshold2_handler),
            FE_TURN_LOG_ON_OFF_CMD: ("[cmd][mode]->turn loggin mode on or off. Accepted values on/off.",
                                     rf'^{FE_TURN_LOG_ON_OFF_CMD}\s+(?:on|off)$',
                                     self.enable_disable_log_handler),
            FE_START_BER_TEST_CMD: ("[cmd] -> start a ber test.",
                                    rf'^{FE_START_BER_TEST_CMD}\s+[1-9]\d*\s*$',
                                    self.start_ber_test_handler),
            FE_SET_INTERNAL_MODE_CMD: ("[cmd][mode][node_id?] -> set internal mode. Use 'stmd 0|1|2' to set modes 0, 1, 2.\n\t\t'stmd 0' -> enter modem mode.\n\t\t'stmd 1 <node_id>' -> enter pinger mode on a specific node id.\n\t\t'stmd 2' -> enter idrophone node through usb.",
                                       rf'^{FE_SET_INTERNAL_MODE_CMD}\s+(?:0|2|3|1\s+(.+))$',
                                       self.set_internal_mode_handler),
            FE_HELP_CMD: ("help [Command] -> show the list of available commands or details about a specific command.",
                          rf'^{FE_HELP_CMD}(?:\s+\w+)?$',
                          self.help_handler)
        }

    def run(self):
        self.console.clear()
        self.print_banner()
        
        with self.console.status("[bold green]Connecting to QUARP Server...", spinner="dots"):
            connected = self.core.connect()
            
        if connected:
            self.input_loop()
        else:
            self.console.print("[bold red]Failed to start. Server might be down.[/bold red]")

    def print_banner(self):
        panel = Panel(
            Text(ASCII_ART, justify="center", style="bold cyan"),
            subtitle="[dim]Advanced Acoustic Communication System[/dim]",
            border_style="blue",
            box=box.DOUBLE
        )
        self.console.print(panel)

    def input_loop(self):
        self.console.print(f"[bold green]Session Started at {time.strftime('%H:%M:%S')}[/bold green]")
        self.console.print("[dim]Type 'help' for a list of commands.[/dim]")
        
        while self.core.running:
            try:
                # Use Rich Prompt
                user_text = Prompt.ask(self.prompt_text).strip()
                self.process_command_string(user_text)
            except EOFError:
                break
            except KeyboardInterrupt:
                self.console.print("\n[bold red]Stopping...[/bold red]")
                self.core.disconnect()
                break

    def process_command_string(self, cmd_string: str):
        cmd_string = cmd_string.strip()
        if not cmd_string: return

        tokens = cmd_string.split()
        cmd_key = tokens[0]
        
        matched = False
        if cmd_key in self.available_commands:
            descr, pattern, handler = self.available_commands[cmd_key]
            if re.match(pattern, cmd_string):
                try:
                    handler(cmd_string) 
                except Exception as e:
                    self.console.print(f"[bold red]Error executing command: {e}[/bold red]")
                matched = True
            else:
                self.console.print(Panel(f"[bold red]Command Usage Error:[/bold red] {cmd_key}\n[yellow]{descr}[/yellow]", border_style="red"))
                matched = True
        
        if not matched:
            self.console.print(f"[bold red]Unknown command:[/bold red] [white]{cmd_key}[/white]. Type [bold green]{FE_HELP_CMD}[/bold green] for details.")

    # =========================================================================
    # --- CALLBACKS (VIEW UPDATES) ---
    # =========================================================================
    
    def print_async(self, renderable):
        """Helper to print async messages without breaking the prompt visually."""
        # We print a carriage return + clear + renderable + newline + prompt
        # Actually rich print usually ends with newline.
        # self.console.print moves to next line. 
        # We want to clear the current "QUARP > " which might be there.
        
        # Strategy:
        # \r to go to start
        # Print renderable (which puts a new line)
        # Reprint prompt (no newline)
        
        # Note: If user was typing, their text might be visually hidden or appended crazily
        # but this solves the empty prompt issue.
        self.console.print(f"\r", end="") 
        self.console.print(renderable)
        self.console.print(self.prompt_text, end="")        
    
    def on_connected(self, ip, port):
        self.print_async(f"[bold green]\u2705 Connected successfully to {ip}:{port}[/bold green]")

    def on_disconnected(self):
        self.print_async("[bold red]\u274C Disconnected from server.[/bold red]")

    def on_error(self, msg):
        self.print_async(f"[bold red]System Error: {msg}[/bold red]")

    def on_message_received(self, packet):
        pass

    # Specific Packet Print Handlers
    # Specific Packet Print Handlers
    def handle_incoming_msg_print(self, packet):
        if packet.crc_check:
            print()
            # Good Packet
            try:
                payload_str = bytes(packet.payload).decode('utf-8', errors='replace')
            except:
                payload_str = str(packet.payload)
            
            # Use getattr to safely access pre_fec if available, default to N/A
            pre_fec = getattr(packet, 'pre_fec', 'N/A')

            panel_content = f"[bold green]DATA RECEIVED \u2705[/bold green]\n\n" \
                            f"[bold white]{payload_str}[/bold white]\n\n" \
                            f"[dim]SNR:[/dim] {packet.snr:.2f} dB  |  " \
                            f"[dim]Pre-FEC:[/dim] {pre_fec}  |  " \
                            f"[dim]Timestamp:[/dim] {time.strftime('%H:%M:%S', time.localtime(packet.time_stamp)) if packet.time_stamp else 'N/A'}"
            
            self.print_async(Panel(panel_content, border_style="green", box=box.ROUNDED))
            
        else:
            print()
            # Bad Packet
            panel_content = f"[bold red]DATA RECEIVED (CRC FAIL) \u274C[/bold red]\n\n" \
                            f"[dim]Raw:[/dim] {packet.payload}\n\n" \
                            f"[dim]SNR:[/dim] {packet.snr:.2f} dB"
            self.print_async(Panel(panel_content, border_style="red", box=box.ROUNDED))

    def handle_one_way_range_print(self, packet):
        self.print_async(f"[cyan]Range Update:[/cyan] ID={packet.range_id}, Time={packet.time_stamp}")

    def handle_tracking_print(self, packet):
        # Create a nice table for tracking info
        table = Table(title="[bold magenta]Tracking Update[/bold magenta]", box=box.ROUNDED, show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        if hasattr(packet, 'tracking_shifts'):
             table.add_row("Shifts", str(packet.tracking_shifts))
        if hasattr(packet, 'tracking_factors'):
             table.add_row("Factors", str(packet.tracking_factors))
        
        # Add IMU data (Yaw, Pitch, Roll) if available
        if hasattr(packet, 'yaw'):
            table.add_row("Yaw", f"{packet.yaw:.2f}" if isinstance(packet.yaw, (int, float)) else str(packet.yaw))
        if hasattr(packet, 'pitch'):
            table.add_row("Pitch", f"{packet.pitch:.2f}" if isinstance(packet.pitch, (int, float)) else str(packet.pitch))
        if hasattr(packet, 'roll'):
            table.add_row("Roll", f"{packet.roll:.2f}" if isinstance(packet.roll, (int, float)) else str(packet.roll))
        
        self.print_async(table)

    def handle_ack_print(self, packet):
        # Pretty print based on packet content if possible, or just standard
        self.print_async(f"[green]ACK:[/green] {str(packet)}")

    def handle_nack_print(self, packet):
        self.print_async(f"[bold red]NACK:[/bold red] Command Rejected \u274C")


    # =========================================================================
    # --- COMMAND INPUT HANDLERS (PARSE & CALL CORE) ---
    # =========================================================================

    def send_command_handler(self, data):
        tokens = data.split()
        msg = " ".join(tokens[1:]) 
        if not msg: msg = tokens[1]
        self.core.send_message(msg)
        self.console.print(f"[dim]Sending message: {msg}[/dim]")

    def set_transmission_level_handler(self, data):
        tokens = data.split()
        val = int(tokens[1])
        self.core.set_transmission_level(val)
        self.console.print(f"[dim]Setting TX Level to {val}[/dim]")

    def get_transmission_level_handler(self, data):
        self.core.get_transmission_level()

    def set_synchronization_channel_handler(self, data):
        tokens = data.split()
        val = int(tokens[1])
        self.core.set_sync_channel(val)
        self.console.print(f"[dim]Setting Sync Channel to {val}[/dim]")

    def get_synchronization_channel_handler(self, data):
        self.core.get_sync_channel()

    def set_demodulation_channel_handler(self, data):
        tokens = data.split()
        val = int(tokens[1])
        self.core.set_demod_channel(val)
        self.console.print(f"[dim]Setting Demod Channel to {val}[/dim]")

    def get_demodulation_channel_handler(self, data):
        self.core.get_demod_channel()

    def set_transmission_volume_handler(self, data):
        tokens = data.split()
        val = float(tokens[1])
        self.core.set_tx_volume(val)
        self.console.print(f"[dim]Setting TX Volume to {val}[/dim]")

    def get_transmission_volume_handler(self, data):
        self.core.get_tx_volume()

    def set_reception_volume_handler(self, data):
        tokens = data.split()
        val = float(tokens[1])
        self.core.set_rx_volume(val)
        self.console.print(f"[dim]Setting RX Volume to {val}[/dim]")

    def get_reception_volume_handler(self, data):
        self.core.get_rx_volume()

    def set_correlation_threshold1_handler(self, data):
        tokens = data.split()
        val = float(tokens[1])
        self.core.set_corr_threshold1(val)
        self.console.print(f"[dim]Setting Corr Threshold 1 to {val}[/dim]")

    def get_correlation_threshold1_handler(self, data):
        self.core.get_corr_threshold1()

    def set_correlation_threshold2_handler(self, data):
        tokens = data.split()
        val = float(tokens[1])
        self.core.set_corr_threshold2(val)
        self.console.print(f"[dim]Setting Corr Threshold 2 to {val}[/dim]")

    def get_correlation_threshold2_handler(self, data):
        self.core.get_corr_threshold2()

    def enable_disable_log_handler(self, data):
        tokens = data.split()
        enable = (tokens[1] == 'on')
        self.core.enable_log(enable)
        self.console.print(f"[dim]Logging {'Enabled' if enable else 'Disabled'}[/dim]")

    def start_ber_test_handler(self, data):
        tokens = data.split()
        val = int(tokens[1])
        self.core.start_ber_test(val)
        self.console.print(f"[dim]Starting BER Test for {val} seconds[/dim]")

    def set_internal_mode_handler(self, data):
        tokens = data.split()
        mode = int(tokens[1])
        node_id = int(tokens[2]) if len(tokens) > 2 else None
        self.core.set_internal_mode(mode, node_id)
        self.console.print(f"[dim]Setting Internal Mode to {mode} (Node: {node_id})[/dim]")

    def help_handler(self, data):
        tokens = data.split()
        if len(tokens) == 1:
            table = Table(title="Available Commands", box=box.ROUNDED, show_header=True, header_style="bold magenta")
            table.add_column("Command", style="cyan", no_wrap=True)
            table.add_column("Description", style="white")

            for cmd, (descr, _, _) in self.available_commands.items():
                short_desc = descr.split('\n')[0]
                table.add_row(cmd, short_desc)
            
            self.console.print(table)
            
        elif len(tokens) == 2:
            cmd = tokens[1]
            if cmd in self.available_commands:
                descr, pattern, _ = self.available_commands[cmd]
                
                panel = Panel(
                    f"[bold]Description:[/bold]\n{descr}\n\n[bold]Regex Pattern:[/bold]\n[dim]{pattern}[/dim]",
                    title=f"Command: [cyan]{cmd}[/cyan]",
                    border_style="green",
                    box=box.ROUNDED
                )
                self.console.print(panel)
            else:
                 self.console.print(f"[bold red]Command “{cmd}” unrecognized.[/bold red]")
        else:
             self.console.print("[bold red]Help command misspelled.[/bold red]")
