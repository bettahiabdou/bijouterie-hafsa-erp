"""
Sales forms for Bijouterie Hafsa ERP
Includes invoice, payment, and delivery forms with comprehensive validation
"""
from django import forms
from django.core.exceptions import ValidationError
from decimal import Decimal
from .models import SaleInvoice, SaleInvoiceItem, ClientLoan, ClientLoanItem, Layaway
from products.models import Product
from clients.models import Client
from settings_app.models import PaymentMethod, BankAccount, DeliveryMethod, DeliveryPerson


class SaleInvoiceForm(forms.ModelForm):
    """Form for creating and editing sale invoices"""

    # Additional field for payment amount during invoice creation
    amount_paid = forms.DecimalField(
        required=False,
        min_value=0,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
            'step': '0.01',
            'min': '0',
            'placeholder': '0.00'
        }),
        help_text='Montant payé lors de la création (optionnel)'
    )

    class Meta:
        model = SaleInvoice
        fields = [
            'reference', 'date', 'client', 'payment_method', 'bank_account',
            'tax_rate', 'notes', 'payment_reference'
        ]
        widgets = {
            'reference': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
                'placeholder': 'INV-20260210-0001'
            }),
            'date': forms.DateInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
                'type': 'date'
            }),
            'client': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
            }),
            'payment_method': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
            }),
            'bank_account': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
            }),
            'tax_rate': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
                'step': '0.01',
                'min': '0',
                'max': '100',
                'value': '0',
                'placeholder': '0.00'
            }),
            'payment_reference': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
                'placeholder': 'N° de chèque, référence virement, n° de carte...'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none',
                'rows': '3'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add data attributes to payment method options for dynamic visibility
        if 'payment_method' in self.fields:
            self.fields['payment_method'].widget.attrs.update({
                'id': 'paymentMethodSelect',
            })

        # Make optional fields actually optional
        optional_fields = [
            'payment_method', 'bank_account', 'tax_rate', 'notes', 'payment_reference'
        ]
        for field_name in optional_fields:
            if field_name in self.fields:
                self.fields[field_name].required = False

    def clean(self):
        """Validate form data"""
        cleaned_data = super().clean()
        reference = cleaned_data.get('reference')
        client = cleaned_data.get('client')
        tax_rate = cleaned_data.get('tax_rate')
        payment_method = cleaned_data.get('payment_method')
        payment_reference = cleaned_data.get('payment_reference')

        # Validate reference is unique (if changed)
        if reference:
            from sales.models import SaleInvoice
            existing = SaleInvoice.objects.filter(reference=reference).exclude(
                id=self.instance.id if self.instance.id else None
            )
            if existing.exists():
                raise ValidationError(
                    f'La référence "{reference}" existe déjà. Veuillez en choisir une autre.'
                )

        # Validate tax rate
        if tax_rate and (tax_rate < 0 or tax_rate > 100):
            raise ValidationError('Le taux TVA doit être entre 0 et 100%.')

        # Validate client credit limit (is_over_credit_limit is a property, not a method)
        if client and client.is_over_credit_limit:
            raise ValidationError(
                f'Le client {client.full_name} a dépassé sa limite de crédit.'
            )

        # VALIDATION: Payment reference is required for certain payment methods
        # Only validate when creating a new invoice OR when payment method is being changed
        is_new = not self.instance.id
        payment_method_changed = payment_method and (
            is_new or
            (self.instance.payment_method_id != payment_method.id if payment_method else False)
        )

        if payment_method and (is_new or payment_method_changed):
            payment_method_name = str(payment_method).lower()
            # Methods that require a reference
            REQUIRES_REFERENCE = ['virement', 'transfer', 'chèque', 'cheque', 'check', 'carte', 'card', 'mobile']
            requires_ref = any(req in payment_method_name for req in REQUIRES_REFERENCE)

            if requires_ref and not payment_reference:
                # Check if existing payment_reference exists on the invoice
                existing_ref = self.instance.payment_reference if self.instance.id else None
                if not existing_ref:
                    raise ValidationError(
                        f'Une référence de paiement est obligatoire pour {payment_method} '
                        '(N° de chèque, référence virement, n° de carte, etc.)'
                    )

        # Validate payment reference is unique (if provided and changed)
        if payment_reference:
            # Check for duplicates (exclude current invoice if editing)
            from sales.models import SaleInvoice
            existing = SaleInvoice.objects.filter(
                payment_reference=payment_reference
            ).exclude(
                id=self.instance.id if self.instance.id else None
            )
            if existing.exists():
                raise ValidationError(
                    f'Cette référence de paiement est déjà utilisée par la facture {existing.first().reference}'
                )

        return cleaned_data


