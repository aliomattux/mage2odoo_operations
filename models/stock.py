from openerp.osv import osv, fields
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT, DEFAULT_SERVER_DATE_FORMAT
import time

class StockPicking(osv.osv):
    _inherit = 'stock.picking'
    _columns = {
	'printed': fields.boolean('Printed', select=True),
        'printer': fields.many2one('res.users', 'Printed By', help="User who printed picking"),
        'printed_date': fields.datetime('Date Printed', help="The date this picking was printed"),
	'anticipated_ship_date': fields.date('Anticipated Ship Date'),
    }
    _defaults = {
	'printed': False,
    }


class StockPickingType(osv.osv):
    _inherit = 'stock.picking.type'

    def _get_picking_count_domains(self, context=False):
        domains = {
            'count_picking_draft': [('state', '=', 'draft')],
            'count_picking_waiting': [('state', '=', 'confirmed')],
            'count_picking_ready': [('state', 'in', ('assigned', 'partially_available'))],
            'count_picking': [('state', 'in', ('assigned', 'waiting', 'confirmed', 'partially_available'))],
            'count_picking_late': [('min_date', '<', time.strftime(DEFAULT_SERVER_DATETIME_FORMAT)), ('state', 'in', ('assigned', 'waiting', 'confirmed', 'partially_available'))],
            'count_picking_backorders': [('backorder_id', '!=', False), ('state', 'in', ('confirmed', 'assigned', 'waiting', 'partially_available'))],
        }

	return domains


