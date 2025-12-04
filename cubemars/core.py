import asyncio
import can
import logging
from .protocol import CanPacketId, MotorFeedback, pack_command, unpack_motor_feedback

logger = logging.getLogger(__name__)

class AsyncMotor:
    """
    Asynchronous core for controlling a CubeMars motor.
    Handles the CAN bus communication loop and state updates.
    """
    def __init__(self, bus: can.Bus, motor_id: int):
        self.bus = bus
        self.motor_id = motor_id
        self._feedback = MotorFeedback()
        self._monitor_task = None
        self._control_task = None
        self._running = False
        self._control_mode = None
        self._control_args = ()

    @property
    def feedback(self) -> MotorFeedback:
        """Returns the latest feedback from the motor."""
        return self._feedback

    async def start(self, start_monitor=True):
        """Starts the background monitoring task."""
        if self._running:
            return
        self._running = True
        if start_monitor:
            self._monitor_task = asyncio.create_task(self._monitor_loop())
            logger.info(f"Started monitoring motor {self.motor_id}")
        else:
            logger.info(f"Started motor {self.motor_id} (external monitoring)")
        
        self._control_task = asyncio.create_task(self._control_loop())

    async def stop(self):
        """Stops the motor (sends 0 current) and the monitoring task."""
        logger.info(f"Stopping motor {self.motor_id}")
        self._control_mode = None # Stop continuous sending
        try:
            # Send 0 current to safely stop the motor
            await self.set_current(0.0)
        except Exception as e:
            logger.error(f"Failed to send stop command: {e}")
        
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
            
        if self._control_task:
            self._control_task.cancel()
            try:
                await self._control_task
            except asyncio.CancelledError:
                pass
            self._control_task = None

    async def _control_loop(self):
        """Background task to continuously send control commands."""
        while self._running:
            if self._control_mode is not None:
                try:
                    await self._send_command(self._control_mode, *self._control_args)
                except Exception as e:
                    logger.error(f"Control loop error: {e}")
            await asyncio.sleep(0.01) # Send at 100Hz

    def process_message(self, msg: can.Message):
        """Processes a CAN message externally (for shared bus)."""
        if not self._running:
            return
        if msg.arbitration_id & 0xFF == self.motor_id:
            self._feedback = unpack_motor_feedback(msg.data)

    async def _monitor_loop(self):
        """Background task to read messages from the bus."""
        reader = can.AsyncBufferedReader()
        
        # Check if a notifier already exists for this bus to avoid "multiple active Notifier" error
        # python-can's Notifier attaches to the bus. If we create multiple AsyncMotors sharing the same bus,
        # we can't create multiple Notifiers for the same bus object.
        # Instead, we should ideally have one central listener dispatching messages.
        # However, for simplicity in this architecture where AsyncMotor is self-contained:
        # We will use a listener if provided, or create a new one.
        
        # WORKAROUND: Since we can't easily share the Notifier instance across independent AsyncMotor instances
        # without a refactor, we will use a direct listener approach if possible, or catch the error.
        # Better approach: The Bus wrapper should handle the Notifier and dispatch to motors.
        
        # For now, let's try to attach the reader directly if possible, or use a shared mechanism.
        # Actually, can.Notifier is designed to be one-per-bus.
        
        # Refactored approach: We won't use can.Notifier inside AsyncMotor.
        # We will assume the user (or the parent API) sets up the listener if sharing the bus.
        # BUT, to keep AsyncMotor standalone, we need a way to read.
        
        # If we are sharing the bus, we can't use Notifier.
        # We will use a simple polling loop with non-blocking recv() if Notifier fails,
        # OR we rely on the fact that we can add listeners to an existing Notifier?
        # python-can Notifier doesn't easily expose "get existing notifier for bus".
        
        # SOLUTION: We will NOT use can.Notifier here. We will use direct async reading if supported,
        # or we will rely on a shared reader passed in? No, that breaks encapsulation.
        
        # Let's try to use the bus's recv() method directly in a loop with a small timeout/sleep,
        # which is safe for multiple readers IF the bus supports it (it usually doesn't support multiple readers stealing messages).
        
        # CORRECT ARCHITECTURE FIX:
        # When using multiple motors on one bus, we need ONE central reader that dispatches messages to the correct motor instance.
        # The current architecture (each Motor has its own loop reading from the bus) is flawed for shared buses because
        # reading a message consumes it. Motor A would steal Motor B's messages.
        
        # However, fixing the architecture completely is a big change.
        # Quick fix for "ValueError: A bus can not be added to multiple active Notifier instances":
        # We need to handle the case where we are just sending commands (blind fire) or accept that feedback might be spotty
        # if we don't have a central dispatcher.
        
        # But the user wants feedback.
        # We will modify AsyncMotor to accept an optional 'listener' or 'notifier'.
        # OR, we change _monitor_loop to NOT use Notifier, but just `await bus.recv()`.
        # But `bus.recv()` is not async on standard buses.
        
        # Let's go with the "Central Dispatcher" pattern in the next step.
        # For now, to stop the crash, we will wrap the Notifier creation in a try-catch and fallback?
        # No, that won't solve the "stealing messages" issue.
        
        # We will modify this method to do nothing if it detects it can't run, 
        # but really we need to change how we handle shared buses.
        
        # TEMPORARY FIX to allow the script to run (even if feedback is broken for shared bus):
        try:
            notifier = can.Notifier(self.bus, [reader], loop=asyncio.get_running_loop())
        except ValueError:
            # If we can't create a notifier (likely because one exists), we log it and exit the monitor loop.
            # This means this specific motor instance won't get feedback, but it won't crash.
            logger.warning(f"Motor {self.motor_id}: Could not attach listener (Bus shared?). Feedback will be disabled.")
            return

        try:
            while self._running:
                msg = await reader.get_message()
                if msg.arbitration_id & 0xFF == self.motor_id:
                    self._feedback = unpack_motor_feedback(msg.data)
        except Exception as e:
            logger.error(f"Error in monitor loop: {e}")
        finally:
            notifier.stop()

    async def _send_command(self, mode: CanPacketId, *args):
        """Constructs and sends a CAN message."""
        data = pack_command(mode, *args)
        
        # ID construction: Controller ID (lower 8 bits) | Mode (shifted by 8)
        # Note: The C code uses 29-bit extended ID.
        arb_id = self.motor_id | (int(mode) << 8)
        
        msg = can.Message(
            arbitration_id=arb_id,
            data=data,
            is_extended_id=True
        )
        
        # python-can's send is synchronous by default on some interfaces, 
        # but we can wrap it or use the bus's send method. 
        # For AsyncBus, send might be async. 
        # However, we are passing a generic 'bus' which might be sync.
        # To be safe in an async context, we can run it in an executor if it blocks,
        # but usually writing to socketcan/slcan is fast enough.
        # If using can.AsyncBus, we would await self.bus.send(msg).
        # But to support both sync/async bus objects passed in, we'll assume standard usage.
        # If the user passes a sync bus, we just call send().
        
        try:
            self.bus.send(msg)
        except can.CanError as e:
            logger.error(f"Failed to send CAN message: {e}")
            raise

    async def set_duty(self, duty: float):
        """Sets the duty cycle (0.0 to 1.0)."""
        self._control_mode = CanPacketId.SET_DUTY
        self._control_args = (duty,)
        await self._send_command(CanPacketId.SET_DUTY, duty)

    async def set_current(self, current: float):
        """Sets the current loop reference (Amps)."""
        self._control_mode = CanPacketId.SET_CURRENT
        self._control_args = (current,)
        await self._send_command(CanPacketId.SET_CURRENT, current)

    async def set_brake_current(self, current: float):
        """Sets the brake current (Amps)."""
        self._control_mode = CanPacketId.SET_CURRENT_BRAKE
        self._control_args = (current,)
        await self._send_command(CanPacketId.SET_CURRENT_BRAKE, current)

    async def set_rpm(self, rpm: float):
        """Sets the velocity (Electrical RPM)."""
        self._control_mode = CanPacketId.SET_RPM
        self._control_args = (rpm,)
        await self._send_command(CanPacketId.SET_RPM, rpm)

    async def set_pos(self, pos: float, spd: int = 12000, accel: int = 40000):
        """Sets the position (Degrees). Uses SET_POS_SPD with default speed/accel."""
        self._control_mode = CanPacketId.SET_POS_SPD
        self._control_args = (pos, spd, accel)
        await self._send_command(CanPacketId.SET_POS_SPD, pos, spd, accel)

    async def set_origin(self, mode: int):
        """Sets the origin (0=Temp, 1=Perm, 2=Restore)."""
        self._control_mode = None
        await self._send_command(CanPacketId.SET_ORIGIN_HERE, mode)

    async def set_pos_spd(self, pos: float, spd: int = 12000, accel: int = 40000):
        """Sets position with speed and acceleration limits."""
        self._control_mode = CanPacketId.SET_POS_SPD
        self._control_args = (pos, spd, accel)
        await self._send_command(CanPacketId.SET_POS_SPD, pos, spd, accel)
