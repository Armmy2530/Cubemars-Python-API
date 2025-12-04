/**
 * @file main.c
 * @brief Command-Line Interface (CLI) for controlling a CubeMars AK-series motor.
 *
 * This program provides an interactive CLI to send control commands to an AK-series
 * motor driver in Servo Mode via a SocketCAN interface on Linux. It continuously
 * sends the selected command and displays real-time feedback from the motor.
 * The command formats and protocols are based on the "AK Series Actuator Driver Manual V1.0.6".
 *
 */
#define _GNU_SOURCE
#define _DEFAULT_SOURCE

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <termios.h>
#include <fcntl.h>

#include <sys/types.h>
#include <net/if.h>
#include <sys/ioctl.h>
#include <sys/socket.h>

#include <linux/can.h>
#include <linux/can/raw.h>


// Represents the different control modes for the motor in Servo Mode.
// Based on the manual, page 32.
typedef enum {
    CAN_PACKET_SET_DUTY = 0,          // Duty cycle mode
    CAN_PACKET_SET_CURRENT,           // Current loop mode
    CAN_PACKET_SET_CURRENT_BRAKE,     // Current brake mode
    CAN_PACKET_SET_RPM,               // Velocity mode
    CAN_PACKET_SET_POS,               // Position mode
    CAN_PACKET_SET_ORIGIN_HERE,       // Set origin mode
    CAN_PACKET_SET_POS_SPD,           // Position and velocity loop mode
} CAN_PACKET_ID;

// Struct to hold the parsed feedback from the motor
typedef struct {
    float position;      // In degrees
    float velocity;      // In electrical RPM
    float current;       // In Amperes
    int8_t temperature;  // In Celsius
    uint8_t error_code;  // See manual for codes
} MotorFeedback;

// --- Terminal Mode Functions ---
static struct termios oldt;

void enable_non_blocking_mode() {
    struct termios newt;
    tcgetattr(STDIN_FILENO, &oldt);
    newt = oldt;
    newt.c_lflag &= ~(ICANON | ECHO);
    tcsetattr(STDIN_FILENO, TCSANOW, &newt);
    fcntl(STDIN_FILENO, F_SETFL, O_NONBLOCK);
}

void disable_non_blocking_mode() {
    tcsetattr(STDIN_FILENO, TCSANOW, &oldt);
    fcntl(STDIN_FILENO, F_SETFL, 0);
}
// --------------------------------

/**
 * @brief Parses a CAN frame containing motor feedback.
 * Based on the manual, page 39.
 * @param frame The received CAN frame.
 * @param feedback Pointer to the struct where feedback data will be stored.
 */
void unpack_motor_feedback(const struct can_frame *frame, MotorFeedback *feedback) {
    int16_t pos_int = (int16_t)(frame->data[0] << 8 | frame->data[1]);
    int16_t spd_int = (int16_t)(frame->data[2] << 8 | frame->data[3]);
    int16_t cur_int = (int16_t)(frame->data[4] << 8 | frame->data[5]);

    feedback->position = (float)pos_int * 0.1f;
    feedback->velocity = (float)spd_int * 10.0f;
    feedback->current = (float)cur_int * 0.01f;
    feedback->temperature = (int8_t)frame->data[6];
    feedback->error_code = frame->data[7];
}

/**
 * @brief Prints the motor feedback to the console.
 * @param feedback Pointer to the feedback data struct.
 */
void print_feedback(const MotorFeedback *feedback) {
    printf("\rPos: %6.1f deg | Vel: %8.1f eRPM | Cur: %5.2f A | Temp: %3d C | Err: %u",
           feedback->position, feedback->velocity, feedback->current, feedback->temperature, feedback->error_code);
    fflush(stdout);
}


/**
 * @brief Sends a CAN message via a SocketCAN interface.
 *
 * @param s The socket file descriptor.
 * @param id The extended CAN ID (29 bits).
 * @param data Pointer to the data payload array.
 * @param len The length of the data payload (0-8 bytes).
 */
void comm_can_transmit_eid(int s, uint32_t id, const uint8_t *data, uint8_t len) {
    struct can_frame frame;
    memset(&frame, 0, sizeof(frame)); // Clear the frame structure

    // Set the CAN ID. The CAN_EFF_FLAG indicates an extended (29-bit) frame.
    frame.can_id = id | CAN_EFF_FLAG;
    frame.can_dlc = len;
    memcpy(frame.data, data, len);

    // Write the frame to the socket
    if (write(s, &frame, sizeof(struct can_frame)) != sizeof(struct can_frame)) {
        perror("\nCAN write error");
    }
}

/**
 * @brief Appends a 32-bit integer to a buffer in big-endian format.
 * From the manual, page 33.
 * @param buffer The destination buffer.
 * @param number The 32-bit integer to append.
 * @param index Pointer to the current index in the buffer, which is incremented.
 */
