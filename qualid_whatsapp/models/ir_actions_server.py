# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Command


class IrActionsServer(models.Model):
    _inherit = 'ir.actions.server'

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
    qualid_media_url = fields.Char(
        'Header Media URL',
        help='Public URL of the image / video / document for templates with a media header.',
    )
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

    @api.depends('qualid_template_id')
    def _compute_qualid_template_needs_media(self):
        for action in self:
            tpl = action.qualid_template_id
            action.qualid_template_needs_media = bool(tpl) and tpl._qualid_has_media_header()

    # base_automation hides `name` and computes it from the type — give ours a readable name.
    @api.depends('qualid_template_id')
    def _compute_name(self):
        super()._compute_name()
        for action in self.filtered(lambda a: a.state == 'qualid_template'):
            if action.qualid_template_id:
                action.name = _('Send WhatsApp: %s', action.qualid_template_id.display_name)
            else:
                action.name = _('Send WhatsApp')

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

    @api.constrains('state', 'qualid_template_id')
    def _check_qualid_template(self):
        for action in self:
            if action.state == 'qualid_template' and not action.qualid_template_id:
                raise ValidationError(_('Select a WhatsApp template for the action "%s".', action.name or ''))

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
            media_url=self.qualid_media_url,
            action=self,
            once_per_record=self.qualid_once_per_record,
            send_now=self.qualid_send_mode == 'now',
        )
        return False
