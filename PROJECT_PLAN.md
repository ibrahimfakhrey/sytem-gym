# خطة مشروع نظام إدارة الجيم متعدد البراندات
## Multi-Brand Gym Management System - Complete Project Plan

---

## 1. نظرة عامة على المشروع (Project Overview)

### 1.1 الهدف
بناء نظام ويب متكامل لإدارة براندات جيم متعددة داخل شركة واحدة، مع:
- فصل كامل للبيانات بين البراندات
- تكامل مع نظام البصمة (AAS) لأحد البراندات
- واجهة مستخدم عربية
- استضافة سحابية (Railway/Render)

### 1.2 المتطلبات الأساسية
| المتطلب | التفاصيل |
|---------|----------|
| اللغة | العربية فقط (RTL) |
| الدفع | نقدي فقط (بدون بوابة دفع) |
| البصمة | براند واحد فقط (الأجهزة مركبة) |
| التقارير | تصدير Excel و PDF |
| الاستضافة | Railway أو Render |

---

## 2. التقنيات المستخدمة (Tech Stack)

### 2.1 Backend
```
- Python 3.11+
- Flask 3.x
- Flask-SQLAlchemy (ORM)
- Flask-Login (Authentication)
- Flask-Migrate (Database migrations)
- Flask-WTF (Forms)
- Werkzeug (Password hashing)
```

### 2.2 Database
```
- PostgreSQL (Production - Cloud)
- SQLite (Development - Local)
```

### 2.3 Frontend
```
- HTML5
- CSS3 (RTL Support)
- Jinja2 Templates
- Bootstrap 5 (RTL version)
- Chart.js (للرسوم البيانية)
```

### 2.4 Export & Reports
```
- openpyxl (Excel export)
- ReportLab أو WeasyPrint (PDF export)
```

### 2.5 Fingerprint Integration
```
- Python socket (TCP/IP communication)
- Local Bridge Service (Windows)
- REST API (sync with cloud)
```

---

## 3. هيكل قاعدة البيانات (Database Schema)

### 3.1 ERD Diagram
```
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│  companies  │───1:N─│   brands    │───1:N─│  branches   │
└─────────────┘       └─────────────┘       └─────────────┘
                            │
            ┌───────────────┼───────────────┐
            │               │               │
            ▼               ▼               ▼
      ┌──────────┐    ┌──────────┐    ┌──────────┐
      │  users   │    │ members  │    │  plans   │
      └──────────┘    └──────────┘    └──────────┘
            │               │               │
            │               └───────┬───────┘
            │                       ▼
            │              ┌──────────────────┐
            │              │  subscriptions   │
            │              └──────────────────┘
            │                       │
            ▼                       ▼
    ┌───────────────┐      ┌───────────────┐
    │ employee_     │      │ member_       │
    │ attendance    │      │ attendance    │
    └───────────────┘      └───────────────┘
            │                       │
            └───────────┬───────────┘
                        ▼
              ┌─────────────────┐
              │    finance      │
              │ (income/expense/│
              │  salary/refund) │
              └─────────────────┘
```

### 3.2 تفاصيل الجداول

#### 3.2.1 companies (الشركات)
```sql
CREATE TABLE companies (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active       BOOLEAN DEFAULT TRUE
);
```

