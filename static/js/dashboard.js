/**
 * PayFlow — Dashboard Dynamic Controller
 * Handles metric auto-refresh, quick simulation presets, and live table updates.
 */

document.addEventListener('DOMContentLoaded', () => {
  const refreshBtn = document.getElementById('refreshMetricsBtn');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', async () => {
      refreshBtn.disabled = true;
      refreshBtn.classList.add('disabled');
      await refreshDashboardMetrics();
      showToast('Dashboard metrics refreshed from database', 'info');
      refreshBtn.disabled = false;
      refreshBtn.classList.remove('disabled');
    });
  }
});

/**
 * Runs a quick preset payment simulation
 */
async function runPresetPayment(amountRupees, description, status) {
  openCreateModal();
  document.getElementById('modalAmountINR').value = amountRupees.toFixed(2);
  document.getElementById('modalDescription').value = description;
  document.getElementById('modalSimulateStatus').value = status;
  document.getElementById('modalIdempotencyKey').value = generateRandomKey();

  const paiseDisplay = document.getElementById('calculatedPaise');
  if (paiseDisplay) {
    paiseDisplay.textContent = Math.round(amountRupees * 100).toLocaleString('en-IN');
  }

  showToast(`Loaded preset '${description}'. Submitting payment...`, 'info');

  // Trigger form submit
  const form = document.getElementById('createPaymentForm');
  if (form) {
    form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
  }
}

/**
 * Fetches fresh metrics from /api/dashboard and updates the UI in place
 */
async function refreshDashboardMetrics() {
  try {
    const res = await fetch('/api/dashboard');
    if (!res.ok) return;

    const data = await res.json();

    // Update KPIs
    const elGrossVol = document.getElementById('metricGrossVolume');
    const elGrossPaise = document.getElementById('metricGrossPaise');
    const elTotal = document.getElementById('metricTotalPayments');
    const elSuccCount = document.getElementById('metricSucceededCount');
    const elSuccAmt = document.getElementById('metricSucceededAmount');
    const elRefCount = document.getElementById('metricRefundedCount');
    const elRefAmt = document.getElementById('metricRefundedAmount');
    const elFailCount = document.getElementById('metricFailedCount');

    if (elGrossVol) elGrossVol.textContent = '₹' + data.formatted.succeeded_inr;
    if (elGrossPaise) elGrossPaise.textContent = data.amounts_paise.succeeded.toLocaleString('en-IN') + ' paise';
    if (elTotal) elTotal.textContent = data.total_payments;
    if (elSuccCount) elSuccCount.textContent = data.counts.succeeded;
    if (elSuccAmt) elSuccAmt.textContent = '₹' + data.formatted.succeeded_inr;
    if (elRefCount) elRefCount.textContent = data.counts.refunded;
    if (elRefAmt) elRefAmt.textContent = '₹' + data.formatted.refunded_inr;
    if (elFailCount) elFailCount.textContent = data.counts.failed;

    // Update Recent Transactions Table Body
    const tbody = document.getElementById('recentTableBody');
    if (tbody && data.recent_transactions && data.recent_transactions.length > 0) {
      tbody.innerHTML = '';
      data.recent_transactions.forEach(t => {
        const tr = document.createElement('tr');
        tr.setAttribute('data-id', t.id);

        let refundBtn = '';
        if (t.status === 'succeeded') {
          refundBtn = `<button type="button" class="btn-table-action refund" onclick="triggerRefund('${t.id}')">Refund</button>`;
        }

        const dateStr = t.created_at ? t.created_at.substring(0, 19).replace('T', ' ') : '';

        tr.innerHTML = `
          <td><a href="/transactions/${t.id}" class="mono-link">${t.id}</a></td>
          <td><span class="table-desc">${escapeHtml(t.description)}</span></td>
          <td><strong class="font-tabular">₹${t.formatted_amount_inr}</strong></td>
          <td><span class="mono-text">${t.amount_paise.toLocaleString('en-IN')}</span></td>
          <td>
            <span class="status-pill ${t.status}">
              <span class="status-dot"></span>
              ${t.status.charAt(0).toUpperCase() + t.status.slice(1)}
            </span>
          </td>
          <td><span class="time-text">${dateStr}</span></td>
          <td>
            <div class="action-buttons">
              <a href="/transactions/${t.id}" class="btn-table-action">Details</a>
              ${refundBtn}
            </div>
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

  } catch (err) {
    console.warn('Could not auto-refresh metrics:', err);
  }
}
