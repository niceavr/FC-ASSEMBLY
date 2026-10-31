
import tkinter as tk
from tkinter import ttk
import cv2
import os
import socket
from PIL import Image, ImageTk

from tkinter import messagebox

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
picture_aspect = 4 / 3  # width / height of the camera picture
camera_direction = DEFAULT_CAMERA_DIRECTION  # turned with the Settings
                                             # page's Camera View
camera_frame = None     # latest camera picture, turned as shown; read by
                        # the Settings page's camera view
camera_shown = True     # CAMERA ON/OFF button: picture behind the boxes
camera_button = None

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

    # Light up the boxes on the Camera Output: (fill, outline, outline
    # width, text color) of each box
    for box in workspace.boxes:

        if box.label == bin_name:
            # Selected BIN blinks
            if blink_on:
                look = (step_color, FOCUS_COLOR, 4,
                        text_color_for(step_color))
            else:
                look = (TABLE, FOCUS_COLOR, 4, FOCUS_COLOR)

        elif box.kind == "JIG" and box.label in step["jigs"]:
            # The BIN's jigs get their own fill color, or the BIN's color
            # when they have none, and a white border
            fill_color = box.color or step_color
            look = (fill_color, WHITE, 4, text_color_for(fill_color))

        else:
            # Remaining boxes stay dark
            look = (TABLE, BORDER, 2, INACTIVE_TEXT)

        workspace.set_look(box, look)


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

    # Camera picture with a draggable box for every BIN and J
    workspace = CameraWorkspace(canvas, on_moved=save_workspace_positions)

    workspace_window = canvas.create_window(
        (CAMERA_X1 + CAMERA_X2) / 2, (CAMERA_Y1 + CAMERA_Y2) / 2,
        anchor="center",
        window=workspace.canvas
    )
    fit_workspace()


def fit_workspace():
    # Largest workspace with the camera picture's shape that fits the
    # Camera Output, centered, like the Settings page's. The box positions
    # and sizes are parts of the workspace, so the boxes land on the same
    # spots of the picture and keep the same shape as on the Settings page
    area_w = CAMERA_X2 - CAMERA_X1 - 2 * CAMERA_BORDER
    area_h = CAMERA_Y2 - CAMERA_Y1 - 2 * CAMERA_BORDER
    width = min(area_w, area_h * picture_aspect)
    height = width / picture_aspect

    canvas.itemconfigure(
        workspace_window,
        width=max(int(width), 1),
        height=max(int(height), 1)
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


def show_camera_button():
    # The label says what clicking the button does
    if camera_shown:
        camera_button.config(text="CAMERA OFF", fg=BLACK, bg=FOCUS_COLOR)
    else:
        camera_button.config(text="CAMERA ON", fg=TEXT, bg=TABLE)


def update_camera():
    global camera_job
    global camera_frame
    global picture_aspect

    if camera_capture is not None:

        success, frame = camera_capture.read()
        width, height = workspace.size()

        # The workspace has no size until the window is shown
        if success and width > 1 and height > 1:

            rotation = CAMERA_ROTATIONS[camera_direction]

            if rotation is not None:
                frame = cv2.rotate(frame, rotation)

            camera_frame = frame

            # Turning the camera changes the picture's shape
            frame_h, frame_w = frame.shape[:2]
            aspect = frame_w / frame_h

            if abs(aspect - picture_aspect) > 0.01:
                picture_aspect = aspect
                fit_workspace()

            # With the camera OFF the picture is still read for the
            # Settings page's camera view, but not shown here
            if camera_shown:

                frame = cv2.cvtColor(
                    frame,
                    cv2.COLOR_BGR2RGB
                )

                # The workspace has the picture's shape, so this only
                # scales it, without stretching
                frame = cv2.resize(
                    frame,
                    (width, height)
                )

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

    # Navigate only through the BIN boxes of the selected part
    current_step = (current_step + direction) % len(bin_steps)

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
