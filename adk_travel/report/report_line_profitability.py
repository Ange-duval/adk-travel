# -*- coding: utf-8 -*-
from collections import defaultdict
from odoo import models


class ReportLineProfitability(models.AbstractModel):
    _name = 'report.adk_travel.report_line_profitability_view'
    _description = 'Rapport de Rentabilité (moteur QWeb)'

    def _group_key(self, line, report_type):
        if report_type == 'line':
            return line.trip_id.line_id.name or 'Non défini'
        elif report_type == 'class':
            return line.travel_class_id.name or 'Non défini'
        elif report_type == 'agency':
            return line.agency_id.name or 'Non défini'
        else:
            return line.trip_id.vehicle_id.name or 'Non défini'

    def _get_report_values(self, docids, data=None):
        data = data or {}
        bookings = self.env['adk.travel.booking']

        # Source de vérité privilégiée : on redemande exactement les mêmes
        # ventes que celles calculées par l'assistant (évite tout souci de
        # transmission des docids d'une action à l'autre).
        wizard_id = data.get('wizard_id')
        if wizard_id:
            wizard = self.env['adk.travel.report.wizard'].browse(wizard_id).exists()
            if wizard:
                bookings = wizard._get_bookings()

        if not bookings and docids:
            bookings = self.env['adk.travel.booking'].browse(docids)

        report_type = data.get('report_type', 'line')
        agencies = bookings.mapped('agency_id')
        wizard_agency = self.env['adk.travel.report.wizard'].browse(wizard_id).exists().agency_id if wizard_id else False
        agency = wizard_agency or (agencies if len(agencies) == 1 else self.env['adk.travel.agency'])
        lines = bookings.mapped('passenger_line_ids').filtered(lambda l: l.state != 'cancelled')

        grouped = defaultdict(lambda: {'count': 0, 'trip_amount': 0.0, 'baggage_amount': 0.0, 'total': 0.0})
        for line in lines:
            key = self._group_key(line, report_type)
            grouped[key]['count'] += 1
            grouped[key]['trip_amount'] += line.price_unit
            grouped[key]['baggage_amount'] += line.baggage_fee
            grouped[key]['total'] += line.amount_total

        grand_total = sum(v['total'] for v in grouped.values())
        report_type_labels = {
            'line': 'Ligne / Destination',
            'class': 'Classe de voyage',
            'vehicle': 'Véhicule',
            'agency': 'Agence',
        }

        return {
            'doc_ids': docids,
            'doc_model': 'adk.travel.booking',
            'docs': bookings,
            'grouped_data': dict(grouped),
            'grand_total': grand_total,
            'report_type_label': report_type_labels.get(report_type, ''),
            'date_start': (data or {}).get('date_start'),
            'date_end': (data or {}).get('date_end'),
            'agency': agency,
            'header_name': agency.name or ', '.join(agencies.mapped('name')) or self.env.company.name,
            'company': self.env.company,
        }
