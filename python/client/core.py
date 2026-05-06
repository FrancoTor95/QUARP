import socket
import threading
import json
import traceback
import struct
import logging

# Add parent directory to path to import high_level_interface
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# from high_level_interface import *
try:
    from client.interface import *
except ModuleNotFoundError:
    from .interface import *

class QUARPCore:
    """
    Core logic for QUARP Client.
    Handles connection, packet transmission, and reception.
    Does NOT handle user input or console output (use events/callbacks).
    """
    def __init__(self, server_ip, server_port, log_level=logging.INFO):
        self.server_ip = server_ip
        self.server_port = server_port
        self.socket = None
        self.running = False
        self.receive_thread = None
        
        # Callbacks (can be set by the view/controller)
        self.on_connected = None
        self.on_disconnected = None
        self.on_message_received = None # generic handler for valid packets
        self.on_error = None

        # internal specific Packet handlers map
        # If a handler is found here, it is called INSTEAD of generic on_message_received?
        # Or maybe we just expose a way to register specific handlers that process data 
        # and then maybe notify specific events.
        # For simplicity, let's keep the user's pattern: a dict of handlers.
        self.handlers = {
            FE_INCOMING_MSG: self._handle_incoming_msg,
            FE_ONE_WAY_RANGE_CMD: self._handle_one_way_range,
            FE_TRACKING_CMD: self._handle_tracking,
            FE_ACK_CMD: self._handle_ack,
            FE_NACK_CMD: self._handle_nack,
        }

    # =========================================================================
    # --- CONNECTION MANAGEMENT ---
    # =========================================================================

    def connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.server_ip, self.server_port))
            self.running = True
            
            if self.on_connected:
                self.on_connected(self.server_ip, self.server_port)
            
            self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.receive_thread.start()
            return True
        except Exception as e:
            if self.on_error:
                self.on_error(f"Error connecting to server: {e}")
            return False

    def disconnect(self):
        self.running = False
        if self.socket:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
                self.socket.close()
            except:
                pass
        
        # Wait for the thread to finish cleanly to avoid IO errors at shutdown
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=1.0)

        if self.on_disconnected:
            self.on_disconnected()

    def send_packet(self, packet):
        if self.socket and self.running:
            try:
                self.socket.sendall(packet.serialize())
            except Exception as e:
                if self.on_error:
                    self.on_error(f"Error sending packet: {e}")

    def register_handler(self, cmd, handler):
        self.handlers[cmd] = handler

    # =========================================================================
    # --- RECEPTION LOOP ---
    # =========================================================================

    def _receive_loop(self):
        buffer = b""
        decoder = json.JSONDecoder()

        while self.running and self._is_socket_alive():
            try:
                data = self.socket.recv(4096)
                if not data:
                    if self.on_disconnected:
                        self.on_disconnected()
                    self.running = False
                    break
                
                buffer += data
                try:
                    buffer_str = buffer.decode('utf-8')
                except UnicodeDecodeError:
                    continue

                pos = 0
                while pos < len(buffer_str):
                    lstripped_str = buffer_str[pos:].lstrip()
                    if not lstripped_str:
                        pos = len(buffer_str)
                        break
                    
                    strip_offset = (len(buffer_str) - pos) - len(lstripped_str)

                    try:
                        obj, end_index = decoder.raw_decode(lstripped_str)
                        json_start = pos + strip_offset
                        json_end = pos + strip_offset + end_index
                        json_bytes = buffer_str[json_start:json_end].encode('utf-8')
                        data_packet = ExternalPacket.deserialize(json_bytes)
                        self._dispatch_packet(data_packet)
                        pos = json_end
                    except json.JSONDecodeError:
                        break
                
                if pos < len(buffer_str):
                    buffer = buffer_str[pos:].encode('utf-8')
                else:
                    buffer = b""

            except Exception as e:
                if self.on_error:
                    self.on_error(f"Runtime error in receiver: {e}")
                    traceback.print_exc() # Still printing traceback for debug
                self.running = False
                break

    def _dispatch_packet(self, packet):
        # 1. Dispatch to specific handler if present
        if packet.cmd in self.handlers:
            try:
                self.handlers[packet.cmd](packet)
            except Exception as e:
                if self.on_error:
                    self.on_error(f"Error in handler for {packet.cmd}: {e}")
        
        # 2. Also trigger generic callback (optional, useful for logging everything)
        if self.on_message_received:
            self.on_message_received(packet)

    def _is_socket_alive(self):
        try:
            self.socket.send(b"")
            return True
        except:
            return False

    # =========================================================================
    # --- HANDLERS (LOGIC ONLY - NO PRINTS) ---
    # =========================================================================
    # These handlers are now "internal processors". 
    # Since we moved 'print' to the View, these might just emit events.
    # But wait, the handlers defined in the ClientLib were doing PRINTS.
    # If Core is logic only, how do we get the data to the View?
    # 
    # Approach:
    # The Core handlers should trigger SPECIFIC callbacks that the View implements.
    # e.g. self.on_ack(packet)
    #
    # However, to keep it simple and flexible, we can rely on `on_message_received` 
    # OR we can add specific callbacks.
    # For now, let's keep empty default implementations that subclasses/View can hook into.
    
    def _handle_incoming_msg(self, packet):
        # Core logic: maybe update some stats?
        pass

    def _handle_one_way_range(self, packet):
        pass

    def _handle_tracking(self, packet):
        pass

    def _handle_ack(self, packet):
        pass

    def _handle_nack(self, packet):
        pass

    # =========================================================================
    # --- COMMAND METHODS ---
    # =========================================================================
    
    def send_message(self, message: str):
        payload = message.encode()
        self.send_packet(ExternalPacket(FE_SEND_CMD, payload=payload))

    def set_transmission_level(self, level: int):
        payload = int(level).to_bytes(4, byteorder='little')
        self.send_packet(ExternalPacket(FE_SET_TRANSMISSION_LEVEL_CMD, payload=payload))

    def get_transmission_level(self):
        self.send_packet(ExternalPacket(FE_GET_TRANSMISSION_LEVEL_CMD, payload=b''))

    def set_sync_channel(self, channel: int):
        payload = int(channel).to_bytes(4, byteorder='little')
        self.send_packet(ExternalPacket(FE_SET_SYNCHRONIZATION_CHANNEL_CMD, payload=payload))

    def get_sync_channel(self):
        self.send_packet(ExternalPacket(FE_GET_SYNCHRONIZATION_CHANNEL_CMD, payload=b''))

    def set_demod_channel(self, channel: int):
        payload = int(channel).to_bytes(4, byteorder='little')
        self.send_packet(ExternalPacket(FE_SET_DEMOD_CHANNEL_CMD, payload=payload))

    def get_demod_channel(self):
        self.send_packet(ExternalPacket(FE_GET_DEMOD_CHANNEL_CMD, payload=b''))

    def set_tx_volume(self, volume: float):
        payload = struct.pack('<f', float(volume))
        self.send_packet(ExternalPacket(FE_SET_VOL_CMD, payload=payload))

    def get_tx_volume(self):
        self.send_packet(ExternalPacket(FE_GET_VOL_CMD, payload=b''))
        
    def set_rx_volume(self, volume: float):
        payload = struct.pack('<f', float(volume))
        self.send_packet(ExternalPacket(FE_SET_RECEPTION_VOLUME_CMD, payload=payload))

    def get_rx_volume(self):
        self.send_packet(ExternalPacket(FE_GET_RECEPTION_VOLUME_CMD, payload=b''))

    def set_corr_threshold1(self, val: float):
        payload = struct.pack('<f', float(val))
        self.send_packet(ExternalPacket(FE_SET_CORR1_CMD, payload=payload))

    def get_corr_threshold1(self):
        self.send_packet(ExternalPacket(FE_GET_CORR1_CMD, payload=b''))

    def set_corr_threshold2(self, val: float):
        payload = struct.pack('<f', float(val))
        self.send_packet(ExternalPacket(FE_SET_CORR2_CMD, payload=payload))

    def get_corr_threshold2(self):
        self.send_packet(ExternalPacket(FE_GET_CORR2_CMD, payload=b''))

    def start_ber_test(self, val: int):
        payload = struct.pack('<i', int(val))
        self.send_packet(ExternalPacket(FE_START_BER_TEST_CMD, payload=payload))

    def enable_log(self, enable: bool):
        payload = b'on' if enable else b'off'
        self.send_packet(ExternalPacket(FE_TURN_LOG_ON_OFF_CMD, payload=payload))

    def set_internal_mode(self, mode: int, node_id: int = None):
        mode_pack = struct.pack('<i', mode)
        if mode in (0, 2, 3):
            payload = mode_pack
        elif mode == 1:
            if node_id is None:
                # Should propagate error
                if self.on_error: self.on_error("Error: node_id required for mode 1")
                return
            id_pack = struct.pack('<i', node_id)
            payload = mode_pack + id_pack
        else:
            if self.on_error: self.on_error(f"Unknown mode {mode}")
            return
            
        self.send_packet(ExternalPacket(FE_SET_INTERNAL_MODE_CMD, payload=payload))
