# 📊 Invoice Status Logic - How It Works

**File:** `sales/models.py` - `SaleInvoice.update_status()` method
**Logic:** Automatic status determination based on **payment amount** and **delivery status**

---

## 📋 Possible Invoice Statuses

| Status | French | Code | Description |
|--------|--------|------|-------------|
| **Brouillon** | Draft | `draft` | Invoice not yet confirmed |
| **Confirmé** | Confirmed | `confirmed` | ✅ Invoice created, waiting for payment |
| **Partiellement payé** | Partially Paid | `partial` | 💰 Some payment received, but not fully paid |
| **Payé** | Paid | `paid` | ✅ Fully paid, but not delivered yet |
| **Livré** | Delivered | `delivered` | ✅ Delivered to customer (payment complete) |
| **Annulé** | Cancelled | `cancelled` | ❌ Invoice cancelled |

---

## 🔄 Status Determination Logic

The status is **automatically calculated** based on:
1. **Amount Paid** (`amount_paid`)
2. **Total Amount** (`total_amount`)
3. **Delivery Status** (`delivery_status`)
4. **Delivery Method** (`delivery_method`)

### Decision Tree

```
Is status CANCELLED?
└─ YES → Stay CANCELLED (don't change)
└─ NO → Check payment:

    Is amount_paid >= total_amount?
    └─ YES (fully paid) → Check delivery:
        ├─ If delivered OR no delivery method set
        │  └─ Status = DELIVERED (Livré) ✅
        └─ If not delivered AND delivery method exists
           └─ Status = PAID (Payé) ✅

    └─ NO (not fully paid) → Check if any payment made:
        ├─ If amount_paid > 0 (some payment)
        │  └─ Status = PARTIAL_PAID (Partiellement payé) 💰
        └─ If amount_paid = 0 (no payment)
           └─ Status = CONFIRMED (Confirmé) ⏳
```

---

## 📝 Examples

### Example 1: New Invoice Created
```
When you create an invoice:
- amount_paid = 0 DH
- total_amount = 1000 DH
- delivery_status = (empty/not set)

Logic:
- amount_paid (0) = 0? YES
- Status = CONFIRMED ✅
```

### Example 2: Partial Payment Received
```
Invoice:
- amount_paid = 400 DH
- total_amount = 1000 DH
- delivery_status = (empty/not set)

Logic:
- amount_paid (400) >= total_amount (1000)? NO
- amount_paid (400) > 0? YES
- Status = PARTIAL_PAID 💰
```

### Example 3: Full Payment Received (No Delivery)
```
Invoice:
- amount_paid = 1000 DH
- total_amount = 1000 DH
- delivery_status = (empty/not set)
- delivery_method = (empty/not set)

Logic:
- amount_paid (1000) >= total_amount (1000)? YES
- delivery_status = empty OR delivery_method = empty? YES
- Status = DELIVERED ✅
```

### Example 4: Full Payment + Delivery Pending
```
Invoice:
- amount_paid = 1000 DH
- total_amount = 1000 DH
- delivery_status = 'pending'
- delivery_method = 'courier'

Logic:
- amount_paid (1000) >= total_amount (1000)? YES
- delivery_status = 'delivered' OR delivery_method empty? NO
- Status = PAID ✅
```

### Example 5: Fully Delivered
```
Invoice:
- amount_paid = 1000 DH
- total_amount = 1000 DH
- delivery_status = 'delivered'
- delivery_method = 'courier'

Logic:
- amount_paid (1000) >= total_amount (1000)? YES
- delivery_status = 'delivered' OR delivery_method empty? YES (delivered!)
- Status = DELIVERED ✅
```

---

## 🔄 When Status Updates

The status is **automatically updated** when:

1. **Invoice is created** → Status set to CONFIRMED
2. **Payment is recorded** → Status recalculated based on amount paid
3. **Delivery status changes** → Status recalculated

### In Code

```python
def update_payment(self, amount):
    """Update payment amount"""
    self.amount_paid += amount
    self.balance_due = self.total_amount - self.amount_paid
    self.update_status()  # ← Status recalculated automatically
    self.save(update_fields=['amount_paid', 'balance_due', 'status'])
```

---

## 🎯 Status Meanings

### CONFIRMÉ (Confirmed) ⏳
- **When:** Invoice just created, no payment yet
- **Meaning:** Waiting for customer payment
- **What to do:** Collect payment from customer

### PARTIELLEMENT PAYÉ (Partially Paid) 💰
- **When:** Customer paid some but not all
- **Meaning:** Partial payment received
- **What to do:** Collect remaining balance or deliver with payment plan

### PAYÉ (Paid) ✅
- **When:** Full payment received, but not delivered yet
- **Meaning:** Money received, waiting to deliver
- **What to do:** Ship/deliver the goods

### LIVRÉ (Delivered) ✅
- **When:** Full payment + delivery complete (OR payment with no delivery method)
- **Meaning:** Transaction complete
- **What to do:** Nothing, invoice closed

---

## 💡 Key Points

1. **Automatic:** Status changes automatically based on payment/delivery
2. **No Manual Change:** You don't manually set status (it's calculated)
3. **Payment-Driven:** Primary logic is payment amount
4. **Delivery-Aware:** Takes delivery status into account
5. **Cancelled is Final:** Once cancelled, status doesn't change

---

## 📊 Status Flow Chart

```
Create Invoice
    ↓
CONFIRMED (No payment yet)
    ↓
Customer pays partially?
    ├─ YES → PARTIAL_PAID
    │         ↓
    │         More payment?
    │         ├─ YES → PAID or DELIVERED
    │         └─ NO → stays PARTIAL_PAID
    │
    └─ NO → waiting...
            ↓
Customer pays full amount?
    ├─ YES → Check delivery
    │         ├─ Delivered? → DELIVERED ✅
    │         └─ Not delivered? → PAID ✅
    │
    └─ NO → stays CONFIRMED

Cancel?
    └─ YES → CANCELLED ❌
```

---

## 🔧 Configuration

**File:** `sales/models.py` Lines 17-23

To add new statuses or change the logic, edit:
```python
class Status(models.TextChoices):
    DRAFT = 'draft', _('Brouillon')
    CONFIRMED = 'confirmed', _('Confirmé')
    PARTIAL_PAID = 'partial', _('Partiellement payé')
    PAID = 'paid', _('Payé')
    DELIVERED = 'delivered', _('Livré')
    CANCELLED = 'cancelled', _('Annulé')
```

And update the `update_status()` method (lines 312-325) to reflect new logic.

---

## ❓ FAQ

**Q: How do I manually change the status?**
A: You don't! Status is calculated automatically. To change it, you need to:
- Record a payment (changes amount_paid)
- Update delivery status (changes delivery_status)
- Cancel the invoice (sets status to CANCELLED)

**Q: What if I need to force a status?**
A: Use the `transition_to()` method which validates allowed transitions:
```python
invoice.transition_to('paid')
```

**Q: Can an invoice go backward in status?**
A: No, there are validation rules that prevent invalid transitions.

---

**Last Updated:** February 4, 2026
**Source:** `sales/models.py` - SaleInvoice class

