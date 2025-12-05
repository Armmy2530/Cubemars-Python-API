# CubeMars Motor Control API

A Python library and CLI tool for controlling CubeMars motors via CAN bus interface.

## Overview

This project provides a high-level Python API for communicating with CubeMars motors over CAN bus. It supports multiple control modes including duty cycle, current, velocity (RPM), and position control.

## Features

- **Simple Python API** - Easy-to-use synchronous wrapper around async motor control
- **Multiple Control Modes** - Duty cycle, current, brake, RPM, position control
- **Real-time Feedback** - Get motor position, velocity, current, and temperature
- **Multi-Motor Support** - Control multiple motors on a shared CAN bus
- **Interactive CLI** - Terminal application for testing and manual control
- **Thread-safe** - Background thread handles CAN communication

## Project Structure

```
CubemarsAPI/
├── cubemars/              # Main package
│   ├── __init__.py       # Package exports
│   ├── api.py            # High-level synchronous API (CubeMarsMotor, CubeMarsBus)
│   ├── core.py           # Low-level async motor control (AsyncMotor)
│   └── protocol.py       # CAN protocol implementation
├── cli.py                # Interactive terminal application
├── example_simple_control.py       # Basic usage example
├── example_multi_motor_control.py  # Multi-motor example
├── pyproject.toml        # Project configuration
└── readme.md             # This file
```

## Installation

### Prerequisites

- Python 3.8 or higher
- CAN interface hardware (e.g., CANable with candlelight driver)
- USB drivers (libusb for Windows)

### Install from source

```bash
# Clone the repository
git clone https://github.com/Armmy2530/Cubemars-Python-API.git
cd CubemarsAPI

# Install dependencies using uv
uv sync
```

### Windows: libusb-1.0.dll Setup

The `libusb-1.0.dll` is automatically installed when you run `uv sync`. You need to copy it to the project root:

**Copy the DLL to project root:**

```bash
# PowerShell/CMD
copy .venv\Lib\site-packages\libusb\_platform\windows\x86_64\libusb-1.0.dll .
```

**Step 2: Add PATH configuration to your Python code**

Add this code at the start of your Python script to help find the DLL:

```python
import sys
import os

# Add current directory to PATH to find libusb-1.0.dll on Windows
if sys.platform == 'win32':
    os.environ['PATH'] = os.getcwd() + os.pathsep + os.environ['PATH']

from cubemars import CubeMarsMotor
# Your code here...
```

**Note**: The examples in this repository (`example_simple_control.py`, `cli.py`) already include this code.

### Required Python packages

- `python-can` - CAN bus communication
- `click` - CLI framework (optional, for CLI tool)

## CAN Interface Setup

### CANable with Candlelight Driver

If you're using a **CANable adapter with the candlelight firmware**, use these settings:

- **Interface**: `gs_usb`
- **Channel**: `0`
- **Bitrate**: `1000000` (1 Mbps - default)

Example:
```python
motor = CubeMarsMotor(interface='gs_usb', channel='0', motor_id=20)
```

### Other CAN Interfaces

The library supports any interface compatible with python-can:
- `socketcan` (Linux)
- `slcan` (Serial CAN)
- `pcan` (PEAK CAN)
- `vector` (Vector hardware)

## Available API

### CubeMarsMotor Class

Main class for controlling a single motor.

```python
from cubemars import CubeMarsMotor

# Create motor instance
motor = CubeMarsMotor(
    interface='gs_usb',  # CAN interface type
    channel='0',         # CAN channel
    bitrate=1000000,     # CAN bitrate (optional, default: 1000000)
    motor_id=20          # Motor CAN ID
)
```

#### Control Methods

