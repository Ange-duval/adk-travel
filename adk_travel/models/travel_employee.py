# -*- coding: utf-8 -*-
from odoo import models, fields, api


class TravelEmployee(models.Model):
    _name = 'adk.travel.employee'
    _description = "Employé de l'agence"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'adk.travel.agency.mixin']
    _order = 'name asc'

    name = fields.Char(string="Nom complet", required=True, tracking=True)
    matricule = fields.Char(string="Matricule", copy=False, tracking=True)
    function = fields.Selection([
        ('chef_agence', "Chef d'agence"),
        ('guichetiere', "Guichetière / Guichetier"),
        ('chauffeur', "Chauffeur"),
        ('admin', "Administrateur"),
        ('autre', "Autre"),
    ], string="Fonction", required=True, default='guichetiere', tracking=True)
    phone = fields.Char(string="Téléphone")
    email = fields.Char(string="Email")
    hire_date = fields.Date(string="Date d'embauche")
    contract_ref = fields.Char(string="Référence contrat")
    photo = fields.Image(string="Photo", max_width=512, max_height=512)
    user_id = fields.Many2one('res.users', string="Utilisateur lié")
    active = fields.Boolean(default=True)
    notes = fields.Text(string="Observations")

    # Chauffeur
    license_number = fields.Char(string="Numéro de permis")
    license_expiry = fields.Date(string="Expiration du permis")
    vehicle_ids = fields.One2many('adk.travel.vehicle', 'driver_id', string="Véhicules assignés")
    trip_ids = fields.One2many('adk.travel.trip', 'driver_id', string="Voyages effectués")
    trip_count = fields.Integer(string="Nb Voyages", compute="_compute_trip_count")

    # Guichetière / vente
    booking_ids = fields.One2many('adk.travel.booking', 'guichetier_id', string="Ventes réalisées")
    booking_count = fields.Integer(string="Nb Ventes", compute="_compute_booking_count")
    sales_total = fields.Monetary(string="Total des ventes", compute="_compute_booking_count", currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    agency_id = fields.Many2one(tracking=True)

    @api.depends('trip_ids')
    def _compute_trip_count(self):
        for rec in self:
            rec.trip_count = len(rec.trip_ids)

    @api.depends('booking_ids', 'booking_ids.amount_total', 'booking_ids.state')
    def _compute_booking_count(self):
        for rec in self:
            valid = rec.booking_ids.filtered(lambda b: b.state == 'confirmed')
            rec.booking_count = len(valid)
            rec.sales_total = sum(valid.mapped('amount_total'))

    _sql_constraints = [
        ('matricule_unique', 'UNIQUE(matricule)', 'Ce matricule existe déjà.'),
    ]

    def action_view_trips(self):
        self.ensure_one()
        return {
            'name': "Voyages effectués",
            'type': 'ir.actions.act_window',
            'res_model': 'adk.travel.trip',
            'view_mode': 'list,calendar,form',
            'domain': [('driver_id', '=', self.id)],
        }

    def action_view_bookings(self):
        self.ensure_one()
        return {
            'name': "Ventes réalisées",
            'type': 'ir.actions.act_window',
            'res_model': 'adk.travel.booking',
            'view_mode': 'list,form',
            'domain': [('guichetier_id', '=', self.id)],
        }
