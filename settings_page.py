"""
Settings Page - Dynamic Bin and Jig Box Configuration

Enter part details, choose how many Bin and Jig boxes are needed, generate
the layout, then drag the BIN and J boxes anywhere on the live camera
picture, which is the background of the Bin & Jig Configuration area.
The details and box positions are saved to a MySQL database and restored the
next time the application opens. Connection details are read from
db_config.ini (see db_config.example.ini).
"""

import configparser
import os
import re
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import colorchooser, messagebox, ttk

import cv2
import numpy as np
import pymysql
from PIL import Image, ImageTk

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
SELECTED_OUTLINE = "#00E676"

# (fill, outline) of each kind of box
BOX_STYLES = {
    "BIN": (BIN_FILL, BIN_OUTLINE),
    "JIG": (JIG_FILL, JIG_OUTLINE),
}

# Fill colors a box can be given. Bright colors that show up well on a
# projector; "Custom..." on the Settings page allows any other color.
FILL_COLORS = [
    ("White", "#FFFFFF"),
    ("Red", "#FF3030"),
    ("Green", "#00E676"),
    ("Blue", "#2979FF"),
    ("Yellow", "#FFEA00"),
    ("Orange", "#FF9100"),
    ("Purple", "#D500F9"),
    ("Cyan", "#00E5FF"),
    ("Pink", "#FF4081"),
    ("Lime", "#C6FF00"),
    ("Brown", "#8D6E63"),
    ("Grey", "#9E9E9E"),
]

TITLE_FONT = ("Segoe UI", 22, "bold")
LABEL_FONT = ("Segoe UI", 10)
INPUT_FONT = ("Segoe UI", 11)
BUTTON_FONT = ("Segoe UI", 10, "bold")
BOX_W = 80
BOX_H = 60
BOX_RADIUS = 12
BOX_GAP = 12          # minimum space between two boxes
MAX_SPACING = 40      # space between boxes in the default layout
ROW_PAD = 12          # space between the boxes and the row edge
ROW_HEIGHT = BOX_H + 2 * ROW_PAD
# Width of the row the console's work area draws the boxes in
ROW_WIDTH = 1204
DRAG_THRESHOLD = 4    # pixels the mouse must move before a click becomes a drag

COUNT_OPTIONS = [str(n) for n in range(1, 13)]

# Boxes on the camera picture (Settings page and the console's Camera
# Output). Sizes are parts of the workspace width / height.
WORKSPACE_BOX_W = 0.08
WORKSPACE_BOX_H = 0.12
WORKSPACE_GAP = 0.015   # space between boxes in the default arrangement
WORKSPACE_MIN_H = 420   # Settings page workspace height in pixels, at least
LEFT_COLUMN_W = 300     # Settings page form and buttons column

# Camera view: finds and outlines the bins and jigs in the picture
CAMERA_INDEX = 0                # camera used when no picture is passed in
CAMERA_REFRESH_MS = 50
# Which side of the camera picture is shown at the top
CAMERA_ROTATIONS = {
    "UP": None,
    "DOWN": cv2.ROTATE_180,
    "LEFT": cv2.ROTATE_90_COUNTERCLOCKWISE,
    "RIGHT": cv2.ROTATE_90_CLOCKWISE,
}
CAMERA_ARROWS = {"UP": "▲", "DOWN": "▼", "LEFT": "◀", "RIGHT": "▶"}
BIN_MARK = (248, 189, 56)       # ACCENT in OpenCV's BGR order
JIG_MARK = (36, 191, 251)       # JIG_OUTLINE in BGR
WARNING = "#FBBF24"
OK_COLOR = "#00E676"
YELLOW_LOW = (10, 170, 90)      # yellow bins, OpenCV HSV (hue 0-180)
YELLOW_HIGH = (40, 255, 255)
DARK_MAX_VALUE = 70             # jigs are the dark objects below the bins
MIN_OBJECT_WIDTH = 0.03         # ignore anything narrower than this part
                                # of the picture width

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

def text_color_for(fill):
    """Black text on light fills, white text on dark ones."""
    r, g, b = (int(fill[i:i + 2], 16) for i in (1, 3, 5))
    return "#000000" if 0.299 * r + 0.587 * g + 0.114 * b > 128 else "#FFFFFF"


@dataclass
class BoxConfig:
    label: str
    x: int
    y: int
    color: str = ""  # fill color as "#RRGGBB"; "" means no color assigned
    # Top-left corner in the console's Camera Output, as parts (0 to 1) of
    # its width and height; None until the box has been placed there
    cam_x: float = None
    cam_y: float = None


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
    # Width of the box rows when the layout was saved, so other screens can
    # redraw the boxes at the same relative positions
    row_width: int = 0


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
        row_width     SMALLINT UNSIGNED NULL,
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
        fill_color  CHAR(7) NULL,
        cam_x       DOUBLE NULL,
        cam_y       DOUBLE NULL,
        CONSTRAINT pk_box_positions PRIMARY KEY (box_id),
        CONSTRAINT uq_box UNIQUE (settings_id, box_type, label),
        CONSTRAINT fk_box_positions_settings FOREIGN KEY (settings_id)
            REFERENCES part_settings (settings_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
]

