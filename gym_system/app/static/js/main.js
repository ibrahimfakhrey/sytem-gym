// نظام إدارة الجيم - JavaScript الرئيسي

document.addEventListener('DOMContentLoaded', function() {
    // Auto-hide alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            bsAlert.close();
        }, 5000);
    });

    // Confirm delete actions
    document.querySelectorAll('[data-confirm]').forEach(element => {
        element.addEventListener('click', function(e) {
            const message = this.dataset.confirm || 'هل أنت متأكد؟';
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });

    // Auto-focus first input in forms
    const firstInput = document.querySelector('form input:not([type="hidden"]):not([type="submit"])');
    if (firstInput) {
        firstInput.focus();
    }

    // Format currency inputs
    document.querySelectorAll('.currency-input').forEach(input => {
        input.addEventListener('blur', function() {
            const value = parseFloat(this.value);
            if (!isNaN(value)) {
                this.value = value.toFixed(2);
            }
        });
    });

    // Phone number formatting
    document.querySelectorAll('input[type="tel"]').forEach(input => {
        input.addEventListener('input', function() {
            // Remove non-digits
            this.value = this.value.replace(/[^\d]/g, '');
        });
    });
});

// Member search functionality
function initMemberSearch(inputId, resultsId, callback) {
    const input = document.getElementById(inputId);
    const results = document.getElementById(resultsId);

    if (!input || !results) return;

    let searchTimeout;

    input.addEventListener('input', function() {
        clearTimeout(searchTimeout);
        const query = this.value.trim();

        if (query.length < 2) {
            results.innerHTML = '';
            return;
        }

        searchTimeout = setTimeout(() => {
            fetch(`/members/search?q=${encodeURIComponent(query)}`)
                .then(response => response.json())
                .then(data => {
                    if (data.results.length === 0) {
                        results.innerHTML = '<div class="text-center text-muted py-3">لا توجد نتائج</div>';
                        return;
                    }

                    results.innerHTML = data.results.map(member => `
                        <div class="member-card" onclick="${callback}(${member.id})">
                            <div class="avatar">${member.name.charAt(0)}</div>
                            <div class="info">
                                <div class="name">${member.name}</div>
                                <div class="phone">${member.phone}</div>
                            </div>
                            <span class="badge bg-${member.status_class}">${member.status}</span>
                        </div>
                    `).join('');
                })
                .catch(error => {
                    console.error('Search error:', error);
                    results.innerHTML = '<div class="text-center text-danger py-3">حدث خطأ في البحث</div>';
                });
        }, 300);
    });
}

// Attendance search
function initAttendanceSearch() {
    const input = document.getElementById('attendanceSearch');
    const results = document.getElementById('searchResults');
    const form = document.getElementById('checkInForm');
    const memberIdInput = document.getElementById('memberId');

    if (!input || !results) return;

    let searchTimeout;

    input.addEventListener('input', function() {
        clearTimeout(searchTimeout);
        const query = this.value.trim();

        if (query.length < 2) {
            results.innerHTML = '';
            return;
        }

        searchTimeout = setTimeout(() => {
            fetch(`/attendance/api/search?q=${encodeURIComponent(query)}`)
                .then(response => response.json())
                .then(data => {
                    if (data.results.length === 0) {
                        results.innerHTML = '<div class="text-center text-muted py-3">لا توجد نتائج</div>';
                        return;
                    }

                    results.innerHTML = data.results.map(member => `
                        <div class="member-card ${member.can_check_in ? '' : 'opacity-75'}"
                             onclick="selectMemberForCheckIn(${member.id}, '${member.name}', ${member.can_check_in})">
                            <div class="avatar">${member.name.charAt(0)}</div>
                            <div class="info">
                                <div class="name">${member.name}</div>
                                <div class="phone">${member.phone}</div>
                                ${member.days_remaining > 0 ? `<small class="text-muted">متبقي: ${member.days_remaining} يوم</small>` : ''}
                            </div>
                            <div class="text-end">
                                <span class="badge bg-${member.status_class}">${member.status}</span>
                                ${!member.can_check_in ? `<br><small class="text-danger">${member.message}</small>` : ''}
                            </div>
                        </div>
                    `).join('');
                })
                .catch(error => {
                    console.error('Search error:', error);
                    results.innerHTML = '<div class="text-center text-danger py-3">حدث خطأ في البحث</div>';
                });
        }, 300);
    });
}

function selectMemberForCheckIn(memberId, memberName, canCheckIn) {
    const memberIdInput = document.getElementById('memberId');
    const form = document.getElementById('checkInForm');
    const selectedMember = document.getElementById('selectedMember');
    const searchResults = document.getElementById('searchResults');

    if (memberIdInput && form) {
        memberIdInput.value = memberId;

        if (selectedMember) {
            selectedMember.innerHTML = `
                <div class="alert alert-info">
                    <strong>العضو المحدد:</strong> ${memberName}
                    ${!canCheckIn ? '<br><span class="text-warning">تحذير: قد يكون هناك مشكلة في الاشتراك</span>' : ''}
                </div>
            `;
        }

        if (searchResults) {
            searchResults.innerHTML = '';
        }

        // Auto submit if can check in
        if (canCheckIn) {
            form.submit();
        }
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Initialize attendance search if on attendance page
    if (document.getElementById('attendanceSearch')) {
        initAttendanceSearch();
    }
});

// Print function
function printPage() {
    window.print();
}

// Export table to Excel (simple CSV)
function exportTableToCSV(tableId, filename) {
    const table = document.getElementById(tableId);
    if (!table) return;

    let csv = [];
    const rows = table.querySelectorAll('tr');

    rows.forEach(row => {
        const cols = row.querySelectorAll('td, th');
        const rowData = [];
        cols.forEach(col => {
            // Remove any HTML and get text content
            let text = col.innerText.replace(/"/g, '""');
            rowData.push(`"${text}"`);
        });
        csv.push(rowData.join(','));
    });

    // Create download
    const csvContent = '\uFEFF' + csv.join('\n'); // BOM for UTF-8
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename || 'export.csv';
    link.click();
}
