# 🧪 Testing Plan - Gym Management System Bug Fixes

**Created:** 2026-01-31
**Total Test Cases:** 26
**Estimated Time:** 2-3 hours (comprehensive) | 1 hour (critical only)

---

## 📋 Test Environment Setup

### Prerequisites
Before starting tests, ensure you have:

- [ ] Database with multiple brands (at least 2)
- [ ] Database with multiple branches (at least 3, some in same brand)
- [ ] Test user accounts for each role:
  - [ ] Owner account
  - [ ] Brand Manager account
  - [ ] Central Accountant (no branch_id set)
  - [ ] Branch Accountant (with branch_id set)
  - [ ] Receptionist (with branch_id set)
- [ ] At least 5 test members
- [ ] At least 3 active subscriptions
- [ ] Biometric device configured (or ability to check DeviceCommand table)

### Test Data Setup Commands

```sql
-- Check your test users have correct roles and branches
SELECT id, name, email, role_id, brand_id, branch_id FROM users;

-- Check you have multiple branches
SELECT id, brand_id, name, is_active FROM branches;

-- Check existing subscriptions
SELECT id, member_id, status, end_date FROM subscriptions ORDER BY end_date DESC LIMIT 10;
```

---

## 🔴 PHASE 1: CRITICAL TESTS (Priority: MUST PASS)
**Estimated Time:** 30 minutes

### Test 1.1: Payment Method Required on Subscription Creation
**Priority:** CRITICAL
**Bug Fixed:** Issue #5 - Missing payment method validation
**Location:** `/subscriptions/create`

**Steps:**
1. Login as receptionist or brand manager
2. Navigate to Members → Select a member → Create Subscription
3. Fill out form:
   - Select a plan
   - Enter paid amount
   - **DO NOT select payment method** (leave it as "-- اختر طريقة الدفع --")
4. Click Submit

**Expected Result:**
- ❌ Form should reject with validation error
- ❌ Error message: "يرجى اختيار طريقة الدفع"
- ❌ Subscription should NOT be created

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

### Test 1.2: Payment Method Required on Subscription Renewal
**Priority:** CRITICAL
**Bug Fixed:** Issue #11 - Missing payment method in renewal
**Location:** `/subscriptions/<id>/renew`

**Steps:**
1. Go to Subscriptions → View an active subscription
2. Click "Renew" button
3. Fill renewal form:
   - Enter paid amount
   - **DO NOT select payment method**
4. Click Submit

**Expected Result:**
- ❌ Form should reject with validation error
- ❌ Renewal should NOT be created without payment method

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

### Test 1.3: Transaction Metadata - Service Type & Branch Tracking
**Priority:** CRITICAL
**Bug Fixed:** Issue #15.2 - Missing service_type_id and branch_id in Income
**Location:** Database verification after subscription creation

**Steps:**
1. Create a new subscription with:
   - Service type: "جيم" (or any service type)
   - Plan: Any plan
   - Payment method: كاش
   - Paid amount: 500
2. After creation, run this query:

```sql
-- Check the latest income record
SELECT
    id,
    brand_id,
    branch_id,
    service_type_id,
    subscription_id,
    amount,
    payment_method,
    type,
    date
FROM income
ORDER BY created_at DESC
LIMIT 1;
```

