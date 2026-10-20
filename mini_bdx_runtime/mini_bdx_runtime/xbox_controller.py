import contextlib
import time
from queue import Queue
from threading import Thread

import numpy as np
import pygame

from mini_bdx_runtime.buttons import Buttons

X_RANGE = [-0.15, 0.15]
# Sideways slower than forward: no policy ever stepped sideways faster than
# ~0.13 m/s, and training now draws +-0.1 (Open_Duck_Playground run14).
Y_RANGE = [-0.1, 0.1]
YAW_RANGE = [-1.0, 1.0]

# rads
NECK_PITCH_RANGE = [-0.34, 1.1]
HEAD_PITCH_RANGE = [-0.78, 0.3]
HEAD_YAW_RANGE = [-0.5, 0.5]
HEAD_ROLL_RANGE = [-0.5, 0.5]

# Raw pygame (SDL evdev backend) axis/button indices per controller family.
# Buttons are named after their Xbox position (A = bottom face button, ...).
LAYOUTS: dict[str, dict[str, dict[str, int]]] = {
    "xbox": {
        "axes": {"lx": 0, "ly": 1, "rx": 2, "ry": 3, "rt": 4, "lt": 5},
        "buttons": {"A": 0, "B": 1, "X": 3, "Y": 4, "LB": 6, "RB": 7},
    },
    # DualShock 4 / DualSense (hid_playstation): cross, circle, square, triangle, L1, R1
    "playstation": {
        "axes": {"lx": 0, "ly": 1, "lt": 2, "rx": 3, "ry": 4, "rt": 5},
        "buttons": {"A": 0, "B": 1, "X": 3, "Y": 2, "LB": 4, "RB": 5},
    },
}

# Trigger readings below this are treated as fully released.
TRIGGER_DEADZONE = 0.1
# Stick readings below this are treated as centred: canard's right stick rests
# at 0.03-0.04, which the policy takes for a slow turn and steps to. The range
# past it is rescaled, so a full push is still 1.
STICK_DEADZONE = 0.08
# Decimal places commands and triggers are rounded to.
ROUND_DECIMALS = 3
# The worker only keeps the most recent command.
CMD_QUEUE_SIZE = 1


def stick(v: float) -> float:
    if abs(v) <= STICK_DEADZONE:
        return 0.0
    return float(np.sign(v)) * (abs(v) - STICK_DEADZONE) / (1 - STICK_DEADZONE)


def detect_layout(joystick_name: str) -> str:
    name = joystick_name.lower()
    # "Xbox Wireless Controller" would otherwise match the PS4's bare name.
    if "xbox" in name or "microsoft" in name:
        return "xbox"
    playstation_keys = ("wireless controller", "playstation", "sony", "dualsense", "ps4", "ps5")
    if any(k in name for k in playstation_keys):
        return "playstation"
    return "xbox"


