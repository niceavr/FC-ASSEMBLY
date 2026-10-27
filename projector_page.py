"""
Projector Page - BenQ MX528 power control over RS232

Pick the COM port the projector's RS232 cable is plugged into, connect, then
turn the projector on or off or ask for its power state. Commands use the
BenQ RS232 protocol (for example "*pow=on#"). The chosen port and baud rate
are saved to projector_config.ini and selected again next time.

Projector side: the baud rate set here must match the projector menu
(SYSTEM SETUP: Advanced > Baud Rate). Use a null-modem (crossed) RS232
cable to the projector's 9-pin RS232 port. After power off the projector
cools down for about 90 seconds and ignores all commands until it is done.
"""

import configparser
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

import serial
from serial.tools import list_ports

from settings_page import (
    ACCENT,
    BG,
    BORDER,
    BUTTON_FONT,
    ERROR,
    INPUT_FONT,
    LABEL_FONT,
    MUTED,
    PANEL,
    ROW_BG,
    TEXT,
    TITLE_FONT,
)

# ==================================================
# CONSTANTS
# ==================================================

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTOR_CONFIG_FILE = os.path.join(APP_DIR, "projector_config.ini")

PROJECTOR_NAME = "BenQ MX528"

BAUD_RATES = ["2400", "4800", "9600", "14400", "19200", "38400", "57600",
              "115200"]
DEFAULT_BAUD = "115200"

READ_TIMEOUT = 2.0   # seconds to wait for the projector's reply
POLL_MS = 100        # how often the window checks for replies

# BenQ RS232 commands. Each one is sent as "\r<command>\r".
CMD_POWER_ON = "*pow=on#"
CMD_POWER_OFF = "*pow=off#"
CMD_POWER_STATUS = "*pow=?#"

ON_COLOR = "#00E676"
OFF_COLOR = "#DC2626"
UNKNOWN_COLOR = MUTED

# Replies the projector sends when it cannot run a command, written in
# upper case without spaces (e.g. "*Block item#" becomes "*BLOCKITEM#")
ERROR_REPLIES = {
    "*BLOCKITEM#": "Projector is busy (warming up or cooling down). "
                   "Wait about 90 seconds and try again.",
    "*ILLEGALFORMAT#": "Projector did not understand the command.",
    "*UNSUPPORTEDITEM#": "Projector does not support this command.",
}


class ProjectorError(Exception):
    pass


# ==================================================
# RS232 CONNECTION
# ==================================================

class BenQProjector:
    """Sends BenQ RS232 commands and reads the replies. Blocking; the page
    calls it from a worker thread."""

    def __init__(self):
        self.port = None
        self.lock = threading.Lock()

    @property
    def connected(self):
        return self.port is not None and self.port.is_open

    def open(self, port_name, baud):
        self.close()
        try:
            self.port = serial.Serial(
                port_name,
                baudrate=int(baud),
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1,
                write_timeout=1,
            )
        except (serial.SerialException, ValueError) as e:
            self.port = None
            raise ProjectorError(f"Could not open {port_name}: {e}") from e

    def close(self):
        if self.port is not None:
            try:
                self.port.close()
            except serial.SerialException:
                pass
        self.port = None

    def send(self, command):
        """Send one command and return the projector's reply lines."""
        with self.lock:
            if not self.connected:
                raise ProjectorError("Not connected to the projector.")
            try:
                self.port.reset_input_buffer()
                self.port.write(f"\r{command}\r".encode("ascii"))
                self.port.flush()
                return self._read_reply(command)
            except serial.SerialException as e:
                # The port is unusable now (cable pulled, adapter removed)
                self.close()
                raise ProjectorError(f"Serial port error: {e}") from e

    def _read_reply(self, command):
        # The projector echoes the command, then answers on its own line,
        # e.g. "*pow=?#" followed by "*POW=ON#". Only lines that have
        # arrived in full count, so half an echo is not taken as the answer.
        data = b""
        deadline = time.monotonic() + READ_TIMEOUT
        while time.monotonic() < deadline:
            data += self.port.read(64)
            line_end = max(data.rfind(b"\r"), data.rfind(b"\n"))
            lines = self._lines(data[:line_end + 1])
            if any(self._is_answer(line, command) for line in lines):
                break

        lines = self._lines(data)
        if not lines:
            raise ProjectorError(
                "No reply from the projector. If it was just turned off, it "
                "ignores commands while cooling (about 90 seconds). "
                "Otherwise check the cable, the COM port and that the baud "
                "rate matches the projector menu."
            )
        return lines

    @staticmethod
    def _lines(data):
        text = data.decode("ascii", errors="replace")
        return [
            line.strip().strip(">").strip()
            for line in text.replace("\n", "\r").split("\r")
            if line.strip().strip(">").strip()
        ]

    @staticmethod
    def _is_answer(line, command):
        # The echo is the command exactly as sent (lower case); the answer
        # is upper case, e.g. "*POW=ON#"
        return line != command


