/**
 * Form Validation Module
 * Phase 3: Inline Form Validation with Real-time Feedback
 *
 * Provides real-time validation, error messages, and visual feedback for form fields
 */

(function() {
  'use strict';

  /**
   * FormValidator - Main validation engine
   */
  const FormValidator = {
    // Default validation rules
    rules: {
      // Required field validation
      '[data-validate="required"]': {
        required: true,
        message: 'Ce champ est obligatoire'
      },
      '[name="client"]': {
        required: false, // Optional field
        message: 'Client is required'
      },
      // Note: product_id and quantity validation removed - handled by individual form validation
      // to support desktop/mobile dual views with same field names
      '[name="product_weight"]': {
        required: true,
        min: 0,
        message: 'Le poids est obligatoire',
        messageMin: 'Le poids doit être positif'
      },
      '[name="product_category"]': {
        required: true,
        message: 'La catégorie est obligatoire'
      },
      '[name="product_type"]': {
        required: true,
        message: 'Le type est obligatoire'
      },
      '[name="product_name"]': {
        required: true,
        minLength: 2,
        message: 'Le nom du produit est obligatoire',
        messageMinLength: 'Le nom doit contenir au moins 2 caractères'
      },
      '[name="product_selling_price"]': {
        required: false,
        min: 0,
        messageMin: 'Le prix doit être positif'
      },
      '[name="selling_price"]': {
        required: false,
        min: 0,
        messageMin: 'Le prix doit être positif'
      },
      '[name="purchase_price_per_gram"]': {
        required: true,
        min: 0,
        message: 'Le prix est obligatoire',
        messageMin: 'Le prix doit être positif'
      },
      '[name="margin_value"]': {
        required: true,
        min: 0,
        message: 'La marge est obligatoire',
        messageMin: 'La marge doit être positive'
      }
    },

    /**
     * Initialize validation for all form fields
     */
    init: function() {
      if (window.innerWidth > 1280) {
        console.log('✓ Form validation available (desktop mode)');
      } else {
        console.log('✓ Form validation active (mobile mode)');
      }

      // Attach event listeners to all form fields
      document.querySelectorAll('input, select, textarea').forEach(field => {
        // Validate on blur
        field.addEventListener('blur', () => {
          FormValidator.validate(field);
        });

        // Validate on input (with debounce for better performance)
        field.addEventListener('input', FormValidator.debounce(() => {
          FormValidator.validate(field);
        }, 300));

        // Validate on change for selects
        if (field.tagName === 'SELECT') {
          field.addEventListener('change', () => {
            FormValidator.validate(field);
          });
        }
      });

      // Validate on form submission
      document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', (e) => {
          const isValid = FormValidator.validateForm(form);
          if (!isValid) {
            e.preventDefault();
            FormValidator.scrollToFirstError();
          }
        });
      });

      console.log('✓ Form validation listeners attached');
    },

    /**
     * Check if an element is visible (not hidden by CSS)
     */
    isElementVisible: function(element) {
      if (!element) return false;

      // Quick check: if element is inside a desktop-view or mobile-view container,
      // check if that container is currently visible based on viewport width
      const desktopView = element.closest('.desktop-view');
      const mobileView = element.closest('.mobile-view');
      const isMobileViewport = window.innerWidth <= 768;

      // If in desktop-view but we're on mobile viewport, skip validation
      if (desktopView && isMobileViewport) {
        return false;
      }

      // If in mobile-view but we're on desktop viewport, skip validation
      if (mobileView && !isMobileViewport) {
        return false;
      }

      // Also check computed style for other hidden elements
      let el = element;
      while (el) {
        const style = window.getComputedStyle(el);
        if (style.display === 'none') {
          return false;
        }
        el = el.parentElement;
      }
      return true;
    },

    /**
     * Validate a single field
     */
    validate: function(field) {
      if (!field) return true;

      // Skip hidden fields (e.g., desktop/mobile toggle views)
      if (!FormValidator.isElementVisible(field)) {
        return true;
      }

      const selector = FormValidator.getFieldSelector(field);
      const rule = FormValidator.rules[selector];

      if (!rule) return true;

      let isValid = true;
      const value = field.value.trim();

      // Check required
      if (rule.required && !value) {
        FormValidator.showError(field, rule.message || 'Ce champ est obligatoire');
        return false;
      }

      if (!value) {
        FormValidator.clearError(field);
        return true;
      }

      // Check minLength
      if (rule.minLength && value.length < rule.minLength) {
        FormValidator.showError(field, rule.messageMinLength || rule.message);
        return false;
      }

      // Check min value
      if (rule.min !== undefined && parseFloat(value) < rule.min) {
        FormValidator.showError(field, rule.messageMin || rule.message);
        return false;
      }

      // Check max value
      if (rule.max !== undefined && parseFloat(value) > rule.max) {
        FormValidator.showError(field, rule.messageMax || rule.message);
        return false;
      }

      FormValidator.clearError(field);
      return true;
    },

    /**
     * Validate entire form
     */
    validateForm: function(form) {
      let isValid = true;
      const fields = form.querySelectorAll('input, select, textarea');

      fields.forEach(field => {
        if (!FormValidator.validate(field)) {
          isValid = false;
        }
      });

      return isValid;
    },

    /**
     * Get field selector from field element
     */
    getFieldSelector: function(field) {
      // Try by name attribute
      if (field.name) {
        const byName = `[name="${field.name}"]`;
        if (FormValidator.rules[byName]) return byName;
      }

      // Try by data-validate attribute
      if (field.dataset.validate) {
        const byData = `[data-validate="${field.dataset.validate}"]`;
        if (FormValidator.rules[byData]) return byData;
      }

      return null;
    },

    /**
     * Show error message
     */
    showError: function(field, message) {
      // Remove existing error if present
      FormValidator.clearError(field);

      // Add error class to field
      field.classList.add('is-invalid');
      field.style.borderColor = '#dc2626';

      // Create error message element
      const errorDiv = document.createElement('div');
      errorDiv.className = 'form-error-message';
      errorDiv.style.cssText = `
        color: #dc2626;
        font-size: 0.875rem;
        margin-top: 0.25rem;
        animation: slideDown 0.2s ease-out;
      `;
      errorDiv.textContent = message;

      // Insert after field
      field.parentNode.insertBefore(errorDiv, field.nextSibling);

      // Add aria-invalid for accessibility
      field.setAttribute('aria-invalid', 'true');
      field.setAttribute('aria-describedby', 'error-' + (field.name || Math.random()));
      errorDiv.id = 'error-' + (field.name || Math.random());

      console.log('✗ Validation error:', field.name, '-', message);
    },

    /**
     * Clear error message
     */
    clearError: function(field) {
      field.classList.remove('is-invalid');
      field.style.borderColor = '';

      // Remove error message element
      const errorMsg = field.parentNode.querySelector('.form-error-message');
      if (errorMsg) {
        errorMsg.style.animation = 'slideUp 0.2s ease-out';
        setTimeout(() => errorMsg.remove(), 200);
      }

      field.removeAttribute('aria-invalid');
    },

    /**
     * Scroll to first error field
     */
    scrollToFirstError: function() {
      const firstError = document.querySelector('.is-invalid');
      if (firstError && window.innerWidth < 768) {
        setTimeout(() => {
          firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
          firstError.focus();
        }, 100);
      }
    },

    /**
     * Debounce function
     */
    debounce: function(func, delay) {
      let timeout;
      return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func(...args), delay);
      };
    },

    /**
     * Add custom validation rule
     */
    addRule: function(selector, rule) {
      FormValidator.rules[selector] = rule;
      console.log('✓ Added validation rule:', selector);
    }
  };

  /**
   * Initialize when DOM is ready
   */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', FormValidator.init);
  } else {
    FormValidator.init();
  }

  // Export for global access
  window.FormValidator = FormValidator;

})();

