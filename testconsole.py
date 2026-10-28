
import tkinter as tk
from tkinter import ttk
import cv2
import numpy as np
import os
from PIL import Image, ImageTk

from tkinter import messagebox

from projector_page import ProjectorPage
from settings_page import (
    BOX_GAP as SETTINGS_BOX_GAP,
    BOX_H as SETTINGS_BOX_H,
    BOX_RADIUS as SETTINGS_BOX_RADIUS,
    BOX_W as SETTINGS_BOX_W,
    DB_CONFIG_FILE,
    ROW_HEIGHT as SETTINGS_ROW_HEIGHT,
    ROW_PAD as SETTINGS_ROW_PAD,
    MySqlSettingsStore,
    SettingsPage,
    StorageError,
    rounded_rect_points,
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

# Each box is a dict: label, x, y, w, h, box_id, label_id
bin_boxes = []
jig_boxes = []

heading_id = None
instruction_id = None
video_status_id = None
video_image_id = None
active_message_id = None
store = None
part_var = None
part_combo = None
part_status = None
part_values = {}
settings_window = None
projector_window = None

video_capture = None
video_photo = None
video_job = None
blink_job = None

camera_capture = None
camera_photo = None
camera_image_id = None
camera_status_id = None
camera_job = None
camera_direction = "UP"
camera_buttons = {}
camera_frame = None     # latest camera picture, turned as shown

# Outlines of the bins and jigs found by the synchronizer:
# (x1, y1, x2, y2, BGR color) in camera picture pixels
sync_marks = []
sync_marks_job = None

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
# BOX DIMENSIONS
# ==================================================

# First row: full-size boxes
BOX_W = 112
BOX_H = 100

# Second row: half-size boxes
BOX2_W = BOX_W // 2
BOX2_H = BOX_H // 2

LEFT_X = 30
TOP_Y = 235

COL_GAP = 122
ROW_GAP = 220

# Area the boxes must stay inside
WORK_X1 = 20
WORK_X2 = 790
WORK_PAD = 10

# Rows copied from the Settings page
PART_ROW_GAP = 130          # top of the BIN row to top of the J row
SETTINGS_ROW_WIDTH = 1204   # Settings page row width at its default size

# ==================================================
# VIDEO DIMENSIONS
# ==================================================

# Step video: 20% of the original 655 x 400 box
VIDEO_X1 = 805
VIDEO_Y1 = 110
VIDEO_X2 = VIDEO_X1 + 131
VIDEO_Y2 = VIDEO_Y1 + 80

VIDEO_W = VIDEO_X2 - VIDEO_X1 - 6
VIDEO_H = VIDEO_Y2 - VIDEO_Y1 - 6

# ==================================================
# CAMERA DIMENSIONS
# ==================================================

CAMERA_INDEX = 0    # 0 = first camera connected to the PC

CAMERA_X1 = 805
CAMERA_Y1 = 225
CAMERA_X2 = 1460
CAMERA_Y2 = 625

CAMERA_W = CAMERA_X2 - CAMERA_X1 - 6
CAMERA_H = CAMERA_Y2 - CAMERA_Y1 - 6

# Which side of the camera picture is shown at the top
CAMERA_ROTATIONS = {
    "UP": None,
    "DOWN": cv2.ROTATE_180,
    "LEFT": cv2.ROTATE_90_COUNTERCLOCKWISE,
    "RIGHT": cv2.ROTATE_90_CLOCKWISE,
}

# ==================================================
# SYNCHRONIZER (CAMERA -> BOX POSITIONS)
# ==================================================

# Yellow bins in the camera picture (OpenCV HSV: hue 0-180)
YELLOW_LOW = (10, 170, 90)
YELLOW_HIGH = (40, 255, 255)

# Jigs are the dark objects below the bins
DARK_MAX_VALUE = 70

# Ignore anything narrower than this part of the picture width
MIN_OBJECT_WIDTH = 0.03

# How long the found bins and jigs stay outlined on the camera picture
SYNC_MARK_MS = 4000

SYNC_BIN_MARK = (248, 189, 56)    # FOCUS_COLOR in OpenCV's BGR order
SYNC_JIG_MARK = (118, 230, 0)     # "#00E676" in BGR

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
    # Six BIN and six J boxes, used when no part is loaded
    bins = []
    jigs = []

    for col in range(6):
        x = LEFT_X + col * COL_GAP

        bins.append(
            (f"BIN{col + 1}", x, TOP_Y, BOX_W, BOX_H, "")
        )

        # Center each small box under its BIN
        jigs.append(
            (
                f"J{col + 1}",
                x + (BOX_W - BOX2_W) // 2,
                TOP_Y + ROW_GAP,
                BOX2_W,
                BOX2_H,
                "",
            )
        )

    return {"bins": bins, "jigs": jigs, "rows": [], "radius": 0}


def layout_from_settings(settings):
    # Draw the rows exactly as they look on the Settings page: the whole
    # row is scaled down to the work area width, so every box keeps the
    # same position and size relative to its row.
    widest = max(b.x for b in settings.bins + settings.jigs)
    row_width = max(
        settings.row_width or SETTINGS_ROW_WIDTH,
        widest + SETTINGS_BOX_W + SETTINGS_ROW_PAD
    )

    left = WORK_X1 + WORK_PAD
    scale = (WORK_X2 - WORK_X1 - 2 * WORK_PAD) / row_width

    box_w = SETTINGS_BOX_W * scale
    box_h = SETTINGS_BOX_H * scale
    row_h = SETTINGS_ROW_HEIGHT * scale

    bin_row_y = TOP_Y
    jig_row_y = TOP_Y + PART_ROW_GAP

    def place(boxes, row_y):
        return [
            (b.label, left + b.x * scale, row_y + b.y * scale, box_w, box_h,
             b.color)
            for b in boxes
        ]

    rows = [
        (left, bin_row_y, left + row_width * scale, bin_row_y + row_h,
         "ROW 1 - BIN BOXES"),
        (left, jig_row_y, left + row_width * scale, jig_row_y + row_h,
         "ROW 2 - JIG BOXES"),
    ]

    return {
        "bins": place(settings.bins, bin_row_y),
        "jigs": place(settings.jigs, jig_row_y),
        "rows": rows,
        "radius": SETTINGS_BOX_RADIUS * scale,
    }


def draw_box(label, x, y, box_w, box_h, color, font_size, radius=0):
    # color is the fill color set on the Settings page ("" if none); it is
    # shown when the box is active
    if radius:
        # Rounded box, like on the Settings page
        box_id = canvas.create_polygon(
            *rounded_rect_points(x, y, x + box_w, y + box_h, radius),
            smooth=True,
            fill=TABLE,
            outline=BORDER,
            width=2,
            tags="box"
        )
    else:
        box_id = canvas.create_rectangle(
            x, y,
            x + box_w, y + box_h,
            fill=TABLE,
            outline=BORDER,
            width=2,
            tags="box"
        )

    label_id = canvas.create_text(
        x + box_w / 2,
        y + box_h / 2,
        text=label,
        fill=INACTIVE_TEXT,
        font=("Arial", font_size, "bold"),
        tags="box"
    )

    return {
        "label": label,
        "x": x, "y": y, "w": box_w, "h": box_h,
        "color": color,
        "box_id": box_id,
        "label_id": label_id,
    }


def build_boxes(layout):
    global bin_boxes, jig_boxes
    global current_step, blink_on, active_message_id

    canvas.delete("box")
    active_message_id = None

    # Row strips behind the boxes, with a caption above each
    for x1, y1, x2, y2, title in layout["rows"]:
        canvas.create_rectangle(
            x1, y1, x2, y2,
            fill="#0F172A",
            outline=BORDER,
            width=1,
            tags="box"
        )
        canvas.create_text(
            x1, y1 - 10,
            anchor="w",
            text=title,
            fill=INACTIVE_TEXT,
            font=("Arial", 9, "bold"),
            tags="box"
        )

    radius = layout["radius"]

    # Smaller boxes get smaller labels
    bin_boxes = [
        draw_box(*b, min(12, max(7, int(b[3] / 6))), radius)
        for b in layout["bins"]
    ]
    jig_boxes = [
        draw_box(*j, min(10, max(7, int(j[3] / 5))), radius)
        for j in layout["jigs"]
    ]

    current_step = 0
    blink_on = True


# ==================================================
# PART SELECTION (FROM THE SETTINGS DATABASE)
# ==================================================

def show_part_details(settings):
    part_values["model"].config(text=settings.model_number)
    part_values["customer"].config(text=settings.customer_name)
    part_values["vendor"].config(text=settings.vendor_code)
    part_values["bins"].config(text=str(settings.bin_count))
    part_values["jigs"].config(text=str(settings.jig_count))
    set_part_status("")


def set_part_status(text):
    # Warning line at the bottom of the card; hidden when empty
    part_status.config(text=text)

    if text:
        part_status.grid()
    else:
        part_status.grid_remove()


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
        on_saved=on_settings_saved
    )


