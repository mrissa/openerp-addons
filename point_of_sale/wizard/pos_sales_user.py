# -*- coding: utf-8 -*-
##############################################################################
#    
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Tiny SPRL (<http://tiny.be>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.     
#
##############################################################################

import netsvc
from osv import osv,fields
from tools.translate import _
from mx import DateTime
import time

class pos_sale_user(osv.osv_memory):
    _name = 'pos.sale.user'
    _description = 'Sale by User'

    _columns = {
        'date_start': fields.date('Date Start',required=True),
        'date_end': fields.date('Date End',required=True),
        'user_id': fields.many2many('res.users', 'sale_user_rel', 'user_id', 'uid', 'Salesman'),        
    }
    
    def print_report(self, cr, uid, ids, context={}):
        """ 
         To get the date and print the report           
         @param self: The object pointer.
         @param cr: A database cursor
         @param uid: ID of the user currently logged in
         @param context: A standard dictionary 
         @return : return report
        """
        
        datas = {'ids' : context.get('active_ids', [])}
        res = self.read(cr, uid, ids, ['date_start','date_end','user_id'], context)
        res = res and res[0] or {}    
        datas['form'] = res        
        return { 
            'type':'ir.actions.report.xml',
            'report_name':'pos.sales.user',
            'datas':datas,               
       }
pos_sale_user()
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:

