import tkinter as tk

# Demo work areas on a simulated worktable
steps = [
    ("STEP 1: PICK SPANNER", "Pick the required spanner", 150, 170),
    ("STEP 2: ASSEMBLE CABLE", "Place cable in assembly area", 430, 170),
    ("STEP 3: INSPECT", "Inspect and confirm OK", 700, 170),
]

current_step = 0

root = tk.Tk()
root.title("Projector Work Guidance Demo")
root.configure(bg="white")
root.geometry("1280x720")

canvas = tk.Canvas(root, bg="white", highlightthickness=0)
canvas.pack(fill="both", expand=True)


def show_step():
    canvas.delete("all")
    title, instruction, x, y = steps[current_step]

    canvas.create_text(
        640, 45, text=title,
        font=("Arial", 28, "bold"), fill="black"
    )

    # Simulated worktable
    canvas.create_rectangle(
        40, 100, 1240, 590,
        outline="#888888", width=3
    )

    # Work areas
    for i, (_, label, ax, ay) in enumerate(steps):
        selected = i == current_step
        color = "#00AA44" if selected else "#AAAAAA"
        canvas.create_rectangle(
            ax - 75, ay - 45, ax + 75, ay + 45,
            outline=color, width=5 if selected else 2
        )
        canvas.create_text(
            ax, ay + 65, text=label,
            font=("Arial", 14), fill=color
        )

    canvas.create_text(
        640, 530, text=instruction,
        font=("Arial", 24, "bold"), fill="black"
    )

    canvas.create_text(
        640, 630,
        text="SPACE / RIGHT = NEXT     LEFT = PREVIOUS",
        font=("Arial", 16), fill="black"
    )


def next_step(event=None):
    global current_step
    current_step = (current_step + 1) % len(steps)
    show_step()


def previous_step(event=None):
    global current_step
    current_step = (current_step - 1) % len(steps)
    show_step()


root.bind("<space>", next_step)
root.bind("<Right>", next_step)
root.bind("<Left>", previous_step)
root.bind("<F11>", lambda e: root.attributes(
    "-fullscreen", not root.attributes("-fullscreen")
))
root.bind("<Escape>", lambda e: root.attributes("-fullscreen", False))

show_step()
root.mainloop()