def on_settings_saved(settings):
    # Show the saved layout here straight away
    refresh_parts()
    load_part(settings.part_number)


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

    # Card with a colored accent strip on the left
    card = tk.Frame(
        canvas,
        bg=TABLE,
        highlightthickness=1,
        highlightbackground=BORDER
    )

    tk.Frame(card, bg=FOCUS_COLOR, width=5).pack(side="left", fill="y")

    body = tk.Frame(card, bg=TABLE, padx=12, pady=10)
    body.pack(side="left", fill="both", expand=True)

    # (key, caption, characters wide, value color, column weight)
    fields = [
        ("part", "PART NUMBER", 12, TEXT, 3),
        ("model", "MODEL", 10, TEXT, 2),
        ("customer", "CUSTOMER", 14, TEXT, 3),
        ("vendor", "VENDOR", 9, TEXT, 2),
        ("bins", "BINS", 3, FOCUS_COLOR, 1),
        ("jigs", "JIGS", 3, "#00E676", 1),
    ]

    part_var = tk.StringVar()

    column = 0

    for index, (key, caption, chars, color, weight) in enumerate(fields):

        # Thin divider between fields
        if index > 0:
            tk.Frame(body, bg=BORDER, width=1).grid(
                row=0, column=column, sticky="ns", padx=10
            )
            column += 1

        body.columnconfigure(column, weight=weight)

        cell = tk.Frame(body, bg=TABLE)
        cell.grid(row=0, column=column, sticky="w")
        column += 1

        tk.Label(
            cell,
            text=caption,
            bg=TABLE,
            fg=INACTIVE_TEXT,
            font=("Arial", 9, "bold")
        ).pack(anchor="w")

        if key == "part":
            part_combo = ttk.Combobox(
                cell,
                textvariable=part_var,
                state="readonly",
                width=chars,
                font=("Arial", 11, "bold"),
                style="Part.TCombobox",
                postcommand=refresh_parts
            )
            part_combo.pack(anchor="w", pady=(3, 0))
            part_combo.bind("<<ComboboxSelected>>", on_part_selected)

        else:
            value = tk.Label(
                cell,
                text="-",
                width=chars,
                anchor="w",
                bg=TABLE,
                fg=color,
                font=("Arial", 12, "bold")
            )
            value.pack(anchor="w", pady=(3, 0))
            part_values[key] = value

    part_status = tk.Label(
        body,
        text="",
        anchor="w",
        bg=TABLE,
        fg="#FBBF24",
        font=("Arial", 10, "bold")
    )
    part_status.grid(
        row=1, column=0, columnspan=column, sticky="w", pady=(8, 0)
    )
    part_status.grid_remove()

    # Under the WORK STEPS heading, across the work area
    canvas.create_window(
        (WORK_X1 + WORK_X2) / 2, 128,
        anchor="n",
        width=WORK_X2 - WORK_X1 - 2 * WORK_PAD - 20,
        window=card
    )


