# -*- coding: utf-8 -*-
from odoo import models, fields, api


class TravelLine(models.Model):
    _name = 'adk.travel.line'
    _description = 'Ligne / Destination'
    _order = 'name asc'

    name = fields.Char(string="Nom de la ligne", required=True, help="Ex: Douala - Yaoundé")
    origin = fields.Char(string="Départ", required=True)
    destination = fields.Char(string="Arrivée", required=True)
    distance_km = fields.Float(string="Distance (km)")
    duration_hours = fields.Float(string="Durée estimée (h)")
    active = fields.Boolean(default=True)
    trip_ids = fields.One2many('adk.travel.trip', 'line_id', string="Voyages")
    trip_count = fields.Integer(string="Nb Voyages", compute="_compute_trip_count")

    @api.depends('trip_ids')
    def _compute_trip_count(self):
        for rec in self:
            rec.trip_count = len(rec.trip_ids)

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Cette ligne existe déjà.'),
    ]

    def action_view_trips(self):
        self.ensure_one()
        return {
            'name': "Voyages de la ligne",
            'type': 'ir.actions.act_window',
            'res_model': 'adk.travel.trip',
            'view_mode': 'list,calendar,form',
            'domain': [('line_id', '=', self.id)],
        }


class TravelClass(models.Model):
    _name = 'adk.travel.class'
    _description = 'Gamme / Classe de voyage'
    _order = 'sequence asc'

    name = fields.Char(string="Classe", required=True, help="Ex: VIP, Classe Éco")
    code = fields.Char(string="Code", required=True)
    sequence = fields.Integer(string="Ordre", default=10)
    color = fields.Integer(string="Couleur")
    base_price = fields.Float(string="Tarif de base", required=True)
    baggage_free_kg = fields.Float(string="Poids bagage gratuit (kg)", default=20.0)
    baggage_price_per_kg = fields.Float(string="Prix supplément bagage (par kg)", default=500.0)
    baggage_price_per_extra_item = fields.Float(string="Prix par bagage supplémentaire (unité)", default=1000.0)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Ce code de classe existe déjà.'),
    ]


class TravelVehicleType(models.Model):
    _name = 'adk.travel.vehicle.type'
    _description = 'Type de véhicule'
    _order = 'name asc'

    name = fields.Char(string="Type de véhicule", required=True, help="Ex: Gros Car, Bus, Voiture")
    code = fields.Char(string="Code")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Ce type de véhicule existe déjà.'),
    ]


class TravelPaymentMethod(models.Model):
    _name = 'adk.travel.payment.method'
    _description = 'Mode de paiement'
    _order = 'name asc'

    name = fields.Char(string="Mode de paiement", required=True)
    journal_id = fields.Many2one(
        'account.journal', string="Journal d'encaissement",
        domain="[('type', 'in', ('cash', 'bank'))]",
        help="Journal Odoo (caisse, banque, mobile money…) dans lequel le paiement est enregistré "
             "lorsqu'une vente payée avec ce mode est confirmée. Vide = journal d'encaissement par défaut de l'agence.")
    active = fields.Boolean(default=True)
