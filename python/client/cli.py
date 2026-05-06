import re
import time
import os
import struct
import sys

# Add parent to path for imports
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# from high_level_interface import *
try:
    from client.interface import *
    from client.core import QUARPCore
    from client.utils import ASCII_ART
except ModuleNotFoundError:
    from .interface import *
    from .core import QUARPCore
    from .utils import ASCII_ART

class QUARPConsole:
    """
    Console View/Controller for QUARP.
    Wraps QUARPCore and handles user input/output.
    """
    def __init__(self, server_ip=None, server_port=None, core_instance=None):
        if core_instance:
            self.core = core_instance
        else:
            if server_ip is None or server_port is None:
                raise ValueError("If no core_instance is provided, server_ip and server_port are required.")
            self.core = QUARPCore(server_ip, server_port)
        
        # Register Core Callbacks
        # Register Core Callbacks (Chain with existing ones if present)
        self._chain_callback('on_connected', self.on_connected)
        self._chain_callback('on_disconnected', self.on_disconnected)
        self._chain_callback('on_message_received', self.on_message_received)
        self._chain_callback('on_error', self.on_error)

    def _chain_callback(self, attr_name, new_cb):
        """Helper to chain a new callback with an existing one."""
        old_cb = getattr(self.core, attr_name, None)
        if old_cb:
            def chained(*args, **kwargs):
                old_cb(*args, **kwargs)
                new_cb(*args, **kwargs)
            setattr(self.core, attr_name, chained)
        else:
            setattr(self.core, attr_name, new_cb)

        # Register Logic Handlers (override default only if not already customized)
        # We assume custom handlers do NOT start with "_" (default Core handlers are _handle_...)
        
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
        os.system("cls" if os.name == "nt" else "clear")
        print(ASCII_ART)
        if self.core.connect():
            self.input_loop()
        else:
            print("Failed to start.")

    def input_loop(self):
        while self.core.running:
            try:
                user_text = input("Command: ").strip()
                self.process_command_string(user_text)
            except EOFError:
                break
            except KeyboardInterrupt:
                print("\nStopping...")
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
                    handler(cmd_string) # Call the handler which calls core
                except Exception as e:
                    print(f"Error executing command: {e}")
                matched = True
            else:
                print(f"[Error] Command {cmd_key} usage mismatch.")
                print(descr)
                matched = True
        
        if not matched:
            print(f"[Error] Command {cmd_key} unknown. Type '{FE_HELP_CMD}' for details.")

    # =========================================================================
    # --- CALLBACKS (VIEW UPDATES) ---
    # =========================================================================
    
    def on_connected(self, ip, port):
        print(f"Connected to {ip}:{port}")

    def on_disconnected(self):
        print("Disconnected.")

    def on_error(self, msg):
        print(f"ERROR: {msg}")

    def on_message_received(self, packet):
        # Generic catch-all if needed, but we used specific handlers below
        pass

    # Specific Packet Print Handlers
    def handle_incoming_msg_print(self, packet):
        if packet.crc_check:
            print(f"\n[Data received]: {bytes(packet.payload)} \u2705")
            print(f"SNR = {packet.snr}")
            if packet.time_stamp:
                print(f"ts = {time.strftime('%H:%M:%S', time.localtime(packet.time_stamp))}")
            print(f"pre_fec = {packet.pre_fec}")
        else:
            print(f"\n[Data received]: {packet.payload} \u274C")
            print(f"SNR = {packet.snr}")

    def handle_one_way_range_print(self, packet):
        print(f"range packet from id = {packet.range_id} with ts = {packet.time_stamp}")

    def handle_tracking_print(self, packet):
        print(f"Tracking packet received: Shifts={packet.tracking_shifts}, Factors={packet.tracking_factors}")

    def handle_ack_print(self, packet):
        print(packet) # ExternalPacket __str__

    def handle_nack_print(self, packet):
        print("[Command rejected]\u274C")


    # =========================================================================
    # --- COMMAND INPUT HANDLERS (PARSE & CALL CORE) ---
    # =========================================================================

    def send_command_handler(self, data):
        tokens = data.split()
        msg = " ".join(tokens[1:]) 
        if not msg: msg = tokens[1]
        self.core.send_message(msg)

    def set_transmission_level_handler(self, data):
        tokens = data.split()
        self.core.set_transmission_level(int(tokens[1]))

    def get_transmission_level_handler(self, data):
        self.core.get_transmission_level()

    def set_synchronization_channel_handler(self, data):
        tokens = data.split()
        self.core.set_sync_channel(int(tokens[1]))

    def get_synchronization_channel_handler(self, data):
        self.core.get_sync_channel()

    def set_demodulation_channel_handler(self, data):
        tokens = data.split()
        self.core.set_demod_channel(int(tokens[1]))

    def get_demodulation_channel_handler(self, data):
        self.core.get_demod_channel()

    def set_transmission_volume_handler(self, data):
        tokens = data.split()
        self.core.set_tx_volume(float(tokens[1]))

    def get_transmission_volume_handler(self, data):
        self.core.get_tx_volume()

    def set_reception_volume_handler(self, data):
        tokens = data.split()
        self.core.set_rx_volume(float(tokens[1]))

    def get_reception_volume_handler(self, data):
        self.core.get_rx_volume()

    def set_correlation_threshold1_handler(self, data):
        tokens = data.split()
        self.core.set_corr_threshold1(float(tokens[1]))

    def get_correlation_threshold1_handler(self, data):
        self.core.get_corr_threshold1()

    def set_correlation_threshold2_handler(self, data):
        tokens = data.split()
        self.core.set_corr_threshold2(float(tokens[1]))

    def get_correlation_threshold2_handler(self, data):
        self.core.get_corr_threshold2()

    def enable_disable_log_handler(self, data):
        tokens = data.split()
        self.core.enable_log(tokens[1] == 'on')

    def start_ber_test_handler(self, data):
        tokens = data.split()
        self.core.start_ber_test(int(tokens[1]))

    def set_internal_mode_handler(self, data):
        tokens = data.split()
        mode = int(tokens[1])
        node_id = int(tokens[2]) if len(tokens) > 2 else None
        self.core.set_internal_mode(mode, node_id)

    def help_handler(self, data):
        tokens = data.split()
        if len(tokens) == 1:
            print("\nAvailable commands:")
            for cmd, (descr, _, _) in self.available_commands.items():
                print(f"  {cmd:<4} — {descr}")
            print()
        elif len(tokens) == 2:
            cmd = tokens[1]
            if cmd in self.available_commands:
                descr, pattern, _ = self.available_commands[cmd]
                print(f"\n{cmd} — {descr}")
                sintassi = pattern.strip('^$').replace('\\s+', ' ')
                print(f"How to use: {sintassi}\n")
            else:
                 print(f"[Error] Command “{cmd}” unrecognized.")
        else:
             print("[Error] Help command misspelled.")
