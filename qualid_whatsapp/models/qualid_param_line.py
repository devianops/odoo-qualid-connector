# -*- coding: utf-8 -*-
from odoo import api, fields, models


class QualidParamMixin(models.AbstractModel):
    """Shared definition of one template variable mapping."""
    _name = 'qualid.param.mixin'
    _description = 'Quali-D Template Variable Mapping'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    component = fields.Selection(
        [('header', 'Header'), ('body', 'Body')], default='body', required=True,
    )
    placeholder = fields.Char(
        'Variable', required=True,
        help='Placeholder name as written in the template, e.g. 1 for {{1}}.',
    )
    source = fields.Selection(
        [('field', 'Record Field'), ('text', 'Fixed Text')],
        default='field', required=True,
    )
    field_path = fields.Char(
        'Field',
        help='Technical field name on the record. Use dots to follow relations, '
             'e.g. partner_id.name or user_id.partner_id.phone',
    )
    text = fields.Char('Text')

    @api.depends('placeholder', 'component')
    def _compute_display_name(self):
        for line in self:
            line.display_name = '%s {{%s}}' % (line.component or '', line.placeholder or '')

    def name_get(self):  # Odoo 16
        return [(line.id, '%s {{%s}}' % (line.component or '', line.placeholder or '')) for line in self]

    def _qualid_value(self, record):
        self.ensure_one()
        if self.source == 'text':
            return self.text or ''
        return self.env['qualid.api']._qualid_resolve_path(record, self.field_path)


class QualidActionParam(models.Model):
    _name = 'qualid.action.param'
    _inherit = 'qualid.param.mixin'
    _description = 'Quali-D Server Action Variable'
    _order = 'sequence, id'

    action_id = fields.Many2one('ir.actions.server', required=True, ondelete='cascade', index=True)
