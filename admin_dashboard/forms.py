"""
Forms for Admin Dashboard
"""

from django import forms
from users.models import User


class UserManagementForm(forms.ModelForm):
    """Form for creating and editing users"""

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500',
            'placeholder': 'Mot de passe (laisser vide pour ne pas changer)'
        }),
        required=False,
        help_text='Laisser vide pour ne pas changer le mot de passe existant'
    )

    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500',
            'placeholder': 'Confirmer le mot de passe'
        }),
        required=False,
        help_text='Confirmer le mot de passe'
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'first_name_ar', 'last_name_ar', 'role', 'is_active']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500',
                'placeholder': 'Nom d\'utilisateur'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500',
                'placeholder': 'Email'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500',
                'placeholder': 'Prénom'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500',
                'placeholder': 'Nom'
            }),
            'first_name_ar': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500',
                'placeholder': 'Prénom (Arabe)'
            }),
            'last_name_ar': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500',
                'placeholder': 'Nom (Arabe)'
            }),
            'role': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 rounded'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')

        if password or password_confirm:
            if password != password_confirm:
                raise forms.ValidationError('Les mots de passe ne correspondent pas.')

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)

        # Set password if provided
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)

        if commit:
            user.save()

        return user
