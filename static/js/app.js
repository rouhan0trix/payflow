/**
 * PayFlow — Core Application JavaScript
 * Clean vanilla JS: modal controls, toast notifications, paise converter,
 * idempotency demo helpers, and global refund handler.
 */

// State memory for idempotency testing shortcuts
let lastSubmittedPayload = null;

document.addEventListener('DOMContentLoaded', () => {
  initModalEvents();
  initAmountConverter();
  initIdempotencyHelpers();
  initPaymentForm();
});

/* ==========================================================================
   Toast Notification System
   ========================================================================== */
function showToast(message, type = 'info', duration = 4000) {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.setAttribute('role', 'alert');

  let icon = 'ℹ️';
  if (type === 'success') icon = '✅';
  if (type === 'error') icon = '❌';
  if (type === 'warning') icon = '⚠️';

  toast.innerHTML = `
    <span class="toast-icon">${icon}</span>
    <span class="toast-msg">${escapeHtml(message)}</span>
  `;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.25s ease';
    setTimeout(() => toast.remove(), 250);
  }, duration);
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function copyToClipboard(text, successMsg = 'Copied to clipboard!') {
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => showToast(successMsg, 'success'));
  } else {
    const input = document.createElement('textarea');
    input.value = text;
    document.body.appendChild(input);
    input.select();
    document.execCommand('copy');
    input.remove();
    showToast(successMsg, 'success');
  }
}

/* ==========================================================================
   Modal Dialog Controls
   ========================================================================== */
function openCreateModal() {
  const modal = document.getElementById('createPaymentModal');
  if (!modal) return;

  // Auto-generate fresh idempotency key if empty
  const keyInput = document.getElementById('modalIdempotencyKey');
  if (keyInput && !keyInput.value) {
    keyInput.value = generateRandomKey();
  }

  // Reset result box
  const resultArea = document.getElementById('modalResultArea');
  if (resultArea) resultArea.style.display = 'none';

  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';

  // Focus first input
  const amountInput = document.getElementById('modalAmountINR');
  if (amountInput) amountInput.focus();
}

function closeCreateModal() {
  const modal = document.getElementById('createPaymentModal');
  if (!modal) return;
  modal.style.display = 'none';
  document.body.style.overflow = '';
}

function initModalEvents() {
  const openBtn = document.getElementById('openCreateModalBtn');
  const closeBtn = document.getElementById('closeCreateModalBtn');
  const cancelBtn = document.getElementById('modalCancelBtn');
  const modal = document.getElementById('createPaymentModal');

  if (openBtn) openBtn.addEventListener('click', openCreateModal);
  if (closeBtn) closeBtn.addEventListener('click', closeCreateModal);
  if (cancelBtn) cancelBtn.addEventListener('click', closeCreateModal);

  // Close when clicking on backdrop outside card
  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeCreateModal();
    });
  }

  // Close on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modal && modal.style.display !== 'none') {
      closeCreateModal();
    }
  });
}

/* ==========================================================================
   Live Paise Conversion Helper
   ========================================================================== */
function initAmountConverter() {
  const amountInput = document.getElementById('modalAmountINR');
  const paiseDisplay = document.getElementById('calculatedPaise');

  if (!amountInput || !paiseDisplay) return;

  function updatePaise() {
    const val = parseFloat(amountInput.value);
    if (isNaN(val) || val <= 0) {
      paiseDisplay.textContent = '0';
      return;
    }
    const paise = Math.round(val * 100);
    paiseDisplay.textContent = paise.toLocaleString('en-IN');
  }

  amountInput.addEventListener('input', updatePaise);
  updatePaise();
}

/* ==========================================================================
   Idempotency Helpers & Demo Shortcuts
   ========================================================================== */
function generateRandomKey() {
  const rand = Math.random().toString(36).substring(2, 10);
  const now = Date.now().toString().slice(-4);
  return `order-${now}-${rand}`;
}

function initIdempotencyHelpers() {
  const regenBtn = document.getElementById('regenerateKeyBtn');
  const keyInput = document.getElementById('modalIdempotencyKey');
  const replayBtn = document.getElementById('demoReplayBtn');
  const tamperBtn = document.getElementById('demoTamperBtn');

  if (regenBtn && keyInput) {
    regenBtn.addEventListener('click', () => {
      keyInput.value = generateRandomKey();
      showToast('Generated new unique idempotency key', 'info');
    });
  }

  if (replayBtn) {
    replayBtn.addEventListener('click', () => {
      if (!lastSubmittedPayload) {
        showToast('Submit at least one payment first to test replay!', 'warning');
        return;
      }
      document.getElementById('modalAmountINR').value = (lastSubmittedPayload.amount_paise / 100).toFixed(2);
      document.getElementById('modalDescription').value = lastSubmittedPayload.description;
      document.getElementById('modalIdempotencyKey').value = lastSubmittedPayload.idempotency_key;
      document.getElementById('modalSimulateStatus').value = lastSubmittedPayload.simulate_status || 'succeeded';

      // Trigger paise recalculation
      const paiseDisplay = document.getElementById('calculatedPaise');
      if (paiseDisplay) paiseDisplay.textContent = lastSubmittedPayload.amount_paise.toLocaleString('en-IN');

      showToast('Loaded last request payload. Click Process to test 200 Replay!', 'info');
    });
  }

  if (tamperBtn) {
    tamperBtn.addEventListener('click', () => {
      if (!lastSubmittedPayload) {
        showToast('Submit at least one payment first to test tampering!', 'warning');
        return;
      }
      // Keep key, but tamper amount
      const alteredRupees = ((lastSubmittedPayload.amount_paise / 100) + 150).toFixed(2);
      document.getElementById('modalAmountINR').value = alteredRupees;
      document.getElementById('modalDescription').value = lastSubmittedPayload.description;
      document.getElementById('modalIdempotencyKey').value = lastSubmittedPayload.idempotency_key;

      const paiseDisplay = document.getElementById('calculatedPaise');
      if (paiseDisplay) paiseDisplay.textContent = Math.round(alteredRupees * 100).toLocaleString('en-IN');

      showToast('Tampered amount with SAME idempotency key. Click Process to see 409 Conflict!', 'warning');
    });
  }
}

