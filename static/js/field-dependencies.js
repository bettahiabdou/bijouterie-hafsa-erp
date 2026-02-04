/**
 * Field Dependencies Module
 * Phase 3: Smart Field Dependencies and Conditional Visibility
 *
 * Manages conditional field visibility, auto-fill, cascading dropdowns, and calculations
 */

(function() {
  'use strict';

  /**
   * FieldDependencies - Smart field management
   */
  const FieldDependencies = {
    // Define field relationships and behaviors
    dependencies: {
      // Payment method determines if payment reference and bank account fields show
      '[name="payment_method"]': {
        onchange: function(value) {
          const paymentRefSection = document.getElementById('paymentRefSection');
          const bankAccountSection = document.getElementById('bankAccountSection');

          if (!paymentRefSection || !bankAccountSection) return;

          const selectedText = this.options?.[this.selectedIndex]?.text || '';
          const selectedLower = selectedText.toLowerCase();

          // Methods that don't require reference: cash/espèces
          const noReferenceNeeded = ['espèces', 'cash', 'espece'];
          const needsReference = !noReferenceNeeded.some(text =>
            selectedLower.includes(text.toLowerCase())
          );

          // Only bank transfers need bank account
          const isBankTransfer = selectedLower.includes('virement');

          // Update visibility
          FieldDependencies.toggleSection(paymentRefSection, needsReference);
          FieldDependencies.toggleSection(bankAccountSection, isBankTransfer);

          console.log('✓ Payment method changed:', selectedText);
        }
      },

      // Product selection auto-fills price
      '[name="product_id"]': {
        onchange: function() {
          const option = this.options?.[this.selectedIndex];
          const unitPriceInput = document.getElementById('unit_price');

          if (option && option.dataset.price && unitPriceInput) {
            unitPriceInput.value = parseFloat(option.dataset.price).toFixed(2);
            console.log('✓ Auto-filled price:', unitPriceInput.value);

            // Trigger calculation update
            if (window.updateEstimatedTotal) {
              window.updateEstimatedTotal();
            }
          }
        }
      },

      // Product category might affect available types (extensible)
      '[name="product_category"]': {
        onchange: function() {
          console.log('✓ Category changed:', this.value);
          // Can be extended to filter product types
        }
      },

      // Quantity changes trigger price calculation
      '[name="quantity"]': {
        onchange: function() {
          if (window.updateEstimatedTotal) {
            window.updateEstimatedTotal();
          }
        },
        oninput: function() {
          if (window.updateEstimatedTotal) {
            window.updateEstimatedTotal();
          }
        }
      },

      // Discount changes trigger price calculation
      '[name="discount_amount"]': {
        onchange: function() {
          if (window.updateEstimatedTotal) {
            window.updateEstimatedTotal();
          }
        },
        oninput: function() {
          if (window.updateEstimatedTotal) {
            window.updateEstimatedTotal();
          }
        }
      },

      // Selling price changes
      '[name="selling_price"]': {
        onchange: function() {
          if (window.calculatePreview) {
            window.calculatePreview();
          }
        },
        oninput: function() {
          if (window.calculatePreview) {
            window.calculatePreview();
          }
        }
      },

      // Product weight changes
      '[name="product_weight"]': {
        onchange: function() {
          if (window.calculatePreview) {
            window.calculatePreview();
          }
        },
        oninput: function() {
          if (window.calculatePreview) {
            window.calculatePreview();
          }
        }
      },

      // Purchase price changes
      '[name="purchase_price_per_gram"]': {
        onchange: function() {
          if (window.calculatePreview) {
            window.calculatePreview();
          }
        },
        oninput: function() {
          if (window.calculatePreview) {
            window.calculatePreview();
          }
        }
      },

      // Labor cost changes
      '[name="labor_cost"]': {
        onchange: function() {
          if (window.calculatePreview) {
            window.calculatePreview();
          }
        },
        oninput: function() {
          if (window.calculatePreview) {
            window.calculatePreview();
          }
        }
      },

      // Stone cost changes
      '[name="stone_cost"]': {
        onchange: function() {
          if (window.calculatePreview) {
            window.calculatePreview();
          }
        },
        oninput: function() {
          if (window.calculatePreview) {
            window.calculatePreview();
          }
        }
      },

      // Other costs changes
      '[name="other_cost"]': {
        onchange: function() {
          if (window.calculatePreview) {
            window.calculatePreview();
          }
        },
        oninput: function() {
          if (window.calculatePreview) {
            window.calculatePreview();
          }
        }
      },

      // Margin type changes
      '[name="margin_type"]': {
        onchange: function() {
          const marginUnit = document.getElementById('margin_unit_batch');
          if (marginUnit) {
            marginUnit.textContent = this.value === 'percentage' ? '%' : 'DH';
          }
          if (window.calculatePreview) {
            window.calculatePreview();
          }
        }
      },

      // Margin value changes
      '[name="margin_value"]': {
        onchange: function() {
          if (window.calculatePreview) {
            window.calculatePreview();
          }
        },
        oninput: function() {
          if (window.calculatePreview) {
            window.calculatePreview();
          }
        }
      },

      // Amount paid changes
      '[name="amount_paid"]': {
        onchange: function() {
          if (window.updateInvoiceSummary) {
            window.updateInvoiceSummary();
          }
        },
        oninput: function() {
          if (window.updateInvoiceSummary) {
            window.updateInvoiceSummary();
          }
        }
      },

      // Tax rate changes
      '[name="tax_rate"]': {
        onchange: function() {
          // Form has internal handler, but we can extend here
          console.log('✓ Tax rate changed:', this.value);
        }
      }
    },

    /**
     * Initialize all field dependencies
     */
    init: function() {
      console.log('✓ Initializing field dependencies');

      Object.keys(FieldDependencies.dependencies).forEach(selector => {
        const fields = document.querySelectorAll(selector);

        fields.forEach(field => {
          const dependency = FieldDependencies.dependencies[selector];

          // Attach onchange handler
          if (dependency.onchange) {
            field.addEventListener('change', dependency.onchange);
          }

          // Attach oninput handler
          if (dependency.oninput) {
            field.addEventListener('input', FieldDependencies.debounce(dependency.oninput, 150));
          }

          // Trigger initial dependency check
          if (dependency.onchange && field.value) {
            dependency.onchange.call(field);
          }
        });
      });

      console.log('✓ Field dependencies initialized');
    },

    /**
     * Toggle section visibility
     */
    toggleSection: function(section, show) {
      if (!section) return;

      if (show) {
        section.classList.remove('hidden');
        section.style.display = 'block';
      } else {
        section.classList.add('hidden');
        section.style.display = 'none';
      }
    },

    /**
     * Show field
     */
    showField: function(field) {
      if (!field) return;
      field.classList.remove('hidden');
      field.style.display = '';
      field.disabled = false;
    },

    /**
     * Hide field
     */
    hideField: function(field) {
      if (!field) return;
      field.classList.add('hidden');
      field.style.display = 'none';
      field.disabled = true;
    },

    /**
     * Enable field
     */
    enableField: function(field) {
      if (!field) return;
      field.disabled = false;
      field.classList.remove('opacity-50');
    },

    /**
     * Disable field
     */
    disableField: function(field) {
      if (!field) return;
      field.disabled = true;
      field.classList.add('opacity-50');
    },

    /**
     * Auto-fill field with value
     */
    autoFill: function(field, value) {
      if (!field) return;
      field.value = value;

      // Trigger change event to update dependent fields
      const event = new Event('change', { bubbles: true });
      field.dispatchEvent(event);

      console.log('✓ Auto-filled:', field.name, '=', value);
    },

    /**
     * Debounce function for performance
     */
    debounce: function(func, delay) {
      let timeout;
      return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), delay);
      };
    },

    /**
     * Add custom dependency
     */
    addDependency: function(selector, dependency) {
      FieldDependencies.dependencies[selector] = dependency;
      console.log('✓ Added field dependency:', selector);

      // Initialize the new dependency
      const field = document.querySelector(selector);
      if (field && dependency.onchange) {
        field.addEventListener('change', dependency.onchange);
        if (dependency.oninput) {
          field.addEventListener('input', FieldDependencies.debounce(dependency.oninput, 150));
        }
      }
    }
  };

  /**
   * Initialize when DOM is ready
   */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', FieldDependencies.init);
  } else {
    FieldDependencies.init();
  }

  // Export for global access
  window.FieldDependencies = FieldDependencies;

})();