class SaleInvoiceItemForm(forms.ModelForm):
    """Form for individual invoice line items"""

    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(status='available').select_related(
            'category', 'metal_type', 'metal_purity', 'supplier'
        ),
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
        })
    )

    class Meta:
        model = SaleInvoiceItem
        fields = ['product', 'quantity', 'negotiated_price', 'discount_amount', 'notes']
        widgets = {
            'quantity': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
                'step': '0.001',
                'min': '0.001',
                'value': '1'
            }),
            'negotiated_price': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
                'step': '0.01',
                'min': '0'
            }),
            'discount_amount': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
                'step': '0.01',
                'min': '0'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none',
                'rows': '2'
            }),
        }

    def clean(self):
        """Validate line item"""
        cleaned_data = super().clean()
        quantity = cleaned_data.get('quantity')
        negotiated_price = cleaned_data.get('negotiated_price')
        product = cleaned_data.get('product')

        # Validate quantity
        if quantity and quantity <= 0:
            raise ValidationError('La quantité doit être supérieure à 0.')

        # Validate price
        if negotiated_price is not None and negotiated_price < 0:
            raise ValidationError('Le prix doit être positif.')

        # Check minimum price if configured
        if product and negotiated_price is not None:
            if product.is_below_minimum() and not product.allow_below_minimum_price:
                raise ValidationError(
                    f'Le prix {negotiated_price} DH est en dessous du prix minimum '
                    f'configuré ({product.minimum_selling_price} DH).'
                )

        return cleaned_data


class SaleInvoiceItemFormSet(forms.BaseInlineFormSet):
    """FormSet for managing multiple invoice items"""

    def clean(self):
        """Validate the entire formset"""
        super().clean()

        # Ensure at least one item
        if not any(self.cleaned_data) or len(self.cleaned_data) == 0:
            raise ValidationError('Une facture doit contenir au moins un article.')

        # Validate no duplicate products
        products = []
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get('DELETE'):
                product = form.cleaned_data.get('product')
                if product in products:
                    raise ValidationError('Un produit ne peut être ajouté qu\'une fois par facture.')
                products.append(product)


class PaymentForm(forms.Form):
    """Form for recording payments on invoices"""

    amount = forms.DecimalField(
        label='Montant payé (DH)',
        max_digits=14,
        decimal_places=2,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
            'step': '0.01',
            'min': '0.01',
            'placeholder': '0.00'
        })
    )

    payment_method = forms.ModelChoiceField(
        queryset=PaymentMethod.objects.filter(is_active=True),
        label='Méthode de paiement',
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
        })
    )

    bank_account = forms.ModelChoiceField(
        queryset=BankAccount.objects.filter(is_active=True),
        label='Compte bancaire',
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
        })
    )

    payment_reference = forms.CharField(
        label='Référence de paiement',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
            'placeholder': 'N° de chèque, référence virement, n° de carte...'
        })
    )

    notes = forms.CharField(
        label='Notes',
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none',
            'rows': '3'
        })
    )

    def clean(self):
        """Validate payment data"""
        cleaned_data = super().clean()
        amount = cleaned_data.get('amount')
        payment_method = cleaned_data.get('payment_method')

        if amount and amount <= 0:
            raise ValidationError('Le montant du paiement doit être positif.')

        if not payment_method:
            raise ValidationError('Veuillez sélectionner une méthode de paiement.')

        return cleaned_data


class DeliveryForm(forms.ModelForm):
    """Form for updating delivery information"""

    class Meta:
        model = SaleInvoice
        fields = ['delivery_method', 'delivery_person', 'delivery_address', 'delivery_cost', 'delivery_status', 'delivery_date']
        widgets = {
            'delivery_method': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
            }),
            'delivery_person': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
            }),
            'delivery_address': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none',
                'rows': '3'
            }),
            'delivery_cost': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
                'step': '0.01',
                'min': '0'
            }),
            'delivery_status': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
            }),
            'delivery_date': forms.DateInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
                'type': 'date'
            }),
        }


class ClientLoanForm(forms.ModelForm):
    """Form for creating client loans"""

    items = forms.ModelMultipleChoiceField(
        queryset=Product.objects.filter(status='available').select_related(
            'category', 'metal_type', 'metal_purity'
        ),
        label='Articles à prêter',
        widget=forms.CheckboxSelectMultiple()
    )

    class Meta:
        model = ClientLoan
        fields = ['client', 'return_date', 'deposit_amount', 'notes']
        widgets = {
            'client': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
            }),
            'return_date': forms.DateInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
                'type': 'date'
            }),
            'deposit_amount': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
                'step': '0.01',
                'min': '0'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none',
                'rows': '3'
            }),
        }


class LayawayForm(forms.ModelForm):
    """Form for creating layaway plans"""

    class Meta:
        model = Layaway
        fields = ['client', 'product', 'agreed_price', 'expiry_date', 'notes']
        widgets = {
            'client': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
            }),
            'product': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
            }),
            'agreed_price': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
                'step': '0.01',
                'min': '0.01'
            }),
            'expiry_date': forms.DateInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
                'type': 'date'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none',
                'rows': '3'
            }),
        }

    def clean(self):
        """Validate layaway"""
        cleaned_data = super().clean()
        agreed_price = cleaned_data.get('agreed_price')
        product = cleaned_data.get('product')

        if agreed_price and agreed_price <= 0:
            raise ValidationError('Le prix doit être supérieur à 0.')

        if product and agreed_price:
            if agreed_price < product.total_cost:
                raise ValidationError(
                    f'Le prix convenu ({agreed_price} DH) ne peut pas être inférieur '
                    f'au coût d\'achat ({product.total_cost} DH).'
                )

        return cleaned_data
