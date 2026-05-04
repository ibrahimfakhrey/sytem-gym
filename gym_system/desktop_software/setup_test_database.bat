@echo off
chcp 65001 >nul
echo ============================================================
echo   Setting up Test Database for Gym Management System
echo ============================================================
echo.

REM Get script directory
set "SCRIPT_DIR=%~dp0"
set "TEST_DB_DIR=%SCRIPT_DIR%test_database"
set "DB_FILE=%TEST_DB_DIR%\test_attendance.mdb"

REM Check if database exists
if not exist "%DB_FILE%" (
    echo ERROR: test_attendance.mdb not found!
    echo Please copy the test_attendance.mdb file to: %TEST_DB_DIR%
    pause
    exit /b 1
)

echo Found database: %DB_FILE%
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found. Trying to run directly with pyodbc...
    goto :try_vbs
)

echo Running Python seed script...
python "%SCRIPT_DIR%seed_test_data.py"
if %errorlevel%==0 (
    echo.
    echo SUCCESS! Database has been populated with test data.
    goto :done
)

:try_vbs
echo.
echo Trying alternative method with VBScript...

REM Create VBScript to import data
echo Set conn = CreateObject("ADODB.Connection") > "%TEMP%\import_data.vbs"
echo conn.Open "Provider=Microsoft.Jet.OLEDB.4.0;Data Source=%DB_FILE%;" >> "%TEMP%\import_data.vbs"
echo. >> "%TEMP%\import_data.vbs"
echo ' Insert Departments >> "%TEMP%\import_data.vbs"
echo On Error Resume Next >> "%TEMP%\import_data.vbs"
echo conn.Execute "INSERT INTO Depart (depart_id, depart_name) VALUES ('00000001', 'الأعضاء')" >> "%TEMP%\import_data.vbs"
echo conn.Execute "INSERT INTO Depart (depart_id, depart_name) VALUES ('00000002', 'المدربين')" >> "%TEMP%\import_data.vbs"
echo conn.Execute "INSERT INTO Depart (depart_id, depart_name) VALUES ('00000003', 'الإدارة')" >> "%TEMP%\import_data.vbs"
echo. >> "%TEMP%\import_data.vbs"
echo ' Insert Sample Employees >> "%TEMP%\import_data.vbs"
echo conn.Execute "INSERT INTO Employee (emp_id, card_id, emp_name, depart_id, sex, phone_code, hire_date, end_date) VALUES ('00000001', '0000000001', 'محمد العلي', '00000001', '0', '0501234567', #2024-01-01#, #2026-12-31#)" >> "%TEMP%\import_data.vbs"
echo conn.Execute "INSERT INTO Employee (emp_id, card_id, emp_name, depart_id, sex, phone_code, hire_date, end_date) VALUES ('00000002', '0000000002', 'أحمد الحسن', '00000001', '0', '0551234567', #2024-02-01#, #2026-12-31#)" >> "%TEMP%\import_data.vbs"
echo conn.Execute "INSERT INTO Employee (emp_id, card_id, emp_name, depart_id, sex, phone_code, hire_date, end_date) VALUES ('00000003', '0000000003', 'فاطمة المحمد', '00000001', '1', '0531234567', #2024-03-01#, #2026-12-31#)" >> "%TEMP%\import_data.vbs"
echo conn.Execute "INSERT INTO Employee (emp_id, card_id, emp_name, depart_id, sex, phone_code, hire_date, end_date) VALUES ('00000004', '0000000004', 'خالد السعيد', '00000001', '0', '0541234567', #2024-04-01#, #2026-12-31#)" >> "%TEMP%\import_data.vbs"
echo conn.Execute "INSERT INTO Employee (emp_id, card_id, emp_name, depart_id, sex, phone_code, hire_date, end_date) VALUES ('00000005', '0000000005', 'نورة العمر', '00000001', '1', '0561234567', #2024-05-01#, #2026-12-31#)" >> "%TEMP%\import_data.vbs"
echo conn.Execute "INSERT INTO Employee (emp_id, card_id, emp_name, depart_id, sex, phone_code, hire_date, end_date) VALUES ('00000006', '0000000006', 'عبدالله الناصر', '00000001', '0', '0591234567', #2024-01-15#, #2025-01-01#)" >> "%TEMP%\import_data.vbs"
echo conn.Execute "INSERT INTO Employee (emp_id, card_id, emp_name, depart_id, sex, phone_code, hire_date, end_date) VALUES ('00000007', '0000000007', 'سارة الفهد', '00000001', '1', '0501234568', #2024-06-01#, #2026-12-31#)" >> "%TEMP%\import_data.vbs"
echo conn.Execute "INSERT INTO Employee (emp_id, card_id, emp_name, depart_id, sex, phone_code, hire_date, end_date) VALUES ('00000008', '0000000008', 'يوسف السلطان', '00000001', '0', '0551234568', #2024-07-01#, #2026-12-31#)" >> "%TEMP%\import_data.vbs"
echo conn.Execute "INSERT INTO Employee (emp_id, card_id, emp_name, depart_id, sex, phone_code, hire_date, end_date) VALUES ('00000009', '0000000009', 'مريم الخالد', '00000001', '1', '0531234568', #2024-08-01#, #2026-12-31#)" >> "%TEMP%\import_data.vbs"
echo conn.Execute "INSERT INTO Employee (emp_id, card_id, emp_name, depart_id, sex, phone_code, hire_date, end_date) VALUES ('00000010', '0000000010', 'علي الشمري', '00000001', '0', '0541234568', #2024-09-01#, #2026-12-31#)" >> "%TEMP%\import_data.vbs"
echo. >> "%TEMP%\import_data.vbs"
echo conn.Close >> "%TEMP%\import_data.vbs"
echo WScript.Echo "Data imported successfully!" >> "%TEMP%\import_data.vbs"

cscript //nologo "%TEMP%\import_data.vbs"
if %errorlevel%==0 (
    echo.
    echo SUCCESS! Database has been populated with 10 test members.
)

:done
echo.
echo ============================================================
echo   Database Location: %DB_FILE%
echo   No password required!
echo ============================================================
echo.
pause
