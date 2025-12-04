import sys
import os
import time

# Add current directory to PATH to find libusb-1.0.dll on Windows
if sys.platform == 'win32':
    os.environ['PATH'] = os.getcwd() + os.pathsep + os.environ['PATH']

from cubemars import CubeMarsMotor

def main():
    # Example configuration
    INTERFACE = 'gs_usb'
    CHANNEL = '0'
    
    print(f"Connecting to CAN bus ({INTERFACE} on {CHANNEL})...")

    try:
        # Initialize 4 motors on the same bus (implicit sharing)
        motors = []
        for i in range(1, 5):
            print(f"Initializing Motor {i}...")
            # Note: We pass interface/channel to all, but the underlying system reuses the bus
            motor = CubeMarsMotor(interface=INTERFACE, channel=CHANNEL, motor_id=i)
            motors.append(motor)
        
        print("\nStarting simultaneous control...")
        
        # 1. Set all to Velocity Mode (200 RPM)
        print("Setting all motors to 200 RPM...")
        for motor in motors:
            motor.set_rpm(2000)
        
        # Monitor for 3 seconds
        start_time = time.time()
        while time.time() - start_time < 3:
            status_line = "\r"
            for i, motor in enumerate(motors):
                fb = motor.feedback
                status_line += f"M{i+1}: {fb.velocity:5.0f} RPM | "
            print(status_line, end="")
            time.sleep(0.1)
        
        print("\n\nStopping all motors...")
        for motor in motors:
            motor.set_current(0)
            
        time.sleep(1)
        
        print("Closing connections...")
        for motor in motors:
            motor.close()
            
    except Exception as e:
        print(f"\nAn error occurred: {e}")

if __name__ == "__main__":
    main()
