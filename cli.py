#!/usr/bin/env python3
"""
CubeMars Motor Control - Interactive CLI
A terminal application to test and control CubeMars motors via CAN bus.
"""

import os
import sys
import threading
import time
from typing import Optional

# Add current directory to PATH to find libusb-1.0.dll on Windows
if sys.platform == "win32":
    os.environ["PATH"] = os.getcwd() + os.pathsep + os.environ["PATH"]

# Import terminal handling based on platform
if sys.platform != "win32":
    import termios
    import tty

from cubemars import CubeMarsMotor

# ANSI eseape codes
CLEAR_LINE = "\033[2K"
MOVE_UP = "\033[A"
MOVE_DOWN = "\033[B"
MOVE_TO_COL_0 = "\r"
SAVE_CURSOR = "\033[s"
RESTORE_CURSOR = "\033[u"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"


class MotorCLI:
    """Interactive command-line interface for motor control."""

    def __init__(self):
        self.motor: Optional[CubeMarsMotor] = None
        self.interface = "gs_usb"
        self.channel = "0"
        self.motor_id = 20
        self.monitoring = False
        self.monitor_thread = None
        self.current_input = ""
        self.prompt = "motor> "
        self.lock = threading.Lock()

    def print_banner(self):
        """Display welcome banner."""
        print("=" * 60)
        print("  CubeMars Motor Control - Interactive CLI")
        print("=" * 60)
        print()

    def print_help(self):
        """Display available commands."""
        print("\n" + "=" * 60)
        print("Available Commands:")
        print("=" * 60)
        print("\nConnection:")
        print("  connect [interface] [channel] [motor_id]")
        print("           - Connect to motor (defaults: gs_usb, 0, 20)")
        print("  disconnect - Disconnect from motor")
        print("  status   - Show connection status and motor feedback")

        print("\nControl Commands:")
        print("  duty <value>     - Set duty cycle (0.0 to 1.0)")
        print("  current <amps>   - Set current (Amps)")
        print("  brake <amps>     - Set brake current (Amps)")
        print("  rpm <value>      - Set velocity (RPM)")
        print("  pos <degrees> [speed] [accel]")
        print("                   - Set position (defaults: 12000, 40000)")
        print("  origin <mode>    - Set origin (0=Temp, 1=Perm, 2=Restore)")
        print("  stop             - Stop motor (set current to 0)")

        print("\nMonitoring:")
        print("  monitor [on|off] - Toggle real-time feedback display")
        print("  feedback         - Show current motor feedback once")

        print("\nUtility:")
        print("  help     - Show this help message")
        print("  clear    - Clear screen")
        print("  exit     - Exit the application")
        print("=" * 60 + "\n")

    def print_status(self):
        """Display connection status."""
        if self.motor is None:
            print("\n[NOT CONNECTED]")
            print(
                f"Configuration: {self.interface}:{self.channel}, Motor ID: {self.motor_id}"
            )
        else:
            print("\n[CONNECTED]")
            print(f"Interface: {self.interface}:{self.channel}")
            print(f"Motor ID: {self.motor_id}")
            self.print_feedback()

    def print_feedback(self):
        """Display current motor feedback."""
        if self.motor is None:
            print("Error: Not connected to motor")
            return

        fb = self.motor.feedback
        print("\n--- Motor Feedback ---")
        print(f"Position:     {fb.position:8.2f}°")
        print(f"Velocity:     {fb.velocity:8.1f} RPM")
        print(f"Current:      {fb.current:8.2f} A")
        print(f"Temperature:  {fb.temperature:8.1f}°C")
        print(f"Error Code:   {fb.error_code}")
        print("---------------------")

    def refresh_display(self, monitor_text: str):
        """Refresh both monitor line and input line."""
        with self.lock:
            # Move up to monitor line, clear it, print monitor text
            # Then move down to input line, clear it, print prompt + current input
            output = (
                f"{MOVE_UP}{CLEAR_LINE}{MOVE_TO_COL_0}{monitor_text}\n"
                f"{CLEAR_LINE}{MOVE_TO_COL_0}{self.prompt}{self.current_input}"
            )
            sys.stdout.write(output)
            sys.stdout.flush()

    def monitor_loop(self):
        """Background thread for continuous monitoring."""
        while self.monitoring and self.motor:
            try:
                fb = self.motor.feedback
                monitor_text = (
                    f"[Pos: {fb.position:7.1f}° | Vel: {fb.velocity:7.1f} RPM | "
                    f"Cur: {fb.current:6.2f} A | Temp: {fb.temperature:5.1f}°C]"
                )
                self.refresh_display(monitor_text)
                time.sleep(0.05)
            except Exception as e:
                print(f"\nMonitor error: {e}")
                break

    def start_monitoring(self):
        """Start continuous feedback monitoring."""
        if self.motor is None:
            print("Error: Not connected to motor")
            return

        if not self.monitoring:
            self.monitoring = True
            # Print blank monitor line first, then we'll be on input line
            print("[Starting monitor...]")
            self.monitor_thread = threading.Thread(
                target=self.monitor_loop, daemon=True
            )
            self.monitor_thread.start()
        else:
            print("Monitoring already active")

    def stop_monitoring(self):
        """Stop continuous feedback monitoring."""
        if self.monitoring:
            self.monitoring = False
            if self.monitor_thread:
                self.monitor_thread.join(timeout=1.0)
            # Clear monitor line
            sys.stdout.write(f"{MOVE_UP}{CLEAR_LINE}{MOVE_TO_COL_0}")
            sys.stdout.flush()
            print("Monitoring stopped")
        else:
            print("Monitoring not active")

    def connect(self, interface=None, channel=None, motor_id=None):
        """Connect to motor."""
        if self.motor is not None:
            print("Already connected. Disconnect first.")
            return

        # Update configuration if provided
        if interface:
            self.interface = interface
        if channel:
            self.channel = channel
        if motor_id:
            self.motor_id = int(motor_id)

        print(
            f"Connecting to motor {self.motor_id} on {self.interface}:{self.channel}..."
        )

        try:
            self.motor = CubeMarsMotor(
                interface=self.interface, channel=self.channel, motor_id=self.motor_id
            )
            print("✓ Connected successfully!")
            time.sleep(0.1)  # Give time for initial feedback
            self.print_feedback()
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            self.motor = None

    def disconnect(self):
        """Disconnect from motor."""
        if self.motor is None:
            print("Not connected")
            return

        self.stop_monitoring()
        print("Disconnecting...")

        try:
            self.motor.close()
            self.motor = None
            print("✓ Disconnected")
        except Exception as e:
            print(f"✗ Disconnect error: {e}")

    def execute_command(self, cmd: str, args: list):
        """Execute a motor control command."""
        if self.motor is None:
            print("Error: Not connected to motor. Use 'connect' first.")
            return

        try:
            if cmd == "duty":
                if len(args) < 1:
                    print("Usage: duty <value>")
                    return
                duty = float(args[0])
                self.motor.set_duty(duty)
                print(f"✓ Set duty to {duty}")

            elif cmd == "current":
                if len(args) < 1:
                    print("Usage: current <amps>")
                    return
                current = float(args[0])
                self.motor.set_current(current)
                print(f"✓ Set current to {current} A")

            elif cmd == "brake":
                if len(args) < 1:
                    print("Usage: brake <amps>")
                    return
                current = float(args[0])
                self.motor.set_brake_current(current)
                print(f"✓ Set brake current to {current} A")

            elif cmd == "rpm":
                if len(args) < 1:
                    print("Usage: rpm <value>")
                    return
                rpm = float(args[0])
                self.motor.set_rpm(rpm)
                print(f"✓ Set RPM to {rpm}")

            elif cmd == "pos":
                if len(args) < 1:
                    print("Usage: pos <degrees> [speed] [accel]")
                    return
                pos = float(args[0])
                spd = int(args[1]) if len(args) > 1 else 12000
                accel = int(args[2]) if len(args) > 2 else 40000
                self.motor.set_pos(pos, spd, accel)
                print(f"✓ Moving to {pos}° (speed: {spd}, accel: {accel})")

            elif cmd == "origin":
                if len(args) < 1:
                    print("Usage: origin <mode>  (0=Temp, 1=Perm, 2=Restore)")
                    return
                mode = int(args[0])
                self.motor.set_origin(mode)
                modes = {0: "Temporary", 1: "Permanent", 2: "Restore"}
                print(f"✓ Set origin ({modes.get(mode, 'Unknown')})")

            elif cmd == "stop":
                self.motor.set_current(0.0)
                print("✓ Motor stopped")

            else:
                print(f"Unknown command: {cmd}")

        except ValueError as e:
            print(f"✗ Invalid argument: {e}")
        except Exception as e:
            print(f"✗ Command failed: {e}")

    def read_char(self):
        """Read a single character from stdin."""
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch

    def get_input_with_monitor(self) -> str:
        """Get user input character by character while monitor updates."""
        self.current_input = ""

        while True:
            ch = self.read_char()

            if ch == "\r" or ch == "\n":  # Enter
                result = self.current_input
                self.current_input = ""
                # Print newline to move past input line
                sys.stdout.write("\n")
                sys.stdout.flush()
                return result
            elif ch == "\x7f" or ch == "\x08":  # Backspace
                if self.current_input:
                    with self.lock:
                        self.current_input = self.current_input[:-1]
                        # Redraw input line
                        sys.stdout.write(
                            f"{CLEAR_LINE}{MOVE_TO_COL_0}{self.prompt}{self.current_input}"
                        )
                        sys.stdout.flush()
            elif ch == "\x03":  # Ctrl+C
                raise KeyboardInterrupt
            elif ch == "\x04":  # Ctrl+D
                return "exit"
            elif ch >= " " and ch <= "~":  # Printable ASCII
                with self.lock:
                    self.current_input += ch
                    # Just write the new character
                    sys.stdout.write(ch)
                    sys.stdout.flush()

    def run(self):
        """Main CLI loop."""
        self.print_banner()
        print("Type 'help' for available commands, 'exit' to quit\n")

        try:
            while True:
                try:
                    self.prompt = (
                        f"motor[{self.motor_id}]> " if self.motor else "motor> "
                    )

                    if self.monitoring:
                        # Use character-by-character input when monitoring
                        sys.stdout.write(self.prompt)
                        sys.stdout.flush()
                        user_input = self.get_input_with_monitor()
                    else:
                        user_input = input(self.prompt)

                    user_input = user_input.strip()
                    if not user_input:
                        continue

                    # Temporarily stop monitor for command output
                    was_monitoring = self.monitoring
                    if was_monitoring:
                        self.monitoring = False
                        if self.monitor_thread:
                            self.monitor_thread.join(timeout=0.5)
                        # Clear the monitor line before printing output
                        sys.stdout.write(f"{MOVE_UP}{CLEAR_LINE}{MOVE_TO_COL_0}")
                        sys.stdout.flush()

                    # Parse command
                    parts = user_input.split()
                    cmd = parts[0].lower()
                    args = parts[1:]

                    # Handle commands
                    if cmd == "exit" or cmd == "quit":
                        print("Exiting...")
                        break

                    elif cmd == "help" or cmd == "?":
                        self.print_help()

                    elif cmd == "clear" or cmd == "cls":
                        os.system("cls" if os.name == "nt" else "clear")

                    elif cmd == "connect":
                        self.connect(*args)

                    elif cmd == "disconnect":
                        self.disconnect()
                        was_monitoring = False  # Don't restart if we disconnected

                    elif cmd == "status":
                        self.print_status()

                    elif cmd == "feedback":
                        self.print_feedback()

                    elif cmd == "monitor":
                        if len(args) > 0:
                            if args[0].lower() in ["on", "start", "1"]:
                                self.start_monitoring()
                                was_monitoring = False  # Already started
                            elif args[0].lower() in ["off", "stop", "0"]:
                                # Already stopped above
                                print("Monitoring stopped")
                                was_monitoring = False
                            else:
                                print("Usage: monitor [on|off]")
                        else:
                            # Toggle - if was monitoring, it's now off; if wasn't, turn on
                            if not was_monitoring:
                                self.start_monitoring()
                            else:
                                print("Monitoring stopped")
                            was_monitoring = False

                    else:
                        # Try to execute as motor command
                        self.execute_command(cmd, args)

                    # Restart monitoring if it was active
                    if was_monitoring and self.motor:
                        self.start_monitoring()

                except KeyboardInterrupt:
                    if self.monitoring:
                        self.monitoring = False
                        if self.monitor_thread:
                            self.monitor_thread.join(timeout=0.5)
                    print("\n(Use 'exit' to quit)")
                    continue

        finally:
            # Cleanup
            if self.monitoring:
                self.monitoring = False
                if self.monitor_thread:
                    self.monitor_thread.join(timeout=1.0)
            if self.motor:
                print("\nCleaning up...")
                self.disconnect()


def main():
    """Entry point."""
    cli = MotorCLI()

    # Check for command-line arguments for auto-connect
    if len(sys.argv) > 1:
        if sys.argv[1] in ["-h", "--help", "help"]:
            print("CubeMars Motor Control CLI")
            print("\nUsage:")
            print("  python cli.py                    - Start interactive mode")
            print("  python cli.py [interface] [channel] [motor_id]")
            print("                                   - Start and auto-connect")
            print("\nExample:")
            print("  python cli.py gs_usb 0 20")
            return

        # Auto-connect with provided arguments
        interface = sys.argv[1] if len(sys.argv) > 1 else "gs_usb"
        channel = sys.argv[2] if len(sys.argv) > 2 else "0"
        motor_id = sys.argv[3] if len(sys.argv) > 3 else "20"

        cli.interface = interface
        cli.channel = channel
        cli.motor_id = int(motor_id)
        cli.connect()

    cli.run()


if __name__ == "__main__":
    main()
