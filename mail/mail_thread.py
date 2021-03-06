# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2009-today OpenERP SA (<http://www.openerp.com>)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>
#
##############################################################################

import base64
import dateutil
import email
import logging
import pytz
import time
import tools
import xmlrpclib

from email.message import Message
from mail_message import decode
from openerp import SUPERUSER_ID
from osv import osv, fields
from tools.safe_eval import safe_eval as eval

_logger = logging.getLogger(__name__)

def decode_header(message, header, separator=' '):
    return separator.join(map(decode, message.get_all(header, [])))


class mail_thread(osv.AbstractModel):
    ''' mail_thread model is meant to be inherited by any model that needs to
        act as a discussion topic on which messages can be attached. Public
        methods are prefixed with ``message_`` in order to avoid name
        collisions with methods of the models that will inherit from this class.

        ``mail.thread`` defines fields used to handle and display the
        communication history. ``mail.thread`` also manages followers of
        inheriting classes. All features and expected behavior are managed
        by mail.thread. Widgets has been designed for the 7.0 and following
        versions of OpenERP.

        Inheriting classes are not required to implement any method, as the
        default implementation will work for any model. However it is common
        to override at least the ``message_new`` and ``message_update``
        methods (calling ``super``) to add model-specific behavior at
        creation and update of a thread when processing incoming emails.
    '''
    _name = 'mail.thread'
    _description = 'Email Thread'
    _mail_autothread = True

    def _get_message_data(self, cr, uid, ids, name, args, context=None):
        """ Computes:
            - message_unread: has uid unread message for the document
            - message_summary: html snippet summarizing the Chatter for kanban views """
        res = dict((id, dict(message_unread=False, message_summary='')) for id in ids)

        # search for unread messages, by reading directly mail.notification, as SUPERUSER
        notif_obj = self.pool.get('mail.notification')
        notif_ids = notif_obj.search(cr, SUPERUSER_ID, [
            ('partner_id.user_ids', 'in', [uid]),
            ('message_id.res_id', 'in', ids),
            ('message_id.model', '=', self._name),
            ('read', '=', False)
        ], context=context)
        for notif in notif_obj.browse(cr, SUPERUSER_ID, notif_ids, context=context):
            res[notif.message_id.res_id]['message_unread'] = True

        for thread in self.browse(cr, uid, ids, context=context):
            cls = res[thread.id]['message_unread'] and ' class="oe_kanban_mail_new"' or ''
            res[thread.id]['message_summary'] = "<span%s><span class='oe_e'>9</span> %d</span> <span><span class='oe_e'>+</span> %d</span>" % (cls, len(thread.message_comment_ids), len(thread.message_follower_ids))

        return res
        
    def _get_subscription_data(self, cr, uid, ids, name, args, context=None):
        """ Computes:
            - message_is_follower: is uid in the document followers
            - message_subtype_data: data about document subtypes: which are
                available, which are followed if any """
        res = dict((id, dict(message_subtype_data='', message_is_follower=False)) for id in ids)
        user_pid = self.pool.get('res.users').read(cr, uid, uid, ['partner_id'], context=context)['partner_id'][0]

        # find current model subtypes, add them to a dictionary
        subtype_obj = self.pool.get('mail.message.subtype')
        subtype_ids = subtype_obj.search(cr, uid, ['|', ('res_model', '=', self._name), ('res_model', '=', False)], context=context)
        subtype_dict = dict((subtype.name, dict(default=subtype.default, followed=False, id=subtype.id)) for subtype in subtype_obj.browse(cr, uid, subtype_ids, context=context))
        for id in ids:
            res[id]['message_subtype_data'] = subtype_dict.copy()

        # find the document followers, update the data
        fol_obj = self.pool.get('mail.followers')
        fol_ids = fol_obj.search(cr, uid, [
            ('partner_id', '=', user_pid),
            ('res_id', 'in', ids),
            ('res_model', '=', self._name),
        ], context=context)
        for fol in fol_obj.browse(cr, uid, fol_ids, context=context):
            thread_subtype_dict = res[fol.res_id]['message_subtype_data']
            res[fol.res_id]['message_is_follower'] = True
            for subtype in fol.subtype_ids:
                thread_subtype_dict[subtype.name]['followed'] = True
            res[fol.res_id]['message_subtype_data'] = thread_subtype_dict
        
        return res

    def _search_unread(self, cr, uid, obj=None, name=None, domain=None, context=None):
        partner_id = self.pool.get('res.users').read(cr, uid, uid, ['partner_id'], context=context)['partner_id'][0]
        res = {}
        notif_obj = self.pool.get('mail.notification')
        notif_ids = notif_obj.search(cr, uid, [
            ('partner_id', '=', partner_id),
            ('message_id.model', '=', self._name),
            ('read', '=', False)
        ], context=context)
        for notif in notif_obj.browse(cr, uid, notif_ids, context=context):
            res[notif.message_id.res_id] = True
        return [('id', 'in', res.keys())]

    def _get_followers(self, cr, uid, ids, name, arg, context=None):
        fol_obj = self.pool.get('mail.followers')
        fol_ids = fol_obj.search(cr, SUPERUSER_ID, [('res_model', '=', self._name), ('res_id', 'in', ids)])
        res = dict((res_id, []) for res_id in ids)
        for fol in fol_obj.browse(cr, SUPERUSER_ID, fol_ids):
            res[fol.res_id].append(fol.partner_id.id)
        return res

    def _set_followers(self, cr, uid, id, name, value, arg, context=None):
        if not value:
            return
        partner_obj = self.pool.get('res.partner')
        fol_obj = self.pool.get('mail.followers')

        # read the old set of followers, and determine the new set of followers
        fol_ids = fol_obj.search(cr, SUPERUSER_ID, [('res_model', '=', self._name), ('res_id', '=', id)])
        old = set(fol.partner_id.id for fol in fol_obj.browse(cr, SUPERUSER_ID, fol_ids))
        new = set(old)

        for command in value:
            if isinstance(command, (int, long)):
                new.add(command)
            elif command[0] == 0:
                new.add(partner_obj.create(cr, uid, command[2], context=context))
            elif command[0] == 1:
                partner_obj.write(cr, uid, [command[1]], command[2], context=context)
                new.add(command[1])
            elif command[0] == 2:
                partner_obj.unlink(cr, uid, [command[1]], context=context)
                new.discard(command[1])
            elif command[0] == 3:
                new.discard(command[1])
            elif command[0] == 4:
                new.add(command[1])
            elif command[0] == 5:
                new.clear()
            elif command[0] == 6:
                new = set(command[2])

        # remove partners that are no longer followers
        fol_ids = fol_obj.search(cr, SUPERUSER_ID,
            [('res_model', '=', self._name), ('res_id', '=', id), ('partner_id', 'not in', list(new))])
        fol_obj.unlink(cr, SUPERUSER_ID, fol_ids)

        # add new followers
        for partner_id in new - old:
            fol_obj.create(cr, SUPERUSER_ID, {'res_model': self._name, 'res_id': id, 'partner_id': partner_id})

    def _search_followers(self, cr, uid, obj, name, args, context):
        fol_obj = self.pool.get('mail.followers')
        res = []
        for field, operator, value in args:
            assert field == name
            fol_ids = fol_obj.search(cr, SUPERUSER_ID, [('res_model', '=', self._name), ('partner_id', operator, value)])
            res_ids = [fol.res_id for fol in fol_obj.browse(cr, SUPERUSER_ID, fol_ids)]
            res.append(('id', 'in', res_ids))
        return res

    _columns = {
        'message_is_follower': fields.function(_get_subscription_data,
            type='boolean', string='Is a Follower', multi='_get_subscription_data,'),
        'message_subtype_data': fields.function(_get_subscription_data,
            type='text', string='Subscription data', multi="_get_subscription_data",
            help="Holds data about the subtypes. The content of this field "\
                  "is a structure holding the current model subtypes, and the "\
                  "current document followed subtypes."),
        'message_follower_ids': fields.function(_get_followers, fnct_inv=_set_followers,
                fnct_search=_search_followers, type='many2many', obj='res.partner', string='Followers'),
        'message_comment_ids': fields.one2many('mail.message', 'res_id',
            domain=lambda self: [('model', '=', self._name), ('type', 'in', ('comment', 'email'))],
            string='Comments and emails',
            help="Comments and emails"),
        'message_ids': fields.one2many('mail.message', 'res_id',
            domain=lambda self: [('model', '=', self._name)],
            string='Messages',
            help="Messages and communication history"),
        'message_unread': fields.function(_get_message_data, fnct_search=_search_unread,
            type='boolean', string='Unread Messages', multi="_get_message_data",
            help="If checked new messages require your attention."),
        'message_summary': fields.function(_get_message_data, method=True,
            type='text', string='Summary', multi="_get_message_data",
            help="Holds the Chatter summary (number of messages, ...). "\
                 "This summary is directly in html format in order to "\
                 "be inserted in kanban views."),
    }

    #------------------------------------------------------
    # Automatic subscription when creating
    #------------------------------------------------------

    def create(self, cr, uid, vals, context=None):
        """ Override to subscribe the current user. """
        thread_id = super(mail_thread, self).create(cr, uid, vals, context=context)
        self.message_subscribe_users(cr, uid, [thread_id], [uid], context=context)
        return thread_id

    def unlink(self, cr, uid, ids, context=None):
        """ Override unlink to delete messages and followers. This cannot be
            cascaded, because link is done through (res_model, res_id). """
        msg_obj = self.pool.get('mail.message')
        fol_obj = self.pool.get('mail.followers')
        # delete messages and notifications
        msg_ids = msg_obj.search(cr, uid, [('model', '=', self._name), ('res_id', 'in', ids)], context=context)
        msg_obj.unlink(cr, uid, msg_ids, context=context)
        # delete followers
        fol_ids = fol_obj.search(cr, uid, [('res_model', '=', self._name), ('res_id', 'in', ids)], context=context)
        fol_obj.unlink(cr, uid, fol_ids, context=context)
        return super(mail_thread, self).unlink(cr, uid, ids, context=context)

    def copy(self, cr, uid, id, default=None, context=None):
        default = default or {}
        default['message_ids'] = []
        default['message_comment_ids'] = []
        default['message_follower_ids'] = []
        return super(mail_thread, self).copy(cr, uid, id, default=default, context=context)

    #------------------------------------------------------
    # mail.message wrappers and tools
    #------------------------------------------------------

    def _needaction_domain_get(self, cr, uid, context=None):
        if self._needaction:
            return [('message_unread', '=', True)]
        return []

    #------------------------------------------------------
    # Mail gateway
    #------------------------------------------------------

    def message_capable_models(self, cr, uid, context=None):
        """ Used by the plugin addon, based for plugin_outlook and others. """
        ret_dict = {}
        for model_name in self.pool.obj_list():
            model = self.pool.get(model_name)
            if 'mail.thread' in getattr(model, '_inherit', []):
                ret_dict[model_name] = model._description
        return ret_dict

    def _message_find_partners(self, cr, uid, message, header_fields=['From'], context=None):
        """ Find partners related to some header fields of the message. """
        s = ', '.join([decode(message.get(h)) for h in header_fields if message.get(h)])
        return [partner_id for email in tools.email_split(s)
                for partner_id in self.pool.get('res.partner').search(cr, uid, [('email', 'ilike', email)], context=context)]

    def _message_find_user_id(self, cr, uid, message, context=None):
        from_local_part = tools.email_split(decode(message.get('From')))[0]
        # FP Note: canonification required, the minimu: .lower()
        user_ids = self.pool.get('res.users').search(cr, uid, ['|',
            ('login', '=', from_local_part),
            ('email', '=', from_local_part)], context=context)
        return user_ids[0] if user_ids else uid

    def message_route(self, cr, uid, message, model=None, thread_id=None,
                      custom_values=None, context=None):
        """Attempt to figure out the correct target model, thread_id,
        custom_values and user_id to use for an incoming message.
        Multiple values may be returned, if a message had multiple
        recipients matching existing mail.aliases, for example.

        The following heuristics are used, in this order:
             1. If the message replies to an existing thread_id, and
                properly contains the thread model in the 'In-Reply-To'
                header, use this model/thread_id pair, and ignore
                custom_value (not needed as no creation will take place)
             2. Look for a mail.alias entry matching the message
                recipient, and use the corresponding model, thread_id,
                custom_values and user_id.
             3. Fallback to the ``model``, ``thread_id`` and ``custom_values``
                provided.
             4. If all the above fails, raise an exception.

           :param string message: an email.message instance
           :param string model: the fallback model to use if the message
               does not match any of the currently configured mail aliases
               (may be None if a matching alias is supposed to be present)
           :type dict custom_values: optional dictionary of default field values
                to pass to ``message_new`` if a new record needs to be created.
                Ignored if the thread record already exists, and also if a
                matching mail.alias was found (aliases define their own defaults)
           :param int thread_id: optional ID of the record/thread from ``model``
               to which this mail should be attached. Only used if the message
               does not reply to an existing thread and does not match any mail alias.
           :return: list of [model, thread_id, custom_values, user_id]
        """
        assert isinstance(message, Message), 'message must be an email.message.Message at this point'
        message_id = message.get('Message-Id')

        # 1. Verify if this is a reply to an existing thread
        references = decode_header(message, 'References') or decode_header(message, 'In-Reply-To')
        ref_match = references and tools.reference_re.search(references)
        if ref_match:
            thread_id = int(ref_match.group(1))
            model = ref_match.group(2) or model
            model_pool = self.pool.get(model)
            if thread_id and model and model_pool and model_pool.exists(cr, uid, thread_id) \
                and hasattr(model_pool, 'message_update'):
                _logger.debug('Routing mail with Message-Id %s: direct reply to model: %s, thread_id: %s, custom_values: %s, uid: %s',
                              message_id, model, thread_id, custom_values, uid)
                return [(model, thread_id, custom_values, uid)]

        # 2. Look for a matching mail.alias entry
        # Delivered-To is a safe bet in most modern MTAs, but we have to fallback on To + Cc values
        # for all the odd MTAs out there, as there is no standard header for the envelope's `rcpt_to` value.
        rcpt_tos = decode_header(message, 'Delivered-To') or \
             ','.join([decode_header(message, 'To'),
                       decode_header(message, 'Cc'),
                       decode_header(message, 'Resent-To'),
                       decode_header(message, 'Resent-Cc')])
        local_parts = [e.split('@')[0] for e in tools.email_split(rcpt_tos)]
        if local_parts:
            mail_alias = self.pool.get('mail.alias')
            alias_ids = mail_alias.search(cr, uid, [('alias_name', 'in', local_parts)])
            if alias_ids:
                routes = []
                for alias in mail_alias.browse(cr, uid, alias_ids, context=context):
                    user_id = alias.alias_user_id.id
                    if not user_id:
                        user_id = self._message_find_user_id(cr, uid, message, context=context)
                    routes.append((alias.alias_model_id.model, alias.alias_force_thread_id, \
                                   eval(alias.alias_defaults), user_id))
                _logger.debug('Routing mail with Message-Id %s: direct alias match: %r', message_id, routes)
                return routes

        # 3. Fallback to the provided parameters, if they work
        model_pool = self.pool.get(model)
        if not thread_id:
            # Legacy: fallback to matching [ID] in the Subject
            match = tools.res_re.search(decode_header(message, 'Subject'))
            thread_id = match and match.group(1)
        assert thread_id and hasattr(model_pool, 'message_update') or hasattr(model_pool, 'message_new'), \
            "No possible route found for incoming message with Message-Id %s. " \
            "Create an appropriate mail.alias or force the destination model." % message_id
        if thread_id and not model_pool.exists(cr, uid, thread_id):
            _logger.warning('Received mail reply to missing document %s! Ignoring and creating new document instead for Message-Id %s',
                            thread_id, message_id)
            thread_id = None
        _logger.debug('Routing mail with Message-Id %s: fallback to model:%s, thread_id:%s, custom_values:%s, uid:%s',
                      message_id, model, thread_id, custom_values, uid)
        return [(model, thread_id, custom_values, uid)]

    def message_process(self, cr, uid, model, message, custom_values=None,
                        save_original=False, strip_attachments=False,
                        thread_id=None, context=None):
        """Process an incoming RFC2822 email message, relying on
           ``mail.message.parse()`` for the parsing operation,
           and ``message_route()`` to figure out the target model.

           Once the target model is known, its ``message_new`` method
           is called with the new message (if the thread record did not exist)
            or its ``message_update`` method (if it did).

           :param string model: the fallback model to use if the message
               does not match any of the currently configured mail aliases
               (may be None if a matching alias is supposed to be present)
           :param message: source of the RFC2822 message
           :type message: string or xmlrpclib.Binary
           :type dict custom_values: optional dictionary of field values
                to pass to ``message_new`` if a new record needs to be created.
                Ignored if the thread record already exists, and also if a
                matching mail.alias was found (aliases define their own defaults)
           :param bool save_original: whether to keep a copy of the original
                email source attached to the message after it is imported.
           :param bool strip_attachments: whether to strip all attachments
                before processing the message, in order to save some space.
           :param int thread_id: optional ID of the record/thread from ``model``
               to which this mail should be attached. When provided, this
               overrides the automatic detection based on the message
               headers.
        """
        if context is None: context = {}

        # extract message bytes - we are forced to pass the message as binary because
        # we don't know its encoding until we parse its headers and hence can't
        # convert it to utf-8 for transport between the mailgate script and here.
        if isinstance(message, xmlrpclib.Binary):
            message = str(message.data)
        # Warning: message_from_string doesn't always work correctly on unicode,
        # we must use utf-8 strings here :-(
        if isinstance(message, unicode):
            message = message.encode('utf-8')
        msg_txt = email.message_from_string(message)
        routes = self.message_route(cr, uid, msg_txt, model,
                                    thread_id, custom_values,
                                    context=context)
        msg = self.message_parse(cr, uid, msg_txt, save_original=save_original, context=context)
        if strip_attachments: msg.pop('attachments', None)
        thread_id = False
        for model, thread_id, custom_values, user_id in routes:
            if self._name != model:
                context.update({'thread_model': model})
            model_pool = self.pool.get(model)
            assert thread_id and hasattr(model_pool, 'message_update') or hasattr(model_pool, 'message_new'), \
                "Undeliverable mail with Message-Id %s, model %s does not accept incoming emails" % \
                    (msg['message_id'], model)
            if thread_id and hasattr(model_pool, 'message_update'):
                model_pool.message_update(cr, user_id, [thread_id], msg, context=context)
            else:
                thread_id = model_pool.message_new(cr, user_id, msg, custom_values, context=context)
            model_pool.message_post(cr, uid, [thread_id], context=context, **msg)
        return thread_id

    def message_new(self, cr, uid, msg_dict, custom_values=None, context=None):
        """Called by ``message_process`` when a new message is received
           for a given thread model, if the message did not belong to
           an existing thread.
           The default behavior is to create a new record of the corresponding
           model (based on some very basic info extracted from the message).
           Additional behavior may be implemented by overriding this method.

           :param dict msg_dict: a map containing the email details and
                                 attachments. See ``message_process`` and
                                ``mail.message.parse`` for details.
           :param dict custom_values: optional dictionary of additional
                                      field values to pass to create()
                                      when creating the new thread record.
                                      Be careful, these values may override
                                      any other values coming from the message.
           :param dict context: if a ``thread_model`` value is present
                                in the context, its value will be used
                                to determine the model of the record
                                to create (instead of the current model).
           :rtype: int
           :return: the id of the newly created thread object
        """
        if context is None:
            context = {}
        model = context.get('thread_model') or self._name
        model_pool = self.pool.get(model)
        fields = model_pool.fields_get(cr, uid, context=context)
        data = model_pool.default_get(cr, uid, fields, context=context)
        if 'name' in fields and not data.get('name'):
            data['name'] = msg_dict.get('subject', '')
        if custom_values and isinstance(custom_values, dict):
            data.update(custom_values)
        res_id = model_pool.create(cr, uid, data, context=context)
        return res_id

    def message_update(self, cr, uid, ids, msg_dict, update_vals=None, context=None):
        """Called by ``message_process`` when a new message is received
           for an existing thread. The default behavior is to update the record
           with update_vals taken from the incoming email.
           Additional behavior may be implemented by overriding this
           method.
           :param dict msg_dict: a map containing the email details and
                               attachments. See ``message_process`` and
                               ``mail.message.parse()`` for details.
           :param dict update_vals: a dict containing values to update records
                              given their ids; if the dict is None or is
                              void, no write operation is performed.
        """
        if update_vals:
            self.write(cr, uid, ids, update_vals, context=context)
        return True

    def _message_extract_payload(self, message, save_original=False):
        """Extract body as HTML and attachments from the mail message"""
        attachments = []
        body = u''
        if save_original:
            attachments.append(('original_email.eml', message.as_string()))
        if not message.is_multipart() or 'text/' in message.get('content-type', ''):
            encoding = message.get_content_charset()
            body = message.get_payload(decode=True)
            body = tools.ustr(body, encoding, errors='replace')
            if message.get_content_type() == 'text/plain':
                # text/plain -> <pre/>
                body = tools.append_content_to_html(u'', body)
        else:
            alternative = (message.get_content_type() == 'multipart/alternative')
            for part in message.walk():
                if part.get_content_maintype() == 'multipart':
                    continue # skip container
                filename = part.get_filename() # None if normal part
                encoding = part.get_content_charset() # None if attachment
                # 1) Explicit Attachments -> attachments
                if filename or part.get('content-disposition', '').strip().startswith('attachment'):
                    attachments.append((filename or 'attachment', part.get_payload(decode=True)))
                    continue
                # 2) text/plain -> <pre/>
                if part.get_content_type() == 'text/plain' and (not alternative or not body):
                    body = tools.append_content_to_html(body, tools.ustr(part.get_payload(decode=True),
                                                                         encoding, errors='replace'))
                # 3) text/html -> raw
                elif part.get_content_type() == 'text/html':
                    html = tools.ustr(part.get_payload(decode=True), encoding, errors='replace')
                    if alternative:
                        body = html
                    else:
                        body = tools.append_content_to_html(body, html, plaintext=False)
                # 4) Anything else -> attachment
                else:
                    attachments.append((filename or 'attachment', part.get_payload(decode=True)))
        return body, attachments

    def message_parse(self, cr, uid, message, save_original=False, context=None):
        """Parses a string or email.message.Message representing an
           RFC-2822 email, and returns a generic dict holding the
           message details.

           :param message: the message to parse
           :type message: email.message.Message | string | unicode
           :param bool save_original: whether the returned dict
               should include an ``original`` attachment containing
               the source of the message
           :rtype: dict
           :return: A dict with the following structure, where each
                    field may not be present if missing in original
                    message::

                    { 'message_id': msg_id,
                      'subject': subject,
                      'from': from,
                      'to': to,
                      'cc': cc,
                      'body': unified_body,
                      'attachments': [('file1', 'bytes'),
                                      ('file2', 'bytes')}
                    }
        """
        msg_dict = {}
        if not isinstance(message, Message):
            if isinstance(message, unicode):
                # Warning: message_from_string doesn't always work correctly on unicode,
                # we must use utf-8 strings here :-(
                message = message.encode('utf-8')
            message = email.message_from_string(message)

        message_id = message['message-id']
        if not message_id:
            # Very unusual situation, be we should be fault-tolerant here
            message_id = "<%s@localhost>" % time.time()
            _logger.debug('Parsing Message without message-id, generating a random one: %s', message_id)
        msg_dict['message_id'] = message_id

        if 'Subject' in message:
            msg_dict['subject'] = decode(message.get('Subject'))

        # Envelope fields not stored in  mail.message but made available for message_new()
        msg_dict['from'] = decode(message.get('from'))
        msg_dict['to'] = decode(message.get('to'))
        msg_dict['cc'] = decode(message.get('cc'))

        if 'From' in message:
            author_ids = self._message_find_partners(cr, uid, message, ['From'], context=context)
            if author_ids:
                msg_dict['author_id'] = author_ids[0]
        partner_ids = self._message_find_partners(cr, uid, message, ['From', 'To', 'Cc'], context=context)
        msg_dict['partner_ids'] = partner_ids

        if 'Date' in message:
            date_hdr = decode(message.get('Date'))
            # convert from email timezone to server timezone
            date_server_datetime = dateutil.parser.parse(date_hdr).astimezone(pytz.timezone(tools.get_server_timezone()))
            date_server_datetime_str = date_server_datetime.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            msg_dict['date'] = date_server_datetime_str

        if 'In-Reply-To' in message:
            parent_ids = self.pool.get('mail.message').search(cr, uid, [('message_id', '=', decode(message['In-Reply-To']))])
            if parent_ids:
                msg_dict['parent_id'] = parent_ids[0]

        if 'References' in message and 'parent_id' not in msg_dict:
            parent_ids = self.pool.get('mail.message').search(cr, uid, [('message_id', 'in',
                                                                         [x.strip() for x in decode(message['References']).split()])])
            if parent_ids:
                msg_dict['parent_id'] = parent_ids[0]

        msg_dict['body'], msg_dict['attachments'] = self._message_extract_payload(message)
        return msg_dict

    #------------------------------------------------------
    # Note specific
    #------------------------------------------------------

    def log(self, cr, uid, id, message, secondary=False, context=None):
        _logger.warning("log() is deprecated. As this module inherit from "\
                        "mail.thread, the message will be managed by this "\
                        "module instead of by the res.log mechanism. Please "\
                        "use mail_thread.message_post() instead of the "\
                        "now deprecated res.log.")
        self.message_post(cr, uid, [id], message, context=context)

    def message_post(self, cr, uid, thread_id, body='', subject=None, type='notification',
                        subtype=None, parent_id=False, attachments=None, context=None, **kwargs):
        """ Post a new message in an existing thread, returning the new
            mail.message ID. Extra keyword arguments will be used as default
            column values for the new mail.message record.
            Auto link messages for same id and object
            :param int thread_id: thread ID to post into, or list with one ID
            :param str body: body of the message, usually raw HTML that will
                be sanitized
            :param str subject: optional subject
            :param str type: mail_message.type
            :param int parent_id: optional ID of parent message in this thread
            :param tuple(str,str) attachments: list of attachment tuples in the form
                ``(name,content)``, where content is NOT base64 encoded
            :return: ID of newly created mail.message
        """

        context = context or {}
        attachments = attachments or []
        assert (not thread_id) or isinstance(thread_id, (int, long)) or \
            (isinstance(thread_id, (list, tuple)) and len(thread_id) == 1), "Invalid thread_id"
        if isinstance(thread_id, (list, tuple)):
            thread_id = thread_id and thread_id[0]

        attachment_ids = []
        for name, content in attachments:
            if isinstance(content, unicode):
                content = content.encode('utf-8')
            data_attach = {
                'name': name,
                'datas': base64.b64encode(str(content)),
                'datas_fname': name,
                'description': name,
                'res_model': context.get('thread_model') or self._name,
                'res_id': thread_id,
            }
            attachment_ids.append((0, 0, data_attach))

        # get subtype
        if not subtype:
            subtype = 'mail.mt_comment'
        s = subtype.split('.')
        if len(s)==1:
            s = ('mail', s[0])
        ref = self.pool.get('ir.model.data').get_object_reference(cr, uid, s[0], s[1])
        subtype_id = ref and ref[1] or False

        model = context.get('thread_model', self._name) if thread_id else False
        messages = self.pool.get('mail.message')

        #auto link messages for same id and object
        if self._mail_autothread and thread_id:
            message_ids = messages.search(cr, uid, ['&',('res_id', '=', thread_id),('model','=',model)], context=context)
            if len(message_ids):
                parent_id = min(message_ids)


        values = kwargs
        values.update({
            'model': model,
            'res_id': thread_id or False,
            'body': body,
            'subject': subject or False,
            'type': type,
            'parent_id': parent_id,
            'attachment_ids': attachment_ids,
            'subtype_id': subtype_id,
        })
        # Avoid warnings about non-existing fields
        for x in ('from', 'to', 'cc'):
            values.pop(x, None)

        return messages.create(cr, uid, values, context=context)

    #------------------------------------------------------
    # Followers API
    #------------------------------------------------------

    def message_post_api(self, cr, uid, thread_id, body='', subject=False, type='notification',
                        subtype=None, parent_id=False, attachments=None, context=None, **kwargs):
        added_message_id = self.message_post(cr, uid, thread_id=thread_id, body=body, subject=subject, type=type,
                        subtype=subtype, parent_id=parent_id, attachments=attachments, context=context)
        added_message = self.pool.get('mail.message').message_read(cr, uid, [added_message_id])

        return added_message

    def get_message_subtypes(self, cr, uid, ids, context=None):
        """ message_subtype_data: data about document subtypes: which are
                available, which are followed if any """
        return self._get_subscription_data(cr, uid, ids, None, None, context=context)

    def message_subscribe_users(self, cr, uid, ids, user_ids=None, subtype_ids=None, context=None):
        """ Wrapper on message_subscribe, using users. If user_ids is not
            provided, subscribe uid instead. """
        if not user_ids:
            return False
        partner_ids = [user.partner_id.id for user in self.pool.get('res.users').browse(cr, uid, user_ids, context=context)]
        return self.message_subscribe(cr, uid, ids, partner_ids, subtype_ids=subtype_ids, context=context)

    def message_subscribe(self, cr, uid, ids, partner_ids, subtype_ids=None, context=None):
        """ Add partners to the records followers. """
        self.write(cr, uid, ids, {'message_follower_ids': [(4, pid) for pid in partner_ids]}, context=context)
        # if subtypes are not specified (and not set to a void list), fetch default ones
        if subtype_ids is None:
            subtype_obj = self.pool.get('mail.message.subtype')
            subtype_ids = subtype_obj.search(cr, uid, [('default', '=', True), '|', ('res_model', '=', self._name), ('res_model', '=', False)], context=context)
        # update the subscriptions
        fol_obj = self.pool.get('mail.followers')
        fol_ids = fol_obj.search(cr, 1, [('res_model', '=', self._name), ('res_id', 'in', ids), ('partner_id', 'in', partner_ids)], context=context)
        fol_obj.write(cr, 1, fol_ids, {'subtype_ids': [(6, 0, subtype_ids)]}, context=context)
        return True

    def message_unsubscribe_users(self, cr, uid, ids, user_ids=None, context=None):
        """ Wrapper on message_subscribe, using users. If user_ids is not
            provided, unsubscribe uid instead. """
        if not user_ids:
            user_ids = [uid]
        partner_ids = [user.partner_id.id for user in self.pool.get('res.users').browse(cr, uid, user_ids, context=context)]
        return self.message_unsubscribe(cr, uid, ids, partner_ids, context=context)

    def message_unsubscribe(self, cr, uid, ids, partner_ids, context=None):
        """ Remove partners from the records followers. """
        return self.write(cr, uid, ids, {'message_follower_ids': [(3, pid) for pid in partner_ids]}, context=context)

    #------------------------------------------------------
    # Thread state
    #------------------------------------------------------

    def message_mark_as_unread(self, cr, uid, ids, context=None):
        """ Set as unread. """
        partner_id = self.pool.get('res.users').browse(cr, uid, uid, context=context).partner_id.id
        cr.execute('''
            UPDATE mail_notification SET
                read=false
            WHERE
                message_id IN (SELECT id from mail_message where res_id=any(%s) and model=%s limit 1) and
                partner_id = %s
        ''', (ids, self._name, partner_id))
        return True

    def message_mark_as_read(self, cr, uid, ids, context=None):
        """ Set as read. """
        partner_id = self.pool.get('res.users').browse(cr, uid, uid, context=context).partner_id.id
        cr.execute('''
            UPDATE mail_notification SET
                read=true
            WHERE
                message_id IN (SELECT id FROM mail_message WHERE res_id=ANY(%s) AND model=%s) AND
                partner_id = %s
        ''', (ids, self._name, partner_id))
        return True

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
