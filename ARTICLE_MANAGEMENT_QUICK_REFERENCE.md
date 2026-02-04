# ⚡ QUICK REFERENCE: Invoice Article Management

**Issue Resolved:** "But how are we supposed to add product in the invoice when I don't have where to add it to the invoice?"

---

## ✅ WHAT'S NEW

### The Problem (Before)
- ❌ Created invoice in DRAFT status
- ❌ Went to detail page
- ❌ **No button to add articles**
- ❌ Stuck - couldn't complete invoice

### The Solution (Now)
- ✅ Create invoice
- ✅ Go to detail page
- ✅ **Click "Ajouter un Article" button** (NEW!)
- ✅ Modal appears to add product
- ✅ Article added instantly
- ✅ Repeat for each product

---

## 🎯 HOW TO USE

### Step 1: Create Invoice
```
Navigate to:  /sales/invoices/create/
Fill form:    Any fields you want (all optional!)
Click:        "Créer la Facture"
Result:       Invoice created (DRAFT status)
```

### Step 2: View Invoice & Add Articles
```
You're now on: /sales/invoices/INV-20260204-0001/

See section: "Articles"
See button:  "+ Ajouter un Article" (BLUE BUTTON)
Click it:    Modal appears!
```

### Step 3: Fill Article Form

**In the modal that appears:**

```
1. Produit (Product) - REQUIRED
   - Click dropdown
   - Select product (e.g., "BAG-002 - Bague Or")
   - Price auto-fills

2. Quantité (Quantity) - DEFAULT 1
   - Change if needed
   - Supports decimals (e.g., 2.5)
   - Total updates automatically

3. Prix Unitaire (Unit Price) - AUTO-FILLED
   - Usually auto-filled from product price
   - Can change for negotiated prices

4. Remise (Discount) - OPTIONAL
   - Leave as 0 if no discount
   - Subtracted from total

SEE: "Total estimé: 2500 DH" (Updates in real-time!)
```

### Step 4: Add Article
```
Click:   "Ajouter Article" button
Result:  AJAX submission (no page reload)
         Modal closes
         Article appears in table below
```

### Step 5: See Article in Table
```
The article now shows in your invoice:

Produit          | Quantité | Prix Unitaire | Total  | Actions
Bague Or         | 1        | 850 DH        | 850 DH | Supprimer
```

### Step 6: Repeat or Continue
```
Option A: Add more articles
  └─ Click "+ Ajouter un Article" again

Option B: Record payment
  └─ Click "Enregistrer un Paiement"

Option C: Delete article
  └─ Click "Supprimer" in Actions column
```

---

## 🔑 KEY POINTS

### When Can I Add Articles?
✅ **ONLY when invoice is DRAFT**
- After creating invoice
- Before confirming invoice
- Before changing to CONFIRMED status

❌ **NOT when invoice is CONFIRMED**
- Button won't appear
- Articles are locked
- Can't add/remove articles

### Can I Delete Articles?
✅ **YES - if invoice is DRAFT**
- See "Supprimer" button in Actions column
- Click it - confirmation dialog appears
- Confirm - article is gone

❌ **NO - if invoice is CONFIRMED**
- Delete button won't show
- Articles are immutable
- Must stay as-is

### Do I Have to Add Articles?
✅ **NO - articles are optional**
- You CAN create an invoice with zero articles
- Later add articles from detail page
- OR skip articles entirely (if needed)

### What About Walk-In Sales?
✅ **FULLY SUPPORTED**
- Don't select a client
- Leave client dropdown empty
- Shows "No client (walk-in sale)" on page
- All other features work normally

---

## 📋 COMMON TASKS

### Task: Add 2 Rings to Invoice

```
1. Open invoice detail page
2. Click "+ Ajouter un Article"
3. Select: Bague Or (BAG-002)
   Qty: 1
   Price: 850 (auto-filled)
   Discount: 0
4. Click "Ajouter Article"
   ✅ Ring 1 added!

5. Click "+ Ajouter un Article" again
6. Select: Bague Argent (BAG-003)
   Qty: 1
   Price: 500 (auto-filled)
   Discount: 0
7. Click "Ajouter Article"
   ✅ Ring 2 added!

8. See both in table:
   - Bague Or: 850 DH
   - Bague Argent: 500 DH
   - Total: 1350 DH
```

