"""
FIREFLYT Productions – Projekt-Setup, Fenster
=============================================
Bedienoberflaeche fuer PROJEKT_SETUP.py: Name waehlen, Projektordner waehlen,
pruefen, starten. Die Arbeit macht PROJEKT_SETUP.py als eigener Prozess.
"""

import ctypes
import json
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

SCRIPT = Path(__file__).with_name("PROJEKT_SETUP.py")
SETTINGS = Path(os.environ.get("APPDATA", "")) / "FIREFLYT" / "projekt_setup.json"
EDITORS = ("CONRAD", "FELIX")
EXIT_PROJECT_OPEN, EXIT_PROJECT_EXISTS = 3, 4


def load_settings():
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(data):
    try:
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


class App:
    def __init__(self, root, folder):
        self.root = root
        self.process = None
        self.open_project = "ein Projekt"
        self.lines = queue.Queue()
        settings = load_settings()

        root.title("FIREFLYT Projekt-Setup")
        scale = float(root.tk.call("tk", "scaling")) / 1.333
        root.geometry(f"{int(860 * scale)}x{int(620 * scale)}")
        root.minsize(int(640 * scale), int(420 * scale))
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        top = ttk.Frame(root, padding=12)
        top.pack(fill="x")

        ttk.Label(top, text="Wer bist du?").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.editor = tk.StringVar(value=settings.get("editor", "CONRAD"))
        who = ttk.Frame(top)
        who.grid(row=0, column=1, sticky="w", pady=(0, 8))
        for name in EDITORS:
            ttk.Radiobutton(who, text=name.capitalize(), value=name, variable=self.editor,
                            command=self.check).pack(side="left", padx=(0, 16))

        ttk.Label(top, text="Projektordner").grid(row=1, column=0, sticky="w", padx=(0, 12))
        self.folder = tk.StringVar(value=folder)
        entry = ttk.Entry(top, textvariable=self.folder)
        entry.grid(row=1, column=1, sticky="ew")
        entry.bind("<Return>", lambda _: self.check())
        entry.bind("<FocusOut>", lambda _: self.check())
        ttk.Button(top, text="Auswählen …", command=self.browse).grid(row=1, column=2, padx=(8, 0))
        top.columnconfigure(1, weight=1)

        self.status = tk.StringVar(value="Projektordner wählen. Die Dateien sollten schon kopiert sein.")
        ttk.Label(root, textvariable=self.status, padding=(12, 0), font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.progress = ttk.Progressbar(root, mode="indeterminate")
        self.progress.pack(fill="x", padx=12, pady=8)

        body = ttk.Frame(root, padding=(12, 0))
        body.pack(fill="both", expand=True)
        self.text = tk.Text(body, wrap="word", font=("Consolas", 9), state="disabled")
        scroll = ttk.Scrollbar(body, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.text.tag_configure("warn", foreground="#b45309")
        self.text.tag_configure("stop", foreground="#b91c1c")

        bottom = ttk.Frame(root, padding=12)
        bottom.pack(fill="x")
        self.start_button = ttk.Button(bottom, text="Starten", command=self.start, state="disabled")
        self.start_button.pack(side="right")
        ttk.Button(bottom, text="Schließen", command=self.on_close).pack(side="right", padx=8)

        self.root.after(100, self.pump)
        if folder:
            self.root.after(200, self.check)

    # ---- Ablauf ----------------------------------------------------------

    def browse(self):
        start = self.folder.get().strip() or r"Z:\2026"
        chosen = filedialog.askdirectory(title="Projektordner wählen", initialdir=start)
        if chosen:
            self.folder.set(str(Path(chosen)))
            self.check()

    def check(self):
        if self.process or not self.folder.get().strip():
            return
        self.last_checked = (self.folder.get(), self.editor.get())
        self.start_button.configure(state="disabled")
        self.clear()
        self.run(["--dry-run"], self.after_check)

    def after_check(self, code):
        if code == 0:
            self.status.set("Geprüft. Bereit zum Start.")
            self.start_button.configure(state="normal")
        else:
            self.status.set("Bitte den Hinweis unten beheben.")

    def start(self, extra=None):
        save_settings({"editor": self.editor.get()})
        self.start_button.configure(state="disabled")
        self.clear()
        self.status.set("Läuft …")
        self.run(extra or [], self.after_run)

    def after_run(self, code):
        if code == 0:
            self.status.set("Fertig. Das Projekt ist bereit, Proxys laufen im Hintergrund.")
            messagebox.showinfo("Projekt-Setup",
                                "Fertig. Das Projekt ist bereit.\n\nDer Proxy Generator rechnet im Hintergrund weiter.",
                                parent=self.root)
        elif code == 1:
            self.status.set("Fertig, aber bitte die Hinweise unten lesen.")
            messagebox.showwarning("Projekt-Setup", "Fertig, aber bitte die Hinweise unten lesen.", parent=self.root)
        elif code == EXIT_PROJECT_OPEN:
            if messagebox.askyesno("Projekt offen",
                                   f"In Resolve ist noch offen:\n{self.open_project}\n\n"
                                   "Speichern, schließen und weitermachen?",
                                   parent=self.root):
                self.start(["--close-open"])
                return
            self.status.set("Nicht gestartet. In Resolve ist noch ein Projekt offen.")
        elif code == EXIT_PROJECT_EXISTS:
            if messagebox.askyesno("Projekt existiert schon",
                                   "Dieses Projekt gibt es schon.\n\n"
                                   "Nur Fehlendes ergänzen? Vorhandenes bleibt unverändert.",
                                   parent=self.root):
                self.start(["--resume"])
                return
            self.status.set("Nicht gestartet. Das Projekt existiert schon.")
        else:
            self.status.set("Abgebrochen. Grund steht unten.")
        self.start_button.configure(state="normal")

    # ---- Prozess ---------------------------------------------------------

    def run(self, extra, done):
        args = [sys.executable.replace("pythonw.exe", "python.exe"), "-u", str(SCRIPT),
                self.folder.get().strip(), "--editor", self.editor.get()] + extra
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        self.done = done
        self.progress.start(12)
        self.process = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, text=True,
            encoding="utf-8", errors="replace", bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW)
        threading.Thread(target=self.read_output, args=(self.process,), daemon=True).start()

    def read_output(self, process):
        for line in process.stdout:
            self.lines.put(line.rstrip("\n"))
        self.lines.put(("exit", process.wait()))

    def pump(self):
        try:
            while True:
                item = self.lines.get_nowait()
                if isinstance(item, tuple):
                    self.progress.stop()
                    self.process = None
                    self.done(item[1])
                else:
                    self.append(item)
        except queue.Empty:
            pass
        self.root.after(100, self.pump)

    def append(self, line):
        short = line.split("] ", 1)[-1].strip()
        if short.startswith("[") and "/6]" in short:
            self.status.set(short)
        match = re.search(r"In Resolve ist '(.+)' geoeffnet", line)
        if match:
            self.open_project = match.group(1)
        tag = "stop" if "ABBRUCH" in line else "warn" if short.startswith("!") else ""
        self.text.configure(state="normal")
        self.text.insert("end", line + "\n", tag)
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def on_close(self):
        if self.process and not messagebox.askyesno(
                "Läuft noch",
                "Das Setup läuft noch.\n\nFenster trotzdem schließen? Das Setup läuft dann im "
                "Hintergrund weiter, aber du siehst keine Meldungen mehr.",
                parent=self.root):
            return
        self.root.destroy()


def main():
    # Sonst skaliert Windows das Fenster auf hochaufloesenden Monitoren unscharf hoch
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    try:
        ttk.Style(root).theme_use("vista")
    except tk.TclError:
        pass
    App(root, sys.argv[1] if len(sys.argv) > 1 else "")
    root.mainloop()


if __name__ == "__main__":
    # pythonw hat keine Konsole: ohne das hier stirbt das Programm lautlos
    try:
        main()
    except Exception:
        crash = tk.Tk()
        crash.withdraw()
        messagebox.showerror("Projekt-Setup", "Das Fenster ist abgestürzt:\n\n" + traceback.format_exc())