# Columns added after the first release: (table, column, definition).
# Databases created earlier get them added automatically.
ADDED_COLUMNS = [
    ("part_settings", "row_width", "SMALLINT UNSIGNED NULL AFTER jig_count"),
    ("box_positions", "fill_color", "CHAR(7) NULL AFTER y"),
    ("box_positions", "cam_x", "DOUBLE NULL AFTER fill_color"),
    ("box_positions", "cam_y", "DOUBLE NULL AFTER cam_x"),
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
                for table, column, definition in ADDED_COLUMNS:
                    cur.execute(
                        "SELECT COUNT(*) AS n FROM information_schema.COLUMNS "
                        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
                        "AND COLUMN_NAME = %s",
                        (self.config["database"], table, column),
                    )
                    if cur.fetchone()["n"] == 0:
                        cur.execute(
                            f"ALTER TABLE {table} ADD COLUMN "
                            f"{column} {definition}"
                        )
            conn.commit()
        except pymysql.MySQLError as e:
            raise StorageError(f"Could not create the database:\n{e}") from e
        finally:
            conn.close()
        self._schema_ready = True

    def list_parts(self):
        """Part numbers of all saved parts, in the order they were added."""
        self._ensure_schema()
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT part_number FROM part_settings ORDER BY settings_id"
                )
                return [row["part_number"] for row in cur.fetchall()]
        except pymysql.MySQLError as e:
            raise StorageError(f"Could not load the part list:\n{e}") from e
        finally:
            conn.close()

    def load(self, part_number=None):
        """Return the Settings for part_number, or for the most recently saved
        part when part_number is None. Returns None if there is no such part."""
        self._ensure_schema()
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                if part_number is None:
                    cur.execute(
                        "SELECT * FROM part_settings "
                        "ORDER BY updated_at DESC, settings_id DESC LIMIT 1"
                    )
                else:
                    cur.execute(
                        "SELECT * FROM part_settings WHERE part_number = %s",
                        (part_number,),
                    )
                row = cur.fetchone()
                if row is None:
                    return None
                cur.execute(
                    "SELECT box_type, label, x, y, fill_color, cam_x, cam_y "
                    "FROM box_positions "
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
                BoxConfig(b["label"], b["x"], b["y"], b["fill_color"] or "",
                          b["cam_x"], b["cam_y"])
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
            row_width=row["row_width"] or 0,
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
            settings.row_width or None,
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
                "jig_count = %s, row_width = %s, "
                "updated_at = CURRENT_TIMESTAMP(6) "
                "WHERE settings_id = %s",
                (*values, row["settings_id"]),
            )
            return row["settings_id"]
        cur.execute(
            "INSERT INTO part_settings (part_number, model_number, "
            "customer_name, vendor_code, bin_count, jig_count, row_width) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (settings.part_number, *values),
        )
        return cur.lastrowid

    @staticmethod
    def _save_boxes(cur, settings_id, settings):
        """Update boxes that already exist, insert new ones and delete boxes
        that are no longer in the layout. A box without a Camera Output
        position keeps the one already saved."""
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
                color = b.color or None
                if box_id is None:
                    cur.execute(
                        "INSERT INTO box_positions (settings_id, box_type, "
                        "label, x, y, fill_color, cam_x, cam_y) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (settings_id, box_type, b.label, b.x, b.y, color,
                         b.cam_x, b.cam_y),
                    )
                else:
                    cur.execute(
                        "UPDATE box_positions SET x = %s, y = %s, "
                        "fill_color = %s, cam_x = COALESCE(%s, cam_x), "
                        "cam_y = COALESCE(%s, cam_y) WHERE box_id = %s",
                        (b.x, b.y, color, b.cam_x, b.cam_y, box_id),
                    )
        if existing:
            cur.executemany(
                "DELETE FROM box_positions WHERE box_id = %s",
                [(box_id,) for box_id in existing.values()],
            )

    def save_camera_positions(self, part_number, positions):
        """Store where each box was dragged to in the console's Camera
        Output. positions: (box_type, label, x, y) with x and y as parts of
        the workspace width and height."""
        self._ensure_schema()
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.executemany(
                    "UPDATE box_positions bp JOIN part_settings ps "
                    "ON ps.settings_id = bp.settings_id "
                    "SET bp.cam_x = %s, bp.cam_y = %s "
                    "WHERE ps.part_number = %s AND bp.box_type = %s "
                    "AND bp.label = %s",
                    [(x, y, part_number, box_type, label)
                     for box_type, label, x, y in positions],
                )
            conn.commit()
        except pymysql.MySQLError as e:
            conn.rollback()
            raise StorageError(f"Could not save box positions:\n{e}") from e
        finally:
            conn.close()


# ==================================================
# BOX LAYOUT AND CAMERA WORKSPACE
# ==================================================

def rounded_rect_points(x1, y1, x2, y2, r):
    """Polygon points that draw a rounded rectangle when smooth=True."""
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]


def row_width_for(count):
    """Narrowest row that holds count boxes with the minimum gap."""
    return 2 * ROW_PAD + count * BOX_W + max(count - 1, 0) * BOX_GAP


