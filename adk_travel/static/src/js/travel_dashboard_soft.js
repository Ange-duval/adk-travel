/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const PALETTE = ["#8ec1e6", "#f2c48c", "#9ccfb4", "#c9bfd6", "#ee9a9a", "#a9d6d8"];
const TRIP_COLORS = { draft: "#c9bfd6", confirmed: "#8ec1e6", in_progress: "#f2c48c", done: "#9ccfb4" };
const FLEET_COLORS = { available: "#9ccfb4", en_route: "#8ec1e6", maintenance: "#f2c48c", panne: "#ee9a9a" };

export class AdkTravelSoftDashboard extends Component {
    static template = "adk_travel.SoftDashboard";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ loading: true, agency: 0, period: "all", data: null });
        this.periods = [
            { key: "30", label: "30 jours" },
            { key: "90", label: "3 mois" },
            { key: "365", label: "12 mois" },
            { key: "all", label: "Tout" },
        ];
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        this.state.data = await this.orm.call("adk.travel.dashboard.data", "get_data", [], {
            agency_id: this.state.agency,
            period: this.state.period,
        });
        this.state.loading = false;
    }
    async setAgency(id) { this.state.agency = id; await this.load(); }
    async setPeriod(key) { this.state.period = key; await this.load(); }

    // ---------- Formats ----------
    money(v) {
        const c = this.state.data.currency;
        const n = new Intl.NumberFormat("fr-FR", {
            minimumFractionDigits: c.decimals, maximumFractionDigits: c.decimals,
        }).format(v || 0);
        return c.position === "after" ? `${n} ${c.symbol}` : `${c.symbol} ${n}`;
    }
    short(v) {
        v = v || 0;
        if (Math.abs(v) >= 1e6) return (Math.round(v / 1e5) / 10).toString().replace(".", ",") + " M";
        if (Math.abs(v) >= 1e3) return Math.round(v / 1e3) + " k";
        return String(Math.round(v));
    }
    initials(name) {
        return (name || "?").split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase();
    }
    fillColor(rate) {
        if (rate >= 75) return "#9ccfb4";
        if (rate >= 40) return "#f2c48c";
        return "#ee9a9a";
    }
    diffColor(v) { return v < 0 ? "#d97676" : v > 0 ? "#5fae88" : "#9a91a3"; }
    sum(items) { return items.reduce((s, i) => s + i.value, 0); }

    // ---------- Graphiques ----------
    donut(items, colorOf) {
        const r = 54, C = 2 * Math.PI * r;
        const total = items.reduce((s, i) => s + i.value, 0);
        let acc = 0;
        return items.map((i, idx) => {
            const len = total ? (i.value / total) * C : 0;
            const seg = {
                ...i, color: colorOf(i, idx),
                dash: `${Math.max(len - 2, 0)} ${C - Math.max(len - 2, 0)}`, offset: -acc,
            };
            acc += len;
            return seg;
        });
    }
    get classDonut() { return this.donut(this.state.data.classes, (i, n) => PALETTE[n % PALETTE.length]); }
    get methodDonut() { return this.donut(this.state.data.methods, (i, n) => PALETTE[n % PALETTE.length]); }
    get tripDonut() { return this.donut(this.state.data.trip_state, (i) => TRIP_COLORS[i.key]); }
    get fleetDonut() { return this.donut(this.state.data.fleet, (i) => FLEET_COLORS[i.key]); }

    get ringDash() {
        const C = 2 * Math.PI * 54;
        const v = Math.min(Math.max(this.state.data.kpis.fill, 0), 100);
        return `${(v / 100) * C} ${C}`;
    }

    get chart() {
        const W = 640, H = 230, padL = 20, padR = 16, padT = 34, padB = 34;
        const months = this.state.data.monthly;
        const maxB = Math.max(...months.map((m) => m.bar), 1);
        const maxL = Math.max(...months.map((m) => m.line), 1);
        const step = (W - padL - padR) / months.length;
        const bw = Math.min(step * 0.5, 46);
        const ph = H - padT - padB;
        const bars = months.map((m, i) => {
            const h = (m.bar / maxB) * ph * 0.36;
            const x = padL + step * i + (step - bw) / 2;
            return { x, y: H - padB - h, w: bw, h, label: m.label, value: m.bar, cx: x + bw / 2 };
        });
        const pts = months.map((m, i) => ({
            x: padL + step * i + step / 2,
            y: padT + ph - (0.52 + 0.46 * (m.line / maxL)) * ph,
            label: this.short(m.line), has: m.line > 0,
        }));
        const drawn = pts.filter((p) => p.has);
        return { W, H, bars, drawn, line: drawn.map((p) => `${p.x},${p.y}`).join(" "), base: H - padB };
    }

    // ---------- Navigation ----------
    _dom(extra = [], field = "agency_id") {
        const d = [...extra];
        if (this.state.agency) d.push([field, "=", this.state.agency]);
        return d;
    }
    openList(name, model, domain = [], views = [[false, "list"], [false, "form"]]) {
        this.action.doAction({ type: "ir.actions.act_window", name, res_model: model, views, domain: this._dom(domain) });
    }
    openRecord(model, id) {
        this.action.doAction({ type: "ir.actions.act_window", res_model: model, res_id: id, views: [[false, "form"]] });
    }
    openSales(name = "Ventes", extra = []) { this.openList(name, "adk.travel.booking", [["state", "=", "confirmed"], ...extra]); }
    openTrips(name = "Voyages", extra = []) { this.openList(name, "adk.travel.trip", extra); }
    openFleet() { this.openList("Flotte", "adk.travel.vehicle"); }
    openDue() { this.openSales("Factures à encaisser", [["invoice_residual", ">", 0]]); }
}

registry.category("actions").add("adk_travel.soft_dashboard", AdkTravelSoftDashboard);
