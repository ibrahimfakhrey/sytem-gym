# Bug Investigation Plan - Gym Management System
**Tester:** Aya Mohamed Farouk
**Date Created:** 2026-01-31
**Status:** Investigation Phase

---

## CRITICAL ISSUES (Blockers)

### 1. Owner Dashboard - Smart Notifications

#### Issue 1.1: Wrong Logic - "Expiring Soon" showing "Already Expired"
- **Route:** `/` (Owner Dashboard)
- **Expected:** Show subscriptions expiring in 48h and 7 days
- **Actual:** Shows already expired subscriptions
- **Investigation:**
  - [ ] Check dashboard route logic in `app/routes/dashboard.py`
  - [ ] Review subscription expiry query/filter logic
  - [ ] Verify date comparison logic (should be future dates, not past)

#### Issue 1.2: Employee Attendance Alerts Not Showing
- **Route:** `/` (Owner Dashboard)
- **Expected:** Show late/absent employee alerts with branch details
- **Actual:** Data calculated correctly but not pushed to notifications panel
- **Investigation:**
  - [ ] Check employee attendance calculation in `app/routes/employees.py`
  - [ ] Verify notification integration in owner dashboard
  - [ ] Look for missing data pipeline between attendance module and dashboard

#### Issue 1.3: Missing Revenue Anomaly Detection
- **Expected:** Alert when branch revenue drops below normal
- **Actual:** No alerts or indicators for revenue comparison
- **Investigation:**
  - [ ] Check if revenue anomaly logic exists
  - [ ] Review historical revenue tracking/averaging
  - [ ] Verify alert system for revenue drops

#### Issue 1.4: Missing Legal/Administrative Alerts
- **Expected:** Alerts for expiring contracts, leases, commercial registrations
- **Actual:** Feature completely missing
- **Investigation:**
  - [ ] Check if legal/administrative module exists in database
  - [ ] Verify if there's any contract/lease tracking functionality

---

### 2. Owner Dashboard - Revenue Summary

#### Issue 2.1: Missing Service Demand Analytics
- **Route:** `/` (Owner Dashboard)
- **Expected:** Show top/bottom services (karate vs swimming, etc.)
- **Actual:** No service-level performance analytics
- **Investigation:**
  - [ ] Check dashboard charts/cards for service analytics
  - [ ] Verify if service performance data is calculated
  - [ ] Look for missing visualization components

#### Issue 2.2: Missing Service Type Filter
- **Route:** `/finance/income` or `/reports/financial`
- **Expected:** Filter by service type (gym/pool/karate/salon)
- **Actual:** Only branch/date filters available
- **Investigation:**
  - [ ] Check filter options in revenue/income routes
  - [ ] Verify service_type field in income records
  - [ ] Look for missing dropdown/filter UI component

---

### 3. Owner Dashboard - Branch Drill Down

#### Issue 3.1: [CRITICAL] Non-Functional Branch Navigation
- **Route:** `/` (Owner Dashboard)
- **Expected:** Click on branch to navigate to branch details
- **Actual:** Branch cards/names are static text, not interactive links
- **Investigation:**
  - [ ] Check branch card HTML/template for click handlers
  - [ ] Verify if branch detail routes exist
  - [ ] Look for missing event listeners or hyperlinks

#### Issue 3.2: [CRITICAL] Missing Branch-Specific Dashboard
- **Expected:** Owner can view branch dashboard with manager-level access
- **Actual:** No navigation mechanism to branch subdashboard
- **Investigation:**
  - [ ] Check if branch dashboard route exists for owner
  - [ ] Verify permission logic for owner accessing branch data
  - [ ] Look for missing branch detail aggregation

#### Issue 3.3: Missing Granular Branch Data
- **Expected:** Fingerprint stats, complaints, pool revenue breakdown
- **Actual:** Data not linked to owner's view
- **Investigation:**
  - [ ] Check integration between attendance/complaints and owner dashboard
  - [ ] Verify data pipeline for branch-level operational data
  - [ ] Look for missing queries in owner dashboard route

