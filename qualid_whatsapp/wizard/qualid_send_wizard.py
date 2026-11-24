# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class QualidSendWizard(models.TransientModel):
    _name = 'qualid.send.wizard'
    _inherit = ['qualid.media.mixin']
    _description = 'Send WhatsApp Template (Quali-D)'

    res_model = fields.Char(required=True, readonly=True)
    res_ids = fields.Char(required=True, readonly=True, help='Comma-separated record IDs')
    record_count = fields.Integer(compute='_compute_record_count')
    template_id = fields.Many2one('qualid.whatsapp.template', 'Template', required=True)
    phone_path = fields.Char(
        'Phone Field',
        help='Leave empty to try the record and the partner\'s numbers automatically.',
    )
    phone_override = fields.Char(
        'Phone Number',
        help='Only for a single record: send to this number instead of the record\'s.',
    )
    needs_media = fields.Boolean(compute='_compute_needs_media')
    header_type = fields.Char(compute='_compute_needs_media')
    line_ids = fields.One2many('qualid.send.wizard.line', 'wizard_id', 'Variables')
    preview_phone = fields.Char(compute='_compute_preview', string='Recipient')
    preview_text = fields.Text(compute='_compute_preview', string='Preview')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context
        model = ctx.get('active_model')
        ids = ctx.get('active_ids') or ([ctx['active_id']] if ctx.get('active_id') else [])
        if model and ids:
            res.setdefault('res_model', model)
            res.setdefault('res_ids', ','.join(str(i) for i in ids))
        return res

    def _records(self):
        self.ensure_one()
        ids = [int(i) for i in (self.res_ids or '').split(',') if i.strip().isdigit()]
        return self.env[self.res_model].browse(ids).exists() if self.res_model else self.env['res.partner']

    @api.depends('res_ids')
    def _compute_record_count(self):
        for wiz in self:
            wiz.record_count = len([i for i in (wiz.res_ids or '').split(',') if i.strip()])

    @api.depends('template_id')
    def _compute_needs_media(self):
        for wiz in self:
            wiz.needs_media = bool(wiz.template_id) and wiz.template_id._qualid_has_media_header()
            wiz.header_type = (wiz.template_id.header_format or '').lower() if wiz.needs_media else False

    @api.depends('template_id', 'line_ids.source', 'line_ids.field_path', 'line_ids.text',
                 'phone_path', 'phone_override')
    def _compute_preview(self):
        Api = self.env['qualid.api']
        for wiz in self:
            record = wiz._records()[:1] if wiz.res_model else False
            if not record:
                wiz.preview_phone = wiz.preview_text = False
                continue
            wiz.preview_phone = wiz.phone_override or Api._qualid_resolve_phone(record, wiz.phone_path) \
                or _('(no phone found)')
            text = wiz.template_id.body_text or ''
            for line in wiz.line_ids.filtered(lambda l: l.component == 'body'):
                text = text.replace('{{%s}}' % line.placeholder, line._qualid_value(record) or '…')
            wiz.preview_text = text

    @api.onchange('template_id')
    def _onchange_template_id(self):
        tpl = self.template_id
        commands = [Command.clear()]
        if tpl:
            seq = 1
            if tpl.header_has_variable:
                commands.append(Command.create({'sequence': seq, 'component': 'header', 'placeholder': '1'}))
                seq += 1
            for name in tpl._qualid_body_variable_names():
                commands.append(Command.create({'sequence': seq, 'component': 'body', 'placeholder': name}))
                seq += 1
        self.line_ids = commands
        if tpl and tpl._qualid_has_media_header():
            header = (tpl.header_format or '').lower()
            self.qualid_media_source = 'report' if header == 'document' else 'image_field' if header == 'image' else 'attachment'

    def action_send(self):
        self.ensure_one()
        records = self._records()
        if not records:
            raise UserError(_('No records selected.'))
        if self.phone_override and len(records) > 1:
            raise UserError(_('A phone number override can only be used with a single record.'))
        media_error = self._qualid_media_validate(self.template_id)
        if media_error:
            raise UserError(media_error)

        msgs = self.env['qualid.whatsapp.message']._qualid_enqueue(
            records, self.template_id, self.line_ids,
            phone_path=self.phone_path, media_spec=self._qualid_media_spec(self.template_id),
            phone=self.phone_override or None,
            send_now=len(records) == 1,
        )

        sent = len(msgs.filtered(lambda m: m.state == 'sent'))
        queued = len(msgs.filtered(lambda m: m.state == 'queued'))
        failed = msgs.filtered(lambda m: m.state == 'failed')

        if len(records) == 1 and failed:
            raise UserError(failed[0].error_message or _('Sending failed.'))

        parts = []
        if sent:
            parts.append(_('%s sent', sent))
        if queued:
            parts.append(_('%s queued', queued))
        if failed:
            parts.append(_('%s failed (see WhatsApp Messages)', len(failed)))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('WhatsApp'),
                'message': ', '.join(parts) or _('Nothing to send.'),
                'type': 'warning' if failed else 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }


class QualidSendWizardLine(models.TransientModel):
    _name = 'qualid.send.wizard.line'
    _inherit = 'qualid.param.mixin'
    _description = 'Send WhatsApp Template — Variable'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('qualid.send.wizard', required=True, ondelete='cascade')
