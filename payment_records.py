"""
Payment Record Manager (encoded prices)
---------------------------------------
- Price is typed as a number ONLY in the Add Payment window.
- It is saved and shown only as coded letters, with filler letters (m / n)
  mixed in: every group of 3 code letters gets 1 random m or n inside it.
- Pick a project in the dropdown to see all payments of that deal.
- Buttons: Add Payment, Create PDF, Print, Delete Selected.

Run:  python payment_records.py
"""

import html
import math
import os
import random
import re
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import time
import webbrowser
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# ----------------------------------------------------------------------
# CODE TABLE (edit here to change the encoding)
# 7 -> s is my choice, because you did not give a letter for 7.
# m and n are used as random filler letters (see add_noise), and are NOT
# real code letters. p stays as 5, as you specified.
# ----------------------------------------------------------------------
CODE_MAP = {
    "1": "b", "2": "h", "3": "t", "4": "r", "5": "p",
    "6": "w", "7": "s", "8": "x", "9": "z", "0": "o",
}
DECODE_MAP = {v: k for k, v in CODE_MAP.items()}
FILLER = "mn"

# When packaged as an .exe, keep payments.db next to the .exe
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).resolve().parent
DB_FILE = APP_DIR / "payments.db"

ALL = "All projects"
DATE_FMT = "%d-%m-%Y"

# ----------------------------------------------------------------------
# Colors / font
# ----------------------------------------------------------------------
BG = "#f1f5f9"
INK = "#1e293b"
MUTED = "#64748b"
HEAD_A, HEAD_B = "#4338ca", "#0ea5e9"
ACCENT, ACCENT_H = "#4f46e5", "#6366f1"
GREEN, GREEN_H = "#059669", "#10b981"
SKY, SKY_H = "#0284c7", "#0ea5e9"
ROSE, ROSE_H = "#e11d48", "#f43f5e"
ROW_A, ROW_B, ROW_HOVER = "#ffffff", "#eef2ff", "#dbe4ff"
FLASH = "#86efac"
FONT = "Segoe UI"


# ----------------------------------------------------------------------
# Encoding helpers
# ----------------------------------------------------------------------
def encode_price(number_text):
    """'1500' -> 'bpoo' (clean code, no filler)."""
    return "".join(CODE_MAP[ch] for ch in number_text)


def decode_price(code_text):
    return int("".join(DECODE_MAP[ch] for ch in code_text))


def add_noise(code, rng=random):
    """Take the code 3 letters at a time and put 1 random m or n between
    the letters of each group (3 letters become 4). A short last group
    also gets one filler."""
    out = []
    for i in range(0, len(code), 3):
        group = list(code[i:i + 3])
        pos = rng.randint(1, len(group) - 1) if len(group) > 1 else 1
        group.insert(pos, rng.choice(FILLER))
        out.append("".join(group))
    return "".join(out)


def coded_total(rows):
    total = sum(decode_price(r[4]) for r in rows)
    # seeded by the value, so the same total always looks the same
    return add_noise(encode_price(str(total)), random.Random(str(total)))


# ----------------------------------------------------------------------
# Animation helpers
# ----------------------------------------------------------------------
def lerp_color(c1, c2, t):
    t = max(0.0, min(1.0, t))
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def ease_out(t):
    return 1 - (1 - max(0.0, min(1.0, t))) ** 3


def fade_in(win, step=0.09, delay=16):
    try:
        win.attributes("-alpha", 0.0)
    except tk.TclError:
        return

    def go(a):
        a = min(1.0, a + step)
        try:
            win.attributes("-alpha", a)
        except tk.TclError:
            return
        if a < 1.0:
            win.after(delay, go, a)

    go(0.0)


def open_file(path):
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


