// Global Variables
let chartInstance = null;
let sectorChartInstance = null;
let debounceTimeout = null;
let selectedUploadedFiles = []; // To keep track of uploaded files in memory

// DOM Elements
const searchInput = document.getElementById("search-input");
const autocompleteList = document.getElementById("autocomplete-list");
const clearSearchBtn = document.getElementById("clear-search-btn");

const welcomeView = document.getElementById("welcome-view");
const loadingView = document.getElementById("loading-view");
const errorView = document.getElementById("error-view");
const dashboardView = document.getElementById("dashboard-view");
const errorMsg = document.getElementById("error-msg");
const retryBtn = document.getElementById("retry-btn");

// New DOM Elements for Batch Screening
const batchResultsView = document.getElementById("batch-results-view");
const localFilesList = document.getElementById("local-files-list");
const dropZone = document.getElementById("drop-zone");
const fileUploader = document.getElementById("file-uploader");
const uploadedFilesList = document.getElementById("uploaded-files-list");
const startScreeningBtn = document.getElementById("start-screening-btn");
const saveRulesBtn = document.getElementById("save-rules-btn");

const ruleMinSales = document.getElementById("rule-min-sales");
const ruleMinEps = document.getElementById("rule-min-eps");
const ruleMinNpm = document.getElementById("rule-min-npm");
const ruleAllowIpo = document.getElementById("rule-allow-ipo");

const batchTotalBadge = document.getElementById("batch-total-badge");
const batchPassBadge = document.getElementById("batch-pass-badge");
const batchFailBadge = document.getElementById("batch-fail-badge");

const downloadStrongBtn = document.getElementById("download-strong-btn");
const downloadRejectedBtn = document.getElementById("download-rejected-btn");
const backToHomeBtn = document.getElementById("back-to-home-btn");

// Initialization
document.addEventListener("DOMContentLoaded", () => {
    // Set up search autocomplete
    searchInput.addEventListener("input", handleSearchInput);
    searchInput.addEventListener("focus", () => {
        if (autocompleteList.children.length > 0) {
            autocompleteList.classList.remove("hidden");
        }
    });

    // Clear search
    clearSearchBtn.addEventListener("click", () => {
        searchInput.value = "";
        autocompleteList.innerHTML = "";
        autocompleteList.classList.add("hidden");
        clearSearchBtn.classList.add("hidden");
        searchInput.focus();
    });

    // Close autocomplete when clicking outside
    document.addEventListener("click", (e) => {
        if (!e.target.closest(".search-box-container")) {
            autocompleteList.classList.add("hidden");
        }
    });

    // Tag clicks (Popular Stocks)
    document.querySelectorAll(".tag-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const symbol = btn.getAttribute("data-symbol");
            loadStockData(symbol);
        });
    });

    // Retry Button
    retryBtn.addEventListener("click", () => {
        errorView.classList.add("hidden");
        welcomeView.classList.remove("hidden");
        searchInput.value = "";
    });

    // Initialize Batch Screening Features
    initBatchScreening();

    // Check App Config (e.g. Hide Batch Screener if set via env)
    checkAppConfig();
});

// Search Autocomplete Handler
function handleSearchInput() {
    const query = searchInput.value.trim();
    
    if (query.length > 0) {
        clearSearchBtn.classList.remove("hidden");
    } else {
        clearSearchBtn.classList.add("hidden");
        autocompleteList.innerHTML = "";
        autocompleteList.classList.add("hidden");
        return;
    }

    clearTimeout(debounceTimeout);
    debounceTimeout = setTimeout(async () => {
        try {
            const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
            const data = await res.json();
            
            displayAutocompleteResults(data.results || []);
        } catch (err) {
            console.error("Autocomplete error:", err);
        }
    }, 300);
}

