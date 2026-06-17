// MCM Market JavaScript

// Auto-hide alerts after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.transition = 'opacity 0.5s ease';
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 500);
        }, 5000);
    });
});

// Product search with debounce
let searchTimeout;
function searchProducts(query) {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        if (query.length > 0) {
            window.location.href = `/search?q=${encodeURIComponent(query)}`;
        } else {
            window.location.href = '/';
        }
    }, 500);
}

// Confirm delete
function confirmDelete(message) {
    return confirm(message || 'Are you sure you want to delete this? This action cannot be undone.');
}

// Format price
function formatPrice(price) {
    return new Intl.NumberFormat('en-US', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    }).format(price);
}

// Copy to clipboard
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('Copied to clipboard!', 'success');
    }).catch(() => {
        // Fallback
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        showToast('Copied to clipboard!', 'success');
    });
}

// Toast notifications
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toastContainer') || createToastContainer();
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white bg-${type} border-0`;
    toast.role = 'alert';
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">${message}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    toastContainer.appendChild(toast);
    const bsToast = new bootstrap.Toast(toast);
    bsToast.show();
    setTimeout(() => toast.remove(), 3000);
}

function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toastContainer';
    container.style.position = 'fixed';
    container.style.bottom = '20px';
    container.style.right = '20px';
    container.style.zIndex = '9999';
    document.body.appendChild(container);
    return container;
}

// Filter logs table
function filterLogs() {
    const input = document.getElementById('logSearch');
    const filter = input.value.toLowerCase();
    const table = document.getElementById('logsTable');
    const rows = table.getElementsByTagName('tr');
    
    for (let i = 1; i < rows.length; i++) {
        const cells = rows[i].getElementsByTagName('td');
        let found = false;
        for (let j = 0; j < cells.length; j++) {
            const text = cells[j].textContent.toLowerCase();
            if (text.includes(filter)) {
                found = true;
                break;
            }
        }
        rows[i].style.display = found ? '' : 'none';
    }
}

// Export logs
function exportLogs() {
    const from = document.getElementById('dateFrom').value;
    const to = document.getElementById('dateTo').value;
    window.location.href = `/admin/logs/download?from=${from}&to=${to}`;
}

// Load more products (infinite scroll)
let page = 1;
let loading = false;
function loadMoreProducts() {
    if (loading) return;
    loading = true;
    
    fetch(`/api/products?page=${page}`)
        .then(response => response.json())
        .then(data => {
            if (data.products.length > 0) {
                // Append products to grid
                const grid = document.getElementById('productGrid');
                data.products.forEach(product => {
                    const card = createProductCard(product);
                    grid.appendChild(card);
                });
                page++;
            } else {
                // No more products
                document.getElementById('loadMoreBtn').style.display = 'none';
            }
            loading = false;
        })
        .catch(error => {
            console.error('Error loading products:', error);
            loading = false;
        });
}

function createProductCard(product) {
    const div = document.createElement('div');
    div.className = 'col-md-4 fade-in';
    div.innerHTML = `
        <div class="card product-card">
            <div class="card-body">
                <h5 class="card-title">${product.name}</h5>
                <p class="card-text">${product.description ? product.description.substring(0, 100) : ''}</p>
                <p class="fw-bold">💰 ${formatPrice(product.price)} FCFA</p>
                <p><small>📍 ${product.location}</small></p>
                <p><small>🏪 ${product.shop_name}</small></p>
                <a href="https://wa.me/${product.whatsapp}" target="_blank" class="btn whatsapp-btn w-100">
                    💬 Contact on WhatsApp
                </a>
            </div>
        </div>
    `;
    return div;
}

// Initialize Bootstrap tooltips
document.addEventListener('DOMContentLoaded', function() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
});

console.log('🚀 MCM Market loaded successfully!');
