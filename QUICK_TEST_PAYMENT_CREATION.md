# ⚡ Quick Test: Payment During Invoice Creation

**Commit:** 00e822d
**Test Time:** 5-10 minutes

---

## 🎯 What Changed

**Before:** Create invoice → Then use "Payer" button to add payment
**After:** Add payment amount DURING invoice creation → One transaction!

---

## 🧪 Test in 3 Simple Scenarios

### Test 1: Invoice WITHOUT Payment (2 min)

**Steps:**
```
1. Go to http://127.0.0.1:8000/sales/invoices/create/
2. Select any client
3. Add articles (use "Ajouter un Article" button)
4. Leave "Montant Payé à la Création" blank
5. Click "Créer la Facture"
```

**Expected Results:**
- ✅ Invoice created successfully
- ✅ See message: "Facture créée avec X articles."
- ✅ Invoice detail shows Status: CONFIRMÉ (BLUE badge)
- ✅ Amount Paid: 0 DH
- ✅ Balance: [Total Amount]
- ✅ Green "Payer" button visible

---

### Test 2: Invoice with PARTIAL Payment (3 min)

**Steps:**
```
1. Create invoice with articles (total: 5000 DH)
2. Scroll down to "Montant Payé à la Création" field
3. Enter: 2000
4. Click "Créer la Facture"
```

**Expected Results:**
- ✅ Invoice created successfully
- ✅ See message: "Facture créée avec articles • Paiement: 2000 DH (Solde: 3000 DH)."
- ✅ Invoice detail shows Status: PARTIELLEMENT PAYÉ (YELLOW badge)
- ✅ Amount Paid: 2000 DH
- ✅ Balance: 3000 DH
- ✅ Green "Payer" button visible

---

### Test 3: Invoice with FULL Payment (3 min)

**Steps:**
```
1. Create invoice with articles (total: 5000 DH)
2. Enter "Montant Payé à la Création": 5000
3. Click "Créer la Facture"
```

**Expected Results:**
- ✅ Invoice created successfully
- ✅ See message: "Facture créée avec articles • Paiement: 5000 DH ✓ PAYÉE EN INTÉGRALITÉ."
- ✅ Invoice detail shows Status: PAYÉ (ORANGE badge)
- ✅ Amount Paid: 5000 DH
- ✅ Balance: 0 DH
- ✅ Green "Payer" button HIDDEN (already fully paid)

---

## 🎨 Where to Find the New Field

```
Invoice Form
│
├─ Client Section
├─ Parameters Section
│  ├─ TVA (%)
│  ├─ Méthode de Paiement
│  ├─ Référence de Paiement (if needed)
│  ├─ Compte Bancaire (if needed)
│  └─ Montant Payé à la Création ← NEW!
│
├─ Articles Section
│  └─ Add articles here
│
├─ Notes Section
│
└─ Submit Button: "Créer la Facture"
```

---

## ✅ Quick Checklist

- [ ] Test 1 passed: No payment → CONFIRMÉ (blue)
- [ ] Test 2 passed: Partial payment → PARTIELLEMENT PAYÉ (yellow)
- [ ] Test 3 passed: Full payment → PAYÉ (orange)
- [ ] Verify balance due calculated correctly
- [ ] Verify "Payer" button shows/hides appropriately
- [ ] Verify success messages show payment info
- [ ] Try entering decimal: 2000.50 (should work)

---

## 🔍 What to Look For

### Form Field
- Text input with "DH" currency hint
- Placeholder: "0.00"
- Help text explains optional use
- Located after Bank Account field

### Status Badge (on invoice detail)
- CONFIRMÉ = 🔵 Blue
- PARTIELLEMENT PAYÉ = 🟡 Yellow
- PAYÉ = 🟠 Orange
- LIVRÉ = 🟢 Green

### Success Message
Should show:
- Invoice reference (e.g., "INV-20260204-0015")
- Number of articles
- Payment amount (if entered)
- Balance due (if partial)
- ✓ PAYÉE EN INTÉGRALITÉ (if full)

---

## ❌ Troubleshooting

| Problem | Solution |
|---------|----------|
| Field not showing | Hard refresh: Cmd+Shift+R (Mac) or Ctrl+Shift+R (Windows) |
| Payment not recorded | Verify amount is > 0 and uses decimal format (2000.50) |
| Status not updating | Page redirects to detail page - status auto-updates |
| Payment field labeled wrong | Clear browser cache completely |

---

## 💡 How It Works

```
INVOICE CREATION WORKFLOW

1. Salesperson fills form
   ├─ Client
   ├─ Articles (multiple)
   ├─ Payment method
   └─ Payment amount ← NEW!

2. Submits "Créer la Facture"
   ↓

3. Backend processes:
   ├─ Creates invoice
   ├─ Adds articles
   ├─ Calculates totals
   ├─ Records payment (if > 0) ← NEW!
   ├─ Updates status ← NEW!
   └─ Logs activity

4. Redirects to detail page
   ↓

5. Invoice shows:
   ├─ Status with color (blue/yellow/orange/green)
   ├─ Payment amount & balance
   └─ "Payer" button (if still owes money)
```

---

## 📊 Status Legend

| Status | Color | Meaning | "Payer" Button |
|--------|-------|---------|---|
| CONFIRMÉ | 🔵 Blue | No payment yet | ✅ Visible |
| PARTIELLEMENT PAYÉ | 🟡 Yellow | Paid some | ✅ Visible |
| PAYÉ | 🟠 Orange | Fully paid | ❌ Hidden |
| LIVRÉ | 🟢 Green | Delivered | ❌ Hidden |

---

## 🎯 Success Criteria

All tests pass when:
- ✅ Payment field appears on form
- ✅ Can enter amount in field
- ✅ Payment recorded during creation
- ✅ Status updates correctly
- ✅ Status colors display
- ✅ Balance due calculated
- ✅ Success message shows details
- ✅ Can still use "Payer" button for additional payments

---

## 📝 Report Results

After testing, let me know:
1. ✅ Which tests passed
2. ❌ Which tests failed (if any)
3. 🔍 Screenshot of status colors
4. 💭 Any issues or unexpected behavior

---

**Ready to test?** Start with Test 1 (no payment) → Test 2 (partial) → Test 3 (full payment).

Takes about 10 minutes total! 🚀
