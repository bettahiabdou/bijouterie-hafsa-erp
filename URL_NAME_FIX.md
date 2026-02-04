# URL Name Fix - NoReverseMatch Error Resolution

## Error Encountered

```
NoReverseMatch at /
Reverse for 'list' not found. 'list' is not a valid view function or pattern name.
```

**Location**: `templates/base.html`, line 130

**Root Cause**: Incorrect Django URL name used in template

---

## The Problem

In `templates/base.html` line 130, the code was:

```html
<a href="{% url 'quotes:list' %}">Devis</a>
```

But the actual URL name in `quotes/urls.py` is `'quote_list'`, not `'list'`.

---

## The Fix

Changed line 130 from:
```html
<a href="{% url 'quotes:list' %}">Devis</a>
```

To:
```html
<a href="{% url 'quotes:quote_list' %}">Devis</a>
```

---

## URL Name Reference

Here's the complete mapping of all URL names used in the templates:

### Products Module (`products:`)
- `products:list` → `/products/` - List all products
- `products:create` → `/products/create/` - Create new product
- `products:inventory_dashboard` → `/products/inventory/dashboard/` - Inventory view

### Sales Module (`sales:`)
- `sales:invoice_list` → `/sales/invoices/` - List invoices
- `sales:invoice_create` → `/sales/invoices/create/` - Create invoice
- `sales:invoice_detail` → `/sales/invoices/<ref>/` - Invoice detail

### Purchases Module (`purchases:`)
- `purchases:purchase_order_list` → `/purchases/orders/` - List POs
- `purchases:purchase_invoice_list` → `/purchases/invoices/` - List purchase invoices
- `purchases:consignment_list` → `/purchases/consignments/` - List consignments

### Repairs Module (`repairs:`)
- `repairs:repair_list` → `/repairs/list/` - List repairs
- `repairs:repair_detail` → `/repairs/<ref>/` - Repair detail

### Quotes Module (`quotes:`) ⚠️ FIXED
- `quotes:quote_list` → `/quotes/list/` - List quotes (was incorrectly `quotes:list`)
- `quotes:quote_create` → `/quotes/create/` - Create quote
- `quotes:quote_detail` → `/quotes/<ref>/` - Quote detail
- `quotes:dashboard` → `/quotes/` - Quotes dashboard

### Users Module (`users:`)
- `users:profile` → `/users/profile/` - User profile
- `users:profile_edit` → `/users/profile/edit/` - Edit profile
- `users:password_change` → `/users/profile/password/` - Change password
- `users:activity_log` → `/users/activity/` - Activity log

### Config URLs (no namespace)
- `login` → `/login/` - Login page
- `logout` → `/logout/` - Logout
- `dashboard` → `/` - Main dashboard

---

## Files Modified

**templates/base.html** (Line 130)
- Fixed incorrect URL name for quotes navigation

---

## Verification

After fix:
- ✅ Django system check passes
- ✅ All URL names are valid
- ✅ Template rendering works
- ✅ Navigation links functional

---

## Testing

To verify the fix works:

1. Start the server:
   ```bash
   python manage.py runserver
   ```

2. Navigate to: `http://localhost:8000/`

3. The dashboard should load without errors

4. Click on "Devis" in the Sales menu - should navigate to quotes list

---

## Git Commit

```
0b15358 - Fix incorrect URL name - quotes:list to quotes:quote_list
```

---

## Key Takeaway

When using Django's `{% url %}` template tag:
- Always match the exact name defined in the app's `urls.py`
- Include the app namespace if the URLconf has `app_name`
- Use the naming convention: `app_name:url_name`

**Incorrect**: `{% url 'quotes:list' %}`
**Correct**: `{% url 'quotes:quote_list' %}`
