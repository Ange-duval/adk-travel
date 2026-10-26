/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { Component, onWillStart, onWillDestroy, useState } from "@odoo/owl";

// Intervalle d'actualisation automatique du Tableau de Bord (en millisecondes)
const REFRESH_INTERVAL_MS = 30000;

/**
 * Petit widget invisible-fonctionnel placé sur le formulaire du Tableau de Bord.
 * Il recharge périodiquement l'enregistrement courant afin de recalculer
 * les champs KPI (non stockés) sans que l'utilisateur ait à cliquer sur "Actualiser".
 */
class TravelDashboardAutoRefresh extends Component {
    static template = "adk_travel.DashboardAutoRefresh";
    static props = { ...standardWidgetProps };

    setup() {
        this.state = useState({
            refreshing: false,
            lastRefresh: new Date(),
        });
        this.intervalId = null;
        onWillStart(() => {
            this.intervalId = setInterval(() => this.refresh(), REFRESH_INTERVAL_MS);
        });
        onWillDestroy(() => {
            if (this.intervalId) {
                clearInterval(this.intervalId);
                this.intervalId = null;
            }
        });
    }

    async refresh() {
        if (this.state.refreshing) {
            return;
        }
        this.state.refreshing = true;
        try {
            await this.props.record.load();
        } catch (error) {
            // On n'interrompt jamais l'interface pour un souci d'auto-refresh silencieux
            console.warn("ADK Travel: échec de l'actualisation automatique du dashboard", error);
        } finally {
            this.state.refreshing = false;
            this.state.lastRefresh = new Date();
        }
    }
}

registry.category("view_widgets").add("travel_dashboard_autorefresh", {
    component: TravelDashboardAutoRefresh,
});
