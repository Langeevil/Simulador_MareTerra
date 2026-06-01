from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import tkinter as tk
import webbrowser
from contextlib import closing
from pathlib import Path
from tkinter import messagebox, ttk


APP_NAME = "Simulador de Biomassa - Mar & Terra"
BRAND_GREEN = "#17413B"
BRAND_GOLD = "#BC933F"
BRAND_GOLD_SOFT = "#E7D8B5"


def app_root() -> Path:
    """Retorna a raiz do projeto em desenvolvimento ou no pacote PyInstaller."""
    if hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent


def runtime_dir() -> Path:
    """Retorna a pasta gravável usada para logs e execução local."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def log_path() -> Path:
    return runtime_dir() / "SimuladorBiomassa.log"


def ensure_runtime_data_files() -> None:
    """Garante uma pasta data/input editavel ao lado do executavel."""
    source = app_root() / "data" / "input"
    target = runtime_dir() / "data" / "input"
    if not source.exists() or source.resolve() == target.resolve():
        return

    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.is_file():
            target_file = target / item.name
            if not target_file.exists():
                shutil.copy2(item, target_file)


def find_free_port(start: int = 8501, attempts: int = 50) -> int:
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("Nao foi encontrada uma porta local livre para abrir o app.")


def run_streamlit_server(port: int) -> None:
    root = app_root()
    os.environ["SIMULADOR_RUNTIME_DIR"] = str(runtime_dir())
    app_path = root / "app" / "app.py"
    src_path = root / "src"

    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    if not app_path.exists():
        raise FileNotFoundError(f"Arquivo da interface nao encontrado: {app_path}")

    from streamlit.web import bootstrap

    flag_options = {
        "server_port": port,
        "server_address": "127.0.0.1",
        "server_headless": True,
        "global_developmentMode": False,
    }
    bootstrap.load_config_options(flag_options)
    bootstrap.run(
        str(app_path),
        False,
        [],
        flag_options,
    )


def server_command(port: int) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--server", str(port)]
    return [sys.executable, str(Path(__file__).resolve()), "--server", str(port)]


def start_server_process(port: int) -> subprocess.Popen:
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW
    log_file = open(log_path(), "a", encoding="utf-8")
    return subprocess.Popen(
        server_command(port),
        stdout=log_file,
        stderr=log_file,
        creationflags=creationflags,
    )


def wait_for_server(url: str, server: subprocess.Popen, timeout_seconds: int = 45) -> bool:
    host = "127.0.0.1"
    port = int(url.rsplit(":", 1)[1])
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        if server.poll() is not None:
            return False
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.4)

    return False


def render_control_window(server: subprocess.Popen, url: str) -> None:
    window = tk.Tk()
    window.title(APP_NAME)
    window.geometry("520x360")
    window.resizable(False, False)
    window.configure(bg="#F6F2EA")

    root = app_root()
    icon_path = root / "app" / "assets" / "mar-terra-logo.ico"
    logo_path = root / "app" / "assets" / "mar-terra-logo-branca.png"
    logo_image = None
    if icon_path.exists():
        try:
            window.iconbitmap(str(icon_path))
        except tk.TclError:
            pass

    style = ttk.Style(window)
    style.theme_use("clam")
    style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=(16, 10))
    style.configure("Secondary.TButton", font=("Segoe UI", 10, "bold"), padding=(16, 10))

    shell = tk.Frame(window, bg="#F6F2EA")
    shell.pack(fill="both", expand=True, padx=18, pady=18)

    hero = tk.Frame(shell, bg=BRAND_GREEN, highlightbackground=BRAND_GOLD, highlightthickness=1)
    hero.pack(fill="x")

    if logo_path.exists():
        try:
            from PIL import Image, ImageTk

            image = Image.open(logo_path).convert("RGBA")
            image.thumbnail((170, 80))
            logo_image = ImageTk.PhotoImage(image)
            tk.Label(hero, image=logo_image, bg=BRAND_GREEN).pack(pady=(22, 8))
        except Exception:
            tk.Label(
                hero,
                text="MAR & TERRA",
                font=("Segoe UI", 22, "bold"),
                bg=BRAND_GREEN,
                fg="#FFFFFF",
            ).pack(pady=(22, 8))

    tk.Label(
        hero,
        text="Simulador de Biomassa",
        font=("Segoe UI", 17, "bold"),
        bg=BRAND_GREEN,
        fg="#FFFFFF",
    ).pack()

    tk.Label(
        hero,
        text="Aplicativo local rodando com segurança no seu computador",
        font=("Segoe UI", 10),
        bg=BRAND_GREEN,
        fg=BRAND_GOLD_SOFT,
    ).pack(pady=(4, 20))

    card = tk.Frame(shell, bg="#FFFFFF", highlightbackground="#DED6C8", highlightthickness=1)
    card.pack(fill="x", pady=(14, 0))

    tk.Label(
        card,
        text="Status",
        font=("Segoe UI", 9, "bold"),
        bg="#FFFFFF",
        fg="#5C6470",
    ).pack(anchor="w", padx=18, pady=(14, 0))

    tk.Label(
        card,
        text="Rodando",
        font=("Segoe UI", 14, "bold"),
        bg="#FFFFFF",
        fg=BRAND_GREEN,
    ).pack(anchor="w", padx=18)

    tk.Label(
        card,
        text=url,
        font=("Segoe UI", 9),
        bg="#FFFFFF",
        fg="#374151",
    ).pack(anchor="w", padx=18, pady=(2, 14))

    buttons = tk.Frame(shell, bg="#F6F2EA")
    buttons.pack(fill="x", pady=(14, 0))

    def open_app() -> None:
        webbrowser.open(url)

    def stop_app() -> None:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
        window.destroy()

    open_button = tk.Button(
        buttons,
        text="Abrir no navegador",
        width=22,
        command=open_app,
        bg=BRAND_GOLD,
        fg="#111111",
        activebackground="#D7B96B",
        activeforeground="#111111",
        relief="flat",
        borderwidth=0,
        font=("Segoe UI", 10, "bold"),
        cursor="hand2",
    )
    open_button.grid(row=0, column=0, padx=(0, 10), ipady=7)

    stop_button = tk.Button(
        buttons,
        text="Encerrar",
        width=18,
        command=stop_app,
        bg=BRAND_GREEN,
        fg="#FFFFFF",
        activebackground="#102F2B",
        activeforeground="#FFFFFF",
        relief="flat",
        borderwidth=0,
        font=("Segoe UI", 10, "bold"),
        cursor="hand2",
    )
    stop_button.grid(row=0, column=1, padx=(0, 0), ipady=7)

    tk.Label(
        shell,
        text="Fechar a aba do navegador não encerra o app. Use Encerrar nesta janela.",
        font=("Segoe UI", 8),
        bg="#F6F2EA",
        fg="#5C6470",
    ).pack(anchor="w", pady=(12, 0))

    window.logo_image = logo_image


    def on_close() -> None:
        if messagebox.askyesno(APP_NAME, "Encerrar o simulador?"):
            stop_app()

    window.protocol("WM_DELETE_WINDOW", on_close)
    window.after(1200, open_app)
    window.mainloop()


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "--server":
        run_streamlit_server(int(sys.argv[2]))
        return

    ensure_runtime_data_files()
    port = find_free_port()
    url = f"http://127.0.0.1:{port}"
    server = start_server_process(port)
    if not wait_for_server(url, server):
        messagebox.showerror(
            APP_NAME,
            "Nao foi possivel iniciar o Streamlit.\n\n"
            f"Veja o log em:\n{log_path()}",
        )
        if server.poll() is None:
            server.terminate()
        return
    render_control_window(server, url)


if __name__ == "__main__":
    main()