### Task: Add Article with Discount

```
1. Click "+ Ajouter un Article"
2. Select: Collier (COL-001)
   Qty: 1
   Price: 1500 (auto-filled)
   Discount: 150 (10% off)
   ✓ Total shows: 1350 DH
3. Click "Ajouter Article"
   ✅ Collier added with discount!
```

### Task: Change Price (Negotiated)

```
1. Click "+ Ajouter un Article"
2. Select: Bracelet (BRA-001)
   Qty: 1
   Price: [Clear and enter 400]
         (Customer negotiated price)
   Discount: 0
   ✓ Total shows: 400 DH
3. Click "Ajouter Article"
   ✅ Bracelet added at negotiated price!
```

### Task: Delete Article

```
1. Look at article table
2. Find the article you want to delete
3. Click "Supprimer" button in Actions column
4. Confirmation dialog: "Êtes-vous sûr?"
5. Click "OK"
   ✅ Article deleted!
```

---

## 🎨 UI LAYOUT

### Invoice Detail Page

```
┌────────────────────────────────────────────────────┐
│  Invoice INV-20260204-0001 - 4 Feb 2026          │
├────────────────────────────────────────────────────┤
│                                                    │
│  CLIENT INFO            │     SIDEBAR              │
│  ┌──────────────────┐   │  ┌─────────────────┐   │
│  │ John Doe         │   │  │ Status: DRAFT   │   │
│  │ john@ex.com      │   │  ├─────────────────┤   │
│  │ +212 6 12345678  │   │  │ Subtotal: 2500  │   │
│  └──────────────────┘   │  │ Tax: 0          │   │
│                         │  │ Total: 2500 DH  │   │
│  ARTICLES               │  ├─────────────────┤   │
│  ┌──────────────────┐   │  │ Paid: 0 DH      │   │
│  │ [+ Ajouter]      │ ← │← │ Balance: 2500   │   │
│  ├──────────────────┤   │  └─────────────────┘   │
│  │ BAG-002 │ 1 │850│850│ X Suppr             │   │
│  │ BAG-003 │ 1 │500│500│ X Suppr             │   │
│  └──────────────────┘   │                        │
│                         │                        │
└────────────────────────────────────────────────────┘

← "Ajouter un Article" button HERE
↑ Article table shows
    Produit | Qty | Prix | Total | Actions
```

---

## 📱 MODAL FORM

When you click the button:

```
┌──────────────────────────────────────┐
│  Ajouter un Article              [X] │
├──────────────────────────────────────┤
│                                      │
│  Produit * ← Required                │
│  [─ Sélectionnez ──────────────────▼]│
│                                      │
│  Quantité *     Prix Unitaire (DH)  │
│  [1]            [0.00]              │
│                                      │
│  Remise (DH)                         │
│  [0.00]                              │
│                                      │
│  ┌──────────────────────────────┐   │
│  │ Total estimé: 0.00 DH        │   │
│  │ (Updates automatically!)      │   │
│  └──────────────────────────────┘   │
│                                      │
│  [Annuler]  [Ajouter Article] ←    │
│                          Click here! │
└──────────────────────────────────────┘
```

---

## ⚙️ TECHNICAL DETAILS

### What Happens Behind the Scenes

**When you click "Ajouter Article":**

```
1. Form validates all required fields
2. AJAX POST to: /sales/invoices/INV-123/add-item/
3. Backend:
   - Checks invoice is DRAFT
   - Checks product exists
   - Validates quantities/prices
   - Creates SaleInvoiceItem
   - Logs activity
4. Returns JSON: {'success': true}
5. Modal closes
6. Page reloads to show new article
```

**When you click "Supprimer":**

```
1. Confirmation dialog appears
2. AJAX POST to: /sales/invoices/delete-item/?item_id=123
3. Backend:
   - Checks invoice is DRAFT
   - Deletes SaleInvoiceItem
   - Logs deletion
4. Returns JSON: {'success': true}
5. Page reloads
```