#### 3.2.2 brands (البراندات)
```sql
CREATE TABLE brands (
    id                  SERIAL PRIMARY KEY,
    company_id          INTEGER REFERENCES companies(id),
    name                VARCHAR(100) NOT NULL,
    logo                VARCHAR(255),           -- مسار الصورة
    uses_fingerprint    BOOLEAN DEFAULT FALSE,  -- هل يستخدم البصمة
    fingerprint_ip      VARCHAR(15),            -- IP جهاز البصمة
    fingerprint_port    INTEGER DEFAULT 5005,   -- Port جهاز البصمة
    is_active           BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 3.2.3 branches (الفروع)
```sql
CREATE TABLE branches (
    id          SERIAL PRIMARY KEY,
    brand_id    INTEGER REFERENCES brands(id),
    name        VARCHAR(100) NOT NULL,
    address     TEXT,
    phone       VARCHAR(20),
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 3.2.4 roles (الأدوار)
```sql
CREATE TABLE roles (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(50) NOT NULL UNIQUE,
    name_ar     VARCHAR(50) NOT NULL,           -- الاسم بالعربية
    description TEXT
);

-- البيانات الافتراضية
INSERT INTO roles (name, name_ar, description) VALUES
('owner', 'المالك', 'صلاحية كاملة على جميع البراندات'),
('receptionist', 'موظف استقبال', 'إدارة العملاء والاشتراكات'),
('finance', 'مالية براند', 'إدارة مالية براند واحد'),
('finance_admin', 'مالية عامة', 'الاطلاع على مالية جميع البراندات'),
('manager', 'مدير', 'إدارة فرع أو براند'),
('coach', 'مدرب', 'الاطلاع على بيانات شخصية فقط');
```

#### 3.2.5 users (المستخدمين)
```sql
CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    brand_id        INTEGER REFERENCES brands(id),      -- NULL للـ owner و finance_admin
    branch_id       INTEGER REFERENCES branches(id),    -- اختياري
    role_id         INTEGER REFERENCES roles(id) NOT NULL,
    name            VARCHAR(100) NOT NULL,
    email           VARCHAR(100) UNIQUE NOT NULL,
    phone           VARCHAR(20),
    password_hash   VARCHAR(255) NOT NULL,
    salary_type     VARCHAR(10) CHECK (salary_type IN ('fixed', 'daily')),
    salary_amount   DECIMAL(10,2),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login      TIMESTAMP
);
```

#### 3.2.6 members (الأعضاء/العملاء)
```sql
CREATE TABLE members (
    id                      SERIAL PRIMARY KEY,
    brand_id                INTEGER REFERENCES brands(id) NOT NULL,
    branch_id               INTEGER REFERENCES branches(id),
    name                    VARCHAR(100) NOT NULL,
    phone                   VARCHAR(20) NOT NULL,
    email                   VARCHAR(100),
    gender                  VARCHAR(10) CHECK (gender IN ('male', 'female')),
    birth_date              DATE,
    national_id             VARCHAR(20),
    address                 TEXT,
    emergency_contact       VARCHAR(100),
    emergency_phone         VARCHAR(20),
    photo                   VARCHAR(255),
    -- بيانات البصمة
    fingerprint_id          INTEGER,                    -- ID في جهاز البصمة
    fingerprint_enrolled    BOOLEAN DEFAULT FALSE,      -- هل تم تسجيل البصمة
    fingerprint_enrolled_at TIMESTAMP,
    -- حالة العضو
    is_active               BOOLEAN DEFAULT TRUE,
    notes                   TEXT,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by              INTEGER REFERENCES users(id)
);
```

#### 3.2.7 plans (باقات الاشتراك)
```sql
CREATE TABLE plans (
    id                      SERIAL PRIMARY KEY,
    brand_id                INTEGER REFERENCES brands(id) NOT NULL,
    name                    VARCHAR(100) NOT NULL,
    description             TEXT,
    duration_days           INTEGER NOT NULL,               -- المدة بالأيام
    duration_months         INTEGER,                        -- المدة بالأشهر (للعرض)
    price                   DECIMAL(10,2) NOT NULL,
    max_freezes             INTEGER DEFAULT 1,              -- عدد مرات التجميد المسموحة
    max_freeze_days         INTEGER DEFAULT 14,             -- أقصى أيام تجميد
    available_all_branches  BOOLEAN DEFAULT TRUE,           -- متاح لجميع الفروع؟
    is_active               BOOLEAN DEFAULT TRUE,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- أمثلة للباقات
-- باقة شهرية (30 يوم) - لجميع الفروع
-- باقة 3 شهور (90 يوم) - لجميع الفروع
-- باقة 6 شهور (180 يوم) - لجميع الفروع
-- باقة سنوية (365 يوم) - لفروع محددة
```

#### 3.2.7.1 plan_branches (ربط الباقات بالفروع)
```sql
-- جدول وسيط لتحديد الفروع المسموح لها باستخدام باقة معينة
-- يُستخدم فقط عندما available_all_branches = FALSE

CREATE TABLE plan_branches (
    id          SERIAL PRIMARY KEY,
    plan_id     INTEGER REFERENCES plans(id) ON DELETE CASCADE,
    branch_id   INTEGER REFERENCES branches(id) ON DELETE CASCADE,
    UNIQUE(plan_id, branch_id)
);

-- مثال: إذا كانت باقة VIP متاحة فقط لفرع 1 و 2:
-- INSERT INTO plan_branches (plan_id, branch_id) VALUES (5, 1), (5, 2);
```

#### 3.2.8 subscriptions (الاشتراكات)
```sql
CREATE TABLE subscriptions (
    id                  SERIAL PRIMARY KEY,
    member_id           INTEGER REFERENCES members(id) NOT NULL,
    plan_id             INTEGER REFERENCES plans(id) NOT NULL,
    brand_id            INTEGER REFERENCES brands(id) NOT NULL,
    branch_id           INTEGER REFERENCES branches(id),
    -- التواريخ
    start_date          DATE NOT NULL,
    end_date            DATE NOT NULL,
    original_end_date   DATE NOT NULL,              -- التاريخ الأصلي قبل التجميد
    -- المبالغ
    total_amount        DECIMAL(10,2) NOT NULL,
    paid_amount         DECIMAL(10,2) NOT NULL DEFAULT 0,
    remaining_amount    DECIMAL(10,2) NOT NULL DEFAULT 0,
    discount            DECIMAL(10,2) DEFAULT 0,
    -- الحالة
    status              VARCHAR(20) DEFAULT 'active'
                        CHECK (status IN ('active', 'frozen', 'expired', 'cancelled')),
    -- معلومات إضافية
    notes               TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by          INTEGER REFERENCES users(id)
);
```

#### 3.2.9 subscription_freezes (تجميد الاشتراكات)
```sql
CREATE TABLE subscription_freezes (
    id                  SERIAL PRIMARY KEY,
    subscription_id     INTEGER REFERENCES subscriptions(id) NOT NULL,
    freeze_start        DATE NOT NULL,
    freeze_end          DATE NOT NULL,
    freeze_days         INTEGER NOT NULL,
    reason              TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by          INTEGER REFERENCES users(id)
);
```

#### 3.2.10 subscription_payments (دفعات الاشتراك)
```sql
CREATE TABLE subscription_payments (
    id                  SERIAL PRIMARY KEY,
    subscription_id     INTEGER REFERENCES subscriptions(id) NOT NULL,
    brand_id            INTEGER REFERENCES brands(id) NOT NULL,
    amount              DECIMAL(10,2) NOT NULL,
    payment_method      VARCHAR(20) DEFAULT 'cash',
    payment_date        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes               TEXT,
    created_by          INTEGER REFERENCES users(id)
);
```

#### 3.2.11 member_attendance (حضور الأعضاء)
```sql
CREATE TABLE member_attendance (
    id              SERIAL PRIMARY KEY,
    member_id       INTEGER REFERENCES members(id) NOT NULL,
    subscription_id INTEGER REFERENCES subscriptions(id),
    brand_id        INTEGER REFERENCES brands(id) NOT NULL,
    branch_id       INTEGER REFERENCES branches(id),
    check_in        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    check_out       TIMESTAMP,
    source          VARCHAR(20) DEFAULT 'manual'
                    CHECK (source IN ('manual', 'qr', 'fingerprint')),
    fingerprint_log_id  INTEGER,                    -- ID من سجل البصمة الأصلي
    notes           TEXT
);

-- Index للبحث السريع
CREATE INDEX idx_member_attendance_date ON member_attendance(brand_id, check_in);
CREATE INDEX idx_member_attendance_member ON member_attendance(member_id, check_in);
```

#### 3.2.12 employee_attendance (حضور الموظفين)
```sql
CREATE TABLE employee_attendance (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) NOT NULL,
    brand_id    INTEGER REFERENCES brands(id) NOT NULL,
    branch_id   INTEGER REFERENCES branches(id),
    date        DATE NOT NULL,
    check_in    TIME,
    check_out   TIME,
    status      VARCHAR(20) DEFAULT 'present'
                CHECK (status IN ('present', 'absent', 'late', 'leave')),
    notes       TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, date)
);
```

#### 3.2.13 income (الدخل)
```sql
CREATE TABLE income (
    id                  SERIAL PRIMARY KEY,
    brand_id            INTEGER REFERENCES brands(id) NOT NULL,
    branch_id           INTEGER REFERENCES branches(id),
    subscription_id     INTEGER REFERENCES subscriptions(id),
    payment_id          INTEGER REFERENCES subscription_payments(id),
    amount              DECIMAL(10,2) NOT NULL,
    type                VARCHAR(30) NOT NULL
                        CHECK (type IN ('subscription', 'renewal', 'other')),
    description         TEXT,
    date                DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by          INTEGER REFERENCES users(id)
);
```

#### 3.2.14 expenses (المصروفات)
```sql
CREATE TABLE expenses (
    id              SERIAL PRIMARY KEY,
    brand_id        INTEGER REFERENCES brands(id) NOT NULL,
    branch_id       INTEGER REFERENCES branches(id),
    category        VARCHAR(50) NOT NULL,
    amount          DECIMAL(10,2) NOT NULL,
    description     TEXT,
    date            DATE NOT NULL DEFAULT CURRENT_DATE,
    receipt_image   VARCHAR(255),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by      INTEGER REFERENCES users(id)
);

-- الفئات الافتراضية للمصروفات
-- 'رواتب', 'إيجار', 'كهرباء', 'ماء', 'صيانة', 'معدات', 'تسويق', 'أخرى'
```

#### 3.2.15 salaries (الرواتب)
```sql
CREATE TABLE salaries (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id) NOT NULL,
    brand_id        INTEGER REFERENCES brands(id) NOT NULL,
    month           INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    year            INTEGER NOT NULL,
    base_salary     DECIMAL(10,2) NOT NULL,
    deductions      DECIMAL(10,2) DEFAULT 0,
    bonuses         DECIMAL(10,2) DEFAULT 0,
    net_salary      DECIMAL(10,2) NOT NULL,
    days_worked     INTEGER,
    status          VARCHAR(20) DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'paid')),
    paid_date       DATE,
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_by     INTEGER REFERENCES users(id),
    UNIQUE(user_id, month, year)
);
```

#### 3.2.16 refunds (المرتجعات)
```sql
CREATE TABLE refunds (
    id                  SERIAL PRIMARY KEY,
    brand_id            INTEGER REFERENCES brands(id) NOT NULL,
    subscription_id     INTEGER REFERENCES subscriptions(id) NOT NULL,
    member_id           INTEGER REFERENCES members(id) NOT NULL,
    amount              DECIMAL(10,2) NOT NULL,
    reason              TEXT NOT NULL,
    refund_date         DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by          INTEGER REFERENCES users(id)
);
```

#### 3.2.17 fingerprint_sync_logs (سجل مزامنة البصمة)
```sql
CREATE TABLE fingerprint_sync_logs (
    id                  SERIAL PRIMARY KEY,
    brand_id            INTEGER REFERENCES brands(id) NOT NULL,
    sync_type           VARCHAR(20) NOT NULL
                        CHECK (sync_type IN ('attendance', 'enrollment', 'full')),
    records_synced      INTEGER DEFAULT 0,
    last_sync_id        INTEGER,                    -- آخر ID تمت مزامنته
    status              VARCHAR(20) DEFAULT 'success'
                        CHECK (status IN ('success', 'failed', 'partial')),
    error_message       TEXT,
    synced_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 4. هيكل المشروع (Project Structure)

```
gym_system/
│
├── app/
│   ├── __init__.py                 # Flask app factory
│   ├── config.py                   # إعدادات التطبيق
│   │
│   ├── models/                     # Database Models
│   │   ├── __init__.py
│   │   ├── company.py              # Company, Brand, Branch
│   │   ├── user.py                 # User, Role
│   │   ├── member.py               # Member
│   │   ├── subscription.py         # Subscription, Plan, Freeze, Payment
│   │   ├── attendance.py           # MemberAttendance, EmployeeAttendance
│   │   ├── finance.py              # Income, Expense, Salary, Refund
│   │   └── fingerprint.py          # FingerprintSyncLog
│   │
│   ├── routes/                     # Route Blueprints
│   │   ├── __init__.py
│   │   ├── auth.py                 # تسجيل الدخول/الخروج
│   │   ├── dashboard.py            # لوحات التحكم حسب الدور
│   │   ├── admin.py                # إدارة البراندات والمستخدمين
│   │   ├── members.py              # إدارة الأعضاء
│   │   ├── subscriptions.py        # إدارة الاشتراكات
│   │   ├── attendance.py           # تسجيل الحضور
│   │   ├── finance.py              # العمليات المالية
│   │   ├── reports.py              # التقارير
│   │   ├── settings.py             # الإعدادات
│   │   └── api/                    # REST API
│   │       ├── __init__.py
│   │       └── fingerprint.py      # API للبصمة
│   │
│   ├── services/                   # Business Logic
│   │   ├── __init__.py
│   │   ├── subscription_service.py # منطق الاشتراكات
│   │   ├── attendance_service.py   # منطق الحضور
│   │   ├── finance_service.py      # منطق المالية
│   │   └── report_service.py       # توليد التقارير
│   │
│   ├── utils/                      # Utilities
│   │   ├── __init__.py
│   │   ├── decorators.py           # @role_required, @brand_required
│   │   ├── helpers.py              # دوال مساعدة
│   │   ├── export.py               # تصدير Excel/PDF
│   │   └── validators.py           # التحقق من البيانات
│   │
│   ├── templates/                  # Jinja2 Templates
│   │   ├── base.html               # القالب الأساسي
│   │   ├── components/             # مكونات قابلة لإعادة الاستخدام
│   │   │   ├── navbar.html
│   │   │   ├── sidebar.html
│   │   │   ├── pagination.html
│   │   │   ├── alerts.html
│   │   │   └── modals.html
│   │   ├── auth/
│   │   │   ├── login.html
│   │   │   └── change_password.html
│   │   ├── dashboard/
│   │   │   ├── owner.html
│   │   │   ├── receptionist.html
│   │   │   ├── finance.html
│   │   │   └── finance_admin.html
│   │   ├── admin/
│   │   │   ├── brands/
│   │   │   │   ├── list.html
│   │   │   │   ├── create.html
│   │   │   │   └── edit.html
│   │   │   ├── branches/
│   │   │   ├── users/
│   │   │   └── plans/
│   │   ├── members/
│   │   │   ├── list.html
│   │   │   ├── create.html
│   │   │   ├── view.html
│   │   │   └── edit.html
│   │   ├── subscriptions/
│   │   │   ├── list.html
│   │   │   ├── create.html
│   │   │   ├── view.html
│   │   │   ├── renew.html
│   │   │   └── freeze.html
│   │   ├── attendance/
│   │   │   ├── members.html
│   │   │   ├── employees.html
│   │   │   └── check_in.html
│   │   ├── finance/
│   │   │   ├── income.html
│   │   │   ├── expenses.html
│   │   │   ├── salaries.html
│   │   │   └── refunds.html
│   │   ├── reports/
│   │   │   ├── financial.html
│   │   │   ├── members.html
│   │   │   ├── attendance.html
│   │   │   └── comparison.html
│   │   └── errors/
│   │       ├── 404.html
│   │       ├── 403.html
│   │       └── 500.html
│   │
│   └── static/
│       ├── css/
│       │   ├── style.css           # الأنماط الرئيسية
│       │   ├── rtl.css             # أنماط RTL
│       │   └── print.css           # أنماط الطباعة
│       ├── js/
│       │   ├── main.js             # JavaScript الرئيسي
│       │   ├── charts.js           # الرسوم البيانية
│       │   └── attendance.js       # صفحة الحضور
│       ├── img/
│       │   └── logo.png
│       └── uploads/                # الملفات المرفوعة
│           ├── logos/
│           ├── members/
│           └── receipts/
│
├── fingerprint_bridge/             # خدمة البصمة المحلية
│   ├── __init__.py
│   ├── main.py                     # نقطة البداية
│   ├── config.py                   # إعدادات الاتصال
│   ├── aas_protocol.py             # بروتوكول التواصل مع جهاز AAS
│   ├── cloud_sync.py               # المزامنة مع السحابة
│   ├── models.py                   # نماذج البيانات المحلية
│   └── logs/                       # سجلات الخدمة
│
├── migrations/                     # Flask-Migrate
│
├── tests/                          # اختبارات
│   ├── __init__.py
│   ├── test_auth.py
│   ├── test_members.py
│   ├── test_subscriptions.py
│   └── test_finance.py
│
├── docs/                           # التوثيق
│   ├── API.md
│   ├── DEPLOYMENT.md
│   └── FINGERPRINT_SETUP.md
│
├── .env.example                    # مثال لملف البيئة
├── .gitignore
├── requirements.txt                # المكتبات المطلوبة
├── requirements-dev.txt            # مكتبات التطوير
├── Procfile                        # لـ Railway/Render
├── runtime.txt                     # إصدار Python
└── run.py                          # تشغيل التطبيق
```

---

## 5. الصلاحيات والأدوار (Roles & Permissions)

### 5.1 مصفوفة الصلاحيات

| الصلاحية | Owner | Receptionist | Finance | Finance Admin | Manager | Coach |
|----------|-------|--------------|---------|---------------|---------|-------|
| **البراندات** |
| إنشاء/تعديل براند | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| عرض جميع البراندات | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ |
| **الأعضاء** |
| إضافة عضو | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ |
| تعديل عضو | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ |
| عرض أعضاء البراند | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **الاشتراكات** |
| إنشاء اشتراك | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ |
| تجديد اشتراك | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ |
| تجميد اشتراك | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ |
| إلغاء اشتراك | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| **الحضور** |
| تسجيل حضور عضو | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ |
| عرض سجل الحضور | ✅ | ✅ | ✅ | ✅ | ✅ | 🔶 |
| **المالية** |
| تسجيل مصروفات | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ |
| إدارة الرواتب | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ |
| إجراء مرتجعات | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ |
| **التقارير** |
| تقارير البراند | ✅ | ❌ | ✅ | ✅ | ✅ | ❌ |
| تقارير مجمعة | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ |
| مقارنة البراندات | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ |
| تصدير التقارير | ✅ | ❌ | ✅ | ✅ | ✅ | ❌ |
| **الإعدادات** |
| إدارة المستخدمين | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| إدارة الباقات | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |

🔶 = حضوره الشخصي فقط

### 5.2 قواعد الوصول للبيانات

```python
# في كل query يجب تطبيق فلتر البراند
# مثال:
def get_members(user):
    query = Member.query

    if user.role.name == 'owner':
        # يرى جميع الأعضاء
        pass
    elif user.role.name == 'finance_admin':
        # يرى جميع الأعضاء (للتقارير فقط)
        pass
    else:
        # يرى أعضاء برانده فقط
        query = query.filter(Member.brand_id == user.brand_id)

    return query.all()
```

---

## 6. واجهات المستخدم (User Interface)

### 6.1 تصميم الواجهة

#### الألوان الرئيسية
```css
:root {
    --primary-color: #2563eb;      /* أزرق */
    --secondary-color: #64748b;    /* رمادي */
    --success-color: #22c55e;      /* أخضر */
    --warning-color: #f59e0b;      /* برتقالي */
    --danger-color: #ef4444;       /* أحمر */
    --background: #f8fafc;         /* خلفية */
    --card-bg: #ffffff;            /* خلفية البطاقات */
    --text-primary: #1e293b;       /* نص رئيسي */
    --text-secondary: #64748b;     /* نص ثانوي */
}
```

#### هيكل الصفحة
```
┌─────────────────────────────────────────────────────────┐
│                      Navbar                              │
│  [Logo] [Brand Selector▼]              [User▼] [Logout]  │
├──────────┬──────────────────────────────────────────────┤
│          │                                               │
│  Sidebar │              Main Content                     │
│          │                                               │
│  - لوحة  │   ┌─────────────────────────────────────┐    │
│    التحكم│   │         Page Header                 │    │
│  - الأعضاء│   │  [Title]           [Action Button]  │    │
│  - الاشت- │   └─────────────────────────────────────┘    │
│    راكات │                                               │
│  - الحضور│   ┌─────────────────────────────────────┐    │
│  - المالية│   │                                     │    │
│  - التقا- │   │         Content Area                │    │
│    رير   │   │                                     │    │
│  - الإعدا│   │                                     │    │
│    دات   │   └─────────────────────────────────────┘    │
│          │                                               │
└──────────┴──────────────────────────────────────────────┘
```

### 6.2 الصفحات الرئيسية

#### 6.2.1 صفحة تسجيل الدخول
- شعار النظام
- حقل البريد الإلكتروني
- حقل كلمة المرور
- زر تسجيل الدخول
- رسالة خطأ (إذا وجدت)

#### 6.2.2 لوحة تحكم المالك (Owner Dashboard)
```
┌─────────────────────────────────────────────────────────┐
│                    نظرة عامة                            │
├─────────────┬─────────────┬─────────────┬──────────────┤
│  إجمالي    │  إجمالي    │   صافي     │   إجمالي    │
│  الدخل     │  المصروفات │   الربح    │   الأعضاء   │
│  150,000   │   45,000   │  105,000   │    1,250    │
└─────────────┴─────────────┴─────────────┴──────────────┘

┌─────────────────────────────────────────────────────────┐
│              مقارنة البراندات (Chart)                   │
│  [Bar Chart comparing brands]                           │
└─────────────────────────────────────────────────────────┘

┌──────────────────────┐  ┌──────────────────────────────┐
│    آخر الاشتراكات    │  │      اشتراكات تنتهي قريباً   │
│  - أحمد - باقة شهرية │  │  - محمد (3 أيام)            │
│  - سارة - باقة سنوية │  │  - فاطمة (5 أيام)           │
│  - خالد - باقة 3 شهور│  │  - علي (7 أيام)             │
└──────────────────────┘  └──────────────────────────────┘
```

#### 6.2.3 لوحة تحكم موظف الاستقبال
```
┌─────────────────────────────────────────────────────────┐
│                 إجراءات سريعة                           │
├──────────────┬──────────────┬──────────────────────────┤
│  [+ عضو جديد]│ [+ اشتراك]  │    [تسجيل حضور]         │
└──────────────┴──────────────┴──────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                   بحث سريع عن عضو                       │
│  [🔍 ابحث بالاسم أو رقم الهاتف...]                     │
└─────────────────────────────────────────────────────────┘

┌──────────────────────┐  ┌──────────────────────────────┐
│   الحضور اليوم: 45   │  │      اشتراكات تنتهي اليوم    │
│                      │  │  - أحمد محمد (هاتف: 055...) │
│   [View All →]       │  │  - سارة أحمد (هاتف: 050...) │
└──────────────────────┘  └──────────────────────────────┘
```

### 6.3 صفحة تسجيل الحضور

```
┌─────────────────────────────────────────────────────────┐
│                    تسجيل حضور                           │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  [🔍 بحث بالاسم أو رقم الهاتف أو ID البصمة]    │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  👤 أحمد محمد السيد                            │   │
│  │  ──────────────────────────────────────────────│   │
│  │  الباقة: شهرية                                  │   │
│  │  تنتهي في: 2024-02-15                          │   │
│  │  الحالة: ✅ نشط                                 │   │
│  │                                                 │   │
│  │  [     ✓ تسجيل الدخول     ]                   │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ❌ الاشتراك منتهي / مجمد (لا يمكن تسجيل الدخول)       │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 6.4 صفحة إنشاء/تعديل الباقات

```
┌─────────────────────────────────────────────────────────┐
│                    إضافة باقة جديدة                      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  اسم الباقة:                                            │
│  ┌─────────────────────────────────────────────────┐   │
│  │  باقة شهرية                                     │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  المدة:                                                 │
│  ┌──────────┐  شهر                                     │
│  │    1     │  (30 يوم)                                │
│  └──────────┘                                          │
│                                                         │
│  السعر:                                                 │
│  ┌──────────┐  ريال                                    │
│  │   500    │                                          │
│  └──────────┘                                          │
│                                                         │
│  إعدادات التجميد:                                       │
│  ┌──────────┐ مرة كحد أقصى    ┌──────────┐ يوم كحد أقصى│
│  │    1     │                 │    14    │             │
│  └──────────┘                 └──────────┘             │
│                                                         │
│  ─────────────────────────────────────────────────────  │
│                                                         │
│  الفروع المتاحة:                                        │
│  ┌─────────────────────────────────────────────────┐   │
│  │ ◉ جميع الفروع                                   │   │
│  │ ○ فروع محددة                                    │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  (إذا اخترت "فروع محددة"):                             │
│  ┌─────────────────────────────────────────────────┐   │
│  │ ☑ الفرع الرئيسي                                 │   │
│  │ ☑ فرع الملز                                     │   │
│  │ ☐ فرع النسيم                                    │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│                        [إلغاء]  [حفظ الباقة]            │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 6.5 صفحة قائمة الباقات

```
┌─────────────────────────────────────────────────────────┐
│  الباقات                              [+ إضافة باقة]   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ الباقة        │ المدة    │ السعر  │ الفروع │    │   │
│  ├───────────────┼──────────┼────────┼────────┼────┤   │
│  │ باقة شهرية   │ 1 شهر   │ 500 ر  │ الكل  │ ✏️🗑│   │
│  │ باقة 3 شهور  │ 3 شهور  │ 1200 ر │ الكل  │ ✏️🗑│   │
│  │ باقة 6 شهور  │ 6 شهور  │ 2000 ر │ الكل  │ ✏️🗑│   │
│  │ باقة VIP     │ 12 شهر  │ 5000 ر │ 2 فرع │ ✏️🗑│   │
│  └───────────────┴──────────┴────────┴────────┴────┘   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 6.6 صفحة إنشاء اشتراك جديد

```
┌─────────────────────────────────────────────────────────┐
│                    اشتراك جديد                          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  العضو: أحمد محمد السيد                                 │
│  الفرع: الفرع الرئيسي                                   │
│                                                         │
│  ─────────────────────────────────────────────────────  │
│                                                         │
│  اختر الباقة:                                           │
│  ┌─────────────────────────────────────────────────┐   │
│  │ ○ باقة شهرية    │ 1 شهر   │ 500 ريال           │   │
│  │ ◉ باقة 3 شهور  │ 3 شهور  │ 1,200 ريال         │   │
│  │ ○ باقة 6 شهور  │ 6 شهور  │ 2,000 ريال         │   │
│  └─────────────────────────────────────────────────┘   │
│  ℹ️ يتم عرض الباقات المتاحة لهذا الفرع فقط             │
│                                                         │
│  ─────────────────────────────────────────────────────  │
│                                                         │
│  تاريخ البداية: [اليوم ▼]                              │
│  تاريخ الانتهاء: 15/04/2026 (تلقائي حسب الباقة)        │
│                                                         │
│  ─────────────────────────────────────────────────────  │
│                                                         │
│  المبلغ الإجمالي:     1,200 ريال                        │
│  الخصم:               ┌──────┐ ريال                    │
│                       │  0   │                          │
│                       └──────┘                          │
│  المبلغ بعد الخصم:    1,200 ريال                        │
│  المبلغ المدفوع:      ┌──────┐ ريال                    │
│                       │ 1200 │                          │
│                       └──────┘                          │
│  المتبقي:             0 ريال                            │
│                                                         │
│                        [إلغاء]  [إنشاء الاشتراك]        │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 7. تكامل نظام البصمة (Fingerprint Integration)

### 7.1 نظرة عامة على الهيكل

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLOUD SERVER                             │
│                    (Railway / Render)                            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                   Flask Application                       │    │
│  │                                                           │    │
│  │   /api/fingerprint/attendance    ← POST attendance data   │    │
│  │   /api/fingerprint/members       → GET pending members    │    │
│  │   /api/fingerprint/enrolled      ← POST enrollment status │    │
│  │   /api/fingerprint/health        → GET service status     │    │
│  │                                                           │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              ▲                                   │
│                              │ HTTPS (REST API)                  │
│                              │ API Key Authentication            │
└──────────────────────────────┼───────────────────────────────────┘
                               │
                               │ Internet
                               │
┌──────────────────────────────┼───────────────────────────────────┐
│          GYM LOCATION        │        (Brand with Fingerprint)   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              Fingerprint Bridge Service                   │    │
│  │              (Python - Windows PC)                        │    │
│  │                                                           │    │
│  │   1. كل 30 ثانية: قراءة سجلات الحضور من جهاز البصمة      │    │
│  │   2. إرسال السجلات الجديدة للسحابة                        │    │
│  │   3. تحميل الأعضاء الجدد المطلوب تسجيل بصمتهم             │    │
│  │   4. تحديث حالة التسجيل                                   │    │
│  │                                                           │    │
│  └─────────────────────────┬───────────────────────────────┘    │
│                            │ TCP/IP                              │
│                            │ 192.168.1.224:5005                  │
│                            ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              AAS Access Control Panel                     │    │
│  │                                                           │    │
│  │   - يخزن بصمات الأعضاء                                    │    │
│  │   - يسجل أوقات الدخول                                     │    │
│  │   - يتحكم في فتح الباب                                    │    │
│  │                                                           │    │
│  └─────────────────────────────────────────────────────────┘    │
│                            │                                     │
│                            ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              Fingerprint Reader                           │    │
│  │              (عند باب الجيم)                              │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 7.2 AAS Controller Communication Protocol

```python
# aas_protocol.py

import socket
import struct

class AASController:
    """
    التواصل مع جهاز التحكم AAS عبر TCP/IP
    البروتوكول مبني على تحليل الـ SDK الموجود
    """

    def __init__(self, ip='192.168.1.224', port=5005, device_id=1):
        self.ip = ip
        self.port = port
        self.device_id = device_id
        self.socket = None

    def connect(self):
        """الاتصال بجهاز البصمة"""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(10)
        self.socket.connect((self.ip, self.port))

    def disconnect(self):
        """قطع الاتصال"""
        if self.socket:
            self.socket.close()

    def get_attendance_logs(self, last_id=0):
        """
        قراءة سجلات الحضور
        Returns: list of attendance records
        [
            {
                'log_id': 123,
                'user_id': 1,
                'timestamp': datetime,
                'verify_type': 'fingerprint'
            }
        ]
        """
        # TODO: تطبيق البروتوكول الفعلي من الـ SDK
        pass

    def enroll_fingerprint(self, user_id, fingerprint_data):
        """
        تسجيل بصمة جديدة
        """
        pass

    def delete_fingerprint(self, user_id):
        """
        حذف بصمة
        """
        pass

    def get_all_users(self):
        """
        قراءة جميع المستخدمين المسجلين
        """
        pass
```

### 7.3 Bridge Service

```python
# fingerprint_bridge/main.py

import time
import logging
from datetime import datetime
from aas_protocol import AASController
from cloud_sync import CloudAPI

# إعدادات
CLOUD_API_URL = "https://your-app.railway.app/api"
API_KEY = "your-secret-api-key"
SYNC_INTERVAL = 30  # ثانية

# إعدادات جهاز البصمة
AAS_IP = "192.168.1.224"
AAS_PORT = 5005
DEVICE_ID = 1

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """الخدمة الرئيسية للمزامنة"""

    aas = AASController(AAS_IP, AAS_PORT, DEVICE_ID)
    cloud = CloudAPI(CLOUD_API_URL, API_KEY)

    last_sync_id = load_last_sync_id()

    logger.info("بدء خدمة مزامنة البصمة...")

    while True:
        try:
            # 1. الاتصال بجهاز البصمة
            aas.connect()

            # 2. قراءة سجلات الحضور الجديدة
            logs = aas.get_attendance_logs(last_id=last_sync_id)

            if logs:
                logger.info(f"تم العثور على {len(logs)} سجل جديد")

                # 3. إرسال للسحابة
                result = cloud.sync_attendance(logs)

                if result['success']:
                    last_sync_id = logs[-1]['log_id']
                    save_last_sync_id(last_sync_id)
                    logger.info(f"تمت مزامنة {len(logs)} سجل")

            # 4. تحميل الأعضاء الجدد للتسجيل
            pending = cloud.get_pending_enrollments()

            for member in pending:
                logger.info(f"عضو جديد للتسجيل: {member['name']}")
                # هنا يتم إعلام المستخدم لتسجيل البصمة يدوياً
                # أو عبر واجهة الـ AAS software

            aas.disconnect()

        except Exception as e:
            logger.error(f"خطأ: {e}")

        # انتظار قبل المزامنة التالية
        time.sleep(SYNC_INTERVAL)

def load_last_sync_id():
    """تحميل آخر ID تمت مزامنته"""
    try:
        with open('last_sync_id.txt', 'r') as f:
            return int(f.read().strip())
    except:
        return 0

def save_last_sync_id(sync_id):
    """حفظ آخر ID تمت مزامنته"""
    with open('last_sync_id.txt', 'w') as f:
        f.write(str(sync_id))

if __name__ == '__main__':
    main()
```

### 7.4 Cloud API Endpoints

```python
# app/routes/api/fingerprint.py

from flask import Blueprint, request, jsonify
from functools import wraps

fingerprint_api = Blueprint('fingerprint_api', __name__, url_prefix='/api/fingerprint')

def require_api_key(f):
    """التحقق من API Key"""
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if api_key != current_app.config['FINGERPRINT_API_KEY']:
            return jsonify({'error': 'Invalid API key'}), 401
        return f(*args, **kwargs)
    return decorated

@fingerprint_api.route('/attendance', methods=['POST'])
@require_api_key
def sync_attendance():
    """
    استقبال سجلات الحضور من Bridge Service

    Request Body:
    {
        "brand_id": 1,
        "records": [
            {
                "fingerprint_id": 123,
                "timestamp": "2024-01-15T09:30:00",
                "log_id": 456
            }
        ]
    }
    """
    data = request.get_json()
    brand_id = data['brand_id']
    records = data['records']

    synced = 0
    errors = []

    for record in records:
        try:
            # البحث عن العضو بـ fingerprint_id
            member = Member.query.filter_by(
                brand_id=brand_id,
                fingerprint_id=record['fingerprint_id']
            ).first()

            if not member:
                errors.append(f"Member not found: {record['fingerprint_id']}")
                continue

            # التحقق من الاشتراك
            subscription = get_active_subscription(member.id)

            if not subscription:
                errors.append(f"No active subscription: {member.id}")
                continue

            # تسجيل الحضور
            attendance = MemberAttendance(
                member_id=member.id,
                subscription_id=subscription.id,
                brand_id=brand_id,
                check_in=datetime.fromisoformat(record['timestamp']),
                source='fingerprint',
                fingerprint_log_id=record['log_id']
            )
            db.session.add(attendance)
            synced += 1

        except Exception as e:
            errors.append(str(e))

    db.session.commit()

    # تسجيل المزامنة
    log = FingerprintSyncLog(
        brand_id=brand_id,
        sync_type='attendance',
        records_synced=synced,
        last_sync_id=records[-1]['log_id'] if records else None,
        status='success' if not errors else 'partial',
        error_message='\n'.join(errors) if errors else None
    )
    db.session.add(log)
    db.session.commit()

    return jsonify({
        'success': True,
        'synced': synced,
        'errors': errors
    })

@fingerprint_api.route('/members/pending', methods=['GET'])
@require_api_key
def get_pending_enrollments():
    """
    الأعضاء الذين يحتاجون تسجيل بصمة
    """
    brand_id = request.args.get('brand_id', type=int)

    members = Member.query.filter_by(
        brand_id=brand_id,
        fingerprint_enrolled=False,
        is_active=True
    ).all()

    return jsonify({
        'members': [
            {
                'id': m.id,
                'name': m.name,
                'phone': m.phone,
                'fingerprint_id': m.fingerprint_id
            }
            for m in members
        ]
    })

@fingerprint_api.route('/members/enrolled', methods=['POST'])
@require_api_key
def mark_enrolled():
    """
    تحديث حالة تسجيل البصمة
    """
    data = request.get_json()
    member_id = data['member_id']
    fingerprint_id = data['fingerprint_id']

    member = Member.query.get(member_id)
    if member:
        member.fingerprint_id = fingerprint_id
        member.fingerprint_enrolled = True
        member.fingerprint_enrolled_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True})

    return jsonify({'success': False, 'error': 'Member not found'}), 404