# ----------------------------------------------------------------------
# Database (only coded prices are ever saved)
# price_code = clean code (used for totals)
# price_show = code with filler letters (what you see / print)
# ----------------------------------------------------------------------
class DB:
    def __init__(self, path):
        self.con = sqlite3.connect(path)
        self.con.execute(
            """CREATE TABLE IF NOT EXISTS payments (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   project TEXT NOT NULL,
                   address TEXT NOT NULL,
                   price_code TEXT NOT NULL,
                   pay_date TEXT NOT NULL,
                   price_show TEXT
               )"""
        )
        cols = [r[1] for r in self.con.execute("PRAGMA table_info(payments)")]
        if "price_show" not in cols:
            self.con.execute("ALTER TABLE payments ADD COLUMN price_show TEXT")
            # the first version used q for 7; q is now filler only, 7 is s
            self.con.execute("UPDATE payments SET price_code = REPLACE(price_code, 'q', 's')")
        rows = self.con.execute(
            "SELECT id, price_code FROM payments WHERE price_show IS NULL"
        ).fetchall()
        for pid, code in rows:
            self.con.execute("UPDATE payments SET price_show=? WHERE id=?", (add_noise(code), pid))
        self.con.commit()

    def add(self, project, address, price_code, price_show, pay_date_iso):
        cur = self.con.execute(
            "INSERT INTO payments (project, address, price_code, price_show, pay_date) "
            "VALUES (?,?,?,?,?)",
            (project, address, price_code, price_show, pay_date_iso),
        )
        self.con.commit()
        return cur.lastrowid

    def delete(self, pid):
        self.con.execute("DELETE FROM payments WHERE id=?", (pid,))
        self.con.commit()

    def projects(self):
        rows = self.con.execute(
            "SELECT DISTINCT project FROM payments ORDER BY project COLLATE NOCASE"
        ).fetchall()
        return [r[0] for r in rows]

    def address_of(self, project):
        row = self.con.execute(
            "SELECT address FROM payments WHERE project=? ORDER BY id DESC LIMIT 1",
            (project,),
        ).fetchone()
        return row[0] if row else ""

    def rows(self, project=None):
        sql = "SELECT id, project, address, price_show, price_code, pay_date FROM payments"
        args = ()
        if project and project != ALL:
            sql += " WHERE project=?"
            args = (project,)
        sql += " ORDER BY pay_date, id"
        return self.con.execute(sql, args).fetchall()