# ==================================================
# DRAW INTERFACE
# ==================================================

def draw_interface():
    global heading_id
    global instruction_id
    global video_status_id

    canvas.create_text(
        750, 35,
        text="PROJECTOR WORK GUIDANCE",
        fill=TEXT,
        font=("Arial", 25, "bold")
    )

    # Opens the Settings form
    settings_button = tk.Button(
        canvas,
        text="⚙  SETTINGS",
        command=open_settings,
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

    canvas.create_window(
        1460, 38,
        anchor="e",
        window=settings_button
    )

    # Opens the projector power control (RS232)
    projector_button = tk.Button(
        canvas,
        text="PROJECTOR",
        command=open_projector,
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

    canvas.create_window(
        1300, 38,
        anchor="e",
        window=projector_button
    )

    # Work area
    canvas.create_rectangle(
        20, 80, 790, 625,
        fill=BG,
        outline=BORDER,
        width=2
    )

    canvas.create_text(
        405, 105,
        text="WORK STEPS",
        fill=TEXT,
        font=("Arial", 17, "bold")
    )

    create_part_panel()

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

    # Camera rectangle
    canvas.create_rectangle(
        CAMERA_X1, CAMERA_Y1,
        CAMERA_X2, CAMERA_Y2,
        fill=BLACK,
        outline=BORDER,
        width=3
    )

    canvas.create_text(
        (CAMERA_X1 + CAMERA_X2) / 2,
        CAMERA_Y1 - 18,
        text="CAMERA",
        fill=TEXT,
        font=("Arial", 17, "bold")
    )

    create_camera_buttons()

    # Moves the BIN and J boxes to where the camera sees them
    sync_button = tk.Button(
        canvas,
        text="⟳  SYNCHRONIZER",
        command=synchronize,
        bg=TABLE,
        fg=TEXT,
        activebackground=FOCUS_COLOR,
        activeforeground=BLACK,
        font=("Arial", 11, "bold"),
        relief="flat",
        padx=16,
        pady=6,
        cursor="hand2",
        takefocus=0,
        highlightthickness=1,
        highlightbackground=FOCUS_COLOR
    )

    canvas.create_window(
        (WORK_X1 + WORK_X2) / 2, 590,
        anchor="center",
        window=sync_button
    )

    # Current BIN heading
    heading_id = canvas.create_text(
        400, 635,
        text="",
        fill=WHITE,
        font=("Arial", 16, "bold"),
        width=740
    )

    # Instruction panel
    canvas.create_rectangle(
        20, 665, 1480, 750,
        fill=TABLE,
        outline=BORDER,
        width=2
    )

    instruction_id = canvas.create_text(
        750, 705,
        text="",
        fill=TEXT,
        font=("Arial", 18, "bold"),
        width=1400
    )

    canvas.create_text(
        750, 790,
        text=(
            "LEFT / RIGHT ARROW: Change BIN"
            "     SPACE: Next BIN"
            "     ESC: Exit"
        ),
        fill=INACTIVE_TEXT,
        font=("Arial", 12)
    )


# ==================================================
# UPDATE BIN AND J BOXES
# ==================================================

def show_step():
    global active_message_id

    if not bin_boxes:
        return

    bin_name = bin_boxes[current_step]["label"]
    description = step_description(current_step)

    # Fill color from the Settings page, or the standard color for this
    # step when none was set
    step_color = (
        bin_boxes[current_step]["color"]
        or ACTIVE_COLORS[current_step % len(ACTIVE_COLORS)]
    )

    canvas.itemconfigure(
        heading_id,
        text=f"{bin_name}: {description}"
    )

    canvas.itemconfigure(
        instruction_id,
        text=f"CURRENT INSTRUCTION: {description}"
    )

    # Remove previous ACTIVE message
    if active_message_id is not None:
        canvas.delete(active_message_id)
        active_message_id = None

    # --------------------------------------------------
    # FIRST ROW: BIN BOXES
    # --------------------------------------------------

    for i, box in enumerate(bin_boxes):

        active = (i == current_step)

        if active:
            if blink_on:
                fill_color = step_color
                text_color = text_color_for(step_color)
            else:
                fill_color = TABLE
                text_color = FOCUS_COLOR

            outline_color = FOCUS_COLOR
            outline_width = 4

        else:
            fill_color = TABLE
            text_color = INACTIVE_TEXT
            outline_color = BORDER
            outline_width = 2

        canvas.itemconfigure(
            box["box_id"],
            fill=fill_color,
            outline=outline_color,
            width=outline_width
        )

        canvas.itemconfigure(
            box["label_id"],
            fill=text_color
        )

        # ACTIVE message under the selected BIN
        if active and blink_on:
            active_message_id = canvas.create_text(
                box["x"] + box["w"] / 2,
                box["y"] + box["h"] + 22,
                text="ACTIVE",
                fill=step_color,
                font=("Arial", 12, "bold"),
                tags="box"
            )

    # --------------------------------------------------
    # SECOND ROW: J BOXES
    # --------------------------------------------------

    for i, box in enumerate(jig_boxes):

        # BIN1 pairs with J1, BIN2 with J2, and so on
        paired = (i == current_step)

        if paired:
            # Matching J box gets its own fill color, or the selected
            # BIN's color when it has none
            fill_color = box["color"] or step_color
            text_color = text_color_for(fill_color)

            # White border only around the matching J box
            outline_color = WHITE
            outline_width = 4

        else:
            # Remaining J boxes stay dark
            fill_color = TABLE
            text_color = INACTIVE_TEXT
            outline_color = BORDER
            outline_width = 2

        canvas.itemconfigure(
            box["box_id"],
            fill=fill_color,
            outline=outline_color,
            width=outline_width
        )

        canvas.itemconfigure(
            box["label_id"],
            fill=text_color
        )


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

def open_camera():
    global camera_capture
    global camera_status_id

    # CAP_DSHOW opens USB cameras quickly on Windows
    capture = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)

    if capture.isOpened():
        camera_capture = capture
        message = "Starting camera..."
    else:
        capture.release()
        message = f"Camera {CAMERA_INDEX} not found or cannot open"

    camera_status_id = canvas.create_text(
        (CAMERA_X1 + CAMERA_X2) / 2,
        (CAMERA_Y1 + CAMERA_Y2) / 2,
        text=message,
        fill=TEXT,
        font=("Arial", 14),
        width=CAMERA_W - 40
    )


def set_camera_direction(direction):
    global camera_direction

    camera_direction = direction
    show_camera_buttons()

    # Give the keyboard back to the window so SPACE changes BINs
    # instead of pressing the button again
    root.focus_set()


def show_camera_buttons():
    # Highlight the button of the direction in use
    for direction, button in camera_buttons.items():
        if direction == camera_direction:
            button.config(bg=FOCUS_COLOR, fg=BLACK)
        else:
            button.config(bg=TABLE, fg=TEXT)


def create_camera_buttons():
    # Beside the step video, above the camera box
    area_x1 = VIDEO_X2 + 15
    area_x2 = CAMERA_X2

    canvas.create_text(
        (area_x1 + area_x2) / 2, VIDEO_Y1 + 12,
        text="CAMERA VIEW",
        fill=INACTIVE_TEXT,
        font=("Arial", 10, "bold")
    )

    frame = tk.Frame(canvas, bg=BG)

    arrows = {"UP": "▲", "DOWN": "▼", "LEFT": "◀", "RIGHT": "▶"}

    for direction in CAMERA_ROTATIONS:
        button = tk.Button(
            frame,
            text=f"{arrows[direction]}  {direction}",
            command=lambda d=direction: set_camera_direction(d),
            bg=TABLE,
            fg=TEXT,
            activebackground=FOCUS_COLOR,
            activeforeground=BLACK,
            font=("Arial", 11, "bold"),
            relief="flat",
            width=9,
            pady=6,
            cursor="hand2",
            takefocus=0,
            highlightthickness=1,
            highlightbackground=FOCUS_COLOR
        )
        button.pack(side="left", padx=5)
        camera_buttons[direction] = button

    canvas.create_window(
        (area_x1 + area_x2) / 2, VIDEO_Y1 + 50,
        anchor="center",
        window=frame
    )

    show_camera_buttons()


def update_camera():
    global camera_photo
    global camera_image_id
    global camera_status_id
    global camera_job
    global camera_frame

    if camera_capture is not None:

        success, frame = camera_capture.read()

        if success:

            rotation = CAMERA_ROTATIONS[camera_direction]

            if rotation is not None:
                frame = cv2.rotate(frame, rotation)

            # Kept without the outlines for the synchronizer
            camera_frame = frame

            if sync_marks:
                frame = frame.copy()

                for x1, y1, x2, y2, color in sync_marks:
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)

            frame = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2RGB
            )

            # Stretch the picture to fill the whole camera box
            frame = cv2.resize(
                frame,
                (CAMERA_W, CAMERA_H)
            )

            image = Image.fromarray(frame)
            camera_photo = ImageTk.PhotoImage(image)

            if camera_status_id is not None:
                canvas.delete(camera_status_id)
                camera_status_id = None

            if camera_image_id is None:
                camera_image_id = canvas.create_image(
                    (CAMERA_X1 + CAMERA_X2) / 2,
                    (CAMERA_Y1 + CAMERA_Y2) / 2,
                    image=camera_photo
                )
            else:
                canvas.itemconfigure(
                    camera_image_id,
                    image=camera_photo
                )

    camera_job = root.after(30, update_camera)


