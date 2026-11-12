
import configparser
import ctypes
from ctypes import wintypes
import tkinter as tk
import cv2
import numpy as np
import os
import socket
import time
from PIL import Image, ImageTk

from tkinter import messagebox

try:
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision
except ImportError:      # no hand drawing without mediapipe
    mp = None

from projector_page import ProjectorPage
from report_page import ReportPage
from settings_page import (
    CAMERA_ROTATIONS,
    DB_CONFIG_FILE,
    DEFAULT_CAMERA_DIRECTION,
    CameraWorkspace,
    MySqlSettingsStore,
    SettingsPage,
    StorageError,
    default_jigs,
    load_station_id,
    show_only_area,
    text_color_for,
)

# ==================================================
# COLORS
# ==================================================

BG = "#121826"
TABLE = "#1E293B"
BORDER = "#64748B"
TEXT = "#F8FAFC"
INACTIVE_TEXT = "#94A3B8"
WHITE = "#FFFFFF"
BLACK = "#000000"
FOCUS_COLOR = "#38BDF8"
HIDDEN_LOOK = ("", "", 0, "")   # box look with no fill, border or label
WARNING_COLOR = "#FBBF24"

ACTIVE_COLORS = [
    WHITE,
    "#FF3030",
    "#00E676",
    WHITE,
    "#FF3030",
    "#00E676",
]

# ==================================================
# VARIABLES
# ==================================================

current_step = 0
blink_on = True

# One dict per BIN of the part, in step order: label, color, jigs (labels
# of the J boxes used with it)
bin_steps = []

store = None
part_var = None         # part number of the part shown; empty until one
                        # is scanned
scan_var = None         # part number being scanned or typed
scan_time = 0.0         # when its last key came in with no textbox in use
welcome_id = None       # WELCOME card with the scan textbox, in the middle
welcome_entry = None    # of the window until the first part is scanned
welcome_message = None
part_status = None
part_values = {}
part_card = None        # PART DETAILS sliding panel and the tab that
part_tab = None         # opens and closes it
part_card_id = None
part_tab_id = None
part_panel_x = None     # left edge of the panel now, and where it slides to
part_panel_target = None
part_slide_job = None
settings_window = None
projector_window = None
report_window = None

current_model = ""      # model of the part shown, for the title and the log
station_id = load_station_id()   # entered on the Settings page
cycle_open = True       # True from BIN1 on while the BINs are only moved
                        # forward; reaching the last BIN then is a cycle
title_label = None
menu_panel = None       # MENU sliding panel and the tab that opens and
menu_tab = None         # closes it
menu_panel_id = None
menu_tab_id = None
menu_panel_h = 0
menu_panel_y = None     # top edge of the panel now, and where it slides to
menu_panel_target = None
menu_slide_job = None
station_label = None    # STATION and QTY labels in the buttons row
quantity_label = None

blink_job = None

camera_capture = None
camera_job = None
workspace = None        # Camera Output: camera picture with draggable boxes
workspace_window = None  # canvas window holding the workspace
camera_size_label = None  # W and H percentages above the Camera Output
raw_frame = None        # latest camera picture as the camera sees it,
                        # turned but not matched to the projector
calibrating = False     # True while the CALIBRATE marks are shown
calibration_canvas = None   # black cover the marks are shown on
calibration_shots = []  # camera pictures of the cover: without a mark,
                        # then with each mark
calibration_quiet = False   # started by the console itself: no warning
                            # when the marks are not seen
calibration_tries = 0   # times the console started it itself
camera_direction = DEFAULT_CAMERA_DIRECTION  # turned with the Settings
                                             # page's Camera View
camera_frame = None     # latest camera picture, turned as shown; read by
                        # the Settings page's camera view
camera_area = None      # part of the camera picture shown for this part,
                        # the rest is black; marked on the Settings page
camera_shown = True     # CAMERA ON/OFF button: picture behind the boxes
camera_button = None
outside_covers = []     # black frames over everything around the camera
                        # picture while the camera is OFF
hand_recognizer = None  # finds hands and their gestures in the camera
                        # picture; None without mediapipe or its model
hand_time = 0           # time in ms given with the last picture

# Hand process of the current step: the hand on the BIN, then on its J
process_stage = "BIN"   # "BIN": waiting for the hand on the BIN, "JIG":
                        # on its J, "DONE": done, next BIN coming
process_box = None      # label of the box under the hand, and since when
process_since = 0.0
process_seen = 0.0      # when the hand was last found on a box
process_jig = None      # J the hand finished on
# Mark of each step in this cycle, by step number: (right process, BIN
# label, J label). Green tick when right, blinking red X when not. All
# are cleared when the focus comes back to BIN1
process_marks = {}
process_job = None      # moves on from the last BIN, after its tick shows

# ==================================================
# MAIN WINDOW
# ==================================================

root = tk.Tk()
root.title("Projector Work Guidance")

# The console is 1500 x 850, made smaller on a PC whose screen it does not
# fit; everything is laid out from this size, so all of it stays in view
WINDOW_W, WINDOW_H = 1500, 850
WINDOW_FRAME_W = 16      # border and title bar around the console
WINDOW_FRAME_H = 40


def screen_room():
    # Width and height of the screen left free by the taskbar
    try:
        area = wintypes.RECT()
        # SPI_GETWORKAREA
        if ctypes.windll.user32.SystemParametersInfoW(
                0x0030, 0, ctypes.byref(area), 0):
            return area.right - area.left, area.bottom - area.top
    except (AttributeError, OSError):
        pass    # not on Windows

    return root.winfo_screenwidth(), root.winfo_screenheight() - 40


room_w, room_h = screen_room()

if (room_w - WINDOW_FRAME_W < WINDOW_W
        or room_h - WINDOW_FRAME_H < WINDOW_H):
    WINDOW_W = min(WINDOW_W, room_w - WINDOW_FRAME_W)
    WINDOW_H = min(WINDOW_H, room_h - WINDOW_FRAME_H)
    # In the screen's top left corner, so none of it is off the screen
    root.geometry(f"{WINDOW_W}x{WINDOW_H}+0+0")
else:
    root.geometry(f"{WINDOW_W}x{WINDOW_H}")

root.minsize(min(1200, WINDOW_W), min(750, WINDOW_H))
root.configure(bg=BG)

canvas = tk.Canvas(
    root,
    bg=BG,
    highlightthickness=0
)
canvas.pack(fill="both", expand=True)

# ==================================================
# SLIDING PANELS
# ==================================================

# The Camera Output fills the window; everything else slides in over it

# PART DETAILS panel, slid in from the left edge of the window
PART_PANEL_W = 300
PART_TAB_W = 26
PART_SLIDE_STEP = 40     # pixels per animation frame
PART_SLIDE_MS = 12

# MENU panel with the title, the buttons and the camera size buttons, slid
# in from the top edge of the window; its tab hangs under its right end
MENU_PAD = 20
MENU_TAB_W = 90

# ==================================================
# CAMERA DIMENSIONS
# ==================================================

CAMERA_INDEX = 0    # 0 = first camera connected to the PC

# Camera Output workspace, filling the window
CAMERA_X1 = 0
CAMERA_Y1 = 0
CAMERA_X2 = WINDOW_W
CAMERA_Y2 = WINDOW_H
CAMERA_BORDER = 0

