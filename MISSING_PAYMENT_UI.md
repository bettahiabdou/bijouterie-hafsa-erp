# ⚠️ ISSUE: Payment UI Not Implemented

**Status:** Missing Feature
**Impact:** Status logic exists but cannot be used
**Severity:** High - Feature incomplete

---

## 🔍 Current State

### What EXISTS (Backend)
✅ Invoice model has `amount_paid` field
✅ Invoice model has `balance_due` field
✅ Invoice model has `update_status()` method
✅ Status logic automatically calculates status
✅ Invoice detail page DISPLAYS payment info (read-only)

### What is MISSING (UI)
❌ **No "Record Payment" button**
❌ **No payment form to enter amount**
❌ **No way to mark invoice as "Paid"**
❌ **No way to mark invoice as "Delivered"**
❌ **No payment history/log**

---

## 📍 Location

**File:** `/templates/sales/invoice_detail.html`
**Section:** Lines 158-173 (Payment Info section)

### Current Code (READ-ONLY)
```html
<!-- Payment Info -->
<div class="bg-white rounded-lg shadow-md p-6">
    <h3 class="text-lg font-bold text-gray-900 mb-4">Paiement</h3>
    <div class="space-y-3 text-sm">
        <div class="flex justify-between">
            <span class="text-gray-600">Payé:</span>
            <span class="font-medium">{{ invoice.amount_paid }} DH</span>  <!-- Only displays, no input -->
        </div>
        <div class="flex justify-between">
            <span class="text-gray-600">Solde:</span>
            <span class="font-bold">{{ invoice.balance_due }} DH</span>  <!-- Only displays -->
        </div>
    </div>
    <!-- NO BUTTON TO RECORD PAYMENT! -->
</div>
```

---

## 🎯 What Needs to Be Built

### 1. Payment Recording UI
```
Current: Shows "Payé: 0 DH" and "Solde: 1000 DH"
Needed: Button to record payment
        Form to enter payment amount
        Button to confirm and save
```

### 2. Payment History
```
Current: Only shows current amount_paid (total)
Needed: List of individual payments with dates
        Example:
        - 2026-02-04: 500 DH (Carte Bancaire)
        - 2026-02-05: 500 DH (Espèces)
        - Total: 1000 DH (PAID)
```

### 3. Delivery Status UI
```
Current: Status automatically set (no control)
Needed: Button to mark as "Delivered"
        Or at least show delivery status option
```

### 4. Status Management
```
Current: Status auto-calculated (read-only)
Needed: Option to manually change status
        OR at least document why it's auto-calculated
```

---

## 💡 Why Status Shows "LIVRÉ" Now

When you create an invoice:

```python
def update_status(self):
    # Line 317-319 in models.py
    if self.amount_paid >= self.total_amount:  # False (0 >= 1000? No)
        if self.delivery_status == 'delivered' or not self.delivery_method:
            self.status = self.Status.DELIVERED  # ← DELIVERED even with 0 payment!
        else:
            self.status = self.Status.PAID
    elif self.amount_paid > 0:  # False (0 > 0? No)
        self.status = self.Status.PARTIAL_PAID
    else:
        self.status = self.Status.CONFIRMED  # Should be here!
```

**BUG:** Invoice shows "LIVRÉ" because:
- `delivery_status` is empty (None/null)
- `delivery_method` is empty (None/null)
- Code interprets this as "no delivery method = already delivered"
- So status jumps to LIVRÉ instead of CONFIRMÉ

---

## 🔧 What Should Happen

### Current (WRONG):
```
Create Invoice
└─ amount_paid = 0
└─ delivery_method = None
└─ Status = LIVRÉ ❌ (Wrong! Should be CONFIRMÉ)
```

### Correct:
```
Create Invoice
└─ amount_paid = 0
└─ delivery_method = None (not set)
└─ Status = CONFIRMÉ ✅ (Correct - waiting for payment)

Record Payment: 500 DH
└─ amount_paid = 500
└─ Status = PARTIELLEMENT PAYÉ ✅

Record Payment: 500 DH
└─ amount_paid = 1000
└─ delivery_method = None
└─ Status = LIVRÉ ✅ (Correct - paid and no delivery method)
```

---

## 🚀 Implementation Roadmap

### Phase 1: Fix Status Logic
1. Fix the condition that incorrectly sets LIVRÉ
2. Change line 318 to properly handle "no delivery_method"
3. Ensure new invoices start as CONFIRMÉ

### Phase 2: Build Payment UI
1. Add "Record Payment" button in Payment section
2. Create payment form with amount input
3. Create payment processing view
4. Update invoice status after payment

### Phase 3: Delivery Management
1. Add delivery status field to invoice detail
2. Allow marking invoice as delivered
3. Trigger status update when delivered

### Phase 4: Payment History
1. Create PaymentLog/Payment model to track individual payments
2. Display payment history in invoice detail
3. Show payment date and method for each payment

---

## 📋 Related Files

| File | Purpose | Status |
|------|---------|--------|
| `sales/models.py` | Invoice model & status logic | ✅ Complete (but has bug) |
| `sales/views.py` | Invoice views | ⚠️ Missing payment view |
| `templates/sales/invoice_detail.html` | Invoice display | ❌ No payment UI |
| `sales/urls.py` | Routes | ❌ Missing payment route |
| `sales/forms.py` | Forms | ❌ Missing payment form |

---

## 🐛 Known Issues

1. **Wrong Initial Status**
   - Invoices show "LIVRÉ" instead of "CONFIRMÉ"
   - Cause: `delivery_method = None` interpreted as "delivered"

2. **No Payment Recording**
   - Can't mark invoice as paid
   - No way to record partial payments

3. **No Delivery Tracking**
   - Can't mark invoice as delivered
   - No delivery status updates

4. **No Payment History**
   - Only shows total amount paid
   - No individual payment records

---

## ✅ Recommendation

**Priority:** HIGH

The status logic is good but **needs UI implementation** to be useful. Users need:
1. A way to record payments
2. A way to track delivery
3. Accurate status display

Without these, the status feature is incomplete and confusing.

---

**Last Updated:** February 4, 2026
**Related Issue:** Form submission now works, revealing missing payment functionality

