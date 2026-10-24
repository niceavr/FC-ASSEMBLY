
import tkinter as tk
import cv2
import os
from PIL import Image, ImageTk

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

box_ids = []
label_ids = []
box_positions = []

heading_id = None
instruction_id = None
video_status_id = None
video_image_id = None
active_message_id = None

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
TOP_Y = 155

COL_GAP = 122
ROW_GAP = 220

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

    # Create two rows with six boxes each
    for row in range(2):
        for col in range(6):

            if row == 0:
                # First row: BIN1 to BIN6
                label = f"BIN{col + 1}"

                box_w = BOX_W
                box_h = BOX_H

                x = LEFT_X + col * COL_GAP
                y = TOP_Y

            else:
                # Second row: J1 to J6
                label = f"J{col + 1}"

                box_w = BOX2_W
                box_h = BOX2_H

                # Center each small box under its BIN
                x = (
                    LEFT_X
                    + col * COL_GAP
                    + (BOX_W - BOX2_W) // 2
                )
                y = TOP_Y + ROW_GAP

            box_positions.append(
                (x, y, box_w, box_h)
            )

            box_id = canvas.create_rectangle(
                x, y,
                x + box_w, y + box_h,
                fill=TABLE,
                outline=BORDER,
                width=2
            )

            label_id = canvas.create_text(
                x + box_w / 2,
                y + box_h / 2,
                text=label,
                fill=INACTIVE_TEXT,
                font=(
                    "Arial",
                    12 if row == 0 else 10,
                    "bold"
                )
            )

            box_ids.append(box_id)
            label_ids.append(label_id)

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

    bin_name, description = steps[current_step]

    canvas.itemconfigure(
        heading_id,
        text=f"{bin_name}: {description}"
    )

    canvas.itemconfigure(
        instruction_id,
        text=f"CURRENT INSTRUCTION: {description}"
    )

    # Matching J box is in the same column
    paired_index = current_step + 6

    # Remove previous ACTIVE message
    if active_message_id is not None:
        canvas.delete(active_message_id)
        active_message_id = None

    # --------------------------------------------------
    # FIRST ROW: BIN1 TO BIN6
    # --------------------------------------------------

    for i in range(6):

        active = (i == current_step)

        if active:
            if blink_on:
                fill_color = ACTIVE_COLORS[i]
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
            box_ids[i],
            fill=fill_color,
            outline=outline_color,
            width=outline_width
        )

        canvas.itemconfigure(
            label_ids[i],
            fill=text_color
        )

        # ACTIVE message under the selected BIN
        if active and blink_on:
            x, y, box_w, box_h = box_positions[i]

            active_message_id = canvas.create_text(
                x + box_w / 2,
                y + box_h + 22,
                text="ACTIVE",
                fill=ACTIVE_COLORS[i],
                font=("Arial", 12, "bold")
            )

    # --------------------------------------------------
    # SECOND ROW: J1 TO J6
    # --------------------------------------------------

    for col in range(6):

        i = col + 6
        paired = (i == paired_index)

        if paired:
            # Matching J box gets the selected BIN's color
            fill_color = ACTIVE_COLORS[current_step]
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
            box_ids[i],
            fill=fill_color,
            outline=outline_color,
            width=outline_width
        )

        canvas.itemconfigure(
            label_ids[i],
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

    filename = video_files[current_step]

    folder = os.path.dirname(
        os.path.abspath(__file__)
    )

    video_path = os.path.join(folder, filename)

    if os.path.isfile(video_path):
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

    # Navigate only through BIN1 to BIN6
    current_step = (current_step + direction) % 6

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
show_step()
open_current_video()

video_job = root.after(30, update_video)
blink_job = root.after(500, blink)

root.protocol(
    "WM_DELETE_WINDOW",
    close_application
)

root.mainloop()
