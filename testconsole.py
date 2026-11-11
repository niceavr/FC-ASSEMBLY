
import configparser
import tkinter as tk
from tkinter import ttk
import cv2
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
    text_color_for,
)

# ==================================================
# STEP DETAILS
# ==================================================

steps = [
    ("BIN1", "Pick the required spanner"),
    ("BIN2", "Place cable in assembly area"),
    ("BIN3", "Inspect and confirm OK"),
    ("BIN4", "Connect the required cable"),
    ("BIN5", "Perform the required test"),
    ("BIN6", "Complete final inspection"),
]

video_files = [
    "one.mp4",
    "two.mp4",
    "three.mp4",
    "four.mp4",
    "five.mp4",
    "six.mp4",
]

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

instruction_id = None
video_status_id = None
video_image_id = None
store = None
part_var = None
part_combo = None
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
title_id = None
station_label = None    # STATION and QTY labels in the buttons row
quantity_label = None

video_capture = None
video_photo = None
video_job = None
blink_job = None

camera_capture = None
camera_job = None
workspace = None        # Camera Output: camera picture with draggable boxes
workspace_window = None  # canvas window holding the workspace
camera_size_label = None  # W and H percentages above the Camera Output
camera_direction = DEFAULT_CAMERA_DIRECTION  # turned with the Settings
                                             # page's Camera View
camera_frame = None     # latest camera picture, turned as shown; read by
                        # the Settings page's camera view
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
# Mark left on each step passed with the arrow key in this cycle, by step
# number: (right process, BIN label, J label). Green tick when right,
# blinking red X when not
process_marks = {}

# ==================================================
# MAIN WINDOW
# ==================================================

root = tk.Tk()
root.title("Projector Work Guidance")
root.geometry("1500x850")
root.minsize(1200, 750)
root.configure(bg=BG)

canvas = tk.Canvas(
    root,
    bg=BG,
    highlightthickness=0
)
canvas.pack(fill="both", expand=True)

# ==================================================
# WORK AREA DIMENSIONS
# ==================================================

# The work area spans the window: the Camera Output with the step video in
# the top right corner; the part details slide in over the Camera Output
WORK_X1 = 20
WORK_X2 = 1480
WORK_Y1 = 80
WORK_Y2 = 745
WORK_PAD = 10

# PART DETAILS panel, slid in from the left edge of the work area
PART_PANEL_W = 300
PART_TAB_W = 26
PART_SLIDE_STEP = 40     # pixels per animation frame
PART_SLIDE_MS = 12

# ==================================================
# VIDEO DIMENSIONS
# ==================================================

# Step video: 20% of the original 655 x 400 box, in the top right corner
# of the work area
VIDEO_X2 = WORK_X2 - WORK_PAD - 4
VIDEO_X1 = VIDEO_X2 - 131
VIDEO_Y1 = 110
VIDEO_Y2 = VIDEO_Y1 + 80

VIDEO_W = VIDEO_X2 - VIDEO_X1 - 6
VIDEO_H = VIDEO_Y2 - VIDEO_Y1 - 6

# ==================================================
# CAMERA DIMENSIONS
# ==================================================

CAMERA_INDEX = 0    # 0 = first camera connected to the PC

# Camera Output workspace, filling the work area left of the step video
CAMERA_X1 = WORK_X1 + WORK_PAD
CAMERA_Y1 = WORK_Y1 + 26
CAMERA_X2 = VIDEO_X1 - 15
CAMERA_Y2 = WORK_Y2 - WORK_PAD
CAMERA_BORDER = 3

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

    try:
        with open(CAMERA_SIZE_FILE, "w", encoding="utf-8") as f:
            config.write(f)
    except OSError as e:
        set_part_status(f"Camera size not saved: {first_line(e)}")


camera_size, camera_offset = load_camera_view()   # [w, h], [x, y]

# ==================================================
# STEP HELPERS
# ==================================================

def step_description(index):
    # Parts can have up to 12 bins; steps beyond the list get a generic text
    if index < len(steps):
        return steps[index][1]
    return f"Work at BIN{index + 1}"