@fingerprint_api.route('/health', methods=['GET'])
@require_api_key
def health_check():
    """
    فحص حالة الخدمة
    """
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.utcnow().isoformat()
    })
```

### 7.5 سير عمل تسجيل البصمة

```
┌─────────────────────────────────────────────────────────────────┐
│                     تسجيل عضو جديد مع بصمة                      │
└─────────────────────────────────────────────────────────────────┘

1. موظف الاستقبال يضيف عضو جديد من الويب
   ↓
2. النظام يولد fingerprint_id فريد للعضو
   ↓
3. العضو يظهر في قائمة "في انتظار تسجيل البصمة"
   ↓
4. في الجيم: فتح برنامج AAS على الكمبيوتر
   ↓
5. تسجيل بصمة العضو في جهاز البصمة باستخدام الـ fingerprint_id
   ↓
6. Bridge Service تكتشف التسجيل الجديد
   ↓
7. إرسال تأكيد للسحابة
   ↓
8. تحديث حالة العضو: fingerprint_enrolled = True
   ↓
9. العضو يمكنه الآن الدخول بالبصمة

┌─────────────────────────────────────────────────────────────────┐
│                        تسجيل حضور بالبصمة                        │
└─────────────────────────────────────────────────────────────────┘

1. العضو يضع بصمته على القارئ
   ↓
