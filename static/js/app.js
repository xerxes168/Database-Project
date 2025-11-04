// static/js/app.js

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

let trendChart = null;

// ========== API HELPERS ==========
async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

async function postJSON(url, data) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data || {}),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

async function deleteJSON(url) {
  const r = await fetch(url, { method: "DELETE" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

// ========== UI HELPERS ==========
function showLoading(el, text = "Loading...") {
  el.classList.remove("hidden");
  el.innerHTML = `
    <div class="flex items-center space-x-2">
      <div class="spinner"></div>
      <span>${text}</span>
    </div>
  `;
}

function hideLoading(el) {
  el.classList.add("hidden");
}

function showError(el, message) {
  el.innerHTML = `
    <div class="p-4 bg-red-900/20 border border-red-500/50 rounded-lg text-red-400 text-sm">
      <strong>Error:</strong> ${message}
    </div>
  `;
}

function renderTable(el, rows) {
  if (!rows || !rows.length) {
    el.innerHTML = `<p class="text-sm text-zinc-400 text-center py-8">No results found.</p>`;
    return;
  }
  
  const cols = Object.keys(rows[0]);
  el.innerHTML = `
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="text-left text-zinc-300 border-b-2 border-zinc-700 bg-zinc-800/50">
          <tr>${cols.map(c => `<th class="py-3 px-4 font-semibold">${c.replace(/_/g, ' ').toUpperCase()}</th>`).join("")}</tr>
        </thead>
        <tbody class="divide-y divide-zinc-800">
          ${rows.map(r => `
            <tr class="hover:bg-zinc-800/40 transition">
              ${cols.map(c => {
                let val = r[c];
                if (typeof val === 'number') {
                  if (c.includes('price') || c.includes('psm')) {
                    val = '$' + val.toLocaleString();
                  } else {
                    val = val.toLocaleString();
                  }
                }
                return `<td class="py-3 px-4 text-zinc-300">${val}</td>`;
              }).join("")}
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

// ========== TAB SYSTEM ==========
function useTabs() {
  const tabs = $$(".ui-tab");
  const panels = $$(".ui-panel");
  
  tabs.forEach(btn => {
    btn.addEventListener("click", () => {
      tabs.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const id = btn.dataset.tab;
      panels.forEach(p => p.classList.add("hidden"));
      const panel = $(`#panel-${id}`);
      if (panel) {
        panel.classList.remove("hidden");
        panel.classList.add("animate-fade-in");
      }
    });
  });
}

// ========== CHART RENDERING ==========
function renderTrendChart(data) {
  const ctx = $("#trend-chart");
  if (!ctx) return;
  
  if (trendChart) {
    trendChart.destroy();
  }
  
  const labels = data.map(d => d.month);
  const medianData = data.map(d => d.median_psm);
  const avgData = data.map(d => d.avg_psm);
  
  trendChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Median $/sqm',
          data: medianData,
          borderColor: 'rgb(16, 185, 129)',
          backgroundColor: 'rgba(16, 185, 129, 0.1)',
          tension: 0.4,
          fill: true,
          pointRadius: 4,
          pointHoverRadius: 6,
        },
        {
          label: 'Average $/sqm',
          data: avgData,
          borderColor: 'rgb(59, 130, 246)',
          backgroundColor: 'rgba(59, 130, 246, 0.1)',
          tension: 0.4,
          fill: true,
          pointRadius: 4,
          pointHoverRadius: 6,
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false,
      },
      plugins: {
        legend: {
          display: true,
          position: 'top',
          labels: {
            color: '#a1a1aa',
            usePointStyle: true,
            padding: 15,
          }
        },
        tooltip: {
          backgroundColor: 'rgba(24, 24, 27, 0.95)',
          titleColor: '#fafafa',
          bodyColor: '#d4d4d8',
          borderColor: '#3f3f46',
          borderWidth: 1,
          padding: 12,
          displayColors: true,
          callbacks: {
            label: function(context) {
              let label = context.dataset.label || '';
              if (label) {
                label += ': ';
              }
              if (context.parsed.y !== null) {
                label += '$' + context.parsed.y.toLocaleString();
              }
              return label;
            }
          }
        }
      },
      scales: {
        x: {
          grid: {
            color: 'rgba(63, 63, 70, 0.3)',
            drawBorder: false,
          },
          ticks: {
            color: '#a1a1aa',
          }
        },
        y: {
          grid: {
            color: 'rgba(63, 63, 70, 0.3)',
            drawBorder: false,
          },
          ticks: {
            color: '#a1a1aa',
            callback: function(value) {
              return '$' + value.toLocaleString();
            }
          }
        }
      }
    }
  });
}

