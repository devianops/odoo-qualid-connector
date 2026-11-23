# -*- coding: utf-8 -*-
from odoo import _, fields, models

from .qualid_api import DEFAULT_API_URL, PARAM_TOKEN, PARAM_URL


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    qualid_api_url = fields.Char('Quali-D API URL', config_parameter=PARAM_URL, default=DEFAULT_API_URL)
    qualid_api_token = fields.Char('Quali-D Token', config_parameter=PARAM_TOKEN)
    qualid_template_count = fields.Integer(compute='_compute_qualid_template_count')

    def _compute_qualid_template_count(self):
        count = self.env['qualid.whatsapp.template'].search_count([])
        for rec in self:
            rec.qualid_template_count = count

    def _qualid_notify(self, message, ntype='success', reload=False):
        params = {'title': _('Quali-D'), 'message': message, 'type': ntype, 'sticky': ntype != 'success'}
        if reload:
            params['next'] = {'type': 'ir.actions.client', 'tag': 'reload'}
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': params}

    def action_qualid_test_connection(self):
        self.ensure_one()
        self.set_values()  # persist what was just typed before testing
        _status, data = self.env['qualid.api']._qualid_request('GET', '/odoo/verify', raise_on_error=False)
        if data.get('success'):
            return self._qualid_notify(_(
                'Connected to Quali-D account %(email)s (token "%(token)s").',
                email=data.get('account_email') or '-', token=data.get('token_name') or '-',
            ))
        return self._qualid_notify(data.get('message') or _('Connection failed.'), 'danger')

    def action_qualid_sync_templates(self):
        self.ensure_one()
        self.set_values()
        count = self.env['qualid.whatsapp.template']._qualid_sync()
        return self._qualid_notify(_('%s approved templates synchronized.', count), reload=True)