void buffer_append_int32(uint8_t* buffer, int32_t number, int32_t *index) {
    buffer[(*index)++] = number >> 24;
    buffer[(*index)++] = number >> 16;
    buffer[(*index)++] = number >> 8;
    buffer[(*index)++] = number;
}

/**
 * @brief Appends a 16-bit integer to a buffer in big-endian format.
 * From the manual, page 33.
 * @param buffer The destination buffer.
 * @param number The 16-bit integer to append.
 * @param index Pointer to the current index in the buffer, which is incremented.
 */
void buffer_append_int16(uint8_t* buffer, int16_t number, int32_t *index) {
    buffer[(*index)++] = number >> 8;
    buffer[(*index)++] = number;
}

/**
 * @brief Sends a command to set the motor's duty cycle.
 * From the manual, page 34.
 * @param s The socket file descriptor.
 * @param controller_id The CAN ID of the target motor controller.
 * @param duty The duty cycle to set (float, e.g., 0.5 for 50%).
 */
void comm_can_set_duty(int s, uint8_t controller_id, float duty) {
    int32_t send_index = 0;
    uint8_t buffer[4];
    buffer_append_int32(buffer, (int32_t)(duty * 100000.0f), &send_index);
    comm_can_transmit_eid(s, controller_id | ((uint32_t)CAN_PACKET_SET_DUTY << 8), buffer, send_index);
}

/**
 * @brief Sends a command to set the motor's current.
 * From the manual, page 34.
 * @param s The socket file descriptor.
 * @param controller_id The CAN ID of the target motor controller.
 * @param current The current in Amperes.
 */
void comm_can_set_current(int s, uint8_t controller_id, float current) {
    int32_t send_index = 0;
    uint8_t buffer[4];
    buffer_append_int32(buffer, (int32_t)(current * 1000.0f), &send_index);
    comm_can_transmit_eid(s, controller_id | ((uint32_t)CAN_PACKET_SET_CURRENT << 8), buffer, send_index);
}

/**
 * @brief Sends a command to activate current brake mode.
 * From the manual, page 35.
 * @param s The socket file descriptor.
 * @param controller_id The CAN ID of the target motor controller.
 * @param current The braking current in Amperes.
 */
void comm_can_set_cb(int s, uint8_t controller_id, float current) {
    int32_t send_index = 0;
    uint8_t buffer[4];
    buffer_append_int32(buffer, (int32_t)(current * 1000.0f), &send_index);
    comm_can_transmit_eid(s, controller_id | ((uint32_t)CAN_PACKET_SET_CURRENT_BRAKE << 8), buffer, send_index);
}

/**
 * @brief Sends a command to set the motor's speed (RPM).
 * From the manual, page 36.
 * @param s The socket file descriptor.
 * @param controller_id The CAN ID of the target motor controller.
 * @param rpm The desired speed in electrical RPM.
 */
void comm_can_set_rpm(int s, uint8_t controller_id, float rpm) {
    int32_t send_index = 0;
    uint8_t buffer[4];
    buffer_append_int32(buffer, (int32_t)rpm, &send_index);
    comm_can_transmit_eid(s, controller_id | ((uint32_t)CAN_PACKET_SET_RPM << 8), buffer, send_index);
}

/**
 * @brief Sends a command to set the motor's position.
 * From the manual, page 37.
 * @param s The socket file descriptor.
 * @param controller_id The CAN ID of the target motor controller.
 * @param pos The desired position in degrees.
 */
void comm_can_set_pos(int s, uint8_t controller_id, float pos) {
    int32_t send_index = 0;
    uint8_t buffer[4];
    // The manual implies a scaling factor of 10,000 for position values.
    buffer_append_int32(buffer, (int32_t)(pos * 10000.0f), &send_index);
    comm_can_transmit_eid(s, controller_id | ((uint32_t)CAN_PACKET_SET_POS << 8), buffer, send_index);
}

/**
 * @brief Sends a command to set the motor's origin.
 * From the manual, page 37-38.
 * @param s The socket file descriptor.
 * @param controller_id The CAN ID of the target motor controller.
 * @param set_origin_mode 0: temporary origin, 1: permanent zero, 2: restore default.
 */
void comm_can_set_origin(int s, uint8_t controller_id, uint8_t set_origin_mode) {
    uint8_t buffer[1];
    buffer[0] = set_origin_mode;
    comm_can_transmit_eid(s, controller_id | ((uint32_t)CAN_PACKET_SET_ORIGIN_HERE << 8), buffer, 1);
}