2. جهاز AAS يتعرف على البصمة ويفتح الباب
   ↓
3. جهاز AAS يسجل الحدث في الذاكرة المحلية
   ↓
4. Bridge Service تقرأ السجل الجديد
   ↓
5. إرسال للسحابة عبر API
   ↓
6. السحابة:
   - تبحث عن العضو بـ fingerprint_id
   - تتحقق من صلاحية الاشتراك
   - تسجل الحضور في قاعدة البيانات
   ↓
7. السجل يظهر في تقارير الحضور
```

---

## 8. العمليات الأساسية (Core Operations)

### 8.0 الحصول على الباقات المتاحة لفرع معين

```python
# app/services/plan_service.py

from app.models import Plan, PlanBranch
from app import db

def get_available_plans_for_branch(brand_id, branch_id):
    """
    الحصول على الباقات المتاحة لفرع معين

    الباقة تكون متاحة إذا:
    1. available_all_branches = True (متاحة لجميع الفروع)
    2. أو الفرع موجود في جدول plan_branches

    Args:
        brand_id: معرف البراند
        branch_id: معرف الفرع

    Returns:
        list of Plan objects
    """

    # الباقات المتاحة لجميع الفروع
    all_branches_plans = Plan.query.filter_by(
        brand_id=brand_id,
        available_all_branches=True,
        is_active=True
    ).all()

    # الباقات المخصصة لهذا الفرع
    specific_plans = Plan.query.join(PlanBranch).filter(
        Plan.brand_id == brand_id,
        Plan.available_all_branches == False,
        Plan.is_active == True,
        PlanBranch.branch_id == branch_id
    ).all()

    return all_branches_plans + specific_plans


