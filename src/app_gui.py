import contextlib
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

from github_pipeline import parse_wb_links, read_links as read_wb_links
from ozon_playwright_fetch import download_pages, read_links as read_oz_links
from paired_price_export import _write_rows, _zip_pairs, guess_chrome_browser, guess_chrome_profile


def _bootstrap_playwright_path() -> None:
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return
    bases = []
    if getattr(sys, "frozen", False):
        bases.append(Path(getattr(sys, "_MEIPASS", Path.cwd())))  # type: ignore[attr-defined]
        bases.append(Path(sys.executable).resolve().parent)
    bases.append(Path(__file__).resolve().parent)
    for base in bases:
        for name in (".local-browsers", "ms-playwright"):
            candidate = base / name
            if candidate.exists():
                os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(candidate)
                return


_bootstrap_playwright_path()


def ensure_chromium_available() -> None:
    from playwright.sync_api import sync_playwright

    def try_launch() -> None:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()

    try:
        try_launch()
        return
    except Exception as exc:  # noqa: BLE001
        if "executable" not in str(exc).lower():
            raise

    if getattr(sys, "frozen", False):
        raise RuntimeError(
            "Chromium не найден в сборке. Пересоберите exe или запустите python-версию и выполните playwright install chromium."
        )

    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    try_launch()


def parse_links_text(text: str) -> List[str]:
    links: List[str] = []
    for line in text.splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            links.append(value)
    return links


class QueueWriter:
    def __init__(self, target: "queue.Queue[tuple[str, object]]"):
        self.target = target

    def write(self, data: str) -> None:
        if not data:
            return
        for line in data.splitlines():
            if line.strip():
                self.target.put(("log", line))

    def flush(self) -> None:
        return


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)
        self.scrollable_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        window = canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.canvas = canvas
        self.window = window


class ParserApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Ozon + WB parser")
        self.geometry("1200x900")
        self.resizable(True, True)
        self._configure_style()

        self.events: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self.progress_total = 1

        self.oz_path = tk.StringVar(value=str(Path("data/links/links_oz.txt")))
        self.wb_path = tk.StringVar(value=str(Path("data/links/links_wb.txt")))
        self.profile_dir = tk.StringVar(value=str(guess_chrome_profile() or Path("output/playwright_profile")))
        self.browser_path = tk.StringVar(value=str(guess_chrome_browser() or ""))
        self.output_path = tk.StringVar(
            value=str(Path("output") / f"paired_prices_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        )
        self.skip_html = tk.BooleanVar(value=True)
        self.headless = tk.BooleanVar(value=False)

        self.oz_text_box: tk.Text
        self.wb_text_box: tk.Text
        self.log_box: tk.Text

        self._build_ui()
        self.after(100, self._drain_events)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        base_font = ("Segoe UI", 10)
        style.configure(".", font=base_font, background="#f7f9fb", foreground="#1f2933")
        style.configure("TFrame", background="#f7f9fb")
        style.configure("Card.TFrame", background="#ffffff", relief="solid", borderwidth=0)
        style.configure("Card.TLabelframe", background="#ffffff", foreground="#1f2933", borderwidth=1, relief="solid")
        style.configure("Card.TLabelframe.Label", background="#ffffff", foreground="#0f172a", font=("Segoe UI Semibold", 10))
        style.configure("TLabel", background="#f7f9fb", foreground="#1f2933")
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 16), foreground="#0f172a", background="#ffffff")
        style.configure("Sub.TLabel", font=("Segoe UI", 10), foreground="#334155", background="#ffffff")
        style.configure("TButton", padding=10, font=("Segoe UI Semibold", 10))
        style.configure("Accent.TButton", background="#e5e7eb", foreground="#111827")
        style.configure("Primary.TButton", background="#2563eb", foreground="#ffffff")
        style.map("Primary.TButton", background=[("active", "#1d4ed8")])
        style.map("Accent.TButton", background=[("active", "#d1d5db")])
        style.configure("TCheckbutton", background="#f7f9fb", foreground="#1f2933")
        style.configure("TLabelframe", background="#f7f9fb", foreground="#1f2933")
        style.configure("TLabelframe.Label", background="#f7f9fb", foreground="#0f172a")
        self.configure(bg="#f7f9fb")

    def _enable_paste(self, widget: tk.Text) -> None:
        def do_paste(event=None):  # type: ignore[override]
            try:
                data = self.clipboard_get()
            except tk.TclError:
                return "break"
            widget.insert(tk.INSERT, data)
            return "break"

        widget.bind("<Control-v>", do_paste)
        widget.bind("<<Paste>>", do_paste)

    def _build_ui(self) -> None:
        main_pane = ttk.Panedwindow(self, orient="vertical")
        main_pane.pack(fill=tk.BOTH, expand=True)

        scroll_area = ScrollableFrame(main_pane)
        form = scroll_area.scrollable_frame
        log_container = ttk.Frame(main_pane, style="Card.TFrame", height=220)

        main_pane.add(scroll_area, weight=3)
        main_pane.add(log_container, weight=1)

        padding = {"padx": 10, "pady": 6}

        hero = ttk.Frame(form, style="Card.TFrame")
        hero.pack(fill=tk.X, padx=14, pady=10)
        ttk.Label(hero, text="Парсер цен Ozon + Wildberries", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            hero,
            text="Вставьте ссылки, залогиньтесь в Ozon при необходимости и получите CSV + Excel.",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        links_frame = ttk.LabelFrame(form, text="Ссылки (Ctrl+V или файлы ниже)", style="Card.TLabelframe")
        links_frame.pack(fill=tk.X, padx=14, pady=8)

        ttk.Label(links_frame, text="Ozon: по одной ссылке в строке").grid(row=0, column=0, sticky="w", **padding)
        self.oz_text_box = tk.Text(links_frame, height=6, width=100, font=("Segoe UI", 10), bg="#ffffff", fg="#111827")
        self.oz_text_box.grid(row=1, column=0, sticky="nsew", **padding)
        self._enable_paste(self.oz_text_box)

        ttk.Label(links_frame, text="Wildberries: по одной ссылке в строке").grid(
            row=2, column=0, sticky="w", **padding
        )
        self.wb_text_box = tk.Text(links_frame, height=6, width=100, font=("Segoe UI", 10), bg="#ffffff", fg="#111827")
        self.wb_text_box.grid(row=3, column=0, sticky="nsew", **padding)
        self._enable_paste(self.wb_text_box)
        links_frame.columnconfigure(0, weight=1)

        files_frame = ttk.LabelFrame(form, text="Файлы ссылок (опционально)", style="Card.TLabelframe")
        files_frame.pack(fill=tk.X, padx=14, pady=(0, 8))
        self._add_path_row(files_frame, "Ссылки Ozon (.txt)", self.oz_path, self._pick_oz, 0)
        self._add_path_row(files_frame, "Ссылки WB (.txt)", self.wb_path, self._pick_wb, 1)

        profile_frame = ttk.LabelFrame(form, text="Профиль и браузер", style="Card.TLabelframe")
        profile_frame.pack(fill=tk.X, padx=14, pady=(0, 8))
        self._add_path_row(profile_frame, "Папка профиля Chrome/Chromium", self.profile_dir, self._pick_profile, 0)
        self._add_path_row(profile_frame, "Путь до chrome.exe (опционально)", self.browser_path, self._pick_browser, 1)
        self._add_path_row(profile_frame, "Куда сохранить CSV", self.output_path, self._pick_output, 2)

        options_frame = ttk.Frame(profile_frame, style="Card.TFrame")
        options_frame.grid(row=3, column=0, columnspan=3, sticky="w", **padding)
        ttk.Checkbutton(options_frame, text="Не сохранять HTML (skip)", variable=self.skip_html).pack(side=tk.LEFT)
        ttk.Checkbutton(options_frame, text="Headless режим", variable=self.headless).pack(side=tk.LEFT, padx=(12, 0))

        run_frame = ttk.Frame(form, style="Card.TFrame")
        run_frame.pack(fill=tk.X, padx=14, pady=(0, 8))
        ttk.Button(run_frame, text="Открыть окно для логина Ozon", command=self._open_login_window, style="Accent.TButton").pack(
            side=tk.LEFT, padx=4, pady=6
        )
        ttk.Button(run_frame, text="Старт парсинга", command=self._start, style="Primary.TButton").pack(
            side=tk.RIGHT, padx=4, pady=6
        )

        progress_frame = ttk.Frame(form, style="Card.TFrame")
        progress_frame.pack(fill=tk.X, padx=14, pady=(0, 10))
        ttk.Label(progress_frame, text="Прогресс").pack(anchor="w")
        self.progress = ttk.Progressbar(progress_frame, mode="determinate", maximum=1, value=0)
        self.progress.pack(fill=tk.X)
        self.status_var = tk.StringVar(value="Ожидание запуска")
        ttk.Label(progress_frame, textvariable=self.status_var).pack(anchor="w", pady=(4, 6))

        # Log area (fixed pane)
        ttk.Label(log_container, text="Лог", style="Sub.TLabel").pack(anchor="w", padx=10, pady=(6, 2))
        self.log_box = tk.Text(
            log_container,
            height=12,
            wrap="word",
            font=("Cascadia Mono", 10),
            bg="#ffffff",
            fg="#111827",
        )
        scroll = ttk.Scrollbar(log_container, command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=scroll.set)
        self.log_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=(0, 10))
        scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10), pady=(0, 10))
        self.log_box.configure(state="disabled")

    def _add_path_row(self, parent, label: str, variable: tk.StringVar, picker, row: int) -> None:
        padding = {"padx": 8, "pady": 4}
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", **padding)
        entry = ttk.Entry(parent, textvariable=variable, width=70)
        entry.grid(row=row, column=1, sticky="we", **padding)
        parent.columnconfigure(1, weight=1)
        ttk.Button(parent, text="Обзор", command=picker, style="Accent.TButton").grid(row=row, column=2, **padding)

    def _pick_oz(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if path:
            self.oz_path.set(path)

    def _pick_wb(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if path:
            self.wb_path.set(path)

    def _pick_profile(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self.profile_dir.set(path)

    def _pick_browser(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Chrome", "chrome.exe"), ("All", "*.*")])
        if path:
            self.browser_path.set(path)

    def _pick_output(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialdir="output",
            initialfile=f"paired_prices_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        )
        if path:
            self.output_path.set(path)

    def _collect_links(self, text_widget: tk.Text, file_path: Path, read_file_fn) -> List[str]:
        from_text = parse_links_text(text_widget.get("1.0", tk.END))
        if from_text:
            return from_text
        if file_path.exists():
            return read_file_fn(file_path)
        return []

    def _ensure_profile(self) -> Path:
        raw = self.profile_dir.get().strip()
        path = Path(raw) if raw else Path("output/playwright_profile")
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
        self.profile_dir.set(str(path))
        return path

    def _start(self) -> None:
        try:
            ensure_chromium_available()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Ошибка", f"Не удалось подготовить браузер: {exc}")
            return

        oz_file = Path(self.oz_path.get()).expanduser()
        wb_file = Path(self.wb_path.get()).expanduser()
        profile = self._ensure_profile()
        browser = Path(self.browser_path.get()).expanduser() if self.browser_path.get().strip() else None
        output = Path(self.output_path.get()).expanduser() if self.output_path.get().strip() else None

        oz_links = self._collect_links(self.oz_text_box, oz_file, read_oz_links)
        wb_links = self._collect_links(self.wb_text_box, wb_file, read_wb_links)

        if not oz_links or not wb_links:
            messagebox.showerror("Ошибка", "Нет ссылок Ozon или WB (вставьте в поля или выберите файлы).")
            return
        if not output:
            messagebox.showerror("Ошибка", "Укажите файл для сохранения CSV.")
            return

        self.progress_total = 1
        self._set_status("Запуск...", progress=0, total=1)
        self._append_log("Старт парсинга...")
        self._toggle_controls(disabled=True)

        worker = threading.Thread(
            target=self._run_pipeline,
            args=(oz_links, wb_links, profile, browser, output, self.skip_html.get(), self.headless.get()),
            daemon=True,
        )
        worker.start()

    def _open_login_window(self) -> None:
        try:
            ensure_chromium_available()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Ошибка", f"Не удалось подготовить браузер: {exc}")
            return

        profile_dir = self._ensure_profile()
        browser_path = Path(self.browser_path.get()).expanduser() if self.browser_path.get().strip() else None

        def launch():
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                kwargs = {
                    "user_data_dir": str(profile_dir),
                    "headless": False,
                }
                if browser_path:
                    kwargs["executable_path"] = str(browser_path)
                ctx = p.chromium.launch_persistent_context(**kwargs)
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.goto("https://www.ozon.ru/", wait_until="domcontentloaded")
                messagebox.showinfo(
                    "Логин",
                    "Войдите в Ozon в открывшемся браузере.\nПосле входа закройте окно и запустите парсер.",
                )
                ctx.close()

        threading.Thread(target=launch, daemon=True).start()

    def _run_pipeline(
        self,
        oz_links: List[str],
        wb_links: List[str],
        profile_dir: Path,
        browser_path: Optional[Path],
        output_path: Path,
        skip_html: bool,
        headless: bool,
    ) -> None:
        writer = QueueWriter(self.events)
        try:
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                total_pairs = min(len(oz_links), len(wb_links))
                if len(oz_links) != len(wb_links):
                    self.events.put(
                        ("log", f"[WARN] Кол-во ссылок не совпало (Ozon={len(oz_links)}, WB={len(wb_links)}). Берем пары: {total_pairs}")
                    )
                oz_links = oz_links[:total_pairs]
                wb_links = wb_links[:total_pairs]
                if total_pairs == 0:
                    raise RuntimeError("Нет пар ссылок для обработки.")

                self.events.put(("progress_reset", total_pairs * 2))
                self.events.put(("log", f"Пар для обработки: {total_pairs}"))

                def on_oz_progress(current: int, total: int, url: str, status: str) -> None:
                    self.events.put(
                        ("progress", current, total_pairs * 2, f"Ozon {current}/{total} [{status}]")
                    )

                oz_records = download_pages(
                    links=oz_links,
                    output_dir=Path("data/html/ozon"),
                    profile_dir=profile_dir,
                    browser_path=browser_path,
                    headless=headless,
                    per_page_delay=1.5,
                    timeout=90,
                    overwrite=True,
                    manual_confirm=False,
                    skip_html=skip_html,
                    on_progress=on_oz_progress,
                )

                def on_wb_progress(current: int, total: int, link: str) -> None:
                    self.events.put(
                        ("progress", total_pairs + current, total_pairs * 2, f"WB {current}/{total}")
                    )

                wb_records = parse_wb_links(wb_links, on_progress=on_wb_progress)

                rows = _zip_pairs(oz_records, wb_records, oz_links, wb_links)
                if not rows:
                    raise RuntimeError("Не удалось собрать строки отчета.")

                _write_rows(rows, output_path)
                done_text = f"Готово: {output_path} и {output_path.with_suffix('.xlsx')}"
                self.events.put(("done", done_text))
        except Exception as exc:  # noqa: BLE001
            self.events.put(("error", str(exc)))

    def _drain_events(self) -> None:
        while True:
            try:
                kind, *payload = self.events.get_nowait()
            except queue.Empty:
                break

            if kind == "log":
                self._append_log(str(payload[0]))
            elif kind == "progress_reset":
                total = int(payload[0]) or 1
                self.progress_total = total
                self.progress.configure(maximum=total, value=0)
                self.status_var.set("Старт...")
            elif kind == "progress":
                done, total, msg = int(payload[0]), int(payload[1]), str(payload[2])
                self.progress_total = max(total, 1)
                self.progress.configure(maximum=self.progress_total, value=min(done, self.progress_total))
                self.status_var.set(msg)
            elif kind == "done":
                self.progress.configure(value=self.progress_total)
                self.status_var.set(str(payload[0]))
                self._append_log(str(payload[0]))
                self._toggle_controls(disabled=False)
                messagebox.showinfo("Готово", str(payload[0]))
            elif kind == "error":
                self.status_var.set("Ошибка")
                self._append_log(f"[ERROR] {payload[0]}")
                self._toggle_controls(disabled=False)
                messagebox.showerror("Ошибка", str(payload[0]))

        self.after(100, self._drain_events)

    def _set_status(self, text: str, progress: int, total: int) -> None:
        self.progress.configure(maximum=max(total, 1), value=progress)
        self.status_var.set(text)

    def _append_log(self, text: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert(tk.END, text + "\n")
        self.log_box.see(tk.END)
        self.log_box.configure(state="disabled")

    def _toggle_controls(self, disabled: bool) -> None:
        state = "disabled" if disabled else "normal"
        for child in self.winfo_children():
            try:
                child.configure(state=state)
            except tk.TclError:
                continue
        self.log_box.configure(state="disabled")


def main() -> None:
    app = ParserApp()
    app.mainloop()


if __name__ == "__main__":
    main()
