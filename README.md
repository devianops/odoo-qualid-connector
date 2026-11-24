# Quali-D WhatsApp — Odoo Connector

Send approved WhatsApp Business templates from Odoo through [Quali-D](https://quali-d.com).

| Odoo edition | How to connect |
|---|---|
| Self-hosted / Odoo.sh | Install the `qualid_whatsapp` module (this repo) |
| Odoo Online (SaaS, v17+) | No install needed. Use Odoo's built-in **Send Webhook Notification** action with the URL generated in Quali-D → Settings → Odoo Connector |

## Features

- **Ready-made automations**: one click sets up a complete rule. There are 12 recipes: invoice confirmed or paid, payment and overdue reminders, quotation sent, order confirmed, delivery done, new lead, opportunity won, new contact, purchase order, and task done.
- **Automation Rules**: a new server action type, *Send WhatsApp (Quali-D)*, that works with any model and any trigger.
- **Variable mapping**: fill template variables from record fields, including dotted relations like `partner_id.name`, or from fixed text.
- **Header files**: image, video and document templates are supported. The file can be a PDF of the record (invoice, quotation, delivery slip…), its latest attachment, an image field, or a link. Files are kept with the Quali-D conversation history.
- **Background queue**: sends go through a queue with automatic retries (1 min, then 5 min). You can choose immediate sending instead.
- **Send only once per record**: protects against duplicate triggers. Every send also carries a stable idempotency key, so a retry never sends twice.
- **Manual send wizard**: on Contacts, for one record or in bulk. For any other model, use *Create Contextual Action* on a server action.
- **Logging**: a chatter note on the record and a full message log.

## Installation (self-hosted / Odoo.sh)

1. Copy `qualid_whatsapp/` into your addons path. On Odoo.sh, add this repo as a submodule.
2. Restart Odoo, update the Apps list and install **Quali-D WhatsApp**.
3. In Quali-D, open **Settings → Odoo Connector** and click **New Token**. Copy the token; it is shown only once.
4. In Odoo, open **Settings → Quali-D WhatsApp**, paste the token and save. Templates are imported automatically, and re-synced every hour.

Recommended: add your Odoo server's public IP to the token's **Allowed IPs** in Quali-D.

## Usage: ready-made automations

1. Open **Settings → Quali-D WhatsApp → Automations** and click **Set up** next to a recipe. Recipes for apps that aren't installed are marked *Install …*.
2. Pick a template. The trigger, the filters (for example, customer invoices only), the PDF and suggested variables are filled in. Change any variable if needed.
3. Click **Create Automation**. The finished rule opens so you can review it.

## Usage: your own automation rule

1. Open **My Automations** (or **Quali-D WhatsApp → Configuration → Automation Rules**) and click **New**.
2. Choose a model (e.g. *Sales Order*) and a trigger (e.g. *State is set to Sales Order*).
3. Add an action of type **Send WhatsApp (Quali-D)**.
4. Pick a template. One row appears per template variable; map each row to a field, e.g. `partner_id.name`, `name`, `amount_total`.
5. Optionally set **Phone Field**. If left empty, the module tries `mobile`, `phone`, `partner_id.mobile` and `partner_id.phone`.

## Changing an automation

Open **My Automations** and click the rule.

- **Apply on** limits which records count. For example, a rule on *State is set to Posted* also matches vendor bills until you add *Type is Customer Invoice*.
- Open the **Send WhatsApp** action to change the template, the variables or the header file.
- Untick **Active** to pause the rule without deleting it.

## Usage: Odoo Online (webhook)

1. In Quali-D, open **Settings → Odoo Connector → Webhook**. Pick a template and map each variable to a field name.
2. Copy the generated URL.
3. In Odoo, create an Automation Rule with the action **Send Webhook Notification**. Paste the URL and, under *Fields*, select the phone field and every field used as a variable.

> The webhook URL contains the token. If it leaks, rotate the token in Quali-D and the old URL stops working immediately.

## API (for developers)

```
POST https://api.quali-d.com/odoo_send_template
Authorization: Bearer odoo_qd_…
Content-Type: application/json

{
  "to": "+201001234567",
  "template": "order_shipped",
  "language": "en",
  "body_params": ["Ahmed", "SO0042"],
  "header_text": null,
  "header_media_url": null, "header_media_type": "image",
  "idempotency_key": "sale.order:42:shipped",
  "odoo_model": "sale.order", "odoo_id": 42
}
```

Other endpoints:

- `GET /odoo/verify`: test connection
- `GET /odoo/templates`: approved templates, each with an `odoo_summary` of its variables

Error responses carry an `error_code`. Common values are `ODOO_TOKEN_INVALID`, `ODOO_TOKEN_REVOKED`, `ODOO_IP_NOT_ALLOWED`, `ODOO_RATE_LIMITED`, `ODOO_INVALID_PHONE`, `PLAN_NOT_ELIGIBLE` and `INSUFFICIENT_CREDIT`.

## Version branches

Use the branch that matches your Odoo version. All five pass the same test suite: install, settings page, ready-made automations, rules firing (including PDF headers), empty-variable protection and the send wizard.

| Branch | Odoo | Notes |
|---|---|---|
| `17.0` | 17.0 | Primary development version |
| `18.0` | 18.0 | Same features. The invoice report is called *Invoice PDF* |
| `19.0` | 19.0 | Same features. Odoo 19 removed `mobile`, so contacts and leads use `phone`. "Before the due date" reminders use the *Before* delay mode |
| `20.0` | 20.0 | Same features. Odoo 20 needs PostgreSQL 16 or newer. Webhooks send image/file fields as `{"content": "<base64>"}`, which Quali-D also accepts |
| `16.0` | 16.0 | Same features. Odoo 16 has no "State is set to" trigger, so recipes use *On Creation & Update* on the State field instead. Choose the action type in the rule's *Action To Do* field |

## License

LGPL-3