/* ==========================================================================
   Payment Creation Form Handling
   ========================================================================== */
function initPaymentForm() {
  const form = document.getElementById('createPaymentForm');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const amountRupees = parseFloat(document.getElementById('modalAmountINR').value);
    const description = document.getElementById('modalDescription').value.trim();
    const idempotencyKey = document.getElementById('modalIdempotencyKey').value.trim();
    const simulateStatus = document.getElementById('modalSimulateStatus').value;
    const submitBtn = document.getElementById('modalSubmitBtn');
    const resultArea = document.getElementById('modalResultArea');
    const resultStatus = document.getElementById('modalResultStatus');
    const resultNotice = document.getElementById('modalResultNotice');
    const resultJson = document.getElementById('modalResultJson');

    if (isNaN(amountRupees) || amountRupees <= 0) {
      showToast('Please enter a valid amount greater than 0', 'error');
      return;
    }
    if (!description) {
      showToast('Description is required', 'error');
      return;
    }
    if (!idempotencyKey) {
      showToast('Idempotency key is required', 'error');
      return;
    }

    const amountPaise = Math.round(amountRupees * 100);

    const payload = {
      amount_paise: amountPaise,
      currency: 'INR',
      description: description,
      idempotency_key: idempotencyKey,
      simulate_status: simulateStatus
    };

    submitBtn.disabled = true;
    submitBtn.classList.add('disabled');

    try {
      const response = await fetch('/api/payments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await response.json();

      // Show result drawer inside modal
      resultArea.style.display = 'flex';
      resultJson.textContent = JSON.stringify(data, null, 2);

      if (response.status === 201) {
        resultStatus.className = 'result-badge created';
        resultStatus.textContent = 'HTTP 201 Created';
        resultNotice.textContent = `New payment created with status '${data.status}'.`;
        showToast(`Payment ${data.id} created successfully!`, 'success');
        lastSubmittedPayload = { ...payload };

        // Generate next key ready for next time
        setTimeout(() => {
          document.getElementById('modalIdempotencyKey').value = generateRandomKey();
        }, 1500);

      } else if (response.status === 200 && data.is_replay) {
        resultStatus.className = 'result-badge replay';
        resultStatus.textContent = 'HTTP 200 Replay (Idempotent)';
        resultNotice.textContent = 'Identical idempotency key recognized. Returned existing payment record.';
        showToast(`Idempotency Replay: Returned existing ${data.id} without duplicating!`, 'info');

      } else if (response.status === 409) {
        resultStatus.className = 'result-badge conflict';
        resultStatus.textContent = 'HTTP 409 Conflict';
        resultNotice.textContent = data.error || 'Idempotency key conflict: payload modified.';
        showToast('HTTP 409 Conflict: Same key reused with different request payload!', 'error');

      } else {
        resultStatus.className = 'result-badge error';
        resultStatus.textContent = `HTTP ${response.status} Error`;
        resultNotice.textContent = data.error || 'Validation error.';
        showToast(data.error || 'Payment failed', 'error');
      }

      // If user is on dashboard or transactions page, refresh table dynamically
      if (typeof refreshDashboardMetrics === 'function') {
        refreshDashboardMetrics();
      }

    } catch (err) {
      showToast('Network error while processing payment: ' + err.message, 'error');
    } finally {
      submitBtn.disabled = false;
      submitBtn.classList.remove('disabled');
    }
  });
}

/* ==========================================================================
   Global Refund Execution Handler
   ========================================================================== */
async function triggerRefund(paymentId, redirectOnSuccess = false) {
  if (!confirm(`Are you sure you want to issue a full simulated refund for payment '${paymentId}'?\n\nThis will trigger an atomic database transaction.`)) {
    return;
  }

  showToast(`Processing simulated refund for ${paymentId}...`, 'info');

  try {
    const res = await fetch(`/api/payments/${encodeURIComponent(paymentId)}/refund`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });

    const data = await res.json();

    if (res.ok) {
      showToast(`Refund issued successfully! (Refund ID: ${data.payment.refund.id})`, 'success');
      setTimeout(() => {
        window.location.reload();
      }, 700);
    } else {
      showToast(`Refund rejected (HTTP ${res.status}): ${data.error}`, 'error');
    }
  } catch (err) {
    showToast('Failed to process refund: ' + err.message, 'error');
  }
}