# Camera picture size and place, set with the buttons above the Camera
# Output so the projected boxes can be matched to the boxes on the camera
# picture: width and height are parts of the Camera Output's (above 1 the
# picture spills over the console around it), x and y move it from the
# center in pixels. Saved on this PC
CAMERA_SIZE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "camera_size_config.ini"
)
CAMERA_SIZE_STEP = 0.01
CAMERA_SIZE_MIN = 0.3
CAMERA_SIZE_MAX = 2.0
CAMERA_MOVE_STEP = 2      # pixels per click
CAMERA_MOVE_MAX = 1000
BUTTON_REPEAT_DELAY = 400   # ms held before a button starts repeating
BUTTON_REPEAT_MS = 50

# The projector shows this window on the table and the camera looks at the
# table from another place, so a box put on a BIN in the camera picture is
# not projected on that BIN. CALIBRATE matches them: it shows a few marks,
# one at a time, on a black window, finds where the camera sees each
# projected mark, and from then on the camera picture is stretched so
# that everything in it is shown where the projector puts it back on
# itself. Saved on this PC with the camera size.
# Until it has been done the console does it by itself, when it starts
# and again when the first part is scanned, in case the projector was
# still off; the CALIBRATE button does it again at any time.
CALIBRATION_START_MS = 3000  # after the console starts, so the camera
                             # has its first pictures
CALIBRATION_TRIES = 2
# Where the marks are shown, as parts of the Camera Output: on the flat
# table between the BINs and the jigs. A mark projected on a BIN is seen
# off its place, as the BIN stands above the table
CALIBRATION_POINTS = ((0.25, 0.5), (0.75, 0.5), (0.75, 0.7), (0.25, 0.7))
# A fifth mark, shown after them, has to be seen where the four say it
# is: something that moved in front of the camera is not taken for marks
CALIBRATION_CHECK = (0.5, 0.6)
CALIBRATION_CHECK_MAX = 0.03    # as a part of the Camera Output
CALIBRATION_MARKS = CALIBRATION_POINTS + (CALIBRATION_CHECK,)
CALIBRATION_MIN_AREA = 0.01     # of the camera picture, between the marks
CALIBRATION_MAX_SPOT = 0.02     # of the camera picture, one mark in it
CALIBRATION_MARK = 30       # radius of a mark, in pixels
CALIBRATION_WAIT_MS = 1000  # a mark is shown this long before the camera
                            # picture of it is taken
CALIBRATION_MIN_DIFF = 40   # a mark is this much brighter (of 255) in the
                            # camera picture than the black window

SCAN_KEY_SECONDS = 2.0      # a scanner types a part number's keys faster
                            # than this apart

# Hands found in the camera picture are drawn on it: dots on the joints,
# lines between them and the gesture's name above the hand. Only shown,
# the steps do not change
GESTURE_MODEL_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "gesture_recognizer.task"
)
MAX_HANDS = 2
HAND_LINE_COLOR = (0, 230, 118)     # RGB
HAND_DOT_COLOR = (255, 48, 48)
HAND_TEXT_COLOR = (255, 255, 255)

# Each step is done by the hand going into its BIN, then staying at its
# J: as soon as any part of the hand touches the BIN the focus moves to
# the J, and when the hand has been at the J for 2 seconds a green tick
# shows between them and the focus moves on to the next BIN by itself.
# The hand at another J after the BIN blinks a red X under the BIN,
# until the right J is done; moving to the next BIN with the arrow key
# before that does too
JIG_HOLD_SECONDS = 2.0
CYCLE_END_MS = 1500         # the full row of marks shows this long after
                            # the last BIN, before they clear at BIN1
WRONG_HOLD_SECONDS = 1.0    # at a wrong J this long, not just passing
HAND_LOST_SECONDS = 0.7     # pictures without the hand this long still
                            # count as being there: the recognizer misses
                            # some pictures, more so of a hand in a BIN
HAND_CONFIDENCE = 0.3       # low, so a hand partly hidden in a BIN or
                            # behind parts is still found
PROCESS_OK_COLOR = "#00E676"
PROCESS_WRONG_COLOR = "#FF3030"
PROCESS_LINE_WIDTH = 14
PROCESS_MARK_SIZE = 22      # half the tick's and X's width, in pixels


def load_camera_view():
    # ([width, height], [x, y]) saved on this PC; the full Camera Output,
    # centered, when none was saved
    config = configparser.ConfigParser()
    config.read(CAMERA_SIZE_FILE, encoding="utf-8")

    def read(name, default, kind, low, high):
        try:
            value = kind(config.get("camera", name, fallback=default))
        except ValueError:
            value = default
        return min(max(value, low), high)

    size = [read(name, 1.0, float, CAMERA_SIZE_MIN, CAMERA_SIZE_MAX)
            for name in ("width", "height")]
    offset = [read(name, 0, int, -CAMERA_MOVE_MAX, CAMERA_MOVE_MAX)
              for name in ("x", "y")]
    return size, offset


def save_camera_view():
    config = configparser.ConfigParser()
    config["camera"] = {
        "width": f"{camera_size[0]:.2f}",
        "height": f"{camera_size[1]:.2f}",
        "x": str(camera_offset[0]),
        "y": str(camera_offset[1]),
    }

    if calibration is not None:
        config["calibration"] = {
            "matrix": " ".join(repr(float(v)) for v in calibration.flatten())
        }

    try:
        with open(CAMERA_SIZE_FILE, "w", encoding="utf-8") as f:
            config.write(f)
    except OSError as e:
        set_part_status(f"Camera size not saved: {first_line(e)}")


def load_calibration():
    # The CALIBRATE result saved on this PC, or None: 3 x 3 numbers that
    # take a place in the camera picture to where it is shown, both as
    # parts of the width and height
    config = configparser.ConfigParser()
    config.read(CAMERA_SIZE_FILE, encoding="utf-8")

    try:
        values = [
            float(value) for value in
            config.get("calibration", "matrix", fallback="").split()
        ]
    except ValueError:
        return None

    if len(values) != 9:
        return None

    return np.array(values).reshape(3, 3)


camera_size, camera_offset = load_camera_view()   # [w, h], [x, y]
calibration = load_calibration()

# ==================================================
# BOX LAYOUT
# ==================================================

def layout_from_settings(settings):
    jig_labels = [j.label for j in settings.jigs]

    return {
        # Bins whose jigs were never picked use the jig with their number
        "bins": [
            {
                "label": b.label,
                "color": b.color,
                "jigs": (
                    b.jigs if b.jigs is not None
                    else default_jigs(b.label, jig_labels)
                ),
            }
            for b in settings.bins
        ],
        "workspace": (
            [("BIN", b.label, b.color, b.cam_x, b.cam_y, b.cam_w, b.cam_h)
             for b in settings.bins]
            + [("JIG", j.label, j.color, j.cam_x, j.cam_y, j.cam_w, j.cam_h)
               for j in settings.jigs]
        ),
    }


def build_boxes(layout):
    global bin_steps, current_step, blink_on

    bin_steps = layout["bins"]
    workspace.set_boxes(layout["workspace"])

    current_step = 0
    blink_on = True
    start_cycle()
    process_marks.clear()   # marks of the part shown before
    reset_process()


def start_cycle():
    global cycle_open

    cycle_open = True


# ==================================================
# PART SELECTION (FROM THE SETTINGS DATABASE)
# ==================================================

def show_part_details(settings):
    global current_model
    global camera_area

    current_model = settings.model_number
    camera_area = settings.area
    title_label.config(
        text=f"{settings.model_number} - {settings.part_number}"
    )
    part_values["part"].config(text=settings.part_number)
    part_values["model"].config(text=settings.model_number)
    part_values["customer"].config(text=settings.customer_name)
    part_values["vendor"].config(text=settings.vendor_code)
    part_values["bins"].config(text=str(settings.bin_count))
    part_values["jigs"].config(text=str(settings.jig_count))
    set_part_status("")
    show_quantity()


