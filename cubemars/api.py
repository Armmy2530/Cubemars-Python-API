import threading
import asyncio
import can
import time
from typing import Optional
from .core import AsyncMotor
from .protocol import MotorFeedback


def _validate_interface_channel(interface, channel):
    """Validate the interface and channel parameters.

    Args:
        interface: CAN interface name (e.g. 'socketcan', 'gs_usb', 'slcan').
        channel: CAN channel identifier. Must be a string for most interfaces
            (e.g. 'can0', '0', '/dev/ttyUSB0'). Passing an int produces a
            cryptic "expected str, bytes or os.PathLike object, not int"
            error from python-can because it tries to open the int as a
            config-file path.

    Raises:
        TypeError: If interface or channel is the wrong type.
        ValueError: If interface or channel is empty.
    """
    if not isinstance(interface, str):
        raise TypeError(
            f"interface must be a string (e.g. 'socketcan', 'gs_usb', 'slcan'), "
            f"got {type(interface).__name__}: {interface!r}"
        )
    if not interface:
        raise ValueError("interface must be a non-empty string")
    if not isinstance(channel, str):
        raise TypeError(
            f"channel must be a string (e.g. 'can0', '0', '/dev/ttyUSB0'), "
            f"got {type(channel).__name__}: {channel!r}. "
            f"Passing an int triggers a cryptic error inside python-can."
        )
    if not channel:
        raise ValueError("channel must be a non-empty string")