def step_video(index):
    if index < len(video_files):
        return video_files[index]
    return None


# ==================================================
# BOX LAYOUT
# ==================================================

def default_layout():
    # Six BIN and six J boxes, BIN1 with J1 and so on, used when no part
    # is loaded
    labels = (
        [("BIN", f"BIN{i}") for i in range(1, 7)]
        + [("JIG", f"J{i}") for i in range(1, 7)]
    )

    return {
        "bins": [
            {"label": f"BIN{i}", "color": "", "jigs": [f"J{i}"]}
            for i in range(1, 7)
        ],
        # No saved Camera Output positions: the workspace places them
        "workspace": [
            (kind, label, "", None, None, None, None)
            for kind, label in labels
        ],
    }


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

    current_model = settings.model_number
    canvas.itemconfigure(
        title_id, text=f"{settings.model_number} - {settings.part_number}"
    )
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


def refresh_parts():
    # Runs every time the dropdown opens, so parts saved on the
    # Settings page while this window is open also appear
    if store is None:
        return

    try:
        parts = store.list_parts()
    except StorageError as e:
        set_part_status(f"Database not available: {first_line(e)}")
        return

    part_combo["values"] = parts


def load_part(part_number=None):
    # part_number=None loads the most recently saved part
    if store is None:
        return

    try:
        settings = store.load(part_number)
    except StorageError as e:
        set_part_status(f"Database not available: {first_line(e)}")
        return

    if settings is None:
        set_part_status(
            "No parts saved yet. Add one on the Settings page."
        )
        return

    part_var.set(settings.part_number)
    show_part_details(settings)

    build_boxes(layout_from_settings(settings))
    show_step()
    open_current_video()


def on_part_selected(event=None):
    load_part(part_var.get())

    # Give the keyboard back to the window so the arrow keys
    # and SPACE change BINs again
    root.focus_set()


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

    # Opens on the part selected here
    SettingsPage(
        settings_window,
        store,
        part_number=part_var.get() or None,
        on_saved=on_settings_saved,
        get_camera_frame=lambda: camera_frame,
        get_camera_direction=lambda: camera_direction,
        set_camera_direction=set_camera_direction,
        on_station_saved=on_station_saved
    )


def on_settings_saved(settings):
    # Show the saved layout here straight away
    refresh_parts()
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
    global part_var, part_combo, part_status

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(
        "Part.TCombobox",
        fieldbackground=BG,
        background=BG,
        foreground=TEXT,
        arrowcolor=FOCUS_COLOR,
        bordercolor=BORDER,
        lightcolor=BG,
        darkcolor=BG,
        arrowsize=14,
        padding=(6, 3),
    )
    style.map(
        "Part.TCombobox",
        fieldbackground=[("readonly", BG)],
        background=[("active", TABLE), ("readonly", BG)],
        foreground=[("readonly", TEXT)],
        selectbackground=[("readonly", BG)],
        selectforeground=[("readonly", TEXT)],
        bordercolor=[("focus", FOCUS_COLOR), ("active", FOCUS_COLOR)],
        lightcolor=[("focus", BG)],
        darkcolor=[("focus", BG)],
    )
    root.option_add("*TCombobox*Listbox.background", TABLE)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", FOCUS_COLOR)
    root.option_add("*TCombobox*Listbox.selectForeground", BLACK)

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

    part_var = tk.StringVar()

    for index, (key, caption, color) in enumerate(fields):

        # Thin divider between fields
        if index > 0:
            tk.Frame(body, bg=BORDER, height=1).pack(fill="x", pady=6)

        tk.Label(
            body,
            text=caption,
            bg=TABLE,
            fg=INACTIVE_TEXT,
            font=("Arial", 9, "bold")
        ).pack(anchor="w")

        if key == "part":
            part_combo = ttk.Combobox(
                body,
                textvariable=part_var,
                state="readonly",
                font=("Arial", 11, "bold"),
                style="Part.TCombobox",
                postcommand=refresh_parts
            )
            part_combo.pack(anchor="w", fill="x", pady=(3, 0))
            part_combo.bind("<<ComboboxSelected>>", on_part_selected)

        else:
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
    top = CAMERA_Y1 + CAMERA_BORDER

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

    target = WORK_X1 + 2 if open_panel else -PART_PANEL_W

    if target == part_panel_target:
        return

    part_panel_target = target
    show_part_tab()

    if part_slide_job is None:
        slide_part_step()