def current_station():
    # The Station ID entered on the Settings page; until one is entered the
    # PC's name, so cycles are still counted
    return station_id or socket.gethostname()


def show_station():
    if station_id:
        station_label.config(text=f"STATION: {station_id}", fg=TEXT)
    else:
        # Yellow: the PC's name, not an entered Station ID
        station_label.config(
            text=f"STATION: {current_station()}", fg=WARNING_COLOR
        )


def show_quantity():
    # Cycles of the current part finished today at this station
    part = part_var.get()

    if store is None or not part:
        quantity_label.config(text="QTY: -")
        return

    try:
        quantity = store.count_completed_today(current_station(), part)
    except StorageError as e:
        quantity_label.config(text="QTY: -")
        set_part_status(f"Quantity not loaded: {first_line(e)}")
        return

    quantity_label.config(text=f"QTY: {quantity}")


def record_completed():
    # Called when a cycle reaches the last BIN
    part = part_var.get()

    if store is None or not part:
        return

    try:
        store.record_completed(current_station(), part, current_model)
    except StorageError as e:
        set_part_status(f"Cycle not counted: {first_line(e)}")
        return

    show_quantity()
    flash_quantity()


def flash_quantity(times=4):
    # Blink the QTY label green a few times so the new count is noticed
    if times % 2 == 0:
        quantity_label.config(bg="#00E676", fg=BLACK)
    else:
        quantity_label.config(bg=TABLE, fg="#00E676")

    if times > 1:
        root.after(250, flash_quantity, times - 1)


def set_part_status(text):
    # Warning line at the bottom of the card; hidden when empty. The panel
    # slides open so the warning is seen
    part_status.config(text=text)

    if text:
        part_status.pack(anchor="w", fill="x", pady=(10, 0))
        slide_part_panel(True)
    else:
        part_status.pack_forget()


def first_line(error):
    lines = str(error).splitlines()
    return lines[0] if lines else str(error)


def connect_database():
    global store

    try:
        store = MySqlSettingsStore(DB_CONFIG_FILE)
    except StorageError as e:
        store = None
        set_part_status(f"Database not available: {first_line(e)}")


def load_part(part_number):
    # Shows the part with this number, as it was saved on the Settings
    # page; True when it is shown
    if store is None:
        show_scan_message("Database not available")
        return False

    try:
        settings = store.load(part_number)
    except StorageError as e:
        show_scan_message(f"Database not available: {first_line(e)}")
        return False

    if settings is None:
        show_scan_message(f"Part {part_number} not found")
        return False

    part_var.set(settings.part_number)
    hide_welcome()
    show_part_details(settings)

    build_boxes(layout_from_settings(settings))
    show_step()
    calibrate_if_needed()
    return True


# ==================================================
# WELCOME AND PART SCAN
# ==================================================

def create_welcome():
    global welcome_id, welcome_entry, welcome_message

    # Card in the middle of the window, over the Camera Output
    card = tk.Frame(
        canvas,
        bg=TABLE,
        padx=60,
        pady=36,
        highlightthickness=1,
        highlightbackground=BORDER
    )

    tk.Label(
        card,
        text="WELCOME",
        bg=TABLE,
        fg=FOCUS_COLOR,
        font=("Arial", 44, "bold")
    ).pack()

    tk.Label(
        card,
        text="SCAN THE PART NUMBER",
        bg=TABLE,
        fg=INACTIVE_TEXT,
        font=("Arial", 12, "bold")
    ).pack(pady=(24, 6))

    welcome_entry = create_scan_entry(card, ("Arial", 20, "bold"))
    welcome_entry.config(width=22, justify="center")
    welcome_entry.pack(ipady=6)

    welcome_message = tk.Label(
        card,
        text="",
        bg=TABLE,
        fg=WARNING_COLOR,
        font=("Arial", 11, "bold")
    )
    welcome_message.pack(pady=(10, 0))

    welcome_id = canvas.create_window(
        WINDOW_W / 2, WINDOW_H / 2,
        anchor="center",
        window=card
    )

    welcome_entry.focus_set()


def create_scan_entry(parent, font):
    # Textbox for the part number; the scanner's Enter shows the part
    entry = tk.Entry(
        parent,
        textvariable=scan_var,
        bg=BG,
        fg=TEXT,
        insertbackground=TEXT,
        font=font,
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER,
        highlightcolor=FOCUS_COLOR
    )
    entry.bind("<Return>", scan_part)
    return entry


def welcome_shown():
    return canvas.itemcget(welcome_id, "state") != "hidden"


def hide_welcome():
    canvas.itemconfigure(welcome_id, state="hidden")


def show_scan_message(text):
    # On the WELCOME card while it shows, then on the PART DETAILS panel
    if welcome_shown():
        welcome_message.config(text=text)
    else:
        set_part_status(text)


def scan_part(event=None):
    # Shows the scanned part and no other
    part_number = scan_var.get().strip()
    scan_var.set("")

    if not part_number:
        return

    if load_part(part_number):
        # Give the keyboard back to the window so the arrow keys
        # and SPACE change BINs again
        root.focus_set()


def in_textbox(event):
    # True for a key pressed in a textbox, which is typing and not a
    # shortcut
    return event is not None and isinstance(event.widget, tk.Entry)


def on_scan_key(event):
    # A part number scanned with no textbox in use goes into the scan
    # textbox too, so the next part can be scanned at any time
    global scan_time

    if in_textbox(event) or not event.char or not event.char.isprintable():
        return

    now = time.monotonic()

    # Keys left from long ago are not part of this scan
    if now - scan_time > SCAN_KEY_SECONDS:
        scan_var.set("")

    scan_time = now
    scan_var.set(scan_var.get() + event.char)


def on_scan_enter(event):
    if not in_textbox(event):
        scan_part()


# ==================================================
# SETTINGS WINDOW
# ==================================================

def open_settings(event=None):
    global settings_window

    # Only one Settings window at a time
    if settings_window is not None and settings_window.winfo_exists():
        settings_window.deiconify()
        settings_window.lift()
        settings_window.focus_force()
        return

    if store is None:
        messagebox.showerror(
            "Settings",
            "The database is not available, so settings cannot be opened.",
            parent=root
        )
        return

    settings_window = tk.Toplevel(root)
    settings_window.bind("<Destroy>", on_settings_closed)
    # Over the console: its Camera Output is the same size, in the same
    # place on the screen
    settings_window.geometry(f"+{root.winfo_x()}+{root.winfo_y()}")

    # Opens on the part selected here
    SettingsPage(
        settings_window,
        store,
        part_number=part_var.get() or None,
        on_saved=on_settings_saved,
        get_camera_frame=lambda: camera_frame,
        get_camera_view=camera_view,
        get_camera_direction=lambda: camera_direction,
        set_camera_direction=set_camera_direction,
        on_station_saved=on_station_saved
    )


def on_settings_saved(settings):
    # Show the saved layout here straight away, when it is of the part
    # shown; another part shows only when it is scanned
    if settings.part_number == part_var.get():
        load_part(settings.part_number)


def on_station_saved(new_station_id):
    global station_id

    station_id = new_station_id
    show_station()
    show_quantity()


def on_settings_closed(event):
    global settings_window

    # <Destroy> also fires for every widget inside the window
    if event.widget is settings_window:
        settings_window = None


# ==================================================
# PROJECTOR WINDOW
# ==================================================