| Method | Description | Parameters |
|--------|-------------|------------|
| `set_duty(duty)` | Set duty cycle | `duty`: 0.0 to 1.0 |
| `set_current(current)` | Set current | `current`: Amps |
| `set_brake_current(current)` | Set brake current | `current`: Amps |
| `set_rpm(rpm)` | Set velocity | `rpm`: RPM |
| `set_pos(pos, spd, accel)` | Set position | `pos`: degrees, `spd`: speed (default: 12000), `accel`: acceleration (default: 40000) |
| `set_origin(mode)` | Set origin point | `mode`: 0=Temp, 1=Perm, 2=Restore |
| `close()` | Stop motor and cleanup | - |

#### Feedback Property

Access real-time motor feedback:

```python
fb = motor.feedback

print(f"Position: {fb.position}°")
print(f"Velocity: {fb.velocity} RPM")
print(f"Current: {fb.current} A")
print(f"Temperature: {fb.temperature}°C")
print(f"Error Code: {fb.error_code}")
```

### CubeMarsBus Class

For controlling multiple motors on the same CAN bus (more efficient):

```python
from cubemars import CubeMarsBus, CubeMarsMotor

# Create shared bus
bus = CubeMarsBus.get_or_create('gs_usb', '0', bitrate=1000000)

# Create motors using shared bus
motor1 = CubeMarsMotor(motor_id=1, bus=bus)
motor2 = CubeMarsMotor(motor_id=2, bus=bus)

# Control motors
motor1.set_rpm(1000)
motor2.set_rpm(2000)

# Cleanup
motor1.close()
motor2.close()
bus.release()
```

## Examples

### Basic Single Motor Control

```python
from cubemars import CubeMarsMotor
import time

# Connect to motor
with CubeMarsMotor(interface='gs_usb', channel='0', motor_id=20) as motor:
    print("Motor Connected!")
    
    # Velocity control - spin at 2000 RPM
    print("Spinning at 2000 RPM...")
    motor.set_rpm(2000)
    time.sleep(3)
    
    # Position control - move to 180 degrees
    print("Moving to 180 degrees...")
    motor.set_pos(180)
    time.sleep(2)
    
    # Get feedback
    fb = motor.feedback
    print(f"Position: {fb.position}°, Velocity: {fb.velocity} RPM")
    
    # Motor automatically stops when exiting 'with' block
```

### Multi-Motor Control

```python
from cubemars import CubeMarsBus, CubeMarsMotor
import time

# Create shared bus for better performance
bus = CubeMarsBus.get_or_create('gs_usb', '0')

# Create two motors
motor1 = CubeMarsMotor(motor_id=1, bus=bus)
motor2 = CubeMarsMotor(motor_id=2, bus=bus)

try:
    # Control both motors simultaneously
    motor1.set_pos(90)
    motor2.set_pos(180)
    
    time.sleep(3)
    
    # Monitor both motors
    print(f"Motor 1: {motor1.feedback.position}°")
    print(f"Motor 2: {motor2.feedback.position}°")
    
finally:
    motor1.close()
    motor2.close()
    bus.release()
```

### Current Control

```python
from cubemars import CubeMarsMotor
import time

with CubeMarsMotor(interface='gs_usb', channel='0', motor_id=20) as motor:
    # Apply 2A current for 1 second
    motor.set_current(2.0)
    time.sleep(1)
    
    # Stop (0 current)
    motor.set_current(0.0)
```

## Interactive CLI

The project includes a powerful interactive CLI for testing and manual motor control.

### Starting the CLI

```bash
# Interactive mode - connect manually
python cli.py

# Auto-connect mode
python cli.py gs_usb 0 20
```

### CLI Commands

#### Connection Commands
```
connect [interface] [channel] [motor_id]  # Connect to motor
disconnect                                 # Disconnect from motor
status                                     # Show connection status and feedback
```

#### Control Commands
```
duty <value>                    # Set duty cycle (0.0 to 1.0)
current <amps>                  # Set current in Amps
brake <amps>                    # Set brake current
rpm <value>                     # Set velocity in RPM
pos <degrees> [speed] [accel]   # Move to position
origin <mode>                   # Set origin (0=Temp, 1=Perm, 2=Restore)
stop                            # Emergency stop (current = 0)
```