### No Page Reload
- AJAX technology used
- Modal closes smoothly
- Page refreshes to show changes
- No need to manually refresh

---

## 🛡️ VALIDATION

### What Gets Checked

**When adding article:**
- ✅ Product selected
- ✅ Product exists in database
- ✅ Quantity > 0
- ✅ Unit price ≥ 0
- ✅ Invoice is DRAFT status
- ✅ All calculations correct

**When deleting article:**
- ✅ Article exists
- ✅ Invoice is still DRAFT
- ✅ User confirmed deletion

### If Something's Wrong

```
Error: "Seules les factures en brouillon peuvent..."
→ Invoice is not DRAFT (already confirmed)
→ Solution: Create a new invoice

Error: "Produit requis"
→ You didn't select a product
→ Solution: Click dropdown and select one

Error: "Quantité invalide"
→ Quantity is not a valid number or ≤ 0
→ Solution: Enter a valid number > 0

Error: "La quantité doit être supérieure à 0"
→ You entered 0 or negative number
→ Solution: Enter a positive number
```

---

## 💡 PRO TIPS

1. **Use Quick Client Modal**
   - Don't create invoice without client first
   - Instead: Click "Nouveau Client" button in form
   - Adds client without leaving page

2. **Hover for Delete Button**
   - Delete button appears when you hover over article row
   - Easier to see and click
   - Confirmation dialog prevents accidents

3. **Real-Time Total**
   - Total updates as you type
   - See what you'll charge before confirming
   - Catch mistakes early

4. **Decimal Quantities**
   - Use decimals for partial items
   - Example: 2.5 = 2 full + 1 half
   - Perfect for weight-based items

5. **Negotiated Prices**
   - Click unit price field and change it
   - Don't delete and re-enter
   - Total recalculates automatically

---

## 🔗 RELATED FEATURES

### From Invoice Detail Page, You Can:

1. **Edit** - Change basic invoice info
   ```
   Click: "Éditer" button
   Edit: Client, payment method, delivery, etc.
   ```

2. **Record Payment**
   ```
   Click: "Enregistrer un Paiement" button
   Enter: Amount paid
   See: Balance due updates
   ```

3. **Record Delivery**
   ```
   Click: "Enregistrer Livraison" button
   Track: Delivery person, address, date
   ```

4. **Delete Invoice**
   ```
   Click: "Supprimer" button
   Soft deletes (keeps in system, marked deleted)
   ```

---

## 📞 TROUBLESHOOTING

**Q: Where is the "Add Article" button?**
A: Make sure invoice is DRAFT status (not CONFIRMED).
   If DRAFT, button appears in Articles section header.

**Q: Can I edit an article after adding it?**
A: Currently no - but you can delete and re-add with new details.
   (Edit feature could be added in future)

**Q: What if I add wrong product?**
A: Click "Supprimer" in that article's row, then re-add correct one.

**Q: Does quantity support decimals?**
A: Yes! Supports up to 3 decimal places (0.001).
   Perfect for jewelry (grams, ounces, etc.)

**Q: Can I add same product twice?**
A: Yes - appears as separate rows in table.
   Example: Bague Or added twice = 2 separate rows

**Q: What about walk-in sales (no client)?**
A: Leave client empty - shows "No client (walk-in sale)".
   Everything else works the same!

---

## 🎯 NEXT STEPS

1. **Try it out** - Create a test invoice
2. **Add articles** - Use the new button
3. **Record payment** - Complete the sale
4. **Check activity log** - See your changes logged

---

## 📚 MORE INFO

- **Full Technical Docs**: See `INVOICE_ARTICLE_MANAGEMENT.md`
- **Complete Workflow**: See `INVOICE_WORKFLOW_SUMMARY.md`
- **Walk-In Sales**: See `OPTIONAL_CLIENT_FEATURE.md`

---

**Status:** ✅ Live and Ready
**Last Updated:** February 4, 2026
**Commit:** db59727