def slide_part_step():
    # Moves the panel and its tab a step toward where they slide to
    global part_panel_x, part_slide_job

    distance = part_panel_target - part_panel_x
    step = max(-PART_SLIDE_STEP, min(PART_SLIDE_STEP, distance))
    part_panel_x += step

    top = CAMERA_Y1 + CAMERA_BORDER
    canvas.coords(part_card_id, part_panel_x, top)
    canvas.coords(part_tab_id, part_panel_x + PART_PANEL_W, top)

    if part_panel_x == part_panel_target:
        part_slide_job = None
    else:
        part_slide_job = root.after(PART_SLIDE_MS, slide_part_step)


# ==================================================
# DRAW INTERFACE
# ==================================================

def draw_interface():
    global instruction_id
    global video_status_id
    global camera_button
    global title_id
    global station_label
    global quantity_label

    # Model and part number of the part shown
    title_id = canvas.create_text(
        WORK_X1, 38,
        anchor="w",
        text="NO PART SELECTED",
        fill=TEXT,
        font=("Arial", 22, "bold")
    )

    # Buttons row on the right, from right to left
    bar = tk.Frame(canvas, bg=BG)

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

    canvas.create_window(
        WORK_X2, 38,
        anchor="e",
        window=bar
    )
    show_camera_button()

    # Work area
    canvas.create_rectangle(
        WORK_X1, WORK_Y1, WORK_X2, WORK_Y2,
        fill=BG,
        outline=BORDER,
        width=2
    )

    # Video rectangle
    canvas.create_rectangle(
        VIDEO_X1, VIDEO_Y1,
        VIDEO_X2, VIDEO_Y2,
        fill=BLACK,
        outline=BORDER,
        width=3
    )

    canvas.create_text(
        VIDEO_X1, VIDEO_Y1 - 14,
        anchor="w",
        text="STEP VIDEO",
        fill=TEXT,
        font=("Arial", 11, "bold")
    )

    video_status_id = canvas.create_text(
        (VIDEO_X1 + VIDEO_X2) / 2,
        (VIDEO_Y1 + VIDEO_Y2) / 2,
        text="Loading video...",
        fill=TEXT,
        font=("Arial", 8)
    )

    create_camera_workspace()

    # Made after the Camera Output so the panel slides in over it
    create_part_panel()

    # Black covers for the camera OFF view, over everything else
    create_outside_covers()

    # Instruction panel, kept short so the Camera Output above it can be
    # tall
    canvas.create_rectangle(
        20, 755, 1480, 805,
        fill=TABLE,
        outline=BORDER,
        width=2
    )

    instruction_id = canvas.create_text(
        750, 780,
        text="",
        fill=TEXT,
        font=("Arial", 18, "bold"),
        width=1400
    )

    canvas.create_text(
        750, 828,
        text=(
            "LEFT / RIGHT ARROW: Change BIN"
            "     SPACE: Next BIN"
            "     BIN1 to the last BIN: 1 cycle (QTY + 1)"
            "     ESC: Exit"
        ),
        fill=INACTIVE_TEXT,
        font=("Arial", 11)
    )


# ==================================================
# UPDATE BIN AND J BOXES
# ==================================================