// ========== PANEL 1: EXPLORE TRENDS ==========
async function setupTrendsPanel() {
  $("#btn-search").addEventListener("click", async () => {
    const trendState = $("#trend-state");
    const trendTable = $("#trend-table");
    const trendLoading = $("#trend-loading");
    
    showLoading(trendState, "Running SQL query with window functions...");
    trendLoading.classList.remove("hidden");
    
    try {
      const res = await postJSON("/api/search/trends", {
        town: $("#sel-town").value,
        flat_type: $("#sel-flat").value,
        start_month: $("#sel-start").value,
        end_month: $("#sel-end").value
      });
      
      if (res.ok && res.rows) {
        renderTrendChart(res.rows);
        renderTable(trendTable, res.rows);
      } else {
        showError(trendTable, "No data returned");
      }
    } catch (err) {
      showError(trendTable, err.message);
    } finally {
      hideLoading(trendState);
      trendLoading.classList.add("hidden");
    }
  });
}

// ========== PANEL 2: TRANSACTIONS ==========
async function setupTransactionsPanel() {
  $("#btn-search-trans").addEventListener("click", async () => {
    const transList = $("#trans-list");
    const transCount = $("#trans-count");
    const transLoading = $("#trans-loading");
    
    showLoading(transLoading, "Loading transactions...");
    
    try {
      const res = await postJSON("/api/search/transactions", {
        town: $("#trans-town").value,
        flat_type: $("#trans-flat").value,
        limit: parseInt($("#trans-limit").value)
      });
      
      if (res.ok && res.transactions) {
        transCount.textContent = `${res.count} results`;
        
        transList.innerHTML = res.transactions.map(t => `
          <div class="p-4 bg-zinc-800/50 rounded-lg border border-zinc-700 hover:border-emerald-500/50 transition">
            <div class="flex items-start justify-between mb-2">
              <div>
                <div class="font-semibold text-zinc-200">Block ${t.block}, ${t.street}</div>
                <div class="text-xs text-zinc-400 mt-1">${t.storey} • ${t.floor_area} sqm • ${t.remaining_lease}</div>
              </div>
              <div class="text-right">
                <div class="text-lg font-bold text-emerald-400">$${t.price.toLocaleString()}</div>
                <div class="text-xs text-zinc-400">$${t.psm.toLocaleString()}/sqm</div>
              </div>
            </div>
            <div class="flex items-center justify-between text-xs text-zinc-500">
              <span>Lease from ${t.lease_start}</span>
              <span>${t.month}</span>
            </div>
          </div>
        `).join("");
      } else {
        transList.innerHTML = `<p class="text-center text-zinc-400 py-8">No transactions found</p>`;
      }
    } catch (err) {
      showError(transList, err.message);
    } finally {
      hideLoading(transLoading);
    }
  });
}

