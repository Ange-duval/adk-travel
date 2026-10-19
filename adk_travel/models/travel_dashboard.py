# -*- coding: utf-8 -*-
from datetime import date, timedelta, datetime
from odoo import models, fields, api, _
from .utils import day_bounds_utc


class TravelDashboard(models.TransientModel):
    _name = 'adk.travel.dashboard'
    _description = 'Tableau de Bord Agence de Voyage'

    name = fields.Char(string="Nom", default="Mon Dashboard")
    agency_id = fields.Many2one(
        'adk.travel.agency', string="Agence",
        default=lambda self: self.env['adk.travel.agency']._get_default_agency().id,
        help="Laissez vide pour voir toutes les agences auxquelles vous avez accès.")
    title = fields.Char(string="Titre", compute="_compute_title")

    # ── Flash du jour
    revenue_today = fields.Float(string="Recettes du jour", compute="_compute_stats")
    passengers_today = fields.Integer(string="Passagers actifs (aujourd'hui)", compute="_compute_stats")
    bookings_today = fields.Integer(string="Billets vendus aujourd'hui", compute="_compute_stats")
    trips_in_progress = fields.Integer(string="Bus en route", compute="_compute_stats")

    # ── Flotte
    count_vehicles = fields.Integer(string="Total véhicules", compute="_compute_stats")
    count_vehicles_available = fields.Integer(string="Véhicules disponibles", compute="_compute_stats")
    count_vehicles_en_route = fields.Integer(string="Véhicules en route", compute="_compute_stats")
    count_vehicles_panne = fields.Integer(string="Véhicules en panne", compute="_compute_stats")

    # ── Équipe
    count_employees = fields.Integer(string="Total employés", compute="_compute_stats")
    count_chauffeurs = fields.Integer(string="Chauffeurs", compute="_compute_stats")
    count_guichetieres = fields.Integer(string="Guichetières", compute="_compute_stats")

    # ── Voyages & remplissage
    count_trips_today = fields.Integer(string="Voyages du jour", compute="_compute_stats")
    avg_fill_rate_today = fields.Float(string="Taux de remplissage moyen (%)", compute="_compute_stats")

    # ── Finance mensuelle
    revenue_month = fields.Float(string="Recettes du mois", compute="_compute_stats")
    amount_unpaid = fields.Float(string="Factures à encaisser", compute="_compute_stats")
    count_bookings_month = fields.Integer(string="Ventes du mois", compute="_compute_stats")

    @api.depends('agency_id')
    def _compute_title(self):
        for rec in self:
            rec.title = _("Tableau de bord — %s") % rec.agency_id.name if rec.agency_id else _("Tableau de bord — Toutes les agences")

    @api.depends('agency_id')
    def _compute_stats(self):
        today = fields.Date.context_today(self)
        month_start = today.replace(day=1)
        today_start, today_end = day_bounds_utc(self.env, today)
        month_start_dt, __ = day_bounds_utc(self.env, month_start)

        Booking = self.env['adk.travel.booking']
        BookingLine = self.env['adk.travel.booking.line']
        Vehicle = self.env['adk.travel.vehicle']
        Employee = self.env['adk.travel.employee']
        Trip = self.env['adk.travel.trip']

        for rec in self:
            agency = [('agency_id', '=', rec.agency_id.id)] if rec.agency_id else []
            bookings_today = Booking.search(agency + [
                ('booking_date', '>=', today_start), ('booking_date', '<=', today_end),
                ('state', '=', 'confirmed'),
            ])
            rec.revenue_today = sum(bookings_today.mapped('amount_total'))
            rec.bookings_today = len(bookings_today)
            rec.passengers_today = sum(bookings_today.mapped('passenger_count'))
            rec.trips_in_progress = Trip.search_count(agency + [('state', '=', 'in_progress')])

            rec.count_vehicles = Vehicle.search_count(agency + [('active', '=', True)])
            rec.count_vehicles_available = Vehicle.search_count(agency + [('state', '=', 'available')])
            rec.count_vehicles_en_route = Vehicle.search_count(agency + [('state', '=', 'en_route')])
            rec.count_vehicles_panne = Vehicle.search_count(agency + [('state', 'in', ('panne', 'maintenance'))])

            rec.count_employees = Employee.search_count(agency + [('active', '=', True)])
            rec.count_chauffeurs = Employee.search_count(agency + [('function', '=', 'chauffeur')])
            rec.count_guichetieres = Employee.search_count(agency + [('function', '=', 'guichetiere')])

            trips_today = Trip.search(agency + [
                ('departure_datetime', '>=', today_start), ('departure_datetime', '<=', today_end),
                ('state', '!=', 'cancelled'),
            ])
            rec.count_trips_today = len(trips_today)
            rec.avg_fill_rate_today = (sum(trips_today.mapped('fill_rate')) / len(trips_today)) if trips_today else 0.0

            bookings_month = Booking.search(agency + [
                ('booking_date', '>=', month_start_dt), ('state', '=', 'confirmed'),
            ])
            rec.revenue_month = sum(bookings_month.mapped('amount_total'))
            rec.count_bookings_month = len(bookings_month)
            # Reste à encaisser sur les ventes confirmées (lecture des factures sans droit comptable requis).
            rec.amount_unpaid = sum(Booking.sudo().search(agency + [
                ('state', '=', 'confirmed'), ('invoice_id.state', '=', 'posted'),
            ]).mapped('invoice_residual'))

    def action_view_vehicles_available(self):
        return {
            'name': 'Véhicules Disponibles',
            'type': 'ir.actions.act_window',
            'res_model': 'adk.travel.vehicle',
            'view_mode': 'kanban,list,form',
            'domain': [('state', '=', 'available')] + ([('agency_id', '=', self.agency_id.id)] if self.agency_id else []),
        }

    def action_view_trips_today(self):
        today = fields.Date.context_today(self)
        start, end = day_bounds_utc(self.env, today)
        return {
            'name': "Voyages du jour",
            'type': 'ir.actions.act_window',
            'res_model': 'adk.travel.trip',
            'view_mode': 'list,form',
            'domain': [
                ('departure_datetime', '>=', start),
                ('departure_datetime', '<=', end),
            ] + ([('agency_id', '=', self.agency_id.id)] if self.agency_id else []),
        }

    def action_refresh(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'adk.travel.dashboard',
            'view_mode': 'form',
            'target': 'main',
            'res_id': self.id,
        }

    @api.model
    def action_open_dashboard(self):
        dashboard = self.create({})
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tableau de Bord',
            'res_model': 'adk.travel.dashboard',
            'view_mode': 'form',
            'target': 'main',
            'res_id': dashboard.id,
        }
