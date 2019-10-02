"use strict"
class AppViewModel {
    constructor(chart) {
        this.chartSeries = ko.observable({})
        this.chart = chart;
        this.range = ko.observable(1);
        this.isLoading = ko.observable(false);
        this.units = {
            DEWP: '°C',
            TEMP: '°C',
            HUM: '%',
            PRES: 'hPa'
        };

        this.last_date = ko.observable("Keine Werte");
        this.last_time = ko.observable("");
        this.bme280_box_data = ko.observableArray();
        this.bme280_raum_data = ko.observableArray();
        this.relaymonitor_data = ko.observableArray();
        this.refresh(1);
    }
    async refresh(days) {
        days = days || 1;
        this.range(days);
        this.clearChart();
        this.isLoading(true);
        let response = await fetch('getStats?hours=' + (days * 24));
        this.isLoading(false);
        let data = await response.json();
        data.forEach(val => {
            val.UNIT = this.units[val.VALUETYPE]
        });

        let last_timestamp = Math.max(...data.map(val => val.LAST_TIMESTAMP));
        if (!isNaN(last_timestamp)) {
            let last = new Date(last_timestamp * 1000);
            this.last_date(last.toLocaleDateString('de-DE', { weekday: 'short', month: 'numeric', day: 'numeric' }));
            this.last_time(last.getHours() + ":" + ("00" + last.getMinutes()).slice(-2));
        }
        this.bme280_box_data(data.filter(val => val.SENSOR == 'BME280_BOX' && ['TEMP', 'HUM', 'DEWP'].indexOf(val.VALUETYPE) !== -1));
        this.bme280_raum_data(data.filter(val => val.SENSOR == 'BME280_RAUM' && ['TEMP', 'HUM', 'DEWP'].indexOf(val.VALUETYPE) !== -1));
        this.relaymonitor_data(data.filter(val => val.SENSOR == 'RELAYMONITOR' && ['CH1', 'CH2', 'CH3', 'CH4'].indexOf(val.VALUETYPE) !== -1));

    }

    clearChart() {
        let chartSeries = this.chartSeries();
        Object.keys(chartSeries).forEach(id => chartSeries[id].remove());
        this.chartSeries({});
        this.chart.redraw();
    }

    async addToChart(sensor, valuetype) {
        if (!(sensor || valuetype)) { return; }
        if (this.isLoading()) { return; }
        this.isLoading(true);
        let chartSeries = this.chartSeries();
        let id = sensor.toLowerCase() + "_" + valuetype.toLowerCase();

        if (chartSeries[id] === undefined) {
            let avgOver = 8 * 3600;
            if (this.range() <= 30) { avgOver = 15 * 60 }
            if (this.range() <= 7) { avgOver = 5 * 60 }
            if (this.range() <= 1) { avgOver = 1 * 60 }
            let response = await fetch('getPlotValues?sensor=' + sensor + '&valuetype=' + valuetype + '&hours=' + this.range() * 24 + '&avg_over=' + avgOver);
            let data = await response.json();

            chartSeries[id] = this.chart.addSeries({
                turboThreshold: 0,
                name: id,
                yAxis: valuetype.toLowerCase() == "hum" ? "hum" : "temp",
                data: data,
                states: { hover: { lineWidthPlus: 0 } },
                enableMouseTracking: false
            }, false);
        }
        else {
            chartSeries[id].remove();
            delete chartSeries[id];
        }

        this.chart.redraw();
        this.chartSeries(chartSeries);
        this.isLoading(false);
    }

    isSeriesDisplayed(sensor, valuetype) {
        sensor = sensor || '';
        valuetype = valuetype || '';
        let id = sensor.toLowerCase() + "_" + valuetype.toLowerCase();
        return ko.pureComputed(function () {
            if (id === '_') { return Object.keys(this.chartSeries()).length != 0; }
            else { return this.chartSeries()[id] !== undefined; }
        }, this);
    }

    getVal(value) {
        return value === undefined || value === null ? 'N/A' : value;
    }
}