def create_plan(brand_id, name, duration_months, price, branch_ids=None,
                max_freezes=1, max_freeze_days=14, description=None):
    """
    إنشاء باقة جديدة

    Args:
        brand_id: معرف البراند
        name: اسم الباقة
        duration_months: المدة بالأشهر
        price: السعر
        branch_ids: قائمة الفروع (None = جميع الفروع)
        max_freezes: عدد مرات التجميد
        max_freeze_days: أقصى أيام تجميد
        description: وصف الباقة

    Returns:
        Plan object
    """

    # حساب الأيام (تقريبي: شهر = 30 يوم)
    duration_days = duration_months * 30

    plan = Plan(
        brand_id=brand_id,
        name=name,
        description=description,
        duration_days=duration_days,
        duration_months=duration_months,
        price=price,
        max_freezes=max_freezes,
        max_freeze_days=max_freeze_days,
        available_all_branches=(branch_ids is None)
    )
    db.session.add(plan)
    db.session.flush()

    # إذا كانت لفروع محددة
    if branch_ids:
        for branch_id in branch_ids:
            plan_branch = PlanBranch(plan_id=plan.id, branch_id=branch_id)
            db.session.add(plan_branch)

    db.session.commit()
    return plan
```

### 8.1 إنشاء اشتراك جديد

```python
# app/services/subscription_service.py

from datetime import date, timedelta
from app.models import Subscription, Income, SubscriptionPayment
from app import db

def create_subscription(member_id, plan_id, brand_id, branch_id, paid_amount,
                       discount=0, notes=None, created_by=None):
    """
    إنشاء اشتراك جديد

    Args:
        member_id: معرف العضو
        plan_id: معرف الباقة
        brand_id: معرف البراند
        branch_id: معرف الفرع
        paid_amount: المبلغ المدفوع
        discount: الخصم (إن وجد)
        notes: ملاحظات
        created_by: معرف المستخدم المنشئ

    Returns:
        Subscription object
    """

    plan = Plan.query.get(plan_id)

    # التحقق من أن الباقة متاحة لهذا الفرع
    available_plans = get_available_plans_for_branch(brand_id, branch_id)
    if plan not in available_plans:
        raise ValueError("هذه الباقة غير متاحة لهذا الفرع")

    # حساب التواريخ
    start_date = date.today()
    end_date = start_date + timedelta(days=plan.duration_days)

    # حساب المبالغ
    total_amount = plan.price - discount
    remaining_amount = total_amount - paid_amount

    # إنشاء الاشتراك
    subscription = Subscription(
        member_id=member_id,
        plan_id=plan_id,
        brand_id=brand_id,
        start_date=start_date,
        end_date=end_date,
        original_end_date=end_date,
        total_amount=total_amount,
        paid_amount=paid_amount,
        remaining_amount=remaining_amount,
        discount=discount,
        status='active',
        notes=notes,
        created_by=created_by
    )
    db.session.add(subscription)
    db.session.flush()  # للحصول على ID

    # تسجيل الدفعة
    if paid_amount > 0:
        payment = SubscriptionPayment(
            subscription_id=subscription.id,
            brand_id=brand_id,
            amount=paid_amount,
            payment_method='cash',
            created_by=created_by
        )
        db.session.add(payment)

        # تسجيل الدخل
        income = Income(
            brand_id=brand_id,
            subscription_id=subscription.id,
            payment_id=payment.id,
            amount=paid_amount,
            type='subscription',
            date=date.today(),
            created_by=created_by
        )
        db.session.add(income)

    db.session.commit()

    return subscription
```

### 8.2 تجديد اشتراك

```python
def renew_subscription(subscription_id, paid_amount, notes=None, created_by=None):
    """
    تجديد اشتراك قائم
    """

    subscription = Subscription.query.get(subscription_id)
    plan = subscription.plan

    # تحديد تاريخ البداية الجديد
    if subscription.end_date >= date.today():
        # الاشتراك لم ينته بعد - نبدأ من نهايته
        new_start = subscription.end_date
    else:
        # الاشتراك منتهي - نبدأ من اليوم
        new_start = date.today()

    new_end = new_start + timedelta(days=plan.duration_days)

    # تحديث الاشتراك
    subscription.start_date = new_start
    subscription.end_date = new_end
    subscription.original_end_date = new_end
    subscription.total_amount += plan.price
    subscription.paid_amount += paid_amount
    subscription.remaining_amount = subscription.total_amount - subscription.paid_amount
    subscription.status = 'active'

    # تسجيل الدفعة والدخل
    if paid_amount > 0:
        payment = SubscriptionPayment(
            subscription_id=subscription.id,
            brand_id=subscription.brand_id,
            amount=paid_amount,
            payment_method='cash',
            notes=notes,
            created_by=created_by
        )
        db.session.add(payment)

        income = Income(
            brand_id=subscription.brand_id,
            subscription_id=subscription.id,
            amount=paid_amount,
            type='renewal',
            date=date.today(),
            created_by=created_by
        )
        db.session.add(income)

    db.session.commit()

    return subscription
```

### 8.3 تجميد اشتراك

```python
def freeze_subscription(subscription_id, freeze_start, freeze_end,
                       reason=None, created_by=None):
    """
    تجميد اشتراك

    - يتم تمديد تاريخ الانتهاء بعدد أيام التجميد
    - يتم تغيير حالة الاشتراك إلى frozen
    """

    subscription = Subscription.query.get(subscription_id)

    # التحقق من عدد مرات التجميد
    existing_freezes = SubscriptionFreeze.query.filter_by(
        subscription_id=subscription_id
    ).count()

    if existing_freezes >= subscription.plan.max_freezes:
        raise ValueError("تجاوزت الحد الأقصى لمرات التجميد")

    # حساب أيام التجميد
    freeze_start_date = datetime.strptime(freeze_start, '%Y-%m-%d').date()
    freeze_end_date = datetime.strptime(freeze_end, '%Y-%m-%d').date()
    freeze_days = (freeze_end_date - freeze_start_date).days

    if freeze_days > subscription.plan.max_freeze_days:
        raise ValueError(f"الحد الأقصى للتجميد {subscription.plan.max_freeze_days} يوم")

    # تسجيل التجميد
    freeze = SubscriptionFreeze(
        subscription_id=subscription_id,
        freeze_start=freeze_start_date,
        freeze_end=freeze_end_date,
        freeze_days=freeze_days,
        reason=reason,
        created_by=created_by
    )
    db.session.add(freeze)

    # تمديد تاريخ الانتهاء
    subscription.end_date = subscription.end_date + timedelta(days=freeze_days)
    subscription.status = 'frozen'

    db.session.commit()

    return freeze