class XBoxController:
    def __init__(self, command_freq: float, only_head_control: bool = False) -> None:
        self.command_freq = command_freq
        self.head_control_mode = only_head_control
        self.only_head_control = only_head_control

        self.last_commands = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        self.last_left_trigger = 0.0
        self.last_right_trigger = 0.0
        pygame.init()
        # The controller may be absent at startup or drop out later (Bluetooth):
        # it is (re)opened on JOYDEVICEADDED and dropped on JOYDEVICEREMOVED.
        self.p1: pygame.joystick.JoystickType | None = None
        self.layout: dict[str, dict[str, int]] | None = None
        if pygame.joystick.get_count() > 0:
            self.open_joystick(0)
        else:
            print("No joystick connected, waiting for one.")
        self.cmd_queue: Queue = Queue(maxsize=CMD_QUEUE_SIZE)

        self.A_pressed = False
        self.B_pressed = False
        self.X_pressed = False
        self.Y_pressed = False
        self.LB_pressed = False
        self.RB_pressed = False

        self.buttons = Buttons()

        Thread(target=self.commands_worker, daemon=True).start()

    def open_joystick(self, device_index: int) -> None:
        p1 = pygame.joystick.Joystick(device_index)
        p1.init()
        layout_name = detect_layout(p1.get_name())
        self.p1 = p1
        self.layout = LAYOUTS[layout_name]
        print(
            f"Loaded joystick '{p1.get_name()}' with {p1.get_numaxes()} axes"
            f" ({layout_name} layout)."
        )

    def close_joystick(self) -> None:
        if self.p1 is not None:
            print(f"Joystick '{self.p1.get_name()}' disconnected.")
        self.p1 = None
        self.layout = None
        self.last_commands = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        self.last_left_trigger = 0.0
        self.last_right_trigger = 0.0
        # A button held during the drop-out never gets its JOYBUTTONUP; clear it
        # so reconnecting doesn't register as a fresh press (and e.g. unpause).
        self.A_pressed = False
        self.B_pressed = False
        self.X_pressed = False
        self.Y_pressed = False
        self.LB_pressed = False
        self.RB_pressed = False

    def is_connected(self) -> bool:
        return self.p1 is not None

    def commands_worker(self) -> None:
        while True:
            self.cmd_queue.put(self.get_commands())
            time.sleep(1 / self.command_freq)

    def get_commands(self) -> tuple:
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.JOYDEVICEADDED and self.p1 is None:
                self.open_joystick(event.device_index)
            elif (
                event.type == pygame.JOYDEVICEREMOVED
                and self.p1 is not None
                and event.instance_id == self.p1.get_instance_id()
            ):
                self.close_joystick()

        if self.p1 is None or self.layout is None:
            return (
                np.zeros(7),
                False,
                False,
                False,
                False,
                False,
                False,
                0.0,
                0.0,
                0,
            )

        last_commands = self.last_commands
        left_trigger = self.last_left_trigger
        right_trigger = self.last_right_trigger

        axes = self.layout["axes"]
        buttons = self.layout["buttons"]

        l_x = -stick(self.p1.get_axis(axes["lx"]))
        l_y = -stick(self.p1.get_axis(axes["ly"]))
        r_x = -stick(self.p1.get_axis(axes["rx"]))

        right_trigger = np.around((self.p1.get_axis(axes["rt"]) + 1) / 2, ROUND_DECIMALS)
        left_trigger = np.around((self.p1.get_axis(axes["lt"]) + 1) / 2, ROUND_DECIMALS)

        if left_trigger < TRIGGER_DEADZONE:
            left_trigger = 0
        if right_trigger < TRIGGER_DEADZONE:
            right_trigger = 0

        if not self.head_control_mode:
            lin_vel_y = l_x
            lin_vel_x = l_y
            ang_vel = r_x
            if lin_vel_x >= 0:
                lin_vel_x *= np.abs(X_RANGE[1])
            else:
                lin_vel_x *= np.abs(X_RANGE[0])

            if lin_vel_y >= 0:
                lin_vel_y *= np.abs(Y_RANGE[1])
            else:
                lin_vel_y *= np.abs(Y_RANGE[0])

            if ang_vel >= 0:
                ang_vel *= np.abs(YAW_RANGE[1])
            else:
                ang_vel *= np.abs(YAW_RANGE[0])

            last_commands[0] = lin_vel_x
            last_commands[1] = lin_vel_y
            last_commands[2] = ang_vel
        else:
            last_commands[0] = 0.0
            last_commands[1] = 0.0
            last_commands[2] = 0.0
            last_commands[3] = 0.0  # neck pitch 0 for now

            head_yaw = l_x
            head_pitch = l_y
            head_roll = r_x

            if head_yaw >= 0:
                head_yaw *= np.abs(HEAD_YAW_RANGE[0])
            else:
                head_yaw *= np.abs(HEAD_YAW_RANGE[1])

            if head_pitch >= 0:
                head_pitch *= np.abs(HEAD_PITCH_RANGE[0])
            else:
                head_pitch *= np.abs(HEAD_PITCH_RANGE[1])

            if head_roll >= 0:
                head_roll *= np.abs(HEAD_ROLL_RANGE[0])
            else:
                head_roll *= np.abs(HEAD_ROLL_RANGE[1])

            last_commands[4] = head_pitch
            last_commands[5] = head_yaw
            last_commands[6] = head_roll

        for event in events:
            if event.type == pygame.JOYBUTTONDOWN:

                if self.p1.get_button(buttons["A"]):
                    self.A_pressed = True

                if self.p1.get_button(buttons["B"]):
                    self.B_pressed = True

                if self.p1.get_button(buttons["X"]):
                    self.X_pressed = True

                if self.p1.get_button(buttons["Y"]):
                    self.Y_pressed = True
                    if not self.only_head_control:
                        self.head_control_mode = not self.head_control_mode

                if self.p1.get_button(buttons["LB"]):
                    self.LB_pressed = True

                if self.p1.get_button(buttons["RB"]):
                    self.RB_pressed = True

            if event.type == pygame.JOYBUTTONUP:
                self.A_pressed = False
                self.B_pressed = False
                self.X_pressed = False
                self.Y_pressed = False
                self.LB_pressed = False
                self.RB_pressed = False

        up_down = self.p1.get_hat(0)[1] if self.p1.get_numhats() > 0 else 0

        return (
            np.around(last_commands, ROUND_DECIMALS),
            self.A_pressed,
            self.B_pressed,
            self.X_pressed,
            self.Y_pressed,
            self.LB_pressed,
            self.RB_pressed,
            left_trigger,
            right_trigger,
            up_down,
        )

    def get_last_command(self) -> tuple:
        A_pressed = False
        B_pressed = False
        X_pressed = False
        Y_pressed = False
        LB_pressed = False
        RB_pressed = False
        up_down = 0
        with contextlib.suppress(Exception):
            (
                self.last_commands,
                A_pressed,
                B_pressed,
                X_pressed,
                Y_pressed,
                LB_pressed,
                RB_pressed,
                self.last_left_trigger,
                self.last_right_trigger,
                up_down,
            ) = self.cmd_queue.get(False)  # non blocking

        self.buttons.update(
            A_pressed,
            B_pressed,
            X_pressed,
            Y_pressed,
            LB_pressed,
            RB_pressed,
            up_down == 1,
            up_down == -1,
        )

        return (
            self.last_commands,
            self.buttons,
            self.last_left_trigger,
            self.last_right_trigger,
        )

if __name__ == "__main__":
    controller = XBoxController(20)

    while True:
        print(controller.get_last_command())
        time.sleep(0.05)
