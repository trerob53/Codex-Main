@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo   Cerasus Hub - Build EXE
echo ============================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH.
    pause
    exit /b 1
)

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt --quiet

echo.
echo Building Cerasus Hub EXE...
echo.

pyinstaller --clean --onefile --noconsole --name CerasusHub ^
    --add-data "src;src" ^
    --hidden-import PySide6.QtWidgets ^
    --hidden-import PySide6.QtCore ^
    --hidden-import PySide6.QtGui ^
    --hidden-import PySide6.QtPrintSupport ^
    --hidden-import sqlite3 ^
    --hidden-import qrcode ^
    --hidden-import PIL ^
    --hidden-import pypdf ^
    --hidden-import pypdf.generic ^
    --hidden-import src.config ^
    --hidden-import src.database ^
    --hidden-import src.auth ^
    --hidden-import src.audit ^
    --hidden-import src.lock_manager ^
    --hidden-import src.session_manager ^
    --hidden-import src.hub_gui ^
    --hidden-import src.shared_widgets ^
    --hidden-import src.shared_data ^
    --hidden-import src.notifications ^
    --hidden-import src.notification_ui ^
    --hidden-import src.backup_manager ^
    --hidden-import src.hub_backups ^
    --hidden-import src.pages_activity_feed ^
    --hidden-import src.pages_site_dashboard ^
    --hidden-import src.pages_site_comparison ^
    --hidden-import src.pages_task_queue ^
    --hidden-import src.search_engine ^
    --hidden-import src.executive_report ^
    --hidden-import src.announcements ^
    --hidden-import src.document_vault ^
    --hidden-import src.custom_fields ^
    --hidden-import src.change_password_dialog ^
    --hidden-import src.user_management ^
    --hidden-import src.analytics_engine ^
    --hidden-import src.hub_analytics ^
    --hidden-import src.hub_audit_viewer ^
    --hidden-import src.hub_people ^
    --hidden-import src.loading_overlay ^
    --hidden-import src.officer_360 ^
    --hidden-import src.officer_profile ^
    --hidden-import src.pdf_export ^
    --hidden-import src.permissions ^
    --hidden-import src.print_helper ^
    --hidden-import src.report_builder ^
    --hidden-import src.report_generator ^
    --hidden-import src.scheduled_reports ^
    --hidden-import src.form_validation ^
    --hidden-import src.db_tools ^
    --hidden-import src.web_companion ^
    --hidden-import src.modules.operations ^
    --hidden-import src.modules.uniforms ^
    --hidden-import src.modules.attendance ^
    --hidden-import src.modules.training ^
    --hidden-import src.modules.da_generator ^
    --hidden-import src.modules.incidents ^
    --hidden-import src.modules.overtime ^
    --hidden-import src.modules.operations.pages_dashboard ^
    --hidden-import src.modules.operations.pages_flex_board ^
    --hidden-import src.modules.operations.pages_ops ^
    --hidden-import src.modules.operations.pages_pto ^
    --hidden-import src.modules.operations.pages_admin ^
    --hidden-import src.modules.operations.pages_handoff ^
    --hidden-import src.modules.operations.pages_incidents ^
    --hidden-import src.modules.operations.data_manager ^
    --hidden-import src.modules.operations.migrations ^
    --hidden-import src.modules.uniforms.pages_dashboard ^
    --hidden-import src.modules.uniforms.pages_personnel ^
    --hidden-import src.modules.uniforms.pages_sites ^
    --hidden-import src.modules.uniforms.pages_uniform ^
    --hidden-import src.modules.uniforms.pages_inventory ^
    --hidden-import src.modules.uniforms.pages_compliance ^
    --hidden-import src.modules.uniforms.pages_admin ^
    --hidden-import src.modules.uniforms.data_manager ^
    --hidden-import src.modules.uniforms.migrations ^
    --hidden-import src.modules.uniforms.email_service ^
    --hidden-import src.modules.uniforms.notification_log ^
    --hidden-import src.modules.uniforms.qr_labels ^
    --hidden-import src.modules.attendance.pages_dashboard ^
    --hidden-import src.modules.attendance.pages_roster ^
    --hidden-import src.modules.attendance.pages_infractions ^
    --hidden-import src.modules.attendance.pages_discipline ^
    --hidden-import src.modules.attendance.pages_reviews ^
    --hidden-import src.modules.attendance.pages_reports ^
    --hidden-import src.modules.attendance.pages_admin ^
    --hidden-import src.modules.attendance.pages_import ^
    --hidden-import src.modules.attendance.pages_bulk_import ^
    --hidden-import src.modules.attendance.data_manager ^
    --hidden-import src.modules.attendance.migrations ^
    --hidden-import src.modules.attendance.duplicate_scanner ^
    --hidden-import src.modules.attendance.policy_engine ^
    --hidden-import src.modules.attendance.risk_engine ^
    --hidden-import src.modules.training.pages_dashboard ^
    --hidden-import src.modules.training.pages_courses ^
    --hidden-import src.modules.training.pages_leaderboard ^
    --hidden-import src.modules.training.pages_certificates ^
    --hidden-import src.modules.training.pages_admin ^
    --hidden-import src.modules.training.data_manager ^
    --hidden-import src.modules.training.migrations ^
    --hidden-import src.modules.da_generator.pages_wizard ^
    --hidden-import src.modules.da_generator.pages_history ^
    --hidden-import src.modules.da_generator.pages_settings ^
    --hidden-import src.modules.da_generator.pages_templates ^
    --hidden-import src.modules.da_generator.data_manager ^
    --hidden-import src.modules.da_generator.migrations ^
    --hidden-import src.modules.da_generator.api_client ^
    --hidden-import src.modules.da_generator.ceis_prompts ^
    --hidden-import src.modules.da_generator.local_engine ^
    --hidden-import src.modules.da_generator.pdf_filler ^
    --hidden-import src.modules.incidents.pages_dashboard ^
    --hidden-import src.modules.incidents.pages_incidents ^
    --hidden-import src.modules.incidents.pages_admin ^
    --hidden-import src.modules.incidents.data_manager ^
    --hidden-import src.modules.incidents.migrations ^
    --hidden-import src.modules.overtime.pages_dashboard ^
    --hidden-import src.modules.overtime.pages_analysis ^
    --hidden-import src.modules.overtime.pages_admin ^
    --hidden-import src.modules.overtime.data_manager ^
    --hidden-import src.modules.overtime.migrations ^
    --exclude-module tkinter ^
    --exclude-module matplotlib ^
    --exclude-module unittest ^
    main.py

if errorlevel 1 (
    echo.
    echo BUILD FAILED
    pause
    exit /b 1
)

echo.
echo ============================================
echo   BUILD SUCCESSFUL
echo   Output: dist\CerasusHub.exe
echo ============================================
echo.
echo Deploy: Copy CerasusHub.exe to any shared drive folder.
echo The app creates data/, logs/, reports/, labels/ next to the EXE.
echo.
pause
