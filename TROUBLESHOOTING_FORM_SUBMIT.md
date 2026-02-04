# 🔧 TROUBLESHOOTING: "Créer la Facture" Button Not Working

**Date:** February 4, 2026
**Status:** Diagnostic Guide

---

## 🐛 Symptom

When you click "Créer la Facture" button in `/sales/invoices/create/`, the form does not submit. The page stays on the same form.

---

## 🔍 How to Diagnose

### Step 1: Open Browser Console

1. **Press:** `F12` (or `Ctrl+Shift+I` on Windows/Linux, `Cmd+Shift+I` on Mac)
2. **Click:** Console tab
3. **Leave console open**

### Step 2: Try to Create Invoice

1. **Fill the form with minimum data:**
   - Leave Client empty (optional)
   - Select Payment Method: "Espèces"
   - Leave Tax at 0
   - Don't add any articles

2. **Click:** "Créer la Facture" button

3. **Check console for messages:**
   - You should see: `"Main form submit event triggered"`
   - You should see: `"Form submitting with 0 items"`

### Step 3: Check for JavaScript Errors

In the Console tab, look for any **red error messages** like:
```
Uncaught TypeError: Cannot read property 'value' of null
```

---

## ✅ What Should Happen

**Good Flow:**
```
1. Click button
2. Console shows: "Main form submit event triggered"
3. Console shows: "Form submitting with 0 items"
4. Page redirects to invoice detail (/sales/invoices/FAC-XXXXX/)
5. Success message appears
```

**Bad Flow:**
```
1. Click button
2. No console messages appear
3. Page doesn't change
4. OR you see red error in console
```

---

## 🛠️ Common Issues & Solutions

### Issue 1: No Console Messages Appear

**Cause:** Form submit event not being triggered

**Solution:**
1. Make sure you pulled latest code: `git pull origin main`
2. Hard refresh: `Ctrl+Shift+R` (Windows/Linux) or `Cmd+Shift+R` (Mac)
3. Clear browser cache completely
4. Try in a new private/incognito window

### Issue 2: Red Error in Console

**Example Error:**
```
Uncaught TypeError: selectedTextLower is not defined
```

**Solution:**
This means there's a JavaScript error in the payment field logic. Check:
1. Hard refresh browser
2. Check if all fields are properly loaded
3. Try selecting a payment method to trigger the visibility logic
4. Check for other errors in console

### Issue 3: Form Submits but Nothing Happens

**Cause:** Backend error not visible to user

**Solution:**
1. Open browser DevTools Network tab
2. Refresh page
3. Fill form and click button
4. Look for POST request to `/sales/invoices/create/`
5. Click on it to see the response
6. Look for error details in the response

---

## 📋 Checklist Before Submitting

Before clicking "Créer la Facture", verify:

- [ ] You're on the correct page: `/sales/invoices/create/`
- [ ] Browser console is open (F12)
- [ ] At least one form field is filled (or click button with empty form to test)
- [ ] JavaScript is enabled in browser
- [ ] You're using a modern browser (Chrome, Firefox, Safari, Edge)
- [ ] No red errors in console before clicking

---

## 🔄 Reset & Retry Steps

If form still doesn't work:

1. **Pull latest code:**
   ```bash
   cd /Users/user/.claude-worktrees/Claude_cde/serene-gagarin
   git pull origin main
   ```

2. **Stop server** (if running):
   - Press `Ctrl+C` in terminal where server is running

3. **Apply database migration:**
   ```bash
   python manage.py migrate sales
   ```

4. **Start server again:**
   ```bash
   python manage.py runserver
   ```

5. **Hard refresh browser:**
   - `Ctrl+Shift+R` (Windows/Linux)
   - `Cmd+Shift+R` (Mac)

6. **Try again** with console open

---

## 📊 Form Fields to Send

When form submits, these fields should be POSTed:

```
Required (always sent):
├─ client: (ID or empty)
├─ payment_method: (ID)
├─ tax_rate: (number)
└─ csrf_token: (Django security token)

Optional (only if filled):
├─ payment_reference: (text)
├─ bank_account: (ID - only for Virement Bancaire)
├─ notes: (text)
└─ items[0], items[1], etc: (JSON - only if articles added)
```

---

## 🎯 Expected POST Request

When button clicked, browser should send POST request to:
```
POST /sales/invoices/create/
```

With form data containing at minimum:
- `csrfmiddlewaretoken`
- `client` (optional)
- `payment_method`
- `tax_rate`

---

## ✅ Success Indicators

You'll know form is working when:

1. **Console Messages:**
   - ✅ "Main form submit event triggered"
   - ✅ "Form submitting with X items"

2. **Network Tab:**
   - ✅ POST request to `/sales/invoices/create/` returns 302 (redirect)
   - ✅ Redirects to `/sales/invoices/FAC-XXXXX/`

3. **Page Changes:**
   - ✅ URL changes from `/create/` to `/invoices/FAC-XXXXX/`
   - ✅ Page shows invoice detail
   - ✅ Success message at top: "Facture "FAC-XXXXX" créée..."

---

## 🆘 If Still Stuck

If you've tried all the above and form still doesn't work:

1. **Take screenshot** of the console with any error messages
2. **Note the exact behavior:**
   - What happens when you click button?
   - Do you see any console messages?
   - Any error messages?
3. **Run this in console to test:**
   ```javascript
   // Test form element exists
   console.log('Form exists:', document.querySelector('form'));

   // Test submit button exists
   console.log('Submit button:', document.querySelector('button[type="submit"]'));

   // Test payment method select exists
   console.log('Payment method select:', document.querySelector('select[name="payment_method"]'));
   ```

---

## 📝 Latest Changes (Feb 4, 2026)

- Added `payment_reference` field to form and model
- Created database migration `0006_add_payment_reference.py`
- Improved form submit event listener
- Added console logging for debugging

**Commits:**
- `a4ae55b` - Form fields
- `0d47a7e` - Model and migration
- `366706f` - Submit listener fix

---

**Need Help?** Check the browser console messages - they will tell you exactly what's happening!