// ========== PANEL 3: AFFORDABILITY ==========
async function setupAffordabilityPanel() {
  $("#btn-afford").addEventListener("click", async () => {
    const afResult = $("#af-result");
    
    afResult.innerHTML = `
      <div class="flex items-center justify-center py-8">
        <div class="spinner"></div>
      </div>
    `;
    
    try {
      const payload = {
        income: parseFloat($("#af-income").value) || 0,
        expenses: parseFloat($("#af-expenses").value) || 0,
        interest: parseFloat($("#af-interest").value) || 2.6,
        tenure_years: parseInt($("#af-tenure").value) || 25,
        down_payment_pct: parseFloat($("#af-downpayment").value) || 20,
      };
      
      const res = await postJSON("/api/affordability", payload);
      
      if (!res.ok) {
        showError(afResult, "Calculation failed");
        return;
      }
      
      const statusColor = res.affordable ? 'emerald' : 'red';
      const statusIcon = res.affordable ? 
        `<svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
        </svg>` :
        `<svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
        </svg>`;
      
      afResult.innerHTML = `
        <div class="space-y-4">
          <div class="flex items-center space-x-3 p-4 bg-${statusColor}-900/20 border border-${statusColor}-500/50 rounded-lg">
            <div class="text-${statusColor}-400">${statusIcon}</div>
            <div>
              <div class="font-semibold text-lg text-${statusColor}-400">
                ${res.affordable ? 'Affordable!' : 'May Be Challenging'}
              </div>
              <div class="text-sm text-zinc-400">Based on 30% income threshold</div>
            </div>
          </div>
          
          <div class="grid grid-cols-2 gap-4">
            <div class="p-4 bg-zinc-800 rounded-lg border border-zinc-700">
              <div class="text-xs text-zinc-400 mb-1">Max Property Value</div>
              <div class="text-2xl font-bold text-emerald-400">$${res.max_property_value.toLocaleString()}</div>
            </div>
            
            <div class="p-4 bg-zinc-800 rounded-lg border border-zinc-700">
              <div class="text-xs text-zinc-400 mb-1">Max Loan Amount</div>
              <div class="text-2xl font-bold text-blue-400">$${res.max_loan_amount.toLocaleString()}</div>
            </div>
            
            <div class="p-4 bg-zinc-800 rounded-lg border border-zinc-700">
              <div class="text-xs text-zinc-400 mb-1">Max Monthly Payment</div>
              <div class="text-xl font-bold text-zinc-200">$${res.max_monthly_payment.toLocaleString()}</div>
            </div>
            
            <div class="p-4 bg-zinc-800 rounded-lg border border-zinc-700">
              <div class="text-xs text-zinc-400 mb-1">Max Price per sqm</div>
              <div class="text-xl font-bold text-zinc-200">$${res.max_psm.toLocaleString()}</div>
            </div>
          </div>
          
          <div class="p-4 bg-zinc-800/50 rounded-lg border border-zinc-700/50">
            <div class="text-xs text-zinc-400 mb-2">Calculation Details</div>
            <div class="text-sm text-zinc-300 space-y-1">
              <p>• Down payment required: <span class="font-semibold text-emerald-400">$${res.down_payment_required.toLocaleString()}</span></p>
              <p>• Interest rate: ${payload.interest}% over ${payload.tenure_years} years</p>
              <p>• Based on ${payload.down_payment_pct}% down payment</p>
            </div>
          </div>
        </div>
      `;
    } catch (err) {
      showError(afResult, err.message);
    }
  });
  
  // Save scenario
  $("#btn-save-scenario").addEventListener("click", async () => {
    const name = $("#sc-name").value.trim();
    if (!name) {
      alert("Please enter a scenario name");
      return;
    }
    
    try {
      const item = {
        name: name,
        income: parseFloat($("#af-income").value) || 0,
        expenses: parseFloat($("#af-expenses").value) || 0,
        interest: parseFloat($("#af-interest").value) || 2.6,
        tenure_years: parseInt($("#af-tenure").value) || 25,
      };
      
      const res = await postJSON("/api/scenarios", item);
      if (res.ok) {
        $("#sc-name").value = "";
        await refreshScenarios();
        alert("Scenario saved to MongoDB!");
      }
    } catch (err) {
      alert("Error saving scenario: " + err.message);
    }
  });
  
  $("#btn-refresh-scenarios").addEventListener("click", refreshScenarios);
  await refreshScenarios();
}

