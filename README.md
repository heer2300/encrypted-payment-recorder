# Payment Records

A simple Windows desktop app for tracking payments on real-estate deals, where the price is stored and displayed as an **encoded string of letters** instead of a plain number — so a screenshot, printout, or PDF never shows the real amount to someone who doesn't know the code.

Built with Python's built-in `tkinter` and `sqlite3`, so it runs as a single file with no external dependencies.

## Features

- **Table view** of all payments: Project Name, Address, Price (coded), Date.
- **Add Payment** — a form asks for the project, address, price, and date. The **price is typed as a plain number only in this form**; once saved, only the coded version is stored and shown anywhere else in the app.
- **Multiple payments per deal** — add as many payments as you like against the same project name; the address autofills from the last entry for that project.
- **Filter by project** — a dropdown lets you show all payments for one deal, or all deals at once.
- **Running total**, shown in code, for whatever is currently filtered.
- **Create PDF** — exports the current view to a PDF file.
- **Print** — opens a print-ready page in your browser.
- **Delete Selected** — removes a payment record.
- Colored UI with smooth animations (fading windows, gliding table rows, a shimmering header, and buttons that hop when clicked).

## Price encoding

Each digit maps to a letter:

| Digit | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 0 |
|-------|---|---|---|---|---|---|---|---|---|---|
| Letter| b | h | t | r | p | w | s | x | z | o |

So `1500` becomes `bpoo`.

To make the code harder to guess at a glance, every group of 3 letters gets one random **filler letter** (`m` or `n`) inserted into it, turning each group of 3 into 4 characters — for example `bpoo` might display as `bpmoom`. Anyone who knows the digit-to-letter table simply ignores the `m`/`n` characters and reads the rest in groups of 3 to get the real number back.

The plain number is **only ever visible in the Add Payment form**, at the moment of entry. It is never written to the database, the table view, the PDF, or the printout.

You can change the digit-to-letter table by editing the `CODE_MAP` dictionary near the top of `payment_records.py`.

## Requirements

- Windows (for the packaged `.exe`), or any OS with Python 3 installed (to run the `.py` file directly).
- No external Python packages are required — only the standard library.

## Running from source

```bash
python payment_records.py
```

A `payments.db` SQLite file is created automatically next to the script on first run.

## Building a Windows .exe

1. Install Python from [python.org](https://www.python.org/) and make sure **"Add Python to PATH"** is checked during setup.
2. Keep `payment_records.py` and `build_exe.bat` in the same folder.
3. Double-click `build_exe.bat`. It installs [PyInstaller](https://pyinstaller.org/) and builds the app.
4. The finished app is at `dist\PaymentRecords.exe` — a single file, no console window.

Re-run `build_exe.bat` any time you update `payment_records.py`; the `.exe` does not update itself.

**Note:** Windows Defender or another antivirus may flag a freshly built PyInstaller `.exe` as unrecognized. This is a common false positive for self-built executables — you can allow it.

## Data storage

All records are kept in `payments.db`, an SQLite file created next to the app (or next to the `.exe`, if packaged). Back up your data by copying this file.