# ==================================================
# SYNCHRONIZER
# ==================================================

def find_columns(mask, min_width):
    # Left-to-right (x1, x2) runs of columns where the mask covers at
    # least 40% of what its fullest column covers
    counts = (mask > 0).sum(axis=0)

    if counts.max() == 0:
        return []

    covered = counts >= 0.4 * counts.max()

    runs = []
    start = None

    for x, on in enumerate(covered.tolist() + [False]):
        if on and start is None:
            start = x
        elif not on and start is not None:
            if x - start >= min_width:
                runs.append((start, x))
            start = None

    return runs


def detect_bins_and_jigs(frame):
    # Returns the yellow bins and the dark jigs below them, each as
    # left-to-right (x1, y1, x2, y2) rectangles in picture pixels
    width = frame.shape[1]
    min_width = int(width * MIN_OBJECT_WIDTH)

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    kernel = np.ones((5, 5), np.uint8)

    yellow = cv2.inRange(hsv, YELLOW_LOW, YELLOW_HIGH)
    yellow = cv2.morphologyEx(yellow, cv2.MORPH_OPEN, kernel)

    # Rows that are mostly yellow make up the bin strip
    rows = np.nonzero((yellow > 0).mean(axis=1) > 0.2)[0]

    if len(rows) == 0:
        return [], []

    bin_top, bin_bottom = int(rows.min()), int(rows.max())

    bins = [
        (x1, bin_top, x2, bin_bottom)
        for x1, x2 in find_columns(yellow[bin_top:bin_bottom + 1], min_width)
    ]

    # Jigs: dark objects anywhere below the bin strip
    dark = cv2.inRange(hsv, (0, 0, 0), (180, 255, DARK_MAX_VALUE))
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, kernel)
    dark[:bin_bottom + 1] = 0

    rows = np.nonzero((dark > 0).any(axis=1))[0]

    if len(rows) == 0:
        return bins, []

    jig_top, jig_bottom = int(rows.min()), int(rows.max())

    jigs = [
        (x1, jig_top, x2, jig_bottom)
        for x1, x2 in find_columns(dark, min_width)
    ]

    return bins, jigs


