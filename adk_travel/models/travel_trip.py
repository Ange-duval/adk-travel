# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class TravelTrip(models.Model):
    _name = 'adk.travel.trip'
    _description = 'Voyage / Départ programmé'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'adk.travel.agency.mixin']
    _order = 'departure_datetime desc'

    name = fields.Char(string="Référence", required=True, copy=False, readonly=True, default=lambda self: _('Nouveau'))
    line_id = fields.Many2one('adk.travel.line', string="Ligne / Destination", required=True, tracking=True)
    vehicle_id = fields.Many2one('adk.travel.vehicle', string="Véhicule", required=True, tracking=True,
                                  domain="[('agency_id', '=', agency_id)]")
    driver_id = fields.Many2one('adk.travel.employee', string="Chauffeur", tracking=True,
                                 domain="[('function', '=', 'chauffeur'), ('agency_id', '=', agency_id)]")
    departure_datetime = fields.Datetime(string="Date et heure de départ", required=True, tracking=True)
    capacity = fields.Integer(string="Capacité", related='vehicle_id.capacity', store=True)
    booking_line_ids = fields.One2many('adk.travel.booking.line', 'trip_id', string="Passagers")
    booked_seats = fields.Integer(string="Places réservées", compute="_compute_seats")
    available_seats = fields.Integer(string="Places disponibles", compute="_compute_seats")
    fill_rate = fields.Float(string="Taux de remplissage (%)", compute="_compute_seats")
    state = fields.Selection([
        ('draft', "Planifié"),
        ('confirmed', "Confirmé"),
        ('in_progress', "En route"),
        ('done', "Terminé"),
        ('cancelled', "Annulé"),
    ], string="Statut", default='draft', required=True, tracking=True)
    revenue_total = fields.Monetary(string="Recette totale", compute="_compute_revenue", currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    notes = fields.Text(string="Observations")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nouveau')) == _('Nouveau'):
                vals['name'] = self.env['ir.sequence'].next_by_code('adk.travel.trip') or _('Nouveau')
        return super().create(vals_list)

    @api.depends('booking_line_ids', 'booking_line_ids.state', 'capacity')
    def _compute_seats(self):
        for rec in self:
            valid_lines = rec.booking_line_ids.filtered(lambda l: l.state != 'cancelled')
            rec.booked_seats = len(valid_lines)
            rec.available_seats = max(rec.capacity - rec.booked_seats, 0)
            rec.fill_rate = (rec.booked_seats / rec.capacity) if rec.capacity else 0.0  # fraction : le widget « percentage » multiplie par 100

    @api.depends('booking_line_ids', 'booking_line_ids.amount_total', 'booking_line_ids.state')
    def _compute_revenue(self):
        for rec in self:
            valid_lines = rec.booking_line_ids.filtered(lambda l: l.state != 'cancelled')
            rec.revenue_total = sum(valid_lines.mapped('amount_total'))

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_start(self):
        self.write({'state': 'in_progress'})
        self.vehicle_id.action_set_en_route()

    def action_done(self):
        self.write({'state': 'done'})
        self.vehicle_id.action_set_available()

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def check_seats_available(self, requested, already_counted=0):
        """Vérifie qu'il reste assez de places. `already_counted` = places de la
        vente en cours déjà comptées dans `booked_seats` (lignes non annulées)."""
        self.ensure_one()
        free = self.capacity - (self.booked_seats - already_counted)
        if requested > free:
            raise UserError(_(
                "Il ne reste que %(av)s place(s) disponible(s) sur ce voyage (%(req)s demandée(s)).",
                av=max(free, 0), req=requested))

    @api.onchange('agency_id')
    def _onchange_agency_id(self):
        if self.vehicle_id and self.vehicle_id.agency_id != self.agency_id:
            self.vehicle_id = False
        if self.driver_id and self.driver_id.agency_id != self.agency_id:
            self.driver_id = False

    @api.onchange('vehicle_id')
    def _onchange_vehicle_id(self):
        if self.vehicle_id.driver_id and not self.driver_id:
            self.driver_id = self.vehicle_id.driver_id

    @api.constrains('agency_id', 'vehicle_id', 'driver_id')
    def _check_agency_consistency(self):
        for rec in self:
            if rec.vehicle_id and rec.vehicle_id.agency_id != rec.agency_id:
                raise ValidationError(_("Le véhicule choisi n'appartient pas à l'agence du voyage."))
            if rec.driver_id and rec.driver_id.agency_id != rec.agency_id:
                raise ValidationError(_("Le chauffeur choisi n'appartient pas à l'agence du voyage."))