# ----------------------------------------------------------------------
# Jumping button (drawn on a canvas so it can move and fade smoothly)
# ----------------------------------------------------------------------
class JumpButton(tk.Canvas):
    PAD = 12  # free space above the button so it has room to jump

    def __init__(self, parent, text, command, color, hover, width=124, height=38):
        bg = parent.cget("bg")
        self.total_h = height + self.PAD + 8
        super().__init__(parent, width=width, height=self.total_h, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.parent_bg = bg
        self.text, self.command = text, command
        self.color, self.hover_color = color, hover
        self.bw, self.bh = width, height
        self.hp = 0.0          # hover progress 0..1 (smooth color fade)
        self.target = 0.0
        self.jump_start = None
        self.jump_amp = 0.0
        self.pressed = False
        self._job = None
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self._draw(0.0)

    # --- events ---
    def _enter(self, _e):
        self.target = 1.0
        self._jump(self.PAD - 3)

    def _leave(self, _e):
        self.target = 0.0
        self.pressed = False
        self._kick()

    def _press(self, _e):
        self.pressed = True
        self._kick()

    def _release(self, e):
        was = self.pressed
        self.pressed = False
        inside = 0 <= e.x <= self.bw and 0 <= e.y <= self.total_h
        if was and inside:
            self._jump(self.PAD - 1)
            self.after(170, self.command)   # let the jump be seen first
        else:
            self._kick()

    # --- animation ---
    def _jump(self, amp):
        self.jump_amp = amp
        self.jump_start = time.time()
        self._kick()

    def _kick(self):
        if self._job is None:
            self._tick()

    def _hop(self, t):
        a = self.jump_amp
        if t < 0.30:                       # big hop
            u = t / 0.30
            return a * 4 * u * (1 - u)
        t -= 0.30
        if t < 0.20:                       # small second bounce
            u = t / 0.20
            return a * 0.35 * 4 * u * (1 - u)
        return None

    def _tick(self):
        if not self.winfo_exists():
            return
        self.hp += (self.target - self.hp) * 0.22
        lift = 0.0
        if self.jump_start is not None:
            h = self._hop(time.time() - self.jump_start)
            if h is None:
                self.jump_start = None
            else:
                lift = h
        self._draw(lift)
        if self.jump_start is not None or abs(self.target - self.hp) > 0.01:
            self._job = self.after(16, self._tick)
        else:
            self.hp = self.target
            self._draw(0.0)
            self._job = None

    def _draw(self, lift):
        self.delete("all")
        top = self.PAD - lift - 2 * self.hp + (2 if self.pressed else 0)
        body = lerp_color(self.color, self.hover_color, self.hp)
        cx = self.bw / 2
        ground = self.PAD + self.bh + 2
        rise = min(1.0, (lift + 2 * self.hp) / self.PAD)
        sw = self.bw * (0.86 - 0.30 * rise)          # shadow shrinks as button rises
        self.create_oval(cx - sw / 2, ground, cx + sw / 2, ground + 5,
                         fill=lerp_color(self.parent_bg, "#000000", 0.16 - 0.08 * rise),
                         outline="")
        x1, y1, x2, y2, r = 1, top, self.bw - 1, top + self.bh, 10
        pts = [x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
               x2, y1 + r, x2, y2 - r, x2, y2 - r, x2, y2, x2 - r, y2, x2 - r, y2,
               x1 + r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y2 - r, x1, y1 + r,
               x1, y1 + r, x1, y1]
        self.create_polygon(pts, smooth=True, fill=body, outline="")
        self.create_text(cx, top + self.bh / 2, text=self.text, fill="white",
                         font=(FONT, 10, "bold"))


# ----------------------------------------------------------------------
# Header with a soft gradient and a slow moving shimmer line
# ----------------------------------------------------------------------
class Header(tk.Canvas):
    H = 78

    def __init__(self, parent, title, subtitle, c1, c2):
        super().__init__(parent, height=self.H, highlightthickness=0, bd=0, bg=c1)
        self.title_text, self.sub, self.c1, self.c2 = title, subtitle, c1, c2
        self.phase = 0.0
        self.bind("<Configure>", lambda e: self._draw())
        self._shimmer()

    def _draw(self):
        self.delete("bg")
        w = max(self.winfo_width(), 2)
        n = 70
        for i in range(n):
            self.create_rectangle(w * i / n, 0, w * (i + 1) / n + 1, self.H,
                                  fill=lerp_color(self.c1, self.c2, i / (n - 1)),
                                  outline="", tags="bg")
        self.create_text(26, 32, text=self.title_text, anchor="w", fill="white",
                         font=(FONT, 20, "bold"), tags="bg")
        self.create_text(27, 58, text=self.sub, anchor="w", fill="#e0e7ff",
                         font=(FONT, 10), tags="bg")

    def _shimmer(self):
        if not self.winfo_exists():
            return
        w = max(self.winfo_width(), 2)
        self.delete("shim")
        self.phase = (self.phase + 0.004) % 1.0
        x = -100 + (w + 200) * self.phase
        for k in range(20):
            xx = x - 100 + k * 10
            a = math.sin(math.pi * k / 19)
            base = lerp_color(self.c1, self.c2, xx / w)
            self.create_rectangle(xx, self.H - 4, xx + 10, self.H,
                                  fill=lerp_color(base, "#ffffff", 0.8 * a),
                                  outline="", tags="shim")
        self.after(30, self._shimmer)


# ----------------------------------------------------------------------
# Minimal PDF writer (no extra libraries needed)
# ----------------------------------------------------------------------
class SimplePDF:
    W, H = 595, 842   # A4 in points

    def __init__(self):
        self.pages = []

    def new_page(self):
        self.pages.append([])

    @staticmethod
    def _esc(s):
        s = s.encode("cp1252", "replace").decode("latin-1")
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    def text(self, x, top, s, size=10, bold=False, color=(0, 0, 0)):
        y = self.H - top - size
        r, g, b = color
        self.pages[-1].append(
            f"BT /{'F2' if bold else 'F1'} {size} Tf {r:.3f} {g:.3f} {b:.3f} rg "
            f"{x:.2f} {y:.2f} Td ({self._esc(s)}) Tj ET"
        )

    def rect(self, x, top, w, h, fill=None, stroke=None):
        y = self.H - top - h
        ops = []
        if fill:
            ops.append("%.3f %.3f %.3f rg" % fill)
        if stroke:
            ops.append("%.3f %.3f %.3f RG 0.5 w" % stroke)
        ops.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re")
        ops.append("B" if fill and stroke else ("f" if fill else "S"))
        self.pages[-1].append(" ".join(ops))

    def save(self, path):
        n = len(self.pages)
        kids = " ".join(f"{5 + 2 * i} 0 R" for i in range(n))
        objs = [
            "<< /Type /Catalog /Pages 2 0 R >>",
            f"<< /Type /Pages /Kids [{kids}] /Count {n} >>",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        ]
        for i, ops in enumerate(self.pages):
            stream = "\n".join(ops)
            objs.append(
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {self.W} {self.H}] "
                f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {6 + 2 * i} 0 R >>"
            )
            objs.append(f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream")
        out = bytearray(b"%PDF-1.4\n")
        offsets = []
        for num, body in enumerate(objs, start=1):
            offsets.append(len(out))
            out += f"{num} 0 obj\n".encode() + body.encode("latin-1") + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
        for off in offsets:
            out += f"{off:010d} 00000 n \n".encode()
        out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
                f"startxref\n{xref}\n%%EOF\n").encode()
        Path(path).write_bytes(bytes(out))


