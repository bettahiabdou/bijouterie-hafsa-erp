/**
 * Mobile-Friendly Forms JavaScript
 * Phase 2: Collapsible Sections, Floating Action Buttons, and Advanced Interactions
 *
 * Provides interactive enhancements for mobile-friendly data entry forms
 */

(function() {
  'use strict';

  /**
   * Initialize collapsible sections for mobile
   * Hides sections on mobile, shows/hides on toggle
   */
  function initializeCollapsibleSections() {
    const toggleButtons = document.querySelectorAll('[id$="Toggle"]');

    toggleButtons.forEach(btn => {
      btn.addEventListener('click', function(e) {
        e.preventDefault();

        // Get the content section ID by replacing 'Toggle' with 'Content'
        const contentId = this.id.replace('Toggle', 'Content');
        const content = document.getElementById(contentId);
        const icon = this.querySelector('i');

        if (!content) return;

        // Toggle visibility
        const isHidden = content.classList.contains('hidden');

        if (isHidden) {
          // Show section
          content.classList.remove('hidden');
          content.classList.add('section-expand');

          // Update icon
          if (icon) {
            icon.classList.remove('fa-chevron-down');
            icon.classList.add('fa-chevron-up');
          }

          // Scroll to section on mobile
          if (window.innerWidth < 768) {
            setTimeout(() => {
              content.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }, 100);
          }
        } else {
          // Hide section
          content.classList.add('hidden');
          content.classList.remove('section-expand');

          // Update icon
          if (icon) {
            icon.classList.remove('fa-chevron-up');
            icon.classList.add('fa-chevron-down');
          }
        }
      });
    });
  }

  /**
   * Setup floating action buttons (FAB) for bulk operations
   * Creates fixed button at bottom-right for adding items on mobile
   */
  function initializeFloatingActionButton() {
    const desktopAddButton = document.getElementById('addItemBtn') ||
                              document.getElementById('add_product_btn') ||
                              document.getElementById('addInvoiceBtn');

    if (!desktopAddButton) return;

    // Check if FAB already exists
    if (document.querySelector('.fab')) return;

    // Create FAB
    const fab = document.createElement('button');
    fab.type = 'button';
    fab.className = 'fab';
    fab.innerHTML = '<i class="fas fa-plus"></i>';
    fab.title = desktopAddButton.title || 'Ajouter';
    fab.setAttribute('aria-label', 'Ajouter un nouvel article');

    // Click handler - delegate to desktop button
    fab.addEventListener('click', function(e) {
      e.preventDefault();
      desktopAddButton.click();
    });

    // Add to body
    document.body.appendChild(fab);

    // Hide FAB when scrolled to bottom (where button usually is)
    window.addEventListener('scroll', debounce(() => {
      const rect = desktopAddButton.getBoundingClientRect();
      const isVisible = rect.top < window.innerHeight - 100;

      if (isVisible && window.innerWidth < 768) {
        fab.style.opacity = '0.5';
        fab.style.pointerEvents = 'none';
      } else {
        fab.style.opacity = '1';
        fab.style.pointerEvents = 'auto';
      }
    }, 200));
  }

  /**
   * Setup sticky form actions button area
   * Makes submit/cancel buttons stick to bottom on mobile while scrolling
   */
  function initializeStickyActions() {
    const stickyArea = document.querySelector('.form-actions-sticky');

    if (!stickyArea) return;

    // Only apply on mobile
    if (window.innerWidth >= 768) return;

    let lastScrollY = window.scrollY;

    window.addEventListener('scroll', debounce(() => {
      const currentScrollY = window.scrollY;
      const isScrollingDown = currentScrollY > lastScrollY;

      lastScrollY = currentScrollY;

      // Show/hide based on scroll direction
      if (isScrollingDown && currentScrollY > 100) {
        stickyArea.style.opacity = '0.9';
        stickyArea.style.visibility = 'visible';
      } else {
        stickyArea.style.opacity = '1';
      }
    }, 100));
  }

  /**
   * Debounce function to prevent excessive function calls
   */
  function debounce(func, delay) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, delay);
    };
  }

  /**
   * Initialize table responsiveness
   * Transform table rows to cards on mobile with proper label display
   */
  function initializeTableResponsiveness() {
    const tables = document.querySelectorAll('.table-responsive-cards');

    tables.forEach(table => {
      // Get all data-label attributes from header
      const headers = table.querySelectorAll('thead th');
      const rows = table.querySelectorAll('tbody tr');

      rows.forEach(row => {
        const cells = row.querySelectorAll('td');

        cells.forEach((cell, index) => {
          const header = headers[index];
          if (header && !cell.hasAttribute('data-label')) {
            const label = header.textContent.trim();
            cell.setAttribute('data-label', label);
          }
        });
      });
    });
  }

  /**
   * Enhance form inputs with better mobile interaction
   * Prevent accidental submissions and improve touch experience
   */
  function enhanceFormInputs() {
    const inputs = document.querySelectorAll('input[type="number"], input[type="text"], select');

    inputs.forEach(input => {
      // Ensure minimum font size to prevent iOS auto-zoom
      if (window.innerWidth <= 768) {
        input.style.fontSize = '16px';
      }

      // Add better focus handling
      input.addEventListener('focus', function() {
        // Scroll element into view on mobile
        if (window.innerWidth < 768) {
          this.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      });
    });
  }

  /**
   * Initialize keyboard handling for mobile
   * Improve number input experience
   */
  function initializeKeyboardHandling() {
    const numberInputs = document.querySelectorAll('input[type="number"]');

    numberInputs.forEach(input => {
      // Handle decimal input for locales that use comma
      input.addEventListener('change', function() {
        // Convert comma to dot for proper parsing
        const value = this.value.replace(',', '.');
        this.value = value;
      });

      // Improve inputmode for mobile keyboards
      input.setAttribute('inputmode', 'decimal');
    });
  }

  /**
   * Setup scroll restoration for sticky headers
   */
  function initializeStickyHeaders() {
    const header = document.querySelector('.sticky');

    if (!header) return;

    let lastScrollY = 0;

    window.addEventListener('scroll', debounce(() => {
      const currentScrollY = window.scrollY;

      if (currentScrollY > 100) {
        header.style.boxShadow = '0 4px 6px rgba(0, 0, 0, 0.1)';
      } else {
        header.style.boxShadow = 'none';
      }

      lastScrollY = currentScrollY;
    }, 50));
  }

  /**
   * Initialize form submission handlers
   * Add loading states and prevent double submissions
   */
  function initializeFormSubmission() {
    const forms = document.querySelectorAll('form[method="post"]');

    forms.forEach(form => {
      form.addEventListener('submit', function(e) {
        const submitBtn = this.querySelector('button[type="submit"]');

        if (submitBtn && !submitBtn.disabled) {
          // Add loading state
          submitBtn.disabled = true;
          submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Veuillez patienter...';

          // Re-enable after 3 seconds (failsafe)
          setTimeout(() => {
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="fas fa-save mr-2"></i> Envoyer';
          }, 3000);
        }
      });
    });
  }

  /**
   * Initialize validation feedback
   * Show/hide error messages with animations
   */
  function initializeValidationFeedback() {
    const errorMessages = document.querySelectorAll('.form-error');

    errorMessages.forEach(error => {
      // Add fade-in animation
      error.style.animation = 'slideDown 0.3s ease-out';

      // Auto-scroll to first error on mobile
      if (window.innerWidth < 768 && document.activeElement !== document.body) {
        const firstError = document.querySelector('.form-error');
        if (firstError) {
          setTimeout(() => {
            firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }, 100);
        }
      }
    });
  }

  /**
   * Handle responsive behavior on window resize
   */
  function handleResponsiveResize() {
    let resizeTimeout;

    window.addEventListener('resize', () => {
      clearTimeout(resizeTimeout);
      resizeTimeout = setTimeout(() => {
        // Re-initialize sticky elements based on new screen size
        const stickyArea = document.querySelector('.form-actions-sticky');
        if (stickyArea) {
          if (window.innerWidth < 768) {
            stickyArea.style.position = 'sticky';
          } else {
            stickyArea.style.position = 'static';
          }
        }

        // Update font sizes for inputs
        enhanceFormInputs();
      }, 250);
    });
  }

  /**
   * Initialize all mobile form enhancements
   * Called when DOM is ready
   */
  function initializeMobileFormEnhancements() {
    // Only initialize on mobile/tablet
    if (window.innerWidth > 1280) {
      console.log('✓ Mobile form enhancements available but not active on desktop');
      return;
    }

    console.log('✓ Initializing mobile form enhancements');

    // Initialize each component
    initializeCollapsibleSections();
    initializeFloatingActionButton();
    initializeStickyActions();
    initializeTableResponsiveness();
    enhanceFormInputs();
    initializeKeyboardHandling();
    initializeStickyHeaders();
    initializeFormSubmission();
    initializeValidationFeedback();
    handleResponsiveResize();

    console.log('✓ Mobile form enhancements initialized');
  }

  /**
   * Wait for DOM to be ready, then initialize
   */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeMobileFormEnhancements);
  } else {
    initializeMobileFormEnhancements();
  }

  // Export for global access if needed
  window.MobileFormEnhancements = {
    debounce,
    initializeCollapsibleSections,
    initializeFloatingActionButton,
  };
})();