async function refreshScenarios() {
  const list = $("#sc-list");
  
  try {
    const res = await getJSON("/api/scenarios");
    
    if (!res.ok || !res.items || res.items.length === 0) {
      list.innerHTML = `<p class="text-sm text-zinc-400 text-center py-4">No saved scenarios yet</p>`;
      return;
    }
    
    list.innerHTML = res.items.map(it => `
      <div class="flex items-center justify-between p-3 bg-zinc-800 rounded-lg border border-zinc-700 hover:border-emerald-500/50 transition">
        <div class="flex-1">
          <div class="font-medium text-sm text-zinc-200">${it.name}</div>
          <div class="text-xs text-zinc-400 mt-1">
            Income: $${it.income.toLocaleString()} • 
            Expenses: $${it.expenses.toLocaleString()} • 
            ${it.interest}% • 
            ${it.tenure_years}y
          </div>
        </div>
        <button class="ml-3 px-3 py-1.5 text-xs bg-red-600 hover:bg-red-500 rounded transition" data-del="${it._id}">
          Delete
        </button>
      </div>
    `).join("");
    
    list.querySelectorAll("[data-del]").forEach(btn => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-del");
        if (confirm("Delete this scenario?")) {
          try {
            await deleteJSON(`/api/scenarios?id=${encodeURIComponent(id)}`);
            await refreshScenarios();
          } catch (err) {
            alert("Error deleting: " + err.message);
          }
        }
      });
    });
  } catch (err) {
    showError(list, err.message);
  }
}

// ========== PANEL 4: TOWN COMPARISON ==========
async function setupComparePanel() {
  $("#btn-compare").addEventListener("click", async () => {
    const results = $("#compare-results");
    
    results.innerHTML = `
      <div class="col-span-3 flex items-center justify-center py-12">
        <div class="spinner"></div>
      </div>
    `;
    
    try {
      const towns = [
        $("#comp-town1").value,
        $("#comp-town2").value,
        $("#comp-town3").value
      ].filter(t => t);
      
      const res = await postJSON("/api/compare/towns", {
        towns: towns,
        flat_type: $("#sel-flat").value
      });
      
      if (res.ok && res.comparison) {
        results.innerHTML = res.comparison.map(town => `
          <div class="p-6 bg-zinc-900 rounded-xl border border-zinc-800 card-hover">
            <h3 class="text-xl font-bold mb-4 text-emerald-400">${town.town}</h3>
            
            <div class="space-y-3">
              <div class="flex justify-between items-center">
                <span class="text-sm text-zinc-400">Median $/sqm</span>
                <span class="font-bold text-lg">$${town.median_psm.toLocaleString()}</span>
              </div>
              
              <div class="flex justify-between items-center">
                <span class="text-sm text-zinc-400">Avg Price</span>
                <span class="font-semibold">$${town.avg_price.toLocaleString()}</span>
              </div>
              
              <div class="flex justify-between items-center">
                <span class="text-sm text-zinc-400">Transactions</span>
                <span class="font-semibold">${town.transactions}</span>
              </div>
              
              <div class="pt-3 border-t border-zinc-800">
                <div class="text-xs text-zinc-400 mb-2">Amenities</div>
                <div class="grid grid-cols-2 gap-2 text-sm">
                  <div>MRT: <span class="font-semibold">${town.mrt_count}</span></div>
                  <div>Schools: <span class="font-semibold">${town.school_count}</span></div>
                </div>
              </div>
              
              <div class="pt-3 border-t border-zinc-800">
                <div class="text-xs text-zinc-400 mb-1">Affordability Score</div>
                <div class="flex items-center space-x-2">
                  <div class="flex-1 h-2 bg-zinc-800 rounded-full overflow-hidden">
                    <div class="h-full bg-gradient-to-r from-emerald-600 to-emerald-400 rounded-full" 
                         style="width: ${town.affordability_score * 10}%"></div>
                  </div>
                  <span class="font-bold text-emerald-400">${town.affordability_score}/10</span>
                </div>
              </div>
            </div>
          </div>
        `).join("");
      } else {
        results.innerHTML = `<p class="col-span-3 text-center text-zinc-400 py-8">No comparison data available</p>`;
      }
    } catch (err) {
      results.innerHTML = `<div class="col-span-3 p-4 bg-red-900/20 border border-red-500/50 rounded-lg text-red-400">${err.message}</div>`;
    }
  });
}