def _rgb(h):
    return tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))


def build_pdf(path, project_label, rows):
    pdf = SimplePDF()
    M, PAD, LINE, BOTTOM = 30, 5, 13, 60
    cols = [("Project Name", 150), ("Address", 210), ("Price", 100), ("Date", 75)]
    total_w = sum(w for _, w in cols)
    head_c, stripe_c, ink, grey = _rgb("#312e81"), _rgb("#eef2ff"), _rgb("#1e293b"), _rgb("#cbd5e1")
    page_no = 0

    def start_page():
        nonlocal page_no
        page_no += 1
        pdf.new_page()
        pdf.text(pdf.W / 2 - 18, pdf.H - 40, f"Page {page_no}", 8, color=(0.4, 0.4, 0.4))

    def draw_header(top):
        pdf.rect(M, top, total_w, 22, fill=head_c)
        x = M
        for name, w in cols:
            pdf.text(x + PAD, top + 6, name, 10, True, (1, 1, 1))
            x += w
        return top + 22

    start_page()
    pdf.text(M, 34, "Payment Records", 20, True, head_c)
    pdf.text(M, 64, f"Project: {project_label}", 10, color=ink)
    pdf.text(M, 78, f"Created: {date.today().strftime(DATE_FMT)}     Payments: {len(rows)}",
             10, color=ink)
    y = draw_header(100)

    for idx, (_pid, project, address, show, _code, iso) in enumerate(rows):
        cells = [project, address, show, datetime.strptime(iso, "%Y-%m-%d").strftime(DATE_FMT)]
        wrapped = [textwrap.wrap(t, max(4, int((w - 2 * PAD) / 6.0))) or [""]
                   for (_n, w), t in zip(cols, cells)]
        h = max(len(lines) for lines in wrapped) * LINE + 2 * PAD - 2
        if y + h > pdf.H - BOTTOM:
            start_page()
            y = draw_header(40)
        if idx % 2:
            pdf.rect(M, y, total_w, h, fill=stripe_c)
        x = M
        for (_n, w), lines in zip(cols, wrapped):
            for k, line in enumerate(lines):
                pdf.text(x + PAD, y + PAD + k * LINE, line, 10, color=ink)
            x += w
        pdf.rect(M, y, total_w, h, stroke=grey)
        y += h

    if y + 30 > pdf.H - BOTTOM:
        start_page()
        y = 40
    pdf.text(M, y + 14, f"Total: {coded_total(rows)}", 12, True, head_c)
    pdf.save(path)


