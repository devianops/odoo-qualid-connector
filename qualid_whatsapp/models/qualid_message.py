# -*- coding: utf-8 -*-
import json
import logging
import threading
from datetime import timedelta

from markupsafe import Markup

from odoo import _, api, fields, models

from .qualid_media import MEDIA_SOURCES, QualidMediaError

_logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
RETRYABLE_STATUS = {0, 409, 429, 500, 502, 503, 504}
CRON_BATCH = 50


class QualidWhatsappMessage(models.Model):
    _name = 'qualid.whatsapp.message'
    _description = 'Quali-D WhatsApp Message'
    _order = 'id desc'
    _rec_name = 'template_name'

    state = fields.Selection([
        ('queued', 'Queued'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('cancel', 'Cancelled'),
    ], default='queued', required=True, index=True, readonly=True)

    res_model = fields.Char('Document Model', readonly=True, index=True)
    res_id = fields.Many2oneReference('Document ID', model_field='res_model', readonly=True, index=True)
    record_name = fields.Char('Document', readonly=True)

    phone = fields.Char(readonly=True)
    template_id = fields.Many2one('qualid.whatsapp.template', 'Template Record', readonly=True, ondelete='set null')
    template_name = fields.Char('Template', readonly=True, required=True)
    template_language = fields.Char('Language', readonly=True, required=True)
    body_params = fields.Text('Body Variables', readonly=True, help='JSON list')
    header_text = fields.Char(readonly=True)
    media_type = fields.Selection(
        [('image', 'Image'), ('video', 'Video'), ('document', 'Document')], 'Header Type', readonly=True,
    )
    media_source = fields.Selection(MEDIA_SOURCES, 'Header File', readonly=True)
    media_report_id = fields.Many2one('ir.actions.report', 'PDF Report', readonly=True, ondelete='set null')
    media_field_name = fields.Char('Header Field', readonly=True)
    media_attachment_filter = fields.Char('Attachment Filter', readonly=True)
    media_url = fields.Char('Header File Link', readonly=True,
                            help='Public link sent to WhatsApp. Files uploaded from Odoo are kept with the Quali-D conversation history.')
    media_filename = fields.Char('Header File Name', readonly=True)

    action_id = fields.Many2one('ir.actions.server', 'Server Action', readonly=True, ondelete='set null')
    idempotency_key = fields.Char(readonly=True, copy=False, index=True)

    attempts = fields.Integer(readonly=True, default=0)
    next_attempt = fields.Datetime(readonly=True, index=True)
    sent_date = fields.Datetime(readonly=True)
    wa_message_id = fields.Char('WhatsApp Message ID', readonly=True)
    qualid_log_id = fields.Integer('Quali-D Log ID', readonly=True)
    error_code = fields.Char(readonly=True)
    error_message = fields.Text(readonly=True)

    _idempotency_key_uniq = models.Constraint(
        'unique(idempotency_key)',
        'This message was already queued for this record.',
    )

    # ------------------------------------------------------------------
    # Queueing
    # ------------------------------------------------------------------
    @api.model
    def _qualid_enqueue(self, records, template, param_lines, phone_path=None, media_spec=None,
                        action=None, once_per_record=False, send_now=False, phone=None):
        """Create one message per record. Returns the created/requeued messages.

        `phone` forces the recipient (single-record manual sends only).
        """
        Api = self.env['qualid.api']
        Message = self.sudo()
        result = Message.browse()
        media_vals = dict(media_spec or {})

        forced_phone = phone
        for record in records:
            phone = forced_phone or Api._qualid_resolve_phone(record, phone_path)
            body, header, empty = [], None, []
            for line in param_lines.sorted(lambda l: (l.sequence, l.id)):
                val = line._qualid_value(record)
                if not (val or '').strip():
                    # WhatsApp rejects empty variables — fail clearly instead of sending.
                    empty.append('{{%s}} (%s)' % (line.placeholder, line.field_path if line.source == 'field' else _('fixed text')))
                if line.component == 'header':
                    header = val
                else:
                    body.append(val)
            empty_error = _('Empty template variable for this record: %s. Fill in the field on the record '
                            '(or change the variable), then retry.', ', '.join(empty)) if empty else False

            key = False
            if once_per_record and action:
                key = 'action:%s:%s:%s' % (action.id, record._name, record.id)
                existing = Message.search([('idempotency_key', '=', key)], limit=1)
                if existing:
                    if existing.state in ('failed', 'cancel'):
                        existing.write({
                            'state': 'failed' if empty_error else 'queued', 'phone': phone,
                            'body_params': json.dumps(body),
                            'header_text': header, 'attempts': 0, 'next_attempt': False,
                            'error_code': 'EMPTY_VARIABLE' if empty_error else False,
                            'error_message': empty_error or False, 'media_filename': False,
                            **media_vals,
                        })
                        result |= existing
                    continue

            vals = {
                'res_model': record._name,
                'res_id': record.id,
                'record_name': (record.display_name or '')[:250],
                'phone': phone,
                'template_id': template.id,
                'template_name': template.name,
                'template_language': template.language,
                'body_params': json.dumps(body),
                'header_text': header,
                **media_vals,
                'action_id': action.id if action else False,
                'idempotency_key': key,
            }
            if not phone:
                vals.update(state='failed', error_code='NO_PHONE',
                            error_message=_('No phone number found on the record.'))
            elif empty_error:
                vals.update(state='failed', error_code='EMPTY_VARIABLE', error_message=empty_error)
            msg = Message.create(vals)
            if msg.state == 'failed':
                msg._qualid_post_chatter()
            result |= msg

        queued = result.filtered(lambda m: m.state == 'queued')
        if queued:
            if send_now:
                queued._qualid_send()
            else:
                self._qualid_trigger_cron()
        return result

    @api.model
    def _qualid_trigger_cron(self, at=None):
        cron = self.env.ref('qualid_whatsapp.ir_cron_qualid_send_queue', raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger(at=at)

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------
    def _qualid_payload(self):
        self.ensure_one()
        db_uuid = self.env['ir.config_parameter'].sudo().get_str('database.uuid', '')
        payload = {
            'to': self.phone,
            'template': self.template_name,
            'language': self.template_language,
            'body_params': json.loads(self.body_params or '[]'),
            'odoo_model': self.res_model,
            'odoo_id': self.res_id,
            # Stable per message: a retry after a timeout can never double-send.
            'idempotency_key': 'odoo:%s:%s' % (db_uuid[:16], self.id),
        }
        if self.header_text:
            payload['header_text'] = self.header_text
        if self.media_type and self.media_url:
            payload['header_media_url'] = self.media_url
            payload['header_media_type'] = self.media_type
        return payload

    def _qualid_send(self):
        Api = self.env['qualid.api']
        for msg in self.sudo():
            if msg.state != 'queued':
                continue
            if msg.media_type and not msg.media_url:
                try:
                    url, filename = self.env['qualid.media.resolver']._qualid_resolve(msg)
                    msg.write({'media_url': url, 'media_filename': filename or False})
                except QualidMediaError as e:
                    msg.write({'state': 'failed', 'attempts': msg.attempts + 1,
                               'error_code': e.code, 'error_message': e.message, 'next_attempt': False})
                    msg._qualid_post_chatter()
                    continue
            status, data = Api._qualid_request('POST', '/odoo_send_template', payload=msg._qualid_payload(),
                                               raise_on_error=False)
            attempts = msg.attempts + 1
            if status == 200 and data.get('success'):
                msg.write({
                    'state': 'sent',
                    'attempts': attempts,
                    'sent_date': fields.Datetime.now(),
                    'wa_message_id': data.get('whatsapp_message_id'),
                    'qualid_log_id': data.get('log_id') or 0,
                    'error_code': False,
                    'error_message': False,
                    'next_attempt': False,
                })
            elif status in RETRYABLE_STATUS and attempts < MAX_ATTEMPTS and data.get('error_code') != 'NO_TOKEN':
                delay = 60 * (5 ** (attempts - 1))  # 1 min, 5 min
                if data.get('retry_after'):
                    delay = max(delay, int(data['retry_after']))
                at = fields.Datetime.now() + timedelta(seconds=delay)
                msg.write({
                    'attempts': attempts,
                    'next_attempt': at,
                    'error_code': data.get('error_code'),
                    'error_message': data.get('message'),
                })
                self._qualid_trigger_cron(at=at)
            else:
                msg.write({
                    'state': 'failed',
                    'attempts': attempts,
                    'error_code': data.get('error_code') or ('HTTP_%s' % status),
                    'error_message': data.get('message') or _('Unknown error'),
                    'next_attempt': False,
                })
            if msg.state in ('sent', 'failed'):
                msg._qualid_post_chatter()

    def _qualid_post_chatter(self):
        for msg in self:
            if not msg.res_model or not msg.res_id or msg.res_model not in self.env:
                continue
            record = self.env[msg.res_model].browse(msg.res_id).exists()
            if not record or not hasattr(record, 'message_post'):
                continue
            if msg.state == 'sent':
                body = Markup(_('WhatsApp template <b>%(tpl)s</b> sent to %(phone)s via Quali-D.')) % {
                    'tpl': msg.template_name, 'phone': msg.phone,
                }
            else:
                body = Markup(_('WhatsApp template <b>%(tpl)s</b> could not be sent: %(err)s')) % {
                    'tpl': msg.template_name, 'err': msg.error_message or msg.error_code or '',
                }
            try:
                record.sudo().message_post(body=body, subtype_xmlid='mail.mt_note')
            except Exception:  # noqa: BLE001 — chatter is best-effort
                _logger.exception('Quali-D: could not post chatter note on %s,%s', msg.res_model, msg.res_id)

    @api.model
    def _cron_process_queue(self):
        now = fields.Datetime.now()
        domain = [('state', '=', 'queued'), '|', ('next_attempt', '=', False), ('next_attempt', '<=', now)]
        ids = self.search(domain, limit=CRON_BATCH, order='id').ids
        testing = getattr(threading.current_thread(), 'testing', False)

        for msg_id in ids:
            # Lock the row so a parallel "send now" or second worker cannot send it twice.
            self.env.cr.execute(
                "SELECT id FROM qualid_whatsapp_message WHERE id = %s AND state = 'queued' FOR UPDATE SKIP LOCKED",
                (msg_id,),
            )
            if not self.env.cr.fetchone():
                continue
            msg = self.browse(msg_id)
            try:
                msg._qualid_send()
            except Exception:  # noqa: BLE001
                _logger.exception('Quali-D: unexpected error sending message %s', msg_id)
                self.env.cr.rollback()
                continue
            if not testing:
                self.env.cr.commit()  # pylint: disable=invalid-commit

        if len(ids) == CRON_BATCH:
            self._qualid_trigger_cron()

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------
    def action_retry(self):
        to_retry = self.filtered(lambda m: m.state in ('failed', 'cancel') and m.phone)
        to_retry.write({'state': 'queued', 'attempts': 0, 'next_attempt': False,
                        'error_code': False, 'error_message': False})
        # regenerate files produced from the record (fresh PDF / attachment / image)
        to_retry.filtered(lambda m: m.media_source not in (False, 'url', 'url_field')).write(
            {'media_url': False, 'media_filename': False})
        if to_retry:
            self._qualid_trigger_cron()
        return True

    def action_cancel(self):
        self.filtered(lambda m: m.state == 'queued').write({'state': 'cancel'})
        return True

    def action_open_record(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'view_mode': 'form',
            'target': 'current',
        }
