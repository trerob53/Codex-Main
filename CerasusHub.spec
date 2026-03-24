# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('src', 'src')],
    hiddenimports=['PySide6.QtWidgets', 'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtPrintSupport', 'sqlite3', 'qrcode', 'PIL', 'pypdf', 'pypdf.generic', 'src.config', 'src.database', 'src.auth', 'src.audit', 'src.lock_manager', 'src.session_manager', 'src.hub_gui', 'src.shared_widgets', 'src.shared_data', 'src.notifications', 'src.notification_ui', 'src.backup_manager', 'src.hub_backups', 'src.pages_activity_feed', 'src.pages_site_dashboard', 'src.pages_site_comparison', 'src.pages_task_queue', 'src.search_engine', 'src.executive_report', 'src.announcements', 'src.document_vault', 'src.custom_fields', 'src.change_password_dialog', 'src.user_management', 'src.analytics_engine', 'src.hub_analytics', 'src.hub_audit_viewer', 'src.hub_people', 'src.loading_overlay', 'src.officer_360', 'src.officer_profile', 'src.pdf_export', 'src.permissions', 'src.print_helper', 'src.report_builder', 'src.report_generator', 'src.scheduled_reports', 'src.form_validation', 'src.db_tools', 'src.web_companion', 'src.modules.operations', 'src.modules.uniforms', 'src.modules.attendance', 'src.modules.training', 'src.modules.da_generator', 'src.modules.incidents', 'src.modules.overtime', 'src.modules.operations.pages_dashboard', 'src.modules.operations.pages_flex_board', 'src.modules.operations.pages_ops', 'src.modules.operations.pages_pto', 'src.modules.operations.pages_admin', 'src.modules.operations.pages_handoff', 'src.modules.operations.pages_incidents', 'src.modules.operations.data_manager', 'src.modules.operations.migrations', 'src.modules.uniforms.pages_dashboard', 'src.modules.uniforms.pages_personnel', 'src.modules.uniforms.pages_sites', 'src.modules.uniforms.pages_uniform', 'src.modules.uniforms.pages_inventory', 'src.modules.uniforms.pages_compliance', 'src.modules.uniforms.pages_admin', 'src.modules.uniforms.data_manager', 'src.modules.uniforms.migrations', 'src.modules.uniforms.email_service', 'src.modules.uniforms.notification_log', 'src.modules.uniforms.qr_labels', 'src.modules.attendance.pages_dashboard', 'src.modules.attendance.pages_roster', 'src.modules.attendance.pages_infractions', 'src.modules.attendance.pages_discipline', 'src.modules.attendance.pages_reviews', 'src.modules.attendance.pages_reports', 'src.modules.attendance.pages_admin', 'src.modules.attendance.pages_import', 'src.modules.attendance.pages_bulk_import', 'src.modules.attendance.data_manager', 'src.modules.attendance.migrations', 'src.modules.attendance.duplicate_scanner', 'src.modules.attendance.policy_engine', 'src.modules.attendance.risk_engine', 'src.modules.training.pages_dashboard', 'src.modules.training.pages_courses', 'src.modules.training.pages_leaderboard', 'src.modules.training.pages_certificates', 'src.modules.training.pages_admin', 'src.modules.training.data_manager', 'src.modules.training.migrations', 'src.modules.da_generator.pages_wizard', 'src.modules.da_generator.pages_history', 'src.modules.da_generator.pages_settings', 'src.modules.da_generator.pages_templates', 'src.modules.da_generator.data_manager', 'src.modules.da_generator.migrations', 'src.modules.da_generator.api_client', 'src.modules.da_generator.ceis_prompts', 'src.modules.da_generator.local_engine', 'src.modules.da_generator.pdf_filler', 'src.modules.incidents.pages_dashboard', 'src.modules.incidents.pages_incidents', 'src.modules.incidents.pages_admin', 'src.modules.incidents.data_manager', 'src.modules.incidents.migrations', 'src.modules.overtime.pages_dashboard', 'src.modules.overtime.pages_analysis', 'src.modules.overtime.pages_admin', 'src.modules.overtime.data_manager', 'src.modules.overtime.migrations'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'unittest'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CerasusHub',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
