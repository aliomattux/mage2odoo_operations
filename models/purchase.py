import pytz
from openerp import SUPERUSER_ID, workflow
from datetime import datetime
from dateutil.relativedelta import relativedelta
from operator import attrgetter
from openerp.tools.safe_eval import safe_eval as eval
from openerp.osv import fields, osv
from openerp.tools.translate import _
import openerp.addons.decimal_precision as dp
from openerp.osv.orm import browse_record_list, browse_record, browse_null
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT, DATETIME_FORMATS_MAP


class PurchaseSaleOrder(osv.osv):
    _name = 'purchase.sale.order'
    _columns = {
	'sale_id': fields.many2one('sale.order', string="Sale Order"),
	'purchase_id': fields.many2one('purchase.order', string="Purchase Order"),
    }


class PurchaseOrder(osv.osv):
    _inherit = 'purchase.order'
    _columns = {
                'anticipated_receive_date': fields.date('Anticipated Receipt Date'),
		'sale_orders': fields.many2many('sale.order', 'sale_order_purchase_rel', 'purchase_id', 'sale_id', 'Sale Orders', readonly=True, copy=False),
    }

#class PurchaseOrder(osv.osv):
 #   _inherit = 'purchase.order'

  #  def _prepare_order_line_move(self, cr, uid, order, order_line, picking_id, \
#		group_id, context=None):
#
 #       res = super(PurchaseOrder, self)._prepare_order_line_move(cr, uid, order, \
#		order_line, picking_id, group_id, context)
#
#	return res

class SaleOrder(osv.osv):
    _inherit = 'sale.order'
    _columns = {
	'purchase_ids': fields.many2many('purchase.order', 'sale_order_purchase_rel', 'sale_id', 'purchase_id', 'Purchase Orders', readonly=True, copy=False, help="This is the list of Purchase Orders that have been generated for this sales order"),
    }