def even_positions(count, width):
    """Evenly spaced x positions, centered in a row of the given width."""
    free = width - 2 * ROW_PAD - count * BOX_W
    spacing = min(MAX_SPACING, max(BOX_GAP, free // max(count - 1, 1)))
    total = count * BOX_W + (count - 1) * spacing
    start = max(ROW_PAD, (width - total) // 2)
    return [start + i * (BOX_W + spacing) for i in range(count)]


def boxes_overlap(xs):
    """True when any two boxes at these x positions overlap. Parts saved
    while Bins and Jigs had a row each have them on top of each other."""
    xs = sorted(xs)
    return any(b - a < BOX_W for a, b in zip(xs, xs[1:]))


class WorkspaceBox:
    def __init__(self, kind, label, color, x, y):
        self.kind = kind      # "BIN" or "JIG"
        self.label = label
        self.color = color    # fill color as "#RRGGBB", "" if none
        self.x = x            # top-left corner, as parts (0 to 1) of the
        self.y = y            # workspace width and height
        self.shape_id = None
        self.text_id = None


class CameraWorkspace:
    """The live camera picture with a box for every Bin and Jig on top of
    it. Each box can be dragged anywhere inside the workspace on its own; it
    never leaves the workspace and is not dropped on top of another box.
    Positions are kept as parts of the workspace width and height, so a box
    stays on the same spot of the picture when the workspace size changes.
    Used by the Settings page and by the console's Camera Output."""

    def __init__(self, parent, on_moved=None, on_select=None):
        """on_moved(positions) is called after the user drops a box, with
        (kind, label, x, y) for every box. on_select(box) is called when the
        user clicks a box, or empty space (box is None)."""
        self.on_moved = on_moved
        self.on_select = on_select
        self.boxes = []         # drawing order: the last box is on top
        self.selected = None
        self.drag = None
        self.photo = None

        self.canvas = tk.Canvas(parent, bg="#000000", highlightthickness=0)
        self.picture_id = self.canvas.create_image(0, 0, anchor="nw")
        self.message_id = self.canvas.create_text(
            0, 0, text="", fill=TEXT, font=("Segoe UI", 14)
        )

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>", self._on_hover)
        self.canvas.bind("<Configure>", self._on_resize)

    # ---------- picture ----------

    def size(self):
        return self.canvas.winfo_width(), self.canvas.winfo_height()

    def show_picture(self, photo):
        self.photo = photo  # Tk does not keep the picture alive by itself
        self.canvas.itemconfigure(self.picture_id, image=photo)
        self.show_message("")

    def show_message(self, text):
        width, height = self.size()
        self.canvas.coords(self.message_id, width / 2, height / 2)
        self.canvas.itemconfigure(
            self.message_id, text=text, width=max(width - 40, 50)
        )

    # ---------- boxes ----------

    def set_boxes(self, items, keep_current=True):
        """Show one box per (kind, label, color, x, y). A box without a
        position keeps the spot it already has here (when keep_current), or
        goes to the first free spot, so the boxes already placed are not
        disturbed."""
        current = {box.label: (box.x, box.y) for box in self.boxes}
        if not keep_current:
            current = {}

        self.clear()

        waiting = []
        for kind, label, color, x, y in items:
            box = WorkspaceBox(kind, label, color, x, y)
            if x is None or y is None:
                if label in current:
                    box.x, box.y = current[label]
                else:
                    waiting.append(box)
            else:
                box.x, box.y = self._clamp(x, y)
            self.boxes.append(box)

        placed = [box for box in self.boxes if box not in waiting]
        for box in waiting:
            box.x, box.y = self._free_spot(placed)
            placed.append(box)

        for box in self.boxes:
            box.shape_id = self.canvas.create_polygon(
                0, 0, 0, 0, smooth=True, width=2, tags="box"
            )
            box.text_id = self.canvas.create_text(
                0, 0, text=box.label, tags="box"
            )
            self._paint(box)
            self._draw(box)

    def clear(self):
        self.canvas.delete("box")
        self.boxes = []
        self.selected = None
        self.drag = None

    def count(self, kind):
        return sum(box.kind == kind for box in self.boxes)

    def positions(self):
        return [(box.kind, box.label, box.x, box.y) for box in self.boxes]

    def set_color(self, box, color):
        box.color = color
        self._paint(box)

    def select(self, box):
        old, self.selected = self.selected, box
        for changed in (old, box):
            if changed is not None and changed in self.boxes:
                self._paint(changed)

    @staticmethod
    def _clamp(x, y):
        return (
            min(max(x, 0), 1 - WORKSPACE_BOX_W),
            min(max(y, 0), 1 - WORKSPACE_BOX_H),
        )

    @staticmethod
    def _overlaps(x, y, other):
        # Boxes may touch, but not cover each other
        return (x < other.x + WORKSPACE_BOX_W and other.x < x + WORKSPACE_BOX_W
                and y < other.y + WORKSPACE_BOX_H
                and other.y < y + WORKSPACE_BOX_H)

    def _free_spot(self, placed):
        """First spot, row by row from the top left, that no box covers."""
        y = WORKSPACE_GAP
        while y + WORKSPACE_BOX_H <= 1:
            x = WORKSPACE_GAP
            while x + WORKSPACE_BOX_W <= 1:
                if not any(self._overlaps(x, y, other) for other in placed):
                    return x, y
                x += WORKSPACE_BOX_W + WORKSPACE_GAP
            y += WORKSPACE_BOX_H + WORKSPACE_GAP
        return WORKSPACE_GAP, WORKSPACE_GAP  # workspace full

    def _can_move(self, box, x, y):
        """True unless the box would cover a box it does not cover now. A
        box that already overlaps another can still be dragged off it."""
        return not any(
            self._overlaps(x, y, other)
            and not self._overlaps(box.x, box.y, other)
            for other in self.boxes
            if other is not box
        )

    def _paint(self, box):
        fill, outline = BOX_STYLES[box.kind]
        fill = box.color or fill
        selected = box is self.selected
        self.canvas.itemconfigure(
            box.shape_id,
            fill=fill,
            outline=SELECTED_OUTLINE if selected else outline,
            width=4 if selected else 2,
        )
        self.canvas.itemconfigure(
            box.text_id, fill=text_color_for(fill) if box.color else TEXT
        )

    def _draw(self, box):
        width, height = self.size()
        x1, y1 = box.x * width, box.y * height
        x2 = x1 + WORKSPACE_BOX_W * width
        y2 = y1 + WORKSPACE_BOX_H * height
        radius = min(x2 - x1, y2 - y1) * 0.2
        self.canvas.coords(
            box.shape_id, *rounded_rect_points(x1, y1, x2, y2, radius)
        )
        self.canvas.coords(box.text_id, (x1 + x2) / 2, (y1 + y2) / 2)
        font_size = max(7, min(16, int((y2 - y1) / 3.5)))
        self.canvas.itemconfigure(
            box.text_id, font=("Segoe UI", font_size, "bold")
        )

    def _box_at(self, px, py):
        width, height = self.size()
        for box in reversed(self.boxes):
            if (box.x * width <= px <= (box.x + WORKSPACE_BOX_W) * width
                    and box.y * height <= py
                    <= (box.y + WORKSPACE_BOX_H) * height):
                return box
        return None

    # ---------- mouse events ----------

    def _on_press(self, event):
        box = self._box_at(event.x, event.y)
        self.select(box)
        if self.on_select:
            self.on_select(box)
        if box:
            width, height = self.size()
            self.drag = {
                "box": box,
                "start": (event.x, event.y),
                "offset": (event.x - box.x * width,
                           event.y - box.y * height),
                "moving": False,
            }

    def _on_drag(self, event):
        if not self.drag:
            return
        box = self.drag["box"]

        # Ignore tiny movements so a click only selects the box.
        if not self.drag["moving"]:
            start_x, start_y = self.drag["start"]
            if max(abs(event.x - start_x),
                   abs(event.y - start_y)) < DRAG_THRESHOLD:
                return
            self.drag["moving"] = True
            self.canvas.config(cursor="fleur")
            # Bring the dragged box to the front
            self.boxes.remove(box)
            self.boxes.append(box)
            self.canvas.tag_raise(box.shape_id)
            self.canvas.tag_raise(box.text_id)

        width, height = self.size()
        offset_x, offset_y = self.drag["offset"]
        x, y = self._clamp(
            (event.x - offset_x) / width, (event.y - offset_y) / height
        )

        # When the spot is taken, slide along the side of the other box
        for new_x, new_y in ((x, y), (x, box.y), (box.x, y)):
            if self._can_move(box, new_x, new_y):
                if (new_x, new_y) != (box.x, box.y):
                    box.x, box.y = new_x, new_y
                    self._draw(box)
                break

    def _on_release(self, event):
        moved = self.drag is not None and self.drag["moving"]
        self.drag = None
        self._on_hover(event)
        if moved and self.on_moved:
            self.on_moved(self.positions())

    def _on_hover(self, event):
        if self.drag:
            return
        over_box = self._box_at(event.x, event.y) is not None
        self.canvas.config(cursor="hand2" if over_box else "")

    def _on_resize(self, _event):
        width, height = self.size()
        self.canvas.coords(self.message_id, width / 2, height / 2)
        self.canvas.itemconfigure(self.message_id, width=max(width - 40, 50))
        for box in self.boxes:
            self._draw(box)


class _Tooltip:
    """Small label that appears while the mouse is over a widget."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _event):
        x = self.widget.winfo_rootx()
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 2
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self.tip, text=self.text, bg=ROW_BG, fg=TEXT, font=LABEL_FONT,
            padx=6, pady=2, highlightthickness=1, highlightbackground=BORDER,
        ).pack()

    def _hide(self, _event):
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


# ==================================================
# FINDING BINS AND JIGS IN THE CAMERA PICTURE
# ==================================================

def find_columns(mask, min_width):
    """Left-to-right (x1, x2) runs of columns where the mask covers at least
    40% of what its fullest column covers."""
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
    """The yellow bins and the dark jigs below them, each as left-to-right
    (x1, y1, x2, y2) rectangles in picture pixels."""
    min_width = int(frame.shape[1] * MIN_OBJECT_WIDTH)
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
    rows = np.nonzero(dark.any(axis=1))[0]
    if len(rows) == 0:
        return bins, []
    jig_top, jig_bottom = int(rows.min()), int(rows.max())
    jigs = [
        (x1, jig_top, x2, jig_bottom)
        for x1, x2 in find_columns(dark, min_width)
    ]

    return bins, jigs


def drop_cut_off(found, count, width):
    """Objects cut off at the picture edge are only partly in view; leave
    them out first when the camera sees more than the part has."""
    found = list(found)
    while len(found) > count:
        at_edge = [r for r in found if r[0] <= 0 or r[2] >= width]
        if not at_edge:
            break
        found.remove(min(at_edge, key=lambda r: r[2] - r[0]))
    return found


# ==================================================
# SETTINGS PAGE
# ==================================================

class SettingsPage:
    def __init__(self, root, store, part_number=None, on_saved=None,
                 get_camera_frame=None, get_camera_direction=None,
                 set_camera_direction=None):
        """root can be the main Tk window or a Toplevel opened from another
        screen. part_number picks which part to show first (default: the
        most recently saved one). on_saved(settings) is called after every
        successful save. get_camera_frame() returns the latest camera
        picture (or None); without it the page opens the camera itself.
        get_camera_direction() and set_camera_direction(direction) let the
        camera arrow buttons turn the picture of the screen that passes it
        in; without them the page turns its own camera's picture."""
        self.root = root
        self.store = store
        self.on_saved = on_saved
        self.get_camera_frame = get_camera_frame
        self.capture = None       # own camera, only without get_camera_frame
        self.camera_frame = None  # latest camera picture, without outlines
        self.camera_job = None
        self.get_camera_direction = get_camera_direction
        self.set_camera_direction = set_camera_direction
        self.camera_direction = "UP"  # own camera only
        self.camera_buttons = {}
        self.shown_direction = None   # direction the buttons highlight
        self.picture_aspect = 4 / 3  # width / height of the camera picture
        self.selected = None      # the selected box
        self.vars = {}
        self.inputs = {}
        self.loaded_part = ""  # part number shown in the Saved Parts list
        self.dirty = False     # True when there are unsaved changes

        root.title("Settings - Bin & Jig Configuration")
        root.geometry("1280x800")
        root.minsize(1150, 700)
        root.configure(bg=BG)

        self._setup_style()
        self._build_header()
        self._build_status_bar()

        # Form and buttons in a column on the left, so the camera picture
        # with the boxes gets the full height on the right
        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True)
        self.left = tk.Frame(body, bg=BG, width=LEFT_COLUMN_W)
        self.left.pack(side="left", fill="y", padx=(20, 0))
        self.left.pack_propagate(False)
        self.right = tk.Frame(body, bg=BG)
        self.right.pack(side="left", fill="both", expand=True)

        self._build_form()
        self._build_buttons()
        self._build_camera_buttons()
        self._build_layout_group()

        self.load_settings(part_number)

        self._start_camera()
        root.bind("<Destroy>", self._on_destroy, add="+")

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
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=20, pady=(14, 8))
        self.header = header

        tk.Label(
            header, text="Settings", bg=BG, fg=ACCENT, font=TITLE_FONT
        ).pack(side="left")

        # Saved Parts list: pick a part to load it into the form
        picker = tk.Frame(header, bg=BG)
        picker.pack(side="right")
        tk.Label(
            picker, text="Saved Parts", bg=BG, fg=MUTED, font=LABEL_FONT
        ).pack(side="left", padx=(0, 8))

        self.part_picker_var = tk.StringVar()
        self.part_picker = ttk.Combobox(
            picker, textvariable=self.part_picker_var, state="readonly",
            width=18, font=INPUT_FONT, style="Dark.TCombobox",
            postcommand=self._refresh_part_list,
        )
        self.part_picker.pack(side="left")
        self.part_picker.bind(
            "<<ComboboxSelected>>", self._on_saved_part_selected
        )

    def _build_form(self):
        form = tk.Frame(
            self.left, bg=PANEL, padx=10, pady=8,
            highlightthickness=1, highlightbackground=BORDER,
        )
        form.pack(fill="x")
        form.columnconfigure(0, weight=1)

        for row, (key, caption) in enumerate(TEXT_FIELDS + COUNT_FIELDS):
            cell = tk.Frame(form, bg=PANEL)
            cell.grid(row=row, column=0, sticky="ew", padx=6, pady=4)
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
            var.trace_add("write", lambda *_: self._mark_dirty())
            self.vars[key] = var
            self.inputs[key] = widget

    def _build_buttons(self):
        bar = tk.Frame(self.left, bg=BG)
        bar.pack(fill="x", pady=12)

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
            ).pack(fill="x", pady=(0, 8))

    def _build_camera_buttons(self):
        """Arrow buttons in the header that pick which side of the camera
        picture is shown at the top."""
        bar = tk.Frame(self.header, bg=BG)
        bar.pack(side="right", padx=(0, 30))
        tk.Label(
            bar, text="Camera View", bg=BG, fg=MUTED, font=LABEL_FONT
        ).pack(side="left", padx=(0, 8))
        for direction in CAMERA_ROTATIONS:
            button = tk.Button(
                bar, text=f"{CAMERA_ARROWS[direction]}  {direction}",
                command=lambda d=direction: self._turn_camera(d),
                bg=ROW_BG, fg=TEXT, activebackground=ACCENT,
                activeforeground=BG, font=BUTTON_FONT, relief="flat",
                width=8, pady=4, cursor="hand2", highlightthickness=1,
                highlightbackground=BORDER,
            )
            button.pack(side="left", padx=3)
            self.camera_buttons[direction] = button
        self._show_camera_direction()

    def _current_direction(self):
        if self.get_camera_direction is not None:
            return self.get_camera_direction()
        return self.camera_direction

    def _turn_camera(self, direction):
        if self.set_camera_direction is not None:
            self.set_camera_direction(direction)
        else:
            self.camera_direction = direction
        self._show_camera_direction()

    def _show_camera_direction(self):
        """Highlight the button of the direction in use."""
        current = self._current_direction()
        if current == self.shown_direction:
            return
        self.shown_direction = current
        for direction, button in self.camera_buttons.items():
            if direction == current:
                button.config(bg=ACCENT, fg=BG)
            else:
                button.config(bg=ROW_BG, fg=TEXT)

    def _build_layout_group(self):
        """The camera picture as background, with the BIN and J boxes on
        top of it."""
        self.group = tk.LabelFrame(
            self.right, text=" Bin & Jig Configuration - Camera Output ",
            bg=PANEL, fg=ACCENT, font=("Segoe UI", 12, "bold"),
            relief="groove", bd=2, padx=12, pady=8,
        )
        self.group.pack(fill="both", expand=True, padx=20)

        heading = tk.Frame(self.group, bg=PANEL)
        heading.pack(fill="x")
        tk.Label(
            heading,
            text="Drag the BIN and J boxes anywhere on the camera picture. "
                 "Click a box to select it and pick its fill color.",
            bg=PANEL, fg=MUTED, font=LABEL_FONT,
        ).pack(side="left")
        self.camera_found = tk.Label(
            heading, text="", bg=PANEL, fg=MUTED, font=BUTTON_FONT
        )
        self.camera_found.pack(side="right")

        # The workspace keeps the camera picture's shape and is centered in
        # this area, which takes all the height the window has left
        self.workspace_area = tk.Frame(
            self.group, bg=ROW_BG, height=WORKSPACE_MIN_H,
            highlightthickness=1, highlightbackground=BORDER,
        )
        self.workspace_area.pack(fill="both", expand=True, pady=(8, 0))
        self.workspace = CameraWorkspace(
            self.workspace_area,
            on_moved=lambda _positions: self._mark_dirty(),
            on_select=self._on_box_selected,
        )
        self.workspace_area.bind("<Configure>", self._fit_workspace)
        self.workspace.show_message("Starting camera...")

        self._build_color_bar()

        # Clicking empty space in the group deselects the current box.
        self.group.bind("<Button-1>", lambda _e: self._deselect())
        self.workspace_area.bind("<Button-1>", lambda _e: self._deselect())

    def _fit_workspace(self, _event=None):
        """Largest workspace with the camera picture's shape that fits."""
        area_w = self.workspace_area.winfo_width() - 2
        area_h = self.workspace_area.winfo_height() - 2
        width = min(area_w, area_h * self.picture_aspect)
        height = width / self.picture_aspect
        self.workspace.canvas.place(
            relx=0.5, rely=0.5, anchor="center",
            width=max(int(width), 1), height=max(int(height), 1),
        )

    def _build_color_bar(self):
        """Fill color swatches for the selected box."""
        bar = tk.Frame(self.group, bg=PANEL)
        bar.pack(fill="x", pady=(10, 0))

        self.color_title = tk.Label(
            bar, text="", width=24, anchor="w",
            bg=PANEL, fg=TEXT, font=("Segoe UI", 10, "bold"),
        )
        self.color_title.pack(side="left")

        self.swatches = {}
        for name, color in FILL_COLORS:
            swatch = tk.Canvas(
                bar, width=26, height=26, bg=PANEL,
                highlightthickness=0, cursor="hand2",
            )
            swatch.create_rectangle(
                4, 4, 23, 23, fill=color, outline=BORDER, tags="chip"
            )
            swatch.pack(side="left", padx=2)
            swatch.bind(
                "<Button-1>", lambda _e, c=color: self._set_selected_color(c)
            )
            self.swatches[color] = swatch
            _Tooltip(swatch, name)

        button_style = dict(
            bg=ROW_BG, fg=TEXT, activebackground=BORDER, activeforeground=TEXT,
            relief="flat", font=LABEL_FONT, padx=10, pady=2, cursor="hand2",
            highlightthickness=1, highlightbackground=BORDER,
        )
        self.custom_button = tk.Button(
            bar, text="Custom...", command=self._choose_custom_color,
            **button_style,
        )
        self.custom_button.pack(side="left", padx=(10, 4))
        self.no_color_button = tk.Button(
            bar, text="None", command=lambda: self._set_selected_color(""),
            **button_style,
        )
        self.no_color_button.pack(side="left", padx=4)

        # Shows the selected box's current color
        self.current_chip = tk.Canvas(
            bar, width=120, height=26, bg=PANEL, highlightthickness=0
        )
        self.current_chip.pack(side="left", padx=(10, 0))

        self._update_color_bar()

    def _update_color_bar(self):
        box = self.selected
        enabled = box is not None
        state = "normal" if enabled else "disabled"
        self.custom_button.config(state=state)
        self.no_color_button.config(state=state)

        if not enabled:
            self.color_title.config(text="Fill color: select a box", fg=MUTED)
        else:
            self.color_title.config(text=f"Fill color for {box.label}:", fg=TEXT)

        current = box.color.upper() if enabled else None
        for color, swatch in self.swatches.items():
            # Thick ring around the swatch that matches the box's color
            swatch.itemconfig(
                "chip",
                outline=SELECTED_OUTLINE if color == current else BORDER,
                width=3 if color == current else 1,
                stipple="" if enabled else "gray50",
            )

        self.current_chip.delete("all")
        if enabled:
            if box.color:
                self.current_chip.create_rectangle(
                    1, 4, 22, 23, fill=box.color, outline=BORDER
                )
                self.current_chip.create_text(
                    28, 13, anchor="w", text=box.color.upper(),
                    fill=MUTED, font=LABEL_FONT,
                )
            else:
                self.current_chip.create_text(
                    1, 13, anchor="w", text="Default", fill=MUTED,
                    font=LABEL_FONT,
                )

    def _set_selected_color(self, color):
        box = self.selected
        if box is None or box.color.upper() == color.upper():
            return
        self.workspace.set_color(box, color)
        self._mark_dirty()
        self._update_color_bar()
        if color:
            self._set_status(f"{box.label} fill color set to {color.upper()}.")
        else:
            self._set_status(f"{box.label} fill color removed.")

    def _choose_custom_color(self):
        box = self.selected
        if box is None:
            return
        _rgb, color = colorchooser.askcolor(
            color=box.color or None,
            title=f"Fill color for {box.label}",
            parent=self.root,
        )
        if color:
            self._set_selected_color(color.upper())

    def _build_status_bar(self):
        self.status = tk.Label(
            self.root, text="", bg=BG, fg=MUTED, font=LABEL_FONT, anchor="w"
        )
        self.status.pack(side="bottom", fill="x", padx=20, pady=8)

    def _set_status(self, text):
        self.status.config(text=text)

    # ---------- selection ----------

    def _on_box_selected(self, box):
        self.selected = box
        if box:
            self._set_status(f"Selected {box.label}")
        self._update_color_bar()

    def _deselect(self):
        self.workspace.select(None)
        self._on_box_selected(None)

    def _clear_selection(self):
        self.workspace.select(None)
        self.selected = None
        self._update_color_bar()

    # ---------- boxes ----------

    def _ordered_boxes(self):
        """BIN1, BIN2, ... then J1, J2, ... whatever order they are drawn
        in."""
        return sorted(
            self.workspace.boxes,
            key=lambda b: (b.kind != "BIN", int(b.label.lstrip("BINJ"))),
        )

    def _export(self):
        """Bin and Jig BoxConfigs with their Camera Output positions, plus
        the row width. The console's work area shows the boxes in one row,
        Bins first, evenly spaced."""
        ordered = self._ordered_boxes()
        row_width = max(ROW_WIDTH, row_width_for(len(ordered)))
        xs = even_positions(len(ordered), row_width)
        configs = {"BIN": [], "JIG": []}
        for box, x in zip(ordered, xs):
            configs[box.kind].append(
                BoxConfig(box.label, x, ROW_PAD, box.color, box.x, box.y)
            )
        return configs["BIN"], configs["JIG"], row_width

    # ---------- saved parts ----------

    def _mark_dirty(self):
        self.dirty = True

    def _refresh_part_list(self):
        # Runs each time the list opens, so newly saved parts appear
        try:
            self.part_picker["values"] = self.store.list_parts()
        except StorageError as e:
            messagebox.showwarning("Could not load parts", str(e),
                                   parent=self.root)

    def _on_saved_part_selected(self, _event=None):
        part = self.part_picker_var.get()
        if part == self.loaded_part and not self.dirty:
            return
        if self.dirty and not messagebox.askyesno(
            "Unsaved changes",
            f"You have changes that are not saved.\n"
            f"Discard them and open part {part}?",
            parent=self.root,
        ):
            # Keep showing the part that is still in the form
            self.part_picker_var.set(self.loaded_part)
            return
        self.load_settings(part)

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
        """Boxes for the selected counts. Boxes that already exist keep
        their spot and color; new ones go to free spots."""
        if not self.validate():
            return
        bins, jigs = self._selected_counts()
        colors = {box.label: box.color for box in self.workspace.boxes}
        labels = (
            [("BIN", f"BIN{i}") for i in range(1, bins + 1)]
            + [("JIG", f"J{i}") for i in range(1, jigs + 1)]
        )
        self._clear_selection()
        self.workspace.set_boxes(
            (kind, label, colors.get(label, ""), None, None)
            for kind, label in labels
        )
        self.dirty = True
        self._set_status(f"Generated {bins} Bin boxes and {jigs} Jig boxes.")

    def save_settings(self):
        if not self.validate():
            return
        if not self.workspace.boxes:
            messagebox.showwarning(
                "No layout", "Click Generate Layout before saving.",
                parent=self.root,
            )
            return
        if self._selected_counts() != (
            self.workspace.count("BIN"), self.workspace.count("JIG")
        ):
            messagebox.showwarning(
                "Layout out of date",
                "The number of bins or jig boxes was changed.\n"
                "Click Generate Layout to update the layout before saving.",
                parent=self.root,
            )
            return

        bins, jigs, row_width = self._export()
        settings = Settings(
            **{key: self.vars[key].get().strip() for key, _ in TEXT_FIELDS},
            bin_count=len(bins),
            jig_count=len(jigs),
            bins=bins,
            jigs=jigs,
            row_width=row_width,
        )
        try:
            self.store.save(settings)
        except StorageError as e:
            messagebox.showerror("Save failed", str(e), parent=self.root)
            return
        self.dirty = False
        self.loaded_part = settings.part_number
        self.part_picker_var.set(settings.part_number)
        self._set_status(f"Settings saved to {self.store.location}")
        if self.on_saved:
            self.on_saved(settings)
        messagebox.showinfo("Saved", "Settings saved.", parent=self.root)

    def reset_layout(self):
        if not self.workspace.boxes:
            messagebox.showinfo(
                "No layout", "There is no layout to reset.", parent=self.root
            )
            return
        self._clear_selection()
        self.workspace.set_boxes(
            [(box.kind, box.label, box.color, None, None)
             for box in self._ordered_boxes()],
            keep_current=False,
        )
        self.dirty = True
        self._set_status("Layout reset to the default positions.")

    # ---------- camera ----------

    def _start_camera(self):
        # Opened from the console: its camera is already in use, so show the
        # pictures it passes in. On its own, the page opens the camera.
        if self.get_camera_frame is None:
            capture = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
            if capture.isOpened():
                self.capture = capture
            else:
                capture.release()
                self.workspace.show_message(
                    f"Camera {CAMERA_INDEX} not found or cannot open"
                )
                return
        self._update_camera()

    def _read_camera(self):
        if self.capture is not None:
            success, frame = self.capture.read()
            if not success:
                return None
            # The console passes its pictures in already turned
            rotation = CAMERA_ROTATIONS[self.camera_direction]
            return frame if rotation is None else cv2.rotate(frame, rotation)
        return self.get_camera_frame()

    def _update_camera(self):
        # The console's own arrow buttons can turn the picture too
        self._show_camera_direction()
        frame = self._read_camera()
        if frame is not None:
            self.camera_frame = frame
            self._show_camera(frame)
        elif self.camera_frame is None:
            self.workspace.show_message("No picture from the camera")
        self.camera_job = self.root.after(
            CAMERA_REFRESH_MS, self._update_camera
        )

    def _show_camera(self, frame):
        """Draw the picture behind the boxes with the found bins and jigs
        outlined, and how many were found (green when they match the
        layout)."""
        height, width = frame.shape[:2]

        # Turning the camera on the console changes the picture's shape
        aspect = width / height
        if abs(aspect - self.picture_aspect) > 0.01:
            self.picture_aspect = aspect
            self._fit_workspace()

        view_w, view_h = self.workspace.size()
        if view_w <= 1 or view_h <= 1:
            return  # not shown yet

        bin_count = self.workspace.count("BIN")
        jig_count = self.workspace.count("JIG")
        bins, jigs = detect_bins_and_jigs(frame)
        bins = drop_cut_off(bins, bin_count, width)
        jigs = drop_cut_off(jigs, jig_count, width)

        scale_x, scale_y = view_w / width, view_h / height
        picture = cv2.resize(frame, (view_w, view_h))
        for found, color in ((bins, BIN_MARK), (jigs, JIG_MARK)):
            for x1, y1, x2, y2 in found:
                cv2.rectangle(
                    picture,
                    (int(x1 * scale_x), int(y1 * scale_y)),
                    (int(x2 * scale_x), int(y2 * scale_y)),
                    color, 2,
                )
        picture = cv2.cvtColor(picture, cv2.COLOR_BGR2RGB)
        self.workspace.show_picture(ImageTk.PhotoImage(Image.fromarray(picture)))

        matches = (len(bins), len(jigs)) == (bin_count, jig_count)
        self.camera_found.config(
            text=f"{len(bins)} bins · {len(jigs)} jigs found",
            fg=OK_COLOR if matches and self.workspace.boxes else WARNING,
        )

    def _on_destroy(self, event):
        # <Destroy> also fires for every widget inside the window
        if event.widget is not self.root:
            return
        if self.camera_job is not None:
            self.root.after_cancel(self.camera_job)
            self.camera_job = None
        if self.capture is not None:
            self.capture.release()
            self.capture = None

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
        self.workspace.clear()
        self.loaded_part = ""
        self.part_picker_var.set("")
        self.dirty = False
        self._set_status("Cleared.")

    def load_settings(self, part_number=None):
        try:
            settings = self.store.load(part_number)
        except StorageError as e:
            messagebox.showwarning("Could not load settings", str(e),
                                   parent=self.root)
            self._set_status("Database not available. Settings cannot be "
                             "loaded or saved.")
            return
        if settings is None:
            if part_number is None:
                self._set_status("No saved settings yet. Fill in the details "
                                 "and click Generate Layout.")
            else:
                self.part_picker_var.set(self.loaded_part)
                messagebox.showwarning(
                    "Part not found",
                    f"Part {part_number} is no longer saved.",
                    parent=self.root,
                )
            return

        for key, _ in TEXT_FIELDS:
            self.vars[key].set(getattr(settings, key))
            self.inputs[key].config(highlightbackground=BORDER)
        for key, _ in COUNT_FIELDS:
            count = str(getattr(settings, key))
            self.vars[key].set(count if count in COUNT_OPTIONS else "")

        # Boxes never placed on the camera picture go to free spots
        self._clear_selection()
        self.workspace.set_boxes(
            [("BIN", b.label, b.color, b.cam_x, b.cam_y)
             for b in settings.bins]
            + [("JIG", j.label, j.color, j.cam_x, j.cam_y)
               for j in settings.jigs],
            keep_current=False,
        )
        self.loaded_part = settings.part_number
        self.part_picker_var.set(settings.part_number)
        self.dirty = False
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
