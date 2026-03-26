#!/usr/bin/env python3
"""
London Properties - Tenant / Room / Rent Manager (Tkinter + SQLite)

Built from a coursework-style write-up: stores tenants, rooms, payments; validates inputs;
does basic rent payment calculations and prints a simple receipt.

Notes
- This is a clean rebuild, not a byte-for-byte recovery of any original code.
- Database file is created next to this script as: london_properties.db
- Optional logo: put a file named 'logo.gif' in the same folder as this script.

Tested with: Python 3.10+ (should work on 3.8+)
"""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog


DB_FILENAME = "london_properties.db"
LOGO_FILENAME = "logo.gif"


# -----------------------------
# Validation helpers
# -----------------------------
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z \-']*$")
PHONE_RE = re.compile(r"^[0-9 +()-]{6,}$")  # permissive, but blocks letters
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_name(s: str) -> bool:
    s = (s or "").strip()
    return bool(NAME_RE.match(s))


def is_valid_phone(s: str) -> bool:
    s = (s or "").strip()
    return bool(PHONE_RE.match(s)) and not any(c.isalpha() for c in s)


def is_valid_email(s: str) -> bool:
    s = (s or "").strip()
    return bool(EMAIL_RE.match(s))


def is_valid_id(s: str) -> bool:
    s = (s or "").strip()
    return s.isdigit() and len(s) <= 6


def money_int(s: str) -> int:
    s = (s or "").strip()
    if s == "":
        raise ValueError("Empty amount")
    if not re.fullmatch(r"[0-9]+", s):
        raise ValueError("Amount must be digits only")
    return int(s)