**Expected Result:**
- ✅ `branch_id` should NOT be NULL (should match member's branch)
- ✅ `service_type_id` should NOT be NULL (should match subscription's service type)
- ✅ `payment_method` should be 'cash'
- ✅ `amount` should be 500

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

**Database Results:**
```
branch_id: _______
service_type_id: _______
payment_method: _______
```

---

### Test 1.4: Biometric Auto-Unblock on Subscription Creation
**Priority:** CRITICAL
**Bug Fixed:** Issue #6.2 - Biometric integration missing
**Location:** Database check after subscription creation

**Steps:**
1. Ensure member has `fingerprint_id` set
2. Ensure brand has `uses_fingerprint = TRUE`
3. Create new subscription for this member
4. Run this query:

```sql
-- Check DeviceCommand was created
SELECT
    id,
    brand_id,
    command_type,
    target_emp_id,
    member_id,
    status,
    command_data,
    created_at
FROM device_commands
ORDER BY created_at DESC
LIMIT 1;
```

**Expected Result:**
- ✅ New record should exist
- ✅ `command_type` should be 'unblock_member'
- ✅ `target_emp_id` should match member's fingerprint_id
- ✅ `member_id` should match the member
- ✅ `status` should be 'pending'
- ✅ `command_data` should contain subscription end_date

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

### Test 1.5: Biometric Block on Subscription Freeze
**Priority:** CRITICAL
**Bug Fixed:** Issue #6.2 - Biometric freeze integration
**Location:** Database check after freeze

**Steps:**
1. Find active subscription for member with fingerprint_id
2. Navigate to subscription view page
3. Click "Freeze Subscription" (تجميد)
4. Fill freeze form and submit
5. Run same query as Test 1.4

**Expected Result:**
- ✅ New DeviceCommand record created
- ✅ `command_type` should be 'block_member'
- ✅ `command_data` should show end_date as '2020-01-01' (past date to block access)

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

### Test 1.6: Biometric Unblock on Subscription Unfreeze
**Priority:** CRITICAL
**Bug Fixed:** Issue #6.2 - Biometric unfreeze integration
**Location:** Database check after unfreeze

**Steps:**
1. Use frozen subscription from Test 1.5
2. Click "Unfreeze" (إلغاء التجميد)
3. Submit form
4. Run DeviceCommand query

**Expected Result:**
- ✅ New DeviceCommand record created
- ✅ `command_type` should be 'unblock_member'
- ✅ `command_data` should contain subscription's actual end_date (not 2020)

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

### Test 1.7: Biometric Update on Renewal
**Priority:** CRITICAL
**Bug Fixed:** Issue #6.2 - Biometric renewal integration
**Location:** Database check after renewal

**Steps:**
1. Renew subscription for member with fingerprint
2. Note the new end_date
3. Run DeviceCommand query

**Expected Result:**
- ✅ New DeviceCommand record created
- ✅ `command_type` should be 'unblock_member'
- ✅ `command_data` should contain NEW end_date from renewal

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

## 🟠 PHASE 2: BLOCKER TESTS (Priority: HIGH)
**Estimated Time:** 15 minutes

### Test 2.1: Branch Edit Route - No 500 Error
**Priority:** BLOCKER
**Bug Fixed:** Issue #8.1 - System crash on branch edit
**Location:** `/admin/branches/<id>/edit`

**Steps:**
1. Login as owner or brand manager
2. Navigate to Admin → Brands → Select Brand → View Branches
3. Click "Edit" (تعديل) button on any branch
4. Observe the page

**Expected Result:**
- ✅ Page should load successfully (NO 500 error)
- ✅ Form should display with branch data pre-filled
- ✅ Form should have fields:
  - Name
  - Address
  - Phone
  - Gym capacity
  - Pool capacity
  - Lease expiry date
  - Commercial registration expiry
  - Active checkbox

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

### Test 2.2: Branch Edit - Legal Document Fields Save
**Priority:** BLOCKER
**Bug Fixed:** Issue #1.4 - Legal contract tracking
**Location:** `/admin/branches/<id>/edit`

**Steps:**
1. From Test 2.1, edit a branch
2. Set:
   - Lease expiry date: 30 days from today
   - Commercial registration expiry: 25 days from today
   - Gym capacity: 150
   - Pool capacity: 75
3. Click Save
4. Navigate away and come back to edit same branch

**Expected Result:**
- ✅ Success message: "تم تحديث الفرع بنجاح"
- ✅ All fields should persist with saved values
- ✅ Database check:

```sql
SELECT
    name,
    lease_expiry_date,
    commercial_registration_expiry,
    gym_capacity,
    pool_capacity
FROM branches
WHERE id = <branch_id>;
```

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

### Test 2.3: User Edit Button is Functional
**Priority:** BLOCKER
**Bug Fixed:** Issue #7.1 - User edit button was static
**Location:** `/admin/users/<id>/edit`

**Steps:**
1. Login as brand manager or owner
2. Navigate to Admin → Users
3. Click "Edit" (✏️) button on any user
4. Observe the page

**Expected Result:**
- ✅ Edit page should load (not static disabled button)
- ✅ Form should display with user data pre-filled
- ✅ Should be able to modify:
  - Name
  - Email
  - Phone
  - Role
  - Active status
- ✅ Password field should be optional

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

## 🟡 PHASE 3: DATA ISOLATION TESTS (Priority: HIGH)
**Estimated Time:** 20 minutes

### Test 3.1: Branch Accountant Sees Only Their Branch (Income)
**Priority:** HIGH
**Bug Fixed:** Issue #15.1 - Branch vs central accountant separation
**Location:** `/finance/income`

**Steps:**
1. Login as **branch accountant** (user with branch_id set)
2. Navigate to Finance → Income
3. Observe the list

**Expected Result:**
- ✅ Income list should show ONLY records from their branch
- ✅ Total amount should reflect ONLY their branch income
- ✅ Verify with query:

```sql
-- Get branch accountant's branch_id from their user record first
SELECT branch_id FROM users WHERE id = <accountant_user_id>;

-- Then check income displayed matches
SELECT COUNT(*), SUM(amount)
FROM income
WHERE branch_id = <accountant_branch_id>;
```

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

**Records Shown:** _______ records
**Total Shown:** _______ ر.س
**Database Count:** _______ records
**Database Total:** _______ ر.س

---

### Test 3.2: Central Accountant Sees All Branches in Brand
**Priority:** HIGH
**Bug Fixed:** Issue #15.1 - Central accountant access
**Location:** `/finance/income`

**Steps:**
1. Login as **central accountant** (user with brand_id but branch_id = NULL)
2. Navigate to Finance → Income
3. Observe the list

**Expected Result:**
- ✅ Income list should show records from ALL branches in their brand
- ✅ Should see records from multiple branches
- ✅ Verify with query:

```sql
-- Get central accountant's brand_id
SELECT brand_id FROM users WHERE id = <accountant_user_id>;

-- Check all branches in that brand
SELECT COUNT(*), SUM(amount)
FROM income
WHERE brand_id = <accountant_brand_id>;
```

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

### Test 3.3: Branch Accountant Sees Only Their Branch (Expenses)
**Priority:** HIGH
**Bug Fixed:** Issue #15.1 - Branch expense filtering
**Location:** `/finance/expenses`

**Steps:**
1. Login as **branch accountant**
2. Navigate to Finance → Expenses
3. Observe the list

**Expected Result:**
- ✅ Expense list should show ONLY records from their branch
- ✅ Verify same way as Test 3.1 using expenses table

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

### Test 3.4: Receptionist Dashboard Shows Only Branch Data
**Priority:** HIGH
**Bug Fixed:** Issue #12 - Receptionist dashboard discrepancy
**Location:** `/dashboard` (receptionist view)

**Steps:**
1. Login as **receptionist** (user with branch_id set)
2. View dashboard homepage
3. Note the statistics shown:
   - Today's attendance count
   - Active members count
   - Today's new subscriptions
   - Today's renewals

**Expected Result:**
- ✅ All counts should be for receptionist's branch ONLY
- ✅ Verify with queries:

```sql
-- Receptionist's branch
SELECT branch_id FROM users WHERE id = <receptionist_user_id>;

-- Today's attendance for that branch
SELECT COUNT(*) FROM member_attendance
WHERE branch_id = <receptionist_branch_id>
AND DATE(check_in) = CURDATE();

-- Active members in that branch
SELECT COUNT(*) FROM members
WHERE branch_id = <receptionist_branch_id>
AND is_active = 1;
```

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

**Dashboard Stats:**
- Attendance: _______
- Active Members: _______
- New Subscriptions: _______

**Database Stats:**
- Attendance: _______
- Active Members: _______

---

## 🟢 PHASE 4: DASHBOARD & ALERTS (Priority: MEDIUM)
**Estimated Time:** 25 minutes

### Test 4.1: Expiring Subscription Alert (48 Hours)
**Priority:** MEDIUM
**Bug Fixed:** Issue #1.1 - Wrong subscription date logic
**Location:** Owner dashboard `/dashboard`

**Steps:**
1. Create test subscription:
   - Start date: Today
   - End date: Tomorrow (1 day from now)
2. Login as owner
3. View dashboard
4. Check alerts section

**Expected Result:**
- ✅ Alert should appear: "X اشتراكات تنتهي خلال 48 ساعة"
- ✅ Should NOT show already expired subscriptions
- ✅ Verify with query:

```sql
-- Should match dashboard count
SELECT COUNT(*) FROM subscriptions
WHERE status = 'active'
AND end_date > CURDATE()
AND end_date <= DATE_ADD(CURDATE(), INTERVAL 2 DAY);
```

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

### Test 4.2: Employee Late Alert
**Priority:** MEDIUM
**Bug Fixed:** Issue #1.2 - Missing employee attendance alerts
**Location:** Owner dashboard

**Steps:**
1. Create employee attendance record:
   - Date: Today
   - Status: 'late'
   - Late minutes: 30
2. Refresh owner dashboard
3. Check alerts

**Expected Result:**
- ✅ Alert should appear: "X موظف متأخر اليوم (X دقيقة) - [names]"
- ✅ Should show late minutes total
- ✅ Should show employee names (up to 3)

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

### Test 4.3: Employee Absent Alert
**Priority:** MEDIUM
**Bug Fixed:** Issue #1.2 - Missing employee attendance alerts
**Location:** Owner dashboard

**Steps:**
1. Create employee attendance record:
   - Date: Today
   - Status: 'absent'
2. Refresh owner dashboard
3. Check alerts

**Expected Result:**
- ✅ Alert should appear: "X موظف غائب اليوم - [names]"
- ✅ Should show absent employee names

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

### Test 4.4: Revenue Anomaly Detection Alert
**Priority:** MEDIUM
**Bug Fixed:** Issue #1.3 - Revenue drop detection
**Location:** Owner dashboard

**Steps:**
1. **Setup baseline revenue:**
   - Create income records for past 4 weeks (days 8-35 ago)
   - Total: 10,000 ر.س per week (40,000 total for 4 weeks)
2. **Create current week drop:**
   - Create income for last 7 days
   - Total: Only 6,000 ر.س (40% drop from 10,000 baseline)
3. Refresh owner dashboard

**Expected Result:**
- ✅ Alert should appear: "انخفاض الإيرادات في [Brand Name] بنسبة X% هذا الأسبوع"
- ✅ Drop percentage should be around 40%
- ✅ Alert should only appear if drop ≥ 20%

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

**Note:** This test requires creating past income records. You can skip if too complex.

---

### Test 4.5: Lease Expiry Alert
**Priority:** MEDIUM
**Bug Fixed:** Issue #1.4 - Legal contract alerts
**Location:** Owner dashboard

**Steps:**
1. Edit a branch (from Test 2.2)
2. Set lease_expiry_date to 20 days from today
3. Save
4. Refresh owner dashboard
5. Check alerts

**Expected Result:**
- ✅ Alert should appear: "X عقد إيجار ينتهي خلال 30 يوم - [branch names]"
- ✅ Should list branch names (up to 3)

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

### Test 4.6: Commercial Registration Expiry Alert
**Priority:** MEDIUM
**Bug Fixed:** Issue #1.4 - Legal contract alerts
**Location:** Owner dashboard

**Steps:**
1. Edit a branch
2. Set commercial_registration_expiry to 15 days from today
3. Save
4. Refresh owner dashboard
5. Check alerts

**Expected Result:**
- ✅ Alert should appear: "X سجل تجاري ينتهي خلال 30 يوم - [branch names]"
- ✅ Should be separate alert from lease expiry
- ✅ Should use danger (red) styling

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

### Test 4.7: Clickable Brand Names in Dashboard
**Priority:** MEDIUM
**Bug Fixed:** Issue #3.1 - Brand navigation
**Location:** Owner dashboard brand list

**Steps:**
1. Login as owner
2. View dashboard
3. Look for brand name in the brand performance table
4. Click on brand name

**Expected Result:**
- ✅ Brand name should be a clickable link (blue, underlined on hover)
- ✅ Should navigate to `/admin/branches?brand_id=X`
- ✅ Should show that brand's branches

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

## 🔵 PHASE 5: REPORTS & ANALYTICS (Priority: MEDIUM)
**Estimated Time:** 20 minutes

### Test 5.1: Financial Report - Payment Method Breakdown
**Priority:** MEDIUM
**Bug Fixed:** Issue #17.4 - Payment method reporting
**Location:** `/reports/financial`

**Steps:**
1. Ensure you have income records with different payment methods:
   - Some with payment_method = 'cash'
   - Some with payment_method = 'card'
   - Some with payment_method = 'transfer'
2. Navigate to Reports → Financial Report
3. Select date range covering those income records
4. View report

**Expected Result:**
- ✅ Report should show section "توزيع طرق الدفع" or similar
- ✅ Should show breakdown:
  - كاش: X ر.س
  - بطاقة: X ر.س
  - حوالة: X ر.س
- ✅ Totals should match overall income

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

### Test 5.2: Financial Report - Service Type Breakdown
**Priority:** MEDIUM
**Bug Fixed:** Issue #17.4 - Service type reporting
**Location:** `/reports/financial`

**Steps:**
1. Ensure you have income records with different service types
2. View financial report (same as Test 5.1)
3. Look for service type breakdown section

**Expected Result:**
- ✅ Report should show section "الإيرادات حسب نوع الخدمة" or similar
- ✅ Should show breakdown by service:
  - جيم: X ر.س
  - سباحة: X ر.س
  - كاراتيه: X ر.س
  - etc.
- ✅ Should show subscription count for each service

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

### Test 5.3: Financial Report - Multi-Branch Comparison
**Priority:** MEDIUM
**Bug Fixed:** Issue #17.5 - Branch comparison feature
**Location:** `/reports/financial`

**Steps:**
1. Navigate to Financial Report
2. Look for "مقارنة الفروع" checkbox or similar
3. Enable branch comparison
4. View report

**Expected Result:**
- ✅ Report should show separate section for branch breakdown
- ✅ Should show table with columns:
  - Branch name
  - Income
  - Expenses
  - Profit
- ✅ Should show all branches in the selected brand
- ✅ Each branch's numbers should be separate

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

### Test 5.4: Expense Attribution - User & Branch Tracking
**Priority:** MEDIUM
**Bug Fixed:** Issue #16.1 - Expense attribution
**Location:** `/finance/expenses/create`

**Steps:**
1. Login as accountant
2. Navigate to Finance → Expenses → Create New
3. Fill form:
   - Category: إيجار
   - Amount: 5000
   - Description: test expense
   - Date: Today
4. Submit
5. View expense list
6. Check database:

```sql
SELECT
    id,
    category_name,
    amount,
    created_by,
    branch_id,
    brand_id
FROM expenses
ORDER BY created_at DESC
LIMIT 1;
```

**Expected Result:**
- ✅ Expense list should show creator's name
- ✅ `created_by` should be current user's ID
- ✅ `branch_id` should match user's branch (if they have one)
- ✅ Expense row should show "المنشئ: [User Name]"

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

### Test 5.5: Expense Filtering - Category Filter
**Priority:** MEDIUM
**Bug Fixed:** Issue #16.3 - Advanced expense filtering
**Location:** `/finance/expenses`

**Steps:**
1. Navigate to Finance → Expenses
2. Look for filter options
3. Select category filter: "إيجار"
4. Apply filter

**Expected Result:**
- ✅ Should show ONLY expenses with category = "إيجار"
- ✅ Other categories should be hidden
- ✅ Count should update

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

### Test 5.6: Expense Filtering - User Filter
**Priority:** MEDIUM
**Bug Fixed:** Issue #16.3 - User filtering
**Location:** `/finance/expenses`

**Steps:**
1. Navigate to Finance → Expenses
2. Select user filter dropdown
3. Choose a specific user
4. Apply filter

**Expected Result:**
- ✅ Should show ONLY expenses created by that user
- ✅ Dropdown should show all users in the brand

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

### Test 5.7: Expense Filtering - Branch Filter (Central Accountant)
**Priority:** MEDIUM
**Bug Fixed:** Issue #16.3 - Branch filtering
**Location:** `/finance/expenses`

**Steps:**
1. Login as **central accountant** (no branch_id)
2. Navigate to Finance → Expenses
3. Look for branch filter dropdown
4. Select a specific branch
5. Apply filter

**Expected Result:**
- ✅ Branch filter dropdown should be visible for central accountants
- ✅ Should show ONLY expenses from selected branch
- ✅ Branch accountants should NOT see this filter (only their branch automatically)

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

## 🟣 PHASE 6: UI/UX FEATURES (Priority: LOW)
**Estimated Time:** 15 minutes

### Test 6.1: Service Type Dropdown Filters Plans
**Priority:** LOW
**Bug Fixed:** Issue #9.1 - Service type selection
**Location:** `/subscriptions/create`

**Steps:**
1. Navigate to create subscription for a member
2. Observe the service type dropdown at top of form
3. Select service type: "جيم"
4. Observe plan list below

**Expected Result:**
- ✅ Service type dropdown should be visible
- ✅ After selecting service type, plans should filter
- ✅ Should show ONLY plans with matching service type
- ✅ Plans with no service type should always show
- ✅ Selecting "الكل" (all) should show all plans

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

### Test 6.2: Plan Cards Show Service Type
**Priority:** LOW
**Bug Fixed:** Issue #9.1 - Service type display
**Location:** `/subscriptions/create`

**Steps:**
1. On same create subscription page
2. Observe plan cards/options
3. Look for service type indicator

**Expected Result:**
- ✅ Each plan card should show service type icon
- ✅ Should display: 🏆 [Service Type Name]
- ✅ Example: "🏆 جيم" or "🏊 سباحة"

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

### Test 6.3: Invoice Generation & Display
**Priority:** LOW
**Bug Fixed:** Issue #10.3 - Invoice generation
**Location:** `/subscriptions/<id>/invoice`

**Steps:**
1. Navigate to any subscription view page
2. Look for "Generate Invoice" or "طباعة فاتورة" button
3. Click it
4. Observe invoice page

**Expected Result:**
- ✅ Invoice page should load successfully
- ✅ Should show:
  - Brand name as header
  - Invoice number (subscription ID)
  - Member information
  - Subscription details (plan, dates, service type)
  - Payment breakdown table:
    - Plan price
    - Discount (if any)
    - Offer discount (if any)
    - Gift card amount (if any)
    - Total
    - Paid amount
    - Remaining (if any)
  - Payment history table
  - Print button at bottom

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

### Test 6.4: Invoice Print Functionality
**Priority:** LOW
**Bug Fixed:** Issue #10.3 - Invoice printing
**Location:** Same invoice page

**Steps:**
1. On invoice page from Test 6.3
2. Click "طباعة" (Print) button
3. Observe print preview

**Expected Result:**
- ✅ Browser print dialog should open
- ✅ Print preview should show invoice
- ✅ Print button should be hidden in preview
- ✅ Navigation elements should be hidden (@media print)

**Actual Result:**
- [ ] PASS ✅
- [ ] FAIL ❌ (Note: _________________)

---

## 📊 TEST RESULTS SUMMARY

### Test Execution Summary
**Date Tested:** _______________
**Tested By:** _______________

| Phase | Total Tests | Passed ✅ | Failed ❌ | Skipped ⏭️ |
|-------|-------------|----------|----------|-----------|
| Phase 1: Critical | 7 | ___ | ___ | ___ |
| Phase 2: Blocker | 3 | ___ | ___ | ___ |
| Phase 3: Data Isolation | 4 | ___ | ___ | ___ |
| Phase 4: Dashboard | 7 | ___ | ___ | ___ |
| Phase 5: Reports | 7 | ___ | ___ | ___ |
| Phase 6: UI/UX | 4 | ___ | ___ | ___ |
| **TOTAL** | **32** | **___** | **___** | **___** |

### Pass Rate
**Overall Pass Rate:** _____ %

### Critical Issues Found
List any CRITICAL or BLOCKER tests that failed:

1. _______________________________________________
2. _______________________________________________
3. _______________________________________________

### Bugs Found During Testing
List any new bugs discovered:

1. _______________________________________________
2. _______________________________________________
3. _______________________________________________

---

## 🔧 Quick Reference: Useful Queries

### Check User Roles & Branches
```sql
SELECT
    u.id,
    u.name,
    u.email,
    r.name as role,
    b.name as brand,
    br.name as branch
FROM users u
LEFT JOIN roles r ON u.role_id = r.id
LEFT JOIN brands b ON u.brand_id = b.id
LEFT JOIN branches br ON u.branch_id = br.id
WHERE u.is_active = 1;
```

### Check Recent Subscriptions
```sql
SELECT
    s.id,
    m.name as member,
    p.name as plan,
    st.name as service_type,
    s.status,
    s.start_date,
    s.end_date,
    s.created_at
FROM subscriptions s
JOIN members m ON s.member_id = m.id
JOIN plans p ON s.plan_id = p.id
LEFT JOIN service_types st ON s.service_type_id = st.id
ORDER BY s.created_at DESC
LIMIT 10;
```

### Check Income Records with Full Details
```sql
SELECT
    i.id,
    i.date,
    i.amount,
    i.payment_method,
    i.type,
    b.name as brand,
    br.name as branch,
    st.name as service_type,
    m.name as member,
    u.name as created_by
FROM income i
LEFT JOIN brands b ON i.brand_id = b.id
LEFT JOIN branches br ON i.branch_id = br.id
LEFT JOIN service_types st ON i.service_type_id = st.id
LEFT JOIN subscriptions s ON i.subscription_id = s.id
LEFT JOIN members m ON s.member_id = m.id
LEFT JOIN users u ON i.created_by = u.id
ORDER BY i.created_at DESC
LIMIT 20;
```

### Check DeviceCommand Records
```sql
SELECT
    dc.id,
    dc.command_type,
    dc.target_emp_id,
    m.name as member,
    dc.status,
    dc.command_data,
    dc.created_at,
    dc.executed_at
FROM device_commands dc
LEFT JOIN members m ON dc.member_id = m.id
ORDER BY dc.created_at DESC
LIMIT 10;
```

### Check Branch Legal Document Expiries
```sql
SELECT
    br.name as branch,
    b.name as brand,
    br.lease_expiry_date,
    DATEDIFF(br.lease_expiry_date, CURDATE()) as lease_days_remaining,
    br.commercial_registration_expiry,
    DATEDIFF(br.commercial_registration_expiry, CURDATE()) as registration_days_remaining
FROM branches br
JOIN brands b ON br.brand_id = b.id
WHERE br.is_active = 1
AND (
    br.lease_expiry_date IS NOT NULL
    OR br.commercial_registration_expiry IS NOT NULL
);
```

---

## 📝 Notes Section

### Testing Environment Details
- Database: _______________
- Server: _______________
- Browser: _______________
- Date: _______________

### Additional Observations
_______________________________________
_______________________________________
_______________________________________
_______________________________________
_______________________________________

### Recommendations
_______________________________________
_______________________________________
_______________________________________
_______________________________________

---

**End of Testing Plan**