def parse_power(lines):
    """Return "ON", "OFF" or None from the reply lines, or raise
    ProjectorError for an error reply."""
    for line in lines:
        upper = line.upper().replace(" ", "")
        if upper in ERROR_REPLIES:
            raise ProjectorError(ERROR_REPLIES[upper])
        if upper == "*POW=ON#":
            return "ON"
        if upper == "*POW=OFF#":
            return "OFF"
    return None


# ==================================================
# SAVED PORT SETTINGS
# ==================================================

def load_port_settings():
    config = configparser.ConfigParser()
    config.read(PROJECTOR_CONFIG_FILE)
    section = config["projector"] if config.has_section("projector") else {}
    return section.get("port", ""), section.get("baud", DEFAULT_BAUD)


def save_port_settings(port, baud):
    config = configparser.ConfigParser()
    config["projector"] = {"port": port, "baud": baud}
    try:
        with open(PROJECTOR_CONFIG_FILE, "w") as f:
            config.write(f)
    except OSError:
        # Not being able to remember the port is not worth stopping for
        pass


# ==================================================
# PAGE
# ==================================================

class ProjectorPage:
    def __init__(self, root):
        """root can be the main Tk window or a Toplevel opened from another
        screen. The serial port is closed when the window is closed."""
        self.root = root
        self.projector = BenQProjector()
        self.replies = queue.Queue()
        self.busy = False
        self.poll_job = None

        root.title(f"Projector - {PROJECTOR_NAME} (RS232)")
        root.geometry("640x600")
        root.minsize(600, 560)
        root.configure(bg=BG)

        self._setup_style()
        self._build_header()
        self._build_connection()
        self._build_power()
        self._build_log()
        self._build_status_bar()

        self.refresh_ports()
        self._update_buttons()
        self.poll_job = root.after(POLL_MS, self._poll_replies)
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

    def _button(self, parent, text, bg, fg, command):
        return tk.Button(
            parent, text=text, command=command, bg=bg, fg=fg,
            activebackground=bg, activeforeground=fg, font=BUTTON_FONT,
            relief="flat", padx=18, pady=7, cursor="hand2",
            highlightthickness=1, highlightbackground=BORDER,
        )

    def _build_header(self):
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=20, pady=(14, 8))

        tk.Label(
            header, text="Projector", bg=BG, fg=ACCENT, font=TITLE_FONT
        ).pack(side="left")
        tk.Label(
            header, text=f"{PROJECTOR_NAME}  ·  RS232", bg=BG, fg=MUTED,
            font=LABEL_FONT,
        ).pack(side="left", padx=(12, 0), pady=(10, 0))

    def _build_connection(self):
        panel = tk.LabelFrame(
            self.root, text=" Connection ", bg=PANEL, fg=ACCENT,
            font=("Segoe UI", 12, "bold"), relief="groove", bd=2,
            padx=16, pady=12,
        )
        panel.pack(fill="x", padx=20)
        panel.columnconfigure(0, weight=1)

        saved_port, saved_baud = load_port_settings()
        self.saved_port = saved_port

        tk.Label(
            panel, text="COM Port", bg=PANEL, fg=MUTED, font=LABEL_FONT
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            panel, text="Baud Rate", bg=PANEL, fg=MUTED, font=LABEL_FONT
        ).grid(row=0, column=2, sticky="w", padx=(12, 0))

        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(
            panel, textvariable=self.port_var, state="readonly",
            font=INPUT_FONT, style="Dark.TCombobox",
        )
        self.port_combo.grid(row=1, column=0, sticky="ew")

        self.refresh_button = tk.Button(
            panel, text="⟳", command=self.refresh_ports, bg=ROW_BG, fg=TEXT,
            activebackground=BORDER, activeforeground=TEXT, relief="flat",
            font=BUTTON_FONT, padx=10, cursor="hand2",
            highlightthickness=1, highlightbackground=BORDER,
        )
        self.refresh_button.grid(row=1, column=1, padx=(6, 0), sticky="ns")

        self.baud_var = tk.StringVar(
            value=saved_baud if saved_baud in BAUD_RATES else DEFAULT_BAUD
        )
        self.baud_combo = ttk.Combobox(
            panel, textvariable=self.baud_var, values=BAUD_RATES,
            state="readonly", width=10, font=INPUT_FONT,
            style="Dark.TCombobox",
        )
        self.baud_combo.grid(row=1, column=2, padx=(12, 0))

        self.connect_button = self._button(
            panel, "Connect", ACCENT, BG, self.toggle_connection
        )
        self.connect_button.grid(row=1, column=3, padx=(12, 0))

        self.connection_label = tk.Label(
            panel, text="", bg=PANEL, fg=MUTED, font=LABEL_FONT, anchor="w"
        )
        self.connection_label.grid(
            row=2, column=0, columnspan=4, sticky="w", pady=(8, 0)
        )

        # Wiring for the projector's 9-pin RS232 port (crossed cable)
        tk.Label(
            panel,
            text="Cable: 9-pin RS232 null-modem (crossed). "
                 "PC pin 2 → projector pin 3, PC pin 3 → projector pin 2, "
                 "pin 5 → pin 5 (ground).",
            bg=PANEL, fg=MUTED, font=LABEL_FONT, anchor="w", justify="left",
            wraplength=560,
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(4, 0))

    def _build_power(self):
        panel = tk.LabelFrame(
            self.root, text=" Power ", bg=PANEL, fg=ACCENT,
            font=("Segoe UI", 12, "bold"), relief="groove", bd=2,
            padx=16, pady=12,
        )
        panel.pack(fill="x", padx=20, pady=(12, 0))

        # Power state lamp
        state = tk.Frame(panel, bg=PANEL)
        state.pack(fill="x")
        self.lamp = tk.Canvas(
            state, width=22, height=22, bg=PANEL, highlightthickness=0
        )
        self.lamp.create_oval(3, 3, 19, 19, fill=UNKNOWN_COLOR,
                              outline=BORDER, tags="lamp")
        self.lamp.pack(side="left")
        self.power_label = tk.Label(
            state, text="Power: unknown", bg=PANEL, fg=TEXT,
            font=("Segoe UI", 12, "bold"),
        )
        self.power_label.pack(side="left", padx=(8, 0))

        buttons = tk.Frame(panel, bg=PANEL)
        buttons.pack(fill="x", pady=(12, 0))
        self.on_button = self._button(
            buttons, "⏻  Power ON", ON_COLOR, BG, self.power_on
        )
        self.on_button.pack(side="left", padx=(0, 10))
        self.off_button = self._button(
            buttons, "⏻  Power OFF", OFF_COLOR, TEXT, self.power_off
        )
        self.off_button.pack(side="left", padx=(0, 10))
        self.status_button = self._button(
            buttons, "Check Status", ROW_BG, TEXT, self.check_status
        )
        self.status_button.pack(side="left")

    def _build_log(self):
        panel = tk.LabelFrame(
            self.root, text=" Communication Log ", bg=PANEL, fg=ACCENT,
            font=("Segoe UI", 12, "bold"), relief="groove", bd=2,
            padx=10, pady=8,
        )
        panel.pack(fill="both", expand=True, padx=20, pady=(12, 0))

        self.log = tk.Text(
            panel, height=8, bg=ROW_BG, fg=TEXT, font=("Consolas", 10),
            relief="flat", highlightthickness=1, highlightbackground=BORDER,
            state="disabled", wrap="word",
        )
        self.log.pack(fill="both", expand=True)
        self.log.tag_configure("sent", foreground=ACCENT)
        self.log.tag_configure("received", foreground=ON_COLOR)
        self.log.tag_configure("error", foreground=ERROR)
        self.log.tag_configure("info", foreground=MUTED)

    def _build_status_bar(self):
        self.status = tk.Label(
            self.root, text="", bg=BG, fg=MUTED, font=LABEL_FONT, anchor="w",
            justify="left",
        )
        self.status.pack(fill="x", padx=20, pady=8)
        # Wrap long messages to the window width instead of cutting them off
        self.status.bind(
            "<Configure>",
            lambda e: self.status.config(wraplength=max(e.width - 4, 100)),
        )

    def _set_status(self, text, error=False):
        self.status.config(text=text, fg=ERROR if error else MUTED)

    def _write_log(self, text, tag):
        stamp = time.strftime("%H:%M:%S")
        self.log.config(state="normal")
        self.log.insert("end", f"{stamp}  {text}\n", tag)
        self.log.see("end")
        self.log.config(state="disabled")

    def _show_power(self, power):
        color = {"ON": ON_COLOR, "OFF": OFF_COLOR}.get(power, UNKNOWN_COLOR)
        self.lamp.itemconfig("lamp", fill=color)
        self.power_label.config(text=f"Power: {(power or 'unknown').lower()}")

    def _update_buttons(self):
        connected = self.projector.connected
        idle = not self.busy

        power_state = "normal" if connected and idle else "disabled"
        for button in (self.on_button, self.off_button, self.status_button):
            button.config(state=power_state)

        setup_state = "disabled" if connected else "normal"
        self.refresh_button.config(state=setup_state)
        self.port_combo.config(
            state="disabled" if connected else "readonly"
        )
        self.baud_combo.config(
            state="disabled" if connected else "readonly"
        )
        self.connect_button.config(
            text="Disconnect" if connected else "Connect",
            bg=PANEL if connected else ACCENT,
            fg=TEXT if connected else BG,
            activebackground=PANEL if connected else ACCENT,
            activeforeground=TEXT if connected else BG,
            state="normal" if idle else "disabled",
        )

        if connected:
            self.connection_label.config(
                text=f"Connected on {self.projector.port.port} at "
                     f"{self.projector.port.baudrate} baud",
                fg=ON_COLOR,
            )
        else:
            self.connection_label.config(text="Not connected", fg=MUTED)

    # ---------- connection ----------

    def refresh_ports(self):
        ports = sorted(list_ports.comports(), key=lambda p: p.device)
        self.port_names = {
            f"{p.device} - {p.description}"
            if p.description and p.description != "n/a" else p.device: p.device
            for p in ports
        }
        choices = list(self.port_names)
        self.port_combo.config(values=choices)

        # Keep the current choice, else the saved port, else the first one
        current = self.port_names.get(self.port_var.get())
        wanted = current or self.saved_port
        match = next(
            (c for c, device in self.port_names.items() if device == wanted),
            None,
        )
        self.port_var.set(match or (choices[0] if choices else ""))

        if choices:
            self._set_status(f"Found {len(choices)} COM port(s).")
        else:
            self._set_status(
                "No COM ports found. Plug in the RS232 / USB-serial cable "
                "and press ⟳.", error=True,
            )

    def toggle_connection(self):
        if self.projector.connected:
            self.projector.close()
            self._show_power(None)
            self._write_log("Disconnected", "info")
            self._set_status("Disconnected.")
            self._update_buttons()
            return

        device = self.port_names.get(self.port_var.get())
        if not device:
            messagebox.showwarning(
                "Projector", "Select a COM port first.", parent=self.root
            )
            return

        baud = self.baud_var.get()
        try:
            self.projector.open(device, baud)
        except ProjectorError as e:
            self._write_log(str(e), "error")
            self._set_status(str(e), error=True)
            self._update_buttons()
            return

        self.saved_port = device
        save_port_settings(device, baud)
        self._write_log(f"Connected to {device} at {baud} baud", "info")
        self._update_buttons()

        # Show the current power state straight away
        self.check_status()

    # ---------- commands ----------

    def power_on(self):
        self._run(CMD_POWER_ON, "Turning the projector on...")

    def power_off(self):
        if not messagebox.askyesno(
            "Projector", "Turn the projector off?", parent=self.root
        ):
            return
        self._run(CMD_POWER_OFF, "Turning the projector off...")

    def check_status(self):
        self._run(CMD_POWER_STATUS, "Checking the power state...")

    def _run(self, command, message):
        if self.busy or not self.projector.connected:
            return
        self.busy = True
        self._update_buttons()
        self._set_status(message)
        self._write_log(f"→ {command}", "sent")

        def work():
            try:
                lines = self.projector.send(command)
                self.replies.put((command, lines, None))
            except ProjectorError as e:
                self.replies.put((command, None, e))
            except Exception as e:
                # Always report back, or the buttons stay disabled
                self.replies.put((command, None, ProjectorError(
                    f"Unexpected error: {e}"
                )))

        # Serial reads block, so keep them off the Tk thread
        threading.Thread(target=work, daemon=True).start()

    def _poll_replies(self):
        try:
            while True:
                self._handle_reply(*self.replies.get_nowait())
        except queue.Empty:
            pass
        self.poll_job = self.root.after(POLL_MS, self._poll_replies)

    def _handle_reply(self, command, lines, error):
        self.busy = False

        if error is None:
            for line in lines:
                self._write_log(f"← {line}", "received")
            try:
                power = parse_power(lines)
            except ProjectorError as e:
                error = e
            else:
                if power:
                    self._show_power(power)
                    self._set_status(f"Projector power is {power}.")
                elif command == CMD_POWER_STATUS:
                    self._set_status("Unexpected reply from the projector.",
                                     error=True)
                else:
                    self._set_status("Command sent.")

        if error is not None:
            self._write_log(str(error), "error")
            self._set_status(str(error), error=True)
            # The port may have gone away (cable pulled, adapter removed)
            if not self.projector.connected:
                self._show_power(None)

        self._update_buttons()

    def _on_destroy(self, event):
        # <Destroy> also fires for every widget inside the window
        if event.widget is not self.root:
            return
        if self.poll_job is not None:
            self.root.after_cancel(self.poll_job)
            self.poll_job = None
        self.projector.close()


if __name__ == "__main__":
    root = tk.Tk()
    ProjectorPage(root)
    root.mainloop()