def drop_cut_off(found, count, width):
    # Bins cut off at the picture edge are only partly in view; leave
    # them out first when the camera sees more than the part has
    found = list(found)

    while len(found) > count:
        at_edge = [r for r in found if r[0] <= 0 or r[2] >= width]

        if not at_edge:
            break

        found.remove(min(at_edge, key=lambda r: r[2] - r[0]))

    return found


def row_positions(found, width, row_width):
    # Settings page x for each box, so its center sits at the same part
    # of the row as the object's center in the camera picture
    low = SETTINGS_ROW_PAD
    high = row_width - SETTINGS_ROW_PAD - SETTINGS_BOX_W
    step = SETTINGS_BOX_W + SETTINGS_BOX_GAP

    xs = [
        round((x1 + x2) / 2 / width * row_width - SETTINGS_BOX_W / 2)
        for x1, _, x2, _ in found
    ]

    # Keep every box inside the row with the Settings page's minimum gap
    for i in range(len(xs)):
        xs[i] = max(xs[i], low if i == 0 else xs[i - 1] + step)

    for i in reversed(range(len(xs))):
        xs[i] = min(xs[i], high if i == len(xs) - 1 else xs[i + 1] - step)

    return xs


def clear_sync_marks():
    global sync_marks, sync_marks_job

    sync_marks = []
    sync_marks_job = None