def show_step():
    if not bin_steps:
        return

    step = bin_steps[current_step]
    bin_name = step["label"]
    description = step_description(current_step)

    # Fill color from the Settings page, or the standard color for this
    # step when none was set
    step_color = (
        step["color"]
        or ACTIVE_COLORS[current_step % len(ACTIVE_COLORS)]
    )

    canvas.itemconfigure(
        instruction_id,
        text=f"CURRENT INSTRUCTION: {bin_name}: {description}"
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
# OPEN CURRENT VIDEO
# ==================================================

def open_current_video():
    global video_capture
    global video_photo
    global video_image_id
    global video_status_id

    if video_capture is not None:
        video_capture.release()
        video_capture = None

    video_photo = None

    if video_image_id is not None:
        canvas.delete(video_image_id)
        video_image_id = None

    if video_status_id is not None:
        canvas.delete(video_status_id)
        video_status_id = None

    filename = step_video(current_step)

    folder = os.path.dirname(
        os.path.abspath(__file__)
    )

    if filename is None:
        video_path = None
        filename = f"no video set for step {current_step + 1}"
    else:
        video_path = os.path.join(folder, filename)

    if video_path and os.path.isfile(video_path):
        capture = cv2.VideoCapture(video_path)

        if capture.isOpened():
            video_capture = capture
        else:
            capture.release()

    if video_capture is None:
        video_status_id = canvas.create_text(
            (VIDEO_X1 + VIDEO_X2) / 2,
            (VIDEO_Y1 + VIDEO_Y2) / 2,
            text=f"Video not found:\n{filename}",
            fill=TEXT,
            font=("Arial", 8),
            width=VIDEO_W - 6
        )


# ==================================================
# PLAY VIDEO CONTINUOUSLY
# ==================================================

def update_video():
    global video_photo
    global video_image_id
    global video_status_id
    global video_job

    if video_capture is not None:

        success, frame = video_capture.read()

        # Loop when video reaches the end
        if not success:
            video_capture.set(
                cv2.CAP_PROP_POS_FRAMES, 0
            )
            success, frame = video_capture.read()

        if success:

            frame = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2RGB
            )

            frame = cv2.resize(
                frame,
                (VIDEO_W, VIDEO_H)
            )

            image = Image.fromarray(frame)
            video_photo = ImageTk.PhotoImage(image)

            center_x = (VIDEO_X1 + VIDEO_X2) / 2
            center_y = (VIDEO_Y1 + VIDEO_Y2) / 2

            if video_status_id is not None:
                canvas.delete(video_status_id)
                video_status_id = None

            if video_image_id is None:
                video_image_id = canvas.create_image(
                    center_x,
                    center_y,
                    image=video_photo
                )
            else:
                canvas.itemconfigure(
                    video_image_id,
                    image=video_photo
                )

    video_job = root.after(30, update_video)


# ==================================================
# CAMERA
# ==================================================

def create_camera_workspace():
    global workspace
    global workspace_window

    canvas.create_rectangle(
        CAMERA_X1, CAMERA_Y1,
        CAMERA_X2, CAMERA_Y2,
        fill=BLACK,
        outline=BORDER,
        width=CAMERA_BORDER
    )

    canvas.create_text(
        CAMERA_X1, CAMERA_Y1 - 10,
        anchor="w",
        text="CAMERA OUTPUT",
        fill=INACTIVE_TEXT,
        font=("Arial", 9, "bold")
    )

    create_camera_size_buttons()

    # Camera picture with a draggable box for every BIN and J
    workspace = CameraWorkspace(canvas, on_moved=save_workspace_positions)

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


def create_camera_size_buttons():
    global camera_size_label

    # Size (W, H) and move (arrows) buttons at the right end of the CAMERA
    # OUTPUT title, the size and place between them, and RESET for the
    # full, centered Camera Output. Holding a button repeats it
    row = tk.Frame(canvas, bg=BG)

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
        width=30
    )
    camera_size_label.pack(side="left", padx=(4, 0))

    size_button("◀", lambda: move_camera(0, -CAMERA_MOVE_STEP))
    size_button("▶", lambda: move_camera(0, CAMERA_MOVE_STEP))
    size_button("▲", lambda: move_camera(1, -CAMERA_MOVE_STEP))
    size_button("▼", lambda: move_camera(1, CAMERA_MOVE_STEP))
    size_button("RESET", reset_camera_size, repeat=False)

    canvas.create_window(
        CAMERA_X2, CAMERA_Y1 - 12,
        anchor="e",
        window=row
    )
    show_camera_size()


