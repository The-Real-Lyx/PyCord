PyCord
A Discord-controlled remote administration tool for Windows. PyCord turns a Python script into a standalone Windows executable that connects to your Discord server and lets you monitor and control the host machine through Discord commands.

⚠️ Disclaimer: This project is intended for educational purposes and legitimate remote administration of machines you own or have explicit permission to manage. Do not use it on systems you do not own or have authorization to control. The author is not responsible for any misuse or damage caused by this software.

Features
🖥️ System monitoring – CPU, RAM, disk, network, uptime, and process overview

📸 Screenshots – capture all connected monitors

📷 Webcam capture – take photos from detected webcams

📜 Browser history – extract history from Chrome, Edge, and Opera

🔍 File search – multithreaded search across all drives

▶️ Remote execution – run allowed file types on the host

🔪 Process control – list and terminate processes (with system protection)

📥 File download – download files via URL to a local folder

🔒 Lock workstation – lock the Windows session remotely

🔄 Restart bot – restart the bot process without losing autostart

🛑 Shutdown PC – shut down the host with a configurable delay

🔊 Volume control – set the system volume (0–100)

💣 Panic mode – wipe all channels, delete the EXE, and shut down

🚀 Autostart – automatically moves itself into the user's Startup folder and relaunches with admin rights

🔒 UAC management – optionally set UAC to "Never notify" (admin required)

Requirements
Windows 10/11

Python 3.12+ (installed automatically by Installer.cmd if missing)

A Discord bot token and a Discord server (guild) ID

Python modules
Module	Purpose
discord.py	Discord bot framework
aiohttp	Async file downloads
psutil	System/process information
mss	Screenshots
opencv-python	Webcam capture
browser-history	Browser history extraction
pycaw + comtypes	System volume control
pyinstaller	Building the standalone EXE
Installer.cmd installs discord.py, aiohttp, psutil, and pyinstaller.

mss, opencv-python, browser-history, and pycaw/comtypes are only needed for the corresponding commands and must be installed manually if you want to use them.

Installation
Clone or download this repository.

Make sure the following files are in the same folder:

Installer.cmd

builder.cmd

PyCord.py

Data.txt

Run Installer.cmd as administrator.

It installs Python (if needed), updates pip, and installs all required modules.

It then automatically launches builder.cmd.

Building the EXE
builder.cmd handles the whole build process:

Removes the outdated pathlib backport (if present).

Verifies that PyCord.py exists.

Prompts for:

Discord Bot Token

Server ID (Guild ID)

Logo path (optional, used as the EXE icon)

Writes the token and server ID to Data.txt.

Builds a onefile, noconsole EXE with PyInstaller.

Copies PyCord.exe directly to your Desktop.

Data.txt is embedded into the EXE, so the token and server ID are read from memory at runtime.

Getting a bot token & server ID
Bot token: Discord Developer Portal → Your App → Bot → Reset Token

Server ID: Enable Developer Mode in Discord, then right-click your server → Copy Server ID

Make sure the bot is invited to your server with the Message Content Intent enabled in the Developer Portal.

How it works
When the EXE runs:

If not already in the user's Startup folder, it moves itself there and relaunches with admin rights.

If admin rights are missing, it triggers a UAC prompt.

It reads Token and Server from the embedded Data.txt.

It connects to Discord and creates a category named pc-<MAC-address> containing:

🤖commands

⬆️up-load

⬇️down-load

‼️information

Commands are only accepted inside the bot's own category and in the 🤖commands channel.

Commands
System information
Command	Description
!ping	Check bot latency
!uptime	Bot and PC uptime
!diskinfo	Disk usage per partition
!ipinfo	Local IP, public IP, hostname
!userinfo	Current user, OS, CPU info
!pcdata	Full system overview (CPU, RAM, disk, network)
!processinfo [filter]	List running processes (top 30 by RAM)
File & process control
Command	Description
!searchpath <filename>	Multithreaded file search across all drives
!run <path>	Execute an allowed file type
!kill <PID|name>	Terminate a process (system processes are protected)
Capture & history
Command	Description
!screenshot	Capture all monitors
!webcam	Capture photos from all webcams
!history	Extract browser history
System control
Command	Description
!lock	Lock the Windows workstation
!shutdown [seconds]	Shut down the PC (default: 30 s)
!setvolume <0-100>	Set the system volume
!restart	Restart the bot process
!stop	Shut down the bot and close the process
Destructive
Command	Description
!panic	Delete all channels in the category, delete the EXE, and shut down
!panic requires you to type confirm within 15 seconds. It deletes every channel in the bot's own category, then schedules the running EXE for deletion via a hidden batch script and terminates the process.

Upload listener
Send an http(s) link into the ⬆️up-load channel and the file will be downloaded to:

text
%LocalAppData%\PyCord\Up-loads
Project structure
text
.
├── builder.cmd      # Builds the standalone EXE
├── Installer.cmd    # Installs Python + modules, then runs builder.cmd
├── PyCord.py        # Main bot script
├── Data.txt         # Token + server ID (embedded at build time)
└── README.md
Security notes
Never commit your real Data.txt with a valid token to a public repository.

The generated EXE contains your token in plain form — treat it as sensitive.

!run is restricted to a safe allowlist of extensions (.exe, .bat, .cmd, .ps1, .py, .msi, .lnk, .vbs, .jar).

!kill protects critical system processes (e.g. lsass.exe, svchost.exe, explorer.exe, and the bot itself).

set_uac_low() modifies registry keys under HKLM\...\Policies\System. Use restore_uac_default() to revert to Windows defaults.

!panic is irreversible — it deletes the EXE and all channels in the bot's category. Use with extreme care.

Troubleshooting
Problem	Solution
pathlib conflict	builder.cmd removes it automatically
PyInstaller not found	Run Installer.cmd again
Bot doesn't respond	Verify token, server ID, and that Message Content Intent is enabled
Commands ignored	Make sure you're in the bot's own category and the 🤖commands channel
Missing mss / cv2 / browser_history	pip install mss opencv-python browser-history
Volume command fails	pip install pycaw comtypes
!panic doesn't delete the EXE	Make sure the bot is running as admin
License
This project is provided as-is for educational purposes. Use at your own risk.

Contributing
Pull requests and issues are welcome. Please make sure not to include any real tokens or personal data in your contributions.

⚠️ Important: If you accidentally committed a real token, revoke it immediately in the Discord Developer Portal and generate a new one.
