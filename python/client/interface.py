import uuid
import json

# =============================================================================
# --- CONSTANTS (From high_level_interface.py) ---
# =============================================================================

FE_ACK_CMD = 'oook'
FE_NACK_CMD = 'nook'
FE_INCOMING_MSG = 'msgs'
FE_SEND_CMD = 'send'
FE_SET_TRANSMISSION_LEVEL_CMD = 'sttl'
FE_GET_TRANSMISSION_LEVEL_CMD = 'gttl'
FE_SET_VOL_CMD = 'stvl'
FE_GET_VOL_CMD = 'gtvl'
FE_SET_CORR1_CMD = 'stc1'
FE_GET_CORR1_CMD = 'gtc1'
FE_SET_CORR2_CMD = 'stc2'
FE_GET_CORR2_CMD = 'gtc2'
FE_TURN_LOG_ON_OFF_CMD = 'slog'
FE_SEND_CONSTANT_FREQ = 'sdkf'
FE_TWO_WAY_RANGE_CMD = 'twrc'
FE_ONE_WAY_RANGE_CMD = 'owrc'
FE_START_BER_TEST_CMD = 'stbr'
FE_STOP_BER_TEST_CMD = 'spbr'
FE_TRACKING_CMD = 'trck'
FE_SET_INTERNAL_MODE_CMD = 'stmd'
FE_SET_SYNCHRONIZATION_CHANNEL_CMD = 'stsc'
FE_GET_SYNCHRONIZATION_CHANNEL_CMD = 'gtsc'
FE_SET_DEMOD_CHANNEL_CMD = 'stdc'
FE_GET_DEMOD_CHANNEL_CMD = 'gtdc'
FE_SET_RECEPTION_VOLUME_CMD = 'strl'
FE_GET_RECEPTION_VOLUME_CMD = 'gtrl'
FE_HELP_CMD = 'help'

# =============================================================================
# --- PACKET CLASS ---
# =============================================================================

class ExternalPacket:
    def __init__(self, cmd: str, payload: bytes = b'', id: str = None,
                 crc_check: bool = None, snr: float = None, time_stamp: float = None, 
                 piggy_back = None, pre_fec = None, range_id = None,
                 tracking_shifts = None, tracking_factors = None, ip = None,
                 yaw = None, pitch = None, roll = None):
        self.cmd = cmd.lower()
        self.payload = payload
        # Use provided ID or generate a new UUID
        self.id = id or str(uuid.uuid4())
        self.crc_check = crc_check
        self.snr = snr
        self.time_stamp = time_stamp
        self.piggy_back = piggy_back
        self.pre_fec = pre_fec
        self.range_id = range_id
        self.tracking_shifts = tracking_shifts
        self.tracking_factors = tracking_factors
        self.ip = ip
        self.yaw = yaw
        self.pitch = pitch
        self.roll = roll

    def serialize(self) -> bytes:
        """Serialize to JSON, excluding 'id' and any None-valued fields."""
        # 1) Remove id from serialization
        data = self.__dict__.copy()
        data.pop('id', None)

        # 2) Convert paylod to list of byte (bytes is not serializable)
        data['payload'] = list(self.payload)
        # data['payload'] = self.payload.hex() # instead lets use hexadecimal strings

        # 4) Remove all None fields
        data = {k: v for k, v in data.items() if v is not None}

        # 5) Serialize data
        # print(data) # Removed print for cleaner library usage
        return json.dumps(data).encode()

    def serialize_payload(self) -> bytes:
        """Return raw payload bytes"""
        return bytes(self.payload) if self.payload else b''

    @staticmethod
    def deserialize(serialized_packet: bytes) -> 'ExternalPacket':
        """Deserialize JSON into an ExternalPacket object"""
        data = json.loads(serialized_packet.decode())
        data['payload'] = bytes(data.get('payload', []))
        # data['payload'] = bytes.fromhex(data.get('payload', [])) # lets try hexadecimal strings
        return ExternalPacket(**data)

    def __str__(self) -> str:
        parts = [
            f"cmd         = {self.cmd!r}",
            f"id          = {self.id!r}",
            f"payload     = {self.payload!r}",
            f"crc_check   = {self.crc_check}",
            f"time_stamp  = {self.time_stamp}",
            f"snr         = {self.snr}",
            f"pg          = {self.piggy_back}"
        ]
        return "\n".join(parts) + "\n"
