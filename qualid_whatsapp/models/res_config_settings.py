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
        token = (icp.get_str(PARAM_TOKEN) or '').strip()
        email = (icp.get_str(PARAM_ACCOUNT_EMAIL) or '').strip()
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
        icp.set_str(PARAM_ACCOUNT_EMAIL, (data.get('account_email') or '') if data.get('success') else '')
        return data

    def set_values(self):
        icp = self.env['ir.config_parameter'].sudo()
        old_token = (icp.get_str(PARAM_TOKEN) or '').strip()
        super().set_values()
        new_token = (icp.get_str(PARAM_TOKEN) or '').strip()
        if new_token != old_token:
            if new_token:
                # New or changed token → verify and pull templates right away (never blocks saving)
                self._qualid_verify()
                self.env['qualid.whatsapp.template']._qualid_sync_safe()
            else:
                icp.set_str(PARAM_ACCOUNT_EMAIL, '')

    def _qualid_notify(self, message, ntype='success', reload=False):
        params = {'title': _('Quali-D'), 'message': message, 'type': ntype, 'sticky': ntype == 'danger'}
        if reload:
            # Reopen Settings on the Quali-D section (a plain web-client reload lands on General Settings)
            params['next'] = self.env['ir.actions.act_window']._for_xml_id('qualid_whatsapp.action_qualid_settings')
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': params}

    def action_qualid_test_connection(self):
        """Used by both "Connect" (not connected yet) and "Test Connection"."""
        self.ensure_one()
        icp = self.env['ir.config_parameter'].sudo()
        was_connected = bool((icp.get_str(PARAM_TOKEN) or '').strip() and (icp.get_str(PARAM_ACCOUNT_EMAIL) or '').strip())
        self.set_values()  # persist what was just typed (a new token is verified + templates synced here)
        data = self._qualid_verify()
        if data.get('success'):
            msg = _('Connected to Quali-D account %(email)s (token "%(token)s").',
                    email=data.get('account_email') or '-', token=data.get('token_name') or '-')
            if not was_connected:
                msg += ' ' + _('%s approved templates imported.', self.env['qualid.whatsapp.template'].search_count([]))
            # The page layout changes on first connect, so reopen it; a plain test only needs the message.
            return self._qualid_notify(msg, reload=not was_connected)
        return self._qualid_notify(data.get('message') or _('Connection failed. Check the token and try again.'),
                                   'danger', reload=was_connected)

    def action_qualid_disconnect(self):
        """Delete the saved token (and account) from this database. Templates and automations are kept."""
        self.ensure_one()
        icp = self.env['ir.config_parameter'].sudo()
        # Odoo 20: set_str(key, False) keeps an empty row, so delete the rows outright
        icp.search([('key', 'in', [PARAM_TOKEN, PARAM_ACCOUNT_EMAIL])]).unlink()
        return self._qualid_notify(_('Disconnected from Quali-D. The token was deleted from this database.'),
                                   'info', reload=True)

    def action_qualid_sync_templates(self):
        self.ensure_one()
        self.set_values()
        count = self.env['qualid.whatsapp.template']._qualid_sync()
        return self._qualid_notify(_('%s approved templates synchronized.', count), reload=True)
