# -*- coding: utf-8 -*-
import io
import base64
import datetime
from collections import defaultdict

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.addons.adk_travel.models.utils import day_bounds_utc


class TravelReportWizard(models.TransientModel):
    _name = 'adk.travel.report.wizard'
    _description = 'Assistant de Rapport'

    date_start = fields.Date(string="Date de début", required=True, default=fields.Date.context_today)
    date_end = fields.Date(string="Date de fin", required=True, default=fields.Date.context_today)
    report_type = fields.Selection([
        ('line', "Par ligne / destination"),
        ('class', "Par classe de voyage"),
        ('vehicle', "Par véhicule"),
        ('agency', "Par agence"),
    ], string="Regrouper par", default='line', required=True)
    agency_id = fields.Many2one(
        'adk.travel.agency', string="Agence",
        default=lambda self: self.env['adk.travel.agency']._get_default_agency().id,
        help="Laissez vide pour inclure toutes les agences auxquelles vous avez accès.")
    line_id = fields.Many2one('adk.travel.line', string="Ligne (filtre)")
    vehicle_id = fields.Many2one('adk.travel.vehicle', string="Véhicule (filtre)")
    include_draft = fields.Boolean(
        string="Inclure les ventes non confirmées (brouillons)",
        default=False,
        help="Par défaut, seules les ventes au statut 'Confirmé' sont comptées. "
             "Cochez cette case pour inclure aussi les ventes en brouillon.")

    def _get_bookings(self):
        # Plage complète 24h/24h : du tout début de date_start (00:00:00)
        # jusqu'à la toute fin de date_end (23:59:59), quelle que soit l'heure
        # de la vente dans la journée.
        datetime_start, datetime_end = day_bounds_utc(self.env, self.date_start, self.date_end)
        domain = [
            ('booking_date', '>=', datetime_start),
            ('booking_date', '<=', datetime_end),
        ]
        if self.include_draft:
            domain.append(('state', '!=', 'cancelled'))
        else:
            domain.append(('state', '=', 'confirmed'))
        if self.agency_id:
            domain.append(('agency_id', '=', self.agency_id.id))
        if self.line_id:
            domain.append(('line_id', '=', self.line_id.id))
        if self.vehicle_id:
            domain.append(('vehicle_id', '=', self.vehicle_id.id))
        return self.env['adk.travel.booking'].search(domain)

    def action_print_report(self):
        bookings = self._get_bookings()
        if not bookings:
            raise UserError(self._no_result_message())
        return self.env.ref('adk_travel.action_report_line_profitability').report_action(bookings, data={
            'wizard_id': self.id,
            'report_type': self.report_type,
            'date_start': fields.Date.to_string(self.date_start),
            'date_end': fields.Date.to_string(self.date_end),
        })

    def _no_result_message(self):
        state_txt = _("toutes sauf annulées") if self.include_draft else _("Confirmé uniquement")
        return _(
            "Aucune vente trouvée du %(start)s au %(end)s (statut : %(state)s).\n"
            "Vérifiez que des ventes existent sur cette période et qu'elles ont bien été validées "
            "(bouton 'Confirmer la vente'), ou cochez 'Inclure les ventes non confirmées'.",
            start=self.date_start, end=self.date_end, state=state_txt)

    def action_view_bookings(self):
        bookings = self._get_bookings()
        return {
            'name': _("Ventes de la période"),
            'type': 'ir.actions.act_window',
            'res_model': 'adk.travel.booking',
            'view_mode': 'list,form',
            'domain': [('id', 'in', bookings.ids)],
        }

    def _group_key(self, line):
        if self.report_type == 'line':
            return line.trip_id.line_id.name or _('Non défini')
        elif self.report_type == 'class':
            return line.travel_class_id.name or _('Non défini')
        elif self.report_type == 'agency':
            return line.agency_id.name or _('Non défini')
        else:
            return line.trip_id.vehicle_id.name or _('Non défini')

    def action_export_excel(self):
        """Génère un export Excel (xlsx) directement, sans dépendance externe."""
        try:
            import xlsxwriter
        except ImportError:
            raise UserError(_("La librairie xlsxwriter n'est pas disponible sur ce serveur."))

        bookings = self._get_bookings()
        if not bookings:
            raise UserError(self._no_result_message())

        lines = bookings.mapped('passenger_line_ids').filtered(lambda l: l.state != 'cancelled')
        grouped = defaultdict(lambda: {'count': 0, 'trip_amount': 0.0, 'baggage_amount': 0.0, 'total': 0.0})
        for line in lines:
            key = self._group_key(line)
            grouped[key]['count'] += 1
            grouped[key]['trip_amount'] += line.price_unit
            grouped[key]['baggage_amount'] += line.baggage_fee
            grouped[key]['total'] += line.amount_total

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        agencies = bookings.mapped('agency_id')
        title = self.agency_id.name or (agencies.name if len(agencies) == 1 else _("Toutes les agences"))
        sheet = workbook.add_worksheet((_("Rapport") + ' ' + title)[:31].translate({ord(c): ' ' for c in '[]:*?/\\'}))
        bold = workbook.add_format({'bold': True, 'bg_color': '#4e73df', 'font_color': 'white'})
        money = workbook.add_format({'num_format': '#,##0'})

        headers = [_('Regroupement'), _('Nb Passagers'), _('Montant Trajets'), _('Montant Bagages'), _('Total')]
        for col, header in enumerate(headers):
            sheet.write(0, col, header, bold)

        row = 1
        grand_total = 0.0
        for key, vals in grouped.items():
            sheet.write(row, 0, key)
            sheet.write(row, 1, vals['count'])
            sheet.write(row, 2, vals['trip_amount'], money)
            sheet.write(row, 3, vals['baggage_amount'], money)
            sheet.write(row, 4, vals['total'], money)
            grand_total += vals['total']
            row += 1

        sheet.write(row, 0, _('TOTAL GÉNÉRAL'), bold)
        sheet.write(row, 4, grand_total, money)
        sheet.set_column(0, 0, 30)
        sheet.set_column(1, 4, 18)
        workbook.close()
        output.seek(0)

        attachment = self.env['ir.attachment'].create({
            'name': 'Rapport_%s_%s_%s.xlsx' % ((title or 'agences').replace(' ', '_'), self.date_start, self.date_end),
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'res_model': 'adk.travel.report.wizard',
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }
