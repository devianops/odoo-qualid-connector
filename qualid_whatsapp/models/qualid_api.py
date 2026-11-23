# -*- coding: utf-8 -*-
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date, format_datetime

_logger = logging.getLogger(__name__)

DEFAULT_API_URL = 'https://api.quali-d.com'
REQUEST_TIMEOUT = 30
PARAM_URL = 'qualid_whatsapp.api_url'
PARAM_TOKEN = 'qualid_whatsapp.api_token'

# Fields tried, in order, when no phone path is configured
AUTO_PHONE_PATHS = (
    'mobile', 'phone_sanitized', 'phone', 'partner_mobile', 'partner_phone',
    'partner_id.mobile', 'partner_id.phone_sanitized', 'partner_id.phone',
)


class QualidApi(models.AbstractModel):
    _name = 'qualid.api'
    _description = 'Quali-D API Client'

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------
    @api.model
    def _qualid_get_config(self):
        icp = self.env['ir.config_parameter'].sudo()
        url = (icp.get_param(PARAM_URL) or DEFAULT_API_URL).strip().rstrip('/')
        token = (icp.get_param(PARAM_TOKEN) or '').strip()
        return url, token

    @api.model
    def _qualid_request(self, method, path, payload=None, params=None, raise_on_error=True):
        """Call the Quali-D API. Returns (http_status, data_dict).

        http_status is 0 on network errors. Never logs the token.
        """
        url, token = self._qualid_get_config()
        if not token:
            if raise_on_error:
                raise UserError(_('Quali-D token is not configured. Go to Settings → Quali-D WhatsApp.'))
            return 0, {'success': False, 'message': _('Quali-D token is not configured.'), 'error_code': 'NO_TOKEN'}
        if not (url.startswith('https://') or url.startswith('http://localhost') or url.startswith('http://127.0.0.1')):
            msg = _('The Quali-D API URL must use https://')
            if raise_on_error:
                raise UserError(msg)
            return 0, {'success': False, 'message': msg, 'error_code': 'INSECURE_URL'}

        headers = {
            'Authorization': 'Bearer %s' % token,
            'Accept': 'application/json',
            'User-Agent': 'Odoo-QualiD-WhatsApp/1.0',
        }
        try:
            resp = requests.request(
                method, url + path, json=payload, params=params,
                headers=headers, timeout=REQUEST_TIMEOUT,
            )
            status = resp.status_code
            try:
                data = resp.json()
                if not isinstance(data, dict):
                    raise ValueError
            except ValueError:
                data = {
                    'success': False,
                    'message': _('Unexpected response from Quali-D (HTTP %s).', status),
                    'error_code': 'BAD_RESPONSE',
                }
        except requests.RequestException as e:
            _logger.warning('Quali-D request %s %s failed: %s', method, path, e.__class__.__name__)
            status = 0
            data = {
                'success': False,
                'message': _('Could not reach Quali-D (%s).', e.__class__.__name__),
                'error_code': 'NETWORK_ERROR',
            }

        if raise_on_error and not data.get('success'):
            raise UserError(data.get('message') or _('Quali-D request failed (HTTP %s).', status))
        return status, data

    # ------------------------------------------------------------------
    # Record value resolution (used by server actions and the wizard)
    # ------------------------------------------------------------------
    @api.model
    def _qualid_resolve_path(self, record, path):
        """Resolve a dotted field path on a record and return a display string.

        'partner_id.name' -> 'Azure Interior'; many2many/one2many -> comma list;
        dates are formatted in the user's language; selections show their label.
        Unknown fields return ''.
        """
        path = (path or '').strip()
        if not path or not record:
            return ''
        value = record[:1]
        field = None
        for part in path.split('.'):
            if not isinstance(value, models.BaseModel):
                return ''
            if part not in value._fields:
                return ''
            field = value._fields[part]
            value = value[:1][part] if len(value) else False
        return self._qualid_format_value(value, field)

    @api.model
    def _qualid_format_value(self, value, field=None):
        if value is False or value is None:
            return ''
        if isinstance(value, models.BaseModel):
            return ', '.join(n for n in value.mapped('display_name') if n)
        ftype = field.type if field is not None else None
        if ftype == 'selection':
            try:
                labels = dict(field._description_selection(self.env))
                return str(labels.get(value, value))
            except Exception:  # noqa: BLE001 — selection labels are best-effort
                return str(value)
        if ftype == 'datetime':
            return format_datetime(self.env, value)
        if ftype == 'date':
            return format_date(self.env, value)
        if ftype in ('float', 'monetary'):
            return '%.2f' % value
        if value is True:
            return _('Yes')
        if ftype == 'html':
            from odoo.tools import html2plaintext
            return html2plaintext(value or '').strip()
        return str(value).strip()

    @api.model
    def _qualid_resolve_phone(self, record, path=None):
        if path:
            return self._qualid_resolve_path(record, path)
        for candidate in AUTO_PHONE_PATHS:
            val = self._qualid_resolve_path(record, candidate)
            if val:
                return val
        return ''

    @api.model
    def _qualid_now(self):
        return fields.Datetime.now()
