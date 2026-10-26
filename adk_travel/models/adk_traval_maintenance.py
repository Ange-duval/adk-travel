# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class TravalMaintenance(models.Model):
    _name = 'adk.traval.maintenance'
    _description = 'Maintenance / Panne Véhicule'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc'

    name = fields.Char(string="Référence", required=True, copy=False, readonly=True, default=lambda self: _('Nouveau'))
    vehicle_id = fields.Many2one('adk.travel.vehicle', string="Véhicule", required=True, tracking=True)
    agency_id = fields.Many2one(related='vehicle_id.agency_id', string="Agence", store=True, index=True)
    request_date = fields.Datetime(string="Date de déclaration", default=fields.Datetime.now, required=True, tracking=True)
    maintenance_type = fields.Selection([
        ('panne', "Panne"),
        ('entretien', "Entretien préventif"),
        ('reparation', "Réparation"),
        ('revision', "Révision périodique"),
    ], string="Type d'intervention", default='panne', required=True, tracking=True)
    issue_description = fields.Text(string="Description du problème", required=True)
    technician = fields.Char(string="Technicien / Garage")
    date_start = fields.Datetime(string="Début intervention")
    date_end = fields.Datetime(string="Fin intervention")
    cost = fields.Monetary(string="Coût de la maintenance", currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    state = fields.Selection([
        ('draft', "Déclarée"),
        ('in_progress', "En cours"),
        ('done', "Terminée"),
        ('cancelled', "Annulée"),
    ], string="Statut", default='draft', required=True, tracking=True)
    notes = fields.Text(string="Observations")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nouveau')) == _('Nouveau'):
                vals['name'] = self.env['ir.sequence'].next_by_code('adk.traval.maintenance') or _('Nouveau')
        return super().create(vals_list)

    def action_start(self):
        self.write({'state': 'in_progress', 'date_start': fields.Datetime.now()})
        for rec in self:
            rec.vehicle_id.write({'state': 'maintenance'})

    def action_report_panne(self):
        for rec in self:
            rec.vehicle_id.write({'state': 'panne'})

    def action_done(self):
        self.write({'state': 'done', 'date_end': fields.Datetime.now()})
        for rec in self:
            rec.vehicle_id.action_set_available()

    def action_cancel(self):
        self.write({'state': 'cancelled'})
