# -*- coding: utf-8 -*-
import json

from odoo import _, api, fields, models


class QualidWhatsappTemplate(models.Model):
    _name = 'qualid.whatsapp.template'
    _description = 'Quali-D WhatsApp Template'
    _order = 'name, language'
    _rec_names_search = ['name', 'language']

    name = fields.Char('Template Name', required=True, readonly=True, index=True)
    language = fields.Char(required=True, readonly=True)
    category = fields.Char(readonly=True)
    status = fields.Char(readonly=True)
    meta_template_id = fields.Char('Meta Template ID', readonly=True)
    parameter_format = fields.Char(readonly=True, default='POSITIONAL')
    header_format = fields.Char(readonly=True, help='TEXT, IMAGE, VIDEO, DOCUMENT or LOCATION')
    header_has_variable = fields.Boolean(readonly=True)
    body_text = fields.Text(readonly=True)
    footer_text = fields.Char(readonly=True)
    body_variables = fields.Char(readonly=True, help='JSON list of body placeholder names, e.g. ["1","2"]')
    body_variable_count = fields.Integer('Variables', readonly=True)
    buttons_json = fields.Text('Buttons', readonly=True)
    active = fields.Boolean(default=True)
    last_sync = fields.Datetime(readonly=True)

    _sql_constraints = [
        ('name_lang_uniq', 'unique(name, language)', 'A template with this name and language already exists.'),
    ]

    @api.depends('name', 'language', 'body_variable_count')
    def _compute_display_name(self):
        for tpl in self:
            tpl.display_name = '%s (%s)' % (tpl.name or '', tpl.language or '')

    def _qualid_body_variable_names(self):
        self.ensure_one()
        try:
            names = json.loads(self.body_variables or '[]')
            return [str(n) for n in names] if isinstance(names, list) else []
        except ValueError:
            return []

    def _qualid_has_media_header(self):
        self.ensure_one()
        return (self.header_format or '').upper() in ('IMAGE', 'VIDEO', 'DOCUMENT')

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------
    def action_sync_templates(self):
        count = self.env['qualid.whatsapp.template']._qualid_sync()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Quali-D'),
                'message': _('%s approved templates synchronized.', count),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    @api.model
    def _qualid_sync(self):
        _status, data = self.env['qualid.api']._qualid_request('GET', '/odoo/templates', params={'status': 'APPROVED'})
        now = fields.Datetime.now()
        Template = self.sudo().with_context(active_test=False)
        seen = Template.browse()

        for t in data.get('templates') or []:
            if not t.get('name') or not t.get('language'):
                continue
            s = t.get('odoo_summary') or {}
            vals = {
                'name': t['name'],
                'language': t['language'],
                'category': t.get('category'),
                'status': t.get('status'),
                'meta_template_id': t.get('id'),
                'parameter_format': s.get('parameter_format') or 'POSITIONAL',
                'header_format': s.get('header_format'),
                'header_has_variable': bool(s.get('header_has_variable')),
                'body_text': s.get('body_text') or '',
                'footer_text': s.get('footer_text'),
                'body_variables': json.dumps(s.get('body_variables') or []),
                'body_variable_count': int(s.get('body_variable_count') or 0),
                'buttons_json': json.dumps(s.get('buttons') or [], indent=1),
                'active': True,
                'last_sync': now,
            }
            rec = Template.search([('name', '=', t['name']), ('language', '=', t['language'])], limit=1)
            if rec:
                rec.write(vals)
            else:
                rec = Template.create(vals)
            seen |= rec

        (Template.search([('active', '=', True)]) - seen).write({'active': False})
        return len(seen)
