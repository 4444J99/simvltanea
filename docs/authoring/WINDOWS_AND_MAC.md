# Windows and macOS

The project is developed on macOS and is meant to work on Windows too. This page
says what runs where, how to install FFmpeg, how to run the Python tools from
PowerShell, and how to get clips from a phone onto a Windows PC.

Windows support so far comes from reading the code and from static checks that
run on Linux CI (`tests/test_platform_portability.py`). Nobody has run the
commands below on a Windows machine yet. If one fails there, please open an
issue with the full error message.

## What works where

| Part | macOS | Windows | Notes |
| --- | --- | --- | --- |
| Browser studio | Yes | Yes | A static page; nothing to install. HEVC caveat below |
| `doctor`, `render`, `preview`, `proxy` commands | Yes | Yes | Python 3.12 or newer and FFmpeg (`ffmpeg`, `ffprobe`) on `PATH` |
| Folder import (`tools.media.import_folder`) | Yes | Yes | Copies clips by default on Windows (symlinks need Developer Mode) |
| Photos export (`tools.media.export_photos_album`) | Yes | No | Drives Photos.app through `osascript`, which exists only on macOS |
| Live Photos tagging, clip index, play states | Yes | Only with an export folder | These read the `originals/<id>/.done` receipts that Photos export writes |

**HEVC on Windows.** iPhones record HEVC (H.265) by default. Many Windows
browsers cannot decode it unless the HEVC Video Extensions from the Microsoft
Store are installed, and Firefox cannot decode it at all. The studio then names
the file and its codec in its refusal message. Either set the iPhone camera to
**Most Compatible** (H.264) before recording, or make H.264 proxies first with
`independent-loop-compositor proxy` (see [Proxy clips](PROXY_CLIPS.md)). Proxies
play in every browser.

**Replacing a browser preview on Windows.** `preview` publishes a new preview
by swapping directories atomically, and Windows has no atomic directory swap.
The first build into a new `--output` folder works. Rebuilding into an existing
preview folder stops with "atomic preview directory exchange unavailable".
Delete the old folder or choose a new one.

## Install FFmpeg

macOS, with [Homebrew](https://brew.sh):

```bash
brew install ffmpeg
```

Windows, with winget (included in Windows 10 and 11), in PowerShell:

```powershell
winget install Gyan.FFmpeg
```

Close and reopen PowerShell so the new `PATH` takes effect, then check that both
tools are found:

```powershell
ffmpeg -version
ffprobe -version
```

The tools find FFmpeg on `PATH` with `shutil.which`, which also finds
`ffmpeg.exe`. You do not need to set a path to FFmpeg anywhere.

## Run the tools from PowerShell

Install Python 3.12 or newer from python.org. Its `py` launcher picks the
version. From the repository root:

```powershell
py -3 -m pip install -e ".[verification]"
py -3 -m independent_loop_compositor doctor
```

After the install, `independent-loop-compositor doctor` works as well. To run
modules from a checkout without installing, set `PYTHONPATH` for the session.
PowerShell separates entries with `;`:

```powershell
$env:PYTHONPATH = "$PWD;$PWD\src"
py -3 -m independent_loop_compositor render --help
py -3 -m tools.media.import_folder --help
```

The macOS and Linux equivalent is:

```bash
PYTHONPATH=.:src python3 -m independent_loop_compositor render --help
```

Paths may use `\` or `/` on Windows. Paths the tools write into project files
and site pages always use `/`, so a project made on one system also opens on
the other.

## Bring clips from a phone to a folder on Windows

Photos export needs macOS. On Windows, put the clips in an ordinary folder
first, then point the tools at that folder.

- **Copy from the phone.** Connect the iPhone or Android phone with a cable and
  unlock it. On an iPhone, tap **Trust**. Then either open it in File Explorer
  (`This PC`, then the phone, then `Internal Storage\DCIM`) and copy the video
  files, or use **Import from a connected device** in the Windows Photos app. A
  Live Photo usually arrives as a still image plus a `.MOV` file with the same
  name; the `.MOV` is the clip.
- **Download from iCloud Photos.** Sign in at icloud.com, open **Photos**,
  select the clips, and choose **Download**. The browser saves them to your
  Downloads folder, or as a `.zip` file to extract when you pick several.
  iCloud for Windows can also sync the library to a local folder.

Then make proxies and stage them, for example:

```powershell
py -3 -m independent_loop_compositor proxy "$HOME\Videos\phone-clips" --out "$HOME\Videos\proxies"
py -3 -m tools.media.import_folder "$HOME\Videos\proxies"
```

You can also drop the proxies straight into the browser studio.

## Photos export on a Mac

`python3 -m tools.media.export_photos_album --root /path/to/live-photos` exports
an album's Live Photo originals and writes the receipts that tagging and play
states read. On any other system it exits with one sentence saying that Photos
export needs macOS. It never starts a partial export there.