def show_camera_size():
    camera_size_label.config(
        text=(
            f"W {round(camera_size[0] * 100)}%"
            f"  H {round(camera_size[1] * 100)}%"
            f"  X {camera_offset[0]:+d}"
            f"  Y {camera_offset[1]:+d}"
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
    camera_size[0] = camera_size[1] = 1.0
    camera_offset[0] = camera_offset[1] = 0
    camera_size_changed()


def camera_size_changed():
    show_camera_size()
    fit_workspace()
    save_camera_view()


def fit_workspace():
    # The workspace is the W and H parts of the Camera Output, centered and
    # then moved by X and Y; at 100% and no move it fills it, so the
    # picture is stretched out to the edges. The box positions and sizes
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
    width = (CAMERA_X2 - CAMERA_X1 - 2 * CAMERA_BORDER) * camera_size[0]
    height = (CAMERA_Y2 - CAMERA_Y1 - 2 * CAMERA_BORDER) * camera_size[1]
    center_x = (CAMERA_X1 + CAMERA_X2) / 2 + camera_offset[0]
    center_y = (CAMERA_Y1 + CAMERA_Y2) / 2 + camera_offset[1]

    return (
        center_x - width / 2, center_y - height / 2,
        center_x + width / 2, center_y + height / 2,
    )


def save_workspace_positions(positions):
    # Remember where the boxes were dragged to and their sizes, for the
    # part shown
    part = part_var.get()

    if store is None or not part:
        return

    try:
        store.save_camera_positions(part, positions)
    except StorageError as e:
        set_part_status(f"Box positions not saved: {first_line(e)}")


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
    global process_stage, process_box, process_jig

    process_stage = "BIN"
    process_box = None
    process_jig = None
    draw_process()


def check_process(hands):
    # Follows the hand: into the BIN, then 2 seconds at its J
    global process_stage, process_box, process_since, process_jig
    global process_seen

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
    # mark it has. Marks from the last cycle stay until BIN1 is marked
    if not bin_steps:
        return

    step = bin_steps[current_step]

    if current_step == 0:
        process_marks.clear()

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
    global camera_direction

    camera_direction = direction


def toggle_camera():
    global camera_shown

    camera_shown = not camera_shown
    show_camera_button()

    if not camera_shown:
        workspace.clear_picture()
        # A clicked box's selection outline would show on a hidden box
        workspace.select(None)

    # Camera OFF shows only the selected BIN and its jigs, blinking
    show_step()
    show_outside_covers()


def create_outside_covers():
    # Four black frames, above, below, left and right of the camera
    # picture. They are on top of the console's buttons, panels and step
    # video but not of the picture; clicking one turns the camera ON
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

    if camera_capture is not None:

        success, frame = camera_capture.read()
        width, height = workspace.size()

        # The workspace has no size until the window is shown
        if success and width > 1 and height > 1:

            rotation = CAMERA_ROTATIONS[camera_direction]

            if rotation is not None:
                frame = cv2.rotate(frame, rotation)

            camera_frame = frame

            # The hands are followed with the camera OFF too, when the
            # projector shows only the boxes
            frame = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2RGB
            )

            hands = find_hands(frame)
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

    # The BIN reached is done again, without its old mark (from the last
    # cycle, or before going back)
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
    open_current_video()


def next_step(event=None):
    change_step(1)


def previous_step(event=None):
    change_step(-1)


# ==================================================
# CLOSE APPLICATION
# ==================================================

def close_application(event=None):

    if video_job is not None:
        root.after_cancel(video_job)

    if blink_job is not None:
        root.after_cancel(blink_job)

    if camera_job is not None:
        root.after_cancel(camera_job)

    if video_capture is not None:
        video_capture.release()

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

# ==================================================
# START APPLICATION
# ==================================================

draw_interface()

# Show the default layout first, then replace it with the most
# recently saved part if the database is available
build_boxes(default_layout())
show_step()
open_current_video()

connect_database()
refresh_parts()
load_part()

open_camera()
open_hand_recognizer()

video_job = root.after(30, update_video)
blink_job = root.after(500, blink)
camera_job = root.after(30, update_camera)

root.protocol(
    "WM_DELETE_WINDOW",
    close_application
)

root.mainloop()