class ProcurementOrder(osv.osv):
    _inherit = 'procurement.order'
    _columns = {
        'mo_sale': fields.many2one('sale.order')
    }


    def make_po(self, cr, uid, ids, context=None):
        """ Resolve the purchase from procurement, which may result in a new PO creation, a new PO line creation or a quantity change on existing PO line.
        Note that some operations (as the PO creation) are made as SUPERUSER because the current user may not have rights to do it (mto product launched by a sale for example)

        @return: dictionary giving for each procurement its related resolving PO line.
        """
        res = {}
        company = self.pool.get('res.users').browse(cr, uid, uid, context=context).company_id
        po_obj = self.pool.get('purchase.order')
        po_line_obj = self.pool.get('purchase.order.line')
        seq_obj = self.pool.get('ir.sequence')

	#####  ADDED  #####
	sale_obj = self.pool.get('sale.order')
	########

        pass_ids = []
        linked_po_ids = []
        sum_po_line_ids = []
        for procurement in self.browse(cr, uid, ids, context=context):
            partner = self._get_product_supplier(cr, uid, procurement, context=context)
            if not partner:
                self.message_post(cr, uid, [procurement.id], _('There is no supplier associated to product %s') % (procurement.product_id.name))
                res[procurement.id] = False
            else:
                schedule_date = self._get_purchase_schedule_date(cr, uid, procurement, company, context=context)
                purchase_date = self._get_purchase_order_date(cr, uid, procurement, company, schedule_date, context=context)
                line_vals = self._get_po_line_values_from_proc(cr, uid, procurement, partner, company, schedule_date, context=context)
                #look for any other draft PO for the same supplier, to attach the new line on instead of creating a new draft one
                available_draft_po_ids = po_obj.search(cr, uid, [
                    ('partner_id', '=', partner.id), ('state', '=', 'draft'), ('picking_type_id', '=', procurement.rule_id.picking_type_id.id),
                    ('location_id', '=', procurement.location_id.id), ('company_id', '=', procurement.company_id.id), ('dest_address_id', '=', procurement.partner_dest_id.id)], context=context)
                if available_draft_po_ids:
                    po_id = available_draft_po_ids[0]
                    po_rec = po_obj.browse(cr, uid, po_id, context=context)

		    #####  ADDED  #####
		    if procurement.mo_sale and po_rec not in procurement.mo_sale.purchase_ids:
			sale_obj.write(cr, uid, procurement.mo_sale.id, {'purchase_ids': [(4, po_rec.id)]})
		    #####  END  ######

                    #if the product has to be ordered earlier those in the existing PO, we replace the purchase date on the order to avoid ordering it too late
                    if datetime.strptime(po_rec.date_order, DEFAULT_SERVER_DATETIME_FORMAT) > purchase_date:
                        po_obj.write(cr, uid, [po_id], {'date_order': purchase_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT)}, context=context)
                    #look for any other PO line in the selected PO with same product and UoM to sum quantities instead of creating a new po line
                    available_po_line_ids = po_line_obj.search(cr, uid, [('order_id', '=', po_id), ('product_id', '=', line_vals['product_id']), ('product_uom', '=', line_vals['product_uom'])], context=context)
                    if available_po_line_ids:
                        po_line = po_line_obj.browse(cr, uid, available_po_line_ids[0], context=context)
                        po_line_obj.write(cr, SUPERUSER_ID, po_line.id, {'product_qty': po_line.product_qty + line_vals['product_qty']}, context=context)
                        po_line_id = po_line.id
                        sum_po_line_ids.append(procurement.id)
                    else:
                        line_vals.update(order_id=po_id)
                        po_line_id = po_line_obj.create(cr, SUPERUSER_ID, line_vals, context=context)
                        linked_po_ids.append(procurement.id)
                else:
                    name = seq_obj.get(cr, uid, 'purchase.order') or _('PO: %s') % procurement.name
                    po_vals = {
                        'name': name,
                        'origin': procurement.origin,
                        'partner_id': partner.id,
                        'location_id': procurement.location_id.id,
                        'picking_type_id': procurement.rule_id.picking_type_id.id,
                        'pricelist_id': partner.property_product_pricelist_purchase.id,
                        'currency_id': partner.property_product_pricelist_purchase and partner.property_product_pricelist_purchase.currency_id.id or procurement.company_id.currency_id.id,
                        'date_order': purchase_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                        'company_id': procurement.company_id.id,
                        'fiscal_position': partner.property_account_position and partner.property_account_position.id or False,
                        'payment_term_id': partner.property_supplier_payment_term.id or False,
                        'dest_address_id': procurement.partner_dest_id.id,
                    }

                    po_id = self.create_procurement_purchase_order(cr, SUPERUSER_ID, procurement, po_vals, line_vals, context=context)
		    #####  ADDED  ######
		    if procurement.mo_sale:
			sale_obj.write(cr, uid, procurement.mo_sale.id, {'purchase_ids': [(4, po_id)]})
		    #####  END  ######

                    po_line_id = po_obj.browse(cr, uid, po_id, context=context).order_line[0].id
                    pass_ids.append(procurement.id)
                res[procurement.id] = po_line_id
                self.write(cr, uid, [procurement.id], {'purchase_line_id': po_line_id}, context=context)
        if pass_ids:
            self.message_post(cr, uid, pass_ids, body=_("Draft Purchase Order created"), context=context)
        if linked_po_ids:
            self.message_post(cr, uid, linked_po_ids, body=_("Purchase line created and linked to an existing Purchase Order"), context=context)
        if sum_po_line_ids:
            self.message_post(cr, uid, sum_po_line_ids, body=_("Quantity added in existing Purchase Order Line"), context=context)
        return res




class StockMove(osv.osv):
    _inherit = 'stock.move'
 #   _columns = {
#	'mo_sale': fields.many2one('sale.order')
  #  }

    def _prepare_procurement_from_move(self, cr, uid, move, context=None):
	res = super(StockMove, self)._prepare_procurement_from_move(cr, uid, move, context)

	#If this is a make to order move, note this on the po procurement line
	if move.procurement_id.sale_line_id:
	    res['mo_sale'] = move.procurement_id.sale_line_id.order_id.id

	return res
