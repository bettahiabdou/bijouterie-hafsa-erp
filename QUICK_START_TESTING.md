# 🚀 QUICK START: Test Payment UI (5 minutes)

## ✅ Pre-Test Checklist

- [ ] Latest code pulled: `git pull origin main`
- [ ] Django server running: `python manage.py runserver`
- [ ] Browser at http://127.0.0.1:8000/

## 🧪 Test in 3 Steps

### Step 1: Open an Invoice (1 min)
1. Go to http://127.0.0.1:8000/sales/invoices/
2. Click on any invoice to open detail page
3. Look at the right sidebar

### Step 2: Check Payment Section (1 min)
**Expected:** You should see:
- ✅ Green "Payer" button in "Paiement" section
- ✅ Blue status badge showing "Confirmé" (if no payment yet)
- ✅ "Payé: 0 DH" and "Solde: [total] DH"

**If NOT visible:**
- Hard refresh: `Cmd+Shift+R` (Mac) or `Ctrl+Shift+R` (Windows)
- Clear cache: `Ctrl+Shift+Delete`

### Step 3: Record a Payment (3 min)
1. Click green "Payer" button
2. **Expected:** Navigate to payment form page
3. Enter 50% of total amount
4. Select payment method
5. Click "Enregistrer Paiement" (Record Payment)
6. **Expected:** Success message appears
7. Go back to invoice detail
8. **Expected:** Status should now be YELLOW (Partiellement payé)
9. Click "Payer" again
10. Record remaining 50%
11. **Expected:**
    - Status becomes ORANGE (Payé)
    - "Payer" button disappears
    - "Payé" shows full amount
    - "Solde" shows 0 DH

## 📊 Color Reference

| Status | Expected Color |
|--------|-----------------|
| Confirmé | 🔵 Blue |
| Partiellement payé | 🟡 Yellow |
| Payé | 🟠 Orange |
| Livré | 🟢 Green |

## ✅ All Tests Pass When:

- [ ] Button visible for unpaid invoices
- [ ] Button navigates to payment form
- [ ] Payment form accepts amount & method
- [ ] Status updates to yellow (partial payment)
- [ ] Amounts update correctly
- [ ] Status updates to orange (full payment)
- [ ] Button disappears when fully paid
- [ ] Colors display correctly

## ❌ Troubleshooting

**Button not visible?**
→ Hard refresh browser + clear cache

**Button doesn't navigate?**
→ Check browser console (F12) for errors

**Status not updating?**
→ Reload page after recording payment

**Wrong colors?**
→ Browser cache issue, do hard refresh

## 📞 Report Results

Once you test, please let me know:
1. ✅ Which tests passed
2. ❌ Which tests failed (if any)
3. Any errors in browser console
4. Screenshots if colors look wrong

---

**Estimated Time:** 5 minutes
**Commits:** 4c29c4b, 0cca80f
**Status:** Ready to test! 🎉