```

### 8.4 التحقق من صلاحية الحضور

```python
def validate_attendance(member_id):
    """
    التحقق من إمكانية تسجيل حضور العضو

    Returns:
        (can_attend: bool, message: str, subscription: Subscription)
    """

    member = Member.query.get(member_id)

    if not member or not member.is_active:
        return False, "العضو غير موجود أو غير نشط", None

    # البحث عن اشتراك نشط
    subscription = Subscription.query.filter(
        Subscription.member_id == member_id,
        Subscription.status.in_(['active']),
        Subscription.end_date >= date.today()
    ).first()

    if not subscription:
        # التحقق من اشتراك مجمد
        frozen_sub = Subscription.query.filter(
            Subscription.member_id == member_id,
            Subscription.status == 'frozen'
        ).first()

        if frozen_sub:
            return False, "الاشتراك مجمد", frozen_sub

        return False, "لا يوجد اشتراك نشط", None

    # التحقق من عدم انتهاء الاشتراك
    if subscription.end_date < date.today():
        subscription.status = 'expired'
        db.session.commit()
        return False, "الاشتراك منتهي", subscription

    return True, "يمكن تسجيل الحضور", subscription
```

---

## 9. التقارير (Reports)

### 9.1 أنواع التقارير

#### 9.1.1 تقارير مالية
- إجمالي الدخل (يومي/أسبوعي/شهري/سنوي)
- إجمالي المصروفات
- صافي الربح
- تفاصيل المصروفات حسب الفئة
- تقرير الرواتب

#### 9.1.2 تقارير الأعضاء
- عدد الأعضاء الجدد
- عدد الأعضاء النشطين
- الأعضاء المنتهية اشتراكاتهم
- الأعضاء الأكثر حضوراً

#### 9.1.3 تقارير الاشتراكات
- الاشتراكات الجديدة
- التجديدات
- الاشتراكات المجمدة
- الاشتراكات الملغاة
- المبالغ المتبقية (الديون)

#### 9.1.4 تقارير الحضور
- الحضور اليومي
- متوسط الحضور
- أوقات الذروة
- الأعضاء الأقل حضوراً

### 9.2 تصدير التقارير

```python
# app/utils/export.py

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side
from io import BytesIO

