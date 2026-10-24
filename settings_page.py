"""
Settings Page - Dynamic Bin and Jig Box Configuration

Enter part details, choose how many Bin and Jig boxes are needed, generate
the layout, then select and drag boxes horizontally within their own row.
The details and box positions are saved to a MySQL database and restored the
next time the application opens. Connection details are read from
db_config.ini (see db_config.example.ini).
"""

import configparser
import os
import re
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import messagebox, ttk

import pymysql

# ==================================================
# CONSTANTS
# ==================================================

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_CONFIG_FILE = os.path.join(APP_DIR, "db_config.ini")

BG = "#121826"
PANEL = "#1E293B"
ROW_BG = "#0F172A"
BORDER = "#475569"
TEXT = "#F8FAFC"
MUTED = "#94A3B8"
ACCENT = "#38BDF8"
ERROR = "#F87171"

BIN_FILL = "#1E3A8A"
BIN_OUTLINE = "#60A5FA"
JIG_FILL = "#78350F"
JIG_OUTLINE = "#FBBF24"
SELECTED_FILL = "#065F46"
SELECTED_OUTLINE = "#00E676"

TITLE_FONT = ("Segoe UI", 22, "bold")
LABEL_FONT = ("Segoe UI", 10)
INPUT_FONT = ("Segoe UI", 11)
BUTTON_FONT = ("Segoe UI", 10, "bold")
BOX_FONT = ("Segoe UI", 14, "bold")

BOX_W = 80
BOX_H = 60
BOX_RADIUS = 12
BOX_GAP = 12          # minimum space between two boxes
MAX_SPACING = 40      # space between boxes in the default layout
ROW_PAD = 12          # space between the boxes and the row edge
ROW_HEIGHT = BOX_H + 2 * ROW_PAD
DRAG_THRESHOLD = 4    # pixels the mouse must move before a click becomes a drag

COUNT_OPTIONS = [str(n) for n in range(1, 13)]

TEXT_FIELDS = [
    ("part_number", "Part Number"),
    ("model_number", "Model Number"),
    ("customer_name", "Customer Name"),
    ("vendor_code", "Vendor Code"),
]
COUNT_FIELDS = [
    ("bin_count", "Number of Bins"),
    ("jig_count", "Number of Jig Boxes"),
]


# ==================================================
# DATA MODEL AND STORAGE
# ==================================================

@dataclass
class BoxConfig:
    label: str
    x: int
    y: int


@dataclass
class Settings:
    part_number: str = ""
    model_number: str = ""
    customer_name: str = ""
    vendor_code: str = ""
    bin_count: int = 0
    jig_count: int = 0
    bins: list = field(default_factory=list)
    jigs: list = field(default_factory=list)


class StorageError(Exception):
    """Raised when settings cannot be loaded or saved."""


SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS part_settings (
        settings_id   INT NOT NULL AUTO_INCREMENT,
        part_number   VARCHAR(100) NOT NULL,
        model_number  VARCHAR(100) NOT NULL,
        customer_name VARCHAR(150) NOT NULL,
        vendor_code   VARCHAR(100) NOT NULL,
        bin_count     TINYINT UNSIGNED NOT NULL,
        jig_count     TINYINT UNSIGNED NOT NULL,
        updated_at    TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        CONSTRAINT pk_part_settings PRIMARY KEY (settings_id),
        CONSTRAINT uq_part_number UNIQUE (part_number)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS box_positions (
        settings_id INT NOT NULL,
        box_id      INT NOT NULL AUTO_INCREMENT,
        box_type    ENUM('BIN', 'JIG') NOT NULL,
        label       VARCHAR(20) NOT NULL,
        x           INT NOT NULL,
        y           INT NOT NULL,
        CONSTRAINT pk_box_positions PRIMARY KEY (box_id),
        CONSTRAINT uq_box UNIQUE (settings_id, box_type, label),
        CONSTRAINT fk_box_positions_settings FOREIGN KEY (settings_id)
            REFERENCES part_settings (settings_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
]

DEFAULT_DB_CONFIG = """\
[mysql]
host = localhost
port = 3306
user = root
password =
database = fc_assembly
"""


class MySqlSettingsStore:
    """Saves settings in MySQL. Each Part Number is stored as its own row in
    part_settings, with its box positions in box_positions. load() returns
    the most recently saved part. The database and tables are created
    automatically the first time they are needed."""

    def __init__(self, config_file):
        self.config = self._read_config(config_file)
        self.location = (
            f"MySQL database '{self.config['database']}' "
            f"on {self.config['host']}"
        )
        self._schema_ready = False

    @staticmethod
    def _read_config(config_file):
        if not os.path.exists(config_file):
            with open(config_file, "w", encoding="utf-8") as f:
                f.write(DEFAULT_DB_CONFIG)
            raise StorageError(
                f"Created {config_file}.\n"
                "Enter your MySQL user and password in it, then restart."
            )
        parser = configparser.ConfigParser()
        parser.read(config_file, encoding="utf-8")
        if "mysql" not in parser:
            raise StorageError(f"{config_file} has no [mysql] section.")
        section = parser["mysql"]
        database = section.get("database", "fc_assembly")
        # The name is put directly into CREATE DATABASE, so only allow
        # plain identifiers.
        if not re.fullmatch(r"\w+", database):
            raise StorageError(f"Invalid database name: {database!r}")
        return {
            "host": section.get("host", "localhost"),
            "port": section.getint("port", 3306),
            "user": section.get("user", "root"),
            "password": section.get("password", ""),
            "database": database,
        }

    def _connect(self, use_database=True):
        try:
            return pymysql.connect(
                host=self.config["host"],
                port=self.config["port"],
                user=self.config["user"],
                password=self.config["password"],
                database=self.config["database"] if use_database else None,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=5,
            )
        except pymysql.MySQLError as e:
            raise StorageError(f"Could not connect to MySQL:\n{e}") from e

    def _ensure_schema(self):
        if self._schema_ready:
            return
        conn = self._connect(use_database=False)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{self.config['database']}` "
                    "CHARACTER SET utf8mb4"
                )
                cur.execute(f"USE `{self.config['database']}`")
                for statement in SCHEMA:
                    cur.execute(statement)
            conn.commit()
        except pymysql.MySQLError as e:
            raise StorageError(f"Could not create the database:\n{e}") from e
        finally:
            conn.close()
        self._schema_ready = True

    def load(self):
        """Return the most recently saved Settings, or None if there are none."""
        self._ensure_schema()
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM part_settings "
                    "ORDER BY updated_at DESC, settings_id DESC LIMIT 1"
                )
                row = cur.fetchone()
                if row is None:
                    return None
                cur.execute(
                    "SELECT box_type, label, x, y FROM box_positions "
                    "WHERE settings_id = %s ORDER BY box_id",
                    (row["settings_id"],),
                )
                boxes = cur.fetchall()
        except pymysql.MySQLError as e:
            raise StorageError(f"Could not load settings:\n{e}") from e
        finally:
            conn.close()

        def boxes_of(box_type):
            return [
                BoxConfig(b["label"], b["x"], b["y"])
                for b in boxes
                if b["box_type"] == box_type
            ]

        return Settings(
            part_number=row["part_number"],
            model_number=row["model_number"],
            customer_name=row["customer_name"],
            vendor_code=row["vendor_code"],
            bin_count=row["bin_count"],
            jig_count=row["jig_count"],
            bins=boxes_of("BIN"),
            jigs=boxes_of("JIG"),
        )

    def save(self, settings):
        """Insert or update the part and its box positions in one transaction,
        so a failed save never leaves half a layout behind.

        Existing rows are updated in place rather than deleted and inserted
        again, so IDs stay the same and new IDs follow on without gaps."""
        self._ensure_schema()
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                settings_id = self._save_part(cur, settings)
                self._save_boxes(cur, settings_id, settings)
            conn.commit()
        except pymysql.MySQLError as e:
            conn.rollback()
            raise StorageError(f"Could not save settings:\n{e}") from e
        finally:
            conn.close()

    @staticmethod
    def _save_part(cur, settings):
        """Update the part's row, or insert it if it is new. Returns its
        settings_id."""
        values = (
            settings.model_number, settings.customer_name,
            settings.vendor_code, settings.bin_count, settings.jig_count,
        )
        cur.execute(
            "SELECT settings_id FROM part_settings "
            "WHERE part_number = %s FOR UPDATE",
            (settings.part_number,),
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE part_settings SET model_number = %s, "
                "customer_name = %s, vendor_code = %s, bin_count = %s, "
                "jig_count = %s, updated_at = CURRENT_TIMESTAMP(6) "
                "WHERE settings_id = %s",
                (*values, row["settings_id"]),
            )
            return row["settings_id"]
        cur.execute(
            "INSERT INTO part_settings (part_number, model_number, "
            "customer_name, vendor_code, bin_count, jig_count) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (settings.part_number, *values),
        )
        return cur.lastrowid

    @staticmethod
    def _save_boxes(cur, settings_id, settings):
        """Update boxes that already exist, insert new ones and delete boxes
        that are no longer in the layout."""
        cur.execute(
            "SELECT box_id, box_type, label FROM box_positions "
            "WHERE settings_id = %s",
            (settings_id,),
        )
        existing = {
            (r["box_type"], r["label"]): r["box_id"] for r in cur.fetchall()
        }
        for box_type, items in (("BIN", settings.bins), ("JIG", settings.jigs)):
            for b in items:
                box_id = existing.pop((box_type, b.label), None)
                if box_id is None:
                    cur.execute(
                        "INSERT INTO box_positions "
                        "(settings_id, box_type, label, x, y) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (settings_id, box_type, b.label, b.x, b.y),
                    )
                else:
                    cur.execute(
                        "UPDATE box_positions SET x = %s, y = %s "
                        "WHERE box_id = %s",
                        (b.x, b.y, box_id),
                    )
        if existing:
            cur.executemany(
                "DELETE FROM box_positions WHERE box_id = %s",
                [(box_id,) for box_id in existing.values()],
            )


# ==================================================
# BOX ROW
# ==================================================

def rounded_rect_points(x1, y1, x2, y2, r):
    """Polygon points that draw a rounded rectangle when smooth=True."""
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]


class Box:
    def __init__(self, label, x):
        self.label = label
        self.x = x
        self.shape_id = None
        self.text_id = None


class BoxRow:
    """One row of boxes drawn on its own canvas. Boxes only move along x,
    so a Bin box can never end up in the Jig row and vice versa."""

    def __init__(self, parent, title, fill, outline, on_select):
        self.fill = fill
        self.outline = outline
        self.on_select = on_select
        self.boxes = []
        self.drag = None

        self.frame = tk.Frame(parent, bg=PANEL)
        tk.Label(
            self.frame, text=title, bg=PANEL, fg=MUTED, font=LABEL_FONT
        ).pack(anchor="w", pady=(0, 4))

        self.canvas = tk.Canvas(
            self.frame,
            height=ROW_HEIGHT,
            bg=ROW_BG,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        self.canvas.pack(fill="x")

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>", self._on_hover)
        self.canvas.bind("<Configure>", self._on_resize)

    # ---------- layout ----------

    def max_x(self):
        return max(ROW_PAD, self.canvas.winfo_width() - BOX_W - ROW_PAD)

    def default_positions(self, count):
        """Evenly spaced x positions, centered in the row."""
        width = self.canvas.winfo_width()
        free = width - 2 * ROW_PAD - count * BOX_W
        spacing = min(MAX_SPACING, max(BOX_GAP, free // max(count - 1, 1)))
        total = count * BOX_W + (count - 1) * spacing
        start = max(ROW_PAD, (width - total) // 2)
        return [start + i * (BOX_W + spacing) for i in range(count)]

    def generate(self, prefix, count):
        labels = [f"{prefix}{i}" for i in range(1, count + 1)]
        self.set_boxes(zip(labels, self.default_positions(count)))

    def reset_positions(self):
        labels = [box.label for box in self.boxes]
        self.set_boxes(zip(labels, self.default_positions(len(labels))))

    def set_boxes(self, items):
        """Replace all boxes with (label, x) pairs."""
        self.clear()
        for label, x in items:
            box = Box(label, x)
            box.shape_id = self.canvas.create_polygon(
                0, 0, 0, 0, smooth=True,
                fill=self.fill, outline=self.outline, width=2,
            )
            box.text_id = self.canvas.create_text(
                0, 0, text=label, fill=TEXT, font=BOX_FONT
            )
            self.boxes.append(box)
            self._draw(box)
        self._fit_to_width()

    def clear(self):
        self.canvas.delete("all")
        self.boxes = []
        self.drag = None

    def export(self):
        return [BoxConfig(box.label, box.x, ROW_PAD) for box in self.boxes]

    def highlight(self, box, selected):
        self.canvas.itemconfig(
            box.shape_id,
            fill=SELECTED_FILL if selected else self.fill,
            outline=SELECTED_OUTLINE if selected else self.outline,
            width=3 if selected else 2,
        )

    def _draw(self, box):
        x1, y1 = box.x, ROW_PAD
        x2, y2 = x1 + BOX_W, y1 + BOX_H
        self.canvas.coords(
            box.shape_id, *rounded_rect_points(x1, y1, x2, y2, BOX_RADIUS)
        )
        self.canvas.coords(box.text_id, x1 + BOX_W / 2, y1 + BOX_H / 2)

    def _fit_to_width(self):
        """Push boxes left when the row gets narrower, keeping their order
        and the minimum gap so they never overlap or leave the row."""
        limit = self.max_x()
        for box in sorted(self.boxes, key=lambda b: b.x, reverse=True):
            if box.x > limit:
                box.x = limit
                self._draw(box)
            limit = box.x - BOX_W - BOX_GAP

    def _box_at(self, x, y):
        if not ROW_PAD <= y <= ROW_PAD + BOX_H:
            return None
        for box in self.boxes:
            if box.x <= x <= box.x + BOX_W:
                return box
        return None

    def _nearest_free_x(self, box, wanted):
        """The free x position closest to where the user is dragging, so the
        box stays inside the row and never overlaps another box."""
        lo, hi = ROW_PAD, self.max_x()
        blocked = sorted(
            (other.x - BOX_W - BOX_GAP, other.x + BOX_W + BOX_GAP)
            for other in self.boxes
            if other is not box
        )
        free = []
        start = lo
        for block_start, block_end in blocked:
            if block_start > start:
                free.append((start, min(block_start, hi)))
            start = max(start, block_end)
        free.append((start, hi))

        candidates = [min(max(wanted, a), b) for a, b in free if a <= b]
        if not candidates:
            return box.x
        return min(candidates, key=lambda x: abs(x - wanted))

    # ---------- mouse events ----------

    def _on_press(self, event):
        box = self._box_at(event.x, event.y)
        self.on_select(self, box)
        if box:
            self.drag = {
                "box": box,
                "start_x": event.x,
                "offset": event.x - box.x,
                "moving": False,
            }

    def _on_drag(self, event):
        if not self.drag:
            return
        # Ignore tiny movements so a click only selects the box.
        if not self.drag["moving"]:
            if abs(event.x - self.drag["start_x"]) < DRAG_THRESHOLD:
                return
            self.drag["moving"] = True
            self.canvas.config(cursor="sb_h_double_arrow")

        box = self.drag["box"]
        new_x = self._nearest_free_x(box, event.x - self.drag["offset"])
        if new_x != box.x:
            box.x = new_x
            self._draw(box)

    def _on_release(self, event):
        self.drag = None
        self._on_hover(event)

    def _on_hover(self, event):
        if self.drag:
            return
        over_box = self._box_at(event.x, event.y) is not None
        self.canvas.config(cursor="hand2" if over_box else "")

    def _on_resize(self, _event):
        self._fit_to_width()


# ==================================================
# SETTINGS PAGE
# ==================================================

class SettingsPage:
    def __init__(self, root, store):
        self.root = root
        self.store = store
        self.selected = None  # (row, box) of the selected box
        self.vars = {}
        self.inputs = {}

        root.title("Settings - Bin & Jig Configuration")
        root.geometry("1280x720")
        root.minsize(1220, 600)
        root.configure(bg=BG)

        self._setup_style()
        self._build_header()
        self._build_form()
        self._build_buttons()
        self._build_layout_group()
        self._build_status_bar()

        # Rows need their real width before saved positions are restored.
        root.wait_visibility(self.bin_row.canvas)
        root.update_idletasks()
        self.load_settings()

    # ---------- UI ----------

    def _setup_style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "Dark.TCombobox",
            fieldbackground=ROW_BG,
            background=PANEL,
            foreground=TEXT,
            arrowcolor=TEXT,
            bordercolor=BORDER,
            lightcolor=ROW_BG,
            darkcolor=ROW_BG,
            padding=4,
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", ROW_BG)],
            foreground=[("readonly", TEXT)],
            selectbackground=[("readonly", ROW_BG)],
            selectforeground=[("readonly", TEXT)],
        )
        self.root.option_add("*TCombobox*Listbox.background", ROW_BG)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.root.option_add("*TCombobox*Listbox.selectForeground", BG)
        self.root.option_add("*TCombobox*Listbox.font", INPUT_FONT)

    def _build_header(self):
        tk.Label(
            self.root, text="Settings", bg=BG, fg=ACCENT, font=TITLE_FONT
        ).pack(anchor="w", padx=20, pady=(14, 8))

    def _build_form(self):
        form = tk.Frame(
            self.root, bg=PANEL, padx=10, pady=8,
            highlightthickness=1, highlightbackground=BORDER,
        )
        form.pack(fill="x", padx=20)
        for column in range(3):
            form.columnconfigure(column, weight=1, uniform="field")

        for i, (key, caption) in enumerate(TEXT_FIELDS + COUNT_FIELDS):
            row, column = divmod(i, 3)
            cell = tk.Frame(form, bg=PANEL)
            cell.grid(row=row, column=column, sticky="ew", padx=10, pady=6)
            tk.Label(
                cell, text=caption, bg=PANEL, fg=MUTED, font=LABEL_FONT
            ).pack(anchor="w")

            var = tk.StringVar()
            if key in dict(COUNT_FIELDS):
                widget = ttk.Combobox(
                    cell, textvariable=var, values=COUNT_OPTIONS,
                    state="readonly", font=INPUT_FONT, style="Dark.TCombobox",
                )
                widget.pack(fill="x")
            else:
                widget = tk.Entry(
                    cell, textvariable=var, bg=ROW_BG, fg=TEXT,
                    insertbackground=TEXT, relief="flat", font=INPUT_FONT,
                    highlightthickness=1, highlightbackground=BORDER,
                    highlightcolor=ACCENT,
                )
                widget.pack(fill="x", ipady=5)
                # Clear the red error border once the user starts typing.
                var.trace_add(
                    "write",
                    lambda *_, w=widget: w.config(highlightbackground=BORDER),
                )
            self.vars[key] = var
            self.inputs[key] = widget

    def _build_buttons(self):
        bar = tk.Frame(self.root, bg=BG)
        bar.pack(fill="x", padx=20, pady=12)

        buttons = [
            ("Generate Layout", ACCENT, BG, self.generate_layout),
            ("Save Settings", "#00E676", BG, self.save_settings),
            ("Reset Layout", PANEL, TEXT, self.reset_layout),
            ("Clear", "#DC2626", TEXT, self.clear_all),
        ]
        for text, bg, fg, command in buttons:
            tk.Button(
                bar, text=text, command=command, bg=bg, fg=fg,
                activebackground=bg, activeforeground=fg, font=BUTTON_FONT,
                relief="flat", padx=18, pady=7, cursor="hand2",
                highlightthickness=1, highlightbackground=BORDER,
            ).pack(side="left", padx=(0, 10))

    def _build_layout_group(self):
        self.group = tk.LabelFrame(
            self.root, text=" Bin & Jig Configuration ", bg=PANEL, fg=ACCENT,
            font=("Segoe UI", 12, "bold"), relief="groove", bd=2,
            padx=16, pady=12,
        )
        self.group.pack(fill="both", expand=True, padx=20)

        self.bin_row = BoxRow(
            self.group, "Row 1 - Bin boxes", BIN_FILL, BIN_OUTLINE,
            self._on_box_selected,
        )
        self.bin_row.frame.pack(fill="x")

        self.jig_row = BoxRow(
            self.group, "Row 2 - Jig boxes", JIG_FILL, JIG_OUTLINE,
            self._on_box_selected,
        )
        self.jig_row.frame.pack(fill="x", pady=(18, 0))

        tk.Label(
            self.group,
            text="Click a box to select it. Drag it left or right to move it "
                 "within its row.",
            bg=PANEL, fg=MUTED, font=LABEL_FONT,
        ).pack(anchor="w", pady=(14, 0))

        # Clicking empty space in the group deselects the current box.
        self.group.bind("<Button-1>", lambda _e: self._on_box_selected(None, None))

    def _build_status_bar(self):
        self.status = tk.Label(
            self.root, text="", bg=BG, fg=MUTED, font=LABEL_FONT, anchor="w"
        )
        self.status.pack(fill="x", padx=20, pady=8)

    def _set_status(self, text):
        self.status.config(text=text)

    # ---------- selection ----------

    def _on_box_selected(self, row, box):
        if self.selected:
            old_row, old_box = self.selected
            old_row.highlight(old_box, False)
        self.selected = (row, box) if box else None
        if box:
            row.highlight(box, True)
            self._set_status(f"Selected {box.label}")

    def _clear_selection(self):
        self.selected = None

    # ---------- validation ----------

    def validate(self):
        """Show every missing field at once. Returns True when all are filled."""
        problems = []
        for key, caption in TEXT_FIELDS:
            if not self.vars[key].get().strip():
                problems.append(f"{caption} must not be empty.")
                self.inputs[key].config(highlightbackground=ERROR)
        for key, caption in COUNT_FIELDS:
            if not self.vars[key].get():
                problems.append(f"Select the {caption.lower()}.")
        if problems:
            messagebox.showwarning(
                "Missing information", "\n".join(problems), parent=self.root
            )
            return False
        return True

    def _selected_counts(self):
        return int(self.vars["bin_count"].get()), int(self.vars["jig_count"].get())

    # ---------- button actions ----------

    def generate_layout(self):
        if not self.validate():
            return
        bins, jigs = self._selected_counts()
        self._clear_selection()
        self.bin_row.generate("BIN", bins)
        self.jig_row.generate("J", jigs)
        self._set_status(f"Generated {bins} Bin boxes and {jigs} Jig boxes.")

    def save_settings(self):
        if not self.validate():
            return
        if not self.bin_row.boxes:
            messagebox.showwarning(
                "No layout", "Click Generate Layout before saving.",
                parent=self.root,
            )
            return
        if self._selected_counts() != (
            len(self.bin_row.boxes), len(self.jig_row.boxes)
        ):
            messagebox.showwarning(
                "Layout out of date",
                "The number of bins or jig boxes was changed.\n"
                "Click Generate Layout to update the layout before saving.",
                parent=self.root,
            )
            return

        settings = Settings(
            **{key: self.vars[key].get().strip() for key, _ in TEXT_FIELDS},
            bin_count=len(self.bin_row.boxes),
            jig_count=len(self.jig_row.boxes),
            bins=self.bin_row.export(),
            jigs=self.jig_row.export(),
        )
        try:
            self.store.save(settings)
        except StorageError as e:
            messagebox.showerror("Save failed", str(e), parent=self.root)
            return
        self._set_status(f"Settings saved to {self.store.location}")
        messagebox.showinfo("Saved", "Settings saved.", parent=self.root)

    def reset_layout(self):
        if not self.bin_row.boxes:
            messagebox.showinfo(
                "No layout", "There is no layout to reset.", parent=self.root
            )
            return
        self._clear_selection()
        self.bin_row.reset_positions()
        self.jig_row.reset_positions()
        self._set_status("Layout reset to the default positions.")

    def clear_all(self):
        if not messagebox.askyesno(
            "Clear",
            "Clear all fields and remove the generated layout?\n"
            "Saved settings are not deleted.",
            parent=self.root,
        ):
            return
        for key, var in self.vars.items():
            var.set("")
            if key in dict(TEXT_FIELDS):
                self.inputs[key].config(highlightbackground=BORDER)
        self._clear_selection()
        self.bin_row.clear()
        self.jig_row.clear()
        self._set_status("Cleared.")

    def load_settings(self):
        try:
            settings = self.store.load()
        except StorageError as e:
            messagebox.showwarning("Could not load settings", str(e),
                                   parent=self.root)
            self._set_status("Database not available. Settings cannot be "
                             "loaded or saved.")
            return
        if settings is None:
            self._set_status("No saved settings yet. Fill in the details and "
                             "click Generate Layout.")
            return

        for key, _ in TEXT_FIELDS:
            self.vars[key].set(getattr(settings, key))
        for key, _ in COUNT_FIELDS:
            count = str(getattr(settings, key))
            self.vars[key].set(count if count in COUNT_OPTIONS else "")

        self.bin_row.set_boxes((b.label, b.x) for b in settings.bins)
        self.jig_row.set_boxes((j.label, j.x) for j in settings.jigs)
        self._set_status(
            f"Loaded part {settings.part_number} from {self.store.location}"
        )


if __name__ == "__main__":
    root = tk.Tk()
    try:
        store = MySqlSettingsStore(DB_CONFIG_FILE)
    except StorageError as e:
        root.withdraw()
        messagebox.showerror("Database settings", str(e))
        root.destroy()
    else:
        SettingsPage(root, store)
        root.mainloop()