def open_projector(event=None):
    global projector_window

    # Only one Projector window at a time, so the COM port is opened once
    if projector_window is not None and projector_window.winfo_exists():
        projector_window.deiconify()
        projector_window.lift()
        projector_window.focus_force()
        return

    projector_window = tk.Toplevel(root)
    projector_window.bind("<Destroy>", on_projector_closed, add="+")
    ProjectorPage(projector_window)


def open_report(event=None):
    global report_window

    # Only one Report window at a time
    if report_window is not None and report_window.winfo_exists():
        report_window.deiconify()
        report_window.lift()
        report_window.focus_force()
        return

    if store is None:
        messagebox.showwarning(
            "Report",
            "The database is not available, so the report cannot be opened.",
            parent=root
        )
        return

    report_window = tk.Toplevel(root)
    report_window.bind("<Destroy>", on_report_closed)

    # Opens on the part shown here
    ReportPage(
        report_window,
        store,
        model_number=current_model or None,
        part_number=part_var.get() or None
    )


def on_report_closed(event):
    global report_window

    # <Destroy> also fires for every widget inside the window
    if event.widget is report_window:
        report_window = None
        root.focus_force()


def on_projector_closed(event):
    global projector_window

    # <Destroy> also fires for every widget inside the window
    if event.widget is projector_window:
        projector_window = None


def create_part_panel():
    global part_status

    global part_card, part_tab, part_card_id, part_tab_id
    global part_panel_x, part_panel_target

    # Card with a colored accent strip on the left
    part_card = tk.Frame(
        canvas,
        bg=TABLE,
        highlightthickness=1,
        highlightbackground=BORDER
    )

    tk.Frame(part_card, bg=FOCUS_COLOR, width=5).pack(side="left", fill="y")

    body = tk.Frame(part_card, bg=TABLE, padx=14, pady=12)
    body.pack(side="left", fill="both", expand=True)

    tk.Label(
        body,
        text="PART DETAILS",
        bg=TABLE,
        fg=TEXT,
        font=("Arial", 13, "bold")
    ).pack(anchor="w", pady=(0, 6))

    # (key, caption, value color), one under the other
    fields = [
        ("part", "PART NUMBER", TEXT),
        ("model", "MODEL", TEXT),
        ("customer", "CUSTOMER", TEXT),
        ("vendor", "VENDOR", TEXT),
        ("bins", "BINS", FOCUS_COLOR),
        ("jigs", "JIGS", "#00E676"),
    ]

    # Textbox to scan the next part
    tk.Label(
        body,
        text="SCAN PART NUMBER",
        bg=TABLE,
        fg=INACTIVE_TEXT,
        font=("Arial", 9, "bold")
    ).pack(anchor="w")

    create_scan_entry(body, ("Arial", 11, "bold")).pack(
        anchor="w", fill="x", pady=(3, 0), ipady=3
    )

    for key, caption, color in fields:

        # Thin divider between fields
        tk.Frame(body, bg=BORDER, height=1).pack(fill="x", pady=6)

        tk.Label(
            body,
            text=caption,
            bg=TABLE,
            fg=INACTIVE_TEXT,
            font=("Arial", 9, "bold")
        ).pack(anchor="w")

        value = tk.Label(
            body,
            text="-",
            anchor="w",
            justify="left",
            wraplength=PART_PANEL_W - 50,
            bg=TABLE,
            fg=color,
            font=("Arial", 12, "bold")
        )
        value.pack(anchor="w", fill="x", pady=(3, 0))
        part_values[key] = value

    part_status = tk.Label(
        body,
        text="",
        anchor="w",
        justify="left",
        wraplength=PART_PANEL_W - 50,
        bg=TABLE,
        fg="#FBBF24",
        font=("Arial", 10, "bold")
    )

    # Tab on the panel's right edge; still shows when the panel is closed
    part_tab = tk.Button(
        canvas,
        text="",
        command=toggle_part_panel,
        bg=FOCUS_COLOR,
        fg=BLACK,
        activebackground=TEXT,
        activeforeground=BLACK,
        font=("Arial", 10, "bold"),
        relief="flat",
        bd=0,
        pady=8,
        cursor="hand2"
    )

    # Starts closed, over the top left corner of the Camera Output
    part_panel_x = part_panel_target = -PART_PANEL_W
    top = 0

    part_card_id = canvas.create_window(
        part_panel_x, top,
        anchor="nw",
        width=PART_PANEL_W,
        window=part_card
    )

    part_tab_id = canvas.create_window(
        part_panel_x + PART_PANEL_W, top,
        anchor="nw",
        width=PART_TAB_W,
        window=part_tab
    )

    show_part_tab()


def show_part_tab():
    # The arrow shows which way clicking the tab slides the panel
    arrow = "◀" if part_panel_target > -PART_PANEL_W else "▶"
    part_tab.config(text=arrow + "\n\nP\nA\nR\nT")


def toggle_part_panel():
    slide_part_panel(part_panel_target == -PART_PANEL_W)


def slide_part_panel(open_panel):
    global part_panel_target

    target = 0 if open_panel else -PART_PANEL_W

    if target == part_panel_target:
        return

    part_panel_target = target
    show_part_tab()

    if part_slide_job is None:
        slide_part_step()


def place_part_panel():
    # Under the MENU panel as far as that is slid in, so it does not
    # cover the top of the part details
    top = max(menu_panel_y + menu_panel_h, 0) if menu_panel_id else 0

    canvas.coords(part_card_id, part_panel_x, top)
    canvas.coords(part_tab_id, part_panel_x + PART_PANEL_W, top)


def slide_part_step():
    # Moves the panel and its tab a step toward where they slide to
    global part_panel_x, part_slide_job

    distance = part_panel_target - part_panel_x
    step = max(-PART_SLIDE_STEP, min(PART_SLIDE_STEP, distance))
    part_panel_x += step

    place_part_panel()

    if part_panel_x == part_panel_target:
        part_slide_job = None
    else:
        part_slide_job = root.after(PART_SLIDE_MS, slide_part_step)


def create_menu_tab():
    global menu_tab, menu_panel_id, menu_tab_id
    global menu_panel_h, menu_panel_y, menu_panel_target

    # Tab under the panel's right end; still shows when the panel is closed
    menu_tab = tk.Button(
        canvas,
        text="",
        command=toggle_menu_panel,
        bg=FOCUS_COLOR,
        fg=BLACK,
        activebackground=TEXT,
        activeforeground=BLACK,
        font=("Arial", 10, "bold"),
        relief="flat",
        bd=0,
        pady=2,
        cursor="hand2"
    )

    # Starts closed, above the top edge of the Camera Output
    root.update_idletasks()
    menu_panel_h = menu_panel.winfo_reqheight()
    menu_panel_y = menu_panel_target = -menu_panel_h

    menu_panel_id = canvas.create_window(
        0, menu_panel_y,
        anchor="nw",
        width=WINDOW_W,
        window=menu_panel
    )

    menu_tab_id = canvas.create_window(
        WINDOW_W - MENU_PAD, menu_panel_y + menu_panel_h,
        anchor="ne",
        width=MENU_TAB_W,
        window=menu_tab
    )

    # Over the PART DETAILS panel
    menu_panel.lift()
    show_menu_tab()


def show_menu_tab():
    # The arrow shows which way clicking the tab slides the panel
    arrow = "▲" if menu_panel_target == 0 else "▼"
    menu_tab.config(text=arrow + "  MENU")


def toggle_menu_panel():
    global menu_panel_target

    menu_panel_target = 0 if menu_panel_target != 0 else -menu_panel_h
    show_menu_tab()

    if menu_slide_job is None:
        slide_menu_step()


