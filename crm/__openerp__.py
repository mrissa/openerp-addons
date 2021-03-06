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


{
    'name': 'CRM',
    'version': '1.0',
    'category': 'Customer Relationship Management',
    'sequence': 2,
    'summary': 'Leads, Opportunities, Phone Calls',
    'description': """
The generic OpenERP Customer Relationship Management
=====================================================

This application enables a group of people to intelligently and efficiently manage leads, opportunities, meetings and phone calls.

It manages key tasks such as communication, identification, prioritization, assignment, resolution and notification.

OpenERP ensures that all cases are successfully tracked by users, customers and suppliers. It can automatically send reminders, escalate the request, trigger specific methods and many other actions based on your own enterprise rules.

The greatest thing about this system is that users don't need to do anything special. The CRM module has an email gateway for the synchronization interface between mails and OpenERP. That way, users can just send emails to the request tracker.

OpenERP will take care of thanking them for their message, automatically routing it to the appropriate staff and make sure all future correspondence gets to the right place.


Dashboard for CRM will include:
-------------------------------
* Planned Revenue by Stage and User (graph)
* Opportunities by Stage (graph)
""",
    'author': 'OpenERP SA',
    'website': 'http://www.openerp.com',
    'depends': [
        'base_action_rule',
        'base_setup',
        'base_status',
        'process',
        'mail',
        'base_calendar',
        'resource',
        'board',
        'fetchmail'
    ],
    'data': [
        'crm_data.xml',
        'crm_lead_data.xml',
        'crm_phonecall_data.xml',

        'security/crm_security.xml',
        'security/ir.model.access.csv',

        'wizard/crm_lead_to_partner_view.xml',
        'wizard/crm_lead_to_opportunity_view.xml',

        'wizard/crm_phonecall_to_phonecall_view.xml',
        'wizard/crm_phonecall_to_partner_view.xml',
        'wizard/crm_phonecall_to_opportunity_view.xml',

        'wizard/crm_opportunity_to_phonecall_view.xml',
        'wizard/crm_partner_to_opportunity_view.xml',

        'wizard/crm_merge_opportunities_view.xml',

        'crm_view.xml',

        'crm_action_rule_view.xml',
        'crm_lead_view.xml',
        'crm_lead_menu.xml',

        'crm_meeting_view.xml',
        'crm_meeting_menu.xml',
        'crm_meeting_shortcut_data.xml',

        'crm_phonecall_view.xml',
        'crm_phonecall_menu.xml',

        'report/crm_lead_report_view.xml',
        'report/crm_phonecall_report_view.xml',

        'process/crm_configuration_process.xml',

        'res_partner_view.xml',
        'board_crm_view.xml',

        'res_config_view.xml',

    ],
    'demo': [
        'crm_demo.xml',
        'crm_lead_demo.xml',
        'crm_phonecall_demo.xml',
    ],
    'test': [
        'test/process/communication_with_customer.yml',
        'test/process/lead2opportunity2win.yml',
        'test/process/merge_opportunity.yml',
        'test/process/cancel_lead.yml',
        'test/process/action_rule.yml',
        'test/process/segmentation.yml',
        'test/process/phonecalls.yml',
        'test/ui/crm_demo.yml',
        'test/ui/duplicate_lead.yml',
        'test/ui/delete_lead.yml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'images': ['images/sale_crm_crm_dashboard.png', 'images/crm_dashboard.jpeg','images/leads.jpeg','images/meetings.jpeg','images/opportunities.jpeg','images/outbound_calls.jpeg','images/stages.jpeg'],
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
