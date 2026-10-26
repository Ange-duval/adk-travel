# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class TravelAgency(models.Model):
    """Agence de voyage de l'entreprise.

    Chaque entreprise qui installe le module enregistre ici ses propres agences.
    C'est le nom de l'agence (et non celui du module) qui apparaît sur les billets,
    les rapports et le tableau de bord.
    """
    _name = 'adk.travel.agency'
    _description = "Agence de voyage"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name'

    name = fields.Char(string="Nom de l'agence", required=True, tracking=True,
                       help="Ce nom apparaît sur les billets, les rapports et le tableau de bord.")
    code = fields.Char(string="Code", help="Code court de l'agence (ex : DLA-01).")
    sequence = fields.Integer(string="Ordre", default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string="Société", required=True, default=lambda self: self.env.company,
        help="Société comptable : les factures et paiements des ventes de l'agence sont enregistrés dans cette société.")
    currency_id = fields.Many2one(related='company_id.currency_id', string="Devise", readonly=True)

    # --- Identité visuelle et coordonnées (imprimées sur les billets et rapports)
    logo = fields.Image(string="Logo", max_width=512, max_height=512)
    street = fields.Char(string="Adresse")
    street2 = fields.Char(string="Complément d'adresse")
    zip = fields.Char(string="Code postal")
    city = fields.Char(string="Ville")
    state_id = fields.Many2one('res.country.state', string="Région / État",
                               domain="[('country_id', '=?', country_id)]")
    country_id = fields.Many2one('res.country', string="Pays")
    phone = fields.Char(string="Téléphone")
    email = fields.Char(string="Email")
    website = fields.Char(string="Site web")
    registration_number = fields.Char(
        string="N° d'immatriculation",
        help="RCCM, NIU, SIRET… affiché sur les billets et les rapports.")
    ticket_footer = fields.Text(
        string="Message en bas du billet",
        default=lambda self: _("Ce billet est personnel et non cessible. Présentez-le à l'embarquement "
                               "avec le QR code de vérification."))
    full_address = fields.Char(string="Adresse complète", compute='_compute_full_address')

    # --- Organisation
    manager_id = fields.Many2one('adk.travel.employee', string="Chef d'agence", tracking=True,
                                 domain="[('agency_id', '=', id)]")
    user_ids = fields.Many2many(
        'res.users', 'adk_travel_agency_user_rel', 'agency_id', 'user_id',
        string="Utilisateurs autorisés",
        help="Les utilisateurs listés ici (hors Administrateur Agence) ne voient que les données de cette agence. "
             "Si la liste est vide, l'agence est accessible à tous les utilisateurs du module.")

    # --- Facturation / encaissement
    sale_journal_id = fields.Many2one(
        'account.journal', string="Journal de vente",
        domain="[('type', '=', 'sale'), ('company_id', '=', company_id)]",
        help="Journal utilisé pour les factures de billets. Vide = journal de vente par défaut de la société.")
    auto_register_payment = fields.Boolean(
        string="Encaisser à la confirmation", default=True,
        help="Coché : à la confirmation de la vente, la facture est validée et le paiement est enregistré "
             "automatiquement dans le journal lié au mode de paiement (vente au comptant).\n"
             "Décoché : la facture est validée mais reste à payer (vente à crédit, paiement ultérieur "
             "depuis la Facturation).")
    default_payment_journal_id = fields.Many2one(
        'account.journal', string="Journal d'encaissement par défaut",
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]",
        help="Utilisé quand le mode de paiement choisi n'est lié à aucun journal.")

    # --- Statistiques
    employee_count = fields.Integer(compute='_compute_counts', string="Employés")
    vehicle_count = fields.Integer(compute='_compute_counts', string="Véhicules")
    trip_count = fields.Integer(compute='_compute_counts', string="Voyages")
    booking_count = fields.Integer(compute='_compute_counts', string="Ventes")

    _sql_constraints = [
        ('name_company_unique', 'UNIQUE(name, company_id)', "Une agence portant ce nom existe déjà."),
    ]

    @api.depends('street', 'street2', 'zip', 'city', 'state_id', 'country_id')
    def _compute_full_address(self):
        for rec in self:
            city_line = ' '.join(p for p in (rec.zip, rec.city) if p)
            parts = [rec.street, rec.street2, city_line, rec.state_id.name, rec.country_id.name]
            rec.full_address = ', '.join(p for p in parts if p)

    def _compute_counts(self):
        def count(model):
            data = self.env[model]._read_group([('agency_id', 'in', self.ids)], ['agency_id'], ['__count'])
            return {agency.id: cnt for agency, cnt in data}
        employees, vehicles = count('adk.travel.employee'), count('adk.travel.vehicle')
        trips, bookings = count('adk.travel.trip'), count('adk.travel.booking')
        for rec in self:
            rec.employee_count = employees.get(rec.id, 0)
            rec.vehicle_count = vehicles.get(rec.id, 0)
            rec.trip_count = trips.get(rec.id, 0)
            rec.booking_count = bookings.get(rec.id, 0)

    @api.constrains('manager_id')
    def _check_manager_agency(self):
        for rec in self:
            if rec.manager_id and rec.manager_id.agency_id != rec:
                raise ValidationError(_("Le chef d'agence doit faire partie de l'équipe de cette agence."))

    @api.model
    def _get_default_agency(self):
        """Agence proposée par défaut : celle de l'employé lié à l'utilisateur,
        sinon l'unique agence accessible, sinon rien."""
        employee = self.env['adk.travel.employee'].sudo().search(
            [('user_id', '=', self.env.uid), ('agency_id.active', '=', True)], limit=1)
        if employee:
            return employee.agency_id.with_env(self.env)
        agencies = self.search([], limit=2)
        return agencies if len(agencies) == 1 else self.browse()

    def _get_header_vals(self):
        """Valeurs d'en-tête utilisées par les rapports (nom, adresse, contacts)."""
        self.ensure_one()
        return {
            'name': self.name,
            'address': self.full_address,
            'phone': self.phone,
            'email': self.email,
            'registration': self.registration_number,
        }

    def _action_view(self, model, name, view_mode='list,form'):
        self.ensure_one()
        return {
            'name': name,
            'type': 'ir.actions.act_window',
            'res_model': model,
            'view_mode': view_mode,
            'domain': [('agency_id', '=', self.id)],
            'context': {'default_agency_id': self.id},
        }

    def action_view_employees(self):
        return self._action_view('adk.travel.employee', _("Équipe de l'agence"), 'list,kanban,form')

    def action_view_vehicles(self):
        return self._action_view('adk.travel.vehicle', _("Véhicules de l'agence"), 'kanban,list,form')

    def action_view_trips(self):
        return self._action_view('adk.travel.trip', _("Voyages de l'agence"), 'list,calendar,form')

    def action_view_bookings(self):
        return self._action_view('adk.travel.booking', _("Ventes de l'agence"))


class TravelAgencyMixin(models.AbstractModel):
    """Ajoute le champ « Agence » (obligatoire) aux modèles métier."""
    _name = 'adk.travel.agency.mixin'
    _description = "Mixin : rattachement à une agence"

    agency_id = fields.Many2one(
        'adk.travel.agency', string="Agence", required=True, index=True, ondelete='restrict',
        default=lambda self: self.env['adk.travel.agency']._get_default_agency().id)