def slide_menu_step():
    # Moves the panel and its tab a step toward where they slide to
    global menu_panel_y, menu_slide_job

    distance = menu_panel_target - menu_panel_y
    step = max(-PART_SLIDE_STEP, min(PART_SLIDE_STEP, distance))
    menu_panel_y += step

    canvas.coords(menu_panel_id, 0, menu_panel_y)
    canvas.coords(
        menu_tab_id, WINDOW_W - MENU_PAD, menu_panel_y + menu_panel_h
    )
    place_part_panel()

    if menu_panel_y == menu_panel_target:
        menu_slide_job = None
    else:
        menu_slide_job = root.after(PART_SLIDE_MS, slide_menu_step)


# ==================================================
# DRAW INTERFACE
# ==================================================

def draw_interface():
    global camera_button
    global title_label
    global station_label
    global quantity_label
    global menu_panel
    global part_var, scan_var

    part_var = tk.StringVar()
    scan_var = tk.StringVar()

    # MENU panel: the title and the buttons in its first row, the camera
    # size buttons in its second
    menu_panel = tk.Frame(
        canvas,
        bg=BG,
        padx=MENU_PAD,
        pady=10,
        highlightthickness=1,
        highlightbackground=BORDER
    )

    first_row = tk.Frame(menu_panel, bg=BG)
    first_row.pack(fill="x")

    # Model and part number of the part shown
    title_label = tk.Label(
        first_row,
        text="NO PART SELECTED",
        bg=BG,
        fg=TEXT,
        font=("Arial", 22, "bold")
    )
    title_label.pack(side="left")

    # Buttons row on the right, from right to left
    bar = tk.Frame(first_row, bg=BG)
    bar.pack(side="right")

    def top_button(text, command):
        button = tk.Button(
            bar,
            text=text,
            command=command,
            bg=TABLE,
            fg=TEXT,
            activebackground=FOCUS_COLOR,
            activeforeground=BLACK,
            font=("Arial", 11, "bold"),
            relief="flat",
            padx=16,
            pady=6,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=FOCUS_COLOR
        )
        button.pack(side="right", padx=(10, 0))
        return button

    def top_label(text):
        label = tk.Label(
            bar,
            text=text,
            bg=TABLE,
            fg=TEXT,
            font=("Arial", 11, "bold"),
            padx=14,
            pady=7,
            highlightthickness=1,
            highlightbackground=BORDER
        )
        label.pack(side="right", padx=(10, 0))
        return label

    # Opens the Settings form
    top_button("⚙  SETTINGS", open_settings)

    # Opens the projector power control (RS232)
    top_button("PROJECTOR", open_projector)

    # Shows or hides the camera picture in the Camera Output
    camera_button = top_button("", toggle_camera)
    camera_button.config(width=11, padx=0)

    # Opens the production report
    top_button("REPORT", open_report)

    # Parts of this part finished today at this station, and the station
    quantity_label = top_label("QTY: -")
    quantity_label.config(fg="#00E676")
    station_label = top_label("")
    show_station()

    show_camera_button()

    second_row = tk.Frame(menu_panel, bg=BG)
    second_row.pack(fill="x", pady=(10, 0))

    tk.Label(
        second_row,
        text="CAMERA OUTPUT",
        bg=BG,
        fg=INACTIVE_TEXT,
        font=("Arial", 9, "bold")
    ).pack(side="left")

    create_camera_size_buttons(second_row)

    create_camera_workspace()

    # Made after the Camera Output so the panels slide in over it
    create_part_panel()
    create_menu_tab()

    # Shown until the first part is scanned
    create_welcome()

    # Black covers for the camera OFF view, over everything else
    create_outside_covers()


# ==================================================
# UPDATE BIN AND J BOXES
# ==================================================

def show_step():
    if not bin_steps:
        return

    step = bin_steps[current_step]
    bin_name = step["label"]

    # Fill color from the Settings page, or the standard color for this
    # step when none was set
    step_color = (
        step["color"]
        or ACTIVE_COLORS[current_step % len(ACTIVE_COLORS)]
    )

    # The focus blinks on the BIN until the hand has held it, then on its
    # jigs until the hand has held one; after that nothing blinks
    bin_focus = process_stage == "BIN"
    jig_focus = process_stage == "JIG"

    # Light up the boxes on the Camera Output: (fill, outline, outline
    # width, text color) of each box
    for box in workspace.boxes:
        is_jig = box.kind == "JIG" and box.label in step["jigs"]
        fill_color = box.color or step_color
        jig_look = (fill_color, FOCUS_COLOR if jig_focus else WHITE, 4,
                    text_color_for(fill_color))

        if not camera_shown:
            # Camera OFF: only the selected BIN and its jigs are drawn, the
            # focused ones blinking; every other box has no fill, border
            # or label, so nothing else is shown
            if box.label == bin_name and (blink_on or not bin_focus):
                look = (step_color, FOCUS_COLOR if bin_focus else WHITE, 4,
                        text_color_for(step_color))
            elif is_jig and (blink_on or not jig_focus):
                look = jig_look
            else:
                look = HIDDEN_LOOK

        elif box.label == bin_name:
            # Selected BIN blinks while it has the focus
            if not bin_focus:
                look = (step_color, WHITE, 4, text_color_for(step_color))
            elif blink_on:
                look = (step_color, FOCUS_COLOR, 4,
                        text_color_for(step_color))
            else:
                look = (TABLE, FOCUS_COLOR, 4, FOCUS_COLOR)

        elif is_jig:
            # The BIN's jigs get their own fill color, or the BIN's color
            # when they have none, and a white border; they blink once the
            # focus moves to them
            if jig_focus and not blink_on:
                look = (TABLE, FOCUS_COLOR, 4, FOCUS_COLOR)
            else:
                look = jig_look

        else:
            # Remaining boxes stay dark
            look = (TABLE, BORDER, 2, INACTIVE_TEXT)

        workspace.set_look(box, look)

    draw_process()


# ==================================================
# BLINK ACTIVE BIN
# ==================================================

def blink():
    global blink_on
    global blink_job

    blink_on = not blink_on
    show_step()

    blink_job = root.after(500, blink)


# ==================================================
# CAMERA
# ==================================================

def create_camera_workspace():
    global workspace
    global workspace_window

    # Black around a camera picture made smaller than the Camera Output
    canvas.create_rectangle(
        CAMERA_X1, CAMERA_Y1,
        CAMERA_X2, CAMERA_Y2,
        fill=BLACK,
        outline=""
    )

    # Camera picture with a box for every BIN and J, where and as big as
    # saved on the Settings page; they cannot be moved here
    workspace = CameraWorkspace(canvas, movable=False)

    workspace_window = canvas.create_window(
        (CAMERA_X1 + CAMERA_X2) / 2, (CAMERA_Y1 + CAMERA_Y2) / 2,
        anchor="center",
        window=workspace.canvas
    )
    # Behind the buttons and panels, which stay usable when the picture is
    # made bigger than the Camera Output
    # (Canvas.lower moves drawings, so the widget one is called)
    tk.Misc.lower(workspace.canvas)
    fit_workspace()


