# -*- coding: utf-8 -*-
"""Header media (image / video / document) for WhatsApp templates.

The same configuration is used by server actions (automation rules) and the
manual send wizard. Files that only exist inside Odoo (reports, attachments,
image fields) are uploaded to Quali-D, which returns a public link WhatsApp can
download. Quali-D deletes those files after 30 days.
"""
import base64
import io
import logging
import re
import time

from odoo import _, api, fields, models
from odoo.tools.mimetypes import guess_mimetype
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)

MEDIA_SOURCES = [
    ('report', 'PDF of this record (invoice, quotation…)'),
    ('attachment', 'Latest attachment on this record'),
    ('image_field', 'Image from this record'),
    ('url_field', 'Link stored in a field'),
    ('url', 'Same link for everyone'),
]

# Meta limits per header type (MB)
MEDIA_LIMIT_MB = {'image': 5, 'video': 16, 'document': 100}
IMAGE_MIMES = ('image/jpeg', 'image/png')
VIDEO_MIMES = ('video/mp4', 'video/3gpp')
MAX_IMAGE_SIDE = 1600


def mime_to_media_type(mimetype):
    mimetype = (mimetype or '').lower()
    if mimetype.startswith('image/'):
        return 'image'
    if mimetype.startswith('video/'):
        return 'video'
    return 'document'


def safe_filename(name, ext):
    base = re.sub(r'[^\w\-. ]+', '_', name or '', flags=re.UNICODE)
    base = re.sub(r'[\s_]+', '_', base).strip('._- ') or 'file'
    if base.lower().endswith('.' + ext):
        base = base[:-(len(ext) + 1)]
    return '%s.%s' % (base[:100], ext)


class QualidMediaError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class QualidMediaMixin(models.AbstractModel):
    _name = 'qualid.media.mixin'
    _description = 'Quali-D Header File Settings'

    qualid_media_source = fields.Selection(MEDIA_SOURCES, 'Header File', default='report')
    qualid_media_report_id = fields.Many2one(
        'ir.actions.report', 'Header PDF Report', ondelete='set null',
        help='The PDF Odoo prints for this record, e.g. Invoices or Quotation / Order.',
    )
    qualid_media_image_field_id = fields.Many2one(
        'ir.model.fields', 'Header Image Field', ondelete='set null',
        help='An image field on the record, e.g. the contact photo or product image.',
    )
    qualid_media_url_field_id = fields.Many2one(
        'ir.model.fields', 'Header Link Field', ondelete='set null',
        help='A text field on the record that contains a public https:// link to the file.',
    )
    qualid_media_attachment_filter = fields.Char(
        'Attachment Name Contains',
        help='Optional. Only use attachments whose name contains this text (e.g. "result").',
    )
    qualid_media_url = fields.Char('File Link', help='Public https:// link to the file.')

    # ------------------------------------------------------------------
    def _qualid_media_validate(self, template):
        """Return an error message if the header file setup can't work with this template."""
        self.ensure_one()
        if not template or not template._qualid_has_media_header():
            return False
        header = (template.header_format or '').lower()
        src = self.qualid_media_source
        if not src:
            return _('This template has a %s header — choose where the file comes from.', header)
        if src == 'report':
            if header != 'document':
                return _('A PDF report can only be sent with a Document header template. '
                         'This template needs: %s.', header)
            if not self.qualid_media_report_id:
                return _('Choose which PDF report to send.')
        elif src == 'image_field':
            if header != 'image':
                return _('An image field can only be sent with an Image header template. '
                         'This template needs: %s.', header)
            if not self.qualid_media_image_field_id:
                return _('Choose the image field.')
        elif src == 'url_field' and not self.qualid_media_url_field_id:
            return _('Choose the field that contains the link.')
        elif src == 'url':
            if not (self.qualid_media_url or '').lower().startswith(('https://', 'http://')):
                return _('Enter a public link starting with https://')
        return False

    def _qualid_media_spec(self, template):
        """Values stored on each queued message (resolved per record at send time)."""
        self.ensure_one()
        if not template or not template._qualid_has_media_header():
            return {}
        src = self.qualid_media_source
        return {
            'media_type': (template.header_format or '').lower(),
            'media_source': src,
            'media_report_id': self.qualid_media_report_id.id if src == 'report' else False,
            'media_field_name': (
                self.qualid_media_image_field_id.name if src == 'image_field'
                else self.qualid_media_url_field_id.name if src == 'url_field' else False
            ),
            'media_attachment_filter': self.qualid_media_attachment_filter if src == 'attachment' else False,
            'media_url': self.qualid_media_url if src == 'url' else False,
        }