---

### 4. Owner Dashboard - Staff Performance Evaluation

#### Issue 4.1: [CRITICAL] No Staff Ranking System
- **Expected:** Staff performance ranking by revenue/retention
- **Actual:** No UI or logic for staff evaluation
- **Investigation:**
  - [ ] Check if staff performance module exists
  - [ ] Verify if there's any BI/analytics for staff ranking
  - [ ] Look for missing aggregation queries

#### Issue 4.2: Missing Revenue-Staff Attribution
- **Expected:** Link revenue to responsible staff member
- **Actual:** Data is separated - no relational link
- **Investigation:**
  - [ ] Check subscription/income model for staff attribution
  - [ ] Verify if created_by or receptionist_id fields exist
  - [ ] Look for missing foreign key relationships

---

### 5. Owner Dashboard - Financial Intelligence

#### Issue 5.1: [CRITICAL] No Gift Card Analytics
- **Route:** `/finance` or `/reports/financial`
- **Expected:** Gift card ROI and net profit analysis
- **Actual:** No dedicated analytics for gift cards
- **Investigation:**
  - [ ] Check gift card redemption tracking
  - [ ] Verify financial reports include gift card metrics
  - [ ] Look for missing gift card analytics module

#### Issue 5.2: Missing Payment Method Breakdown
- **Expected:** Consolidated view of payment methods across branches
- **Actual:** Only aggregate numbers, no method breakdown
- **Investigation:**
  - [ ] Check income records for payment_method field
  - [ ] Verify dashboard displays payment distribution
  - [ ] Look for missing payment analytics visualization

#### Issue 5.3: Biometric Attendance Not Integrated in Owner View
- **Expected:** Owner sees real-time fingerprint attendance per branch
- **Actual:** Manual entry or separate logs, no live integration
- **Investigation:**
  - [ ] Check fingerprint sync with branch dashboard
  - [ ] Verify attendance source in owner's branch view
  - [ ] Look for missing biometric data pipeline

---

### 6. Owner Dashboard - Subscription Monitoring

#### Issue 6.1: [CRITICAL] No Subscription Status Categorization
- **Expected:** Breakdown of new/renewal/stopped subscriptions
- **Actual:** No accurate categorization or reason tracking
- **Investigation:**
  - [ ] Check subscription status tracking in database
  - [ ] Verify if stop_reason field exists and is populated
  - [ ] Look for missing subscription segmentation logic

#### Issue 6.2: [BLOCKER] No Automated Biometric Lock
- **Expected:** Automatically disable fingerprint access when subscription stopped
- **Actual:** No automated trigger between database and fingerprint device
- **Investigation:**
  - [ ] Check subscription status change hooks
  - [ ] Verify fingerprint device integration for auto-lock
  - [ ] Look for missing hardware-software automation

---

### 7. System Administration - User Management

#### Issue 7.1: [CRITICAL] Non-Functional User Edit Button
- **Route:** `/admin/users`
- **Expected:** Edit icon opens user edit form
- **Actual:** Edit button is static, no event listener
- **Investigation:**
  - [ ] Check user management template for edit links
  - [ ] Verify edit route exists (`/admin/users/<user_id>/edit`)
  - [ ] Look for missing JavaScript event handlers

---

### 8. Admin Panel - Brand & Branch Management

#### Issue 8.1: [CRITICAL] System Crash on "Add Location"
- **Route:** `/admin/brands` → Add Location action
- **Expected:** Add location without system failure
- **Actual:** 500 Internal Server Error, complete system crash
- **Investigation:**
  - [ ] Check server logs for 500 error details
  - [ ] Verify location/branch creation route
  - [ ] Look for database schema issues or null pointer exceptions
  - [ ] Test the add location functionality

#### Issue 8.2: Non-Functional Management Icons
- **Route:** `/admin/brands`
- **Expected:** Edit, location, user management icons work
- **Actual:** Icons either unresponsive or crash system
- **Investigation:**
  - [ ] Check action button links in brand management table
  - [ ] Verify all management routes exist and are stable
  - [ ] Look for broken UI/UX links

