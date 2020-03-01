# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models

class Company(models.Model):
    _inherit = 'res.company'

    po_lead = fields.Float(string='Purchase Lead Time', required=True, default=0.0)
    po_lock = fields.Selection([('edit', 'Allow to edit purchase orders'),
    ('lock', 'Confirmed purchase orders are not editable')], string="Purchase Order Modification", default="edit")
    po_double_validation = fields.Selection([('one_step', 'Confirm purchase orders in one step'),('two_step', 'Get 2 levels of approvals to confirm a purchase order')], string="Levels of Approvals", default='one_step')
    po_double_validation_amount = fields.Monetary(string='Double validation amount', default=5000)