/**
 * @brief Sends a command to set position with speed and acceleration limits.
 * Based on the manual, page 38.
 * @param s The socket file descriptor.
 * @param controller_id The CAN ID of the target motor controller.
 * @param pos The desired position in degrees.
 * @param spd The speed limit in electrical RPM.
 * @param rpa The acceleration limit in electrical RPM/s^2.
 */
void comm_can_set_pos_spd(int s, uint8_t controller_id, float pos, int16_t spd, int16_t rpa) {
    int32_t send_index = 0;
    uint8_t buffer[8];
    // The manual for this mode states position scale is 10,000.
    buffer_append_int32(buffer, (int32_t)(pos * 10000.0f), &send_index);
    buffer_append_int16(buffer, spd, &send_index);
    buffer_append_int16(buffer, rpa, &send_index);
    comm_can_transmit_eid(s, controller_id | ((uint32_t)CAN_PACKET_SET_POS_SPD << 8), buffer, send_index);
}

/**
 * @brief Generic function to run a continuous motor test for velocity, current, etc.
 * @param s Socket descriptor.
 * @param motor_id The ID of the motor to control.
 * @param send_command_func A function pointer to the specific command to send.
 * @param value The value (e.g., RPM, current) to send in the command.
 * @param mode_name A string name for the mode being tested, for display purposes.
 */
void run_continuous_test(
    int s,
    uint8_t motor_id,
    void (*send_command_func)(int, uint8_t, float),
    float value,
    const char* mode_name
) {
    enable_non_blocking_mode();
    printf("\nContinuously sending %s command. Press 's' to stop.\n", mode_name);

    while(1) {
        send_command_func(s, motor_id, value);

        // Check for feedback
        struct can_frame frame;
        int nbytes = read(s, &frame, sizeof(struct can_frame));
        if (nbytes > 0 && (frame.can_id & CAN_EFF_FLAG) && frame.can_dlc == 8) {
            // Check if the feedback is from our motor
            if ((frame.can_id & 0xFF) == motor_id) {
                MotorFeedback feedback;
                unpack_motor_feedback(&frame, &feedback);
                print_feedback(&feedback);
            }
        }

        // Check for stop command
        if (getchar() == 's') break;
        usleep(10000); // 10ms delay (100 Hz)
    }

    // Send a zero-value command to stop the motor safely
    send_command_func(s, motor_id, 0.0f);
    disable_non_blocking_mode();
    printf("\nStopped %s command.\n", mode_name);
}


/**
 * @brief Handles reading and printing feedback in a loop without sending commands.
 * @param s Socket descriptor.
 * @param motor_id The ID of the motor to monitor.
 */
void read_feedback_loop(int s, uint8_t motor_id) {
    printf("\nReading motor feedback. Press 's' to stop.\n");
    enable_non_blocking_mode();
    while (1) {
        struct can_frame frame;
        int nbytes = read(s, &frame, sizeof(struct can_frame));
        if (nbytes > 0 && (frame.can_id & CAN_EFF_FLAG) && frame.can_dlc == 8) {
            if ((frame.can_id & 0xFF) == motor_id) {
                MotorFeedback feedback;
                unpack_motor_feedback(&frame, &feedback);
                print_feedback(&feedback);
            }
        }

        char c = getchar();
        if (c == 's' || c == 'S') {
            break;
        }
        usleep(10000); // 10ms delay
    }
    disable_non_blocking_mode();
    printf("\nStopped reading feedback.\n");
    while (getchar() != '\n'); // Clear stdin buffer
}


void print_menu() {
    printf("\n=======================================\n");
    printf("      CubeMars Motor Control CLI       \n");
    printf("=======================================\n");
    printf(" 1. Set Duty Cycle (Continuous)\n");
    printf(" 2. Set Current (Continuous)\n");
    printf(" 3. Set Current Brake (Continuous)\n");
    printf(" 4. Set Velocity (Continuous)\n");
    printf(" 5. Set Position (Continuous)\n");
    printf(" 6. Set Position with Vel/Accel (Continuous)\n");
    printf(" 7. Set Origin (Single Command)\n");
    printf(" 8. Read Motor Feedback\n");
    printf(" 0. Exit\n");
    printf("---------------------------------------\n");
    printf("Enter your choice: ");
}

