# CubeMars AK Series Motor Python API

A Python library and CLI tool for controlling CubeMars AK-series motors (AK60-6, AK70-10, etc.) over CAN bus. Built with `asyncio` and `python-can`, supporting Windows and Linux.

## Features

- **Cross-Platform**: Works on Windows (with `gs_usb`/`slcan`) and Linux (SocketCAN).
- **Async Core**: High-performance non-blocking I/O using `asyncio`.
- **Sync Wrapper**: Easy-to-use synchronous API for scripts.
- **Multi-Motor Support**: Control multiple motors on a single bus simultaneously.
- **CLI Tool**: Built-in command-line interface for testing and configuration.
- **Continuous Control**: Automatic background sending of speed commands (watchdog prevention).

## Prerequisites

### Hardware
- CubeMars AK-series Motor.
- USB-to-CAN Adapter (e.g., CANable, CandleLight, or any `gs_usb`/`slcan` compatible device).
- 24V-48V Power Supply.

### Software
- Python 3.10 or higher.
- `uv` package manager (recommended) or `pip`.

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/CubemarsAPI.git
   cd CubemarsAPI
   ```

2. **Install dependencies**:
   Using `uv` (Recommended):
   ```bash
   uv sync
   ```
   Or using `pip`:
   ```bash
   pip install -r requirements.txt
   ```

### Windows Specific Setup
If you are using a `gs_usb` device (like CandleLight) on Windows:
1. Ensure `libusb-1.0.dll` is in the project root or your system PATH. (A copy is included in this repo).
2. Install the WinUSB driver for your device using [Zadig](https://zadig.akeo.ie/).

## Usage

### Command Line Interface (CLI)

The CLI allows you to quickly test motor functions without writing code.

```bash
# Run using uv
uv run -m tools.cli --interface gs_usb --channel 0 --bitrate 1000000 --id 1

# Or with python directly
python -m tools.cli --interface gs_usb --channel 0 --id 1
```

**Arguments:**
- `--interface`: CAN interface type (`gs_usb`, `slcan`, `socketcan`). Default: `gs_usb`.
- `--channel`: Channel name (e.g., `0` for first USB device, `COM3` for serial). Default: `0`.
- `--bitrate`: CAN bus speed. Default: `1000000` (1Mbps).
- `--id`: Motor CAN ID. Default: `1`.

### Python API

#### Single Motor Control

```python
from cubemars import CubeMarsMotor
import time

# Initialize motor (automatically creates bus connection)
# For Windows/CandleLight: interface='gs_usb', channel='0'
# For Linux/SocketCAN: interface='socketcan', channel='can0'
with CubeMarsMotor(interface='gs_usb', channel='0', motor_id=1) as motor:
    
    # Set Velocity Mode (RPM)
    print("Running at 500 RPM...")
    motor.set_rpm(500)
    time.sleep(2)
    
    # Read Feedback
    fb = motor.feedback
    print(f"Pos: {fb.position:.2f}°, Vel: {fb.velocity:.0f} RPM, Temp: {fb.temperature}°C")
    
    # Stop
    motor.set_rpm(0)
```

#### Multi-Motor Control

The API automatically manages the shared CAN bus connection. Just create multiple motor instances with the same interface settings.

```python
from cubemars import CubeMarsMotor
import time

# Initialize motors
motor1 = CubeMarsMotor(interface='gs_usb', channel='0', motor_id=1)
motor2 = CubeMarsMotor(interface='gs_usb', channel='0', motor_id=2)

try:
    # Control motors independently
    motor1.set_rpm(200)
    motor2.set_rpm(-200)
    
    time.sleep(2)
    
    # Read feedback
    print(f"Motor 1: {motor1.feedback.velocity} RPM")
    print(f"Motor 2: {motor2.feedback.velocity} RPM")

finally:
    motor1.close()
    motor2.close()
```

## API Reference

### `CubeMarsMotor` Methods

- `set_duty(duty)`: Set duty cycle (-1.0 to 1.0).
- `set_current(current)`: Set torque current (Amps).
- `set_brake_current(current)`: Set brake current (Amps).
- `set_rpm(rpm)`: Set velocity (Electrical RPM). **Sends continuously**.
- `set_pos(pos)`: Set position (Degrees).
- `set_pos_spd(pos, spd, accel)`: Set position with speed/accel limits.
- `set_origin(mode)`: Set zero position (0=Temp, 1=Perm).
- `feedback`: Property returning `MotorFeedback` object (position, velocity, current, temperature, error).

## Troubleshooting

- **"No backend was available"**: Ensure `libusb-1.0.dll` is present (Windows) or drivers are installed.
- **"Task was destroyed but it is pending"**: Ensure you call `motor.close()` or use the `with` statement to clean up resources.
- **Motor not moving**: Check power supply voltage and CAN termination (120Ω resistor).
