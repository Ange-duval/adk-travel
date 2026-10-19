# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import format_datetime


class TravelBooking(models.Model):
    _name = 'adk.travel.booking'
    _description = "Vente au guichet / Réservation"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'adk.travel.agency.mixin']
    _order = 'booking_date desc'

    name = fields.Char(string="Référence vente", required=True, copy=False, readonly=True, default=lambda self: _('Nouveau'))
    booking_date = fields.Datetime(string="Date de la vente", default=fields.Datetime.now, required=True, tracking=True)
    client_name = fields.Char(string="Nom du client", required=True, tracking=True)
    client_phone = fields.Char(string="Téléphone du client")
    partner_id = fields.Many2one(
        'res.partner', string="Client (fiche)", tracking=True,
        help="Fiche client utilisée pour la facture. Si elle est vide, une fiche est créée automatiquement "
             "à partir du nom et du téléphone saisis, au moment de la confirmation.")
    company_id = fields.Many2one(related='agency_id.company_id', string="Société", store=True, index=True)
    trip_id = fields.Many2one('adk.travel.trip', string="Voyage", required=True, tracking=True,
                              domain="[('agency_id', '=', agency_id)]")
    line_id = fields.Many2one(related='trip_id.line_id', string="Ligne", store=True)
    vehicle_id = fields.Many2one(related='trip_id.vehicle_id', string="Véhicule", store=True)
    guichetier_id = fields.Many2one('adk.travel.employee', string="Guichetière / Vendeur",
                                    default=lambda self: self._default_guichetier(),
                                    domain="[('agency_id', '=', agency_id)]")
    payment_method_id = fields.Many2one('adk.travel.payment.method', string="Mode de paiement")
    state = fields.Selection([
        ('draft', "Brouillon"),
        ('confirmed', "Confirmé"),
        ('cancelled', "Annulé"),
    ], string="Statut", default='draft', required=True, tracking=True)
    passenger_line_ids = fields.One2many('adk.travel.booking.line', 'booking_id', string="Passagers", copy=True)
    passenger_count = fields.Integer(string="Nb Passagers", compute="_compute_totals", store=True)
    amount_trip = fields.Monetary(string="Montant trajets", compute="_compute_totals", store=True, currency_field='currency_id')
    amount_baggage = fields.Monetary(string="Montant bagages", compute="_compute_totals", store=True, currency_field='currency_id')
    amount_total = fields.Monetary(string="Montant total", compute="_compute_totals", store=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='agency_id.currency_id', string="Devise", store=True)
    notes = fields.Text(string="Observations")

    # --- Facturation (Comptabilité native Odoo)
    invoice_id = fields.Many2one('account.move', string="Facture", readonly=True, copy=False, tracking=True)
    invoice_name = fields.Char(related='invoice_id.name', string="N° de facture", store=True)
    payment_status = fields.Selection(
        related='invoice_id.payment_state', string="Statut de paiement", store=True)
    invoice_total = fields.Monetary(related='invoice_id.amount_total', string="Total facturé",
                                    store=True, currency_field='currency_id')
    invoice_residual = fields.Monetary(related='invoice_id.amount_residual', string="Reste à payer",
                                       store=True, currency_field='currency_id')
    amount_paid = fields.Monetary(string="Montant encaissé", compute='_compute_amount_paid',
                                  store=True, currency_field='currency_id')

    def _default_guichetier(self):
        emp = self.env['adk.travel.employee'].search([('user_id', '=', self.env.uid)], limit=1)
        return emp.id if emp else False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nouveau')) == _('Nouveau'):
                vals['name'] = self.env['ir.sequence'].next_by_code('adk.travel.booking') or _('Nouveau')
        return super().create(vals_list)

    def unlink(self):
        if self.filtered('invoice_id'):
            raise UserError(_("Une vente facturée ne peut pas être supprimée. Annulez-la à la place."))
        return super().unlink()

    @api.depends('passenger_line_ids', 'passenger_line_ids.amount_total', 'passenger_line_ids.price_unit',
                 'passenger_line_ids.baggage_fee', 'passenger_line_ids.state')
    def _compute_totals(self):
        for rec in self:
            valid = rec.passenger_line_ids.filtered(lambda l: l.state != 'cancelled')
            rec.passenger_count = len(valid)
            rec.amount_trip = sum(valid.mapped('price_unit'))
            rec.amount_baggage = sum(valid.mapped('baggage_fee'))
            rec.amount_total = rec.amount_trip + rec.amount_baggage

    @api.depends('invoice_total', 'invoice_residual', 'invoice_id.state')
    def _compute_amount_paid(self):
        for rec in self:
            if rec.invoice_id and rec.invoice_id.state == 'posted':
                rec.amount_paid = rec.invoice_total - rec.invoice_residual
            else:
                rec.amount_paid = 0.0

    # ------------------------------------------------------------------
    # Contraintes / onchange
    # ------------------------------------------------------------------
    @api.constrains('agency_id', 'trip_id')
    def _check_trip_agency(self):
        for rec in self:
            if rec.trip_id and rec.trip_id.agency_id != rec.agency_id:
                raise ValidationError(_("Le voyage choisi n'appartient pas à l'agence de la vente."))

    @api.onchange('agency_id')
    def _onchange_agency_id(self):
        if self.trip_id and self.trip_id.agency_id != self.agency_id:
            self.trip_id = False
        if self.guichetier_id and self.guichetier_id.agency_id != self.agency_id:
            self.guichetier_id = False

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            self.client_name = self.partner_id.name
            self.client_phone = self.partner_id.phone or self.client_phone

    # ------------------------------------------------------------------
    # Confirmation : facture + paiement
    # ------------------------------------------------------------------
    def action_confirm(self):
        """Confirme la vente : réserve les places, génère les billets,
        crée et valide la facture client, puis enregistre le paiement."""
        for rec in self.filtered(lambda b: b.state == 'draft'):
            lines = rec.passenger_line_ids.filtered(lambda l: l.state != 'cancelled')
            if not lines:
                raise UserError(_("Ajoutez au moins un passager avant de confirmer la vente."))
            if not rec.amount_total:
                raise UserError(_("Le montant de la vente est nul : vérifiez les tarifs des passagers."))
            rec.trip_id.check_seats_available(len(lines), already_counted=len(lines))
            journal = False
            if rec.agency_id.auto_register_payment:
                if not rec.payment_method_id:
                    raise UserError(_("Choisissez le mode de paiement pour encaisser la vente."))
                journal = rec._get_payment_journal()

            invoice = rec._create_invoice()
            rec.write({'state': 'confirmed', 'invoice_id': invoice.id})
            lines.write({'state': 'confirmed'})
            if journal:
                rec._register_payment(invoice, journal)
        return True

    # Ancien nom de l'action, conservé pour compatibilité.
    action_confirm_payment = action_confirm

    def _get_or_create_partner(self):
        self.ensure_one()
        if self.partner_id:
            return self.partner_id
        Partner = self.env['res.partner'].sudo()
        domain = [('name', '=', self.client_name)]
        if self.client_phone:
            domain.append(('phone', '=', self.client_phone))
        partner = Partner.search(domain, limit=1)
        if not partner:
            partner = Partner.create({'name': self.client_name, 'phone': self.client_phone or False})
        self.partner_id = partner
        return partner

    def _get_product(self, xmlid):
        return self.env.ref(xmlid, raise_if_not_found=False)

    def _prepare_invoice_lines(self):
        self.ensure_one()
        ticket_product = self._get_product('adk_travel.product_adk_travel_ticket')
        baggage_product = self._get_product('adk_travel.product_adk_travel_baggage')
        trip = self.trip_id
        departure = format_datetime(self.env, trip.departure_datetime)
        commands = []
        for line in self.passenger_line_ids.filtered(lambda l: l.state != 'cancelled'):
            label = _("Billet %(ref)s — %(passenger)s — %(route)s — départ %(date)s — classe %(klass)s") % {
                'ref': line.ticket_ref, 'passenger': line.passenger_name,
                'route': trip.line_id.name, 'date': departure, 'klass': line.travel_class_id.name,
            }
            if line.seat_id:
                label += _(" — siège %s") % line.seat_id.seat_number
            commands.append((0, 0, {
                'product_id': ticket_product.id if ticket_product else False,
                'name': label,
                'quantity': 1.0,
                'price_unit': line.price_unit,
            }))
            if line.baggage_fee:
                commands.append((0, 0, {
                    'product_id': baggage_product.id if baggage_product else False,
                    'name': _("Supplément bagages — billet %(ref)s (%(count)s pièce(s), %(weight)s kg)") % {
                        'ref': line.ticket_ref, 'count': line.baggage_count, 'weight': line.baggage_weight},
                    'quantity': 1.0,
                    'price_unit': line.baggage_fee,
                }))
        return commands

    def _create_invoice(self):
        """Crée et valide la facture client de la vente. Exécuté avec les droits
        système : la guichetière n'a pas besoin de droits comptables."""
        self.ensure_one()
        partner = self._get_or_create_partner()
        agency = self.agency_id
        vals = {
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'company_id': agency.company_id.id,
            'invoice_origin': self.name,
            'invoice_date': fields.Date.context_today(self),
            'invoice_line_ids': self._prepare_invoice_lines(),
        }
        if agency.sale_journal_id:
            vals['journal_id'] = agency.sale_journal_id.id
        Move = self.env['account.move'].sudo().with_company(agency.company_id)
        invoice = Move.create(vals)
        invoice.action_post()
        invoice.message_post(body=_("Facture générée depuis la vente %(sale)s — agence %(agency)s.") % {
            'sale': self.name, 'agency': agency.name})
        return invoice

    def _get_payment_journal(self):
        self.ensure_one()
        company = self.agency_id.company_id
        journal = self.payment_method_id.journal_id
        if not journal or journal.company_id != company:
            journal = self.agency_id.default_payment_journal_id
        if not journal:
            Journal = self.env['account.journal'].sudo()
            for jtype in ('cash', 'bank'):
                journal = Journal.search([('type', '=', jtype), ('company_id', '=', company.id)], limit=1)
                if journal:
                    break
        if not journal:
            raise UserError(_(
                "Aucun journal d'encaissement (caisse ou banque) n'est disponible pour la société %s. "
                "Liez un journal au mode de paiement « %s » ou à l'agence.") % (company.name, self.payment_method_id.name))
        return journal

    def _register_payment(self, invoice, journal):
        self.ensure_one()
        Register = self.env['account.payment.register'].sudo().with_company(invoice.company_id).with_context(
            active_model='account.move', active_ids=invoice.ids)
        wizard = Register.create({
            'journal_id': journal.id,
            'payment_date': fields.Date.context_today(self),
            'communication': self.name,
        })
        wizard._create_payments()

    # ------------------------------------------------------------------
    # Annulation
    # ------------------------------------------------------------------
    def action_cancel(self):
        for rec in self:
            invoice = rec.invoice_id.sudo()
            if invoice and invoice.state == 'posted':
                if invoice.payment_state in ('paid', 'in_payment', 'partial'):
                    raise UserError(_(
                        "La facture %s est déjà payée (ou en partie). Pour annuler cette vente, "
                        "créez d'abord un avoir depuis la Facturation, puis annulez la vente.") % invoice.name)
                if invoice.payment_state != 'reversed':
                    invoice.button_draft()
                    invoice.button_cancel()
            elif invoice and invoice.state == 'draft':
                invoice.button_cancel()
            rec.write({'state': 'cancelled'})
            rec.passenger_line_ids.write({'state': 'cancelled'})

    def action_view_invoice(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Facture"),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.invoice_id.id,
        }

    def action_print_tickets(self):
        self.ensure_one()
        return self.env.ref('adk_travel.action_report_travel_ticket').report_action(
            self.passenger_line_ids.filtered(lambda l: l.state == 'confirmed'))

    def action_recompute_prices(self):
        """Corrige les lignes existantes dont le tarif est resté à 0
        (ex : données créées avant l'ajout du filet de sécurité serveur)."""
        fixed = 0
        for line in self.mapped('passenger_line_ids'):
            if not line.price_unit and line.travel_class_id:
                line.price_unit = line.travel_class_id.base_price
                fixed += 1
        message = _("%s ligne(s) de tarif corrigée(s).") % fixed if fixed else _("Aucun tarif à corriger, tout est déjà en ordre.")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _("Recalcul des tarifs"), 'message': message, 'type': 'success' if fixed else 'info'},
        }


