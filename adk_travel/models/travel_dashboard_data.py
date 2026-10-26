# -*- coding: utf-8 -*-
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

MONTHS_FR = ['Janv.', 'Févr.', 'Mars', 'Avr.', 'Mai', 'Juin',
             'Juil.', 'Août', 'Sept.', 'Oct.', 'Nov.', 'Déc.']


class TravelDashboardData(models.AbstractModel):
    """Données du tableau de bord « vue d'ensemble » d'ADK Agency Travel.

    Toutes les recherches passent par l'ORM : les règles d'accès (agences
    autorisées, multi-sociétés) s'appliquent à l'utilisateur connecté.
    """
    _name = 'adk.travel.dashboard.data'
    _description = "Données du tableau de bord ADK Agency Travel"

    @api.model
    def get_data(self, agency_id=0, period='all'):
        Agency = self.env['adk.travel.agency']
        Booking = self.env['adk.travel.booking']
        Trip = self.env['adk.travel.trip']
        Vehicle = self.env['adk.travel.vehicle']
        Employee = self.env['adk.travel.employee']
        Maintenance = self.env['adk.traval.maintenance']
        Closing = self.env['adk.travel.cash.closing']
        cur = self.env.company.currency_id
        now = fields.Datetime.now()
        today = fields.Date.context_today(self)

        agencies_all = Agency.search([])
        agencies = agencies_all.filtered(lambda a: a.id == agency_id) if agency_id else agencies_all
        days = {'30': 30, '90': 90, '365': 365}.get(period)
        since = now - timedelta(days=days) if days else None

        b_dom = [('agency_id', 'in', agencies.ids), ('state', '=', 'confirmed')]
        t_dom = [('agency_id', 'in', agencies.ids), ('state', '!=', 'cancelled')]
        if since:
            b_dom.append(('booking_date', '>=', since))
            t_dom.append(('departure_datetime', '>=', since))
        bookings = Booking.search(b_dom)
        trips = Trip.search(t_dom)
        lines = bookings.mapped('passenger_line_ids').filtered(lambda l: l.state == 'confirmed')
        vehicles = Vehicle.search([('agency_id', 'in', agencies.ids)])
        employees = Employee.search([('agency_id', 'in', agencies.ids)])

        def local_date(dt_):
            return fields.Datetime.context_timestamp(self, dt_).date()

        def fmt_dt(dt_):
            return fields.Datetime.context_timestamp(self, dt_).strftime('%d/%m · %H:%M') if dt_ else ''

        revenue = sum(bookings.mapped('amount_total'))
        due_bookings = bookings.filtered(lambda b: b.invoice_residual > 0)
        today_bookings = bookings.filtered(lambda b: b.booking_date and local_date(b.booking_date) == today)
        measured = trips.filtered(lambda t: t.state in ('in_progress', 'done', 'confirmed') and t.capacity)
        fill = round(sum(measured.mapped('fill_rate')) / len(measured) * 100, 1) if measured else 0.0

        kpis = {
            'revenue': revenue,
            'revenue_today': sum(today_bookings.mapped('amount_total')),
            'tickets': len(lines),
            'tickets_today': len(today_bookings.mapped('passenger_line_ids')),
            'bookings': len(bookings),
            'avg_ticket': round(revenue / len(lines)) if lines else 0,
            'due': sum(due_bookings.mapped('invoice_residual')),
            'due_count': len(due_bookings),
            'fill': fill,
            'trips': len(trips),
            'trips_done': len(trips.filtered(lambda t: t.state == 'done')),
            'trips_running': len(trips.filtered(lambda t: t.state == 'in_progress')),
            'trips_upcoming': len(trips.filtered(lambda t: t.state in ('draft', 'confirmed') and t.departure_datetime >= now)),
            'vehicles': len(vehicles),
            'vehicles_available': len(vehicles.filtered(lambda v: v.state == 'available')),
            'employees': len(employees),
        }

        # --- Répartitions ---
        classes = []
        for klass in lines.mapped('travel_class_id'):
            sub = lines.filtered(lambda l: l.travel_class_id == klass)
            classes.append({'key': klass.code or klass.name, 'label': klass.name, 'value': len(sub),
                            'amount': sum(sub.mapped('amount_total'))})
        methods = []
        for pm in bookings.mapped('payment_method_id'):
            sub = bookings.filtered(lambda b: b.payment_method_id == pm)
            methods.append({'key': str(pm.id), 'label': pm.name, 'value': len(sub),
                            'amount': sum(sub.mapped('amount_total'))})
        methods.sort(key=lambda r: -r['amount'])
        trip_state = [
            {'key': 'draft', 'label': "Planifiés", 'value': len(trips.filtered(lambda t: t.state == 'draft'))},
            {'key': 'confirmed', 'label': "Confirmés", 'value': len(trips.filtered(lambda t: t.state == 'confirmed'))},
            {'key': 'in_progress', 'label': "En route", 'value': kpis['trips_running']},
            {'key': 'done', 'label': "Terminés", 'value': kpis['trips_done']},
        ]
        fleet = [
            {'key': 'available', 'label': "Disponibles", 'value': len(vehicles.filtered(lambda v: v.state == 'available'))},
            {'key': 'en_route', 'label': "En route", 'value': len(vehicles.filtered(lambda v: v.state == 'en_route'))},
            {'key': 'maintenance', 'label': "En maintenance", 'value': len(vehicles.filtered(lambda v: v.state == 'maintenance'))},
            {'key': 'panne', 'label': "En panne", 'value': len(vehicles.filtered(lambda v: v.state == 'panne'))},
        ]

        # --- Recettes par ligne ---
        by_line = []
        for line in bookings.mapped('trip_id.line_id'):
            sub = bookings.filtered(lambda b: b.trip_id.line_id == line)
            by_line.append({'name': line.name, 'revenue': sum(sub.mapped('amount_total')),
                            'tickets': len(sub.mapped('passenger_line_ids').filtered(lambda l: l.state == 'confirmed'))})
        by_line.sort(key=lambda r: -r['revenue'])

        # --- Évolution sur 6 mois ---
        first = today.replace(day=1) - relativedelta(months=5)
        monthly = []
        for i in range(6):
            m0 = first + relativedelta(months=i)
            m1 = m0 + relativedelta(months=1)
            sub = bookings.filtered(lambda b: b.booking_date and m0 <= local_date(b.booking_date) < m1)
            monthly.append({'label': MONTHS_FR[m0.month - 1],
                            'bar': len(sub.mapped('passenger_line_ids').filtered(lambda l: l.state == 'confirmed')),
                            'line': sum(sub.mapped('amount_total'))})

        # --- Agences ---
        agency_rows = []
        for ag in agencies:
            ab = bookings.filtered(lambda b: b.agency_id == ag)
            at = trips.filtered(lambda t: t.agency_id == ag)
            am = at.filtered(lambda t: t.state in ('in_progress', 'done', 'confirmed') and t.capacity)
            agency_rows.append({
                'id': ag.id, 'name': ag.name, 'city': ag.city or '',
                'revenue': sum(ab.mapped('amount_total')),
                'tickets': len(ab.mapped('passenger_line_ids').filtered(lambda l: l.state == 'confirmed')),
                'trips': len(at),
                'fill': round(sum(am.mapped('fill_rate')) / len(am) * 100, 1) if am else 0.0,
            })
        agency_rows.sort(key=lambda r: -r['revenue'])

        # --- Guichets ---
        clos_dom = [('agency_id', 'in', agencies.ids), ('state', '=', 'validated')]
        if since:
            clos_dom.append(('date', '>=', since.date()))
        closings = Closing.search(clos_dom)
        sellers = []
        for emp in bookings.mapped('guichetier_id'):
            sub = bookings.filtered(lambda b: b.guichetier_id == emp)
            ec = closings.filtered(lambda c: c.guichetier_id == emp)
            sellers.append({
                'name': emp.name, 'agency': emp.agency_id.name,
                'bookings': len(sub),
                'tickets': len(sub.mapped('passenger_line_ids').filtered(lambda l: l.state == 'confirmed')),
                'revenue': sum(sub.mapped('amount_total')),
                'closings': len(ec), 'diff': sum(ec.mapped('amount_diff')),
            })
        sellers.sort(key=lambda r: -r['revenue'])

        # --- Listes ---
        upcoming = trips.filtered(lambda t: t.state in ('confirmed', 'in_progress')).sorted('departure_datetime')[:6]
        due_list = due_bookings.sorted(lambda b: -b.invoice_residual)[:5]
        maint = Maintenance.search([('vehicle_id', 'in', vehicles.ids), ('state', 'in', ('draft', 'in_progress'))],
                                   order='request_date desc', limit=4)
        mtype = dict(Maintenance._fields['maintenance_type'].selection)
        mstate = dict(Maintenance._fields['state'].selection)

        return {
            'today': today.strftime('%d/%m/%Y'),
            'currency': {'symbol': cur.symbol, 'position': cur.position, 'decimals': cur.decimal_places},
            'agencies_all': [{'id': a.id, 'name': a.name} for a in agencies_all],
            'kpis': kpis,
            'classes': classes, 'methods': methods, 'trip_state': trip_state, 'fleet': fleet,
            'by_line': by_line[:5], 'monthly': monthly,
            'agency_rows': agency_rows, 'sellers': sellers,
            'upcoming': [{
                'id': t.id, 'name': t.name, 'line': t.line_id.name, 'vehicle': t.vehicle_id.name,
                'when': fmt_dt(t.departure_datetime), 'running': t.state == 'in_progress',
                'booked': t.booked_seats, 'capacity': t.capacity,
                'fill': round(t.fill_rate * 100, 1), 'agency': t.agency_id.name,
            } for t in upcoming],
            'due_list': [{
                'id': b.id, 'name': b.name, 'who': b.client_name, 'amount': b.invoice_residual,
                'agency': b.agency_id.name,
            } for b in due_list],
            'maintenance': [{
                'id': r.id, 'vehicle': r.vehicle_id.name, 'type': mtype.get(r.maintenance_type),
                'state': mstate.get(r.state), 'issue': (r.issue_description or '')[:70],
                'panne': r.maintenance_type == 'panne',
            } for r in maint],
        }
