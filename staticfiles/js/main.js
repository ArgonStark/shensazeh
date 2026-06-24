/**
 * Sazandeh - Construction Tools & Materials Store
 * Main JavaScript
 */

(function () {
  'use strict';

  /* ==========================================================================
     CSRF Token Helper
     ========================================================================== */

  function getCsrfToken() {
    const cookie = document.cookie
      .split('; ')
      .find(row => row.startsWith('csrftoken='));
    if (cookie) return cookie.split('=')[1];

    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute('content');

    const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input) return input.value;

    return '';
  }

  /**
   * Make an AJAX fetch request with CSRF token included.
   * @param {string} url
   * @param {object} options - fetch options
   * @returns {Promise<Response>}
   */
  window.ajaxFetch = function (url, options = {}) {
    const defaults = {
      headers: {
        'X-CSRFToken': getCsrfToken(),
        'X-Requested-With': 'XMLHttpRequest',
        'Content-Type': 'application/json',
      },
      credentials: 'same-origin',
    };
    const merged = { ...defaults, ...options };
    if (options.headers) {
      merged.headers = { ...defaults.headers, ...options.headers };
    }
    return fetch(url, merged);
  };

  /* ==========================================================================
     OTP Input Handler
     ========================================================================== */

  window.initOtpInputs = function () {
    const digits = document.querySelectorAll('.otp-digit');
    const fullInput = document.getElementById('otpFull');
    if (!digits.length || !fullInput) return;

    function updateFullValue() {
      let val = '';
      digits.forEach(d => { val += d.value; });
      fullInput.value = val;
    }

    digits.forEach((input, idx) => {
      input.addEventListener('input', function () {
        this.value = this.value.replace(/\D/g, '').slice(0, 1);
        updateFullValue();
        if (this.value && idx < digits.length - 1) {
          digits[idx + 1].focus();
        }
      });

      input.addEventListener('keydown', function (e) {
        if (e.key === 'Backspace' && !this.value && idx > 0) {
          digits[idx - 1].focus();
          digits[idx - 1].value = '';
          updateFullValue();
        }
        if (e.key === 'ArrowRight' && idx > 0) {
          digits[idx - 1].focus();
        }
        if (e.key === 'ArrowLeft' && idx < digits.length - 1) {
          digits[idx + 1].focus();
        }
      });

      // Handle paste
      input.addEventListener('paste', function (e) {
        e.preventDefault();
        const pasted = (e.clipboardData || window.clipboardData).getData('text').replace(/\D/g, '');
        digits.forEach((d, i) => {
          d.value = pasted[i] || '';
        });
        updateFullValue();
        const nextEmpty = Array.from(digits).findIndex(d => !d.value);
        if (nextEmpty !== -1) digits[nextEmpty].focus();
        else digits[digits.length - 1].focus();
      });
    });
  };

  /* ==========================================================================
     OTP Countdown Timer
     ========================================================================== */

  window.startOtpCountdown = function (seconds) {
    const timerEl = document.getElementById('otpTimer');
    const countdownEl = document.getElementById('countdown');
    const resendForm = document.getElementById('resendForm');
    if (!timerEl || !countdownEl) return;

    let remaining = seconds;

    function update() {
      const min = Math.floor(remaining / 60);
      const sec = remaining % 60;
      countdownEl.textContent =
        String(min).padStart(2, '0') + ':' + String(sec).padStart(2, '0');

      if (remaining <= 0) {
        timerEl.classList.add('d-none');
        if (resendForm) resendForm.classList.remove('d-none');
        return;
      }
      remaining--;
      setTimeout(update, 1000);
    }

    update();
  };

  /* ==========================================================================
     Invoice Line Items
     ========================================================================== */

  window.initInvoiceForm = function () {
    const addBtn = document.getElementById('addLineItem');
    const tbody = document.getElementById('lineItemsBody');
    const totalFormsInput = document.getElementById('id_items-TOTAL_FORMS');
    if (!addBtn || !tbody || !totalFormsInput) return;

    function getRowCount() {
      return tbody.querySelectorAll('.line-item').length;
    }

    function formatNumber(num) {
      return new Intl.NumberFormat('fa-IR').format(num);
    }

    function recalculate() {
      let subtotal = 0;
      tbody.querySelectorAll('.line-item').forEach((row, idx) => {
        // Update row numbers
        const rowNum = row.querySelector('.row-number');
        if (rowNum) rowNum.textContent = (idx + 1).toString();

        const qty = parseFloat(row.querySelector('.item-quantity')?.value) || 0;
        const price = parseFloat(row.querySelector('.item-price')?.value) || 0;
        const lineTotal = qty * price;
        subtotal += lineTotal;

        const totalCell = row.querySelector('.item-total');
        if (totalCell) {
          totalCell.textContent = formatNumber(lineTotal) + ' تومان';
        }
      });

      const discountInput = document.getElementById('discountInput');
      const taxInput = document.getElementById('taxInput');
      const discount = parseFloat(discountInput?.value) || 0;
      const taxPercent = parseFloat(taxInput?.value) || 0;
      const afterDiscount = subtotal - discount;
      const taxAmount = Math.round(afterDiscount * taxPercent / 100);
      const grandTotal = afterDiscount + taxAmount;

      const subtotalDisplay = document.getElementById('subtotalDisplay');
      const discountDisplay = document.getElementById('discountDisplay');
      const taxDisplay = document.getElementById('taxDisplay');
      const grandTotalDisplay = document.getElementById('grandTotalDisplay');

      if (subtotalDisplay) subtotalDisplay.textContent = formatNumber(subtotal) + ' تومان';
      if (discountDisplay) discountDisplay.textContent = formatNumber(discount) + ' تومان';
      if (taxDisplay) taxDisplay.textContent = formatNumber(taxAmount) + ' تومان';
      if (grandTotalDisplay) grandTotalDisplay.textContent = formatNumber(grandTotal) + ' تومان';
    }

    // Add new line item
    addBtn.addEventListener('click', function () {
      const idx = getRowCount();
      const firstRow = tbody.querySelector('.line-item');
      if (!firstRow) return;

      const newRow = firstRow.cloneNode(true);
      newRow.setAttribute('data-row', idx);

      // Update name attributes
      newRow.querySelectorAll('[name]').forEach(input => {
        input.name = input.name.replace(/items-\d+-/, 'items-' + idx + '-');
        if (input.tagName === 'SELECT') input.selectedIndex = 0;
        else if (input.type === 'number') input.value = input.classList.contains('item-quantity') ? '1' : '0';
      });

      const totalCell = newRow.querySelector('.item-total');
      if (totalCell) totalCell.textContent = '۰ تومان';

      tbody.appendChild(newRow);
      totalFormsInput.value = getRowCount();
      recalculate();
    });

    // Remove line item
    tbody.addEventListener('click', function (e) {
      const removeBtn = e.target.closest('.remove-line-item');
      if (!removeBtn) return;

      if (getRowCount() <= 1) {
        alert('حداقل یک ردیف باید وجود داشته باشد.');
        return;
      }

      removeBtn.closest('.line-item').remove();
      totalFormsInput.value = getRowCount();
      recalculate();
    });

    // Recalculate on input change
    tbody.addEventListener('input', function (e) {
      if (e.target.classList.contains('item-quantity') || e.target.classList.contains('item-price')) {
        recalculate();
      }
    });

    // Auto-fill price when product selected
    tbody.addEventListener('change', function (e) {
      if (e.target.classList.contains('product-select')) {
        const selected = e.target.options[e.target.selectedIndex];
        const price = selected?.dataset.price || '0';
        const row = e.target.closest('.line-item');
        const priceInput = row?.querySelector('.item-price');
        if (priceInput) {
          priceInput.value = price;
          recalculate();
        }
      }
    });

    // Listen to discount & tax changes
    const discountInput = document.getElementById('discountInput');
    const taxInput = document.getElementById('taxInput');
    if (discountInput) discountInput.addEventListener('input', recalculate);
    if (taxInput) taxInput.addEventListener('input', recalculate);

    // Initial calculation
    recalculate();
  };

  /* ==========================================================================
     Image Gallery Interaction
     ========================================================================== */

  function initGallery() {
    // Thumbnail click -> update active border
    document.querySelectorAll('.gallery-thumb').forEach(thumb => {
      thumb.addEventListener('click', function () {
        const parent = this.closest('.card-body, .mb-5, .col-lg-5');
        if (parent) {
          parent.querySelectorAll('.gallery-thumb').forEach(t => {
            t.classList.remove('border', 'border-primary', 'border-2');
          });
        }
        this.classList.add('border', 'border-primary', 'border-2');
      });
    });

    // Modal image zoom
    document.querySelectorAll('[data-bs-target="#imageModal"], [data-bs-target="#galleryModal"]').forEach(trigger => {
      trigger.addEventListener('click', function () {
        const imgSrc = this.dataset.img || this.src;
        const zoomImg = document.getElementById('zoomImage') || document.getElementById('galleryZoomImage');
        if (zoomImg && imgSrc) {
          zoomImg.src = imgSrc;
        }
      });
    });
  }

  /* ==========================================================================
     Search Autocomplete Stub
     ========================================================================== */

  function initSearchAutocomplete() {
    const searchInput = document.getElementById('searchInput');
    const resultsDiv = document.getElementById('searchResults');
    if (!searchInput || !resultsDiv) return;

    let debounceTimer;

    searchInput.addEventListener('input', function () {
      const query = this.value.trim();

      clearTimeout(debounceTimer);

      if (query.length < 2) {
        resultsDiv.classList.add('d-none');
        resultsDiv.innerHTML = '';
        return;
      }

      debounceTimer = setTimeout(function () {
        // AJAX search request
        ajaxFetch('/api/search/?q=' + encodeURIComponent(query), {
          method: 'GET',
          headers: {
            'X-CSRFToken': getCsrfToken(),
            'X-Requested-With': 'XMLHttpRequest',
          },
        })
          .then(response => {
            if (!response.ok) throw new Error('Network error');
            return response.json();
          })
          .then(data => {
            resultsDiv.innerHTML = '';
            if (data.results && data.results.length > 0) {
              data.results.forEach(item => {
                const div = document.createElement('div');
                div.className = 'search-item d-flex align-items-center gap-2 p-2 border-bottom';
                div.innerHTML =
                  (item.image ? '<img src="' + item.image + '" class="rounded" style="width:40px;height:40px;object-fit:cover;">' : '') +
                  '<div>' +
                  '<div class="fw-bold small">' + item.name + '</div>' +
                  (item.price ? '<small class="text-primary">' + item.price + ' تومان</small>' : '') +
                  '</div>';
                div.addEventListener('click', function () {
                  window.location.href = item.url;
                });
                resultsDiv.appendChild(div);
              });
              resultsDiv.classList.remove('d-none');
            } else {
              resultsDiv.innerHTML = '<div class="p-3 text-center text-muted small">نتیجه‌ای یافت نشد.</div>';
              resultsDiv.classList.remove('d-none');
            }
          })
          .catch(function () {
            // Silently fail for autocomplete
            resultsDiv.classList.add('d-none');
          });
      }, 300);
    });

    // Close results when clicking outside
    document.addEventListener('click', function (e) {
      if (!searchInput.contains(e.target) && !resultsDiv.contains(e.target)) {
        resultsDiv.classList.add('d-none');
      }
    });

    // Close on Escape
    searchInput.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        resultsDiv.classList.add('d-none');
      }
    });
  }

  /* ==========================================================================
     Auto-dismiss alerts
     ========================================================================== */

  function initAutoDismissAlerts() {
    document.querySelectorAll('.alert-dismissible').forEach(alert => {
      setTimeout(() => {
        const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
        if (bsAlert) bsAlert.close();
      }, 5000);
    });
  }

  /* ==========================================================================
     Initialize on DOM Ready
     ========================================================================== */

  document.addEventListener('DOMContentLoaded', function () {
    initGallery();
    initSearchAutocomplete();
    initAutoDismissAlerts();

    // Initialize OTP if on OTP page
    if (document.querySelector('.otp-digit')) {
      initOtpInputs();
    }
  });

})();
