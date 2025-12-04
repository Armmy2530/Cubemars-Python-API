import threading
import asyncio
import can
import time
from typing import Optional
from .core import AsyncMotor
from .protocol import MotorFeedback

class CubeMarsBus:
    """
    Manages a shared CAN bus connection and background thread for multiple motors.
    """
    _registry = {}
    _lock = threading.Lock()

    def __init__(self, interface: str, channel: str, bitrate: int = 1000000):
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
        self._start_background_thread()

    @classmethod
    def get_or_create(cls, interface, channel, bitrate=1000000):
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
                if self._key in self._registry:
                    del self._registry[self._key]

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
        if not self._ready_event.wait(timeout=5.0):
            raise TimeoutError("Failed to initialize bus thread")

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
            print(f"Bus thread error: {e}")
        finally:
            if self._notifier:
                self._notifier.stop()
            if self._bus:
                self._bus.shutdown()
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
        self._motor_id = motor_id
        self._motor: Optional[AsyncMotor] = None
        
        if bus:
            # Use shared bus explicitly provided
            self._bus_manager = bus
            self._explicit_bus = True
        else:
            # Implicitly managed shared bus
            if not interface or not channel:
                raise ValueError("Interface and channel are required if no shared bus is provided")
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

    def set_pos_spd(self, pos: float, spd: int, accel: int):
        self._run_coro(self._motor.set_pos_spd(pos, spd, accel))

    def set_origin(self, mode: int):
        self._run_coro(self._motor.set_origin(mode))