---

## HIGH PRIORITY ISSUES

### 9. Receptionist Journey - Subscription Selection

#### Issue 9.1: [CRITICAL] Missing Activity-Based Classification
- **Route:** `/subscriptions/create`
- **Expected:** Select subscription by activity (gym/swimming/karate)
- **Actual:** Only duration-based plans (monthly/quarterly/annual)
- **Investigation:**
  - [ ] Check subscription plan model for service_type field
  - [ ] Verify plan selection UI includes activity categorization
  - [ ] Look for missing service category logic

#### Issue 9.2: Missing Session-Based Logic
- **Expected:** Show number of sessions for educational tracks
- **Actual:** Only shows days and freeze count
- **Investigation:**
  - [ ] Check subscription/plan model for session fields
  - [ ] Verify session tracking functionality
  - [ ] Look for missing session-based subscription attributes

#### Issue 9.3: Static Subscription Pricing
- **Expected:** Dynamic pricing based on selected activity
- **Actual:** Hardcoded flat list of plans
- **Investigation:**
  - [ ] Check plan selection logic in subscription creation
  - [ ] Verify if plans are filtered by service type
  - [ ] Look for missing dynamic filtering

---

### 10. Receptionist Journey - Payment Integration

#### Issue 10.1: [CRITICAL] Missing Payment Method Selection
- **Route:** `/subscriptions/create`
- **Expected:** Must select payment method (cash/card/transfer)
- **Actual:** No payment method field, subscription activates without payment
- **Investigation:**
  - [ ] Check subscription creation form for payment_method field
  - [ ] Verify payment validation before activation
  - [ ] Look for financial security vulnerability

#### Issue 10.2: Missing Financial Attribution
- **Expected:** Link transaction to branch, service, staff, payment method
- **Actual:** No financial transaction log created
- **Investigation:**
  - [ ] Check if Income record is created with subscription
  - [ ] Verify relational links in database schema
  - [ ] Look for missing financial traceability

#### Issue 10.3: No Invoice Generation
- **Expected:** Print/send invoice after payment
- **Actual:** No billing module triggered
- **Investigation:**
  - [ ] Check for invoice generation logic
  - [ ] Verify if invoice/receipt printing exists
  - [ ] Look for missing billing module

---

### 11. Receptionist Journey - Subscription Renewal

#### Issue 11.1: [CRITICAL] No Payment Integration in Renewal
- **Route:** `/subscriptions/<sub_id>/renew`
- **Expected:** Select payment method before renewal
- **Actual:** Renewal extends date without financial validation
- **Investigation:**
  - [ ] Check renewal route for payment method field
  - [ ] Verify financial transaction creation on renewal
  - [ ] Look for massive financial fraud loophole

#### Issue 11.2: Missing Financial Transaction Logging
- **Expected:** Create new income record for renewal
- **Actual:** No financial record linked to renewal
- **Investigation:**
  - [ ] Check if renewal creates Income entry
  - [ ] Verify transaction_id linking
  - [ ] Look for missing revenue tracking for renewals

#### Issue 11.3: No Expiring Subscription Alerts
- **Expected:** Proactive alerts for subscriptions expiring in 48h
- **Actual:** No smart notifications in receptionist view
- **Investigation:**
  - [ ] Check receptionist dashboard for expiry alerts
  - [ ] Verify notification engine for expiry threshold
  - [ ] Look for missing alert automation

---

### 12. Receptionist Journey - Attendance & Access Control

#### Issue 12.1: [CRITICAL] Manual Attendance Bypass
- **Route:** `/attendance`
- **Expected:** Rely completely on fingerprint for attendance
- **Actual:** All attendance shown as "Manual" source
- **Investigation:**
  - [ ] Check attendance table for source field values
  - [ ] Verify fingerprint integration and data sync
  - [ ] Look for biometric hardware integration failure

