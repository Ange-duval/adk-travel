# -*- coding: utf-8 -*-
{
    'name': 'ADK Agency Travel',
    'version': '18.0.2.1.0',
    'category': 'Services/Transport',
    'summary': "Gérez vos agences de voyage : vente de billets avec QR code, flotte, facturation et paiements Odoo, caisse et rapports — gratuit",
    'description': """
ADK Agency Travel
=================
Module de gestion d'agences de voyage pour Odoo 18.

* Onglet Agences : chaque entreprise enregistre ses agences (nom, logo, coordonnées)
* Le nom de l'agence apparaît sur les billets, rapports et tableau de bord
* Plusieurs agences : équipe, flotte, voyages, ventes et caisses par agence
* Guichet : achat multi-places, classes VIP/Éco, bagages avec suppléments
* Billets imprimables avec QR code
* Facturation intégrée : la confirmation génère la facture client Odoo et le paiement
* Clôture de caisse par agence, tableau de bord temps réel
* Rapports PDF/Excel : rentabilité par ligne, classe, véhicule ou agence
""",
    'author': 'Kambeu Henang Ange Duval',
    'website': '',
    'support': 'duvalkambeu61@gmail.com',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'web', 'account'],
    'data': [
        # 1. Sécurité
        'security/security.xml',
        'security/ir.model.access.csv',

        # 2. Séquences et données
        'data/ir_sequence_data.xml',
        'data/travel_data.xml',
        'data/travel_product_data.xml',

        # 3. Rapports (actions + templates QWeb)
        'report/report_agency_header.xml',
        'report/report_ticket_templates.xml',
        'report/report_cash_closing_templates.xml',
        'report/report_line_profitability_templates.xml',

        # 4. Vues métiers
        'views/travel_agency_views.xml',
        'views/travel_config_views.xml',
        'views/travel_employee_views.xml',
        'views/travel_vehicle_views.xml',
        'views/travel_booking_views.xml',
        'views/travel_trip_views.xml',
        'views/travel_cash_closing_views.xml',
        'views/adk_traval_maintenance_views.xml',
        'views/travel_dashboard_views.xml',
        'views/travel_dashboard_soft_views.xml',

        # 5. Wizards
        'wizard/travel_report_wizard_view.xml',

        # 6. Menus (chargé en dernier)
        'views/travel_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'adk_travel/static/src/scss/travel_dashboard_soft.scss',
            'adk_travel/static/src/js/travel_dashboard_soft.js',
            'adk_travel/static/src/xml/travel_dashboard_soft.xml',
            'adk_travel/static/src/js/travel_dashboard_autorefresh.js',
            'adk_travel/static/src/xml/travel_dashboard_autorefresh.xml',
        ],
    },
    'demo': [],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': True,
    'auto_install': False,
    'images': ['static/description/banner.travel.png'],
}
