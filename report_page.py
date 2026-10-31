"""
Report Page - Production Report

Shows how many parts were finished on the console, picked by model, part
number and a date range. The totals are shown as summary cards, a bar chart
of the quantity per day and a table with one row per day, station, model and
part. The table can be saved as a CSV file.
"""

import calendar
import csv
import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from settings_page import (
    ACCENT,
    BG,
    BORDER,
    BUTTON_FONT,
    INPUT_FONT,
    LABEL_FONT,
    MUTED,
    OK_COLOR,
    PANEL,
    ROW_BG,
    TEXT,
    TITLE_FONT,
    StorageError,
)

# ==================================================
# CONSTANTS
# ==================================================

ALL_MODELS = "All Models"
ALL_PARTS = "All Parts"
DATE_FORMAT = "%d-%m-%Y"        # how dates are shown
CARD_VALUE_FONT = ("Segoe UI", 22, "bold")
GRID_COLOR = "#334155"          # chart grid lines, kept faint
BAR_WIDTH_MAX = 28              # pixels; bars stay thin on short ranges
BAR_GAP = 2                     # surface gap between neighbouring bars
CHART_H = 160
STRIPE_BG = "#162033"           # every other table row


def date_text(day):
    return day.strftime(DATE_FORMAT)


# ==================================================
# DATE PICKER
# ==================================================

class DatePicker:
    """A button showing a date; clicking it opens a small month calendar to
    pick another one."""

    def __init__(self, parent, day, on_change=None):
        self.day = day
        self.on_change = on_change
        self.popup = None
        self.button = tk.Button(
            parent, text="", command=self._open, bg=ROW_BG, fg=TEXT,
            activebackground=ROW_BG, activeforeground=ACCENT,
            font=INPUT_FONT, relief="flat", anchor="w", padx=10, pady=4,
            width=13, cursor="hand2", highlightthickness=1,
            highlightbackground=BORDER,
        )
        self._show()

    def set(self, day):
        self.day = day
        self._show()

    def _show(self):
        self.button.config(text=f"📅  {date_text(self.day)}")

    def _open(self):
        if self.popup is not None:
            self._close()
            return
        self.month = self.day.replace(day=1)
        self.popup = tk.Toplevel(self.button)
        self.popup.overrideredirect(True)
        self.popup.configure(bg=BORDER)
        self.popup.geometry(
            f"+{self.button.winfo_rootx()}"
            f"+{self.button.winfo_rooty() + self.button.winfo_height() + 2}"
        )
        self.popup.bind("<Escape>", lambda _e: self._close())
        self.popup.bind("<FocusOut>", self._on_focus_out)
        self.body = tk.Frame(self.popup, bg=PANEL, padx=8, pady=8)
        self.body.pack(padx=1, pady=1)
        self._draw_month()
        self.popup.focus_force()

    def _on_focus_out(self, _event):
        # Close when the user clicks somewhere else, but not when the focus
        # moves to a button inside the calendar
        def check():
            if self.popup is None:
                return
            focus = self.popup.focus_get()
            if focus is None or not str(focus).startswith(str(self.popup)):
                self._close()
        self.popup.after(100, check)

    def _close(self):
        if self.popup is not None:
            self.popup.destroy()
            self.popup = None

    def _move_month(self, step):
        year, month = self.month.year, self.month.month + step
        if month == 0:
            year, month = year - 1, 12
        elif month == 13:
            year, month = year + 1, 1
        self.month = datetime.date(year, month, 1)
        self._draw_month()

    def _draw_month(self):
        for child in self.body.winfo_children():
            child.destroy()

        nav = tk.Frame(self.body, bg=PANEL)
        nav.grid(row=0, column=0, columnspan=7, sticky="ew", pady=(0, 6))
        for text, step, side in (("◀", -1, "left"), ("▶", 1, "right")):
            tk.Button(
                nav, text=text, command=lambda s=step: self._move_month(s),
                bg=PANEL, fg=TEXT, activebackground=ROW_BG,
                activeforeground=ACCENT, relief="flat", font=BUTTON_FONT,
                cursor="hand2", width=3,
            ).pack(side=side)
        tk.Label(
            nav, text=self.month.strftime("%B %Y"), bg=PANEL, fg=TEXT,
            font=BUTTON_FONT,
        ).pack(side="left", expand=True)

        for col, name in enumerate(("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")):
            tk.Label(
                self.body, text=name, bg=PANEL, fg=MUTED, font=LABEL_FONT,
                width=4,
            ).grid(row=1, column=col)

        today = datetime.date.today()
        weeks = calendar.Calendar().monthdatescalendar(
            self.month.year, self.month.month
        )
        for row, week in enumerate(weeks, start=2):
            for col, day in enumerate(week):
                if day == self.day:
                    bg, fg = ACCENT, BG
                elif day.month != self.month.month:
                    bg, fg = PANEL, BORDER
                else:
                    bg, fg = ROW_BG, TEXT
                tk.Button(
                    self.body, text=str(day.day),
                    command=lambda d=day: self._pick(d),
                    bg=bg, fg=fg, activebackground=ACCENT,
                    activeforeground=BG, relief="flat", width=3,
                    font=(LABEL_FONT[0], LABEL_FONT[1],
                          "bold" if day == today else "normal"),
                    cursor="hand2",
                ).grid(row=row, column=col, padx=1, pady=1)

    def _pick(self, day):
        self._close()
        self.set(day)
        if self.on_change:
            self.on_change(day)


