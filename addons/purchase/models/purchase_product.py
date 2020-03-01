# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import smtplib
from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, SUPERUSER_ID, _
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from odoo.tools.float_utils import float_is_zero, float_compare
from odoo.exceptions import UserError, AccessError
from odoo.tools.misc import formatLang
from odoo.addons.base.res.res_partner import WARNING_MESSAGE, WARNING_HELP
import odoo.addons.decimal_precision as dp
from email.mime.text import MIMEText
import logging
from odoo.http import request

import os
import sys
abspath = sys.path.append(os.path.abspath('gvm/models'))
from sendmail import gvm_mail

_logger = logging.getLogger(__name__)

class GvmPurchaseProduct(models.Model):
    _name = "gvm.purchase_product"
    _inherit = ['mail.thread', 'ir.needaction_mixin']
    _description = "Purchase Product"
    _order = 'date_order desc, id desc'

    @api.model
    def _default_picking_type(self):
        type_obj = self.env['stock.picking.type']
        company_id = self.env.context.get('company_id') or self.env.user.company_id.id
        types = type_obj.search([('code', '=', 'incoming'), ('warehouse_id.company_id', '=', company_id)])
        if not types:
            types = type_obj.search([('code', '=', 'incoming'), ('warehouse_id', '=', False)])
        return types[:1]

    @api.depends('picking_ids', 'picking_ids.state')
    def _compute_is_shipped(self):
        for order in self:
            if order.picking_ids and all([x.state == 'done' for x in order.picking_ids]):
                order.is_shipped = True

    READONLY_STATES = {
#        'purchase': [('readonly', True)],
        'done': [('readonly', True)],
#        'cancel': [('readonly', True)],
    }

    name = fields.Char('Order Reference', required=True, index=True, copy=False, default='New')
    origin = fields.Char('Source Document', copy=False,\
        help="Reference of the document that generated this purchase order "
             "request (e.g. a sale order or an internal procurement request)")
    date_order = fields.Datetime('요청일자', required=True, states=READONLY_STATES, index=True, copy=False, default=fields.Datetime.now,\
        help="Depicts the date where the Quotation should be validated and converted into a purchase order.")
    date_approve = fields.Date('Approval Date', readonly=1, index=True, copy=False)
    partner_id = fields.Many2one('res.partner', string='Vendor', required=True, states=READONLY_STATES, change_default=True, track_visibility='onchange')
    dest_address_id = fields.Many2one('res.partner', string='Drop Ship Address', states=READONLY_STATES,\
        help="Put an address if you want to deliver directly from the vendor to the customer. "\
             "Otherwise, keep empty to deliver to your own company.")
    currency_id = fields.Many2one('res.currency', 'Currency', required=True, states=READONLY_STATES,\
        default=lambda self: self.env.user.company_id.currency_id.id)
    state = fields.Selection([
        ('write', '작성'),
        ('draft', '발주진행'),
        ('sent', 'RFQ Sent'),
        ('to approve', '입금확인'),
        ('purchase', 'Purchase Order'),
        ('done', '발주진행완료'),
        ('cancel', '발주취소'),
        ('order_cancel','결재취소')
        ('modify', '수정됨'),
        ], string='Status', readonly=True, index=True, copy=False, default='write', track_visibility='onchange')
    notes = fields.Text('Terms and Conditions')

    invoice_count = fields.Integer(string='# of Bills', copy=False, default=0)
    invoice_ids = fields.Many2many('account.invoice', string='Bills', copy=False)
    invoice_status = fields.Selection([
        ('no', 'Nothing to Bill'),
        ('to invoice', 'Waiting Bills'),
        ('invoiced', 'Bills Received'),
        ], string='Billing Status', store=True, readonly=True, copy=False, default='no')

    picking_count = fields.Integer(string='Receptions', default=0)
    picking_ids = fields.Many2many('stock.picking', string='Receptions', copy=False)

    # There is no inverse function on purpose since the date may be different on each line
    date_planned = fields.Datetime(string='Scheduled Date', store=True, index=True)

    amount_untaxed = fields.Monetary(string='Untaxed Amount', store=True, readonly=True, track_visibility='onchange')
    amount_tax = fields.Monetary(string='Taxes', store=True, readonly=True)
    amount_total = fields.Monetary(string='Total', store=True, readonly=True)

    fiscal_position_id = fields.Many2one('account.fiscal.position', string='Fiscal Position', oldname='fiscal_position')
    payment_term_id = fields.Many2one('account.payment.term', 'Payment Terms')
    incoterm_id = fields.Many2one('stock.incoterms', 'Incoterm', states={'done': [('readonly', True)]}, help="International Commercial Terms are a series of predefined commercial terms used in international transactions.")

    create_uid = fields.Many2one('res.users', 'Responsible')
    company_id = fields.Many2one('res.company', 'Company', required=True, index=True, states=READONLY_STATES, default=lambda self: self.env.user.company_id.id)

    picking_type_id = fields.Many2one('stock.picking.type', 'Deliver To', states=READONLY_STATES, required=True, default=_default_picking_type,\
        help="This will determine picking type of incoming shipment")
    default_location_dest_id_usage = fields.Selection(related='picking_type_id.default_location_dest_id.usage', string='Destination Location Type',\
        help="Technical field used to display the Drop Ship Address", readonly=True)
    group_id = fields.Many2one('procurement.group', string="Procurement Group", copy=False)
    is_shipped = fields.Boolean(compute="_compute_is_shipped")

    project_id = fields.Many2one('project.project','project')
    project_name = fields.Char('project_name')
    project_code = fields.Boolean(store=True, default=False)
    project_ids = fields.Many2many('project.project',string='project_ids')
    part = fields.Many2one('project.task',string='part')
    issue = fields.Many2one('project.issue',string='issue')
    issue_maker = fields.Boolean('issue_maker',compute='_compute_project_issue')
    department = fields.Char('department',compute='_compute_department')
    attachment = fields.Many2many('ir.attachment', domain="[('res_model','=','gvm.product')]", string='도면')
    line_count = fields.Integer('라인수',default='1')
    drawing_man = fields.Many2one('res.users','설계자')
    order_man = fields.Many2one('res.users','발주자',default=lambda self:self.env.uid)
    permit_man = fields.Many2one('res.users','검토자')
    permit_date = fields.Datetime(string='검토일자')
    category = fields.Selection([('1','기구/가공품'),('2','기구/요소품'),('3','전장/가공품'),('4','전장/요소품'),('5','기타')])
    product = fields.One2many('gvm.product','purchase_by_maker',string='발주', index=True,track_visibility="onchange")
    purchase_product = fields.Many2many('gvm.product',string='product')
    
    @api.depends('order_man')
    def _compute_department(self):
      for record in self:
        record.department = self.env['hr.employee'].search([('user_id','=',self.order_man.id)],limit=1).department_id.name

    @api.onchange('project_id')
    def _compute_project_name(self):
      for record in self:
        record.project_name = record.project_id.name
	if not record.project_id.code and record.project_id:
	  record.project_code = True
	  continue
	record.project_code = False

    @api.onchange('project_ids')
    def onchange_line_count(self):
      if len(self.project_ids) >= 2:
        self.line_count = len(self.project_ids)

    @api.onchange('line_count')
    def onchange_product_line_count(self):
      for product in self.product:
        product.total_count = self.line_count * product.original_count

    @api.onchange('drawing_man')
    def onchange_drawing_man(self):
      for product in self.product:
        product.drawing_man = self.drawing_man.name

    @api.onchange('request')
    def onchange_request_comment(self):
        for product in self.product:
            comment = ''
            if self.request:
                comment = self.request or ''
            if product.etc:
                comment += product.etc
            product.etc = comment

    @api.onchange('category')
    def onchange_category(self):
        for product in self.product:
            product.category = self.category

    @api.depends('project_ids')
    def _compute_project_issue(self):
      for record in self:
        if record.project_id and record.issue:
          for project in self.project_ids:
	    p_issue_list = []
	    for p_issue in project.issue_ids:
	      p_issue_list.append(p_issue.name)
    	    if record.issue.name not in p_issue_list:
	      self.env['project.issue'].create({'name':record.issue.name,
                      'project_id':project.id,
                      'partner_id':record.partner_id.id,
                      'line_count':record.line_count,
                      'department':record.department,
                      })

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        args = args or []
        domain = []
        if name:
            domain = [('name', operator, name)]
        pos = self.search(domain + args, limit=limit)
        return pos.name_get()

    @api.multi
    @api.depends('name')
    def name_get(self):
        result = []
        for po in self:
            name = po.name
            if po.amount_total:
                name += ': ' + formatLang(self.env, po.amount_total, currency_obj=po.currency_id)
            result.append((po.id, name))
        return result

    @api.model
    def create(self, vals):
        _logger.warning("test")
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('purchase.order') or '/'
        res = super(GvmPurchaseProduct, self).create(vals)
        last_id = self.env['gvm.purchase_product'].search([('id','=',res.id)])
        issue = last_id.issue
        if not last_id.project_id:
          raise UserError(_('프로젝트를 입력해주세요'))
	
        if last_id.project_id and issue:
          issue.write({'project_id':last_id.project_id.id})

        newProduct = last_id.product
        for np in newProduct:
          #issue.write({'product':[(4,np.id)]})
	  np.write({
	    'project_id':last_id.project_id.name,
	    'project_set':[(4,last_id.project_id.id)],
	    'issue':issue.id,
	  })
	  #np.write({'issue':issue.id})
        return res

    @api.multi
    def write(self, vals):
        res = super(GvmPurchaseProduct, self).write(vals)
        for record in self:
          last_id = self.env['gvm.purchase_product'].search([('id','=',record.id)])
	  issue = last_id.issue
          if last_id.project_id and issue:
	    issue.project_id = last_id.project_id.id
          issue_id = ''
          if issue:
            issue_id = issue.id
	  for pd in last_id.product:
	    pd.write({
	      'drawing_man':last_id.drawing_man.name,
              'issue': issue_id,
	    })
	return res

    @api.multi
    def unlink(self):
        state = ['write','cancel','order_cancel']
        for order in self:
	    if order.product:
	      for pd in order.product:
	        pd.state = 'delete'
            if not order.state in state:
                raise UserError(_('In order to delete a purchase order, you must cancel it first.'))
        return super(GvmPurchaseProduct, self).unlink()

    @api.multi
    def copy(self, default=None):
        new_po = super(GvmPurchaseProduct, self).copy(default=default)
        return new_po

    @api.multi
    def _track_subtype(self, init_values):
        self.ensure_one()
        if 'state' in init_values and self.state == 'purchase':
            return 'purchase.mt_rfq_approved'
        elif 'state' in init_values and self.state == 'to approve':
            return 'purchase.mt_rfq_confirmed'
        elif 'state' in init_values and self.state == 'done':
            return 'purchase.mt_rfq_done'
        return super(GvmPurchaseProduct, self)._track_subtype(init_values)

    @api.onchange('partner_id', 'company_id')
    def onchange_partner_id(self):
        if not self.partner_id:
            self.fiscal_position_id = False
            self.payment_term_id = False
            self.currency_id = False
        else:
            self.fiscal_position_id = self.env['account.fiscal.position'].with_context(company_id=self.company_id.id).get_fiscal_position(self.partner_id.id)
            self.payment_term_id = self.partner_id.property_supplier_payment_term_id.id
            self.currency_id = self.partner_id.property_purchase_currency_id.id or self.env.user.company_id.currency_id.id
        return {}

    @api.onchange('fiscal_position_id')
    def _compute_tax_id(self):
        """
        Trigger the recompute of the taxes if the fiscal position is changed on the PO.
        """
	return {}

    @api.onchange('partner_id')
    def onchange_partner_id_warning(self):
        if not self.partner_id:
            return
        warning = {}
        title = False
        message = False

        partner = self.partner_id

        # If partner has no warning, check its company
        if partner.purchase_warn == 'no-message' and partner.parent_id:
            partner = partner.parent_id

        if partner.purchase_warn != 'no-message':
            # Block if partner only has warning but parent company is blocked
            if partner.purchase_warn != 'block' and partner.parent_id and partner.parent_id.purchase_warn == 'block':
                partner = partner.parent_id
            title = _("Warning for %s") % partner.name
            message = partner.purchase_warn_msg
            warning = {
                'title': title,
                'message': message
                }
            if partner.purchase_warn == 'block':
                self.update({'partner_id': False})
            return {'warning': warning}
        return {}

    @api.onchange('picking_type_id')
    def _onchange_picking_type_id(self):
        if self.picking_type_id.default_location_dest_id.usage != 'customer':
            self.dest_address_id = False

    @api.multi
    def action_rfq_send(self):
        '''
        This function opens a window to compose an email, with the edi purchase template message loaded by default
        '''
        self.ensure_one()
        ir_model_data = self.env['ir.model.data']
        try:
            if self.env.context.get('send_rfq', False):
                template_id = ir_model_data.get_object_reference('purchase', 'email_template_edi_purchase')[1]
            else:
                template_id = ir_model_data.get_object_reference('purchase', 'email_template_edi_purchase_done')[1]
        except ValueError:
            template_id = False
        try:
            compose_form_id = ir_model_data.get_object_reference('mail', 'email_compose_message_wizard_form')[1]
        except ValueError:
            compose_form_id = False
        ctx = dict(self.env.context or {})
        ctx.update({
            'default_model': 'gvm.purchase_product',
            'default_res_id': self.ids[0],
            'default_use_template': bool(template_id),
            'default_template_id': template_id,
            'default_composition_mode': 'comment',
        })
        return {
            'name': _('Compose Email'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form_id, 'form')],
            'view_id': compose_form_id,
            'target': 'new',
            'context': ctx,
        }

    @api.multi
    def print_quotation(self):
        self.write({'state': "sent"})
        return self.env['report'].get_action(self, 'purchase.report_purchasequotation_by_maker')

    @api.multi
    def button_send_quotation(self):
        if self.product:
	  for product in self.product:
	    product.write({'state':'purchase'})
            # Find Stock
            stock = self.env['product.product'].search([('model','ilike',product.name),
                                                        ('stock','>=',1)],limit=1)

            if stock:
              #sh
              #공용자재에 발주번호 작성
              po = self.name
              if stock.ponum == False:
               value = po
              else:
               value = stock.ponum + ',' + po
              stock.write({'ponum':value})

              product.stock_item = True            
              product.product_id = stock.id

              # 개수가 모자라면 분할해야 함
              stock_log = stock.stock
              stock_count = stock.stock - product.total_count
              stock.stock = stock_count
              if stock_count < 0:
                stock.stock = 0
                remain_count = - (stock_count / self.line_count)
                remain_product = self.env['gvm.product'].create({
	          'sequence_num': product.sequence_num, 
		  'name': product.name, 
		  'product_name': product.product_name, 
		  'material': product.material, 
		  'original_count': remain_count,
		  'etc': product.etc, 
		  'bad_state': product.bad_state, 
		  'purchase_by_maker': product.purchase_by_maker.id,
                  'state': 'purchase',
                  'request_date': product.request_date,
                  'project_id': product.project_id,
                })
	        etc_text = str('발주 %d 개 중 %d 개 재고 사용' 
                 % (product.total_count, (product.total_count + stock_count))).decode('utf-8').encode('utf-8')
                if product.etc and product.etc != 'false':
                  etc_text += product.etc.encode('utf-8')
                product.etc = etc_text
                product.original_count = stock_log
                self.write({'product':[(4,remain_product.id)]})

        # Send Mail
        sender = self.order_man.name
	postId = self.id
        marketing = self.env['hr.employee'].search([('department_id','=',6)])
        post = '견적요청서'
	model_name = 'gvm.purchase_product'
        menu_id = "357"
        action_id = "471"
        po_num = self.env[model_name].search([('id','=',postId)]).name
        send_mail = gvm_mail().gvm_send_mail(sender ,marketing, post, postId, po_num, model_name, menu_id, action_id)
        # Add Follower
        # 298:고은경, 254: 김현태, 296: 오정희, 329: 이재혁, 330: 이다운
        partner_ids = [254, 296, 298, 329, 330]
        self.sudo().write({'state': "draft",
                           'permit_man': self.env.uid,
                           'permit_date': datetime.today(),
        })
        self.message_subscribe_users(user_ids=partner_ids)

    @api.multi
    def button_approve(self, force=False):
        self.write({'state': 'purchase'})
        self._create_picking()
        if self.company_id.po_lock == 'lock':
            self.write({'state': 'done'})
        return {}

    @api.multi
    def button_reorder(self):
        for order in self:
	    if order.product:
	      for pd in order.product:
	        pd.state = 'no'
        self.write({'state': 'write'})
        return {}

    @api.multi
    def button_draft(self):
        for order in self:
	    if order.product:
	      for pd in order.product:
	        pd.state = 'purchaseing'
        self.write({'state': 'draft'})
        return {}

    @api.multi
    def button_confirm(self):
        for order in self:
            if order.state not in ['draft', 'sent']:
                continue
            order._add_supplier_to_product()
            # Deal with double validation process
            if order.company_id.po_double_validation == 'one_step'\
                    or (order.company_id.po_double_validation == 'two_step'\
                        and order.amount_total < self.env.user.company_id.currency_id.compute(order.company_id.po_double_validation_amount, order.currency_id))\
                    or order.user_has_groups('purchase.group_purchase_manager'):
                order.button_approve()
            else:
                order.write({'state': 'to approve'})
	    for product in order.purchase_product:
	      product.write({'draft_request_date':datetime.today()})
        return True

    @api.multi
    def button_cancel(self):
        for order in self:
	    if order.product:
	      for pd in order.product:
	        pd.state = 'cancel'
                # Stock
                if pd.stock_item:
                  stock = self.env['product.product'].search([('model','=',pd.name),
                                                                 ('stock','>=',1)],limit=1)
                  if not stock:
                     stock = self.env['product.product'].search([('model','=',pd.specification),
                                                                 ('stock','>=',1)],limit=1)
                  if stock:
                    stock.stock = stock.stock + (pd.total_count)
            for pick in order.picking_ids:
                if pick.state == 'done':
                    raise UserError(_('Unable to cancel purchase order %s as some receptions have already been done.') % (order.name))
            for inv in order.invoice_ids:
                if inv and inv.state not in ('cancel', 'draft'):
                    raise UserError(_("Unable to cancel this purchase order. You must first cancel related vendor bills."))

            for pick in order.picking_ids.filtered(lambda r: r.state != 'cancel'):
                pick.action_cancel()
            # TDE FIXME: I don' think context key is necessary, as actions are not related / called from each other

        self.write({'state': 'cancel'})

    @api.multi
    def button_unlock(self):
        self.write({'state': 'purchase'})

    @api.multi
    def button_done(self):
      #발주자에게 메일보내기
      gvm = gvm_mail()
      sender = request.env.user.name
      receiver = self.env['hr.employee'].search([('user_id','=',self.order_man.id)])
      #메타데이터 id
      post_id = self.id
      #문서번호(S0001)
      po_num = str(self.name)
      #사용모델위치
      model_name = 'gvm.purchase_product'
      #링크에서 찾아서 쓰면됨
      #현재페이지 위치 찾는 용도(리스트)
      menu_id = "357"
      action_id = "471"
      post = "발주 물품이 입고되었습니다. 확인해주세요."
      Flag = 2
      _logger.warning("sender%s"%sender)
      _logger.warning("receiver%s"%receiver.name)
      send_mail = gvm_mail().gvm_send_mail(sender, receiver, post, post_id, po_num, model_name, menu_id, action_id,Flag)

      #발주완료
      self.write({'state': 'done'})

    @api.multi
    def button_create_bill(self):
        bill = self.env['account.invoice']
	invoice_line_list = []
        self.write({'state': 'to approve'})
	for product in self.product:
	  invoice_line_ids = self.env['account.invoice.line'].create({'account_id':28,
			    'name':product.product_name,
			    'product_id_gvm':product.id,
			    'quantity':product.original_count,
			    'price_unit':product.price,
	  })
	  invoice_line_list.append(invoice_line_ids.id)
	bill_id = bill.create({
	       'purchase_id':self.id,
	       'partner_id': self.partner_id.id,
	       'invoice_line_ids': [(6, 0, invoice_line_list)],
	       'state':'draft',
	       'journal_id':2,
	       'type':'in_invoice',
	       'date_invoice': datetime.today()
	       #'number'
	})
	self.invoice_ids = bill_id

    @api.multi
    def _get_destination_location(self):
        self.ensure_one()
        if self.dest_address_id:
            return self.dest_address_id.property_stock_customer.id
        return self.picking_type_id.default_location_dest_id.id

    @api.model
    def _prepare_picking(self):
        if not self.group_id:
            self.group_id = self.group_id.create({
                'name': self.name,
                'partner_id': self.partner_id.id
            })
        if not self.partner_id.property_stock_supplier.id:
            raise UserError(_("You must set a Vendor Location for this partner %s") % self.partner_id.name)
        return {
            'picking_type_id': self.picking_type_id.id,
            'partner_id': self.partner_id.id,
            'date': self.date_order,
            'origin': self.name,
            'location_dest_id': self._get_destination_location(),
            'location_id': self.partner_id.property_stock_supplier.id,
            'company_id': self.company_id.id,
        }

    @api.multi
    def _create_picking(self):
        StockPicking = self.env['stock.picking']
        return {}

    @api.multi
    def _add_supplier_to_product(self):
        return {}

    @api.multi
    def action_view_picking(self):
        '''
        This function returns an action that display existing picking orders of given purchase order ids.
        When only one found, show the picking immediately.
        '''
        action = self.env.ref('stock.action_picking_tree')
        result = action.read()[0]

        #override the context to get rid of the default filtering on picking type
        result.pop('id', None)
        result['context'] = {}
        pick_ids = sum([order.picking_ids.ids for order in self], [])
        #choose the view_mode accordingly
        if len(pick_ids) > 1:
            result['domain'] = "[('id','in',[" + ','.join(map(str, pick_ids)) + "])]"
        elif len(pick_ids) == 1:
            res = self.env.ref('stock.view_picking_form', False)
            result['views'] = [(res and res.id or False, 'form')]
            result['res_id'] = pick_ids and pick_ids[0] or False
        return result

    @api.multi
    def action_view_invoice(self):
        '''
        This function returns an action that display existing vendor bills of given purchase order ids.
        When only one found, show the vendor bill immediately.
        '''
        action = self.env.ref('account.action_invoice_tree2')
        result = action.read()[0]

        #override the context to get rid of the default filtering
        result['context'] = {'type': 'in_invoice', 'default_purchase_id': self.id}

        if not self.invoice_ids:
            # Choose a default account journal in the same currency in case a new invoice is created
            journal_domain = [
                ('type', '=', 'purchase'),
                ('company_id', '=', self.company_id.id),
                ('currency_id', '=', self.currency_id.id),
            ]
            default_journal_id = self.env['account.journal'].search(journal_domain, limit=1)
            if default_journal_id:
                result['context']['default_journal_id'] = default_journal_id.id
        else:
            # Use the same account journal than a previous invoice
            result['context']['default_journal_id'] = self.invoice_ids[0].journal_id.id

        #choose the view_mode accordingly
        if len(self.invoice_ids) != 1:
            result['domain'] = "[('id', 'in', " + str(self.invoice_ids.ids) + ")]"
        elif len(self.invoice_ids) == 1:
            res = self.env.ref('account.invoice_supplier_form', False)
            result['views'] = [(res and res.id or False, 'form')]
            result['res_id'] = self.invoice_ids.id
        return result

    @api.multi
    def action_set_date_planned(self):
        return {}