class QualidMediaResolver(models.AbstractModel):
    """Turns a message's media settings + its record into a public link."""
    _name = 'qualid.media.resolver'
    _description = 'Quali-D Header File Resolver'

    @api.model
    def _qualid_resolve(self, message):
        """Return (url, filename). Raises QualidMediaError."""
        src = message.media_source
        expected = message.media_type
        if src == 'url':
            return message.media_url, False

        if not message.res_model or message.res_model not in self.env:
            raise QualidMediaError('MEDIA_NO_RECORD', _('The record this message belongs to no longer exists.'))
        record = self.env[message.res_model].sudo().browse(message.res_id).exists()
        if not record:
            raise QualidMediaError('MEDIA_NO_RECORD', _('The record this message belongs to no longer exists.'))

        if src == 'url_field':
            value = record[message.media_field_name] if message.media_field_name in record._fields else False
            value = (value or '').strip() if isinstance(value, str) else ''
            if not value.lower().startswith(('https://', 'http://')):
                raise QualidMediaError('MEDIA_NO_LINK', _('The field "%s" does not contain a link.', message.media_field_name))
            return value, False

        if src == 'report':
            content, filename, mimetype = self._qualid_render_report(message.media_report_id, record)
        elif src == 'attachment':
            content, filename, mimetype = self._qualid_find_attachment(record, expected, message.media_attachment_filter)
        elif src == 'image_field':
            content, filename, mimetype = self._qualid_read_image_field(record, message.media_field_name)
        else:
            raise QualidMediaError('MEDIA_NOT_CONFIGURED', _('No header file is configured for this template.'))

        if expected == 'image':
            content, filename, mimetype = self._qualid_prepare_image(content, filename, mimetype)

        actual = mime_to_media_type(mimetype)
        if actual != expected:
            raise QualidMediaError('MEDIA_TYPE_MISMATCH', _(
                'This template needs a %(expected)s header, but the file "%(name)s" is a %(actual)s.',
                expected=expected, name=filename, actual=actual))
        if expected == 'video' and mimetype not in VIDEO_MIMES:
            raise QualidMediaError('MEDIA_UNSUPPORTED', _('WhatsApp videos must be MP4 or 3GP (got %s).', mimetype))

        limit = MEDIA_LIMIT_MB.get(expected, 16)
        if len(content) > limit * 1024 * 1024:
            raise QualidMediaError('MEDIA_TOO_LARGE', _(
                'The file is %(size).1f MB — WhatsApp allows up to %(limit)s MB for %(type)s headers.',
                size=len(content) / 1048576.0, limit=limit, type=expected))

        status, data = self.env['qualid.api']._qualid_upload(
            filename, content, mimetype, expected_type=expected,
            odoo_model=record._name, odoo_id=record.id,
        )
        if status != 201 or not data.get('success') or not data.get('url'):
            raise QualidMediaError(data.get('error_code') or 'MEDIA_UPLOAD_FAILED',
                                   data.get('message') or _('Could not upload the file to Quali-D.'))
        return data['url'], data.get('filename') or filename

    # ------------------------------------------------------------------
    @api.model
    def _qualid_render_report(self, report, record):
        report = report.sudo().exists()
        if not report:
            raise QualidMediaError('MEDIA_NO_REPORT', _('The selected PDF report no longer exists.'))
        if report.model != record._name:
            raise QualidMediaError('MEDIA_NO_REPORT', _(
                'The report "%(report)s" is for %(model)s, not for this record.', report=report.name, model=report.model))
        try:
            content, _fmt = self.env['ir.actions.report'].sudo()._render_qweb_pdf(report.id, res_ids=[record.id])
        except Exception as e:  # noqa: BLE001
            _logger.exception('Quali-D: rendering report %s for %s,%s failed', report.id, record._name, record.id)
            raise QualidMediaError('MEDIA_REPORT_FAILED', _('Odoo could not generate the PDF: %s', e)) from e

        name = False
        if report.print_report_name:
            try:
                name = safe_eval(report.print_report_name, {'object': record, 'time': time})
            except Exception:  # noqa: BLE001 — fall back to the record name
                name = False
        return content, safe_filename(name or record.display_name or report.name, 'pdf'), 'application/pdf'

    @api.model
    def _qualid_find_attachment(self, record, expected, name_filter):
        domain = [('res_model', '=', record._name), ('res_id', '=', record.id), ('type', '=', 'binary')]
        if name_filter:
            domain.append(('name', 'ilike', name_filter))
        if expected == 'image':
            domain.append(('mimetype', 'like', 'image/'))
        elif expected == 'video':
            domain.append(('mimetype', 'like', 'video/'))
        else:
            domain += [('mimetype', 'not like', 'image/'), ('mimetype', 'not like', 'video/')]
        att = self.env['ir.attachment'].sudo().search(domain, order='create_date desc, id desc', limit=1)
        if not att:
            raise QualidMediaError('MEDIA_NO_ATTACHMENT', _(
                'No %(type)s attachment%(flt)s found on this record.',
                type=expected, flt=(_(' named like "%s"', name_filter) if name_filter else '')))
        content = att.raw or b''
        if not content:
            raise QualidMediaError('MEDIA_EMPTY', _('The attachment "%s" is empty.', att.name))
        mimetype = att.mimetype or guess_mimetype(content)
        return content, att.name or 'file', mimetype

    @api.model
    def _qualid_read_image_field(self, record, field_name):
        if not field_name or field_name not in record._fields:
            raise QualidMediaError('MEDIA_NO_FIELD', _('The image field "%s" does not exist on this record.', field_name))
        value = record[field_name]
        if not value:
            raise QualidMediaError('MEDIA_NO_IMAGE', _('This record has no image in "%s".',
                                                       record._fields[field_name].string))
        content = base64.b64decode(value)
        return content, '%s_%s' % (record._name.replace('.', '_'), record.id), guess_mimetype(content)

    @api.model
    def _qualid_prepare_image(self, content, filename, mimetype):
        """WhatsApp image headers: JPEG or PNG, max 5 MB. Convert/shrink anything else."""
        if mimetype in IMAGE_MIMES and len(content) <= MEDIA_LIMIT_MB['image'] * 1024 * 1024:
            ext = 'jpg' if mimetype == 'image/jpeg' else 'png'
            return content, safe_filename(filename.rsplit('.', 1)[0], ext), mimetype
        if not (mimetype or '').startswith('image/'):
            return content, filename, mimetype  # caller reports the type mismatch
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(content))
            img.load()
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGBA')
                bg = Image.new('RGB', img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[-1])
                img = bg
            else:
                img = img.convert('RGB')
            img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
            out = io.BytesIO()
            img.save(out, format='JPEG', quality=85, optimize=True)
            data = out.getvalue()
        except Exception as e:  # noqa: BLE001
            raise QualidMediaError('MEDIA_IMAGE_CONVERT', _('Could not convert the image to JPEG: %s', e)) from e
        return data, safe_filename(filename.rsplit('.', 1)[0], 'jpg'), 'image/jpeg'
