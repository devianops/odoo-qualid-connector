# -*- coding: utf-8 -*-
{
    'name': 'Quali-D WhatsApp',
    'version': '17.0.1.0.0',
    'summary': 'Send approved WhatsApp templates from Odoo automation rules, server actions and records via Quali-D',
    'description': """
Quali-D WhatsApp Connector
==========================
Send approved WhatsApp Business templates through Quali-D (https://quali-d.com)
directly from Odoo:

* New server action type "Send Quali-D WhatsApp Template" — usable in
  Automation Rules (base_automation), contextual buttons and scheduled actions
* Map template variables to any record field (dotted paths supported)
* Background queue with automatic retries, or immediate sending
* "Send once per record" protection against duplicate automation triggers
* Manual "Send WhatsApp Template" wizard on contacts
* Full send log + chatter note on the record
""",
    'author': 'Quali-D',
    'website': 'https://quali-d.com',
    'support': 'support@quali-d.com',
    'category': 'Marketing',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'base_automation'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/qualid_template_views.xml',
        'views/qualid_message_views.xml',
        'views/ir_actions_server_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/qualid_send_wizard_views.xml',
        'views/menus.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
