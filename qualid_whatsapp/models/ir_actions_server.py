# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Command


class IrActionsServer(models.Model):
    _name = 'ir.actions.server'
    _inherit = ['ir.actions.server', 'qualid.media.mixin']

    state = fields.Selection(
        selection_add=[('qualid_template', 'Send WhatsApp (Quali-D)')],
        ondelete={'qualid_template': 'cascade'},
    )
    qualid_template_id = fields.Many2one(
        'qualid.whatsapp.template', 'WhatsApp Template', ondelete='restrict',
    )
    qualid_phone_path = fields.Char(
        'Phone Field',
        help='Field holding the recipient number, e.g. mobile or partner_id.mobile. '
             'Leave empty to try mobile, phone and the partner\'s numbers automatically.',
    )
    qualid_param_ids = fields.One2many('qualid.action.param', 'action_id', 'Template Variables', copy=True)
    qualid_send_mode = fields.Selection(
        [('queue', 'In background (recommended)'), ('now', 'Immediately')],
        'Send', default='queue',
        help='Background sending never slows down saving the record and retries automatically.',
    )
    qualid_once_per_record = fields.Boolean(
        'Send Only Once Per Record', default=True,
        help='Ignore repeated triggers for the same record (e.g. a record saved twice).',
    )
    qualid_template_needs_media = fields.Boolean(compute='_compute_qualid_template_needs_media')
    qualid_template_header_type = fields.Char(compute='_compute_qualid_template_needs_media')

    @api.depends('qualid_template_id')
    def _compute_qualid_template_needs_media(self):
        for action in self:
            tpl = action.qualid_template_id
            action.qualid_template_needs_media = bool(tpl) and tpl._qualid_has_media_header()
            action.qualid_template_header_type = (tpl.header_format or '').lower() if action.qualid_template_needs_media else False

    @api.onchange('qualid_template_id')
    def _onchange_qualid_template_id(self):
        if self.state != 'qualid_template':
            return
        tpl = self.qualid_template_id
        commands = [Command.clear()]
        if tpl:
            seq = 1
            if tpl.header_has_variable:
                commands.append(Command.create({'sequence': seq, 'component': 'header', 'placeholder': '1',
                                                'source': 'field'}))
                seq += 1
            for name in tpl._qualid_body_variable_names():
                commands.append(Command.create({'sequence': seq, 'component': 'body', 'placeholder': name,
                                                'source': 'field'}))
                seq += 1
        self.qualid_param_ids = commands
        if tpl and tpl._qualid_has_media_header():
            header = (tpl.header_format or '').lower()
            self.qualid_media_source = 'report' if header == 'document' else 'image_field' if header == 'image' else 'attachment'

    @api.constrains('state', 'qualid_template_id', 'qualid_media_source', 'qualid_media_report_id',
                    'qualid_media_image_field_id', 'qualid_media_url_field_id', 'qualid_media_url')
    def _check_qualid_template(self):
        for action in self.filtered(lambda a: a.state == 'qualid_template'):
            if not action.qualid_template_id:
                raise ValidationError(_('Select a WhatsApp template for the action "%s".', action.name or ''))
            error = action._qualid_media_validate(action.qualid_template_id)
            if error:
                raise ValidationError(error)

    def _run_action_qualid_template_multi(self, eval_context=None):
        eval_context = eval_context or {}
        records = eval_context.get('records') or eval_context.get('record')
        if not records:
            ctx = self.env.context
            model = self.model_id.model
            if ctx.get('active_model') == model:
                ids = ctx.get('active_ids') or ([ctx['active_id']] if ctx.get('active_id') else [])
                records = self.env[model].browse(ids)
        if not records:
            return False

        self.env['qualid.whatsapp.message']._qualid_enqueue(
            records,
            self.qualid_template_id,
            self.qualid_param_ids,
            phone_path=self.qualid_phone_path,
            media_spec=self._qualid_media_spec(self.qualid_template_id),
            action=self,
            once_per_record=self.qualid_once_per_record,
            send_now=self.qualid_send_mode == 'now',
        )
        return False
