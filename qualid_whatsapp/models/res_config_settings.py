# -*- coding: utf-8 -*-
from odoo import _, api, fields, models

from .qualid_api import PARAM_TOKEN

PARAM_ACCOUNT_EMAIL = 'qualid_whatsapp.account_email'


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    qualid_api_token = fields.Char('Quali-D Token', config_parameter=PARAM_TOKEN)
    qualid_account_email = fields.Char('Quali-D Account', compute='_compute_qualid_status')
    qualid_connected = fields.Boolean(compute='_compute_qualid_status')
    qualid_template_count = fields.Integer(compute='_compute_qualid_status')
    qualid_last_sync = fields.Datetime(compute='_compute_qualid_status')
    # Which apps are installed — ready-made automations only show "Set up" for these.
    qualid_app_account = fields.Boolean(compute='_compute_qualid_apps')
    qualid_app_sale = fields.Boolean(compute='_compute_qualid_apps')
    qualid_app_stock = fields.Boolean(compute='_compute_qualid_apps')
    qualid_app_crm = fields.Boolean(compute='_compute_qualid_apps')
    qualid_app_purchase = fields.Boolean(compute='_compute_qualid_apps')
    qualid_app_project = fields.Boolean(compute='_compute_qualid_apps')

    @api.depends('company_id')
    def _compute_qualid_apps(self):
        for rec in self:
            rec.qualid_app_account = 'account.move' in self.env
            rec.qualid_app_sale = 'sale.order' in self.env
            rec.qualid_app_stock = 'stock.picking' in self.env
            rec.qualid_app_crm = 'crm.lead' in self.env
            rec.qualid_app_purchase = 'purchase.order' in self.env
            rec.qualid_app_project = 'project.task' in self.env

    # depends on company_id so the settings form computes these when it opens
    @api.depends('company_id')
    def _compute_qualid_status(self):
        icp = self.env['ir.config_parameter'].sudo()
        token = (icp.get_param(PARAM_TOKEN) or '').strip()
        email = (icp.get_param(PARAM_ACCOUNT_EMAIL) or '').strip()
        Template = self.env['qualid.whatsapp.template']
        count = Template.search_count([])
        last = Template.search([('last_sync', '!=', False)], order='last_sync desc', limit=1).last_sync
        for rec in self:
            rec.qualid_connected = bool(token and email)
            rec.qualid_account_email = email or False
            rec.qualid_template_count = count
            rec.qualid_last_sync = last

    def _qualid_verify(self):
        """Call /odoo/verify and remember the account email (cleared on failure)."""
        _status, data = self.env['qualid.api']._qualid_request('GET', '/odoo/verify', raise_on_error=False)
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param(PARAM_ACCOUNT_EMAIL, (data.get('account_email') or '') if data.get('success') else '')
        return data

    def set_values(self):
        icp = self.env['ir.config_parameter'].sudo()
        old_token = (icp.get_param(PARAM_TOKEN) or '').strip()
        super().set_values()
        new_token = (icp.get_param(PARAM_TOKEN) or '').strip()
        if new_token != old_token:
            if new_token:
                # New or changed token → verify and pull templates right away (never blocks saving)
                self._qualid_verify()
                self.env['qualid.whatsapp.template']._qualid_sync_safe()
            else:
                icp.set_param(PARAM_ACCOUNT_EMAIL, '')

    def _qualid_notify(self, message, ntype='success', reload=False):
        params = {'title': _('Quali-D'), 'message': message, 'type': ntype, 'sticky': ntype != 'success'}
        if reload:
            params['next'] = {'type': 'ir.actions.client', 'tag': 'reload'}
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': params}

    def action_qualid_test_connection(self):
        self.ensure_one()
        self.set_values()  # persist what was just typed before testing
        data = self._qualid_verify()
        if data.get('success'):
            return self._qualid_notify(_(
                'Connected to Quali-D account %(email)s (token "%(token)s").',
                email=data.get('account_email') or '-', token=data.get('token_name') or '-',
            ), reload=True)
        return self._qualid_notify(data.get('message') or _('Connection failed.'), 'danger', reload=True)

    def action_qualid_sync_templates(self):
        self.ensure_one()
        self.set_values()
        count = self.env['qualid.whatsapp.template']._qualid_sync()
        return self._qualid_notify(_('%s approved templates synchronized.', count), reload=True)