/**
 * CSS Animations for form validation
 */
const validationStyles = document.createElement('style');
validationStyles.textContent = `
  /* Validation error styles */
  .is-invalid {
    border-color: #dc2626 !important;
    background-color: #fef2f2 !important;
  }

  .is-invalid:focus {
    border-color: #b91c1c !important;
    box-shadow: 0 0 0 3px rgba(220, 38, 38, 0.1) !important;
  }

  .form-error-message {
    color: #dc2626;
    font-size: 0.875rem;
    margin-top: 0.25rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .form-error-message:before {
    content: '✕';
    font-weight: bold;
    font-size: 1.125rem;
  }

  /* Validation success styles (optional) */
  .is-valid {
    border-color: #16a34a !important;
  }

  .is-valid:focus {
    box-shadow: 0 0 0 3px rgba(22, 163, 74, 0.1) !important;
  }

  /* Animations */
  @keyframes slideDown {
    from {
      opacity: 0;
      transform: translateY(-10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  @keyframes slideUp {
    from {
      opacity: 1;
      transform: translateY(0);
    }
    to {
      opacity: 0;
      transform: translateY(-10px);
    }
  }

  /* Touch-friendly error messages on mobile */
  @media (max-width: 768px) {
    .form-error-message {
      padding: 0.5rem;
      background-color: #fef2f2;
      border-left: 3px solid #dc2626;
      margin-left: -0.5rem;
      margin-right: -0.5rem;
      margin-top: 0.5rem;
    }
  }
`;
document.head.appendChild(validationStyles);