# -----------------------------
# Database layer
# -----------------------------
class DB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self._init_schema()

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

    def _init_schema(self):
        cur = self.conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS Tenant (
            tenantId TEXT PRIMARY KEY,
            fname TEXT NOT NULL,
            sname TEXT NOT NULL,
            email TEXT NOT NULL,
            telephone TEXT NOT NULL
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS Room (
            roomId TEXT PRIMARY KEY,
            price INTEGER NOT NULL,
            availability TEXT NOT NULL DEFAULT 'Available',
            tenantId TEXT NULL,
            FOREIGN KEY (tenantId) REFERENCES Tenant(tenantId)
                ON UPDATE CASCADE
                ON DELETE SET NULL
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS Rent (
            rentId TEXT PRIMARY KEY,
            roomId TEXT NOT NULL,
            tenantId TEXT NOT NULL,
            dueDate TEXT NOT NULL,
            paid TEXT NOT NULL CHECK (paid IN ('Y','N')),
            payment INTEGER NOT NULL,
            datePaid TEXT NOT NULL,
            FOREIGN KEY (roomId) REFERENCES Room(roomId)
                ON UPDATE CASCADE
                ON DELETE CASCADE,
            FOREIGN KEY (tenantId) REFERENCES Tenant(tenantId)
                ON UPDATE CASCADE
                ON DELETE CASCADE
        );
        """)

        self.conn.commit()

    # ---------- Tenant ----------
    def upsert_tenant(self, tenantId: str, fname: str, sname: str, email: str, telephone: str):
        self.conn.execute("""
            INSERT INTO Tenant(tenantId, fname, sname, email, telephone)
            VALUES(?,?,?,?,?)
            ON CONFLICT(tenantId) DO UPDATE SET
                fname=excluded.fname,
                sname=excluded.sname,
                email=excluded.email,
                telephone=excluded.telephone;
        """, (tenantId, fname, sname, email, telephone))
        self.conn.commit()

    def delete_tenant(self, tenantId: str):
        self.conn.execute("DELETE FROM Tenant WHERE tenantId=?", (tenantId,))
        self.conn.commit()

    def get_tenant(self, tenantId: str):
        cur = self.conn.execute("SELECT tenantId, fname, sname, email, telephone FROM Tenant WHERE tenantId=?", (tenantId,))
        return cur.fetchone()

    def list_tenants(self):
        cur = self.conn.execute("SELECT tenantId, fname, sname, email, telephone FROM Tenant ORDER BY tenantId;")
        return cur.fetchall()

    # ---------- Room ----------
    def upsert_room(self, roomId: str, price: int, availability: str, tenantId: str | None):
        self.conn.execute("""
            INSERT INTO Room(roomId, price, availability, tenantId)
            VALUES(?,?,?,?)
            ON CONFLICT(roomId) DO UPDATE SET
                price=excluded.price,
                availability=excluded.availability,
                tenantId=excluded.tenantId;
        """, (roomId, price, availability, tenantId))
        self.conn.commit()

    def delete_room(self, roomId: str):
        self.conn.execute("DELETE FROM Room WHERE roomId=?", (roomId,))
        self.conn.commit()

    def get_room(self, roomId: str):
        cur = self.conn.execute("SELECT roomId, price, availability, tenantId FROM Room WHERE roomId=?", (roomId,))
        return cur.fetchone()

    def list_rooms(self):
        cur = self.conn.execute("SELECT roomId, price, availability, tenantId FROM Room ORDER BY roomId;")
        return cur.fetchall()

    # ---------- Rent ----------
    def add_rent(self, rentId: str, roomId: str, tenantId: str, dueDate: str, paid: str, payment: int, datePaid: str):
        self.conn.execute("""
            INSERT INTO Rent(rentId, roomId, tenantId, dueDate, paid, payment, datePaid)
            VALUES(?,?,?,?,?,?,?);
        """, (rentId, roomId, tenantId, dueDate, paid, payment, datePaid))
        self.conn.commit()

    def delete_rent(self, rentId: str):
        self.conn.execute("DELETE FROM Rent WHERE rentId=?", (rentId,))
        self.conn.commit()

    def get_rent(self, rentId: str):
        cur = self.conn.execute("""
            SELECT rentId, roomId, tenantId, dueDate, paid, payment, datePaid
            FROM Rent WHERE rentId=?;
        """, (rentId,))
        return cur.fetchone()

    def list_rents(self):
        cur = self.conn.execute("""
            SELECT rentId, roomId, tenantId, dueDate, paid, payment, datePaid
            FROM Rent ORDER BY datePaid DESC, rentId;
        """)
        return cur.fetchall()

    # ---------- Joins / helpers ----------
    def room_price(self, roomId: str) -> int | None:
        cur = self.conn.execute("SELECT price FROM Room WHERE roomId=?", (roomId,))
        row = cur.fetchone()
        return int(row[0]) if row else None

    def tenant_name_phone(self, tenantId: str):
        cur = self.conn.execute("SELECT fname, sname, telephone, email FROM Tenant WHERE tenantId=?", (tenantId,))
        return cur.fetchone()


# -----------------------------
# UI
# -----------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("London Properties - Tenant / Room / Payments")
        self.geometry("980x620")
        self.minsize(920, 560)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.db = DB(os.path.join(script_dir, DB_FILENAME))

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self._style()
        self._build_header()
        self._build_tabs()
        self.refresh_all()

    def _style(self):
        # Keep defaults; just slightly nicer padding
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TButton", padding=6)
        style.configure("TLabel", padding=2)
        style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("SubHeader.TLabel", font=("Segoe UI", 10))

    def _build_header(self):
        header = ttk.Frame(self)
        header.pack(fill="x", padx=12, pady=10)

        # Logo (optional)
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), LOGO_FILENAME)
        self._logo_img = None
        if os.path.exists(logo_path):
            try:
                self._logo_img = tk.PhotoImage(file=logo_path)
                ttk.Label(header, image=self._logo_img).pack(side="left", padx=(0, 10))
            except Exception:
                self._logo_img = None

        title_box = ttk.Frame(header)
        title_box.pack(side="left", fill="x", expand=True)

        ttk.Label(title_box, text="London Properties", style="Header.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="Simple database app: Tenants • Rooms • Receipts/Payments", style="SubHeader.TLabel").pack(anchor="w")

        ttk.Button(header, text="Backup DB…", command=self.backup_db).pack(side="right")

    def _build_tabs(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.tab_tenants = ttk.Frame(self.nb)
        self.tab_rooms = ttk.Frame(self.nb)
        self.tab_payments = ttk.Frame(self.nb)

        self.nb.add(self.tab_tenants, text="Tenants")
        self.nb.add(self.tab_rooms, text="Rooms")
        self.nb.add(self.tab_payments, text="Receipts / Payments")

        self._build_tenants_tab()
        self._build_rooms_tab()
        self._build_payments_tab()

    # ---------------- Tenants tab ----------------
    def _build_tenants_tab(self):
        top = ttk.Frame(self.tab_tenants)
        top.pack(fill="x", pady=8)

        form = ttk.LabelFrame(top, text="Add / Update Tenant")
        form.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.t_tenantId = tk.StringVar()
        self.t_fname = tk.StringVar()
        self.t_sname = tk.StringVar()
        self.t_email = tk.StringVar()
        self.t_phone = tk.StringVar()

        self._grid_row(form, 0, "Tenant ID (digits):", self.t_tenantId)
        self._grid_row(form, 1, "First name:", self.t_fname)
        self._grid_row(form, 2, "Surname:", self.t_sname)
        self._grid_row(form, 3, "Email:", self.t_email)
        self._grid_row(form, 4, "Telephone:", self.t_phone)

        btns = ttk.Frame(form)
        btns.grid(row=5, column=0, columnspan=2, sticky="ew", padx=8, pady=8)
        ttk.Button(btns, text="Save / Update", command=self.save_tenant).pack(side="left")
        ttk.Button(btns, text="Search by ID", command=self.search_tenant).pack(side="left", padx=6)
        ttk.Button(btns, text="Clear", command=self.clear_tenant_form).pack(side="left", padx=6)
        ttk.Button(btns, text="Delete Selected", command=self.delete_selected_tenant).pack(side="right")

        list_box = ttk.LabelFrame(top, text="Tenants")
        list_box.pack(side="left", fill="both", expand=True)

        cols = ("tenantId", "fname", "sname", "email", "telephone")
        self.tree_tenants = ttk.Treeview(list_box, columns=cols, show="headings", height=10)
        for c, w in zip(cols, (80, 120, 120, 200, 120)):
            self.tree_tenants.heading(c, text=c)
            self.tree_tenants.column(c, width=w, anchor="w")
        self.tree_tenants.pack(fill="both", expand=True, padx=6, pady=6)
        self.tree_tenants.bind("<<TreeviewSelect>>", self.on_select_tenant)

        ttk.Label(self.tab_tenants, text="Tip: select a row to load it into the form, then edit and Save/Update.").pack(anchor="w", padx=4)

    def _grid_row(self, parent, row, label, var):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        parent.columnconfigure(1, weight=1)

    def clear_tenant_form(self):
        for v in (self.t_tenantId, self.t_fname, self.t_sname, self.t_email, self.t_phone):
            v.set("")

    def on_select_tenant(self, _evt=None):
        sel = self.tree_tenants.selection()
        if not sel:
            return
        vals = self.tree_tenants.item(sel[0], "values")
        self.t_tenantId.set(vals[0])
        self.t_fname.set(vals[1])
        self.t_sname.set(vals[2])
        self.t_email.set(vals[3])
        self.t_phone.set(vals[4])

    def save_tenant(self):
        tenantId = self.t_tenantId.get().strip()
        fname = self.t_fname.get().strip()
        sname = self.t_sname.get().strip()
        email = self.t_email.get().strip()
        phone = self.t_phone.get().strip()

        if not is_valid_id(tenantId):
            return messagebox.showerror("Validation", "Tenant ID must be digits only (up to 6 digits).")
        if not is_valid_name(fname):
            return messagebox.showerror("Validation", "First name must be letters only.")
        if not is_valid_name(sname):
            return messagebox.showerror("Validation", "Surname must be letters only.")
        if not is_valid_email(email):
            return messagebox.showerror("Validation", "Email looks invalid.")
        if not is_valid_phone(phone):
            return messagebox.showerror("Validation", "Telephone must be numbers (no letters).")

        self.db.upsert_tenant(tenantId, fname, sname, email, phone)
        self.refresh_all()
        messagebox.showinfo("Saved", "Tenant saved/updated.")

    def search_tenant(self):
        tenantId = self.t_tenantId.get().strip()
        if not is_valid_id(tenantId):
            return messagebox.showerror("Search", "Enter a numeric Tenant ID to search.")
        row = self.db.get_tenant(tenantId)
        if not row:
            return messagebox.showinfo("Search", "No tenant found with that ID.")
        self.t_tenantId.set(row[0])
        self.t_fname.set(row[1])
        self.t_sname.set(row[2])
        self.t_email.set(row[3])
        self.t_phone.set(row[4])

    def delete_selected_tenant(self):
        sel = self.tree_tenants.selection()
        if not sel:
            return messagebox.showinfo("Delete", "Select a tenant row first.")
        tenantId = self.tree_tenants.item(sel[0], "values")[0]
        if messagebox.askyesno("Confirm delete", f"Delete tenant {tenantId}? (Rooms referencing this tenant will be unassigned.)"):
            self.db.delete_tenant(tenantId)
            self.refresh_all()

    # ---------------- Rooms tab ----------------
    def _build_rooms_tab(self):
        top = ttk.Frame(self.tab_rooms)
        top.pack(fill="x", pady=8)

        form = ttk.LabelFrame(top, text="Add / Update Room")
        form.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.r_roomId = tk.StringVar()
        self.r_price = tk.StringVar()
        self.r_availability = tk.StringVar(value="Available")
        self.r_tenantId = tk.StringVar()

        self._grid_row(form, 0, "Room ID (digits):", self.r_roomId)
        self._grid_row(form, 1, "Price per month (digits):", self.r_price)

        ttk.Label(form, text="Availability:").grid(row=2, column=0, sticky="w", padx=8, pady=4)
        ttk.Combobox(form, textvariable=self.r_availability, values=("Available", "Occupied"), state="readonly").grid(row=2, column=1, sticky="ew", padx=8, pady=4)

        ttk.Label(form, text="Assigned Tenant ID (optional):").grid(row=3, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(form, textvariable=self.r_tenantId).grid(row=3, column=1, sticky="ew", padx=8, pady=4)

        btns = ttk.Frame(form)
        btns.grid(row=4, column=0, columnspan=2, sticky="ew", padx=8, pady=8)
        ttk.Button(btns, text="Save / Update", command=self.save_room).pack(side="left")
        ttk.Button(btns, text="Search by ID", command=self.search_room).pack(side="left", padx=6)
        ttk.Button(btns, text="Clear", command=self.clear_room_form).pack(side="left", padx=6)
        ttk.Button(btns, text="Delete Selected", command=self.delete_selected_room).pack(side="right")

        list_box = ttk.LabelFrame(top, text="Rooms")
        list_box.pack(side="left", fill="both", expand=True)

        cols = ("roomId", "price", "availability", "tenantId")
        self.tree_rooms = ttk.Treeview(list_box, columns=cols, show="headings", height=10)
        for c, w in zip(cols, (80, 120, 120, 120)):
            self.tree_rooms.heading(c, text=c)
            self.tree_rooms.column(c, width=w, anchor="w")
        self.tree_rooms.pack(fill="both", expand=True, padx=6, pady=6)
        self.tree_rooms.bind("<<TreeviewSelect>>", self.on_select_room)

        ttk.Label(self.tab_rooms, text="Tip: if you assign a Tenant ID, make sure that tenant exists.").pack(anchor="w", padx=4)

    def clear_room_form(self):
        for v in (self.r_roomId, self.r_price, self.r_tenantId):
            v.set("")
        self.r_availability.set("Available")

    def on_select_room(self, _evt=None):
        sel = self.tree_rooms.selection()
        if not sel:
            return
        vals = self.tree_rooms.item(sel[0], "values")
        self.r_roomId.set(vals[0])
        self.r_price.set(str(vals[1]))
        self.r_availability.set(vals[2])
        self.r_tenantId.set(vals[3] if vals[3] is not None else "")

    def save_room(self):
        roomId = self.r_roomId.get().strip()
        price_s = self.r_price.get().strip()
        availability = self.r_availability.get().strip()
        tenantId = self.r_tenantId.get().strip() or None

        if not is_valid_id(roomId):
            return messagebox.showerror("Validation", "Room ID must be digits only (up to 6 digits).")
        try:
            price = money_int(price_s)
        except ValueError as e:
            return messagebox.showerror("Validation", str(e))

        if tenantId is not None:
            if not is_valid_id(tenantId):
                return messagebox.showerror("Validation", "Assigned Tenant ID must be digits only.")
            if not self.db.get_tenant(tenantId):
                return messagebox.showerror("Validation", "That Tenant ID does not exist yet. Add the tenant first.")

        self.db.upsert_room(roomId, price, availability, tenantId)
        self.refresh_all()
        messagebox.showinfo("Saved", "Room saved/updated.")

    def search_room(self):
        roomId = self.r_roomId.get().strip()
        if not is_valid_id(roomId):
            return messagebox.showerror("Search", "Enter a numeric Room ID to search.")
        row = self.db.get_room(roomId)
        if not row:
            return messagebox.showinfo("Search", "No room found with that ID.")
        self.r_roomId.set(row[0])
        self.r_price.set(str(row[1]))
        self.r_availability.set(row[2])
        self.r_tenantId.set(row[3] or "")

    def delete_selected_room(self):
        sel = self.tree_rooms.selection()
        if not sel:
            return messagebox.showinfo("Delete", "Select a room row first.")
        roomId = self.tree_rooms.item(sel[0], "values")[0]
        if messagebox.askyesno("Confirm delete", f"Delete room {roomId}? (Any payment records for this room will also be deleted.)"):
            self.db.delete_room(roomId)
            self.refresh_all()

    # ---------------- Payments tab ----------------
    def _build_payments_tab(self):
        top = ttk.Frame(self.tab_payments)
        top.pack(fill="x", pady=8)

        form = ttk.LabelFrame(top, text="Record a Payment + Print Receipt")
        form.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.p_rentId = tk.StringVar()
        self.p_roomId = tk.StringVar()
        self.p_tenantId = tk.StringVar()
        self.p_dueDate = tk.StringVar()
        self.p_paid = tk.StringVar(value="Y")
        self.p_payment = tk.StringVar()
        self.p_datePaid = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))

        self._grid_row(form, 0, "Payment/Receipt ID (digits):", self.p_rentId)
        self._grid_row(form, 1, "Room ID:", self.p_roomId)
        self._grid_row(form, 2, "Tenant ID:", self.p_tenantId)

        ttk.Label(form, text="Due date (YYYY-MM-DD):").grid(row=3, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(form, textvariable=self.p_dueDate).grid(row=3, column=1, sticky="ew", padx=8, pady=4)

        ttk.Label(form, text="Paid (Y/N):").grid(row=4, column=0, sticky="w", padx=8, pady=4)
        ttk.Combobox(form, textvariable=self.p_paid, values=("Y", "N"), state="readonly").grid(row=4, column=1, sticky="ew", padx=8, pady=4)

        ttk.Label(form, text="Payment amount (digits):").grid(row=5, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(form, textvariable=self.p_payment).grid(row=5, column=1, sticky="ew", padx=8, pady=4)

        ttk.Label(form, text="Date paid (YYYY-MM-DD):").grid(row=6, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(form, textvariable=self.p_datePaid).grid(row=6, column=1, sticky="ew", padx=8, pady=4)

        btns = ttk.Frame(form)
        btns.grid(row=7, column=0, columnspan=2, sticky="ew", padx=8, pady=8)
        ttk.Button(btns, text="Record Payment", command=self.record_payment).pack(side="left")
        ttk.Button(btns, text="Calculate Only", command=self.calculate_payment).pack(side="left", padx=6)
        ttk.Button(btns, text="Clear", command=self.clear_payment_form).pack(side="left", padx=6)
        ttk.Button(btns, text="Delete Selected", command=self.delete_selected_payment).pack(side="right")

        calc_box = ttk.LabelFrame(top, text="Calculation Result")
        calc_box.pack(side="left", fill="both", expand=True)

        self.calc_text = tk.Text(calc_box, height=12, wrap="word")
        self.calc_text.pack(fill="both", expand=True, padx=6, pady=6)
        self.calc_text.configure(state="disabled")

        list_box = ttk.LabelFrame(self.tab_payments, text="Payments / Receipts")
        list_box.pack(fill="both", expand=True, pady=10)

        cols = ("rentId", "roomId", "tenantId", "dueDate", "paid", "payment", "datePaid")
        self.tree_payments = ttk.Treeview(list_box, columns=cols, show="headings")
        for c, w in zip(cols, (90, 80, 80, 110, 60, 90, 110)):
            self.tree_payments.heading(c, text=c)
            self.tree_payments.column(c, width=w, anchor="w")
        self.tree_payments.pack(fill="both", expand=True, padx=6, pady=6)
        self.tree_payments.bind("<<TreeviewSelect>>", self.on_select_payment)

        bottom_btns = ttk.Frame(self.tab_payments)
        bottom_btns.pack(fill="x")
        ttk.Button(bottom_btns, text="Print Receipt for Selected…", command=self.print_selected_receipt).pack(side="left")
        ttk.Button(bottom_btns, text="Generate Overdue Email for Selected…", command=self.overdue_email_for_selected).pack(side="left", padx=8)

    def clear_payment_form(self):
        for v in (self.p_rentId, self.p_roomId, self.p_tenantId, self.p_dueDate, self.p_payment):
            v.set("")
        self.p_paid.set("Y")
        self.p_datePaid.set(datetime.now().strftime("%Y-%m-%d"))
        self._set_calc("")

    def on_select_payment(self, _evt=None):
        sel = self.tree_payments.selection()
        if not sel:
            return
        vals = self.tree_payments.item(sel[0], "values")
        self.p_rentId.set(vals[0])
        self.p_roomId.set(vals[1])
        self.p_tenantId.set(vals[2])
        self.p_dueDate.set(vals[3])
        self.p_paid.set(vals[4])
        self.p_payment.set(str(vals[5]))
        self.p_datePaid.set(vals[6])

    def _set_calc(self, text: str):
        self.calc_text.configure(state="normal")
        self.calc_text.delete("1.0", "end")
        self.calc_text.insert("1.0", text)
        self.calc_text.configure(state="disabled")

    def calculate_payment(self) -> str | None:
        roomId = self.p_roomId.get().strip()
        tenantId = self.p_tenantId.get().strip()
        pay_s = self.p_payment.get().strip()

        if not is_valid_id(roomId):
            messagebox.showerror("Validation", "Room ID must be digits only.")
            return None
        if not is_valid_id(tenantId):
            messagebox.showerror("Validation", "Tenant ID must be digits only.")
            return None
        if not self.db.get_room(roomId):
            messagebox.showerror("Validation", "That room doesn't exist. Add the room first.")
            return None
        if not self.db.get_tenant(tenantId):
            messagebox.showerror("Validation", "That tenant doesn't exist. Add the tenant first.")
            return None

        try:
            payment = money_int(pay_s)
        except ValueError as e:
            messagebox.showerror("Validation", str(e))
            return None

        price = self.db.room_price(roomId)
        if price is None:
            messagebox.showerror("Error", "Room price not found.")
            return None

        owed = price  # monthly owed, as described in the write-up
        lines = []
        lines.append(f"Room {roomId} monthly price: £{owed}")
        lines.append(f"Payment entered: £{payment}")
        lines.append("")

        if payment == owed:
            lines.append("✅ Payment is exactly correct. Nothing owed, nothing extra.")
        elif payment < owed:
            diff = owed - payment
            lines.append("⚠ Underpayment")
            lines.append(f"Remaining owed: £{diff}")
        else:
            extra = payment - owed
            extra_months = payment // owed  # total months covered by full payment
            remainder = payment % owed
            lines.append("ℹ Overpayment / advance payment detected")
            lines.append(f"Extra over 1 month: £{extra}")
            lines.append(f"Total months covered by this payment: {extra_months} month(s)")
            lines.append(f"Remainder after covering whole months: £{remainder}")

        text = "\n".join(lines)
        self._set_calc(text)
        return text

    def record_payment(self):
        rentId = self.p_rentId.get().strip()
        roomId = self.p_roomId.get().strip()
        tenantId = self.p_tenantId.get().strip()
        dueDate = self.p_dueDate.get().strip()
        paid = self.p_paid.get().strip()
        pay_s = self.p_payment.get().strip()
        datePaid = self.p_datePaid.get().strip()

        if not is_valid_id(rentId):
            return messagebox.showerror("Validation", "Payment/Receipt ID must be digits only (up to 6 digits).")
        if not is_valid_id(roomId):
            return messagebox.showerror("Validation", "Room ID must be digits only.")
        if not is_valid_id(tenantId):
            return messagebox.showerror("Validation", "Tenant ID must be digits only.")
        if not self.db.get_room(roomId):
            return messagebox.showerror("Validation", "That room doesn't exist. Add the room first.")
        if not self.db.get_tenant(tenantId):
            return messagebox.showerror("Validation", "That tenant doesn't exist. Add the tenant first.")

        # Date sanity (keep lenient; only check basic format)
        for d, label in ((dueDate, "Due date"), (datePaid, "Date paid")):
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
                return messagebox.showerror("Validation", f"{label} must be YYYY-MM-DD.")

        try:
            payment = money_int(pay_s)
        except ValueError as e:
            return messagebox.showerror("Validation", str(e))

        # Calculate + show result
        calc_text = self.calculate_payment()
        if calc_text is None:
            return

        try:
            self.db.add_rent(rentId, roomId, tenantId, dueDate, paid, payment, datePaid)
        except sqlite3.IntegrityError:
            return messagebox.showerror("Error", "That Payment/Receipt ID already exists. Use a new ID.")

        self.refresh_all()
        messagebox.showinfo("Recorded", "Payment recorded. You can print a receipt from the list below.")

    def delete_selected_payment(self):
        sel = self.tree_payments.selection()
        if not sel:
            return messagebox.showinfo("Delete", "Select a payment row first.")
        rentId = self.tree_payments.item(sel[0], "values")[0]
        if messagebox.askyesno("Confirm delete", f"Delete payment/receipt {rentId}?"):
            self.db.delete_rent(rentId)
            self.refresh_all()

    def _receipt_text(self, rent_row) -> str:
        rentId, roomId, tenantId, dueDate, paid, payment, datePaid = rent_row
        tenant = self.db.get_tenant(tenantId)
        room = self.db.get_room(roomId)
        price = room[1] if room else None

        fname = tenant[1] if tenant else "?"
        sname = tenant[2] if tenant else "?"
        email = tenant[3] if tenant else "?"
        phone = tenant[4] if tenant else "?"

        lines = []
        lines.append("LONDON PROPERTIES - RECEIPT")
        lines.append("=" * 34)
        lines.append(f"Receipt ID: {rentId}")
        lines.append(f"Date paid:  {datePaid}")
        lines.append("")
        lines.append("Tenant")
        lines.append(f"  ID:   {tenantId}")
        lines.append(f"  Name: {fname} {sname}")
        lines.append(f"  Email:{email}")
        lines.append(f"  Tel:  {phone}")
        lines.append("")
        lines.append("Room / Payment")
        lines.append(f"  Room ID:  {roomId}")
        if price is not None:
            lines.append(f"  Monthly:  £{price}")
        lines.append(f"  Due date: {dueDate}")
        lines.append(f"  Paid?:    {paid}")
        lines.append(f"  Amount:   £{payment}")
        lines.append("")
        # Include calc summary
        owed = int(price) if price is not None else None
        if owed:
            if payment == owed:
                lines.append("Payment status: OK (exact)")
            elif payment < owed:
                lines.append(f"Payment status: UNDERPAID (£{owed - payment} remaining)")
            else:
                months = payment // owed
                rem = payment % owed
                lines.append(f"Payment status: OVERPAID (covers {months} month(s), remainder £{rem})")
        return "\n".join(lines)

    def print_selected_receipt(self):
        sel = self.tree_payments.selection()
        if not sel:
            return messagebox.showinfo("Receipt", "Select a payment row first.")
        rentId = self.tree_payments.item(sel[0], "values")[0]
        row = self.db.get_rent(rentId)
        if not row:
            return messagebox.showerror("Receipt", "Could not load that payment.")

        receipt = self._receipt_text(row)

        # show in popup
        win = tk.Toplevel(self)
        win.title(f"Receipt {rentId}")
        win.geometry("620x520")
        txt = tk.Text(win, wrap="word")
        txt.insert("1.0", receipt)
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True, padx=10, pady=10)

        def save():
            default_name = f"receipt_{rentId}.txt"
            path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                initialfile=default_name,
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
            )
            if not path:
                return
            with open(path, "w", encoding="utf-8") as f:
                f.write(receipt)
            messagebox.showinfo("Saved", f"Receipt saved:\n{path}")

        ttk.Button(win, text="Save to file…", command=save).pack(pady=(0, 10))

    def overdue_email_for_selected(self):
        sel = self.tree_payments.selection()
        if not sel:
            return messagebox.showinfo("Overdue email", "Select a payment row first.")
        rentId = self.tree_payments.item(sel[0], "values")[0]
        row = self.db.get_rent(rentId)
        if not row:
            return messagebox.showerror("Overdue email", "Could not load that payment.")

        rentId, roomId, tenantId, dueDate, paid, payment, datePaid = row
        tenant = self.db.get_tenant(tenantId)
        room = self.db.get_room(roomId)
        if not tenant or not room:
            return messagebox.showerror("Overdue email", "Missing tenant or room data.")

        fname, sname, email, phone = tenant[1], tenant[2], tenant[3], tenant[4]
        price = int(room[1])
        owed = price
        remaining = max(0, owed - int(payment))

        subject = f"Overdue rent payment - Room {roomId}"
        body_lines = []
        body_lines.append(f"Hello {fname} {sname},")
        body_lines.append("")
        body_lines.append(f"Our records show that the rent for Room {roomId} was due on {dueDate}.")
        if remaining > 0:
            body_lines.append(f"An outstanding balance of £{remaining} remains.")
        else:
            body_lines.append("If you believe this is an error, please reply with your payment reference.")
        body_lines.append("")
        body_lines.append("Please arrange payment at your earliest convenience.")
        body_lines.append("")
        body_lines.append("Regards,")
        body_lines.append("London Properties")
        body = "\n".join(body_lines)

        win = tk.Toplevel(self)
        win.title("Generated overdue email")
        win.geometry("720x520")

        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        ttk.Label(frame, text=f"To: {email}").pack(anchor="w")
        ttk.Label(frame, text=f"Subject: {subject}").pack(anchor="w", pady=(0, 10))

        txt = tk.Text(frame, wrap="word")
        txt.insert("1.0", body)
        txt.pack(fill="both", expand=True)

        def save():
            default_name = f"overdue_email_{rentId}.txt"
            path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                initialfile=default_name,
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
            )
            if not path:
                return
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"To: {email}\nSubject: {subject}\n\n{body}\n")
            messagebox.showinfo("Saved", f"Email text saved:\n{path}")

        ttk.Button(frame, text="Save to file…", command=save).pack(pady=8)

    # ---------------- General ----------------
    def refresh_all(self):
        self.refresh_tenants()
        self.refresh_rooms()
        self.refresh_payments()

    def refresh_tenants(self):
        for i in self.tree_tenants.get_children():
            self.tree_tenants.delete(i)
        for row in self.db.list_tenants():
            self.tree_tenants.insert("", "end", values=row)

    def refresh_rooms(self):
        for i in self.tree_rooms.get_children():
            self.tree_rooms.delete(i)
        for row in self.db.list_rooms():
            self.tree_rooms.insert("", "end", values=row)

    def refresh_payments(self):
        for i in self.tree_payments.get_children():
            self.tree_payments.delete(i)
        for row in self.db.list_rents():
            self.tree_payments.insert("", "end", values=row)

    def backup_db(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(script_dir, DB_FILENAME)
        if not os.path.exists(db_path):
            return messagebox.showinfo("Backup", "Database file not found yet.")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"london_properties_backup_{ts}.db"
        save_path = filedialog.asksaveasfilename(
            defaultextension=".db",
            initialfile=default_name,
            filetypes=[("SQLite DB", "*.db"), ("All files", "*.*")]
        )
        if not save_path:
            return
        with open(db_path, "rb") as src, open(save_path, "wb") as dst:
            dst.write(src.read())
        messagebox.showinfo("Backup", f"Backup saved:\n{save_path}")

    def on_close(self):
        try:
            self.db.close()
        finally:
            self.destroy()


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
