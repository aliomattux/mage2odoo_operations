from osv import osv, fields



class PrintHistory(osv.osv):
    _name = 'print.history'
    _columns = {
	'transaction': fields.many2one('stock.picking', 'Transaction'),
	'status': fields.selection([('fail', 'Failed'), ('success', 'Success')], 'Status'),
	'user_id': fields.many2one('res.users', 'Attempted By'),
	'date': fields.datetime('Date Attempted')
    }
