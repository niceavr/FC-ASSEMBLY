
import tkinter as tk
from tkinter import ttk
import cv2
import os
from PIL import Image, ImageTk

from settings_page import (
    BOX_W as SETTINGS_BOX_W,
    DB_CONFIG_FILE,
    MySqlSettingsStore,
    StorageError,
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

video_capture = None
video_photo = None
video_job = None
blink_job = None

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

# ==================================================
# VIDEO DIMENSIONS
# ==================================================

VIDEO_X1 = 805
VIDEO_Y1 = 170
VIDEO_X2 = 1460
VIDEO_Y2 = 570

VIDEO_W = VIDEO_X2 - VIDEO_X1 - 12
VIDEO_H = VIDEO_Y2 - VIDEO_Y1 - 45

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
            (f"BIN{col + 1}", x, TOP_Y, BOX_W, BOX_H)
        )

        # Center each small box under its BIN
        jigs.append(
            (
                f"J{col + 1}",
                x + (BOX_W - BOX2_W) // 2,
                TOP_Y + ROW_GAP,
                BOX2_W,
                BOX2_H,
            )
        )

    return bins, jigs


def layout_from_settings(settings):
    # Map the box positions saved on the Settings page onto the work area,
    # keeping their left-to-right arrangement. Both rows use the same scale
    # so a J box saved under a BIN is still drawn under it.
    half = SETTINGS_BOX_W / 2

    bin_centers = [(b.label, b.x + half) for b in settings.bins]
    jig_centers = [(j.label, j.x + half) for j in settings.jigs]

    all_centers = [c for _, c in bin_centers + jig_centers]
    lowest = min(all_centers)
    highest = max(all_centers)

    area_lo = WORK_X1 + WORK_PAD + BOX_W / 2
    area_hi = WORK_X2 - WORK_PAD - BOX_W / 2

    span = highest - lowest
    scale = min(1, (area_hi - area_lo) / span) if span else 1

    # Center the whole group in the work area
    offset = (area_lo + area_hi) / 2 - (lowest + highest) / 2 * scale

    def place(center):
        return offset + center * scale

    def smallest_gap(centers):
        xs = sorted(place(c) for _, c in centers)
        gaps = [b - a for a, b in zip(xs, xs[1:])]
        return min(gaps) if gaps else float("inf")

    # Shrink boxes when they are close together so they never overlap
    bin_w = max(24, min(BOX_W, smallest_gap(bin_centers) - 10))
    bin_h = BOX_H * bin_w / BOX_W

    jig_w = max(16, min(bin_w / 2, smallest_gap(jig_centers) - 6))
    jig_h = BOX2_H * jig_w / BOX2_W

    bins = [
        (label, place(c) - bin_w / 2, TOP_Y, bin_w, bin_h)
        for label, c in bin_centers
    ]
    jigs = [
        (label, place(c) - jig_w / 2, TOP_Y + ROW_GAP, jig_w, jig_h)
        for label, c in jig_centers
    ]

    return bins, jigs


def draw_box(label, x, y, box_w, box_h, font_size):
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
        "box_id": box_id,
        "label_id": label_id,
    }


def build_boxes(bins, jigs):
    global bin_boxes, jig_boxes
    global current_step, blink_on, active_message_id

    canvas.delete("box")
    active_message_id = None

    # Smaller boxes get smaller labels
    bin_boxes = [
        draw_box(*b, min(12, max(7, int(b[3] / 6))))
        for b in bins
    ]
    jig_boxes = [
        draw_box(*j, min(10, max(7, int(j[3] / 5))))
        for j in jigs
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

    build_boxes(*layout_from_settings(settings))
    show_step()
    open_current_video()


def on_part_selected(event=None):
    load_part(part_var.get())

    # Give the keyboard back to the window so the arrow keys
    # and SPACE change BINs again
    root.focus_set()


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
        (VIDEO_X1 + VIDEO_X2) / 2,
        115,
        text="STEP VIDEO",
        fill=TEXT,
        font=("Arial", 17, "bold")
    )

    video_status_id = canvas.create_text(
        (VIDEO_X1 + VIDEO_X2) / 2,
        (VIDEO_Y1 + VIDEO_Y2) / 2,
        text="Loading video...",
        fill=TEXT,
        font=("Arial", 14)
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
    step_color = ACTIVE_COLORS[current_step % len(ACTIVE_COLORS)]

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
                text_color = BLACK
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
            # Matching J box gets the selected BIN's color
            fill_color = step_color
            text_color = BLACK

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
            text=f"Video not found or cannot open:\n{filename}",
            fill=TEXT,
            font=("Arial", 14),
            width=VIDEO_W - 40
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

    if video_capture is not None:
        video_capture.release()

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
build_boxes(*default_layout())
show_step()
open_current_video()

connect_database()
refresh_parts()
load_part()

video_job = root.after(30, update_video)
blink_job = root.after(500, blink)

root.protocol(
    "WM_DELETE_WINDOW",
    close_application
)

root.mainloop()