int main(int argc, char *argv[]) {
    int choice;
    uint8_t motor_id;
    int s; // Socket descriptor
    struct sockaddr_can addr;
    struct ifreq ifr;

    if (argc < 2) {
        fprintf(stderr, "Usage: %s <can_interface>\n", argv[0]);
        fprintf(stderr, "Example: %s can0\n", argv[0]);
        return 1;
    }

    // --- SocketCAN Initialization ---
    if ((s = socket(PF_CAN, SOCK_RAW, CAN_RAW)) < 0) {
        perror("Socket creation failed");
        return 1;
    }

    strcpy(ifr.ifr_name, argv[1]);
    if (ioctl(s, SIOCGIFINDEX, &ifr) < 0) {
        perror("ioctl failed");
        close(s);
        return 1;
    }

    addr.can_family = AF_CAN;
    addr.can_ifindex = ifr.ifr_ifindex;

    if (bind(s, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("Bind failed");
        close(s);
        return 1;
    }
    printf("Successfully opened and bound CAN socket on %s\n", argv[1]);
    // --- End SocketCAN Initialization ---

    // Set socket to non-blocking mode to allow reading feedback without halting
    fcntl(s, F_SETFL, O_NONBLOCK);

    printf("\nEnter the Motor Controller CAN ID (0-255): ");
    if (scanf("%hhu", &motor_id) != 1) {
        printf("Invalid ID. Exiting.\n");
        close(s);
        return 1;
    }

    while (1) {
        print_menu();
        if (scanf("%d", &choice) != 1) {
            printf("Invalid input. Please enter a number.\n");
            // Clear input buffer
            while (getchar() != '\n');
            continue;
        }

        switch (choice) {
            case 1: { // Duty Cycle
                float duty;
                printf("Enter Duty Cycle (e.g., 0.5): ");
                scanf("%f", &duty);
                run_continuous_test(s, motor_id, comm_can_set_duty, duty, "Duty Cycle");
                break;
            }
            case 2: { // Current
                float current;
                printf("Enter Current (Amps): ");
                scanf("%f", &current);
                run_continuous_test(s, motor_id, comm_can_set_current, current, "Current");
                break;
            }
             case 3: { // Current Brake
                float brake_current;
                printf("Enter Brake Current (Amps): ");
                scanf("%f", &brake_current);
                run_continuous_test(s, motor_id, comm_can_set_cb, brake_current, "Brake Current");
                break;
            }
            case 4: { // Velocity
                float rpm;
                printf("Enter Velocity (eRPM): ");
                scanf("%f", &rpm);
                run_continuous_test(s, motor_id, comm_can_set_rpm, rpm, "Velocity");
                break;
            }
            case 5: { // Position (Continuous)
                float pos;
                printf("Enter Position (Degrees): ");
                scanf("%f", &pos);

                enable_non_blocking_mode();
                printf("\nContinuously sending Position command. Press 's' to stop.\n");
                while(1) {
                    comm_can_set_pos(s, motor_id, pos);
                    struct can_frame frame;
                    if (read(s, &frame, sizeof(struct can_frame)) > 0 && (frame.can_id & CAN_EFF_FLAG) && (frame.can_id & 0xFF) == motor_id) {
                        MotorFeedback feedback;
                        unpack_motor_feedback(&frame, &feedback);
                        print_feedback(&feedback);
                    }
                    if (getchar() == 's') break;
                    usleep(10000); // 10ms
                }
                disable_non_blocking_mode();
                printf("\nStopped position command.\n");
                break;
            }
            case 6: { // Position with Vel/Accel (Continuous)
                float pos;
                int16_t spd, rpa;
                printf("Enter Position (Degrees): ");
                scanf("%f", &pos);
                printf("Enter Max Speed (eRPM): ");
                scanf("%hd", &spd);
                printf("Enter Acceleration (eRPM/s^2): ");
                scanf("%hd", &rpa);

                enable_non_blocking_mode();
                printf("\nContinuously sending Pos/Vel/Accel command. Press 's' to stop.\n");
                while(1) {
                    comm_can_set_pos_spd(s, motor_id, pos, spd, rpa);
                    struct can_frame frame;
                    if (read(s, &frame, sizeof(struct can_frame)) > 0 && (frame.can_id & CAN_EFF_FLAG) && (frame.can_id & 0xFF) == motor_id) {
                        MotorFeedback feedback;
                        unpack_motor_feedback(&frame, &feedback);
                        print_feedback(&feedback);
                    }
                    if (getchar() == 's') break;
                    usleep(10000); // 10ms
                }
                disable_non_blocking_mode();
                printf("\nStopped position command.\n");
                break;
            }
            case 7: { // Set Origin (Single command)
                uint8_t mode;
                printf("Set Origin Mode (0=Temp, 1=Perm, 2=Restore): ");
                scanf("%hhu", &mode);
                if (mode > 2) {
                    printf("Invalid mode. Must be 0, 1, or 2.\n");
                } else {
                    comm_can_set_origin(s, motor_id, mode);
                    printf("Sent Set Origin command.\n");
                }
                break;
            }
            case 8: { // Read Feedback Only
                read_feedback_loop(s, motor_id);
                break;
            }
            case 0:
                printf("Closing socket and exiting program.\n");
                close(s);
                return 0;
            default:
                printf("Invalid choice. Please try again.\n");
                break;
        }
    }

    close(s);
    return 0;
}