// Display Autocomplete suggestions
function displayAutocompleteResults(results) {
    autocompleteList.innerHTML = "";
    
    if (results.length === 0) {
        autocompleteList.classList.add("hidden");
        return;
    }

    results.forEach(item => {
        const div = document.createElement("div");
        div.className = "autocomplete-item";
        
        // Screener returns items with {name, url, code}
        // Example url: /company/RELIANCE/consolidated/
        const symbol = item.code || item.url.split("/company/")[1].split("/")[0];
        
        div.innerHTML = `
            <div class="comp-name">${item.name}</div>
            <div class="comp-meta">
                <span>Symbol: <strong>${symbol}</strong></span>
                <span>Type: NSE/BSE</span>
            </div>
        `;
        
        div.addEventListener("click", () => {
            searchInput.value = item.name;
            autocompleteList.classList.add("hidden");
            loadStockData(symbol);
        });
        
        autocompleteList.appendChild(div);
    });

    autocompleteList.classList.remove("hidden");
}

// Load Stock Data & AI Narrative
async function loadStockData(symbol) {
    // Hide UI components
    welcomeView.classList.add("hidden");
    dashboardView.classList.add("hidden");
    errorView.classList.add("hidden");
    batchResultsView.classList.add("hidden");
    loadingView.classList.remove("hidden");
    
    autocompleteList.classList.add("hidden");
    
    const apiKey = localStorage.getItem("gemini_api_key") || "";
    
    try {
        const response = await fetch(`/api/stock?symbol=${encodeURIComponent(symbol)}`, {
            headers: {
                "x-gemini-api-key": apiKey
            }
        });
        
        if (!response.ok) {
            throw new Error(`Server returned status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.error && (!data.quarterly_financials || data.quarterly_financials.length === 0)) {
            throw new Error(data.error);
        }
        
        populateDashboard(data);
        
        loadingView.classList.add("hidden");
        dashboardView.classList.remove("hidden");
    } catch (err) {
        console.error("Error loading stock data:", err);
        loadingView.classList.add("hidden");
        errorMsg.textContent = err.message || "Failed to fetch stock financials and news. Please try another symbol.";
        errorView.classList.remove("hidden");
    }
}

// Populate Dashboard Views
function populateDashboard(data) {
    // 1. Header Details
    document.getElementById("stock-name").textContent = data.company_name;
    document.getElementById("stock-ticker").textContent = data.symbol;
    document.getElementById("stock-yahoo-ticker").textContent = data.yahoo_symbol;
    document.getElementById("stock-sector").textContent = data.sector;
    document.getElementById("stock-industry").textContent = data.industry;
    
    const price = data.current_price || 0;
    document.getElementById("stock-price").textContent = price ? `₹${Number(price).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "₹--";
    
    const priceChangeEl = document.getElementById("stock-change");
    if (priceChangeEl) {
        priceChangeEl.style.display = "none";
    }

    // 2. Quarterly Financials Table
    const quartersBody = document.querySelector("#quarters-table tbody");
    quartersBody.innerHTML = "";
    
    const financials = data.quarterly_financials || [];
    
    // We want to render the last 6 quarters
    const totalQuarters = financials.length;
    const startIdx = Math.max(0, totalQuarters - 6);
    const renderQuarters = financials.slice(startIdx);
    
    renderQuarters.forEach((q, idx) => {
        const fullIdx = startIdx + idx;
        const prevQ = fullIdx - 1 >= 0 ? financials[fullIdx - 1] : null;
        const yoyQ = fullIdx - 4 >= 0 ? financials[fullIdx - 4] : null;
        
        // Helper to format values alongside QoQ & YoY percentage changes
        function formatMetric(val, prevVal, yoyVal, isPercent = false, prefix = "") {
            if (val === null || val === undefined) return "--";
            
            let displayVal = isPercent ? `${val.toFixed(2)}%` : `${prefix}${val.toLocaleString("en-IN")}`;
            if (!isPercent && prefix === "₹") {
                displayVal += " Cr";
            }
            
            let changes = [];
            
            // QoQ Calculation
            if (prevVal !== null && prevVal !== undefined && prevVal !== 0) {
                if (isPercent) {
                    const diff = val - prevVal; // Margin difference in percentage points
                    const sign = diff >= 0 ? "+" : "";
                    const color = diff >= 0 ? "#10b981" : "#ef4444";
                    changes.push(`<span style="color: ${color}; font-weight: 700;">QoQ: ${sign}${diff.toFixed(1)}%</span>`);
                } else {
                    const diff = ((val - prevVal) / prevVal) * 100;
                    const sign = diff >= 0 ? "+" : "";
                    const color = diff >= 0 ? "#10b981" : "#ef4444";
                    changes.push(`<span style="color: ${color}; font-weight: 700;">QoQ: ${sign}${diff.toFixed(1)}%</span>`);
                }
            }
            
            // YoY Calculation
            if (yoyVal !== null && yoyVal !== undefined && yoyVal !== 0) {
                if (isPercent) {
                    const diff = val - yoyVal; // Margin difference in percentage points
                    const sign = diff >= 0 ? "+" : "";
                    const color = diff >= 0 ? "#10b981" : "#ef4444";
                    changes.push(`<span style="color: ${color}; font-weight: 700;">YoY: ${sign}${diff.toFixed(1)}%</span>`);
                } else {
                    const diff = ((val - yoyVal) / yoyVal) * 100;
                    const sign = diff >= 0 ? "+" : "";
                    const color = diff >= 0 ? "#10b981" : "#ef4444";
                    changes.push(`<span style="color: ${color}; font-weight: 700;">YoY: ${sign}${diff.toFixed(1)}%</span>`);
                }
            }
            
            let changesHtml = "";
            if (changes.length > 0) {
                changesHtml = `<div style="font-size: 0.75rem; margin-top: 0.25rem; color: var(--text-muted); display: flex; gap: 0.4rem; flex-wrap: wrap; font-feature-settings: 'tnum';">
                    ${changes.join(' <span style="opacity: 0.3;">|</span> ')}
                </div>`;
            }
            
            return `<div>
                <div style="font-weight: 600;">${displayVal}</div>
                ${changesHtml}
            </div>`;
        }
        
        const salesHtml = formatMetric(q.sales, prevQ?.sales, yoyQ?.sales, false, "₹");
        const npmHtml = formatMetric(q.npm_percent, prevQ?.npm_percent, yoyQ?.npm_percent, true);
        const epsHtml = formatMetric(q.eps, prevQ?.eps, yoyQ?.eps, false, "₹");
        
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td><strong>${q.quarter}</strong></td>
            <td>${salesHtml}</td>
            <td>${npmHtml}</td>
            <td>${epsHtml}</td>
        `;
        quartersBody.appendChild(tr);
    });
    
    // Financial trends logic
    const salesTrendEl = document.getElementById("financial-sales-trend");
    const npmTrendEl = document.getElementById("financial-npm-trend");
    if (financials.length >= 2) {
        const latest = financials[financials.length - 1];
        const prev = financials[financials.length - 2];
        
        if (latest.sales && prev.sales) {
            const salesDiff = ((latest.sales - prev.sales) / prev.sales) * 100;
            salesTrendEl.innerHTML = `QoQ Sales: <span style="color: ${salesDiff >= 0 ? "var(--success)" : "var(--danger)"}">${salesDiff >= 0 ? "▲" : "▼"} ${Math.abs(salesDiff).toFixed(1)}%</span>`;
        } else {
            salesTrendEl.textContent = "Sales: Steady";
        }
        
        if (latest.npm_percent !== null && prev.npm_percent !== null) {
            const npmDiff = latest.npm_percent - prev.npm_percent;
            npmTrendEl.innerHTML = `QoQ Margin: <span style="color: ${npmDiff >= 0 ? "var(--success)" : "var(--danger)"}">${npmDiff >= 0 ? "▲" : "▼"} ${Math.abs(npmDiff).toFixed(1)}%</span>`;
        } else {
            npmTrendEl.textContent = "Margin: Steady";
        }
    } else {
        salesTrendEl.textContent = "Sales: --";
        npmTrendEl.textContent = "Margin: --";
    }

    // 7. Peers Table
    const peersBody = document.querySelector("#peers-table tbody");
    peersBody.innerHTML = "";
    const peers = data.peers || [];
    if (peers.length === 0) {
        peersBody.innerHTML = `<tr><td colspan="7" style="text-align:center;">No peer metrics available.</td></tr>`;
    } else {
        peers.forEach(p => {
            const isSelf = p.symbol.toUpperCase() === data.symbol.toUpperCase();
            const tr = document.createElement("tr");
            if (isSelf) {
                tr.style.background = "rgba(99, 102, 241, 0.1)";
                tr.style.fontWeight = "700";
            }
            
            // Format values
            const cmpVal = p.cmp ? `₹${p.cmp.toLocaleString("en-IN")}` : "--";
            const peVal = p.pe !== null ? p.pe.toFixed(1) : "--";
            const mcVal = p.market_cap_cr ? p.market_cap_cr.toLocaleString("en-IN") : "--";
            const divVal = p.div_yield_percent !== null ? `${p.div_yield_percent}%` : "--";
            const npVal = p.net_profit_qtr_cr ? `₹${p.net_profit_qtr_cr.toLocaleString("en-IN")}` : "--";
            const salesVal = p.sales_qtr_cr ? `₹${p.sales_qtr_cr.toLocaleString("en-IN")}` : "--";
            
            tr.innerHTML = `
                <td>${p.name} ${isSelf ? ' <small>(Current)</small>' : ''}</td>
                <td>${cmpVal}</td>
                <td>${peVal}</td>
                <td>${mcVal}</td>
                <td>${divVal}</td>
                <td>${npVal}</td>
                <td>${salesVal}</td>
            `;
            
            // Allow clicking peer to load them
            if (!isSelf && p.symbol) {
                tr.style.cursor = "pointer";
                tr.addEventListener("click", () => {
                    loadStockData(p.symbol);
                });
            }
            
            peersBody.appendChild(tr);
        });
    }
}

// Render Relative Strength chart
function renderRSChart(chartData) {
    const ctx = document.getElementById("rs-chart").getContext("2d");
    
    // Destroy previous chart if exists
    if (chartInstance) {
        chartInstance.destroy();
    }
    
    if (chartData.length === 0) {
        return;
    }
    
    const labels = chartData.map(d => d.date);
    const stockPrices = chartData.map(d => d.stock_price);
    const rsLine = chartData.map(d => d.rs_line_norm); // Normalized RS line
    
    chartInstance = new Chart(ctx, {
        type: "line",
        data: {
            labels: labels,
            datasets: [
                {
                    label: "Stock Price (₹)",
                    data: stockPrices,
                    borderColor: "#6366f1",
                    backgroundColor: "rgba(99, 102, 241, 0.05)",
                    borderWidth: 2,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    yAxisID: "yPrice"
                },
                {
                    label: "Relative Strength Index (vs Nifty50, Base 100)",
                    data: rsLine,
                    borderColor: "#06b6d4",
                    backgroundColor: "rgba(6, 182, 212, 0.03)",
                    borderWidth: 2.5,
                    borderDash: [5, 5],
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    yAxisID: "yRS"
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: "index",
                intersect: false
            },
            plugins: {
                legend: {
                    position: "top",
                    labels: {
                        color: "#94a3b8",
                        font: {
                            family: "Plus Jakarta Sans",
                            size: 11
                        }
                    }
                },
                tooltip: {
                    backgroundColor: "#0f131a",
                    titleColor: "#f8fafc",
                    bodyColor: "#94a3b8",
                    borderColor: "rgba(255,255,255,0.1)",
                    borderWidth: 1,
                    titleFont: { family: "Plus Jakarta Sans" },
                    bodyFont: { family: "Plus Jakarta Sans" }
                }
            },
            scales: {
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        color: "#64748b",
                        font: { family: "Plus Jakarta Sans", size: 10 }
                    }
                },
                yPrice: {
                    type: "linear",
                    display: true,
                    position: "left",
                    grid: {
                        color: "rgba(255, 255, 255, 0.03)"
                    },
                    ticks: {
                        color: "#94a3b8",
                        font: { family: "Plus Jakarta Sans", size: 10 }
                    },
                    title: {
                        display: true,
                        text: "Stock Price (₹)",
                        color: "#6366f1",
                        font: { family: "Plus Jakarta Sans", size: 11, weight: "bold" }
                    }
                },
                yRS: {
                    type: "linear",
                    display: true,
                    position: "right",
                    grid: {
                        drawOnChartArea: false // prevent grid lines from overlapping
                    },
                    ticks: {
                        color: "#94a3b8",
                        font: { family: "Plus Jakarta Sans", size: 10 }
                    },
                    title: {
                        display: true,
                        text: "RS Line Rating (Base 100)",
                        color: "#06b6d4",
                        font: { family: "Plus Jakarta Sans", size: 11, weight: "bold" }
                    }
                }
            }
        }
    });
}

async function checkAppConfig() {
    try {
        const res = await fetch("/api/config");
        const config = await res.json();
        if (config.hide_batch_screener) {
            const batchCard = document.querySelector(".batch-card");
            if (batchCard) {
                batchCard.style.display = "none";
            }
            const welcomeGrid = document.querySelector(".welcome-grid");
            if (welcomeGrid) {
                welcomeGrid.style.gridTemplateColumns = "1fr";
                welcomeGrid.style.maxWidth = "720px";
            }
        }
    } catch (err) {
        console.error("Error fetching app config:", err);
    }
}

// ==========================================
// Batch Fundamental Screening Features
// ==========================================
async function initBatchScreening() {
    // 1. Fetch rules and files list
    loadFundamentalRules();
    loadScannedFiles();

    // 2. Threshold Save Event
    saveRulesBtn.addEventListener("click", saveFundamentalRules);

    // 3. Drop Zone setup (Drag & Drop)
    dropZone.addEventListener("click", () => fileUploader.click());
    fileUploader.addEventListener("change", handleFileSelection);

    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("drag-over");
    });

    ["dragleave", "drop"].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropZone.classList.remove("drag-over");
        });
    });

    dropZone.addEventListener("drop", (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            handleFilesList(files);
        }
    });

    // 4. Start Screening
    startScreeningBtn.addEventListener("click", startBatchScreening);

    // 5. Back to Home Button
    backToHomeBtn.addEventListener("click", () => {
        batchResultsView.classList.add("hidden");
        welcomeView.classList.remove("hidden");
        loadScannedFiles();
    });
}

async function loadFundamentalRules() {
    try {
        const res = await fetch("/api/fundamental-rules");
        const rules = await res.json();
        ruleMinSales.value = rules.min_sales_growth_qoq;
        ruleMinEps.value = rules.min_eps_growth_qoq;
        ruleMinNpm.value = rules.min_npm_percent;
        ruleAllowIpo.checked = rules.allow_missing_yoy_for_ipos;
    } catch (err) {
        console.error("Error loading rules:", err);
    }
}

async function saveFundamentalRules() {
    const rules = {
        min_sales_growth_qoq: parseFloat(ruleMinSales.value) || 0.0,
        min_eps_growth_qoq: parseFloat(ruleMinEps.value) || 0.0,
        min_npm_percent: parseFloat(ruleMinNpm.value) || 0.0,
        allow_missing_yoy_for_ipos: ruleAllowIpo.checked
    };

    try {
        const res = await fetch("/api/fundamental-rules", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(rules)
        });
        const data = await res.json();
        if (data.status === "success") {
            alert("Threshold rules applied successfully!");
        }
    } catch (err) {
        console.error("Error saving rules:", err);
        alert("Failed to save rules.");
    }
}

async function loadScannedFiles() {
    try {
        const res = await fetch("/api/scanned-files");
        const data = await res.json();
        displayScannedFiles(data.files || []);
    } catch (err) {
        console.error("Error loading scanned files:", err);
        localFilesList.innerHTML = `<p class="loading-files" style="color:var(--danger)">Failed to load scans.</p>`;
    }
}

function displayScannedFiles(files) {
    localFilesList.innerHTML = "";
    if (files.length === 0) {
        localFilesList.innerHTML = `<p class="loading-files">No technical scans (.xlsx, .csv) found in outputs directory.</p>`;
        return;
    }

    files.forEach(f => {
        const label = document.createElement("label");
        label.innerHTML = `
            <input type="checkbox" name="local-scan-file" value="${f}">
            <span>${f}</span>
        `;
        localFilesList.appendChild(label);
    });
}

function handleFileSelection(e) {
    const files = e.target.files;
    if (files.length > 0) {
        handleFilesList(files);
    }
}

function handleFilesList(files) {
    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        // Check duplicate
        if (selectedUploadedFiles.some(f => f.name === file.name)) continue;
        
        selectedUploadedFiles.push(file);
        
        const tag = document.createElement("div");
        tag.className = "uploaded-file-tag";
        tag.innerHTML = `
            <span>📄 ${file.name}</span>
            <span class="remove-btn">&times;</span>
        `;
        
        tag.querySelector(".remove-btn").addEventListener("click", () => {
            selectedUploadedFiles = selectedUploadedFiles.filter(f => f.name !== file.name);
            tag.remove();
        });
        
        uploadedFilesList.appendChild(tag);
    }
}

async function startBatchScreening() {
    const localCheckboxes = document.querySelectorAll('input[name="local-scan-file"]:checked');
    const localFiles = Array.from(localCheckboxes).map(cb => cb.value);
    
    if (localFiles.length === 0 && selectedUploadedFiles.length === 0) {
        alert("Please select at least one scan list or upload an Excel/CSV file.");
        return;
    }

    const formData = new FormData();
    if (localFiles.length > 0) {
        formData.append("local_files", localFiles.join(","));
    }
    
    selectedUploadedFiles.forEach(file => {
        formData.append("files", file);
    });

    welcomeView.classList.add("hidden");
    dashboardView.classList.add("hidden");
    batchResultsView.classList.add("hidden");
    errorView.classList.add("hidden");
    
    const loadingText = document.getElementById("loading-text");
    loadingText.textContent = "Running Batch Fundamental Screening... Scraping Screener.in in parallel and evaluating QoQ growth metric trends. Please wait.";
    loadingView.classList.remove("hidden");

    try {
        const res = await fetch("/api/batch-screen", {
            method: "POST",
            body: formData
        });
        
        if (!res.ok) {
            const errData = await res.json();
            throw new Error(errData.detail || "Batch screening request failed.");
        }

        const data = await res.json();
        populateBatchResults(data);
        
        loadingView.classList.add("hidden");
        batchResultsView.classList.remove("hidden");
        
        // Auto trigger downloads immediately!
        triggerDownload(data.strong_file);
        setTimeout(() => triggerDownload(data.rejected_file), 1000);
        
    } catch (err) {
        console.error("Batch screening error:", err);
        loadingView.classList.add("hidden");
        errorMsg.textContent = err.message || "An error occurred during batch screening.";
        errorView.classList.remove("hidden");
    }
}

function triggerDownload(filename) {
    if (!filename) return;
    const url = `/api/download?file=${encodeURIComponent(filename)}`;
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

function populateBatchResults(data) {
    batchTotalBadge.textContent = `Total Evaluated: ${data.total_checked}`;
    batchPassBadge.textContent = `Passed: ${data.passed_count}`;
    batchFailBadge.textContent = `Rejected: ${data.rejected_count}`;

    downloadStrongBtn.onclick = () => triggerDownload(data.strong_file);
    downloadRejectedBtn.onclick = () => triggerDownload(data.rejected_file);

    const passedBody = document.querySelector("#passed-stocks-table tbody");
    passedBody.innerHTML = "";
    
    if (data.passed_stocks.length === 0) {
        passedBody.innerHTML = `<tr><td colspan="8" style="text-align:center; color:var(--text-muted);">No stocks passed the strict fundamental criteria.</td></tr>`;
    } else {
        data.passed_stocks.forEach(s => {
            const tr = document.createElement("tr");
            
            const mcVal = s["Market Cap (Cr)"] ? s["Market Cap (Cr)"].toLocaleString("en-IN") : "--";
            const npmVal = s["Q0 NPM %"] !== null ? `${s["Q0 NPM %"].toFixed(1)}%` : "--";
            const salesVal = s["Q0 Sales QoQ %"] !== null ? `${s["Q0 Sales QoQ %"].toFixed(1)}%` : "--";
            const epsVal = s["Q0 EPS QoQ %"] !== null ? `${s["Q0 EPS QoQ %"].toFixed(1)}%` : "--";
            
            tr.innerHTML = `
                <td><strong>${s.Symbol}</strong></td>
                <td>${s["Company Name"]}</td>
                <td>${s.Sector}</td>
                <td>${s.Industry}</td>
                <td>${mcVal}</td>
                <td style="color:var(--success); font-weight:700;">${npmVal}</td>
                <td style="color:var(--success); font-weight:700;">${salesVal}</td>
                <td style="color:var(--success); font-weight:700;">${epsVal}</td>
            `;
            passedBody.appendChild(tr);
        });
    }

    const rejectedBody = document.querySelector("#rejected-stocks-table tbody");
    rejectedBody.innerHTML = "";
    
    if (data.rejected_stocks.length === 0) {
        rejectedBody.innerHTML = `<tr><td colspan="3" style="text-align:center; color:var(--success);">All evaluated stocks passed the thresholds!</td></tr>`;
    } else {
        data.rejected_stocks.forEach(s => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><strong>${s.Symbol}</strong></td>
                <td>${s["Company Name"]}</td>
                <td>${s.Reason}</td>
            `;
            rejectedBody.appendChild(tr);
        });
    }

    const summaryBody = document.querySelector("#sector-summary-table tbody");
    summaryBody.innerHTML = "";
    
    if (data.sector_summary.length === 0) {
        summaryBody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--text-muted);">No summary metrics.</td></tr>`;
    } else {
        data.sector_summary.forEach(sec => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><strong>${sec.Sector}</strong></td>
                <td style="font-weight:700; color:var(--accent);">${sec.Count}</td>
                <td>${sec.Avg_NPM_Q0}%</td>
                <td>${sec.Avg_Market_Cap_Cr.toLocaleString("en-IN")} Cr</td>
            `;
            summaryBody.appendChild(tr);
        });
    }

    renderSectorPieChart(data.sector_summary || []);
}

function renderSectorPieChart(summaryData) {
    const ctx = document.getElementById("sector-pie-chart").getContext("2d");

    if (sectorChartInstance) {
        sectorChartInstance.destroy();
    }

    if (summaryData.length === 0) {
        return;
    }

    const labels = summaryData.map(d => d.Sector);
    const counts = summaryData.map(d => d.Count);
    
    const colors = [
        "#6366f1", "#06b6d4", "#10b981", "#f59e0b", "#ec4899", 
        "#8b5cf6", "#14b8a6", "#f43f5e", "#3b82f6", "#eab308"
    ];

    sectorChartInstance = new Chart(ctx, {
        type: "pie",
        data: {
            labels: labels,
            datasets: [{
                data: counts,
                backgroundColor: colors.slice(0, labels.length),
                borderColor: "rgba(15, 23, 42, 0.9)",
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: "right",
                    labels: {
                        color: "#94a3b8",
                        font: {
                            family: "Plus Jakarta Sans",
                            size: 11
                        },
                        boxWidth: 12
                    }
                },
                tooltip: {
                    backgroundColor: "#0f131a",
                    titleColor: "#f8fafc",
                    bodyColor: "#94a3b8",
                    borderColor: "rgba(255,255,255,0.1)",
                    borderWidth: 1,
                    callbacks: {
                        label: function(context) {
                            const label = context.label || "";
                            const value = context.parsed || 0;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percent = ((value / total) * 100).toFixed(1);
                            return ` ${label}: ${value} stocks (${percent}%)`;
                        }
                    }
                }
            }
        }
    });
}

// Immediate check on script load
checkAppConfig();
