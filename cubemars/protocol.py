import struct
from dataclasses import dataclass
from enum import IntEnum

class CanPacketId(IntEnum):
    SET_DUTY = 0          # Duty cycle mode
    SET_CURRENT = 1       # Current loop mode
    SET_CURRENT_BRAKE = 2 # Current brake mode
    SET_RPM = 3           # Velocity mode
    SET_POS = 4           # Position mode
    SET_ORIGIN_HERE = 5   # Set origin mode
    SET_POS_SPD = 6       # Position and velocity loop mode

@dataclass
class MotorFeedback:
    position: float = 0.0      # Degrees
    velocity: float = 0.0      # Electrical RPM
    current: float = 0.0       # Amperes
    temperature: int = 0       # Celsius
    error_code: int = 0        # Error flags

def unpack_motor_feedback(data: bytes) -> MotorFeedback:
    """
    Parses a CAN frame payload containing motor feedback.
    Based on the manual, page 39.
    """
    if len(data) != 8:
        # Return default if data length is incorrect (safety)
        return MotorFeedback()

    # Unpack big-endian 16-bit integers
    # pos_int (2 bytes), spd_int (2 bytes), cur_int (2 bytes), temp (1 byte), error (1 byte)
    pos_int, spd_int, cur_int, temp, error = struct.unpack('>hhhbb', data)

    return MotorFeedback(
        position=float(pos_int) * 0.1,
        velocity=float(spd_int) * 10.0,
        current=float(cur_int) * 0.01,
        temperature=temp,
        error_code=error
    )

def pack_command(mode: CanPacketId, *args) -> bytes:
    """
    Packs a command into a byte buffer for CAN transmission.
    """
    buffer = bytearray()

    if mode == CanPacketId.SET_DUTY:
        # args[0]: duty cycle (float)
        duty = args[0]
        val = int(duty * 100000.0)
        buffer.extend(struct.pack('>i', val))

    elif mode == CanPacketId.SET_CURRENT:
        # args[0]: current (float)
        current = args[0]
        val = int(current * 1000.0)
        buffer.extend(struct.pack('>i', val))

    elif mode == CanPacketId.SET_CURRENT_BRAKE:
        # args[0]: brake current (float)
        current = args[0]
        val = int(current * 1000.0)
        buffer.extend(struct.pack('>i', val))

    elif mode == CanPacketId.SET_RPM:
        # args[0]: rpm (float)
        rpm = args[0]
        val = int(rpm)
        buffer.extend(struct.pack('>i', val))

    elif mode == CanPacketId.SET_POS:
        # args[0]: position (float)
        pos = args[0]
        val = int(pos * 10000.0)
        buffer.extend(struct.pack('>i', val))

    elif mode == CanPacketId.SET_ORIGIN_HERE:
        # args[0]: mode (int) 0=Temp, 1=Perm, 2=Restore
        origin_mode = int(args[0])
        buffer.extend(struct.pack('>B', origin_mode))

    elif mode == CanPacketId.SET_POS_SPD:
        # args[0]: pos (float), args[1]: spd (int), args[2]: accel (int)
        pos = args[0]
        spd = int(args[1])
        accel = int(args[2])
        
        val_pos = int(pos * 10000.0)
        # Use 'I' and 'H' with masking to emulate C-style overflow/wrapping behavior
        # and avoid struct.error for out-of-range values.
        buffer.extend(struct.pack('>I', val_pos & 0xFFFFFFFF))
        buffer.extend(struct.pack('>H', spd & 0xFFFF))
        buffer.extend(struct.pack('>H', accel & 0xFFFF))

    return bytes(buffer)