// ========== PANEL 5: AMENITIES ==========
async function setupAmenitiesPanel() {
  const amenityFile = $("#amenity-file");
  const amenitySelected = $("#amenity-selected");
  const amenityFilename = $("#amenity-filename");
  
  amenityFile.addEventListener("change", (e) => {
    if (e.target.files.length > 0) {
      amenitySelected.classList.remove("hidden");
      amenityFilename.textContent = `Selected: ${e.target.files[0].name}`;
    }
  });
  
  $("#amenity-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const file = amenityFile.files[0];
    
    if (!file) {
      alert("Please select a file");
      return;
    }
    
    const amenityState = $("#amenity-state");
    amenityState.innerHTML = `
      <div class="flex items-center space-x-2 text-zinc-400">
        <div class="spinner"></div>
        <span>Uploading to MongoDB...</span>
      </div>
    `;
    
    try {
      const fd = new FormData();
      fd.append("file", file);
      
      const r = await fetch("/api/amenities/upload", { method: "POST", body: fd });
      const j = await r.json();
      
      if (j.ok) {
        amenityState.innerHTML = `
          <div class="p-3 bg-emerald-900/20 border border-emerald-500/50 rounded-lg text-emerald-400 text-sm">
            <strong>Success!</strong> Uploaded ${j.filename} with ${j.feature_count} features (${j.upserted} new, ${j.modified} updated)
          </div>
        `;
        amenityFile.value = "";
        amenitySelected.classList.add("hidden");
      } else {
        amenityState.innerHTML = `
          <div class="p-3 bg-red-900/20 border border-red-500/50 rounded-lg text-red-400 text-sm">
            <strong>Error:</strong> ${j.error || "Upload failed"}
          </div>
        `;
      }
    } catch (err) {
      showError(amenityState, err.message);
    }
  });
  
  $("#btn-amenity-stats").addEventListener("click", async () => {
    const statsDiv = $("#amenity-stats");
    const town = $("#amenity-town").value;
    
    statsDiv.innerHTML = `
      <div class="col-span-2 flex items-center justify-center py-8">
        <div class="spinner"></div>
      </div>
    `;
    
    try {
      const res = await getJSON(`/api/amenities/stats?town=${encodeURIComponent(town)}`);
      
      if (res.ok && res.stats) {
        const stats = res.stats;
        statsDiv.innerHTML = `
          ${Object.entries(stats).filter(([k]) => k !== 'town').map(([key, val]) => `
            <div class="p-4 bg-zinc-800 rounded-lg border border-zinc-700">
              <div class="text-xs text-zinc-400 mb-1">${key.replace(/_/g, ' ').toUpperCase()}</div>
              <div class="text-2xl font-bold text-emerald-400">${val}</div>
            </div>
          `).join('')}
        `;
      }
    } catch (err) {
      showError(statsDiv, err.message);
    }
  });
}

// ========== BOOTSTRAP ==========
async function bootstrap() {
  console.log("🚀 Initializing HDB HomeFinder DB...");
  
  // Setup tab system
  useTabs();
  
  try {
    // Load metadata for dropdowns
    const meta = await getJSON("/api/meta");
    
    // Populate town selects
    const townSelects = ["#sel-town", "#trans-town", "#amenity-town", "#comp-town1", "#comp-town2", "#comp-town3"];
    townSelects.forEach(sel => {
      const el = $(sel);
      if (el) {
        el.innerHTML = meta.towns.map(t => `<option value="${t}">${t}</option>`).join("");
      }
    });
    
    // Populate flat type selects
    const flatSelects = ["#sel-flat", "#trans-flat"];
    flatSelects.forEach(sel => {
      const el = $(sel);
      if (el) {
        el.innerHTML = meta.flat_types.map(t => `<option value="${t}">${t}</option>`).join("");
      }
    });
    
    // Populate month selects
    const startSel = $("#sel-start");
    const endSel = $("#sel-end");
    if (startSel && endSel) {
      const monthsHTML = meta.months.map(m => `<option value="${m}">${m}</option>`).join("");
      startSel.innerHTML = monthsHTML;
      endSel.innerHTML = monthsHTML;
      startSel.value = meta.months[0];
      endSel.value = meta.months[meta.months.length - 1];
    }
    
    // Setup all panels
    await setupTrendsPanel();
    await setupTransactionsPanel();
    await setupAffordabilityPanel();
    await setupComparePanel();
    await setupAmenitiesPanel();
    
    console.log("✅ Application ready!");
  } catch (err) {
    console.error("❌ Bootstrap error:", err);
    alert("Failed to initialize application: " + err.message);
  }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootstrap);
} else {
  bootstrap();
}