class TravelBookingLine(models.Model):
    _name = 'adk.travel.booking.line'
    _description = 'Passager / Ticket'
    _order = 'id asc'

    booking_id = fields.Many2one('adk.travel.booking', string="Vente", required=True, ondelete='cascade')
    agency_id = fields.Many2one(related='booking_id.agency_id', string="Agence", store=True, index=True)
    trip_id = fields.Many2one('adk.travel.trip', string="Voyage", related='booking_id.trip_id', store=True)
    ticket_ref = fields.Char(string="N° Billet", copy=False, readonly=True, default=lambda self: _('Nouveau'))
    passenger_name = fields.Char(string="Nom du passager", required=True)
    seat_id = fields.Many2one('adk.travel.vehicle.seat', string="Siège",
                               domain="[('vehicle_id', '=', vehicle_id)]")
    vehicle_id = fields.Many2one(related='booking_id.vehicle_id', string="Véhicule")
    travel_class_id = fields.Many2one('adk.travel.class', string="Classe de voyage", required=True)
    price_unit = fields.Monetary(string="Tarif trajet", currency_field='currency_id')
    baggage_count = fields.Integer(string="Nb Bagages", default=1)
    baggage_weight = fields.Float(string="Poids total bagages (kg)", default=20.0)
    baggage_fee = fields.Monetary(string="Supplément bagage", compute="_compute_baggage_fee", store=True, currency_field='currency_id')
    amount_total = fields.Monetary(string="Total passager", compute="_compute_amount_total", store=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='booking_id.currency_id')
    state = fields.Selection([
        ('draft', "Brouillon"),
        ('confirmed', "Confirmé"),
        ('cancelled', "Annulé"),
    ], string="Statut", default='draft')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('ticket_ref', _('Nouveau')) == _('Nouveau'):
                vals['ticket_ref'] = self.env['ir.sequence'].next_by_code('adk.travel.ticket') or _('Nouveau')
            # Filet de sécurité : si le tarif n'a pas été rempli (onchange non
            # déclenché, import, création par API...), on le déduit de la classe.
            if not vals.get('price_unit') and vals.get('travel_class_id'):
                klass = self.env['adk.travel.class'].browse(vals['travel_class_id'])
                vals['price_unit'] = klass.base_price
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        # Même filet de sécurité en modification, si la classe change sans tarif fourni.
        if 'travel_class_id' in vals and 'price_unit' not in vals:
            for rec in self:
                if not rec.price_unit and rec.travel_class_id:
                    rec.price_unit = rec.travel_class_id.base_price
        return res

    @api.constrains('seat_id', 'trip_id', 'state')
    def _check_seat_unique(self):
        for rec in self.filtered(lambda l: l.seat_id and l.trip_id and l.state != 'cancelled'):
            clash = self.search_count([
                ('id', '!=', rec.id), ('trip_id', '=', rec.trip_id.id),
                ('seat_id', '=', rec.seat_id.id), ('state', '!=', 'cancelled'),
            ])
            if clash:
                raise ValidationError(_("Le siège %s est déjà attribué sur ce voyage.") % rec.seat_id.seat_number)

    @api.onchange('travel_class_id')
    def _onchange_travel_class(self):
        if self.travel_class_id:
            self.price_unit = self.travel_class_id.base_price

    @api.depends('baggage_count', 'baggage_weight', 'travel_class_id')
    def _compute_baggage_fee(self):
        for rec in self:
            klass = rec.travel_class_id
            if not klass:
                rec.baggage_fee = 0.0
                continue
            extra_weight = max(rec.baggage_weight - klass.baggage_free_kg, 0.0)
            weight_fee = extra_weight * klass.baggage_price_per_kg
            extra_items = max(rec.baggage_count - 1, 0)
            items_fee = extra_items * klass.baggage_price_per_extra_item
            rec.baggage_fee = weight_fee + items_fee

    @api.depends('price_unit', 'baggage_fee')
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = rec.price_unit + rec.baggage_fee
