# -*- coding: utf-8 -*-
"""Odoo 16: an automated action delegates to its server action, so the automated
action form edits our fields directly on base.automation. Onchanges defined on
ir.actions.server don't run there, so the template onchange is repeated here."""
from odoo import api, models


class BaseAutomation(models.Model):
    _inherit = 'base.automation'

    @api.onchange('qualid_template_id')
    def _onchange_qualid_template_id(self):
        IrActionsServer = self.env['ir.actions.server']
        IrActionsServer._onchange_qualid_template_id.__func__(self)
