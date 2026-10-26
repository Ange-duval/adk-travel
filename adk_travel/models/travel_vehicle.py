# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class TravelVehicle(models.Model):
    _name = 'adk.travel.vehicle'
    _description = 'Véhicule de la flotte'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'adk.travel.agency.mixin']
    _order = 'name asc'

    name = fields.Char(string="Nom / Désignation", required=True, tracking=True)
    matricule = fields.Char(string="Immatriculation", required=True, tracking=True, copy=False)
    vehicle_type = fields.Many2one('adk.travel.vehicle.type', string="Type de véhicule", required=True, tracking=True)
    capacity = fields.Integer(string="Nombre de places", required=True, default=30, tracking=True)
    brand = fields.Char(string="Marque")
    model = fields.Char(string="Modèle")
    year = fields.Char(string="Année")
    image = fields.Image(string="Photo", max_width=1024, max_height=1024)
    driver_id = fields.Many2one('adk.travel.employee', string="Chauffeur assigné",
                                 domain="[('function', '=', 'chauffeur'), ('agency_id', '=', agency_id)]", tracking=True)
    state = fields.Selection([
        ('available', "Disponible"),
        ('en_route', "En route"),
        ('panne', "En panne"),
        ('maintenance', "En maintenance"),
    ], string="Statut", default='available', required=True, tracking=True)
    active = fields.Boolean(default=True)
    notes = fields.Text(string="Observations")

    seat_ids = fields.One2many('adk.travel.vehicle.seat', 'vehicle_id', string="Plan de places")
    seat_count = fields.Integer(string="Sièges générés", compute="_compute_seat_count")
    trip_ids = fields.One2many('adk.travel.trip', 'vehicle_id', string="Voyages")
    trip_count = fields.Integer(string="Nb Voyages", compute="_compute_trip_count")

    @api.depends('seat_ids')
    def _compute_seat_count(self):
        for rec in self:
            rec.seat_count = len(rec.seat_ids)

    @api.depends('trip_ids')
    def _compute_trip_count(self):
        for rec in self:
            rec.trip_count = len(rec.trip_ids)

    _sql_constraints = [
        ('matricule_unique', 'UNIQUE(matricule)', 'Cette immatriculation existe déjà.'),
        ('capacity_positive', 'CHECK(capacity > 0)', 'La capacité doit être supérieure à 0.'),
    ]

    def action_generate_seats(self):
        """Génère automatiquement le plan de places selon la capacité du véhicule."""
        self.ensure_one()
        self.seat_ids.unlink()
        vals = []
        for i in range(1, self.capacity + 1):
            vals.append({
                'vehicle_id': self.id,
                'seat_number': str(i).zfill(2),
                'sequence': i,
            })
        self.env['adk.travel.vehicle.seat'].create(vals)
        return True

    def action_set_available(self):
        self.write({'state': 'available'})

    def action_set_en_route(self):
        self.write({'state': 'en_route'})

    def action_set_panne(self):
        self.write({'state': 'panne'})

    def action_view_trips(self):
        self.ensure_one()
        return {
            'name': "Voyages du véhicule",
            'type': 'ir.actions.act_window',
            'res_model': 'adk.travel.trip',
            'view_mode': 'list,calendar,form',
            'domain': [('vehicle_id', '=', self.id)],
        }

    def action_view_seats(self):
        self.ensure_one()
        return {
            'name': "Plan de places",
            'type': 'ir.actions.act_window',
            'res_model': 'adk.travel.vehicle.seat',
            'view_mode': 'list,form',
            'domain': [('vehicle_id', '=', self.id)],
            'context': {'default_vehicle_id': self.id},
        }


class TravelVehicleSeat(models.Model):
    _name = 'adk.travel.vehicle.seat'
    _description = 'Siège du véhicule'
    _rec_name = 'seat_number'
    _order = 'sequence asc'

    vehicle_id = fields.Many2one('adk.travel.vehicle', string="Véhicule", required=True, ondelete='cascade')
    seat_number = fields.Char(string="Numéro de siège", required=True)
    sequence = fields.Integer(string="Ordre", default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('seat_vehicle_unique', 'UNIQUE(vehicle_id, seat_number)', 'Ce numéro de siège existe déjà pour ce véhicule.'),
    ]