def export_to_excel(title, headers, data, rtl=True):
    """
    تصدير البيانات إلى Excel

    Args:
        title: عنوان التقرير
        headers: قائمة العناوين
        data: قائمة من القواميس
        rtl: هل الملف بالعربية

    Returns:
        BytesIO object
    """

    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]  # حد Excel لاسم الورقة

    # إعدادات RTL
    if rtl:
        ws.sheet_view.rightToLeft = True

    # العنوان
    ws.merge_cells(start_row=1, start_column=1,
                   end_row=1, end_column=len(headers))
    ws.cell(1, 1, title)
    ws.cell(1, 1).font = Font(bold=True, size=14)
    ws.cell(1, 1).alignment = Alignment(horizontal='center')

    # رؤوس الأعمدة
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='2563EB',
                              end_color='2563EB',
                              fill_type='solid')

    for col, header in enumerate(headers, 1):
        cell = ws.cell(3, col, header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')

    # البيانات
    for row_num, row_data in enumerate(data, 4):
        for col, header in enumerate(headers, 1):
            key = header  # أو استخدم mapping
            value = row_data.get(key, '')
            ws.cell(row_num, col, value)

    # تعديل عرض الأعمدة
    for col in ws.columns:
        max_length = 0
        for cell in col:
            if cell.value:
                max_length = max(max_length, len(str(cell.value)))
        ws.column_dimensions[col[0].column_letter].width = max_length + 2

    # حفظ في BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return output
```

---

## 10. خطة النشر (Deployment Plan)

### 10.1 Railway Deployment

#### المتطلبات
```
# requirements.txt
Flask==3.0.0
Flask-SQLAlchemy==3.1.1
Flask-Login==0.6.3
Flask-Migrate==4.0.5
Flask-WTF==1.2.1
Werkzeug==3.0.1
psycopg2-binary==2.9.9
python-dotenv==1.0.0
gunicorn==21.2.0
openpyxl==3.1.2
Pillow==10.1.0
```

#### Procfile
```
web: gunicorn run:app
```

#### runtime.txt
```
python-3.11.7
```

#### متغيرات البيئة (Environment Variables)
```
# Database
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# Flask
FLASK_APP=run.py
FLASK_ENV=production
SECRET_KEY=your-super-secret-key

# Fingerprint API
FINGERPRINT_API_KEY=your-fingerprint-api-key

# Upload
MAX_CONTENT_LENGTH=16777216
UPLOAD_FOLDER=app/static/uploads
```

### 10.2 خطوات النشر

```bash
# 1. إنشاء مشروع على Railway
railway login
railway init

# 2. إضافة PostgreSQL
railway add postgresql

# 3. رفع الكود
git push railway main

# 4. تشغيل migrations
railway run flask db upgrade

# 5. إنشاء المستخدم الأول (Owner)
railway run flask create-admin
```

### 10.3 إعداد Bridge Service في الجيم

```
1. تثبيت Python على كمبيوتر الجيم
2. نسخ مجلد fingerprint_bridge
3. تعديل config.py بالإعدادات الصحيحة
4. تشغيل الخدمة:
   python main.py

5. (اختياري) تحويلها لخدمة Windows:
   - استخدام NSSM (Non-Sucking Service Manager)
   - أو Task Scheduler
```

---

## 11. مراحل التنفيذ (Implementation Phases)

### المرحلة 1: الأساسيات
- [ ] إعداد المشروع وهيكل الملفات
- [ ] إنشاء قاعدة البيانات والـ Models
- [ ] نظام تسجيل الدخول والصلاحيات
- [ ] القالب الأساسي للواجهة (RTL)

### المرحلة 2: إدارة البراندات
- [ ] لوحة تحكم المالك
- [ ] CRUD للبراندات
- [ ] CRUD للفروع
- [ ] CRUD للمستخدمين
- [ ] CRUD للباقات

### المرحلة 3: الأعضاء والاشتراكات
- [ ] إضافة/تعديل/عرض الأعضاء
- [ ] إنشاء اشتراك جديد
- [ ] تجديد اشتراك
- [ ] تجميد اشتراك
- [ ] سداد دفعات

### المرحلة 4: الحضور
- [ ] تسجيل حضور يدوي
- [ ] صفحة البحث السريع
- [ ] التحقق من صلاحية الاشتراك
- [ ] سجل الحضور

### المرحلة 5: المالية
- [ ] تسجيل المصروفات
- [ ] عرض الدخل
- [ ] إدارة الرواتب
- [ ] المرتجعات

### المرحلة 6: التقارير
- [ ] التقارير المالية
- [ ] تقارير الأعضاء
- [ ] تقارير الحضور
- [ ] تصدير Excel/PDF

### المرحلة 7: تكامل البصمة
- [ ] REST API للبصمة
- [ ] Bridge Service
- [ ] اختبار التكامل
- [ ] توثيق الإعداد

### المرحلة 8: النشر والاختبار
- [ ] نشر على Railway
- [ ] إعداد البصمة في الجيم
- [ ] اختبار شامل
- [ ] تدريب المستخدمين

---

## 12. ملاحظات إضافية

### 12.1 الأمان
- تشفير كلمات المرور باستخدام Werkzeug
- CSRF protection في جميع النماذج
- التحقق من الصلاحيات في كل endpoint
- API Key للتواصل مع Bridge Service
- HTTPS إجباري في الإنتاج

### 12.2 الأداء
- Indexing على الأعمدة المستخدمة في البحث
- Pagination للقوائم الطويلة
- Caching للتقارير
- Lazy loading للصور

### 12.3 النسخ الاحتياطي
- نسخ احتياطي يومي لقاعدة البيانات
- نسخ احتياطي للملفات المرفوعة
- الاحتفاظ بآخر 30 نسخة

---

## 13. المراجع والموارد

### التوثيق
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Flask-SQLAlchemy](https://flask-sqlalchemy.palletsprojects.com/)
- [Bootstrap 5 RTL](https://getbootstrap.com/docs/5.3/getting-started/rtl/)
- [Railway Documentation](https://docs.railway.app/)

### أدوات
- [DB Browser for SQLite](https://sqlitebrowser.org/) - للتطوير المحلي
- [Postman](https://www.postman.com/) - لاختبار API
- [netconfig.exe](./AAS6.0/Access%20Controller/netconfig/) - لإعداد جهاز البصمة

---

---

## 14. نظام التحكم بالبراندات (Brand Control System)

### 14.1 هيكل الصلاحيات المحدث

```
                    ┌─────────────────┐
                    │     Owner       │
                    │   (المالك)      │
                    │ يرى كل البراندات│
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│    Brand A      │ │    Brand B      │ │    Brand C      │
│  (مع بصمة)      │ │   (بدون بصمة)   │ │   (بدون بصمة)   │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  Brand Manager  │ │  Brand Manager  │ │  Brand Manager  │
│ (مدير البراند)  │ │ (مدير البراند)  │ │ (مدير البراند)  │
│تحكم كامل ببرانده│ │تحكم كامل ببرانده│ │تحكم كامل ببرانده│
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
    ┌────┴────┐         ┌────┴────┐         ┌────┴────┐
    ▼         ▼         ▼         ▼         ▼         ▼
┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐
│Recep. │ │Finance│ │Recep. │ │Finance│ │Recep. │ │Finance│
│Coach  │ │       │ │Coach  │ │       │ │Coach  │ │       │
└───────┘ └───────┘ └───────┘ └───────┘ └───────┘ └───────┘
```

### 14.2 الأدوار المحدثة

| الدور | الوصف | نطاق الوصول |
|-------|-------|-------------|
| **Owner** | مالك النظام | جميع البراندات - تحكم كامل |
| **Brand Manager** | مدير براند واحد | براند واحد - تحكم كامل |
| **Receptionist** | موظف استقبال | براند واحد - العملاء والاشتراكات |
| **Finance** | مالية براند | براند واحد - العمليات المالية |
| **Finance Admin** | مالية عامة | جميع البراندات - تقارير فقط |
| **Coach** | مدرب | براند واحد - بياناته فقط |

### 14.3 سير عمل إنشاء براند جديد

```
┌─────────────────────────────────────────────────────────────────┐
│                     إنشاء براند جديد                            │
└─────────────────────────────────────────────────────────────────┘

1. Owner يسجل دخول للنظام
   ↓
2. من لوحة التحكم → إدارة البراندات → إضافة براند جديد
   ↓
3. إدخال بيانات البراند:
   ┌─────────────────────────────────────────┐
   │  اسم البراند: [_________________]       │
   │  الشعار: [اختر صورة]                   │
   │  ☑ تفعيل البراند                       │
   │  ☐ يستخدم نظام البصمة                  │
   │                                         │
   │  إعدادات البصمة (إذا مفعل):            │
   │  IP جهاز البصمة: [192.168.1.224]       │
   │  Port: [5005]                          │
   └─────────────────────────────────────────┘
   ↓
4. حفظ البراند
   ↓
5. إنشاء مستخدم Brand Manager للبراند:
   ┌─────────────────────────────────────────┐
   │  الاسم: [_________________]             │
   │  البريد: [_________________]            │
   │  كلمة المرور: [_________________]       │
   │  الدور: [Brand Manager ▼]               │
   │  البراند: [البراند الجديد ▼]            │
   └─────────────────────────────────────────┘
   ↓
6. Brand Manager يستلم بيانات الدخول
   ↓
7. Brand Manager يبدأ بإعداد البراند:
   - إضافة الفروع (إن وجدت)
   - إضافة باقات الاشتراك
   - إضافة الموظفين (Receptionist, Finance, Coach)
   - إضافة الأعضاء
```

### 14.4 صلاحيات Brand Manager

```python
# صلاحيات مدير البراند

class BrandManagerPermissions:
    """
    مدير البراند له تحكم كامل في برانده فقط
    """

    # ✅ يمكنه:
    can_manage_branches = True      # إدارة الفروع
    can_manage_plans = True         # إدارة الباقات
    can_manage_staff = True         # إدارة الموظفين (ما عدا Brand Manager آخر)
    can_manage_members = True       # إدارة الأعضاء
    can_manage_subscriptions = True # إدارة الاشتراكات
    can_view_finance = True         # عرض المالية
    can_manage_expenses = True      # إدارة المصروفات
    can_manage_salaries = True      # إدارة الرواتب
    can_view_reports = True         # عرض التقارير
    can_export_reports = True       # تصدير التقارير

    # ❌ لا يمكنه:
    can_create_brand = False        # إنشاء براند جديد
    can_delete_brand = False        # حذف براند
    can_view_other_brands = False   # عرض براندات أخرى
    can_create_brand_manager = False # إنشاء مدير براند آخر
```

### 14.5 واجهة Brand Manager

```
┌─────────────────────────────────────────────────────────────────┐
│  🏢 لوحة تحكم: [اسم البراند]                    [أحمد ▼] [خروج] │
├──────────┬──────────────────────────────────────────────────────┤
│          │                                                      │
│  القائمة │              إحصائيات البراند                        │
│          │   ┌──────────┬──────────┬──────────┬──────────┐     │
│ 📊 الرئيسية│   │ الأعضاء  │الاشتراكات│  الدخل   │المصروفات │     │
│ 👥 الأعضاء │   │   150    │   120    │ 50,000  │  15,000  │     │
│ 📋 الاشتراك│   │  +12 🔺  │  +8 🔺   │ هذا الشهر│ هذا الشهر│     │
│ ✓ الحضور  │   └──────────┴──────────┴──────────┴──────────┘     │
│ 💰 المالية │                                                      │
│ 📈 التقارير│   ┌─────────────────────────────────────────────┐   │
│ ⚙️ الإعدادات│   │            الحضور اليوم: 45                 │   │
│   - الفروع │   │  [=============================] 75%        │   │
│   - الباقات│   └─────────────────────────────────────────────┘   │
│   - الموظفين│                                                     │
│          │   ┌──────────────────┐  ┌──────────────────────────┐ │
│          │   │ اشتراكات تنتهي   │  │    آخر العمليات          │ │
│          │   │ قريباً (7 أيام)  │  │ - اشتراك جديد: أحمد     │ │
│          │   │                  │  │ - تجديد: سارة           │ │
│          │   │ • محمد (3 أيام) │  │ - حضور: 45 عضو          │ │
│          │   │ • فاطمة (5 أيام)│  │                          │ │
│          │   └──────────────────┘  └──────────────────────────┘ │
└──────────┴──────────────────────────────────────────────────────┘
```

---

## 15. ترحيل البيانات من AAS (Data Migration from AAS)

### 15.1 نظرة عامة

```
┌─────────────────────────────────────────────────────────────────┐
│                    الوضع الحالي في الجيم                        │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │              AAS Software (Windows PC)                   │  │
│   │                                                          │  │
│   │   قاعدة البيانات تحتوي على:                              │  │
│   │   • بيانات الأعضاء (الاسم، ID، البصمة)                   │  │
│   │   • سجلات الحضور التاريخية                               │  │
│   │   • إعدادات الجهاز                                       │  │
│   │                                                          │  │
│   │   الموقع المحتمل للقاعدة:                                 │  │
│   │   C:\Program Files\AAS\data\att2000.mdb                  │  │
│   │   أو                                                      │  │
│   │   C:\AAS\att2000.mdb                                     │  │
│   └─────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │              Fingerprint Controller                      │  │
│   │              (192.168.1.224:5005)                        │  │
│   │                                                          │  │
│   │   يحتوي على:                                             │  │
│   │   • بصمات الأعضاء المسجلة                                │  │
│   │   • سجلات الحضور المحلية                                 │  │
│   └─────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 15.2 خطة الترحيل

```
┌─────────────────────────────────────────────────────────────────┐
│                      خطوات الترحيل                              │
└─────────────────────────────────────────────────────────────────┘

الخطوة 1: تحديد موقع قاعدة بيانات AAS
─────────────────────────────────────────
• فتح برنامج AAS على كمبيوتر الجيم
• من القائمة: Settings → Database Path
• أو البحث عن: att2000.mdb, att2003.mdb, Access.mdb

الخطوة 2: تصدير بيانات الأعضاء من AAS
─────────────────────────────────────────
• من برنامج AAS: Personnel → Export
• تصدير إلى Excel أو CSV
• البيانات المطلوبة:
  - User ID (رقم البصمة)
  - Name (الاسم)
  - Card Number (رقم البطاقة إن وجد)

الخطوة 3: تجهيز ملف الاستيراد
─────────────────────────────────────────
إنشاء ملف Excel بالتنسيق التالي:

| fingerprint_id | name      | phone       | email           |
|----------------|-----------|-------------|-----------------|
| 1              | أحمد محمد | 0551234567 | ahmed@email.com |
| 2              | سارة علي  | 0559876543 | sara@email.com  |
| ...            | ...       | ...         | ...             |

الخطوة 4: استيراد في النظام الجديد
─────────────────────────────────────────
• تسجيل دخول كـ Owner أو Brand Manager
• الإعدادات → استيراد الأعضاء
• اختيار البراند (الذي يستخدم البصمة)
• رفع ملف Excel
• مراجعة البيانات
• تأكيد الاستيراد

الخطوة 5: التحقق من المطابقة
─────────────────────────────────────────
• التأكد من تطابق fingerprint_id في النظام الجديد
  مع User ID في جهاز البصمة
• اختبار: عضو يسجل حضور بالبصمة → يظهر في النظام
```

### 15.3 هيكل قاعدة بيانات AAS (للمرجعية)

```
قاعدة بيانات AAS النموذجية (Access .mdb):

┌─────────────────────────────────────────────────────────────────┐
│ USERINFO (جدول الأعضاء)                                         │
├─────────────────────────────────────────────────────────────────┤
│ USERID        INT         - رقم المستخدم (مطابق لـ fingerprint_id)│
│ Badgenumber   VARCHAR     - رقم البطاقة                          │
│ Name          VARCHAR     - الاسم                                │
│ Gender        VARCHAR     - الجنس                                │
│ Birthday      DATETIME    - تاريخ الميلاد                        │
│ Address       VARCHAR     - العنوان                              │
│ OPHONE        VARCHAR     - هاتف المكتب                          │
│ PESSION       VARCHAR     - رقم الهوية                           │
│ TITLE         VARCHAR     - المسمى                               │
│ HIREDDAY      DATETIME    - تاريخ التسجيل                        │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ CHECKINOUT (جدول الحضور)                                        │
├─────────────────────────────────────────────────────────────────┤
│ USERID        INT         - رقم المستخدم                         │
│ CHECKTIME     DATETIME    - وقت التسجيل                          │
│ CHECKTYPE     VARCHAR     - نوع (دخول/خروج)                      │
│ VERIFYCODE    INT         - طريقة التحقق (بصمة/بطاقة)            │
│ SENSORID      INT         - رقم الجهاز                           │
└─────────────────────────────────────────────────────────────────┘
```

### 15.4 أداة الترحيل (Migration Tool)

```python
# app/utils/migration.py

import pandas as pd
from app.models import Member, Brand
from app import db

def import_members_from_excel(file_path, brand_id, created_by):
    """
    استيراد الأعضاء من ملف Excel

    الأعمدة المطلوبة:
    - fingerprint_id: رقم البصمة (إجباري)
    - name: الاسم (إجباري)
    - phone: رقم الهاتف (إجباري)
    - email: البريد (اختياري)
    - gender: الجنس (اختياري)
    - national_id: رقم الهوية (اختياري)

    Returns:
        dict: {
            'success': int,
            'failed': int,
            'errors': list
        }
    """

    df = pd.read_excel(file_path)

    results = {
        'success': 0,
        'failed': 0,
        'errors': []
    }

    for index, row in df.iterrows():
        try:
            # التحقق من البيانات الإجبارية
            if pd.isna(row.get('fingerprint_id')):
                raise ValueError(f"السطر {index+2}: رقم البصمة مطلوب")

            if pd.isna(row.get('name')):
                raise ValueError(f"السطر {index+2}: الاسم مطلوب")

            if pd.isna(row.get('phone')):
                raise ValueError(f"السطر {index+2}: رقم الهاتف مطلوب")

            # التحقق من عدم وجود العضو مسبقاً
            existing = Member.query.filter_by(
                brand_id=brand_id,
                fingerprint_id=int(row['fingerprint_id'])
            ).first()

            if existing:
                raise ValueError(f"السطر {index+2}: رقم البصمة {row['fingerprint_id']} موجود مسبقاً")

            # إنشاء العضو
            member = Member(
                brand_id=brand_id,
                fingerprint_id=int(row['fingerprint_id']),
                name=str(row['name']).strip(),
                phone=str(row['phone']).strip(),
                email=row.get('email') if not pd.isna(row.get('email')) else None,
                gender=row.get('gender') if not pd.isna(row.get('gender')) else None,
                national_id=row.get('national_id') if not pd.isna(row.get('national_id')) else None,
                fingerprint_enrolled=True,  # لأنه موجود في AAS
                fingerprint_enrolled_at=datetime.utcnow(),
                created_by=created_by
            )
            db.session.add(member)
            results['success'] += 1

        except Exception as e:
            results['failed'] += 1
            results['errors'].append(str(e))

    if results['success'] > 0:
        db.session.commit()

    return results


def export_members_template():
    """
    إنشاء قالب Excel لاستيراد الأعضاء
    """
    df = pd.DataFrame(columns=[
        'fingerprint_id',
        'name',
        'phone',
        'email',
        'gender',
        'national_id'
    ])

    # إضافة صف مثال
    df.loc[0] = [1, 'أحمد محمد', '0551234567', 'ahmed@email.com', 'male', '1234567890']

    return df
```

### 15.5 صفحة الاستيراد

```
┌─────────────────────────────────────────────────────────────────┐
│                    استيراد الأعضاء من ملف                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  📥 خطوات الاستيراد:                                            │
│                                                                 │
│  1. قم بتحميل القالب ← [تحميل قالب Excel]                       │
│                                                                 │
│  2. أضف بيانات الأعضاء للقالب:                                  │
│     • fingerprint_id: رقم البصمة من نظام AAS (إجباري)          │
│     • name: اسم العضو (إجباري)                                  │
│     • phone: رقم الهاتف (إجباري)                                │
│     • email: البريد الإلكتروني (اختياري)                        │
│     • gender: الجنس male/female (اختياري)                       │
│     • national_id: رقم الهوية (اختياري)                         │
│                                                                 │
│  3. ارفع الملف:                                                 │
│     ┌─────────────────────────────────────────────────────┐    │
│     │  📁 اسحب الملف هنا أو انقر للاختيار                 │    │
│     │                                                      │    │
│     │     يقبل: .xlsx, .xls                               │    │
│     └─────────────────────────────────────────────────────┘    │
│                                                                 │
│  4. [معاينة البيانات]                                          │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ معاينة (أول 5 صفوف):                                    │   │
│  ├───────────────┬──────────────┬─────────────┬───────────┤   │
│  │ fingerprint_id│ name         │ phone       │ email     │   │
│  ├───────────────┼──────────────┼─────────────┼───────────┤   │
│  │ 1             │ أحمد محمد    │ 0551234567 │ ahmed@... │   │
│  │ 2             │ سارة علي     │ 0559876543 │ sara@...  │   │
│  │ 3             │ محمد خالد    │ 0557654321 │ -         │   │
│  └───────────────┴──────────────┴─────────────┴───────────┘   │
│                                                                 │
│  إجمالي: 150 عضو                                               │
│                                                                 │
│                        [إلغاء]  [تأكيد الاستيراد]               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 16. تدفق العمل اليومي (Daily Workflow)

### 16.1 سيناريو: يوم عمل في البراند الذي يستخدم البصمة

```
┌─────────────────────────────────────────────────────────────────┐
│                        الساعة 6:00 صباحاً                        │
│                     (بداية يوم العمل)                           │
└─────────────────────────────────────────────────────────────────┘

1. موظف الاستقبال يسجل دخول للنظام
   URL: https://gym-system.railway.app/login
   ↓
2. يظهر له لوحة التحكم مع:
   • إحصائيات اليوم
   • اشتراكات تنتهي اليوم
   • إجراءات سريعة

┌─────────────────────────────────────────────────────────────────┐
│                     عضو جديد يريد التسجيل                       │
└─────────────────────────────────────────────────────────────────┘

1. موظف الاستقبال → الأعضاء → إضافة عضو جديد
   ↓
2. إدخال بيانات العضو (اسم، هاتف، إلخ)
   ↓
3. اختيار باقة الاشتراك
   ↓
4. إدخال المبلغ المدفوع
   ↓
5. حفظ ← النظام ينشئ:
   • سجل العضو
   • اشتراك نشط
   • سجل دخل
   ↓
6. يظهر تنبيه: "⚠️ هذا العضو يحتاج تسجيل بصمة"
   ↓
7. موظف الاستقبال يفتح برنامج AAS على نفس الكمبيوتر
   ↓
8. Personnel → Add → يدخل نفس الـ fingerprint_id
   ↓
9. العضو يسجل بصمته على القارئ
   ↓
10. Bridge Service تكتشف التسجيل ← ترسل للسحابة
    ↓
11. النظام يحدث: fingerprint_enrolled = True

┌─────────────────────────────────────────────────────────────────┐
│                   عضو حالي يدخل الجيم                           │
└─────────────────────────────────────────────────────────────────┘

1. العضو يضع إصبعه على قارئ البصمة
   ↓
2. جهاز البصمة:
   • يتعرف على البصمة ✓
   • يفتح الباب ✓
   • يسجل الحدث في الذاكرة
   ↓
3. Bridge Service (كل 30 ثانية):
   • تقرأ السجلات الجديدة
   • ترسل للسحابة
   ↓
4. السحابة:
   • تبحث عن العضو بـ fingerprint_id
   • تتحقق من الاشتراك:
     - نشط ✓
     - غير مجمد ✓
     - غير منتهي ✓
   • تسجل الحضور
   ↓
5. الحضور يظهر في:
   • لوحة التحكم (الحضور اليوم: +1)
   • تقارير الحضور
   • سجل العضو

┌─────────────────────────────────────────────────────────────────┐
│              عضو منتهي اشتراكه يحاول الدخول                     │
└─────────────────────────────────────────────────────────────────┘

السيناريو 1: إذا كان جهاز البصمة مبرمج لرفض المنتهي
1. العضو يضع بصمته
2. الجهاز يرفض (لم يتم تحديث صلاحياته)
3. العضو يتوجه للاستقبال
4. موظف الاستقبال يجدد الاشتراك

السيناريو 2: إذا كان الجهاز يقبل الجميع (الأكثر شيوعاً)
1. العضو يضع بصمته
2. الجهاز يفتح الباب (لا يعرف حالة الاشتراك)
3. السجل يصل للسحابة
4. السحابة تكتشف: اشتراك منتهي ⚠️
5. تسجل الحضور مع علامة تحذير
6. يظهر تنبيه لموظف الاستقبال
7. موظف الاستقبال يتواصل مع العضو

ملاحظة: لتفعيل السيناريو 1، يجب برمجة جهاز البصمة
        لمزامنة قائمة الأعضاء النشطين فقط
```

### 16.2 سيناريو: يوم عمل في براند بدون بصمة

```
┌─────────────────────────────────────────────────────────────────┐
│                   عضو يدخل الجيم                                │
└─────────────────────────────────────────────────────────────────┘

1. العضو يصل للاستقبال
   ↓
2. موظف الاستقبال يبحث عن العضو:
   • بالاسم
   • برقم الهاتف
   • بالـ QR Code (إذا كان لديه)
   ↓
3. النظام يعرض بيانات العضو:
   ┌─────────────────────────────────────────┐
   │ 👤 أحمد محمد السيد                     │
   │ ─────────────────────────────────────── │
   │ الباقة: شهرية                          │
   │ تنتهي في: 2024-02-15                   │
   │ الحالة: ✅ نشط                          │
   │                                         │
   │ [✓ تسجيل الدخول]                       │
   └─────────────────────────────────────────┘
   ↓
4. موظف الاستقبال يضغط "تسجيل الدخول"
   ↓
5. النظام:
   • يتحقق من الاشتراك ✓
   • يسجل الحضور
   • يظهر رسالة نجاح
```

---

## 17. الأسئلة الشائعة (FAQ)

### س: ماذا لو انقطع الإنترنت في الجيم؟
```
ج: جهاز البصمة يعمل بشكل مستقل:
   • يفتح الباب للأعضاء المسجلين
   • يحفظ سجلات الحضور محلياً
   • عند عودة الإنترنت، Bridge Service ترسل كل السجلات
```

### س: ماذا لو توقف Bridge Service؟
```
ج: • جهاز البصمة يستمر في العمل
   • السجلات تتراكم في الجهاز
   • عند إعادة تشغيل Bridge، يتم مزامنة كل السجلات
   • يُنصح بإعداد Bridge كخدمة Windows تعمل تلقائياً
```

### س: كيف أعرف أن المزامنة تعمل؟
```
ج: • لوحة التحكم تعرض "آخر مزامنة: منذ X دقيقة"
   • صفحة حالة النظام تعرض تفاصيل المزامنة
   • تنبيه تلقائي إذا توقفت المزامنة لأكثر من 5 دقائق
```

### س: هل يمكن لعضو واحد الاشتراك في أكثر من براند؟
```
ج: لا، كل عضو مرتبط ببراند واحد فقط.
   إذا أراد الاشتراك في براند آخر، يجب إنشاء سجل جديد.
```

---

> **آخر تحديث:** يناير 2026
> **إعداد:** نظام إدارة الجيم متعدد البراندات