def show_sync_marks(bins, jigs):
    global sync_marks, sync_marks_job

    if sync_marks_job is not None:
        root.after_cancel(sync_marks_job)

    sync_marks = (
        [(*r, SYNC_BIN_MARK) for r in bins]
        + [(*r, SYNC_JIG_MARK) for r in jigs]
    )
    sync_marks_job = root.after(SYNC_MARK_MS, clear_sync_marks)


def synchronize():
    # Move the BIN and J boxes of the selected part to where the camera
    # sees the yellow bins and the jigs, then save the new positions
    root.focus_set()

    if store is None:
        messagebox.showerror(
            "Synchronizer",
            "The database is not available, so positions cannot be saved.",
            parent=root
        )
        return

    if not part_var.get():
        messagebox.showerror(
            "Synchronizer", "Select a part first.", parent=root
        )
        return

    if camera_frame is None:
        messagebox.showerror(
            "Synchronizer", "No picture from the camera yet.", parent=root
        )
        return

    frame = camera_frame
    width = frame.shape[1]

    try:
        settings = store.load(part_var.get())
    except StorageError as e:
        messagebox.showerror("Synchronizer", str(e), parent=root)
        return

    if settings is None:
        messagebox.showerror(
            "Synchronizer",
            f"Part {part_var.get()} is not in the database.",
            parent=root
        )
        return

    bins, jigs = detect_bins_and_jigs(frame)
    bins = drop_cut_off(bins, len(settings.bins), width)
    jigs = drop_cut_off(jigs, len(settings.jigs), width)

    show_sync_marks(bins, jigs)

    problems = []

    if len(bins) != len(settings.bins):
        problems.append(
            f"Camera sees {len(bins)} yellow bins, "
            f"part {settings.part_number} has {len(settings.bins)} BINs."
        )

    if len(jigs) != len(settings.jigs):
        problems.append(
            f"Camera sees {len(jigs)} jigs, "
            f"part {settings.part_number} has {len(settings.jigs)} JIGs."
        )

    if problems:
        messagebox.showerror(
            "Synchronizer",
            "\n".join(problems)
            + "\n\nNothing was changed. Check the camera view and try again.",
            parent=root
        )
        return

    row_width = settings.row_width or SETTINGS_ROW_WIDTH
    settings.row_width = row_width

    # BIN1 goes to the leftmost bin in the picture, BIN2 to the next, ...
    for boxes, found in ((settings.bins, bins), (settings.jigs, jigs)):
        for box, x in zip(boxes, row_positions(found, width, row_width)):
            box.x = x

    try:
        store.save(settings)
    except StorageError as e:
        messagebox.showerror("Synchronizer", str(e), parent=root)
        return

    load_part(settings.part_number)

    messagebox.showinfo(
        "Synchronizer",
        f"Moved {len(bins)} BINs and {len(jigs)} JIGs to match the camera "
        f"and saved them for part {settings.part_number}.",
        parent=root
    )


# ==================================================
# NAVIGATION: FIRST ROW ONLY
# ==================================================

def change_step(direction):
    global current_step, blink_on

    if not bin_boxes:
        return

    # Navigate only through the BIN boxes of the selected part
    current_step = (current_step + direction) % len(bin_boxes)

    blink_on = True

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

    if sync_marks_job is not None:
        root.after_cancel(sync_marks_job)

    if video_capture is not None:
        video_capture.release()

    if camera_capture is not None:
        camera_capture.release()

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

video_job = root.after(30, update_video)
blink_job = root.after(500, blink)
camera_job = root.after(30, update_camera)

root.protocol(
    "WM_DELETE_WINDOW",
    close_application
)

root.mainloop()