def create_camera_size_buttons(parent):
    global camera_size_label

    # Size (W, H) and move (arrows) buttons at the right end of the CAMERA
    # OUTPUT title, the size and place between them, and RESET for the
    # full, centered Camera Output. Holding a button repeats it
    row = tk.Frame(parent, bg=BG)

    def size_button(text, command, repeat=True):
        button = tk.Button(
            row,
            text=text,
            command=command,
            bg=TABLE,
            fg=TEXT,
            activebackground=FOCUS_COLOR,
            activeforeground=BLACK,
            font=("Arial", 8, "bold"),
            relief="flat",
            padx=6,
            pady=0,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=BORDER
        )
        if repeat:
            button.config(
                repeatdelay=BUTTON_REPEAT_DELAY,
                repeatinterval=BUTTON_REPEAT_MS
            )
        button.pack(side="left", padx=(4, 0))
        return button

    size_button("W -", lambda: change_camera_size(0, -CAMERA_SIZE_STEP))
    size_button("W +", lambda: change_camera_size(0, CAMERA_SIZE_STEP))
    size_button("H -", lambda: change_camera_size(1, -CAMERA_SIZE_STEP))
    size_button("H +", lambda: change_camera_size(1, CAMERA_SIZE_STEP))

    camera_size_label = tk.Label(
        row,
        text="",
        bg=BG,
        fg=INACTIVE_TEXT,
        font=("Arial", 8, "bold"),
        width=36
    )
    camera_size_label.pack(side="left", padx=(4, 0))

    size_button("◀", lambda: move_camera(0, -CAMERA_MOVE_STEP))
    size_button("▶", lambda: move_camera(0, CAMERA_MOVE_STEP))
    size_button("▲", lambda: move_camera(1, -CAMERA_MOVE_STEP))
    size_button("▼", lambda: move_camera(1, CAMERA_MOVE_STEP))
    size_button("RESET", reset_camera_size, repeat=False)
    size_button("CALIBRATE", start_calibration, repeat=False)

    row.pack(side="right")
    show_camera_size()


def show_camera_size():
    camera_size_label.config(
        text=(
            f"W {round(camera_size[0] * 100)}%"
            f"  H {round(camera_size[1] * 100)}%"
            f"  X {camera_offset[0]:+d}"
            f"  Y {camera_offset[1]:+d}"
            + ("  CALIBRATED" if calibration is not None else "")
        )
    )


def change_camera_size(index, step):
    # index 0 = width, 1 = height
    value = round(camera_size[index] + step, 2)
    camera_size[index] = min(max(value, CAMERA_SIZE_MIN), CAMERA_SIZE_MAX)
    camera_size_changed()


def move_camera(index, step):
    # index 0 = left / right, 1 = up / down
    value = camera_offset[index] + step
    camera_offset[index] = min(max(value, -CAMERA_MOVE_MAX), CAMERA_MOVE_MAX)
    camera_size_changed()


def reset_camera_size():
    # Also back to the picture as the camera sees it
    global calibration

    camera_size[0] = camera_size[1] = 1.0
    camera_offset[0] = camera_offset[1] = 0
    calibration = None
    camera_size_changed()


def camera_size_changed():
    show_camera_size()
    fit_workspace()
    save_camera_view()


def fit_workspace():
    # The workspace is the W and H parts of the Camera Output, centered and
    # then moved by X and Y; at 100% and no move it fills it, so the
    # picture is stretched out to the edges. The Settings page shows its
    # picture at this same size and place. The box positions and sizes
    # are parts of the workspace, so the boxes stretch with the picture
    # and land on the same spots of it as on the Settings page
    x1, y1, x2, y2 = workspace_bounds()

    canvas.coords(workspace_window, (x1 + x2) / 2, (y1 + y2) / 2)
    canvas.itemconfigure(
        workspace_window,
        width=max(int(x2 - x1), 1),
        height=max(int(y2 - y1), 1)
    )
    show_outside_covers()


def workspace_bounds():
    # Left, top, right and bottom of the camera picture on the console
    area_w, area_h = camera_area_size()
    width = area_w * camera_size[0]
    height = area_h * camera_size[1]
    center_x = (CAMERA_X1 + CAMERA_X2) / 2 + camera_offset[0]
    center_y = (CAMERA_Y1 + CAMERA_Y2) / 2 + camera_offset[1]

    return (
        center_x - width / 2, center_y - height / 2,
        center_x + width / 2, center_y + height / 2,
    )


def camera_area_size():
    # Width and height of the Camera Output, inside its border
    return (
        CAMERA_X2 - CAMERA_X1 - 2 * CAMERA_BORDER,
        CAMERA_Y2 - CAMERA_Y1 - 2 * CAMERA_BORDER,
    )


def camera_view():
    # Size of the Camera Output and the camera picture's left, top, width
    # and height inside it, in pixels; the Settings page shows its Camera
    # Output and picture the same
    x1, y1, x2, y2 = workspace_bounds()
    return camera_area_size() + (
        x1 - CAMERA_X1 - CAMERA_BORDER, y1 - CAMERA_Y1 - CAMERA_BORDER,
        max(int(x2 - x1), 1), max(int(y2 - y1), 1),
    )


def calibrate_if_needed():
    # Done by the console itself, without a warning when it cannot be
    global calibration_tries

    if (calibration is not None or calibrating
            or calibration_tries >= CALIBRATION_TRIES):
        return

    calibration_tries += 1
    start_calibration(quiet=True)


def start_calibration(quiet=False):
    global calibrating, calibration_canvas, calibration_quiet

    if calibrating:
        return

    if camera_capture is None:
        if not quiet:
            messagebox.showwarning(
                "Calibrate",
                "The camera is not available, so it cannot be matched to "
                "the projector.",
                parent=root
            )
        return

    calibrating = True
    calibration_quiet = quiet
    calibration_shots.clear()

    # Black over the whole window, so the camera sees only the marks
    calibration_canvas = tk.Canvas(root, bg=BLACK, highlightthickness=0)
    calibration_canvas.place(x=0, y=0, relwidth=1, relheight=1)
    show_calibration_mark(-1)


def show_calibration_mark(index):
    # index -1 shows no mark: the black window alone
    calibration_canvas.delete("all")

    if index >= 0:
        x1, y1, x2, y2 = workspace_bounds()
        part_x, part_y = CALIBRATION_MARKS[index]
        x = x1 + part_x * (x2 - x1)
        y = y1 + part_y * (y2 - y1)
        calibration_canvas.create_oval(
            x - CALIBRATION_MARK, y - CALIBRATION_MARK,
            x + CALIBRATION_MARK, y + CALIBRATION_MARK,
            fill=WHITE,
            outline=""
        )

    root.after(CALIBRATION_WAIT_MS, take_calibration_shot, index)


def take_calibration_shot(index):
    if raw_frame is not None:
        calibration_shots.append(
            cv2.cvtColor(raw_frame, cv2.COLOR_BGR2GRAY)
        )

    if index + 1 < len(CALIBRATION_MARKS):
        show_calibration_mark(index + 1)
    else:
        finish_calibration()


def finish_calibration():
    global calibrating, calibration_canvas, calibration

    calibration_canvas.destroy()
    calibration_canvas = None
    calibrating = False

    found = find_calibration(calibration_shots)
    calibration_shots.clear()

    if found is None:
        if calibration_quiet:
            return

        messagebox.showwarning(
            "Calibrate",
            "The camera did not see all the marks, so nothing was "
            "changed.\n\nThe projector must be on and showing this "
            "window, and the camera must see the place it is projected "
            "on.",
            parent=root
        )
        return

    calibration = found
    camera_size_changed()


def find_calibration(shots):
    # From the pictures of the black window and of each mark: the numbers
    # that take a place in the camera picture to where it is to be shown,
    # or None when a mark was not seen
    if len(shots) != len(CALIBRATION_MARKS) + 1:
        return None

    seen = [find_calibration_mark(shots, index)
            for index in range(1, len(shots))]

    if None in seen:
        return None

    corners = np.float32(seen[:len(CALIBRATION_POINTS)])

    # Marks seen in a line, crossed over or all in one spot are not the
    # four marks
    if (not cv2.isContourConvex(corners.reshape(-1, 1, 2))
            or cv2.contourArea(corners) < CALIBRATION_MIN_AREA):
        return None

    found = cv2.getPerspectiveTransform(
        corners, np.float32(CALIBRATION_POINTS)
    )

    # The fifth mark is seen where the four say it is
    x, y, part = found @ np.array([*seen[-1], 1.0])

    if part == 0 or max(
            abs(x / part - CALIBRATION_CHECK[0]),
            abs(y / part - CALIBRATION_CHECK[1])) > CALIBRATION_CHECK_MAX:
        return None

    return found