class CubeMarsBus:
    """
    Manages a shared CAN bus connection and background thread for multiple motors.
    """
    _registry = {}
    _lock = threading.Lock()

    def __init__(self, interface: str, channel: str, bitrate: int = 1000000):
        _validate_interface_channel(interface, channel)
        if not isinstance(bitrate, int) or bitrate <= 0:
            raise ValueError(f"bitrate must be a positive int, got {bitrate!r}")
        self._interface = interface
        self._channel = channel
        self._bitrate = bitrate
        self._key = (interface, channel)
        self._ref_count = 0
        self._is_managed = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._bus: Optional[can.Bus] = None
        self._notifier: Optional[can.Notifier] = None
        self._motors = {} # motor_id -> AsyncMotor
        self._ready_event = threading.Event()
        self._init_error: Optional[BaseException] = None
        self._start_background_thread()

    @classmethod
    def get_or_create(cls, interface, channel, bitrate=1000000):
        # Validate up front so bad inputs fail before touching the registry.
        _validate_interface_channel(interface, channel)
        if not isinstance(bitrate, int) or bitrate <= 0:
            raise ValueError(f"bitrate must be a positive int, got {bitrate!r}")
        with cls._lock:
            key = (interface, channel)
            if key in cls._registry:
                bus = cls._registry[key]
            else:
                bus = cls(interface, channel, bitrate)
                bus._is_managed = True
                cls._registry[key] = bus

            bus._ref_count += 1
            return bus

    def release(self):
        if not self._is_managed:
            return

        with self._lock:
            self._ref_count -= 1
            if self._ref_count <= 0:
                self.close()
                if self._key in CubeMarsBus._registry:
                    del CubeMarsBus._registry[self._key]

    def register_motor(self, motor_id, motor):
        self._motors[motor_id] = motor

    def unregister_motor(self, motor_id):
        if motor_id in self._motors:
            del self._motors[motor_id]

    def _dispatch_message(self, msg):
        motor_id = msg.arbitration_id & 0xFF
        if motor_id in self._motors:
            self._motors[motor_id].process_message(msg)

    def _start_background_thread(self):
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready_event.wait(timeout=5.0)
        # Surface the real failure from the bus thread if we have one;
        # otherwise report a generic timeout with context.
        if self._init_error is not None:
            raise RuntimeError(
                f"Failed to initialize bus thread for "
                f"interface={self._interface!r}, channel={self._channel!r}: "
                f"{type(self._init_error).__name__}: {self._init_error}"
            ) from self._init_error
        if not self._ready_event.is_set():
            raise TimeoutError(
                f"Failed to initialize bus thread for "
                f"interface={self._interface!r}, channel={self._channel!r} "
                f"within 5.0s"
            )

    def _run_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            self._bus = can.Bus(
                interface=self._interface,
                channel=self._channel,
                bitrate=self._bitrate
            )

            # Create a central notifier for this bus
            self._notifier = can.Notifier(self._bus, [self._dispatch_message], loop=loop)

            self._ready_event.set()
            loop.run_forever()
        except Exception as e:
            # Save the real exception so the main thread can surface it,
            # then unblock _start_background_thread so it doesn't just time out.
            self._init_error = e
            logger_msg = (
                f"Bus thread error for interface={self._interface!r}, "
                f"channel={self._channel!r}: "
                f"{type(e).__name__}: {e}"
            )
            print(logger_msg)
            self._ready_event.set()
        finally:
            if self._notifier:
                try:
                    self._notifier.stop()
                except Exception:
                    pass
            if self._bus:
                try:
                    self._bus.shutdown()
                except Exception:
                    pass
            loop.close()

    def close(self):
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread:
                self._thread.join(timeout=2.0)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class CubeMarsMotor:
    """
    Synchronous wrapper for the CubeMars motor API.
    Runs the async core in a background thread, allowing blocking calls
    from the main thread without managing event loops.
    """
    def __init__(self, interface: str = None, channel: str = None, bitrate: int = 1000000, motor_id: int = 1, bus: CubeMarsBus = None):
        if not isinstance(motor_id, int) or not (0 <= motor_id <= 0xFF):
            raise ValueError(f"motor_id must be an int in [0, 255], got {motor_id!r}")

        if bus is not None:
            # Use shared bus explicitly provided
            self._bus_manager = bus
            self._explicit_bus = True
        else:
            # Implicitly managed shared bus. Validate first so we never feed
            # junk into the registry (e.g. None or ints from a typo).
            if interface is None or channel is None:
                raise ValueError(
                    "Interface and channel are required if no shared bus is provided"
                )
            self._bus_manager = CubeMarsBus.get_or_create(interface, channel, bitrate)
            self._explicit_bus = False

        self._loop = self._bus_manager._loop

        # Create AsyncMotor inside the shared loop
        future = asyncio.run_coroutine_threadsafe(self._init_async_motor(self._bus_manager._bus), self._loop)
        future.result() # Wait for init

    async def _init_async_motor(self, can_bus):
        self._motor = AsyncMotor(can_bus, self._motor_id)
        self._bus_manager.register_motor(self._motor_id, self._motor)
        await self._motor.start(start_monitor=False)

    def close(self):
        """Stops the motor and releases the bus."""
        if self._loop and self._loop.is_running() and self._motor:
             future = asyncio.run_coroutine_threadsafe(self._motor.stop(), self._loop)
             try:
                 future.result(timeout=2.0)
             except Exception as e:
                 print(f"Error stopping motor {self._motor_id}: {e}")
        
        if hasattr(self, '_bus_manager'):
            self._bus_manager.unregister_motor(self._motor_id)
            if not self._explicit_bus:
                self._bus_manager.release()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @property
    def feedback(self) -> MotorFeedback:
        """Returns the latest feedback from the motor."""
        if self._motor:
            return self._motor.feedback
        return MotorFeedback()

    def _run_coro(self, coro):
        """Helper to run a coroutine in the background loop."""
        if not self._loop:
            raise RuntimeError("Motor loop is not running")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result() # Block until sent

    def set_duty(self, duty: float):
        self._run_coro(self._motor.set_duty(duty))

    def set_current(self, current: float):
        self._run_coro(self._motor.set_current(current))

    def set_brake_current(self, current: float):
        self._run_coro(self._motor.set_brake_current(current))

    def set_rpm(self, rpm: float):
        self._run_coro(self._motor.set_rpm(rpm))

    def set_pos(self, pos: float, spd: int = 12000, accel: int = 40000):
        self._run_coro(self._motor.set_pos(pos, spd, accel))

    def set_origin(self, mode: int):
        self._run_coro(self._motor.set_origin(mode))