/**
 * Table Card Transformation Utility
 * Converts desktop tables to mobile-friendly card layouts with JavaScript
 */
(function() {
  'use strict';

  function transformTableToCards() {
    const tables = document.querySelectorAll('.table-responsive-cards');

    tables.forEach(table => {
      // Only transform on mobile
      if (window.innerWidth >= 768) return;

      const headers = Array.from(table.querySelectorAll('thead th'))
        .map(h => h.textContent.trim());
      const rows = table.querySelectorAll('tbody tr');

      rows.forEach((row, index) => {
        const cells = row.querySelectorAll('td');

        cells.forEach((cell, cellIndex) => {
          // Set data-label if not already set
          if (!cell.hasAttribute('data-label') && headers[cellIndex]) {
            cell.setAttribute('data-label', headers[cellIndex]);
          }
        });
      });
    });
  }

  // Run on load and resize
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', transformTableToCards);
  } else {
    transformTableToCards();
  }

  window.addEventListener('resize', function() {
    if (window.innerWidth < 768) {
      transformTableToCards();
    }
  });
})();

/**
 * Touch Enhancement Utility
 * Improves touch interactions on mobile devices
 */
(function() {
  'use strict';

  function enhanceTouchInteraction() {
    // Add touch feedback to buttons
    const buttons = document.querySelectorAll('button, a.btn, .btn');

    buttons.forEach(btn => {
      btn.addEventListener('touchstart', function() {
        this.style.opacity = '0.8';
      });

      btn.addEventListener('touchend', function() {
        this.style.opacity = '1';
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', enhanceTouchInteraction);
  } else {
    enhanceTouchInteraction();
  }
})();