def find_calibration_mark(shots, index):
    # Middle of the mark in its camera picture, shots[index], as parts of
    # the picture's width and height: the small spot that is brighter
    # than in every other picture; None when there is none
    shot = shots[index]
    others = shots[:index] + shots[index + 1:]
    brighter = cv2.GaussianBlur(
        cv2.subtract(shot, np.maximum.reduce(others)), (21, 21), 0
    )
    _low, high, _where, (x, y) = cv2.minMaxLoc(brighter)

    if high < CALIBRATION_MIN_DIFF:
        return None

    bright = (brighter >= high / 2).astype(np.uint8)
    _count, spots = cv2.connectedComponents(bright)
    spot = (spots == spots[y, x]).astype(np.uint8)

    if spot.mean() > CALIBRATION_MAX_SPOT:
        return None

    moments = cv2.moments(spot, binaryImage=True)
    height, width = shot.shape

    return (
        moments["m10"] / moments["m00"] / width,
        moments["m01"] / moments["m00"] / height,
    )


def match_projector(frame):
    # The camera picture stretched so that what it shows is projected
    # back on itself; as it is until CALIBRATE has been done
    if calibration is None:
        return frame

    height, width = frame.shape[:2]
    size = np.diag([width, height, 1.0])

    return cv2.warpPerspective(
        frame,
        size @ calibration @ np.linalg.inv(size),
        (width, height)
    )


def open_camera():
    global camera_capture

    # CAP_DSHOW opens USB cameras quickly on Windows
    capture = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)

    if capture.isOpened():
        camera_capture = capture
        message = "Starting camera..."
    else:
        capture.release()
        message = f"Camera {CAMERA_INDEX} not found or cannot open"

    workspace.show_message(message)


def open_hand_recognizer():
    global hand_recognizer

    # Without it the console runs as before; the terminal says why no
    # hands are shown
    if mp is None:
        print("Hands not shown: mediapipe is not installed "
              "(pip install -r requirements.txt)")
        return

    if not os.path.exists(GESTURE_MODEL_FILE):
        print(f"Hands not shown: {GESTURE_MODEL_FILE} not found")
        return

    options = vision.GestureRecognizerOptions(
        base_options=BaseOptions(model_asset_path=GESTURE_MODEL_FILE),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=MAX_HANDS,
        min_hand_detection_confidence=HAND_CONFIDENCE,
        min_hand_presence_confidence=HAND_CONFIDENCE,
        min_tracking_confidence=HAND_CONFIDENCE
    )

    try:
        hand_recognizer = vision.GestureRecognizer.create_from_options(
            options
        )
    except (RuntimeError, ValueError) as e:
        print(f"Hands not shown: {first_line(e)}")
        hand_recognizer = None


def find_hands(frame):
    # Hands in an RGB camera picture: a (joints, gesture name) pair for
    # each, the joints as (x, y) parts of the picture's width and height
    if hand_recognizer is None:
        return []

    global hand_time

    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
    # The recognizer needs a later time for every picture, even two read
    # within the same millisecond
    hand_time = max(int(time.monotonic() * 1000), hand_time + 1)
    result = hand_recognizer.recognize_for_video(image, hand_time)

    hands = []

    for index, landmarks in enumerate(result.hand_landmarks):
        name = ""
        if index < len(result.gestures) and result.gestures[index]:
            name = result.gestures[index][0].category_name

        # "None" is a hand with no known gesture
        if name in ("", "None"):
            name = "HAND"

        joints = [(point.x, point.y) for point in landmarks]
        hands.append((joints, name.replace("_", " ").upper()))

    return hands


def draw_hands(frame, hands):
    # Draws the hands on the picture as it is shown, so the lines keep
    # their thickness whatever the Camera Output's size
    height, width = frame.shape[:2]

    for joints, name in hands:
        points = [(int(x * width), int(y * height)) for x, y in joints]

        for connection in vision.HandLandmarksConnections.HAND_CONNECTIONS:
            cv2.line(
                frame,
                points[connection.start], points[connection.end],
                HAND_LINE_COLOR, 2
            )

        for point in points:
            cv2.circle(frame, point, 4, HAND_DOT_COLOR, -1)

        left = min(x for x, _ in points)
        top = max(min(y for _, y in points) - 12, 20)
        cv2.putText(
            frame, name, (left, top),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, HAND_TEXT_COLOR, 2
        )


def hand_boxes(hands):
    # Labels of the boxes any part of a hand touches: the rectangle around
    # its joints overlaps the box. The camera picture fills the workspace,
    # so a place in the picture is the same place among the boxes
    touched = set()

    for joints, _name in hands:
        xs = [x for x, _ in joints]
        ys = [y for _, y in joints]

        for box in workspace.boxes:
            if (min(xs) <= box.x + box.w and box.x <= max(xs)
                    and min(ys) <= box.y + box.h and box.y <= max(ys)):
                touched.add(box.label)

    return touched


def reset_process():
    # Start the current step's hand process again
    global process_stage, process_box, process_jig, process_job

    if process_job is not None:
        root.after_cancel(process_job)
        process_job = None

    process_stage = "BIN"
    process_box = None
    process_jig = None
    draw_process()


def check_process(hands):
    # Follows the hand: into the BIN, then 2 seconds at its J
    global process_stage, process_box, process_since, process_jig
    global process_seen, process_job

    if not bin_steps or process_stage == "DONE":
        show_hold(None)
        return

    step = bin_steps[current_step]
    touched = hand_boxes(hands)
    now = time.monotonic()

    if process_stage == "BIN":
        if step["label"] in touched:
            # In the BIN: the blinking stops and the focus moves to the J
            process_stage = "JIG"
            process_box = None
            show_step()
        return

    # At the J: the right J counts over another one the hand also touches
    right = [label for label in step["jigs"] if label in touched]
    wrong = [label for label in touched
             if is_jig(label) and label not in step["jigs"]]
    label = (right or wrong or [None])[0]

    if label is not None:
        process_seen = now
    elif now - process_seen < HAND_LOST_SECONDS:
        label = process_box   # missed for a moment: still there

    if label != process_box:
        process_box = label
        process_since = now

    held = now - process_since

    if label in step["jigs"]:
        show_hold(label, held, JIG_HOLD_SECONDS)

        if held >= JIG_HOLD_SECONDS:
            # Right process: green tick, and on to the next BIN
            process_stage = "DONE"
            process_jig = label
            set_mark(True)
            show_hold(None)
            show_step()
            if current_step == len(bin_steps) - 1:
                process_job = root.after(CYCLE_END_MS, next_step)
            else:
                next_step()
        return

    show_hold(None)

    if (label is not None and held >= WRONG_HOLD_SECONDS
            and current_step not in process_marks):
        # Another J after the BIN: red X, the focus stays on the right J
        set_mark(False)
        draw_process()


def is_jig(label):
    return any(box.label == label and box.kind == "JIG"
               for box in workspace.boxes)


