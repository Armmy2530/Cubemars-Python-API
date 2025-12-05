#!/usr/bin/env python3
"""
CubeMars Motor Control - Interactive CLI
A terminal application to test and control CubeMars motors via CAN bus.
"""

import sys
import os
import time
import threading
from typing import Optional

# Add current directory to PATH to find libusb-1.0.dll on Windows
if sys.platform == 'win32':
    os.environ['PATH'] = os.getcwd() + os.pathsep + os.environ['PATH']

from cubemars import CubeMarsMotor


class MotorCLI:
    """Interactive command-line interface for motor control."""
    
    def __init__(self):
        self.motor: Optional[CubeMarsMotor] = None
        self.interface = 'gs_usb'
        self.channel = '0'
        self.motor_id = 20
        self.monitoring = False
        self.monitor_thread = None
        
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
            print(f"Configuration: {self.interface}:{self.channel}, Motor ID: {self.motor_id}")
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
        
    def monitor_loop(self):
        """Background thread for continuous monitoring."""
        while self.monitoring and self.motor:
            try:
                fb = self.motor.feedback
                print(f"\r[Pos: {fb.position:7.1f}° | Vel: {fb.velocity:7.1f} RPM | "
                      f"Cur: {fb.current:6.2f} A | Temp: {fb.temperature:5.1f}°C]", 
                      end='', flush=True)
                time.sleep(0.1)
            except Exception as e:
                print(f"\nMonitor error: {e}")
                break
        print()  # New line when monitoring stops
        
    def start_monitoring(self):
        """Start continuous feedback monitoring."""
        if self.motor is None:
            print("Error: Not connected to motor")
            return
            
        if not self.monitoring:
            self.monitoring = True
            self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
            self.monitor_thread.start()
            print("Monitoring started (type commands normally, monitor runs in background)")
        else:
            print("Monitoring already active")
            
    def stop_monitoring(self):
        """Stop continuous feedback monitoring."""
        if self.monitoring:
            self.monitoring = False
            if self.monitor_thread:
                self.monitor_thread.join(timeout=1.0)
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
            
        print(f"Connecting to motor {self.motor_id} on {self.interface}:{self.channel}...")
        
        try:
            self.motor = CubeMarsMotor(
                interface=self.interface,
                channel=self.channel,
                motor_id=self.motor_id
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
            if cmd == 'duty':
                if len(args) < 1:
                    print("Usage: duty <value>")
                    return
                duty = float(args[0])
                self.motor.set_duty(duty)
                print(f"✓ Set duty to {duty}")
                
            elif cmd == 'current':
                if len(args) < 1:
                    print("Usage: current <amps>")
                    return
                current = float(args[0])
                self.motor.set_current(current)
                print(f"✓ Set current to {current} A")
                
            elif cmd == 'brake':
                if len(args) < 1:
                    print("Usage: brake <amps>")
                    return
                current = float(args[0])
                self.motor.set_brake_current(current)
                print(f"✓ Set brake current to {current} A")
                
            elif cmd == 'rpm':
                if len(args) < 1:
                    print("Usage: rpm <value>")
                    return
                rpm = float(args[0])
                self.motor.set_rpm(rpm)
                print(f"✓ Set RPM to {rpm}")
                
            elif cmd == 'pos':
                if len(args) < 1:
                    print("Usage: pos <degrees> [speed] [accel]")
                    return
                pos = float(args[0])
                spd = int(args[1]) if len(args) > 1 else 12000
                accel = int(args[2]) if len(args) > 2 else 40000
                self.motor.set_pos(pos, spd, accel)
                print(f"✓ Moving to {pos}° (speed: {spd}, accel: {accel})")
                
            elif cmd == 'origin':
                if len(args) < 1:
                    print("Usage: origin <mode>  (0=Temp, 1=Perm, 2=Restore)")
                    return
                mode = int(args[0])
                self.motor.set_origin(mode)
                modes = {0: "Temporary", 1: "Permanent", 2: "Restore"}
                print(f"✓ Set origin ({modes.get(mode, 'Unknown')})")
                
            elif cmd == 'stop':
                self.motor.set_current(0.0)
                print("✓ Motor stopped")
                
            else:
                print(f"Unknown command: {cmd}")
                
        except ValueError as e:
            print(f"✗ Invalid argument: {e}")
        except Exception as e:
            print(f"✗ Command failed: {e}")
            
    def run(self):
        """Main CLI loop."""
        self.print_banner()
        print("Type 'help' for available commands, 'exit' to quit\n")
        
        try:
            while True:
                try:
                    # Show prompt
                    if self.monitoring:
                        # Move to new line if monitoring is active
                        print()
                    
                    prompt = f"motor[{self.motor_id}]> " if self.motor else "motor> "
                    user_input = input(prompt).strip()
                    
                    if not user_input:
                        continue
                        
                    # Parse command
                    parts = user_input.split()
                    cmd = parts[0].lower()
                    args = parts[1:]
                    
                    # Handle commands
                    if cmd == 'exit' or cmd == 'quit':
                        print("Exiting...")
                        break
                        
                    elif cmd == 'help' or cmd == '?':
                        self.print_help()
                        
                    elif cmd == 'clear' or cmd == 'cls':
                        os.system('cls' if os.name == 'nt' else 'clear')
                        
                    elif cmd == 'connect':
                        self.connect(*args)
                        
                    elif cmd == 'disconnect':
                        self.disconnect()
                        
                    elif cmd == 'status':
                        self.print_status()
                        
                    elif cmd == 'feedback':
                        self.print_feedback()
                        
                    elif cmd == 'monitor':
                        if len(args) > 0:
                            if args[0].lower() in ['on', 'start', '1']:
                                self.start_monitoring()
                            elif args[0].lower() in ['off', 'stop', '0']:
                                self.stop_monitoring()
                            else:
                                print("Usage: monitor [on|off]")
                        else:
                            # Toggle
                            if self.monitoring:
                                self.stop_monitoring()
                            else:
                                self.start_monitoring()
                                
                    else:
                        # Try to execute as motor command
                        self.execute_command(cmd, args)
                        
                except KeyboardInterrupt:
                    print("\n(Use 'exit' to quit)")
                    continue
                    
        finally:
            # Cleanup
            self.stop_monitoring()
            if self.motor:
                print("\nCleaning up...")
                self.disconnect()
                
        print("Goodbye!")


def main():
    """Entry point."""
    cli = MotorCLI()
    
    # Check for command-line arguments for auto-connect
    if len(sys.argv) > 1:
        if sys.argv[1] in ['-h', '--help', 'help']:
            print("CubeMars Motor Control CLI")
            print("\nUsage:")
            print("  python cli.py                    - Start interactive mode")
            print("  python cli.py [interface] [channel] [motor_id]")
            print("                                   - Start and auto-connect")
            print("\nExample:")
            print("  python cli.py gs_usb 0 20")
            return
            
        # Auto-connect with provided arguments
        interface = sys.argv[1] if len(sys.argv) > 1 else 'gs_usb'
        channel = sys.argv[2] if len(sys.argv) > 2 else '0'
        motor_id = sys.argv[3] if len(sys.argv) > 3 else '20'
        
        cli.interface = interface
        cli.channel = channel
        cli.motor_id = int(motor_id)
        cli.connect()
    
    cli.run()


if __name__ == "__main__":
    main()
