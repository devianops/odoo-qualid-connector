# -*- coding: utf-8 -*-
{
    'name': 'Quali-D WhatsApp',
    'version': '20.0.1.1.3',
    'summary': 'Send approved WhatsApp templates from Odoo automation rules, server actions and records via Quali-D',
    'author': 'Quali-D',
    'website': 'https://quali-d.com',
    'support': 'support@quali-d.com',
    'category': 'Marketing',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'base_automation'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'security/ir.access.csv',
        'data/ir_cron.xml',
        'views/qualid_template_views.xml',
        'views/qualid_message_views.xml',
        'views/ir_actions_server_views.xml',
        'wizard/qualid_send_wizard_views.xml',
        'wizard/qualid_automation_wizard_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'qualid_whatsapp/static/src/scss/qualid_settings.scss',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
