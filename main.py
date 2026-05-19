import os
import ssl

os.environ['PYTHONHTTPSVERIFY'] = '0'
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass

import flet as ft
import sqlite3
import asyncio
from escpos.printer import Dummy

# --- UPDATED DATABASE SETUP ---
def init_database():
    conn = sqlite3.connect("mobile_billing.db")
    cursor = conn.cursor()
    # Table for general invoice details
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            party_name TEXT,
            prev_balance REAL,
            total_due REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Table for individual items linked to an invoice ID
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invoice_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER,
            item_name TEXT,
            qty INTEGER,
            price REAL,
            FOREIGN KEY(invoice_id) REFERENCES invoices(id)
        )
    ''')
    conn.commit()
    conn.close()

init_database()

# --- PRINT SERVICE FOR MULTIPLE ITEMS ---
def generate_receipt_bytes(party, items_list, prev, total):
    d = Dummy()
    d.set(align='center', text_type='B') 
    d.text("INVOICE\n")
    d.set(align='center', text_type='NORMAL')
    d.text(f"Party: {party[:20]}\n")
    d.text("--------------------------------\n")
    
    d.set(align='left')
    d.text("Item          Qty    Total\n")
    d.text("--------------------------------\n")
    
    for item in items_list:
        row_total = item['qty'] * item['price']
        row = f"{item['name'][:12].ljust(13)}{str(item['qty']).ljust(6)}{f'{row_total:.2f}'.rjust(10)}\n"
        d.text(row)
        
    d.text("--------------------------------\n")
    d.text(f"Prev Balance:".ljust(22) + f"{prev:.2f}".rjust(10) + "\n")
    d.set(text_type='B')
    d.text(f"TOTAL DUE:".ljust(22) + f"{total:.2f}".rjust(10) + "\n")
    d.cut()
    return d.output

init_database()
def generate_receipt_text(party, items_list, prev, total):
    lines = []

    lines.append("       INVOICE")
    lines.append("----------------------------")
    lines.append(f"Party: {party}")
    lines.append("----------------------------")

    for item in items_list:
        row_total = item['qty'] * item['price']

        lines.append(
            f"{item['name']} x{item['qty']} = {row_total:.2f}"
        )

    lines.append("----------------------------")
    lines.append(f"Previous: {prev:.2f}")
    lines.append(f"TOTAL: {total:.2f}")
    lines.append("----------------------------")

    return "\n".join(lines)

# --- APP INTERFACE ---
def main(page: ft.Page):
    page.title = "Mobile Billing App"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.scroll = "adaptive"
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    # List to hold items for the current invoice
    current_invoice_items = []

    party_input = ft.TextField(label="Customer / Party Name", border_radius=8)
    balance_input = ft.TextField(label="Previous Balance", value="0.0", keyboard_type=ft.KeyboardType.NUMBER, border_radius=8)
    
    # Item inputs with fixed widths to prevent layout cutoffs
    item_input = ft.TextField(label="Item Name", border_radius=8, width=310)
    qty_input = ft.TextField(label="Qty", value="1", keyboard_type=ft.KeyboardType.NUMBER, border_radius=8, width=150)
    price_input = ft.TextField(label="Price", value="0.0", keyboard_type=ft.KeyboardType.NUMBER, border_radius=8, width=150)
    
    # UI elements to show items added live
    items_preview = ft.Column()
    status_msg = ft.Text(value="", color=ft.Colors.BLUE_700, weight=ft.FontWeight.BOLD)

    def add_item_to_list(e):
        try:
            name = item_input.value
            qty = int(qty_input.value)
            price = float(price_input.value)
            
            if not name:
                status_msg.value = "❌ Enter an item name first."
                page.update()
                return
                
            # Add to local temporary list
            current_invoice_items.append({"name": name, "qty": qty, "price": price})
            
            # Update visual list on screen
            items_preview.controls.append(
                ft.Text(f"• {name} x{qty} (${qty*price:.2f})", size=14)
            )
            
            # Clear item input boxes for next item
            item_input.value = ""
            qty_input.value = "1"
            price_input.value = "0.0"
            status_msg.value = f"Added {name} to active list."
            page.update()
        except ValueError:
            status_msg.value = "❌ Invalid numbers in Qty or Price fields."
            page.update()

    def save_and_process_invoice(print_receipt):
        if not current_invoice_items:
            status_msg.value = "❌ Add at least one item before saving."
            page.update()
            return
            
        try:
            party = party_input.value
            prev = float(balance_input.value)
        except ValueError:
            status_msg.value = "❌ Check your Previous Balance format."
            page.update()
            return

        # Compute combined sum
        items_total = sum(i['qty'] * i['price'] for i in current_invoice_items)
        total_due = items_total + prev

        # Write to SQLite tables
        conn = sqlite3.connect("mobile_billing.db")
        cursor = conn.cursor()
        
        # 1. Main entry
        cursor.execute('''
            INSERT INTO invoices (party_name, prev_balance, total_due)
            VALUES (?, ?, ?)
        ''', (party, prev, total_due))
        invoice_id = cursor.lastrowid

        # 2. Relational child items entry
        for item in current_invoice_items:
            cursor.execute('''
                INSERT INTO invoice_items (invoice_id, item_name, qty, price)
                VALUES (?, ?, ?, ?)
            ''', (invoice_id, item['name'], item['qty'], item['price']))
            
        conn.commit()
        conn.close()

        status_msg.value = "✅ Complete Invoice Saved to Database!"
        page.update()
        
        if print_receipt:
            receipt_text = generate_receipt_text(party,current_invoice_items,prev,total_due)
            downloads_path = "/storage/emulated/0/Download/receipt.txt"

            with open(downloads_path, "w", encoding="utf-8") as f:
                f.write(receipt_text)

            status_msg.value = "✅ Receipt saved as receipt.txt"
            page.update()

        # Reset completely for next customer
        current_invoice_items.clear()
        items_preview.controls.clear()
        party_input.value = ""
        balance_input.value = "0.0"
        page.update()

    page.add(
        ft.Container(
            content=ft.Column([
                ft.Text("Chhit Billing System", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE),
                ft.Divider(),
                party_input,
                balance_input,
                ft.Divider(),
                # Item configuration section
                item_input,
                ft.Row([qty_input, price_input], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, width=310),
                ft.ElevatedButton("➕ Add Item to List", on_click=add_item_to_list, width=310, bgcolor=ft.Colors.BLUE_50),
                ft.Text("Current Items:", weight=ft.FontWeight.BOLD),
                items_preview,
                ft.Divider(),
                ft.ElevatedButton("💾 Save Invoice (No Print)", on_click=lambda e: save_and_process_invoice(print_receipt=False), width=310, bgcolor=ft.Colors.GREY_300),
                ft.ElevatedButton("🖨️ Save and Print Receipt", on_click=lambda e: save_and_process_invoice(print_receipt=True), width=310, bgcolor=ft.Colors.BLUE_400, color=ft.Colors.WHITE),
                status_msg
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=20,
            width=350,
            border_radius=10,
            bgcolor=ft.Colors.WHITE,
            shadow=ft.BoxShadow(blur_radius=10, color=ft.Colors.BLACK12)
        )
    )

ft.run(main)
