# -*- coding: utf-8 -*-
"""Ready-made automations: one wizard creates a complete Automation Rule
(trigger, filters, header PDF, suggested variables) with a "Send WhatsApp
(Quali-D)" action, using the same records Odoo's own UI would create."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

UNPAID = ['not_paid', 'partial']
PAID = ['paid', 'in_payment']

# Each preset only uses labels/values verified against Odoo 17's code.
PRESETS = {
    'invoice_posted': {
        'name': 'Invoice confirmed → send the invoice',
        'app': 'Invoicing', 'icon': 'fa-file-text-o', 'model': 'account.move',
        'when': 'A customer invoice is confirmed.',
        'trigger': 'on_state_set', 'state_value': 'posted',
        'domain': [('state', '=', 'posted'), ('move_type', '=', 'out_invoice')],
        'report': 'account.account_invoices',
        'vars': ['partner_id.name', 'name', 'amount_total', 'invoice_date_due'],
    },
    'invoice_paid': {
        'name': 'Invoice paid → thank you',
        'app': 'Invoicing', 'icon': 'fa-check-circle-o', 'model': 'account.move',
        'when': 'A customer invoice becomes paid.',
        'trigger': 'on_create_or_write', 'trigger_fields': ['payment_state'],
        'pre_domain': [('payment_state', 'not in', PAID)],
        'domain': [('move_type', '=', 'out_invoice'), ('payment_state', 'in', PAID)],
        'report': 'account.account_invoices',
        'vars': ['partner_id.name', 'name', 'amount_total'],
    },
    'invoice_due_soon': {
        'name': 'Payment reminder 2 days before due date',
        'app': 'Invoicing', 'icon': 'fa-bell-o', 'model': 'account.move',
        'when': 'An unpaid customer invoice is due in 2 days (checked every 4 hours).',
        'trigger': 'on_time', 'date_field': 'invoice_date_due', 'delay': -2,
        'domain': [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('payment_state', 'in', UNPAID)],
        'report': 'account.account_invoices',
        'vars': ['partner_id.name', 'name', 'amount_residual', 'invoice_date_due'],
    },
    'invoice_overdue': {
        'name': 'Overdue reminder 3 days after due date',
        'app': 'Invoicing', 'icon': 'fa-exclamation-circle', 'model': 'account.move',
        'when': 'A customer invoice is still unpaid 3 days after its due date (checked every 4 hours).',
        'trigger': 'on_time', 'date_field': 'invoice_date_due', 'delay': 3,
        'domain': [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('payment_state', 'in', UNPAID)],
        'report': 'account.account_invoices',
        'vars': ['partner_id.name', 'name', 'amount_residual', 'invoice_date_due'],
    },
    'quotation_sent': {
        'name': 'Quotation sent → send the quotation',
        'app': 'Sales', 'icon': 'fa-paper-plane-o', 'model': 'sale.order',
        'when': 'A quotation is marked as sent.',
        'trigger': 'on_state_set', 'state_value': 'sent',
        'domain': [('state', '=', 'sent')],
        'report': 'sale.action_report_saleorder',
        'vars': ['partner_id.name', 'name', 'amount_total', 'user_id.name'],
    },
    'order_confirmed': {
        'name': 'Order confirmed → send the order',
        'app': 'Sales', 'icon': 'fa-shopping-cart', 'model': 'sale.order',
        'when': 'A quotation is confirmed into a sales order.',
        'trigger': 'on_state_set', 'state_value': 'sale',
        'domain': [('state', '=', 'sale')],
        'report': 'sale.action_report_saleorder',
        'vars': ['partner_id.name', 'name', 'amount_total', 'user_id.name'],
    },
    'delivery_done': {
        'name': 'Order delivered → send the delivery slip',
        'app': 'Inventory', 'icon': 'fa-truck', 'model': 'stock.picking',
        'when': 'A delivery to a customer is validated.',
        'trigger': 'on_state_set', 'state_value': 'done',
        'domain': [('state', '=', 'done'), ('picking_type_code', '=', 'outgoing')],
        'report': 'stock.action_report_delivery',
        'vars': ['partner_id.name', 'name', 'origin'],
    },
    'lead_new': {
        'name': 'New lead → instant reply',
        'app': 'CRM', 'icon': 'fa-bolt', 'model': 'crm.lead',
        'when': 'A new lead or opportunity with a phone number is created.',
        'trigger': 'on_create',
        'domain': ['|', ('mobile', '!=', False), ('phone', '!=', False)],
        'vars': ['contact_name', 'name', 'user_id.name'],
    },
    'lead_won': {
        'name': 'Opportunity won → thank you',
        'app': 'CRM', 'icon': 'fa-trophy', 'model': 'crm.lead',
        'when': 'An opportunity moves to a Won stage.',
        'trigger': 'on_create_or_write', 'trigger_fields': ['stage_id'],
        'pre_domain': [('stage_id.is_won', '=', False)],
        'domain': [('stage_id.is_won', '=', True)],
        'vars': ['contact_name', 'name', 'user_id.name'],
    },
    'contact_welcome': {
        'name': 'New contact → welcome message',
        'app': 'Contacts', 'icon': 'fa-user-plus', 'model': 'res.partner',
        'when': 'A contact with a phone number is created.',
        'trigger': 'on_create',
        'domain': ['|', ('mobile', '!=', False), ('phone', '!=', False)],
        'vars': ['name', '@company'],
    },
    'po_confirmed': {
        'name': 'Purchase order confirmed → send it to the supplier',
        'app': 'Purchase', 'icon': 'fa-shopping-bag', 'model': 'purchase.order',
        'when': 'A purchase order is confirmed.',
        'trigger': 'on_state_set', 'state_value': 'purchase',
        'domain': [('state', '=', 'purchase')],
        'report': 'purchase.action_report_purchase_order',
        'vars': ['partner_id.name', 'name', 'date_planned'],
    },
    'task_done': {
        'name': 'Task done → notify the customer',
        'app': 'Project', 'icon': 'fa-tasks', 'model': 'project.task',
        'when': 'A task with a customer is marked as done.',
        'trigger': 'on_state_set', 'state_value': '1_done',
        'domain': [('state', '=', '1_done'), ('partner_id', '!=', False)],
        'vars': ['partner_id.name', 'name', 'project_id.name'],
    },
}


class QualidAutomationWizard(models.TransientModel):
    _name = 'qualid.automation.wizard'
    _inherit = ['qualid.media.mixin']
    _description = 'New WhatsApp Automation (Quali-D)'

    @api.model
    def _qualid_available_presets(self):
        return [(key, p['name']) for key, p in PRESETS.items() if p['model'] in self.env]

    preset = fields.Selection(selection='_qualid_available_presets', string='Automation', required=True)
    preset_when = fields.Char(compute='_compute_preset_info', string='Sends when')
    preset_app = fields.Char(compute='_compute_preset_info')
    preset_has_report = fields.Boolean(compute='_compute_preset_info')
    model_name = fields.Char(compute='_compute_preset_info')
    template_id = fields.Many2one('qualid.whatsapp.template', 'WhatsApp Template', required=True)
    needs_media = fields.Boolean(compute='_compute_needs_media')
    header_type = fields.Char(compute='_compute_needs_media')
    line_ids = fields.One2many('qualid.automation.wizard.line', 'wizard_id', 'Variables')
    phone_path = fields.Char(
        'Phone Field',
        help='Leave empty to use the record\'s mobile / phone, then its customer\'s.',
    )
    send_mode = fields.Selection(
        [('queue', 'In background (recommended)'), ('now', 'Immediately')], 'Send', default='queue', required=True,
    )
    active = fields.Boolean('Turn on now', default=True)

    @api.depends('preset')
    def _compute_preset_info(self):
        for wiz in self:
            p = PRESETS.get(wiz.preset) or {}
            wiz.preset_when = p.get('when')
            wiz.preset_app = p.get('app')
            wiz.preset_has_report = bool(p.get('report'))
            wiz.model_name = p.get('model')

    @api.depends('template_id')
    def _compute_needs_media(self):
        for wiz in self:
            wiz.needs_media = bool(wiz.template_id) and wiz.template_id._qualid_has_media_header()
            wiz.header_type = (wiz.template_id.header_format or '').lower() if wiz.needs_media else False

    @api.onchange('preset', 'template_id')
    def _onchange_fill(self):
        """Variables get the preset's suggested fields in order; header file defaults to the preset's PDF."""
        p = PRESETS.get(self.preset) or {}
        # '@company' = your own company name as fixed text (never empty)
        suggestions = [('text', self.env.company.name) if s == '@company' else ('field', s)
                       for s in (p.get('vars') or [])]

        def suggested(i):
            src, value = suggestions[i] if i < len(suggestions) else ('field', False)
            return {'source': src, 'field_path': value if src == 'field' else False,
                    'text': value if src == 'text' else False}

        tpl = self.template_id
        commands = [Command.clear()]
        if tpl:
            seq = 1
            if tpl.header_has_variable:
                commands.append(Command.create({'sequence': seq, 'component': 'header', 'placeholder': '1',
                                                **suggested(0)}))
                seq += 1
            for i, name in enumerate(tpl._qualid_body_variable_names()):
                commands.append(Command.create({'sequence': seq, 'component': 'body', 'placeholder': name,
                                                **suggested(i)}))
                seq += 1
        self.line_ids = commands

        header = (tpl.header_format or '').lower() if tpl and tpl._qualid_has_media_header() else ''
        report = self.env.ref(p['report'], raise_if_not_found=False) if p.get('report') else False
        if header == 'document' and report:
            self.qualid_media_source = 'report'
            self.qualid_media_report_id = report
        elif header:
            self.qualid_media_source = 'image_field' if header == 'image' else 'attachment' if header == 'video' else 'report'
            self.qualid_media_report_id = False

    # ------------------------------------------------------------------
    def _qualid_selection_value(self, model, field_name, value):
        field = self.env['ir.model.fields']._get(model, field_name)
        return self.env['ir.model.fields.selection'].search(
            [('field_id', '=', field.id), ('value', '=', value)], limit=1)

    def action_create(self):
        self.ensure_one()
        p = PRESETS.get(self.preset)
        if not p or p['model'] not in self.env:
            raise UserError(_('This automation needs the %s app.', (p or {}).get('app', '')))
        missing = self.line_ids.filtered(lambda l: (l.source == 'field' and not l.field_path)
                                         or (l.source == 'text' and not l.text))
        if missing:
            raise UserError(_('Fill in every template variable (%s).',
                              ', '.join('{{%s}}' % m.placeholder for m in missing)))
        media_error = self._qualid_media_validate(self.template_id)
        if media_error:
            raise UserError(media_error)

        model = self.env['ir.model']._get(p['model'])
        Fields = self.env['ir.model.fields']
        vals = {
            'name': _('WhatsApp: %s', p['name']),
            'model_id': model.id,
            'trigger': p['trigger'],
            'active': self.active,
        }
        if p.get('trigger_fields'):
            vals['trigger_field_ids'] = [Command.set([Fields._get(p['model'], f).id for f in p['trigger_fields']])]
        if p['trigger'] == 'on_state_set':
            # Set explicitly: Odoo only fills these from the trigger in its own form, not on create().
            vals['trigger_field_ids'] = [Command.set([Fields._get(p['model'], 'state').id])]
            vals['trg_selection_field_id'] = self._qualid_selection_value(p['model'], 'state', p['state_value']).id
        if p['trigger'] == 'on_time':
            vals.update({
                'trg_date_id': Fields._get(p['model'], p['date_field']).id,
                'trg_date_range': p['delay'],
                'trg_date_range_type': 'day',
            })
        rule = self.env['base.automation'].create(vals)
        # Written after create: Odoo recomputes these from the trigger, we add our extra conditions.
        rule.write({
            'filter_domain': repr(p.get('domain') or []),
            'filter_pre_domain': repr(p['pre_domain']) if p.get('pre_domain') else False,
        })

        spec = self._qualid_media_spec(self.template_id)
        self.env['ir.actions.server'].create({
            'name': _('Send WhatsApp: %s', self.template_id.display_name),
            'model_id': model.id,
            'usage': 'base_automation',
            'base_automation_id': rule.id,
            'state': 'qualid_template',
            'qualid_template_id': self.template_id.id,
            'qualid_phone_path': self.phone_path or False,
            'qualid_send_mode': self.send_mode,
            'qualid_once_per_record': True,
            'qualid_media_source': spec.get('media_source') or False,
            'qualid_media_report_id': self.qualid_media_report_id.id if spec.get('media_source') == 'report' else False,
            'qualid_media_image_field_id': self.qualid_media_image_field_id.id if spec.get('media_source') == 'image_field' else False,
            'qualid_media_url_field_id': self.qualid_media_url_field_id.id if spec.get('media_source') == 'url_field' else False,
            'qualid_media_attachment_filter': self.qualid_media_attachment_filter if spec.get('media_source') == 'attachment' else False,
            'qualid_media_url': self.qualid_media_url if spec.get('media_source') == 'url' else False,
            'qualid_param_ids': [Command.create({
                'sequence': l.sequence, 'component': l.component, 'placeholder': l.placeholder,
                'source': l.source, 'field_path': l.field_path, 'text': l.text,
            }) for l in self.line_ids],
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'base.automation',
            'res_id': rule.id,
            'view_mode': 'form',
            'target': 'current',
        }


class QualidAutomationWizardLine(models.TransientModel):
    _name = 'qualid.automation.wizard.line'
    _inherit = 'qualid.param.mixin'
    _description = 'New WhatsApp Automation — Variable'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('qualid.automation.wizard', required=True, ondelete='cascade')
