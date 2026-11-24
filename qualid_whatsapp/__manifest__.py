# -*- coding: utf-8 -*-
{
    'name': 'WhatsApp Integration for Odoo - Templates, Invoices & Automations | Quali-D',
    'version': '19.0.1.1.3',
    'summary': 'WhatsApp Business API for Odoo Community & Enterprise: send approved templates, invoice PDFs, payment reminders and order updates on WhatsApp automatically. No Meta developer setup.',
    'author': 'Quali-D',
    'website': 'https://quali-d.com',
    'support': 'support@quali-d.com',
    'category': 'Marketing/WhatsApp',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'base_automation'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'security/ir.model.access.csv',
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
