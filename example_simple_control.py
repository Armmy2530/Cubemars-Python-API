import sys
import os

# Add current directory to PATH to find libusb-1.0.dll on Windows
if sys.platform == 'win32':
    os.environ['PATH'] = os.getcwd() + os.pathsep + os.environ['PATH']

from cubemars import CubeMarsMotor
import time

def main():
    # Example configuration - change these to match your setup
    INTERFACE = 'gs_usb'
    CHANNEL = '0'
    MOTOR_ID = 20

    print(f"Connecting to motor {MOTOR_ID} on {CHANNEL}...")

    try:
        with CubeMarsMotor(interface=INTERFACE, channel=CHANNEL, motor_id=MOTOR_ID) as motor:
            print("Motor Connected!")
            
            # 1. Velocity Mode Example
            target_rpm = 2000
            print(f"Spinning at {target_rpm} RPM for 3 seconds...")
            motor.set_rpm(target_rpm)
            
            start_time = time.time()
            while time.time() - start_time < 3:
                fb = motor.feedback
                print(f"Vel: {fb.velocity:.1f} RPM | Cur: {fb.current:.2f} A")
                time.sleep(0.1)
            
            # 2. Position Mode Example
            print("\nMoving to 0 degrees...")
            motor.set_pos(0)
            time.sleep(2)
            
            print("Moving to 180 degrees...")
            motor.set_pos(180)
            time.sleep(2)
            
            print("\nStopping...")
            # Exiting the 'with' block automatically sends a stop command (0 current)
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