#### Monitoring Commands
```
monitor [on|off]   # Toggle real-time feedback display
feedback           # Show current feedback once
```

#### Utility Commands
```
help    # Show all commands
clear   # Clear screen
exit    # Exit application
```

### Example CLI Session

```
$ python cli.py

============================================================
  CubeMars Motor Control - Interactive CLI
============================================================

Type 'help' for available commands, 'exit' to quit

motor> connect gs_usb 0 20
Connecting to motor 20 on gs_usb:0...
✓ Connected successfully!

--- Motor Feedback ---
Position:        0.00°
Velocity:        0.0 RPM
Current:         0.00 A
Temperature:    25.0°C
Error Code:   0
---------------------

motor[20]> rpm 1000
✓ Set RPM to 1000.0

motor[20]> monitor on
Monitoring started (type commands normally, monitor runs in background)

motor[20]> 
[Pos:   45.2° | Vel: 1000.0 RPM | Cur:  0.85 A | Temp:  26.5°C]

motor[20]> pos 180
✓ Moving to 180.0° (speed: 12000, accel: 40000)

motor[20]> monitor off
Monitoring stopped

motor[20]> feedback

--- Motor Feedback ---
Position:      180.00°
Velocity:        0.0 RPM
Current:         0.00 A
Temperature:    27.2°C
Error Code:   0
---------------------

motor[20]> stop
✓ Motor stopped

motor[20]> exit
Exiting...
Cleaning up...
Disconnecting...
✓ Disconnected
Goodbye!
```

## Using in Your Project

### Method 1: Copy the Module

Copy the `cubemars` folder into your project:

```
YourProject/
├── cubemars/          # Copy this folder
│   ├── __init__.py
│   ├── api.py
│   ├── core.py
│   └── protocol.py
└── your_code.py
```

Then import and use:

```python
from cubemars import CubeMarsMotor

motor = CubeMarsMotor(interface='gs_usb', channel='0', motor_id=20)
motor.set_rpm(1000)
```

### Method 2: Install from GitHub with uv

Add to your `pyproject.toml`:

```toml
[project]
dependencies = [
    "cubemars-motor-control @ git+https://github.com/Armmy2530/Cubemars-Python-API.git",
]
```

Then run:
```bash
uv sync
```

## Notes

### CANable with Candlelight Driver

**Important**: If you're using a CANable adapter with the candlelight firmware/driver:
- Always use `interface='gs_usb'` 
- Always use `channel='0'`
- The default bitrate of 1000000 (1 Mbps) should work for most CubeMars motors

### Windows USB Driver

On Windows, you may need to install libusb drivers. The library automatically adds the current directory to PATH to find `libusb-1.0.dll`.

### Thread Safety

The API uses a background thread to handle CAN communication, allowing you to call motor methods from your main thread without dealing with asyncio.

### Error Handling

Always use context managers (`with` statement) or call `close()` to ensure proper cleanup:

```python
# Good - automatic cleanup
with CubeMarsMotor(...) as motor:
    motor.set_rpm(1000)

# Also good - manual cleanup
motor = CubeMarsMotor(...)
try:
    motor.set_rpm(1000)
finally:
    motor.close()
```

## Troubleshooting

### Can't connect to CAN bus

1. Check that your CAN adapter is properly connected
2. Verify the interface name and channel number
3. On Linux, ensure you have permissions to access the CAN device
4. For CANable with candlelight: use `gs_usb` interface and channel `0`

### No motor feedback

1. Verify the motor ID is correct
2. Check CAN bus wiring and termination resistors
3. Ensure motor is powered on
4. Verify bitrate matches motor configuration (typically 1 Mbps)

### Motor not responding

1. Check motor power supply
2. Verify motor CAN ID configuration
3. Try sending a stop command: `motor.set_current(0.0)`
4. Check for error codes in feedback: `motor.feedback.error_code`
