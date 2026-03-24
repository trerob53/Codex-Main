# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('src/templates', 'src/templates'), ('src/static', 'src/static'), ('src/modules/da_generator/da_template.pdf', 'src/modules/da_generator')],
    hiddenimports=[
        # Flask / Waitress / Jinja2
        'flask', 'flask.json', 'flask.templating', 'jinja2', 'markupsafe',
        'waitress', 'waitress.task', 'waitress.channel', 'waitress.server',
        # Web layer
        'src.web_app', 'src.web_auth', 'src.web_middleware', 'src.email_service',
        'src.blueprints', 'src.blueprints.hub', 'src.blueprints.admin',
        'src.blueprints.api', 'src.blueprints.modules',
        # Core
        'src.database', 'src.config', 'src.auth', 'src.audit',
        'src.session_manager', 'src.permissions', 'src.shared_data',
        'src.notifications', 'src.search_engine', 'src.backup_manager',
        'src.hub_analytics', 'src.analytics_engine',
        'src.report_generator', 'src.pdf_export', 'src.officer_360',
        'src.form_validation', 'src.db_tools', 'src.report_builder',
        'src.scheduled_reports', 'src.hub_audit_viewer', 'src.hub_people',
        'src.lock_manager',
        # Modules — data managers + migrations (no PySide6 pages needed)
        'src.modules.base',
        'src.modules.operations', 'src.modules.operations.data_manager', 'src.modules.operations.migrations',
        'src.modules.uniforms', 'src.modules.uniforms.data_manager', 'src.modules.uniforms.migrations',
        'src.modules.uniforms.email_service', 'src.modules.uniforms.notification_log', 'src.modules.uniforms.qr_labels',
        'src.modules.attendance', 'src.modules.attendance.data_manager', 'src.modules.attendance.migrations',
        'src.modules.attendance.policy_engine', 'src.modules.attendance.duplicate_scanner',
        'src.modules.training', 'src.modules.training.data_manager', 'src.modules.training.migrations',
        'src.modules.da_generator', 'src.modules.da_generator.data_manager', 'src.modules.da_generator.migrations',
        'src.modules.incidents', 'src.modules.incidents.data_manager', 'src.modules.incidents.migrations',
        'src.modules.overtime', 'src.modules.overtime.data_manager', 'src.modules.overtime.migrations',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6', 'PyQt5', 'PyQt6', 'tkinter'],
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
    name='CerasusHub_v4',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
