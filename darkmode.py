
import tkinter as tk

# Work steps and positions
steps = [
    ("STEP 1: PICK SPANNER", "Pick the required spanner", 150, 170),
    ("STEP 2: ASSEMBLE CABLE", "Place cable in assembly area", 430, 170),
    ("STEP 3: INSPECT", "Inspect and confirm OK", 700, 170),
]

current_step = 0
blink_on = True

# Dark mode colors
BG = "#121826"
TABLE = "#1E293B"
BORDER = "#64748B"
TEXT = "#F8FAFC"
INACTIVE_TEXT = "#94A3B8"

# Active colors for Steps 1, 2, and 3
ACTIVE_COLORS = [
    "#FFFFFF",  # Step 1: White
    "#FF3030",  # Step 2: Red
    "#00E676",  # Step 3: Green
]

root = tk.Tk()
root.title("Projector Work Guidance - Dark Mode")
root.geometry("1280x720")
root.configure(bg=BG)

canvas = tk.Canvas(
    root,
    bg=BG,
    highlightthickness=0
)
canvas.pack(fill="both", expand=True)


def show_step():
    canvas.delete("all")

    title, instruction, _, _ = steps[current_step]

    # Heading
    canvas.create_text(
        640, 45,
        text=title,
        font=("Arial", 28, "bold"),
        fill="#38BDF8"
    )

    # Simulated worktable
    canvas.create_rectangle(
        40, 100, 1240, 590,
        fill=TABLE,
        outline="#475569",
        width=3
    )

    # Draw all three work boxes
    for i, (_, label, ax, ay) in enumerate(steps):
        active = (i == current_step)

        if active and blink_on:
            # Active box shows its assigned color
            box_fill = ACTIVE_COLORS[i]
            box_outline = ACTIVE_COLORS[i]
            box_width = 6
            label_color = ACTIVE_COLORS[i]

            # Dark text on white/green, white text on red
            active_text_color = (
                "#FFFFFF" if i == 1 else "#111827"
            )

        else:
            # Inactive boxes remain dark mode
            box_fill = TABLE
            box_outline = BORDER
            box_width = 2
            label_color = INACTIVE_TEXT
            active_text_color = TEXT

        canvas.create_rectangle(
            ax - 75, ay - 45,
            ax + 75, ay + 45,
            fill=box_fill,
            outline=box_outline,
            width=box_width
        )

        # ACTIVE text appears during the bright phase
        if active and blink_on:
            canvas.create_text(
                ax, ay,
                text="ACTIVE",
                font=("Arial", 16, "bold"),
                fill=active_text_color
            )

        # Work-area label
        canvas.create_text(
            ax, ay + 65,
            text=label,
            font=("Arial", 13, "bold"),
            fill=label_color
        )

    # Current instruction panel
    canvas.create_rectangle(
        190, 465, 1090, 555,
        fill="#0B1220",
        outline="#475569",
        width=2
    )

    canvas.create_text(
        640, 485,
        text="CURRENT INSTRUCTION",
        font=("Arial", 14, "bold"),
        fill="#38BDF8"
    )

    canvas.create_text(
        640, 525,
        text=instruction,
        font=("Arial", 22, "bold"),
        fill=TEXT
    )

    # Keyboard instructions
    canvas.create_text(
        640, 625,
        text="SPACE / RIGHT = NEXT STEP",
        font=("Arial", 15, "bold"),
        fill="#38BDF8"
    )

    canvas.create_text(
        640, 660,
        text="LEFT = PREVIOUS STEP  |  F11 = FULLSCREEN  |  ESC = EXIT",
        font=("Arial", 12),
        fill="#CBD5E1"
    )


def blink():
    global blink_on

    blink_on = not blink_on
    show_step()

    # Toggle blink every 500 milliseconds
    root.after(500, blink)


def next_step(event=None):
    global current_step, blink_on

    current_step = (current_step + 1) % len(steps)
    blink_on = True
    show_step()


def previous_step(event=None):
    global current_step, blink_on

    current_step = (current_step - 1) % len(steps)
    blink_on = True
    show_step()


def toggle_fullscreen(event=None):
    root.attributes(
        "-fullscreen",
        not root.attributes("-fullscreen")
    )


def exit_fullscreen(event=None):
    root.attributes("-fullscreen", False)


# Keyboard bindings
root.bind("<space>", next_step)
root.bind("<Right>", next_step)
root.bind("<Left>", previous_step)
root.bind("<F11>", toggle_fullscreen)
root.bind("<Escape>", exit_fullscreen)

# Start application
show_step()
root.after(500, blink)

root.mainloop()