def pdf_unsupported(rows):
    for r in rows:
        for s in (r[1], r[2]):
            try:
                s.encode("cp1252")
            except UnicodeEncodeError:
                return True
    return False


# ----------------------------------------------------------------------
# Add Payment window
# ----------------------------------------------------------------------
class AddDialog(tk.Toplevel):
    def __init__(self, parent, db, on_saved):
        super().__init__(parent, bg=BG)
        self.db, self.on_saved = db, on_saved
        self.title("Add Payment")
        self.resizable(False, False)
        self.transient(parent)
        self.geometry(f"+{parent.winfo_rootx() + 170}+{parent.winfo_rooty() + 110}")

        body = tk.Frame(self, bg=BG, padx=26, pady=18)
        body.pack()
        tk.Label(body, text="Add Payment", bg=BG, fg=INK, font=(FONT, 15, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        def label(r, text):
            tk.Label(body, text=text, bg=BG, fg=MUTED, font=(FONT, 10)).grid(
                row=r, column=0, sticky="w", pady=7, padx=(0, 16))

        label(1, "Project name")
        self.project = ttk.Combobox(body, values=db.projects(), width=34, font=(FONT, 10))
        self.project.grid(row=1, column=1, pady=7)
        self.project.bind("<<ComboboxSelected>>", self.fill_address)
        self.project.bind("<FocusOut>", self.fill_address)

        label(2, "Address")
        self.address = ttk.Entry(body, width=37, font=(FONT, 10))
        self.address.grid(row=2, column=1, pady=7)

        label(3, "Price (number)")
        self.price = ttk.Entry(body, width=37, font=(FONT, 10))
        self.price.grid(row=3, column=1, pady=7)

        label(4, "Date (DD-MM-YYYY)")
        self.date = ttk.Entry(body, width=37, font=(FONT, 10))
        self.date.insert(0, date.today().strftime(DATE_FMT))
        self.date.grid(row=4, column=1, pady=7)

        tk.Label(body, text="The number is visible only here. After saving it is shown as code.",
                 bg=BG, fg=MUTED, font=(FONT, 9)).grid(row=5, column=0, columnspan=2, pady=(6, 4))

        btns = tk.Frame(body, bg=BG)
        btns.grid(row=6, column=0, columnspan=2)
        JumpButton(btns, "Save", self.save, ACCENT, ACCENT_H, width=110).pack(side="left", padx=6)
        JumpButton(btns, "Cancel", self.destroy, "#64748b", "#94a3b8", width=110).pack(side="left", padx=6)

        self.bind("<Return>", lambda e: self.save())
        self.bind("<Escape>", lambda e: self.destroy())
        fade_in(self)
        self.wait_visibility()
        self.grab_set()
        self.project.focus_set()

    def fill_address(self, _event=None):
        name = self.project.get().strip()
        if name and not self.address.get().strip():
            addr = self.db.address_of(name)
            if addr:
                self.address.insert(0, addr)

    def save(self):
        if not self.winfo_exists():
            return
        project = self.project.get().strip()
        address = self.address.get().strip()
        price = re.sub(r"[,\s]", "", self.price.get())
        date_text = self.date.get().strip()

        if not project or not address or not price or not date_text:
            messagebox.showwarning("Missing data", "Please fill all the fields.", parent=self)
            return
        if not price.isdigit():
            messagebox.showwarning("Bad price", "Price must be a whole number.", parent=self)
            return
        try:
            iso = datetime.strptime(date_text, DATE_FMT).strftime("%Y-%m-%d")
        except ValueError:
            messagebox.showwarning("Bad date", "Use date format DD-MM-YYYY.", parent=self)
            return

        code = encode_price(price)
        new_id = self.db.add(project, address, code, add_noise(code), iso)
        self.on_saved(project, new_id)
        self.destroy()


# ----------------------------------------------------------------------
# Main window
# ----------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Payment Records")
        self.geometry("1000x640")
        self.minsize(860, 500)
        self.configure(bg=BG)
        self.db = DB(DB_FILE)

        self.row_tag = {}
        self._gen = 0
        self._hover = None
        self._flash_job = None
        self._status_job = None
        self._toast = None
        self._shown_count = 0

        self._setup_style()
        Header(self, "Payment Records", "Encoded price register", HEAD_A, HEAD_B).pack(fill="x")

        # toolbar
        bar = tk.Frame(self, bg=BG, padx=16, pady=6)
        bar.pack(fill="x")
        tk.Label(bar, text="Project", bg=BG, fg=MUTED, font=(FONT, 10, "bold")).pack(side="left")
        self.filter_var = tk.StringVar(value=ALL)
        self.filter_box = ttk.Combobox(bar, textvariable=self.filter_var, state="readonly",
                                       width=30, font=(FONT, 10))
        self.filter_box.pack(side="left", padx=10)
        self.filter_box.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        buttons = [
            ("Add Payment", self.open_add, ACCENT, ACCENT_H),
            ("Create PDF", self.make_pdf, GREEN, GREEN_H),
            ("Print", self.print_table, SKY, SKY_H),
            ("Delete Selected", self.delete_selected, ROSE, ROSE_H),
        ]
        for text, cmd, c, h in reversed(buttons):
            JumpButton(bar, text, cmd, c, h, width=138 if len(text) > 12 else 118).pack(side="right", padx=4)

        # table
        wrap = tk.Frame(self, bg=BG, padx=16)
        wrap.pack(fill="both", expand=True)
        cols = ("project", "address", "price", "date")
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="browse")
        for col, text, w, stretch in (("project", "Project Name", 230, False),
                                      ("address", "Address", 360, True),
                                      ("price", "Price", 170, False),
                                      ("date", "Date", 110, False)):
            self.tree.heading(col, text=text, anchor="w")
            self.tree.column(col, width=w, anchor="w", stretch=stretch)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.tag_configure("rowa", background=ROW_A)
        self.tree.tag_configure("rowb", background=ROW_B)
        self.tree.tag_configure("hover", background=ROW_HOVER)
        self.tree.tag_configure("flash", background=FLASH)
        self.tree.bind("<Motion>", self.on_hover)
        self.tree.bind("<Leave>", self.clear_hover)
        self.empty = tk.Label(self.tree, text="No payments yet. Click Add Payment to start.",
                              bg=ROW_A, fg=MUTED, font=(FONT, 11))

        # status cards
        stat = tk.Frame(self, bg=BG, padx=16, pady=12)
        stat.pack(fill="x")
        self.count_var, self.total_var = tk.StringVar(value="0"), tk.StringVar(value="")
        self._card(stat, "Payments", self.count_var, 8).pack(side="left")
        self._card(stat, "Total (coded)", self.total_var, 22).pack(side="left", padx=12)

        self.refresh()
        fade_in(self)

    # ---------- setup ----------
    def _setup_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("Treeview", background=ROW_A, fieldbackground=ROW_A, foreground=INK,
                    rowheight=32, borderwidth=0, font=(FONT, 10))
        s.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "white")])
        s.configure("Treeview.Heading", background="#312e81", foreground="white",
                    font=(FONT, 10, "bold"), relief="flat", padding=8)
        s.map("Treeview.Heading", background=[("active", "#4338ca")])
        s.configure("TCombobox", padding=5)
        s.map("TCombobox", fieldbackground=[("readonly", "white")],
              selectbackground=[("readonly", "white")], selectforeground=[("readonly", INK)])
        s.configure("TEntry", padding=6)
        s.configure("Vertical.TScrollbar", troughcolor=BG, background="#c7d2fe", borderwidth=0)
        self.option_add("*TCombobox*Listbox.font", (FONT, 10))
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)

    @staticmethod
    def _card(parent, title, var, width):
        card = tk.Frame(parent, bg="white", padx=16, pady=8,
                        highlightbackground="#e2e8f0", highlightthickness=1)
        tk.Label(card, text=title, bg="white", fg=MUTED, font=(FONT, 9)).pack(anchor="w")
        tk.Label(card, textvariable=var, bg="white", fg=ACCENT, font=(FONT, 15, "bold"),
                 width=width, anchor="w").pack(anchor="w")
        return card

    # ---------- helpers ----------
    def current_rows(self):
        return self.db.rows(self.filter_var.get())

    @staticmethod
    def show_date(iso):
        return datetime.strptime(iso, "%Y-%m-%d").strftime(DATE_FMT)

    # ---------- table refresh (rows glide in one by one) ----------
    def refresh(self, select_project=None, flash_id=None):
        self._gen += 1
        gen = self._gen
        self.clear_hover()
        if self._flash_job:
            self.after_cancel(self._flash_job)
            self._flash_job = None

        self.filter_box["values"] = [ALL] + self.db.projects()
        if select_project:
            self.filter_var.set(select_project)
        if self.filter_var.get() not in self.filter_box["values"]:
            self.filter_var.set(ALL)

        self.tree.delete(*self.tree.get_children())
        self.row_tag.clear()
        rows = self.current_rows()

        if rows:
            self.empty.place_forget()
        else:
            self.empty.place(relx=0.5, rely=0.45, anchor="center")
        self.animate_status(len(rows), coded_total(rows) if rows else "")

        chunk = 1 if len(rows) <= 40 else 60

        def add_batch(i):
            if gen != self._gen:
                return
            for k in range(i, min(i + chunk, len(rows))):
                pid, project, address, show, _code, iso = rows[k]
                tag = "rowb" if k % 2 else "rowa"
                self.row_tag[str(pid)] = tag
                self.tree.insert("", "end", iid=str(pid), tags=(tag,),
                                 values=(project, address, show, self.show_date(iso)))
            if i + chunk < len(rows):
                self.after(16, add_batch, i + chunk)
            elif flash_id is not None and str(flash_id) in self.row_tag:
                self.flash_row(str(flash_id))

        add_batch(0)

    def flash_row(self, iid):
        """New row glows green, then fades into its normal color."""
        stripe = self.row_tag[iid]
        end = ROW_A if stripe == "rowa" else ROW_B
        self.row_tag[iid] = "flash"
        self.tree.item(iid, tags=("flash",))
        self.tree.see(iid)
        start = time.time()

        def step():
            if iid not in self.row_tag:
                return
            p = min((time.time() - start) / 1.2, 1.0)
            self.tree.tag_configure("flash", background=lerp_color(FLASH, end, ease_out(p)))
            if p < 1.0:
                self._flash_job = self.after(16, step)
            else:
                self.row_tag[iid] = stripe
                self.tree.item(iid, tags=(stripe,))
                self._flash_job = None

        step()

    def animate_status(self, count, total_text):
        """Count goes up smoothly and the coded total types itself in."""
        if self._status_job:
            self.after_cancel(self._status_job)
        start_count, start = self._shown_count, time.time()

        def step():
            e = ease_out((time.time() - start) / 0.6)
            self._shown_count = round(start_count + (count - start_count) * e)
            self.count_var.set(str(self._shown_count))
            self.total_var.set(total_text[:round(len(total_text) * e)])
            if e < 1.0:
                self._status_job = self.after(16, step)
            else:
                self._status_job = None

        step()

    # ---------- row hover ----------
    def on_hover(self, e):
        iid = self.tree.identify_row(e.y)
        if iid == self._hover:
            return
        self.clear_hover()
        if iid and iid in self.row_tag:
            self.tree.item(iid, tags=("hover",))
            self._hover = iid

    def clear_hover(self, _e=None):
        if self._hover and self._hover in self.row_tag:
            self.tree.item(self._hover, tags=(self.row_tag[self._hover],))
        self._hover = None

    # ---------- toast message (slides in, waits, slides out) ----------
    def toast(self, text):
        if self._toast is not None and self._toast.winfo_exists():
            self._toast.destroy()
        lbl = tk.Label(self, text=text, bg="#0f172a", fg="white", font=(FONT, 10),
                       padx=18, pady=10)
        self._toast = lbl
        start = time.time()

        def step():
            if not lbl.winfo_exists():
                return
            t = time.time() - start
            if t < 0.3:
                p = ease_out(t / 0.3)
            elif t < 2.6:
                p = 1.0
            elif t < 2.9:
                p = 1 - ease_out((t - 2.6) / 0.3)
            else:
                lbl.destroy()
                return
            lbl.place(relx=1.0, rely=1.0, x=-24, y=-20 + (1 - p) * 70, anchor="se")
            self.after(16, step)

        step()

    # ---------- actions ----------
    def open_add(self):
        def saved(project, pid):
            self.refresh(select_project=project, flash_id=pid)
            self.toast("Payment saved")

        AddDialog(self, self.db, saved)

    def delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Delete", "Select a row first.")
            return
        if messagebox.askyesno("Delete", "Delete the selected payment?"):
            self.db.delete(int(sel[0]))
            self.refresh()
            self.toast("Payment deleted")

    def make_pdf(self):
        rows = self.current_rows()
        if not rows:
            messagebox.showinfo("Create PDF", "Nothing to put in the PDF.")
            return
        label = self.filter_var.get()
        safe = re.sub(r"[^\w\-]+", "_", label).strip("_") or "all"
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf", filetypes=[("PDF file", "*.pdf")],
            initialfile=f"payments_{safe}_{date.today().strftime('%d-%m-%Y')}.pdf")
        if not path:
            return
        try:
            build_pdf(path, label, rows)
        except OSError as err:
            messagebox.showerror("Create PDF", f"Could not save the PDF:\n{err}")
            return
        self.toast("PDF created")
        open_file(path)
        if pdf_unsupported(rows):
            messagebox.showinfo(
                "Create PDF",
                "Some names or addresses contain non-English letters. The PDF can show "
                "them only as '?'. Use the Print button for those, the browser shows them correctly.")

    def print_table(self):
        rows = self.current_rows()
        if not rows:
            messagebox.showinfo("Print", "Nothing to print.")
            return
        body = "".join(
            f"<tr><td>{html.escape(r[1])}</td><td>{html.escape(r[2])}</td>"
            f"<td>{html.escape(r[3])}</td><td>{self.show_date(r[5])}</td></tr>"
            for r in rows
        )
        page = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Payment Records</title>
<style>
 body{{font-family:Arial,sans-serif;margin:30px}}
 table{{border-collapse:collapse;width:100%}}
 th,td{{border:1px solid #444;padding:6px 10px;text-align:left}}
 th{{background:#312e81;color:#fff}}
 tr:nth-child(even) td{{background:#eef2ff}}
</style></head><body>
<h2>Payment Records</h2>
<p>Project: <b>{html.escape(self.filter_var.get())}</b> &nbsp;|&nbsp; Printed: {date.today().strftime(DATE_FMT)}</p>
<table><tr><th>Project Name</th><th>Address</th><th>Price</th><th>Date</th></tr>{body}</table>
<p><b>Payments: {len(rows)} &nbsp;|&nbsp; Total: {coded_total(rows)}</b></p>
<script>window.onload=function(){{window.print();}}</script>
</body></html>"""
        path = os.path.join(tempfile.gettempdir(), "payment_records_print.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(page)
        webbrowser.open("file://" + path.replace("\\", "/"))


if __name__ == "__main__":
    App().mainloop()