def show_hold(label, held=0.0, needed=0.0):
    # Seconds the hand has held the box against the seconds needed, above
    # the box; label None hides it
    workspace.canvas.delete("hold")

    if label is None:
        return

    width, height = workspace.size()

    for box in workspace.boxes:
        if box.label == label:
            workspace.canvas.create_text(
                (box.x + box.w / 2) * width,
                box.y * height - 4,
                anchor="s",
                text=f"{min(held, needed):.1f} / {needed:.0f} s",
                fill=PROCESS_OK_COLOR,
                font=("Arial", 14, "bold"),
                tags="hold"
            )
            return


def mark_step():
    # Called as the arrow key leaves the step: red X when its process was
    # not done
    if process_stage != "DONE" and current_step not in process_marks:
        set_mark(False)


def set_mark(right):
    # Green tick (right) or red X for the current step, in place of the
    # mark it has
    if not bin_steps:
        return

    step = bin_steps[current_step]
    jig = process_jig or (step["jigs"][0] if step["jigs"] else None)
    process_marks[current_step] = (right, step["label"], jig)


def draw_process():
    # A green tick for each step done right and a blinking red X for each
    # done wrong, the same size, in one row just under the lowest BIN, each
    # under its own BIN; drawn over the boxes
    workspace.canvas.delete("process")

    width, height = workspace.size()
    size = PROCESS_MARK_SIZE
    bins = {box.label: box for box in workspace.boxes if box.kind == "BIN"}

    if not bins:
        return

    lowest = max((box.y + box.h) * height for box in bins.values())
    y = lowest + size + PROCESS_LINE_WIDTH

    for right, bin_label, _jig in process_marks.values():
        box = bins.get(bin_label)

        if box is None:
            continue

        x = (box.x + box.w / 2) * width

        if right:
            lines = [(x - size, y, x - size / 3, y + size,
                      x + size, y - size)]
            color = PROCESS_OK_COLOR
        elif blink_on:
            lines = [(x - size, y - size, x + size, y + size),
                     (x + size, y - size, x - size, y + size)]
            color = PROCESS_WRONG_COLOR
        else:
            continue

        for points in lines:
            workspace.canvas.create_line(
                *points,
                fill=color,
                width=PROCESS_LINE_WIDTH,
                capstyle="round",
                joinstyle="round",
                tags="process"
            )


def set_camera_direction(direction):
    # Called by the Settings page's Camera View buttons
    global camera_direction, calibration

    # The marks were seen in the picture as it was turned before
    if direction != camera_direction and calibration is not None:
        calibration = None
        camera_direction = direction
        camera_size_changed()

    camera_direction = direction


def toggle_camera():
    global camera_shown

    camera_shown = not camera_shown
    show_camera_button()

    if not camera_shown:
        workspace.clear_picture()

    # Camera OFF shows only the selected BIN and its jigs, blinking
    show_step()
    show_outside_covers()


def create_outside_covers():
    # Four black frames, above, below, left and right of the camera
    # picture. They are on top of the console's buttons and panels
    # but not of the picture; clicking one turns the camera ON
    for _ in range(4):
        cover = tk.Frame(canvas, bg=BLACK, cursor="hand2")
        cover.bind("<Button-1>", lambda event: toggle_camera())
        outside_covers.append(cover)


def show_outside_covers():
    # With the camera OFF everything outside the camera picture is black,
    # so the projector shows only the BIN and J boxes
    if camera_shown:
        for cover in outside_covers:
            cover.place_forget()
        return

    x1, y1, x2, y2 = workspace_bounds()
    far = 10000   # past the window's right and bottom edges

    places = [
        (0, 0, far, y1),               # above
        (0, y2, far, far),             # below
        (0, y1, x1, y2 - y1),          # left
        (x2, y1, far, y2 - y1),        # right
    ]

    for cover, (x, y, width, height) in zip(outside_covers, places):
        cover.place(
            x=int(x), y=int(y),
            width=max(int(width), 0), height=max(int(height), 0)
        )
        cover.lift()


def show_camera_button():
    # The label says what clicking the button does
    if camera_shown:
        camera_button.config(text="CAMERA OFF", fg=BLACK, bg=FOCUS_COLOR)
    else:
        camera_button.config(text="CAMERA ON", fg=TEXT, bg=TABLE)


def update_camera():
    global camera_job
    global camera_frame
    global raw_frame

    if camera_capture is not None:

        success, frame = camera_capture.read()
        width, height = workspace.size()

        # The workspace has no size until the window is shown
        if success and width > 1 and height > 1:

            rotation = CAMERA_ROTATIONS[camera_direction]

            if rotation is not None:
                frame = cv2.rotate(frame, rotation)

            raw_frame = frame
            frame = match_projector(frame)
            camera_frame = frame

            # The hands are followed with the camera OFF too, when the
            # projector shows only the boxes
            frame = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2RGB
            )

            hands = find_hands(frame)

            # No step is done by a hand seen while the marks are shown
            if not calibrating:
                check_process(hands)

            # With the camera OFF the picture is still read for the
            # Settings page's camera view, but not shown here
            if camera_shown:

                # Stretched to fill the workspace, like the boxes
                frame = cv2.resize(
                    frame,
                    (width, height)
                )

                draw_hands(frame, hands)
                show_only_area(frame, camera_area)

                image = Image.fromarray(frame)
                workspace.show_picture(ImageTk.PhotoImage(image))

    camera_job = root.after(30, update_camera)


# ==================================================
# NAVIGATION: FIRST ROW ONLY
# ==================================================

def change_step(direction):
    global current_step, blink_on, cycle_open

    if not bin_steps:
        return

    if direction == 1:
        mark_step()

    # Navigate only through the BIN boxes of the selected part
    current_step = (current_step + direction) % len(bin_steps)

    # Back at BIN1 a new cycle starts without marks; a BIN gone back to
    # is done again without its old mark
    if current_step == 0:
        process_marks.clear()
    else:
        process_marks.pop(current_step, None)

    # A cycle starts at BIN1 and goes forward BIN by BIN; reaching the
    # last BIN finishes it and counts one. Going back a BIN cancels it, so
    # stepping back and forth on the last BIN does not count again.
    if current_step == 0:
        start_cycle()
    elif direction == -1:
        cycle_open = False

    if (direction == 1 and cycle_open
            and current_step == len(bin_steps) - 1):
        cycle_open = False
        record_completed()

    blink_on = True

    reset_process()
    show_step()


def next_step(event=None):
    if not in_textbox(event):
        change_step(1)


def previous_step(event=None):
    if not in_textbox(event):
        change_step(-1)


# ==================================================
# CLOSE APPLICATION
# ==================================================

def close_application(event=None):

    if blink_job is not None:
        root.after_cancel(blink_job)

    if camera_job is not None:
        root.after_cancel(camera_job)

    if process_job is not None:
        root.after_cancel(process_job)

    if camera_capture is not None:
        camera_capture.release()

    if hand_recognizer is not None:
        hand_recognizer.close()

    root.destroy()


# ==================================================
# KEYBOARD SHORTCUTS
# ==================================================

root.bind("<Right>", next_step)
root.bind("<Left>", previous_step)
root.bind("<space>", next_step)
root.bind("<Escape>", close_application)
root.bind("<Key>", on_scan_key)
root.bind("<Return>", on_scan_enter)

# ==================================================
# START APPLICATION
# ==================================================

draw_interface()

# No part shows until its number is scanned on the WELCOME card
connect_database()

open_camera()
open_hand_recognizer()

blink_job = root.after(500, blink)
camera_job = root.after(30, update_camera)
root.after(CALIBRATION_START_MS, calibrate_if_needed)

root.protocol(
    "WM_DELETE_WINDOW",
    close_application
)

root.mainloop()