# ==================================================
# PAGE
# ==================================================

class ReportPage:
    def __init__(self, root, store, model_number=None, part_number=None):
        """root can be the main Tk window or a Toplevel opened from another
        screen. model_number and part_number pick the filters shown first;
        the date range starts at today."""
        self.root = root
        self.store = store
        self.rows = []
        self.tooltip = None

        root.title("Production Report")
        root.geometry("1250x800")
        root.minsize(1000, 650)
        root.configure(bg=BG)

        self._setup_style()
        self._build_header()
        self._build_filters()
        self._build_cards()
        self._build_chart()
        self._build_table()

        self._load_models()
        if model_number in self.model_combo["values"]:
            self.model_var.set(model_number)
        self._load_parts()
        if part_number in self.part_combo["values"]:
            self.part_var.set(part_number)

        self.show_report()

    # ---------- UI ----------

    def _setup_style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "Report.TCombobox", fieldbackground=ROW_BG, background=PANEL,
            foreground=TEXT, arrowcolor=TEXT, bordercolor=BORDER,
            lightcolor=ROW_BG, darkcolor=ROW_BG, padding=4,
        )
        style.map(
            "Report.TCombobox",
            fieldbackground=[("readonly", ROW_BG)],
            foreground=[("readonly", TEXT)],
            selectbackground=[("readonly", ROW_BG)],
            selectforeground=[("readonly", TEXT)],
        )
        style.configure(
            "Report.Treeview", background=ROW_BG, fieldbackground=ROW_BG,
            foreground=TEXT, bordercolor=BORDER, rowheight=28,
            font=INPUT_FONT,
        )
        style.map(
            "Report.Treeview",
            background=[("selected", ACCENT)],
            foreground=[("selected", BG)],
        )
        style.configure(
            "Report.Treeview.Heading", background=PANEL, foreground=MUTED,
            bordercolor=BORDER, relief="flat", font=BUTTON_FONT, padding=6,
        )
        style.map("Report.Treeview.Heading", background=[("active", PANEL)])
        self.root.option_add("*TCombobox*Listbox.background", ROW_BG)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.root.option_add("*TCombobox*Listbox.selectForeground", BG)
        self.root.option_add("*TCombobox*Listbox.font", INPUT_FONT)

    def _button(self, parent, text, command, bg=PANEL, fg=TEXT):
        return tk.Button(
            parent, text=text, command=command, bg=bg, fg=fg,
            activebackground=bg, activeforeground=fg, font=BUTTON_FONT,
            relief="flat", padx=14, pady=6, cursor="hand2",
            highlightthickness=1, highlightbackground=BORDER,
        )

    def _build_header(self):
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=20, pady=(14, 8))
        tk.Label(
            header, text="Production Report", bg=BG, fg=ACCENT,
            font=TITLE_FONT,
        ).pack(side="left")
        self._button(header, "Export CSV", self.export_csv).pack(
            side="right"
        )
        self.range_label = tk.Label(
            header, text="", bg=BG, fg=MUTED, font=LABEL_FONT
        )
        self.range_label.pack(side="right", padx=(0, 14))

    def _build_filters(self):
        bar = tk.Frame(
            self.root, bg=PANEL, padx=14, pady=10,
            highlightthickness=1, highlightbackground=BORDER,
        )
        bar.pack(fill="x", padx=20)

        # Packed first so it always gets its room
        self._button(bar, "Show Report", self.show_report, ACCENT, BG).pack(
            side="right", anchor="s"
        )

        def field(caption):
            cell = tk.Frame(bar, bg=PANEL)
            cell.pack(side="left", padx=(0, 14))
            tk.Label(
                cell, text=caption, bg=PANEL, fg=MUTED, font=LABEL_FONT
            ).pack(anchor="w")
            return cell

        self.model_var = tk.StringVar(value=ALL_MODELS)
        self.model_combo = ttk.Combobox(
            field("Model"), textvariable=self.model_var, state="readonly",
            width=14, font=INPUT_FONT, style="Report.TCombobox",
            postcommand=self._load_models,
        )
        self.model_combo.pack()
        self.model_combo.bind("<<ComboboxSelected>>", self._on_model_selected)

        self.part_var = tk.StringVar(value=ALL_PARTS)
        self.part_combo = ttk.Combobox(
            field("Part Number"), textvariable=self.part_var,
            state="readonly", width=14, font=INPUT_FONT,
            style="Report.TCombobox", postcommand=self._load_parts,
        )
        self.part_combo.pack()
        self.part_combo.bind(
            "<<ComboboxSelected>>", lambda _e: self.show_report()
        )

        today = datetime.date.today()
        cell = field("Date From")
        self.date_from = DatePicker(cell, today, lambda _d: self.show_report())
        self.date_from.button.pack()
        cell = field("Date To")
        self.date_to = DatePicker(cell, today, lambda _d: self.show_report())
        self.date_to.button.pack()

        # Quick ranges
        quick = field("Quick Range")
        row = tk.Frame(quick, bg=PANEL)
        row.pack()
        for text, days in (("Today", 0), ("7 Days", 6), ("30 Days", 29)):
            tk.Button(
                row, text=text, command=lambda d=days: self._quick_range(d),
                bg=ROW_BG, fg=TEXT, activebackground=ACCENT,
                activeforeground=BG, font=LABEL_FONT, relief="flat",
                padx=8, pady=4, cursor="hand2", highlightthickness=1,
                highlightbackground=BORDER,
            ).pack(side="left", padx=(0, 4))


    def _build_cards(self):
        row = tk.Frame(self.root, bg=BG)
        row.pack(fill="x", padx=20, pady=(12, 0))
        self.card_values = {}
        cards = [
            ("total", "TOTAL QUANTITY", ACCENT),
            ("per_day", "AVERAGE PER DAY", TEXT),
            ("best_day", "BEST DAY", TEXT),
            ("parts", "PART NUMBERS", TEXT),
            ("stations", "STATIONS", TEXT),
        ]
        for index, (key, caption, color) in enumerate(cards):
            row.columnconfigure(index, weight=1, uniform="card")
            card = tk.Frame(
                row, bg=PANEL, padx=16, pady=10,
                highlightthickness=1, highlightbackground=BORDER,
            )
            card.grid(
                row=0, column=index, sticky="nsew",
                padx=(0 if index == 0 else 6, 0),
            )
            tk.Label(
                card, text=caption, bg=PANEL, fg=MUTED,
                font=(LABEL_FONT[0], 9, "bold"),
            ).pack(anchor="w")
            value = tk.Label(
                card, text="-", bg=PANEL, fg=color, font=CARD_VALUE_FONT,
                anchor="w",
            )
            value.pack(anchor="w", fill="x")
            note = tk.Label(
                card, text="", bg=PANEL, fg=MUTED, font=LABEL_FONT,
                anchor="w",
            )
            note.pack(anchor="w", fill="x")
            self.card_values[key] = (value, note)

    def _build_chart(self):
        group = tk.Frame(
            self.root, bg=PANEL, padx=14, pady=8,
            highlightthickness=1, highlightbackground=BORDER,
        )
        group.pack(fill="x", padx=20, pady=(12, 0))
        tk.Label(
            group, text="Quantity per day", bg=PANEL, fg=TEXT,
            font=BUTTON_FONT,
        ).pack(anchor="w")
        self.chart = tk.Canvas(
            group, bg=PANEL, height=CHART_H, highlightthickness=0
        )
        self.chart.pack(fill="x", pady=(4, 0))
        self.chart.bind("<Configure>", lambda _e: self._draw_chart())
        self.chart.bind("<Leave>", lambda _e: self._hide_tooltip())

    def _build_table(self):
        group = tk.Frame(
            self.root, bg=PANEL, padx=14, pady=8,
            highlightthickness=1, highlightbackground=BORDER,
        )
        group.pack(fill="both", expand=True, padx=20, pady=12)

        heading = tk.Frame(group, bg=PANEL)
        heading.pack(fill="x")
        tk.Label(
            heading, text="Details", bg=PANEL, fg=TEXT, font=BUTTON_FONT
        ).pack(side="left")
        self.status = tk.Label(
            heading, text="", bg=PANEL, fg=MUTED, font=LABEL_FONT
        )
        self.status.pack(side="right")

        frame = tk.Frame(group, bg=PANEL)
        frame.pack(fill="both", expand=True, pady=(6, 0))
        columns = [
            ("day", "Date", 110, "w"),
            ("station", "Station ID", 120, "w"),
            ("model", "Model", 150, "w"),
            ("part", "Part Number", 170, "w"),
            ("quantity", "Quantity", 100, "e"),
            ("first", "First", 90, "center"),
            ("last", "Last", 90, "center"),
        ]
        self.table = ttk.Treeview(
            frame, columns=[c[0] for c in columns], show="headings",
            style="Report.Treeview",
        )
        for key, caption, width, anchor in columns:
            self.table.heading(key, text=caption, anchor=anchor)
            self.table.column(key, width=width, anchor=anchor)
        self.table.tag_configure("stripe", background=STRIPE_BG)
        self.table.tag_configure(
            "total", background=PANEL, foreground=OK_COLOR,
            font=BUTTON_FONT,
        )
        scroll = ttk.Scrollbar(
            frame, orient="vertical", command=self.table.yview
        )
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    # ---------- filters ----------

    def _selected_model(self):
        model = self.model_var.get()
        return None if model in ("", ALL_MODELS) else model

    def _selected_part(self):
        part = self.part_var.get()
        return None if part in ("", ALL_PARTS) else part

    def _load_models(self):
        try:
            models = self.store.list_models()
        except StorageError as e:
            self._show_error(e)
            return
        self.model_combo["values"] = [ALL_MODELS] + models

    def _load_parts(self):
        # Only the parts of the selected model
        try:
            parts = self.store.list_parts_of_model(self._selected_model())
        except StorageError as e:
            self._show_error(e)
            return
        self.part_combo["values"] = [ALL_PARTS] + parts
        if self.part_var.get() not in self.part_combo["values"]:
            self.part_var.set(ALL_PARTS)

    def _on_model_selected(self, _event=None):
        self._load_parts()
        self.show_report()

    def _quick_range(self, days):
        today = datetime.date.today()
        self.date_from.set(today - datetime.timedelta(days=days))
        self.date_to.set(today)
        self.show_report()

    # ---------- report ----------

    def show_report(self):
        date_from, date_to = self.date_from.day, self.date_to.day
        if date_from > date_to:
            messagebox.showwarning(
                "Dates", "Date From must not be after Date To.",
                parent=self.root,
            )
            return
        try:
            self.rows = self.store.production_report(
                date_from, date_to, self._selected_model(),
                self._selected_part(),
            )
        except StorageError as e:
            self._show_error(e)
            return

        self.range_label.config(
            text=f"{date_text(date_from)}  to  {date_text(date_to)}"
        )
        self._fill_cards()
        self._draw_chart()
        self._fill_table()

    def _days(self):
        """Every day of the range, oldest first."""
        day, last = self.date_from.day, self.date_to.day
        days = []
        while day <= last:
            days.append(day)
            day += datetime.timedelta(days=1)
        return days

    def _per_day(self):
        totals = {day: 0 for day in self._days()}
        for row in self.rows:
            totals[row["day"]] = totals.get(row["day"], 0) + row["quantity"]
        return totals

    def _fill_cards(self):
        per_day = self._per_day()
        total = sum(per_day.values())
        day_count = len(per_day)
        best_day, best = max(
            per_day.items(), key=lambda item: item[1],
            default=(None, 0),
        )
        values = {
            "total": (f"{total:,}", "parts finished"),
            "per_day": (
                f"{total / day_count:.1f}" if day_count else "0",
                f"over {day_count} day{'s' if day_count != 1 else ''}",
            ),
            "best_day": (
                f"{best:,}" if best else "-",
                date_text(best_day) if best else "no parts finished",
            ),
            "parts": (str(len({r["part_number"] for r in self.rows})), ""),
            "stations": (str(len({r["station_id"] for r in self.rows})), ""),
        }
        for key, (value, note) in values.items():
            self.card_values[key][0].config(text=value)
            self.card_values[key][1].config(text=note)

    def _draw_chart(self):
        chart = self.chart
        chart.delete("all")
        self._hide_tooltip()
        width = chart.winfo_width()
        if width <= 1:
            return
        per_day = self._per_day()
        if not per_day:
            return

        left, right, top, bottom = 44, 10, 12, CHART_H - 26
        plot_w = width - left - right
        plot_h = bottom - top
        peak = max(per_day.values())
        scale_max = max(nice_ceiling(peak), 1)

        # Recessive grid: four lines with their values on the left
        for step in range(5):
            value = scale_max * step / 4
            y = bottom - plot_h * step / 4
            chart.create_line(left, y, width - right, y, fill=GRID_COLOR)
            chart.create_text(
                left - 8, y, text=f"{value:g}", anchor="e", fill=MUTED,
                font=(LABEL_FONT[0], 8),
            )

        days = list(per_day)
        slot = plot_w / len(days)
        bar_w = max(1, min(BAR_WIDTH_MAX, slot - BAR_GAP))
        # Show at most about 12 date labels so they never overlap
        label_every = max(1, round(len(days) / 12))
        for index, day in enumerate(days):
            quantity = per_day[day]
            center = left + slot * (index + 0.5)
            x1, x2 = center - bar_w / 2, center + bar_w / 2
            if quantity:
                y1 = bottom - plot_h * quantity / scale_max
                radius = min(4, bar_w / 2, (bottom - y1) / 2)
                bar = chart.create_polygon(
                    *rounded_top_points(x1, y1, x2, bottom, radius),
                    smooth=True, fill=ACCENT, outline="",
                )
                # Bigger hit target than the bar: the whole day's slot
                hit = chart.create_rectangle(
                    center - slot / 2, top, center + slot / 2, bottom,
                    fill="", outline="",
                )
                for item in (bar, hit):
                    chart.tag_bind(
                        item, "<Enter>",
                        lambda e, d=day, q=quantity, b=bar:
                            self._show_tooltip(e, d, q, b),
                    )
                    chart.tag_bind(
                        item, "<Leave>", lambda _e: self._hide_tooltip()
                    )
            if index % label_every == 0:
                chart.create_text(
                    center, bottom + 12, text=day.strftime("%d %b"),
                    fill=MUTED, font=(LABEL_FONT[0], 8),
                )
        chart.create_line(left, bottom, width - right, bottom, fill=BORDER)

        # Label only the best day, so the chart is not full of numbers
        if peak:
            index = days.index(max(days, key=lambda d: per_day[d]))
            center = left + slot * (index + 0.5)
            chart.create_text(
                center, bottom - plot_h * peak / scale_max - 8,
                text=str(peak), fill=TEXT, font=(LABEL_FONT[0], 9, "bold"),
            )

    def _show_tooltip(self, event, day, quantity, bar):
        self._hide_tooltip()
        self.chart.itemconfigure(bar, fill=TEXT)
        self.tooltip = (bar, self.chart.create_text(
            0, 0, text="", anchor="s"
        ))
        _, text_id = self.tooltip
        self.chart.itemconfigure(
            text_id,
            text=f"{date_text(day)}  ·  {quantity} part"
                 f"{'s' if quantity != 1 else ''}",
            fill=TEXT, font=(LABEL_FONT[0], 9, "bold"),
        )
        x = min(max(event.x, 80), self.chart.winfo_width() - 80)
        self.chart.coords(text_id, x, 14)
        box = self.chart.bbox(text_id)
        background = self.chart.create_rectangle(
            box[0] - 8, box[1] - 4, box[2] + 8, box[3] + 4,
            fill=ROW_BG, outline=BORDER,
        )
        self.chart.tag_raise(text_id)
        self.tooltip = (bar, text_id, background)

    def _hide_tooltip(self):
        if self.tooltip is None:
            return
        bar, *items = self.tooltip
        self.chart.itemconfigure(bar, fill=ACCENT)
        for item in items:
            self.chart.delete(item)
        self.tooltip = None

    def _fill_table(self):
        self.table.delete(*self.table.get_children())
        for index, row in enumerate(self.rows):
            self.table.insert(
                "", "end",
                values=(
                    date_text(row["day"]), row["station_id"],
                    row["model_number"], row["part_number"],
                    f"{row['quantity']:,}",
                    row["first"].strftime("%H:%M"),
                    row["last"].strftime("%H:%M"),
                ),
                tags=("stripe",) if index % 2 else (),
            )
        if self.rows:
            total = sum(row["quantity"] for row in self.rows)
            self.table.insert(
                "", "end",
                values=("TOTAL", "", "", "", f"{total:,}", "", ""),
                tags=("total",),
            )
            self.status.config(
                text=f"{len(self.rows)} row{'s' if len(self.rows) != 1 else ''}",
                fg=MUTED,
            )
        else:
            self.status.config(
                text="No parts finished for these filters", fg=MUTED
            )

    def export_csv(self):
        if not self.rows:
            messagebox.showinfo(
                "Export", "There is nothing to export.", parent=self.root
            )
            return
        name = (f"production_report_{self.date_from.day:%Y%m%d}"
                f"_{self.date_to.day:%Y%m%d}.csv")
        path = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".csv", initialfile=name,
            filetypes=[("CSV files", "*.csv")],
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Date", "Station ID", "Model", "Part Number",
                                 "Quantity", "First", "Last"])
                for row in self.rows:
                    writer.writerow([
                        date_text(row["day"]), row["station_id"],
                        row["model_number"], row["part_number"],
                        row["quantity"], row["first"].strftime("%H:%M"),
                        row["last"].strftime("%H:%M"),
                    ])
        except OSError as e:
            messagebox.showerror("Export failed", str(e), parent=self.root)
            return
        self.status.config(text=f"Saved {path}", fg=OK_COLOR)

    def _show_error(self, error):
        self.status.config(text=str(error).splitlines()[0], fg="#F87171")


def nice_ceiling(value):
    """Smallest of 1, 2, 4, 5 or 10 times a power of ten that is at least
    value, so the chart's grid lines fall on round numbers."""
    if value <= 0:
        return 0
    power = 10 ** (len(str(int(value))) - 1)
    for factor in (1, 2, 4, 5, 10):
        if factor * power >= value:
            return factor * power
    return 10 * power


def rounded_top_points(x1, y1, x2, y2, r):
    """Polygon points for a bar with rounded top corners and a square
    bottom on the baseline, drawn with smooth=True."""
    return [
        x1, y2, x1, y2, x1, y1 + r, x1, y1, x1 + r, y1,
        x2 - r, y1, x2, y1, x2, y1 + r, x2, y2, x2, y2,
    ]


if __name__ == "__main__":
    from settings_page import DB_CONFIG_FILE, MySqlSettingsStore

    window = tk.Tk()
    ReportPage(window, MySqlSettingsStore(DB_CONFIG_FILE))
    window.mainloop()