#### Issue 12.2: Dashboard Data Discrepancy
- **Expected:** Dashboard shows real-time attendance numbers
- **Actual:** Dashboard shows "No attendance today" despite 3 records
- **Investigation:**
  - [ ] Check dashboard widget query for attendance
  - [ ] Verify data sync between attendance table and dashboard
  - [ ] Look for internal data mismatch

#### Issue 12.3: No Subscription Validation on Check-in
- **Expected:** Search validates subscription status before check-in
- **Actual:** Manual entry allows check-in without validation
- **Investigation:**
  - [ ] Check attendance check-in logic
  - [ ] Verify subscription status validation
  - [ ] Look for missing real-time validation

---

### 13. Receptionist Journey - Rejection Handling

#### Issue 13.1: Missing Rejection Reason Tracking
- **Route:** Should appear when renewal is declined
- **Expected:** Popup to log rejection reason (price/time/service/personal)
- **Actual:** No rejection tracking field or popup
- **Investigation:**
  - [ ] Check if rejection reason field exists
  - [ ] Verify CRM module for lost opportunity tracking
  - [ ] Look for missing customer feedback module

#### Issue 13.2: No Integration with Owner Dashboard
- **Expected:** Rejection reports visible to owner
- **Actual:** No data pipeline for rejection metrics
- **Investigation:**
  - [ ] Check if rejection data flows to owner reports
  - [ ] Verify churn analysis functionality
  - [ ] Look for missing reporting integration

---

### 14. Operations & Control

#### Issue 14.1: [CRITICAL] No Suspension & Access Control
- **Expected:** Stop subscription → lock fingerprint → prevent entry
- **Actual:** No automated link between subscription status and biometric
- **Investigation:**
  - [ ] Check subscription stop/suspend logic
  - [ ] Verify automated fingerprint lockout trigger
  - [ ] Look for critical security risk

#### Issue 14.2: [BLOCKER] No Daily Financial Closing
- **Expected:** Receptionist performs end-of-day cash reconciliation
- **Actual:** Feature completely missing
- **Investigation:**
  - [ ] Check if daily closing module exists
  - [ ] Verify cash reconciliation functionality
  - [ ] Look for missing financial audit module

#### Issue 14.3: Missing Booking & Complaints
- **Expected:** Class booking and complaint ticketing system
- **Actual:** Features not implemented
- **Investigation:**
  - [ ] Verify if `/classes` booking routes exist
  - [ ] Check if `/complaints` module is functional
  - [ ] Look for incomplete functional requirements

---

### 15. Accountant Journey - Role Permissions

#### Issue 15.1: [CRITICAL] No Branch vs Central Accountant Separation
- **Route:** `/finance/*`
- **Expected:** Branch accountant sees only their branch, central sees all
- **Actual:** No scope filtering by role
- **Investigation:**
  - [ ] Check accountant role permissions
  - [ ] Verify branch filtering logic
  - [ ] Look for security/privacy violation

#### Issue 15.2: [BLOCKER] Missing Sales Transaction Metadata
- **Route:** `/finance/income`
- **Expected:** Filter by service type, payment method, staff, branch
- **Actual:** No payment_method or service_type columns in transactions
- **Investigation:**
  - [ ] Check income table schema for missing fields
  - [ ] Verify transaction metadata capture
  - [ ] Look for critical data attribution gap

#### Issue 15.3: Missing Daily Closing Audit Flow
- **Expected:** Accountant reviews daily closings and flags discrepancies
- **Actual:** No daily closing review interface
- **Investigation:**
  - [ ] Check if daily closing approval workflow exists
  - [ ] Verify accountant access to closing records
  - [ ] Look for broken audit trail

#### Issue 15.4: No Centralized Comparative Reports
- **Expected:** Compare branch performance in single report
- **Actual:** No reporting engine for cross-branch comparison
- **Investigation:**
  - [ ] Check reporting module capabilities
  - [ ] Verify multi-branch aggregation
  - [ ] Look for missing analytics tools

---

### 16. Accountant Journey - Expense Management

