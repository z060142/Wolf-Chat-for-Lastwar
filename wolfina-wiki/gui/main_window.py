"""Wolfina-Wiki GUI — Tkinter window for conversation monitoring and wiki processing.

Layout:
  ┌─────────────────────────────────────────────────┐
  │  Conversation Buffer (scrollable)               │
  │  [unprocessed messages in white]                │
  │  [processed messages in grey with ✓ badge]      │
  ├─────────────────────────────────────────────────┤
  │  Trigger Progress                               │
  │  Messages: ██░░░░ 5/20 | Chars: ███░░ 400/2000  │
  │  Time: █░░░░ 45s/300s                           │
  ├─────────────────────────────────────────────────┤
  │  Status Log (scrollable)                        │
  ├─────────────────────────────────────────────────┤
  │  [Process Now]  [Clear Buffer]  [Pause/Resume]  │
  └─────────────────────────────────────────────────┘
"""

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from core.conversation_buffer import conversation_buffer
from core.settings import settings
from core.wiki_processor import ProcessingResult, wiki_processor

POLL_INTERVAL_MS = 500

COLOR_BG = "#1a1a2e"
COLOR_PANEL = "#16213e"
COLOR_ACCENT = "#0f3460"
COLOR_TEXT = "#e0e0e0"
COLOR_TEXT_DIM = "#888888"
COLOR_PROCESSED = "#2d2d2d"
COLOR_UNPROCESSED = "#1e3a5f"
COLOR_TRIGGER_BAR = "#0f3460"
COLOR_TRIGGER_FILL = "#4a9eff"
COLOR_TRIGGER_DONE = "#2ecc71"
COLOR_STATUS_OK = "#2ecc71"
COLOR_STATUS_ERR = "#e74c3c"
COLOR_STATUS_INFO = "#3498db"
COLOR_BUTTON = "#0f3460"
COLOR_BUTTON_ACTIVE = "#1a5276"
COLOR_PAUSE = "#e67e22"
COLOR_PAUSE_ACTIVE = "#d35400"


class WikiMainWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self._paused = False
        self._last_message_count = 0
        self._setup_window()
        self._build_ui()
        self._register_processor_callback()
        self._schedule_poll()

    # ------------------------------------------------------------------
    # Window setup
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        self.root.title("Wolfina Wiki — Conversation Monitor")
        self.root.geometry("750x700")
        self.root.minsize(600, 500)
        self.root.configure(bg=COLOR_BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=3)
        self.root.rowconfigure(1, weight=0)
        self.root.rowconfigure(2, weight=1)
        self.root.rowconfigure(3, weight=0)

        # ── Section 1: Conversation buffer ──────────────────────────────
        buf_frame = tk.Frame(self.root, bg=COLOR_BG, padx=6, pady=4)
        buf_frame.grid(row=0, column=0, sticky="nsew")
        buf_frame.columnconfigure(0, weight=1)
        buf_frame.rowconfigure(1, weight=1)

        tk.Label(
            buf_frame, text="Conversation Buffer", bg=COLOR_BG,
            fg=COLOR_TEXT, font=("Segoe UI", 10, "bold"), anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self._msg_listbox = tk.Listbox(
            buf_frame,
            bg=COLOR_PANEL, fg=COLOR_TEXT,
            selectbackground=COLOR_ACCENT, selectforeground=COLOR_TEXT,
            font=("Consolas", 9),
            activestyle="none",
            bd=0, highlightthickness=1, highlightcolor=COLOR_ACCENT,
            relief="flat",
        )
        self._msg_listbox.grid(row=1, column=0, sticky="nsew")

        msg_scroll = tk.Scrollbar(buf_frame, orient="vertical", command=self._msg_listbox.yview)
        msg_scroll.grid(row=1, column=1, sticky="ns")
        self._msg_listbox.configure(yscrollcommand=msg_scroll.set)

        # ── Section 2: Trigger progress ─────────────────────────────────
        trig_frame = tk.Frame(self.root, bg=COLOR_ACCENT, padx=10, pady=8)
        trig_frame.grid(row=1, column=0, sticky="ew")
        trig_frame.columnconfigure(1, weight=1)

        labels = ["Messages", "Chars", "Time"]
        self._progress_bars: list[ttk.Progressbar] = []
        self._progress_labels: list[tk.Label] = []

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Wiki.Horizontal.TProgressbar",
            troughcolor=COLOR_TRIGGER_BAR,
            background=COLOR_TRIGGER_FILL,
            darkcolor=COLOR_TRIGGER_FILL,
            lightcolor=COLOR_TRIGGER_FILL,
            bordercolor=COLOR_ACCENT,
        )
        style.configure(
            "WikiDone.Horizontal.TProgressbar",
            troughcolor=COLOR_TRIGGER_BAR,
            background=COLOR_TRIGGER_DONE,
            darkcolor=COLOR_TRIGGER_DONE,
            lightcolor=COLOR_TRIGGER_DONE,
            bordercolor=COLOR_ACCENT,
        )

        for i, label in enumerate(labels):
            tk.Label(
                trig_frame, text=label, bg=COLOR_ACCENT, fg=COLOR_TEXT,
                font=("Segoe UI", 9), width=9, anchor="e",
            ).grid(row=i, column=0, padx=(0, 6), pady=2, sticky="e")

            pb = ttk.Progressbar(
                trig_frame, orient="horizontal", length=200,
                mode="determinate", style="Wiki.Horizontal.TProgressbar",
            )
            pb.grid(row=i, column=1, sticky="ew", pady=2)
            self._progress_bars.append(pb)

            lbl = tk.Label(
                trig_frame, text="0 / ?", bg=COLOR_ACCENT, fg=COLOR_TEXT,
                font=("Consolas", 9), width=18, anchor="w",
            )
            lbl.grid(row=i, column=2, padx=(8, 0), pady=2, sticky="w")
            self._progress_labels.append(lbl)

        # ── Section 3: Status log ────────────────────────────────────────
        log_frame = tk.Frame(self.root, bg=COLOR_BG, padx=6, pady=4)
        log_frame.grid(row=2, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)

        tk.Label(
            log_frame, text="Processing Log", bg=COLOR_BG,
            fg=COLOR_TEXT, font=("Segoe UI", 10, "bold"), anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self._log_text = tk.Text(
            log_frame, bg=COLOR_PANEL, fg=COLOR_TEXT,
            font=("Consolas", 8),
            state="disabled", wrap="word",
            bd=0, highlightthickness=1, highlightcolor=COLOR_ACCENT,
            relief="flat", height=6,
        )
        self._log_text.grid(row=1, column=0, sticky="nsew")

        log_scroll = tk.Scrollbar(log_frame, orient="vertical", command=self._log_text.yview)
        log_scroll.grid(row=1, column=1, sticky="ns")
        self._log_text.configure(yscrollcommand=log_scroll.set)

        self._log_text.tag_configure("ok", foreground=COLOR_STATUS_OK)
        self._log_text.tag_configure("err", foreground=COLOR_STATUS_ERR)
        self._log_text.tag_configure("info", foreground=COLOR_STATUS_INFO)

        # ── Section 4: Buttons ───────────────────────────────────────────
        btn_frame = tk.Frame(self.root, bg=COLOR_BG, padx=6, pady=6)
        btn_frame.grid(row=3, column=0, sticky="ew")

        self._btn_process = tk.Button(
            btn_frame, text="Process Now",
            bg=COLOR_BUTTON, fg=COLOR_TEXT, activebackground=COLOR_BUTTON_ACTIVE,
            activeforeground=COLOR_TEXT, relief="flat", padx=14, pady=6,
            font=("Segoe UI", 10, "bold"),
            command=self._on_process_now,
        )
        self._btn_process.pack(side="left", padx=(0, 6))

        self._btn_clear = tk.Button(
            btn_frame, text="Clear Buffer",
            bg=COLOR_BUTTON, fg=COLOR_TEXT, activebackground=COLOR_BUTTON_ACTIVE,
            activeforeground=COLOR_TEXT, relief="flat", padx=14, pady=6,
            font=("Segoe UI", 10),
            command=self._on_clear,
        )
        self._btn_clear.pack(side="left", padx=(0, 6))

        self._btn_pause = tk.Button(
            btn_frame, text="Pause",
            bg=COLOR_PAUSE, fg=COLOR_TEXT, activebackground=COLOR_PAUSE_ACTIVE,
            activeforeground=COLOR_TEXT, relief="flat", padx=14, pady=6,
            font=("Segoe UI", 10),
            command=self._on_pause_toggle,
        )
        self._btn_pause.pack(side="left")

        # Processor status indicator
        self._status_var = tk.StringVar(value="Idle")
        tk.Label(
            btn_frame, textvariable=self._status_var,
            bg=COLOR_BG, fg=COLOR_TEXT_DIM, font=("Segoe UI", 9),
        ).pack(side="right", padx=6)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _register_processor_callback(self) -> None:
        wiki_processor.add_completion_callback(self._on_processing_complete)

    def _on_process_now(self) -> None:
        if wiki_processor.is_running:
            self._append_log("Already processing...", "info")
            return
        messages = conversation_buffer.get_pending_messages()
        if not messages:
            self._append_log("No pending messages to process.", "info")
            return
        self._status_var.set("Processing...")
        self._btn_process.config(state="disabled")
        wiki_processor.trigger_async(messages)

    def _on_clear(self) -> None:
        conversation_buffer.clear_all()
        self._append_log("Buffer cleared.", "info")

    def _on_pause_toggle(self) -> None:
        self._paused = not self._paused
        conversation_buffer.set_paused(self._paused)
        if self._paused:
            self._btn_pause.config(text="Resume", bg=COLOR_STATUS_ERR)
            self._append_log("Paused — auto-processing suspended.", "info")
        else:
            self._btn_pause.config(text="Pause", bg=COLOR_PAUSE)
            self._append_log("Resumed — auto-processing active.", "info")

    def _on_processing_complete(self, result: ProcessingResult) -> None:
        # Called from background thread — schedule on main thread
        self.root.after(0, lambda: self._handle_result(result))

    def _handle_result(self, result: ProcessingResult) -> None:
        for line in result.log_lines:
            tag = "err" if "error" in line.lower() or "fail" in line.lower() else "ok"
            self._append_log(line, tag)
        for err in result.errors:
            self._append_log(f"ERROR: {err}", "err")
        self._status_var.set("Idle")
        self._btn_process.config(state="normal")

    def _on_close(self) -> None:
        self.root.destroy()

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------

    def _schedule_poll(self) -> None:
        self.root.after(POLL_INTERVAL_MS, self._poll)

    def _poll(self) -> None:
        try:
            self._refresh_messages()
            self._refresh_progress()
            self._check_auto_trigger()
            self._refresh_processor_status()
        except Exception:
            pass
        self._schedule_poll()

    def _refresh_messages(self) -> None:
        all_msgs = conversation_buffer.get_all_messages()
        if len(all_msgs) == self._last_message_count:
            # Re-check for processed state changes
            pass
        self._last_message_count = len(all_msgs)

        self._msg_listbox.delete(0, tk.END)
        for msg in all_msgs:
            ts = msg.timestamp.strftime("%H:%M:%S")
            prefix = "✓ " if msg.processed else "   "
            text = f"{prefix}[{ts}] {msg.speaker}: {msg.content[:120]}"
            self._msg_listbox.insert(tk.END, text)
            idx = self._msg_listbox.size() - 1
            if msg.processed:
                self._msg_listbox.itemconfig(idx, fg=COLOR_TEXT_DIM, bg=COLOR_PROCESSED)
            else:
                self._msg_listbox.itemconfig(idx, fg=COLOR_TEXT, bg=COLOR_UNPROCESSED)

        # Auto-scroll to bottom if new messages
        if all_msgs:
            self._msg_listbox.see(tk.END)

    def _refresh_progress(self) -> None:
        stats = conversation_buffer.get_stats()
        thresholds = [
            (stats["pending_count"], settings.trigger_msg_count, "msgs"),
            (stats["total_chars"], settings.trigger_char_count, "chars"),
            (int(stats["elapsed_sec"]), settings.trigger_duration_sec, "s"),
        ]
        for i, (current, maximum, unit) in enumerate(thresholds):
            pct = min(100, int(current / maximum * 100)) if maximum > 0 else 0
            self._progress_bars[i]["value"] = pct
            style = "WikiDone.Horizontal.TProgressbar" if pct >= 100 else "Wiki.Horizontal.TProgressbar"
            self._progress_bars[i].configure(style=style)
            self._progress_labels[i].config(text=f"{current} / {maximum} {unit}")

    def _check_auto_trigger(self) -> None:
        if not wiki_processor.is_running and conversation_buffer.should_trigger():
            self._status_var.set("Processing...")
            self._btn_process.config(state="disabled")
            wiki_processor.trigger_async()
            self._append_log("Auto-triggered processing.", "info")

    def _refresh_processor_status(self) -> None:
        if wiki_processor.is_running:
            self._status_var.set("Processing...")
            self._btn_process.config(state="disabled")
        else:
            if self._status_var.get() == "Processing...":
                self._status_var.set("Idle")
                self._btn_process.config(state="normal")

    # ------------------------------------------------------------------
    # Log helper
    # ------------------------------------------------------------------

    def _append_log(self, text: str, tag: str = "info") -> None:
        self._log_text.config(state="normal")
        self._log_text.insert(tk.END, text + "\n", tag)
        self._log_text.see(tk.END)
        self._log_text.config(state="disabled")


def launch_gui() -> None:
    """Create and run the Tkinter main window. Blocks until window is closed."""
    root = tk.Tk()
    WikiMainWindow(root)
    root.mainloop()
