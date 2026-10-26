# -*- coding: utf-8 -*-
import datetime
from odoo import models, fields, api, _
from .utils import day_bounds_utc


class TravelCashClosing(models.Model):
    _name = 'adk.travel.cash.closing'
    _description = 'Clôture de caisse journalière'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'adk.travel.agency.mixin']
    _order = 'date desc'

    name = fields.Char(string="Référence", required=True, copy=False, readonly=True, default=lambda self: _('Nouveau'))
    date = fields.Date(string="Date", default=fields.Date.context_today, required=True, tracking=True)
    guichetier_id = fields.Many2one('adk.travel.employee', string="Guichetière / Vendeur", required=True, tracking=True,
                                     domain="[('agency_id', '=', agency_id)]")
    booking_ids = fields.Many2many('adk.travel.booking', string="Ventes du jour", compute="_compute_bookings", store=True)
    amount_expected = fields.Monetary(string="Montant encaissé attendu (système)", compute="_compute_bookings", store=True, currency_field='currency_id')
    amount_counted = fields.Monetary(string="Montant compté (caisse)", tracking=True, currency_field='currency_id')
    amount_diff = fields.Monetary(string="Écart", compute="_compute_diff", store=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='agency_id.currency_id', string="Devise", store=True)
    state = fields.Selection([
        ('draft', "Brouillon"),
        ('validated', "Validée"),
    ], string="Statut", default='draft', tracking=True)
    notes = fields.Text(string="Observations")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nouveau')) == _('Nouveau'):
                vals['name'] = self.env['ir.sequence'].next_by_code('adk.travel.cash.closing') or _('Nouveau')
        return super().create(vals_list)

    @api.onchange('agency_id')
    def _onchange_agency_id(self):
        if self.guichetier_id and self.guichetier_id.agency_id != self.agency_id:
            self.guichetier_id = False

    @api.depends('guichetier_id', 'agency_id', 'date')
    def _compute_bookings(self):
        for rec in self:
            if not (rec.guichetier_id and rec.date):
                rec.booking_ids = [(5, 0, 0)]
                rec.amount_expected = 0.0
                continue
            datetime_start, datetime_end = day_bounds_utc(self.env, rec.date)
            bookings = self.env['adk.travel.booking'].search([
                ('guichetier_id', '=', rec.guichetier_id.id),
                ('agency_id', '=', rec.agency_id.id),
                ('state', '=', 'confirmed'),
                ('booking_date', '>=', datetime_start),
                ('booking_date', '<=', datetime_end),
            ])
            rec.booking_ids = [(6, 0, bookings.ids)]
            # Seul l'argent réellement encaissé (facture payée) est attendu en caisse.
            rec.amount_expected = sum(bookings.mapped('amount_paid'))

    @api.depends('amount_expected', 'amount_counted')
    def _compute_diff(self):
        for rec in self:
            rec.amount_diff = rec.amount_counted - rec.amount_expected

    def action_validate(self):
        self.write({'state': 'validated'})