#### Issue 16.1: [CRITICAL] Missing Expense Attribution
- **Route:** `/finance/expenses`
- **Expected:** Show user who created expense and branch
- **Actual:** Only date, category, description, amount
- **Investigation:**
  - [ ] Check expense table for user_id and branch_id fields
  - [ ] Verify expense UI displays attribution
  - [ ] Look for missing relational data

#### Issue 16.2: No Approval Workflow
- **Expected:** Expenses require owner/manager approval
- **Actual:** Expenses directly added without approval status
- **Investigation:**
  - [ ] Check for expense status field (pending/approved/rejected)
  - [ ] Verify approval workflow logic
  - [ ] Look for authorization bypass vulnerability

#### Issue 16.3: Limited Filtering
- **Expected:** Filter expenses by branch, user, category
- **Actual:** Only date range filter
- **Investigation:**
  - [ ] Check expense filter options
  - [ ] Verify query parameter support
  - [ ] Look for missing filter UI

---

### 17. Accountant Journey - Daily Closing & Reports

#### Issue 17.1: [CRITICAL] No Daily Closing Interface
- **Route:** Should be in accountant dashboard
- **Expected:** Match actual cash with system cash, approve closing
- **Actual:** No interface for cash reconciliation
- **Investigation:**
  - [ ] Check if daily closing routes exist
  - [ ] Verify cash reconciliation module
  - [ ] Look for critical financial accountability gap

#### Issue 17.2: [CRITICAL] No Centralized Audit Dashboard
- **Expected:** Central accountant sees all branch closing statuses
- **Actual:** No tracking for which branches closed/have discrepancies
- **Investigation:**
  - [ ] Check central accountant dashboard
  - [ ] Verify multi-branch closing overview
  - [ ] Look for missing centralized audit system

#### Issue 17.3: Missing Variance Logging
- **Expected:** Log unjustified cash differences
- **Actual:** No variance tracking table
- **Investigation:**
  - [ ] Check if cash variance logging exists
  - [ ] Verify discrepancy investigation workflow
  - [ ] Look for missing audit trail

#### Issue 17.4: Incomplete Reporting Granularity
- **Route:** `/reports/financial`
- **Expected:** Break down revenue by service type and payment method
- **Actual:** Only aggregate totals (revenue, expenses, profit)
- **Investigation:**
  - [ ] Check report generation logic
  - [ ] Verify GROUP BY service/payment method queries
  - [ ] Look for missing data breakdown

#### Issue 17.5: No Multi-Branch Comparison
- **Expected:** Select all branches for comparative reports
- **Actual:** Only current branch data shown
- **Investigation:**
  - [ ] Check report filtering options
  - [ ] Verify cross-branch aggregation
  - [ ] Look for missing comparative analysis

#### Issue 17.6: Dashboard Data Inconsistency
- **Expected:** Accurate real-time financial data
- **Actual:** Dashboard shows "no attendance" while income shows transactions
- **Investigation:**
  - [ ] Check dashboard widget data sources
  - [ ] Verify data sync anomaly
  - [ ] Look for query inconsistencies

---

## INVESTIGATION METHODOLOGY

For each issue, we will:
1. **Read the relevant route file(s)**
2. **Check the database models** for required fields
3. **Verify template/UI components** for missing elements
4. **Test the functionality** if accessible
5. **Document findings** (Bug Confirmed / Works as Expected / Partially Implemented)
6. **Propose fix** if bug is confirmed

---

## PRIORITY LEVELS

- **[CRITICAL/BLOCKER]**: System crash, security vulnerability, financial fraud risk
- **[MAJOR]**: Missing core functionality, broken user journey
- **[MINOR]**: UI inconsistency, missing convenience feature

---

## NEXT STEPS

1. Review this plan with user
2. Begin systematic investigation starting with CRITICAL issues
3. For each confirmed bug, decide: Fix now or document for batch fix
4. Generate final bug confirmation report

---

**Investigation Start Date:** 2026-01-31
**Estimated Investigation Time:** Multiple sessions (17 major issue categories, ~50+ individual issues)
